from __future__ import annotations

import os
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional
from urllib.parse import urlparse, parse_qs

from fastapi import HTTPException, status

from app.db import DOWNLOADS_DIR, get_connection


# 1 並列制御用のロック（同時に1つだけ実行）
_DOWNLOAD_LOCK = Lock()


def _is_playlist_url(url: str) -> bool:
    """Determine if the given url likely represents a playlist.

    For now, we simply detect common patterns such as 'list=' query param or '/playlist' path.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    qs = parse_qs(parsed.query)
    if "list" in qs and qs["list"]:
        return True
    if parsed.path and "playlist" in parsed.path:
        return True
    return False


def _validate_download_type(download_type: str) -> None:
    if download_type not in {"video", "audio"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="download_type は 'video' または 'audio' を指定してください。",
        )


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="URLが不正です。http(s):// で始まる有効なURLを指定してください。",
        )
    if _is_playlist_url(url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="プレイリストURLは未対応です。",
        )


def _row_to_dict(row: Any) -> Dict[str, Any]:
    # sqlite3.Rowはdict-likeだがdictではないので、キーの存在チェックが必要
    keys = row.keys()
    return {
        "id": row["id"],
        "url": row["url"],
        "title": row["title"],
        "status": row["status"],
        "download_type": row["download_type"],
        "file_size": row["file_size"],
        "progress": row["progress"],
        "file_path": row["file_path"],
        "error_message": row["error_message"],
        "yt_dlp_params": row["yt_dlp_params"] if "yt_dlp_params" in keys else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _run_download_task(
    download_id: int,
    url: str,
    download_type: str,
    force_redownload: bool = False,
    yt_dlp_params: str | None = None,
) -> None:
    """Background download task serialized to run 1 at a time.

    - ステータス/進捗/サイズ/ファイルパス/エラーをDBに反映
    - 既存ファイルがある場合はスキップしてcompletedにする
    - プレイリストは事前バリデーションで弾かれている想定
    """
    # 遅延インポート（起動を軽くする）
    from yt_dlp import YoutubeDL

    last_filename: Optional[str] = None

    def _update_sql(query: str, params: tuple[Any, ...]) -> None:
        with get_connection() as conn_u:
            conn_u.execute(query, params)
            conn_u.commit()

    # 1 並列ロックで囲む
    with _DOWNLOAD_LOCK:
        # downloading に遷移
        _update_sql(
            "UPDATE downloads SET status = 'downloading', progress = 0, error_message = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (download_id,),
        )
        try:
            # 共通オプション
            base_opts: Dict[str, Any] = {
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                # "restrictfilenames": True,
                "overwrites": bool(force_redownload),
                "cachedir": False,
                "no_mtime": True,
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
                "outtmpl": str(DOWNLOADS_DIR / "%(title).150B [%(id)s].%(ext)s"),
                "add_header": ["Accept-Language: ja-JP"],
            }
            if download_type == "audio":
                base_opts["format"] = "bestaudio/best"
                base_opts["postprocessors"] = [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "320",
                    }
                ]

            # ユーザー指定の追加パラメータを反映
            if yt_dlp_params:
                import shlex

                try:
                    extra_args = shlex.split(yt_dlp_params)
                except ValueError as e:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"追加パラメータの解析に失敗しました: {e}",
                    )

                # YoutubeDLのCLIオプションをPython APIのパラメータに変換
                # 既知のオプションは直接マッピングし、それ以外はpostprocessor_argsやhttp_headersなどに振り分け
                # ここでは簡易的に--key value形式や--flag形式をdictに追加
                i = 0
                while i < len(extra_args):
                    arg = extra_args[i]
                    if arg.startswith("--"):
                        key = arg[2:].replace("-", "_")
                        # 値を伴うオプション
                        if i + 1 < len(extra_args) and not extra_args[i + 1].startswith(
                            "--"
                        ):
                            val = extra_args[i + 1]
                            # 特殊処理: add_headerはリストで
                            if key == "add_header":
                                base_opts.setdefault("add_header", []).append(val)
                            else:
                                base_opts[key] = val
                            i += 2
                        else:
                            # フラグ型
                            base_opts[key] = True
                            i += 1
                    else:
                        i += 1

            # メタ情報と期待されるファイル名を先に取得
            with YoutubeDL(base_opts) as ydl_probe:
                info_probe = ydl_probe.extract_info(url, download=False)
                title = (
                    info_probe.get("title") if isinstance(info_probe, dict) else None
                )
                if title:
                    _update_sql(
                        "UPDATE downloads SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (title, download_id),
                    )
                expected_path = Path(ydl_probe.prepare_filename(info_probe))

            # 既にファイルが存在する場合の挙動
            if expected_path.exists():
                if not force_redownload:
                    try:
                        size = expected_path.stat().st_size
                    except OSError:
                        size = 0
                    _update_sql(
                        "UPDATE downloads SET status = 'completed', file_path = ?, file_size = ?, progress = 100, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (str(expected_path), int(size), download_id),
                    )
                    return
                else:
                    # 再試行(強制)時は既存ファイルを削除して最初からやり直す
                    try:
                        expected_path.unlink()
                    except OSError:
                        pass

            # 進捗フック
            def _hook(d: Dict[str, Any]) -> None:
                nonlocal last_filename
                st = d.get("status")
                if st == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    downloaded = d.get("downloaded_bytes") or 0
                    progress = 0
                    if total:
                        try:
                            progress = int(
                                max(0, min(100, (downloaded * 100) // total))
                            )
                        except Exception:
                            progress = 0
                    filename = d.get("filename") or last_filename
                    if filename:
                        last_filename = filename
                    _update_sql(
                        "UPDATE downloads SET progress = ?, file_size = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (int(progress), int(total or 0), download_id),
                    )
                elif st == "finished":
                    filename = d.get("filename") or last_filename
                    if filename:
                        last_filename = filename
                        try:
                            size = os.path.getsize(filename)
                        except OSError:
                            size = 0
                        # ファイルパスは最後にexpected_pathで上書きするので、ここではサイズと進捗のみ更新
                        _update_sql(
                            "UPDATE downloads SET file_size = ?, progress = 100, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                            (int(size), download_id),
                        )

            run_opts = dict(base_opts)
            run_opts["progress_hooks"] = [_hook]

            # 実ダウンロード
            with YoutubeDL(run_opts) as ydl_run:
                ydl_run.extract_info(url, download=True)

            # 完了（冪等に最終反映）
            path_str = str(expected_path)
            try:
                size = os.path.getsize(path_str)
            except OSError:
                size = 0
            _update_sql(
                "UPDATE downloads SET status = 'completed', file_path = ?, file_size = ?, progress = 100, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (path_str, int(size), download_id),
            )
        except Exception as e:
            msg = str(e)
            if len(msg) > 500:
                msg = msg[:500]
            _update_sql(
                "UPDATE downloads SET status = 'error', error_message = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (msg, download_id),
            )

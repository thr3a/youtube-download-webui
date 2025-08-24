from __future__ import annotations

import shlex
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException, status
from yt_dlp import YoutubeDL

from app.cli_to_api import cli_to_api
from app.db import DOWNLOADS_DIR, get_connection

# 並列制御用のロック（同時に1つだけ実行）
_DOWNLOAD_LOCK = Lock()


# シンプルなロジック、URLに「list=」クエリや「/playlist」パスが含まれている場合はプレイリストとみなす
def _is_playlist_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    qs = parse_qs(parsed.query)
    if qs.get("list"):
        return True
    return bool(parsed.path and "playlist" in parsed.path)


def validate_download_type(download_type: str) -> None:
    if download_type not in {"video", "audio"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="download_type は 'video' または 'audio' を指定してください。",
        )


def validate_url(url: str) -> None:
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


def row_to_dict(row: Any) -> dict[str, Any]:
    # sqlite3.Rowはdict-likeだがdictではないので、キーの存在チェックが必要
    # DBカラム追加時にKeyErrorを防ぐため、yt_dlp_paramsのみ存在チェック
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


def run_download_task(
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
    last_filename: str | None = None
    final_path: str | None = None

    def _update_sql(query: str, params: tuple[Any, ...]) -> None:
        with get_connection() as conn_u:
            conn_u.execute(query, params)
            conn_u.commit()

    # 並列ロックで囲む（同時実行を防ぐ）
    with _DOWNLOAD_LOCK:
        # downloadingに変更
        _update_sql(
            "UPDATE downloads SET status = 'downloading', progress = 0, error_message = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (download_id,),
        )
        try:
            # yt-dlpのデフォルトオプション
            default_opts: dict[str, Any] = {
                "noplaylist": True,
                "quiet": False,
                "no_warnings": False,
                # "restrictfilenames": True,
                "overwrites": bool(force_redownload),
                "cachedir": False,
                "no_mtime": True,
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
                "outtmpl": str(DOWNLOADS_DIR / "%(title).150B [%(id)s].%(ext)s"),
                "add_header": ["Accept-Language: ja-JP"],
            }
            if download_type == "audio":
                default_opts["format"] = "bestaudio/best"
                default_opts["postprocessors"] = [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "320",
                    }
                ]

            # ユーザー指定の追加パラメータを反映
            user_opts: dict[str, Any] = {}
            if yt_dlp_params:
                try:
                    # 文字列をシェル引数として分割し、API用dictに変換
                    extra_args = shlex.split(yt_dlp_params)
                    user_opts = cli_to_api(extra_args)
                except ValueError as e:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"追加パラメータの解析に失敗しました: {e}",
                    ) from e

            # デフォルトオプションとユーザー指定オプションをマージ
            download_opts = dict(default_opts)
            download_opts.update(user_opts)

            # メタ情報と期待されるファイル名を先に取得
            with YoutubeDL(download_opts) as ydl_probe:
                info_probe = ydl_probe.extract_info(url, download=False)
                title = info_probe.get("title") if isinstance(info_probe, dict) else None
                if title:
                    _update_sql(
                        "UPDATE downloads SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (title, download_id),
                    )
                expected_path = Path(ydl_probe.prepare_filename(info_probe))

            # 既にファイルが存在する場合の挙動
            if expected_path.exists():
                if not force_redownload:
                    # 強制再DLでなければスキップしてcompletedに
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
            def _hook(d: dict[str, Any]) -> None:
                # yt-dlpの進捗情報をDBに反映
                nonlocal last_filename
                st = d.get("status")
                if st == "downloading":
                    # ダウンロード中: 進捗率・ファイルサイズを更新
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    downloaded = d.get("downloaded_bytes") or 0
                    progress = 0
                    if total:
                        try:
                            progress = int(max(0, min(100, (downloaded * 100) // total)))
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
                    # ダウンロード完了: ファイルサイズ・進捗100%を更新
                    filename = d.get("filename") or last_filename
                    if filename:
                        last_filename = filename
                        try:
                            size = Path(filename).stat().st_size
                        except OSError:
                            size = 0
                        # ファイルパスは最後にexpected_pathで上書きするので、ここではサイズと進捗のみ更新
                        _update_sql(
                            "UPDATE downloads SET file_size = ?, progress = 100, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                            (int(size), download_id),
                        )

            # ポストプロセッサフック
            def _postprocessor_hook(d: dict[str, Any]) -> None:
                nonlocal final_path
                st = d.get("status")
                if st == "finished":
                    # ポストプロセッサ完了: 最終ファイル名を取得
                    final_path = d.get("info_dict", {}).get("filepath")

            run_opts = dict(download_opts)
            run_opts["progress_hooks"] = [_hook]
            run_opts["postprocessor_hooks"] = [_postprocessor_hook]

            # 実ダウンロード
            with YoutubeDL(run_opts) as ydl_run:
                ydl_run.extract_info(url, download=True)

            # 完了時にDBへ最終情報を反映
            try:
                size = Path(final_path).stat().st_size
            except OSError:
                size = 0
            _update_sql(
                "UPDATE downloads SET status = 'completed', file_path = ?, file_size = ?, progress = 100, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (str(final_path), int(size), download_id),
            )
        except Exception as e:
            msg = str(e)
            if len(msg) > 500:
                msg = msg[:500]
            _update_sql(
                "UPDATE downloads SET status = 'error', error_message = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (msg, download_id),
            )

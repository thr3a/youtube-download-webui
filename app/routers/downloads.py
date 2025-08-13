"""Downloads API router.

Provides endpoints for:
- POST /api/downloads: 登録（DBにqueuedで作成）
- GET  /api/downloads: 履歴一覧取得
- GET  /api/downloads/{id}: 詳細取得
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qs

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.db import DOWNLOADS_DIR, get_connection

import os
from pathlib import Path
from threading import Lock

router = APIRouter(prefix="/api/downloads", tags=["downloads"])

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
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _run_download_task(
    download_id: int, url: str, download_type: str, force_redownload: bool = False
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
                "outtmpl": str(DOWNLOADS_DIR / "%(title)s [%(id)s].%(ext)s"),
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
            else:
                base_opts["format"] = "best"

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
                        _update_sql(
                            "UPDATE downloads SET file_path = ?, file_size = ?, progress = 100, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                            (str(filename), int(size), download_id),
                        )

            run_opts = dict(base_opts)
            run_opts["progress_hooks"] = [_hook]

            # 実ダウンロード
            with YoutubeDL(run_opts) as ydl_run:
                ydl_run.extract_info(url, download=True)

            # 完了（冪等に最終反映）
            path_str = str(last_filename) if last_filename else str(expected_path)
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


@router.get("", response_model=List[Dict[str, Any]])
def list_downloads() -> List[Dict[str, Any]]:
    """履歴一覧を新しい順で返す。"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM downloads ORDER BY id DESC",
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


@router.get("/{download_id}", response_model=Dict[str, Any])
def get_download(download_id: int) -> Dict[str, Any]:
    """単一エントリ取得。"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM downloads WHERE id = ?",
            (download_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return _row_to_dict(row)


@router.post("/{download_id}/retry", response_model=Dict[str, Any])
def retry_download(
    download_id: int, background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """ダウンロードの再試行（最初からやり直す）。

    - ダウンロード中以外の全ステータスで実行可能（completedも可）
    - 進捗/ファイル情報/エラー/タイトルを初期化しqueueへ戻す
    - 実行はバックグラウンドでforce_redownload=Trueとして再実行
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM downloads WHERE id = ?",
            (download_id,),
        ).fetchone()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Not found"
            )

        if row["status"] == "downloading":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="ダウンロード中は再試行できません。",
            )

        # 状態を初期化してキューへ戻す（最初から）
        conn.execute(
            """
            UPDATE downloads
               SET status = 'queued',
                   progress = 0,
                   file_size = 0,
                   file_path = NULL,
                   error_message = NULL,
                   title = NULL,
                   updated_at = CURRENT_TIMESTAMP
             WHERE id = ?
            """,
            (download_id,),
        )
        conn.commit()

        # バックグラウンド実行（強制再ダウンロード）
        background_tasks.add_task(
            _run_download_task, download_id, row["url"], row["download_type"], True
        )

        row2 = conn.execute(
            "SELECT * FROM downloads WHERE id = ?",
            (download_id,),
        ).fetchone()

    return _row_to_dict(row2)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Dict[str, Any])
def create_download(
    payload: Dict[str, Any], background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """新規ダウンロードの登録（DBにqueuedで作成）し、バックグラウンドで実行を開始する。

    Body:
      {
        "url": "https://...",
        "download_type": "video" | "audio"
      }
    """
    url: Optional[str] = payload.get("url")
    download_type: Optional[str] = payload.get("download_type")

    if not url or not isinstance(url, str):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="url は必須です。",
        )
    if not download_type or not isinstance(download_type, str):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="download_type は必須です。",
        )

    _validate_url(url)
    _validate_download_type(download_type)

    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO downloads (url, download_type, status)
            VALUES (?, ?, 'queued')
            """,
            (url, download_type),
        )
        new_id = cur.lastrowid
        conn.commit()

        row = conn.execute(
            "SELECT * FROM downloads WHERE id = ?",
            (new_id,),
        ).fetchone()

    # バックグラウンドで実処理をキュー（ロックにより1並列実行）
    background_tasks.add_task(_run_download_task, new_id, url, download_type)

    return _row_to_dict(row)

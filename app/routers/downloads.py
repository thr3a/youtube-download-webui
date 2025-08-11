"""Downloads API router.

Provides endpoints for:
- POST /api/downloads: 登録（DBにqueuedで作成）
- GET  /api/downloads: 履歴一覧取得
- GET  /api/downloads/{id}: 詳細取得
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qs

from fastapi import APIRouter, HTTPException, status

from app.db import get_connection

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


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


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Dict[str, Any])
def create_download(payload: Dict[str, Any]) -> Dict[str, Any]:
    """新規ダウンロードの登録（DBにqueuedで作成）。

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

    return _row_to_dict(row)

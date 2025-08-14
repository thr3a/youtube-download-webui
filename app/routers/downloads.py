"""Downloads API router.

Provides endpoints for:
- POST /api/downloads: 登録（DBにqueuedで作成）
- GET  /api/downloads: 履歴一覧取得
- GET  /api/downloads/{id}: 詳細取得
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import StreamingResponse

from app.db import get_connection
from app.routers.utils import (
    _row_to_dict,
    _validate_url,
    _validate_download_type,
    _run_download_task,
)

import os

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


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


def _file_iterator(file_path: str, chunk_size: int = 8192):
    """ファイルをチャンク単位で読み込むジェネレータ関数。"""
    with open(file_path, "rb") as file:
        while chunk := file.read(chunk_size):
            yield chunk


@router.get("/{download_id}/download")
def download_file(download_id: int) -> StreamingResponse:
    """指定されたIDのダウンロード済みファイルをクライアントに送信する。"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM downloads WHERE id = ?",
            (download_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    if row["status"] != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ダウンロードが完了していません。",
        )

    file_path = row["file_path"]
    print(file_path)
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ファイルが見つかりません。",
        )

    filename = os.path.basename(file_path)
    encoded_filename = quote(filename)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
        "Content-Type": "application/octet-stream",
    }

    return StreamingResponse(
        _file_iterator(file_path),
        headers=headers,
    )


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

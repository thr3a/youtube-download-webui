from __future__ import annotations

import pathlib
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.db import get_connection
from app.routers.utils import (
    _row_to_dict,
    _run_download_task,
    _validate_download_type,
    _validate_url,
)


class DownloadItem(BaseModel):
    id: int
    url: str
    download_type: str
    status: str
    progress: int
    file_size: int | None = None
    file_path: str | None = None
    error_message: str | None = None
    title: str | None = None
    yt_dlp_params: str | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": 1,
                    "url": "https://example.com/video",
                    "download_type": "video",
                    "status": "completed",
                    "progress": 100,
                    "file_size": 1048576,
                    "file_path": "/path/to/file.mp4",
                    "error_message": None,
                    "title": "Example Video",
                    "yt_dlp_params": "--write-thumbnail",
                }
            ]
        }
    }


class ErrorResponse(BaseModel):
    detail: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"detail": "Not found"},
                {"detail": "ダウンロード中は再試行できません。"},
            ]
        }
    }


class CreateDownloadRequest(BaseModel):
    url: str = Field(..., description="ダウンロード対象のURL")
    download_type: str = Field(..., description="ダウンロード種別 (video または audio)")
    yt_dlp_params: str | None = Field(None, description="yt-dlpに追加で渡すパラメータ")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "url": "https://example.com/video",
                    "download_type": "video",
                    "yt_dlp_params": "--write-thumbnail",
                }
            ]
        }
    }


router = APIRouter(prefix="/api/downloads", tags=["downloads"])


@router.get(
    "",
    summary="ダウンロード履歴一覧取得",
    description="登録済みのダウンロード履歴を新しい順に返します。",
    response_model=list[DownloadItem],
    response_description="ダウンロード履歴のリスト",
    responses={
        200: {"description": "成功時", "model": list[DownloadItem]},
    },
)
def list_downloads() -> list[dict[str, Any]]:
    """履歴一覧を新しい順で返す。"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM downloads ORDER BY id DESC",
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


@router.get(
    "/{download_id}",
    summary="ダウンロード詳細取得",
    description="指定されたIDのダウンロード情報を返します。",
    response_model=DownloadItem,
    responses={
        200: {"description": "成功時", "model": DownloadItem},
        404: {"description": "指定されたIDが存在しない場合", "model": ErrorResponse},
    },
)
def get_download(download_id: int) -> dict[str, Any]:
    """単一エントリ取得。"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM downloads WHERE id = ?",
            (download_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return _row_to_dict(row)


def _file_iterator(file_path: str, chunk_size: int = 8192) -> iter[bytes]:
    """ファイルをチャンク単位で読み込むジェネレータ関数。"""
    with open(file_path, "rb") as file:
        while chunk := file.read(chunk_size):
            yield chunk


@router.get(
    "/{download_id}/download",
    summary="ダウンロードファイル取得",
    description="指定されたIDのダウンロード済みファイルを返します。`status` が `completed` の場合のみ取得可能です。",
    responses={
        200: {"description": "ファイルストリームを返します"},
        400: {
            "description": "ダウンロードが完了していない場合",
            "model": ErrorResponse,
        },
        404: {
            "description": "ファイルまたはIDが存在しない場合",
            "model": ErrorResponse,
        },
    },
)
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
    if not file_path or not pathlib.Path(file_path).exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ファイルが見つかりません。",
        )

    filename = pathlib.Path(file_path).name
    encoded_filename = quote(filename)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
        "Content-Type": "application/octet-stream",
    }

    return StreamingResponse(
        _file_iterator(file_path),
        headers=headers,
    )


@router.post(
    "/{download_id}/retry",
    summary="ダウンロード再試行",
    description="指定されたIDのダウンロードを最初から再試行します。`downloading` 状態以外で実行可能です。",
    response_model=DownloadItem,
    responses={
        200: {"description": "再試行開始後のダウンロード情報", "model": DownloadItem},
        404: {"description": "指定されたIDが存在しない場合", "model": ErrorResponse},
        409: {
            "description": "ダウンロード中は再試行できません",
            "model": ErrorResponse,
        },
    },
)
def retry_download(download_id: int, background_tasks: BackgroundTasks) -> dict[str, Any]:
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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

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
            _run_download_task,
            download_id,
            row["url"],
            row["download_type"],
            True,
            row["yt_dlp_params"],
        )

        row2 = conn.execute(
            "SELECT * FROM downloads WHERE id = ?",
            (download_id,),
        ).fetchone()

    return _row_to_dict(row2)


@router.post(
    "",
    summary="新規ダウンロード登録",
    description="新しいダウンロードを登録し、バックグラウンドで実行を開始します。",
    status_code=status.HTTP_201_CREATED,
    response_model=DownloadItem,
    responses={
        201: {"description": "登録成功時のダウンロード情報", "model": DownloadItem},
        422: {"description": "入力値が不正な場合", "model": ErrorResponse},
    },
)
def create_download(payload: CreateDownloadRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    """新規ダウンロードの登録（DBにqueuedで作成）し、バックグラウンドで実行を開始する。

    Body:
      {
        "url": "https://...",
        "download_type": "video" | "audio",
        "yt_dlp_params": "--write-thumbnail"
      }
    """
    url: str | None = payload.url
    download_type: str | None = payload.download_type
    yt_dlp_params: str | None = payload.yt_dlp_params

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
            INSERT INTO downloads (url, download_type, status, yt_dlp_params)
            VALUES (?, ?, 'queued', ?)
            """,
            (url, download_type, yt_dlp_params),
        )
        new_id = cur.lastrowid
        conn.commit()

        row = conn.execute(
            "SELECT * FROM downloads WHERE id = ?",
            (new_id,),
        ).fetchone()

    # バックグラウンドで実処理をキュー（ロックにより1並列実行）
    background_tasks.add_task(_run_download_task, new_id, url, download_type, False, yt_dlp_params)

    return _row_to_dict(row)

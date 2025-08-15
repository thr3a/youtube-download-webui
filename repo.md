Directory Structure:
```
.
├── app
│   ├── __init__.py
│   ├── db.py
│   ├── main.py
│   └── routers
│       ├── __init__.py
│       ├── downloads.py
│       └── utils.py
└── pyproject.toml

```

---
File: app/db.py
---
"""SQLite database utilities for the YouTube download web UI.

- DB file: ./webui.db (project root)
- Table: downloads (created on startup if not exists)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "webui.db"
DOWNLOADS_DIR = ROOT_DIR / "downloads"


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    title TEXT,
    -- ステータス：キュー登録(queued), ダウンロード中(downloading), 完了(completed), エラー(error), キャンセル(canceled)
    status TEXT NOT NULL CHECK(status IN ('queued', 'downloading', 'completed', 'error', 'canceled')) DEFAULT 'queued',
    -- 保存形式：動画(video), 音声(audio)
    download_type TEXT NOT NULL CHECK(download_type IN ('video', 'audio')),
    file_size INTEGER NOT NULL DEFAULT 0,
    progress INTEGER NOT NULL DEFAULT 0,
    file_path TEXT,
    error_message TEXT,
    yt_dlp_params TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def get_connection() -> sqlite3.Connection:
    """Create a SQLite3 connection with sane defaults.

    Returns:
        sqlite3.Connection: connection with Row factory and timeouts set.
    """
    conn = sqlite3.connect(DB_PATH)
    # Return rows as dict-like objects
    conn.row_factory = sqlite3.Row
    # Avoid "database is locked" in light concurrent access
    conn.execute("PRAGMA busy_timeout = 5000;")
    # Safer journaling mode for concurrent readers/writers
    conn.execute("PRAGMA journal_mode = WAL;")
    # Enforce foreign keys (none yet, but good habit)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    """Initialize the database schema if it does not exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        # テーブル作成
        conn.executescript(SCHEMA_SQL)

        # マイグレーション: yt_dlp_params カラムの追加
        cursor = conn.execute("PRAGMA table_info(downloads)")
        columns = [row["name"] for row in cursor.fetchall()]
        if "yt_dlp_params" not in columns:
            conn.execute("ALTER TABLE downloads ADD COLUMN yt_dlp_params TEXT")

        conn.commit()

---
File: app/main.py
---
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .db import init_db
from .routers.downloads import router as downloads_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    """アプリ起動時にDBと保存先ディレクトリを初期化する。"""
    init_db()
    yield


app = FastAPI(
    title="YouTube ダウンロード WebUI",
    summary="yt-dlp を用いて動画/音声を1並列でダウンロードするシンプルな Web UI",
    description="YouTube などの動画 URL を登録し、バックグラウンドでダウンロードを実行。履歴管理・進捗表示・保存/再試行に対応。",
    version="1.0.0",
    openapi_tags=[
        {
            "name": "downloads",
            "description": "ダウンロード履歴の登録・取得・再試行・ファイル保存を扱うエンドポイント群。",
        },
    ],
    lifespan=lifespan,
)

# 静的ファイルとテンプレートの設定
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# 実装したDownloads API
app.include_router(downloads_router)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request) -> HTMLResponse:
    """トップページ: Jinja2テンプレートを返す。"""
    return templates.TemplateResponse(
        name="index.html",
        context={"request": request},
    )


@app.get("/health")
async def health() -> dict[str, str]:
    """ヘルスチェック用エンドポイント。"""
    return {"status": "ok"}

---
File: app/__init__.py
---

---
File: app/routers/utils.py
---
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

---
File: app/routers/downloads.py
---
"""Downloads API router.

Provides endpoints for:
- POST /api/downloads: 登録（DBにqueuedで作成）
- GET  /api/downloads: 履歴一覧取得
- GET  /api/downloads/{id}: 詳細取得
"""

from __future__ import annotations


from pydantic import BaseModel, Field
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
    response_model=List[DownloadItem],
    response_description="ダウンロード履歴のリスト",
    responses={
        200: {"description": "成功時", "model": List[DownloadItem]},
    },
)
def list_downloads() -> List[Dict[str, Any]]:
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
def create_download(
    payload: CreateDownloadRequest, background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """新規ダウンロードの登録（DBにqueuedで作成）し、バックグラウンドで実行を開始する。

    Body:
      {
        "url": "https://...",
        "download_type": "video" | "audio",
        "yt_dlp_params": "--write-thumbnail"
      }
    """
    url: Optional[str] = payload.url
    download_type: Optional[str] = payload.download_type
    yt_dlp_params: Optional[str] = payload.yt_dlp_params

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
    background_tasks.add_task(
        _run_download_task, new_id, url, download_type, False, yt_dlp_params
    )

    return _row_to_dict(row)

---
File: app/routers/__init__.py
---

---
File: pyproject.toml
---
[project]
name = "youtube-download-webui"
version = "0.1.0"
description = "Add your description here"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "fastapi[all]>=0.115.6",
    "jinja2>=3.1.6",
    "pytest>=8.4.1",
    "ruff>=0.8.4",
    "yt-dlp[curl-cffi,default]",
]

[tool.uv.sources]
yt-dlp = { url = "https://github.com/yt-dlp/yt-dlp/archive/master.tar.gz" }


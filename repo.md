Directory Structure:
```
.
├── app
│   ├── __init__.py
│   ├── cli_to_api.py
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
    -- ステータス：キュー登録(queued), ダウンロード中(downloading), 完了(completed), エラー(error),キャンセル(canceled)
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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


async def init_db() -> None:  # noqa: RUF029
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

import os
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .db import init_db
from .routers.downloads import router as downloads_router

security = HTTPBasic()


async def verify_username(request: Request) -> HTTPBasicCredentials:
    # 環境変数から認証情報を取得
    env_username = os.getenv("USERNAME")
    env_password = os.getenv("PASSWORD")

    # 環境変数が設定されていない場合はエラー
    if not env_username or not env_password:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="USERNAME or PASSWORD environment variable is not set",
        )

    credentials = await security(request)
    correct_username = secrets.compare_digest(credentials.username, env_username)
    correct_password = secrets.compare_digest(credentials.password, env_password)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect name or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    """アプリ起動時にDBと保存先ディレクトリを初期化する。"""
    await init_db()
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

app.include_router(downloads_router)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request) -> HTMLResponse:
    """トップページ: Jinja2テンプレートを返す。"""
    # ベーシック認証を適用
    await verify_username(request)
    return templates.TemplateResponse(
        name="index.html",
        context={"request": request},
    )


@app.get("/health")
async def health() -> dict[str, str]:
    """ヘルスチェック用エンドポイント。"""
    return {"status": "ok"}

---
File: app/cli_to_api.py
---
# ref: https://github.com/yt-dlp/yt-dlp/blob/master/devscripts/cli_to_api.py
import argparse
import pathlib
import sys

sys.path.insert(0, pathlib.Path(pathlib.Path(pathlib.Path(__file__).resolve()).parent).parent)

import yt_dlp
import yt_dlp.options

create_parser = yt_dlp.options.create_parser


def parse_patched_options(opts: list) -> argparse.Namespace:
    patched_parser = create_parser()
    # patched_parser.defaults.update(
    #     {
    #         "ignoreerrors": False,
    #         "retries": 0,
    #         "fragment_retries": 0,
    #         "extract_flat": False,
    #         "concat_playlist": "never",
    #         "update_self": False,
    #     }
    # )
    yt_dlp.options.create_parser = lambda: patched_parser
    try:
        return yt_dlp.parse_options(opts)
    finally:
        yt_dlp.options.create_parser = create_parser


default_opts = parse_patched_options([]).ydl_opts


def cli_to_api(opts: list, cli_defaults: bool = False) -> dict:
    opts = (yt_dlp.parse_options if cli_defaults else parse_patched_options)(opts).ydl_opts

    diff = {k: v for k, v in opts.items() if default_opts[k] != v}
    if "postprocessors" in diff:
        diff["postprocessors"] = [pp for pp in diff["postprocessors"] if pp not in default_opts["postprocessors"]]
    return diff


if __name__ == "__main__":
    from pprint import pprint

    print("\nThe arguments passed translate to:\n")
    pprint(cli_to_api(sys.argv[1:]))
    print("\nCombining these with the CLI defaults gives:\n")
    pprint(cli_to_api(sys.argv[1:], True))

---
File: app/__init__.py
---

---
File: app/routers/utils.py
---
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


def _row_to_dict(row: Any) -> dict[str, Any]:
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

---
File: app/routers/downloads.py
---
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
    file_size = row["file_size"]
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
        "Content-Type": "application/octet-stream",
        "Content-Length": str(file_size),
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
requires-python = ">=3.13"
dependencies = [
    "fastapi[all]>=0.115.6",
    "jinja2>=3.1.6",
    "pytest>=8.4.1",
    "ruff>=0.8.4",
    "yt-dlp[curl-cffi,default]>=2025.8.22.235700.dev0",
]

[tool.ruff]
line-length = 300
target-version = "py313"
exclude = [".git", ".ruff_cache", ".venv", ".vscode"]

[tool.ruff.lint]
preview = true
select = [
    "ANN", # type annotation
    "B",   # flake8-bugbear
    "D",   # pydocstyle
    "E",   # pycodestyle errors
    "F",   # pyflakes
    "I",   # isort
    "PTH", # use `pathlib.Path` instead of `os.path`
    "RUF", # ruff specific rules
    "SIM", # flake8-simplify
    "UP",  # pyupgrade
    "W",   # pycodestyle warnings
]
ignore = [
    "RUF001", # 文字列内の曖昧なUnicode文字を許容
    "ANN401", # 関数引数の型アノテーションがAnyでも許容
    "B007",   # ループ変数の未使用を許容
    "B008",   # デフォルト引数での関数呼び出しを許容
    "B905",   # strict=Trueなしのzip()使用を許容
    "COM812", # カンマの付け忘れを許容
    "COM819", # カンマ禁止違反を許容
    "D1",     # 公開モジュール・クラス・関数・メソッドのdocstring省略を許容
    "D203",   # クラスdocstring前の空行数（GoogleスタイルではD211優先のため無視）
    "D205",   # docstringの要約行と説明の間の空行数を無視
    "D212",   # 複数行docstringの要約行の位置（1行目開始）を無視
    "D213",   # 複数行docstringの要約行の位置（2行目開始）を無視
    "D400",   # docstringの1行目の末尾ピリオドを無視
    "D415",   # docstringの1行目の末尾句読点（ピリオド等）を無視
    "E114",   # コメント行のインデントが4の倍数でない場合を許容
    "G004",   # ログ出力でのf-string使用を許容
    "ISC001", # 1行での暗黙的な文字列連結を許容
    "ISC002", # 複数行での暗黙的な文字列連結を許容
    "PTH123", # open()のPath.open()置き換えを強制しない
    # "Q000",   # シングルクォート使用を許容（ダブルクォート推奨違反）
    "Q001",   # 複数行文字列でのシングルクォート使用を許容
    "Q002",   # docstringでのシングルクォート使用を許容
    "RUF002", # docstring内の曖昧なUnicode文字を許容
    "RUF003", # コメント内の曖昧なUnicode文字を許容
    "SIM105", # try-except-passをcontextlib.suppressで置き換えなくても許容
    "SIM108", # if-elseブロックを三項演算子にしなくても許容
    "SIM116", # 連続したif文を辞書にしなくても許容
    "UP038",  # isinstanceの(X, Y)をX | Yにしなくても許容（非推奨）
]
unfixable = [
    "F401", # unused import
    "F841", # unused variable
]

[tool.ruff.lint.per-file-ignores]
"__init__.py" = ["F401"]

[tool.ruff.lint.pydocstyle]
convention = "google"


from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .db import init_db
from .routers.downloads import router as downloads_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
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

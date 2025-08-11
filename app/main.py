from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .db import init_db
from .routers import items
from .routers.downloads import router as downloads_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    """アプリ起動時にDBと保存先ディレクトリを初期化する。"""
    init_db()
    yield


app = FastAPI(lifespan=lifespan)

# 静的ファイルとテンプレートの設定
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# 既存のサンプルルーター（必要なら残す）
app.include_router(items.router)
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

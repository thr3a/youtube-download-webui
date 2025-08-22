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

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from .db import init_db
from .routers import items
from .routers.downloads import router as downloads_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    # アプリ起動時にDBと保存先ディレクトリを初期化
    init_db()
    yield


app = FastAPI(lifespan=lifespan)

# 既存のサンプルルーター（必要なら残す）
app.include_router(items.router)
# 実装したDownloads API
app.include_router(downloads_router)


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    # 単一HTML（シンプルなSPA風）で実装
    return """<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>YouTube Download WebUI</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    :root {
      --bg: #0b0f14;
      --panel: #121822;
      --panel2: #0f1420;
      --text: #e6eefc;
      --muted: #9fb0c7;
      --accent: #4cc2ff;
      --accent-2: #6bffb3;
      --danger: #ff6b6b;
      --warn: #ffc857;
      --ok: #70e000;
      --border: #263041;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; padding: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans JP", "Helvetica Neue", Arial, "Apple Color Emoji", "Segoe UI Emoji";
      background: linear-gradient(180deg, #081017 0%, #0b0f14 100%);
      color: var(--text);
    }
    header {
      padding: 24px 16px;
      border-bottom: 1px solid var(--border);
      background: rgba(18, 24, 34, .6);
      position: sticky; top: 0; backdrop-filter: blur(8px);
    }
    .container { max-width: 980px; margin: 0 auto; padding: 16px; }
    h1 { margin: 0; font-size: 20px; letter-spacing: .02em; }
    .panel {
      background: linear-gradient(180deg, var(--panel) 0%, var(--panel2) 100%);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px;
      box-shadow: 0 10px 30px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.03);
    }
    .row { display: flex; gap: 8px; flex-wrap: wrap; }
    input[type="text"] {
      flex: 1 1 560px; min-width: 240px;
      padding: 12px 14px; border-radius: 10px; border: 1px solid var(--border);
      background: #0c121b; color: var(--text); outline: none;
    }
    input[type="text"]::placeholder { color: #5d708d; }
    .radios {
      display: inline-flex; align-items: center; gap: 10px;
      padding: 6px 10px; border: 1px solid var(--border); border-radius: 10px; background: #0c121b;
      color: var(--muted);
    }
    button.primary {
      background: linear-gradient(180deg, #2a9df4 0%, #1976d2 100%);
      color: white; border: 0; border-radius: 10px; padding: 12px 18px; font-weight: 600;
      cursor: pointer; box-shadow: 0 6px 16px rgba(25,118,210,.35);
    }
    button.primary:disabled { opacity: .6; cursor: not-allowed; }
    .history { margin-top: 18px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 10px 8px; border-bottom: 1px solid var(--border); vertical-align: middle; }
    th { text-align: left; color: var(--muted); font-weight: 600; font-size: 12px; letter-spacing: .05em; text-transform: uppercase; }
    .status {
      display: inline-flex; align-items: center; gap: 6px; font-size: 12px; padding: 4px 8px; border-radius: 999px; border: 1px solid var(--border);
      background: #0c121b; color: var(--muted);
    }
    .status.queued { color: #9fb0c7; }
    .status.downloading { color: var(--accent); border-color: rgba(76,194,255,.4); }
    .status.completed { color: var(--ok); border-color: rgba(112,224,0,.35); }
    .status.error { color: var(--danger); border-color: rgba(255,107,107,.4); }
    .status.canceled { color: var(--warn); border-color: rgba(255,200,87,.4); }
    .progress {
      height: 10px; background: #0c121b; border-radius: 999px; overflow: hidden; border: 1px solid var(--border);
      width: 160px;
    }
    .progress > span { display: block; height: 100%;
      background: linear-gradient(90deg, #33d9ff, #6bffb3);
      width: 0%;
      transition: width .3s ease;
    }
    .muted { color: var(--muted); }
    .btn {
      padding: 6px 10px; border-radius: 8px; border: 1px solid var(--border); background: #0c121b; color: var(--text); cursor: pointer;
    }
    .btn:disabled { opacity: .5; cursor: not-allowed; }
    .err { color: var(--danger); font-size: 12px; }
    .help { font-size: 12px; color: var(--muted); margin-top: 6px; }
    .footer-space { height: 24px; }
    .title-cell { max-width: 360px; }
    .nowrap { white-space: nowrap; }
  </style>
</head>
<body>
  <header>
    <div class="container">
      <h1>Youtube Download WebUI</h1>
    </div>
  </header>

  <main class="container">
    <section class="panel">
      <div class="row">
        <input id="url" type="text" placeholder="動画のURLを入力 (https://...)" />
        <div class="radios">
          <label><input type="radio" name="download_type" value="video" checked> 動画</label>
          <label><input type="radio" name="download_type" value="audio"> 音声のみ</label>
        </div>
        <button id="startBtn" class="primary">開始</button>
      </div>
      <div id="formError" class="help err" style="display:none;"></div>
      <div class="help">プレイリストURLは未対応 / 1並列ダウンロード。履歴はSQLite(./webui.db)に保存されます。</div>
    </section>

    <section class="panel history">
      <table>
        <thead>
          <tr>
            <th class="nowrap">ステータス</th>
            <th>タイトル</th>
            <th class="nowrap">形式</th>
            <th class="nowrap">サイズ</th>
            <th class="nowrap">進捗</th>
            <th>エラー</th>
            <th class="nowrap">操作</th>
          </tr>
        </thead>
        <tbody id="historyBody">
          <!-- rows -->
        </tbody>
      </table>
    </section>
    <div class="footer-space"></div>
  </main>

  <script>
    const $ = (q) => document.querySelector(q);
    const $$ = (q) => Array.from(document.querySelectorAll(q));

    function fmtBytes(bytes) {
      if (!bytes || bytes <= 0) return "-";
      const units = ["B","KB","MB","GB","TB"];
      const i = Math.floor(Math.log(bytes) / Math.log(1024));
      return (bytes / Math.pow(1024, i)).toFixed(1) + " " + units[i];
    }

    function statusClass(s) {
      return ["queued","downloading","completed","error","canceled"].includes(s) ? s : "";
    }

    function escapeHtml(s) {
      return (s ?? "").toString()
        .replaceAll("&","&")
        .replaceAll("<","<")
        .replaceAll(">",">");
    }

    function renderRows(items) {
      const tbody = $("#historyBody");
      if (!Array.isArray(items)) items = [];
      tbody.innerHTML = items.map(item => {
        const prog = Math.max(0, Math.min(100, Number(item.progress || 0)));
        const size = fmtBytes(Number(item.file_size || 0));
        const title = item.title ? escapeHtml(item.title) : "<span class='muted'>(未取得)</span>";
        const err = item.error_message ? "<div class='err'>" + escapeHtml(item.error_message) + "</div>" : "";
        const canSave = item.status === "completed" && item.file_path;
        const canRetry = item.status === "error" || item.status === "canceled";
        return `
          <tr>
            <td><span class="status ${statusClass(item.status)}">${escapeHtml(item.status)}</span></td>
            <td class="title-cell">${title}<div class="muted" style="font-size:12px;">${escapeHtml(item.url)}</div></td>
            <td class="nowrap">${escapeHtml(item.download_type)}</td>
            <td class="nowrap">${size}</td>
            <td class="nowrap">
              <div class="progress" title="${prog}%"><span style="width:${prog}%"></span></div>
            </td>
            <td>${err}</td>
            <td class="nowrap">
              <button class="btn" ${canSave ? "" : "disabled"} title="${canSave ? "保存" : "ダウンロード未完了"}">保存</button>
              <button class="btn" ${canRetry ? "" : "disabled"} title="${canRetry ? "再試行" : "エラー/キャンセル時のみ"}">再試行</button>
            </td>
          </tr>
        `;
      }).join("");
    }

    async function fetchHistory() {
      try {
        const res = await fetch("/api/downloads");
        if (!res.ok) throw new Error("一覧取得に失敗しました");
        const data = await res.json();
        renderRows(data);
      } catch (e) {
        console.error(e);
      }
    }

    async function registerDownload(url, download_type) {
      const errBox = $("#formError");
      errBox.style.display = "none";
      errBox.textContent = "";
      try {
        const res = await fetch("/api/downloads", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url, download_type }),
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error((body.detail) ?? ("登録に失敗しました (HTTP " + res.status + ")"));
        }
        await fetchHistory();
      } catch (e) {
        errBox.textContent = e.message || String(e);
        errBox.style.display = "block";
      }
    }

    function currentType() {
      const r = $$('input[name="download_type"]').find(x => x.checked);
      return r ? r.value : "video";
    }

    $("#startBtn").addEventListener("click", async () => {
      const url = $("#url").value.trim();
      if (!url) {
        const errBox = $("#formError");
        errBox.textContent = "URLを入力してください。";
        errBox.style.display = "block";
        return;
      }
      $("#startBtn").disabled = true;
      try {
        await registerDownload(url, currentType());
        $("#url").value = "";
      } finally {
        $("#startBtn").disabled = false;
      }
    });

    // 初期表示とポーリング（進捗や状態の自動更新のため）
    fetchHistory();
    setInterval(fetchHistory, 5000);
  </script>
</body>
</html>"""


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

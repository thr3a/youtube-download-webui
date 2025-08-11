const $ = (q) => document.querySelector(q);
const $$ = (q) => Array.from(document.querySelectorAll(q));

function fmtBytes(bytes) {
  if (!bytes || bytes <= 0) return "-";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return (bytes / Math.pow(1024, i)).toFixed(1) + " " + units[i];
}

function statusClass(s) {
  return ["queued", "downloading", "completed", "error", "canceled"].includes(s)
    ? s
    : "";
}

function escapeHtml(s) {
  return (s ?? "")
    .toString()
    .replaceAll("&", "&")
    .replaceAll("<", "<")
    .replaceAll(">", ">");
}

function renderRows(items) {
  const tbody = $("#historyBody");
  if (!Array.isArray(items)) items = [];
  tbody.innerHTML = items
    .map((item) => {
      const prog = Math.max(0, Math.min(100, Number(item.progress || 0)));
      const size = fmtBytes(Number(item.file_size || 0));
      const title = item.title
        ? escapeHtml(item.title)
        : "<span class='muted'>(未取得)</span>";
      const err = item.error_message
        ? "<div class='err'>" + escapeHtml(item.error_message) + "</div>"
        : "";
      const canSave = item.status === "completed" && item.file_path;
      const canRetry = item.status !== "downloading";
      return `
          <tr data-id="${item.id}">
            <td><span class="status ${statusClass(item.status)}">${escapeHtml(item.status)}</span></td>
            <td class="title-cell">${title}<div class="muted" style="font-size:12px;">${escapeHtml(item.url)}</div></td>
            <td class="nowrap">${escapeHtml(item.download_type)}</td>
            <td class="nowrap">${size}</td>
            <td class="nowrap">
              <div class="progress" title="${prog}%"><span style="width:${prog}%"></span></div>
            </td>
            <td>${err}</td>
            <td class="nowrap">
              <button class="btn btn-save" ${canSave ? "" : "disabled"} title="${
        canSave ? "保存" : "ダウンロード未完了"
      }">保存</button>
              <button class="btn btn-retry" ${canRetry ? "" : "disabled"} title="${
        canRetry ? "再試行" : "ダウンロード中は不可"
      }">再試行</button>
            </td>
          </tr>
        `;
    })
    .join("");
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
      throw new Error(
        body.detail ?? "登録に失敗しました (HTTP " + res.status + ")",
      );
    }
    await fetchHistory();
  } catch (e) {
    errBox.textContent = e.message || String(e);
    errBox.style.display = "block";
  }
}

async function retryDownload(id) {
  try {
    const res = await fetch(`/api/downloads/${id}/retry`, { method: "POST" });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(
        body.detail ?? "再試行に失敗しました (HTTP " + res.status + ")",
      );
    }
    await fetchHistory();
  } catch (e) {
    alert(e.message || String(e));
  }
}

document.getElementById("historyBody").addEventListener("click", async (e) => {
  const btn = e.target.closest("button");
  if (!btn) return;
  const tr = btn.closest("tr");
  if (!tr) return;
  const id = Number(tr.dataset.id);
  if (btn.classList.contains("btn-retry")) {
    btn.disabled = true;
    try {
      await retryDownload(id);
    } finally {
      btn.disabled = false;
    }
  }
});

function currentType() {
  const r = $$('input[name="download_type"]').find((x) => x.checked);
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

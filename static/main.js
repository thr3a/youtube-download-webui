const $ = (q) => document.querySelector(q);
const $$ = (q) => Array.from(document.querySelectorAll(q));

function fmtBytes(bytes) {
  if (!bytes || bytes <= 0) return "-";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return (bytes / Math.pow(1024, i)).toFixed(1) + " " + units[i];
}

function statusBadgeClass(s) {
  const base =
    "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold";
  switch (s) {
    case "queued":
      return base + " bg-gray-100 text-gray-700";
    case "downloading":
      return base + " bg-blue-100 text-blue-800";
    case "completed":
      return base + " bg-green-100 text-green-700";
    case "error":
      return base + " bg-red-100 text-red-700";
    case "canceled":
      return base + " bg-amber-100 text-amber-700";
    default:
      return base + " bg-gray-100 text-gray-700";
  }
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
        : '<span class="text-gray-500">(未取得)</span>';
      const err = item.error_message
        ? '<div class="text-red-700">' + escapeHtml(item.error_message) + "</div>"
        : "";
      const canSave = item.status === "completed" && item.file_path;
      const canRetry = item.status !== "downloading";
      const retryTitle = item.yt_dlp_params
        ? escapeHtml(item.yt_dlp_params)
        : canRetry
          ? "再試行"
          : "ダウンロード中は不可";
      return `
          <tr data-id="${item.id}">
            <td><span class="${statusBadgeClass(item.status)}">${escapeHtml(item.status)}</span></td>
            <td class="title-cell">${title}<div class="text-xs text-gray-500">${escapeHtml(item.url)}</div></td>
            <td class="whitespace-nowrap">${escapeHtml(item.download_type)}</td>
            <td class="whitespace-nowrap">${size}</td>
            <td class="whitespace-nowrap">
              <div class="w-32 h-2 bg-gray-200 rounded-md overflow-hidden" title="${prog}%">
                <span class="block h-full bg-blue-500 transition-all" style="width:${prog}%"></span>
              </div>
            </td>
            <td>${err}</td>
            <td class="whitespace-nowrap">
              <button class="btn btn-save inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md border border-green-300 text-green-700 bg-green-50 hover:bg-green-100 text-sm font-semibold disabled:opacity-50 disabled:cursor-not-allowed" ${canSave ? "" : "disabled"} title="${canSave ? "保存" : "ダウンロード未完了"}">保存</button>
              <button class="btn btn-retry inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md border border-blue-300 text-blue-800 bg-blue-50 hover:bg-blue-100 text-sm font-semibold disabled:opacity-50 disabled:cursor-not-allowed" ${canRetry ? "" : "disabled"} title="${retryTitle}">再試行</button>
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

async function registerDownload(url, download_type, yt_dlp_params) {
  const errBox = $("#formError");
  errBox.style.display = "none";
  errBox.textContent = "";
  try {
    const res = await fetch("/api/downloads", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, download_type, yt_dlp_params }),
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
  } else if (btn.classList.contains("btn-save")) {
    // 保存ボタンがクリックされたときの処理
    try {
      // 新しいタブでダウンロードリンクを開く
      window.open(`/api/downloads/${id}/download`, "_blank");
    } catch (error) {
      console.error("保存に失敗しました:", error);
      alert("保存に失敗しました。");
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
  const ytDlpParams = $("#ytDlpParams").value.trim();
  $("#startBtn").disabled = true;
  try {
    await registerDownload(url, currentType(), ytDlpParams);
    $("#url").value = "";
    $("#ytDlpParams").value = "";
  } finally {
    $("#startBtn").disabled = false;
  }
});

// 偽装ボタン
const impersonateBtn = document.getElementById("impersonateBtn");
if (impersonateBtn) {
  impersonateBtn.addEventListener("click", () => {
    const input = document.getElementById("ytDlpParams");
    if (!input) return;
    const flag = "--impersonate chrome:windows-10";
    const current = (input.value || "").trim();
    if (!current.includes(flag)) {
      input.value = current ? current + " " + flag : flag;
    }
    input.focus();
  });
}

// 初期表示とポーリング（進捗や状態の自動更新のため）
fetchHistory();
setInterval(fetchHistory, 2000);

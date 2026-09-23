/* 文件比对专家前端逻辑 */

const API_BASE = "";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

let currentResult = null;
let currentMarkdown = "";
let chatHistory = [];
let currentSessionId = null;

const oldInput = $("#old-pdf");
const newInput = $("#new-pdf");
const oldBox = $("#drop-old");
const newBox = $("#drop-new");
const compareBtn = $("#compare-btn");
const errorMsg = $("#error-msg");
const loading = $("#loading");

// ---------- 视图切换 ----------

function showView(name) {
  // name: upload | result | report | history
  ["upload-view", "result-view", "report-view", "history-view"].forEach((id) => {
    $("#" + id).classList.toggle("hidden", id !== name + "-view");
  });
  $("#nav-expert").classList.toggle("active", name === "upload" || name === "result" || name === "report");
  $("#nav-history").classList.toggle("active", name === "history");
}

$("#nav-expert").addEventListener("click", (e) => {
  e.preventDefault();
  showView(currentResult ? "result" : "upload");
});

$("#nav-history").addEventListener("click", (e) => {
  e.preventDefault();
  showView("history");
  loadHistory("");
});

function setupUpload(box, input, nameEl) {
  box.addEventListener("click", () => input.click());
  box.addEventListener("dragover", (e) => {
    e.preventDefault();
    box.classList.add("dragover");
  });
  box.addEventListener("dragleave", () => box.classList.remove("dragover"));
  box.addEventListener("drop", (e) => {
    e.preventDefault();
    box.classList.remove("dragover");
    const file = e.dataTransfer.files[0];
    if (file && file.type === "application/pdf") {
      input.files = e.dataTransfer.files;
      showFileName(box, nameEl, file.name);
    }
  });
  input.addEventListener("change", () => {
    const file = input.files[0];
    if (file) showFileName(box, nameEl, file.name);
  });
}

function showFileName(box, nameEl, name) {
  nameEl.textContent = name;
  box.classList.add("has-file");
  checkReady();
}

function checkReady() {
  compareBtn.disabled = !(oldInput.files[0] && newInput.files[0]);
}

setupUpload(oldBox, oldInput, $("#old-name"));
setupUpload(newBox, newInput, $("#new-name"));

compareBtn.addEventListener("click", async () => {
  errorMsg.textContent = "";
  const oldFile = oldInput.files[0];
  const newFile = newInput.files[0];
  if (!oldFile || !newFile) return;

  loading.classList.remove("hidden");
  const form = new FormData();
  form.append("old_pdf", oldFile);
  form.append("new_pdf", newFile);

  try {
    const res = await fetch(`${API_BASE}/api/compare`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) throw new Error(await res.text());
    currentResult = await res.json();

    // 同时生成报告
    const reportRes = await fetch(`${API_BASE}/api/report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentResult),
    });
    if (!reportRes.ok) throw new Error(await reportRes.text());
    const reportData = await reportRes.json();
    currentMarkdown = reportData.report_markdown;

    // 比对完成后服务端已创建持久化会话，后续问答都挂在这个会话下
    currentSessionId = currentResult.session_id || null;

    showResult(currentResult, reportData.report_html);
  } catch (err) {
    errorMsg.textContent = "比对失败：" + err.message;
  } finally {
    loading.classList.add("hidden");
  }
});

function showResult(result, reportHtml) {
  showView("result");

  const stats = result.stats;
  const comparableText = result.comparable ? "可比对" : "不可比对";
  $("#compare-meta").textContent =
    `${result.old_meta.filename || "旧版"} vs ${result.new_meta.filename || "新版"} · ${comparableText}`;

  $("#stats-badges").innerHTML = `
    <span class="stat-badge similar">相似 ${stats.similar || 0}</span>
    <span class="stat-badge modified">修改 ${stats.modified || 0}</span>
    <span class="stat-badge added">新增 ${stats.added || 0}</span>
    <span class="stat-badge deleted">删除 ${stats.deleted || 0}</span>
  `;

  $("#summary-box").innerHTML = `
    <strong>综合结论</strong>：${result.summary}<br/>
    <strong>风险等级</strong>：${result.risk_level}
  `;

  $("#report-body").innerHTML = reportHtml;
  chatHistory = [];
  $("#chat-history").innerHTML = "";
}

$("#view-report-btn").addEventListener("click", () => showView("report"));

$("#back-btn").addEventListener("click", () => showView("result"));

$("#copy-btn").addEventListener("click", async () => {
  const text = currentResult ? currentResult.summary : "";
  await navigator.clipboard.writeText(text);
  alert("结论已复制");
});

$("#download-md-btn").addEventListener("click", () => {
  const blob = new Blob([currentMarkdown], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "版本差异对比报告.md";
  a.click();
  URL.revokeObjectURL(url);
});

$("#restart-btn").addEventListener("click", () => {
  oldInput.value = "";
  newInput.value = "";
  $("#old-name").textContent = "";
  $("#new-name").textContent = "";
  oldBox.classList.remove("has-file");
  newBox.classList.remove("has-file");
  currentResult = null;
  currentMarkdown = "";
  chatHistory = [];
  currentSessionId = null;
  $("#chat-history").innerHTML = "";
  checkReady();
  showView("upload");
});

// 对话
const chatInput = $("#chat-input");
const chatSend = $("#chat-send");
const chatHistoryEl = $("#chat-history");

async function sendChat() {
  const q = chatInput.value.trim();
  if (!q || !currentResult) return;
  chatInput.value = "";
  addBubble("user", q, false, formatTs(new Date().toISOString()));
  chatHistory.push({ role: "user", content: q });

  chatSend.disabled = true;
  // 本地模型非流式生成可能要几十秒，先放个占位气泡，
  // 避免看起来像「发了没反应」
  const pendingEl = addBubble("assistant", "正在思考中…（本地模型生成需要一些时间）", true);
  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: q,
        context: currentResult,
        history: chatHistory.slice(-6),
        session_id: currentSessionId,
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    pendingEl.remove();
    addBubble("assistant", data.answer, false, formatTs(data.ts));
    chatHistory.push({ role: "assistant", content: data.answer });
  } catch (err) {
    pendingEl.remove();
    addBubble("assistant", "请求失败：" + err.message);
  } finally {
    chatSend.disabled = false;
  }
}

function formatTs(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    const p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  } catch {
    return "";
  }
}

function addBubble(role, text, pending = false, ts = "") {
  const div = document.createElement("div");
  div.className = `chat-bubble ${role}` + (pending ? " pending" : "");
  div.textContent = text;
  if (ts) {
    const t = document.createElement("span");
    t.className = "bubble-ts";
    t.textContent = ts;
    div.appendChild(t);
  }
  chatHistoryEl.appendChild(div);
  chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
  return div;
}

chatSend.addEventListener("click", sendChat);
chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendChat();
});

// ---------- 审核历史 ----------

const historyListEl = $("#history-list");
const historySearchEl = $("#history-search");
let historySearchTimer = null;

async function loadHistory(q) {
  historyListEl.innerHTML = `<div class="history-empty">加载中…</div>`;
  try {
    const res = await fetch(`${API_BASE}/api/sessions?q=${encodeURIComponent(q || "")}`);
    if (!res.ok) throw new Error(await res.text());
    const sessions = await res.json();
    renderHistory(sessions);
  } catch (err) {
    historyListEl.innerHTML = `<div class="history-empty">加载失败：${err.message}</div>`;
  }
}

function renderHistory(sessions) {
  if (!sessions.length) {
    historyListEl.innerHTML = `<div class="history-empty">没有找到会话。做一次比对后，记录会自动保存到这里。</div>`;
    return;
  }
  historyListEl.innerHTML = "";
  sessions.forEach((s) => {
    const el = document.createElement("div");
    el.className = "history-item";
    el.innerHTML = `
      <div class="history-item-top">
        <div class="history-item-title">${s.title}</div>
        <div class="history-item-time">${s.updated_at.replace("T", " ").slice(0, 16)}</div>
      </div>
      <div class="history-item-summary">${s.summary || ""}</div>
      <div class="history-item-foot">
        <div class="history-item-badges">
          <span class="stat-badge similar">相似 ${s.stats.similar || 0}</span>
          <span class="stat-badge modified">修改 ${s.stats.modified || 0}</span>
          <span class="stat-badge added">新增 ${s.stats.added || 0}</span>
          <span class="stat-badge deleted">删除 ${s.stats.deleted || 0}</span>
          <span class="stat-badge" style="background:#f0f2f7;color:var(--text-secondary)">💬 ${s.message_count}</span>
        </div>
        <div class="history-item-actions">
          <button class="secondary-btn restore-btn">恢复会话</button>
          <button class="link-danger delete-btn">删除</button>
        </div>
      </div>
    `;
    // restore 需要会话完整数据，删除只需要 id，各自独立处理
    el.querySelector(".restore-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      restoreSession(s.session_id);
    });
    el.querySelector(".delete-btn").addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!confirm(`确定删除会话「${s.title}」？删除后不可恢复。`)) return;
      await fetch(`${API_BASE}/api/sessions/${s.session_id}`, { method: "DELETE" });
      loadHistory(historySearchEl.value);
    });
    // 整卡点击也能恢复
    el.addEventListener("click", () => restoreSession(s.session_id));
    historyListEl.appendChild(el);
  });
}

async function restoreSession(sessionId) {
  loading.classList.remove("hidden");
  try {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}`);
    if (!res.ok) throw new Error(await res.text());
    const detail = await res.json();

    // 恢复 = 把会话里的比对结果、报告、对话全部还原到界面
    currentResult = detail.compare;
    currentResult.session_id = detail.session_id;
    currentSessionId = detail.session_id;
    currentMarkdown = detail.report_markdown || "";
    chatHistory = detail.messages.map((m) => ({ role: m.role, content: m.content }));

    showResult(detail.compare, detail.report_html || "");
    chatHistoryEl.innerHTML = "";
    detail.messages.forEach((m) => addBubble(m.role, m.content, false, formatTs(m.ts)));
  } catch (err) {
    alert("恢复会话失败：" + err.message);
  } finally {
    loading.classList.add("hidden");
  }
}

$("#history-refresh-btn").addEventListener("click", () => loadHistory(historySearchEl.value));
historySearchEl.addEventListener("input", () => {
  clearTimeout(historySearchTimer);
  historySearchTimer = setTimeout(() => loadHistory(historySearchEl.value), 300);
});

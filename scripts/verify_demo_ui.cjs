/**
 * 端到端校验离线 Demo（samples/ui-demo.html）的交互逻辑：
 * 用 jsdom 载入单文件 HTML，真实触发点击，走完
 *   载入示例 → 开始比对 → 看报告 → 差异问答 → 审核历史（搜索 / 恢复 / 删除）
 * 并检查会话是否真的落进 localStorage（刷新页面不丢）。
 *
 * 依赖：jsdom（装在隔离的 node 工作区，通过 NODE_PATH 引入）
 * 用法：node scripts/verify_demo_ui.cjs
 */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const htmlPath = path.join(__dirname, "..", "samples", "ui-demo.html");
const html = fs.readFileSync(htmlPath, "utf8");

const dom = new JSDOM(html, {
  runScripts: "dangerously",
  url: "http://localhost/ui-demo.html",
  pretendToBeVisual: true,
});
const { window } = dom;
const { document } = window;

// jsdom 未实现的浏览器 API，按测试需要打桩
window.confirm = () => true;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const $ = (s) => document.querySelector(s);
const visible = (id) => !$("#" + id).classList.contains("hidden");
const text = (s) => ($(s) ? $(s).textContent.trim() : "");

let failed = 0;
const check = (ok, msg) => {
  if (!ok) failed++;
  console.log(`  ${ok ? "✓" : "✗ FAIL"} ${msg}`);
};

(async () => {
  console.log("=== 步骤 1：载入示例文档并比对 ===");
  $("#demo-btn").click();
  check(text("#old-name") === "技术规格说明书_Rev01.pdf", "点击后旧版文件名已填入");
  check(text("#new-name") === "技术规格说明书_Rev03.pdf", "点击后新版文件名已填入");

  $("#compare-btn").click();
  const loadingShown = !$("#loading").classList.contains("hidden");
  check(loadingShown, "比对时出现 loading 遮罩");
  await sleep(900);

  check(visible("result-view"), "结果视图已显示");
  check(!$("#loading").classList.contains("hidden") === false, "比对结束后 loading 已关闭");
  const badges = $("#stats-badges").textContent.replace(/\s+/g, " ");
  console.log("     统计徽章:", badges);
  check(/相似 \d+/.test(badges) && /修改 \d+/.test(badges) && /新增 \d+/.test(badges) && /删除 \d+/.test(badges), "四类统计徽章齐全");
  check(text("#summary-box").includes("综合结论"), "结论摘要已渲染");
  check($("#report-body").innerHTML.includes("<del"), "报告含字符级删除高亮 <del>");
  check($("#report-body").innerHTML.includes("<ins"), "报告含字符级新增高亮 <ins>");
  check($("#trace").textContent.includes("比对流水线"), "执行过程记录已展示");
  check($("#store-tag").textContent.includes("无需后端"), "本地存储可用（顶部标识为默认态）");

  const idxRaw = window.localStorage.getItem("docdiff_demo_index_v1");
  const ids = JSON.parse(idxRaw || "[]");
  check(ids.length === 1, `会话已写入 localStorage 索引（当前 ${ids.length} 条）`);
  const saved = JSON.parse(window.localStorage.getItem("docdiff_demo_session_" + ids[0]) || "null");
  check(!!saved && saved.stats && saved.items.length > 0, "会话含完整比对结果（stats + items）");
  check(!!saved.report_markdown && !!saved.report_html, "会话含报告 Markdown 与 HTML");
  check((saved.messages || []).length === 1 && !!saved.messages[0].ts, "会话含带时间戳的初始消息");

  console.log("\n=== 步骤 2：差异问答（含时间戳与引用序号）===");
  $("#chat-input").value = "金额有什么变化？";
  $("#chat-send").click();
  await sleep(600);
  const bubbles = [...document.querySelectorAll(".chat-bubble")];
  check(bubbles.length === 3, `对话气泡数量正确（初始 1 + 用户 1 + 回答 1，实际 ${bubbles.length}）`);
  const answer = bubbles[bubbles.length - 1].textContent;
  check(answer.includes("["), "回答里带 [n] 引用序号");
  check(!document.querySelector(".chat-bubble.pending"), "「正在生成回答」占位气泡已被替换");
  const tsCount = document.querySelectorAll(".bubble-ts").length;
  check(tsCount === 3, `每条气泡都有时间戳（实际 ${tsCount} 条）`);
  const saved2 = JSON.parse(window.localStorage.getItem("docdiff_demo_session_" + ids[0]));
  check(saved2.messages.length === 3, `问答已落盘（会话内 ${saved2.messages.length} 条消息）`);

  console.log("\n=== 步骤 3：再比一次（验证多会话与历史列表）===");
  $(".scenario-btn[data-scenario='contract']").click();
  check(text("#old-name") === "采购合同_HT-2026-0311_v1.pdf", "切换到合同场景，文件名已更新");
  $("#compare-btn").click();
  await sleep(900);
  $("#chat-input").value = "有哪些风险点？";
  $("#chat-send").click();
  await sleep(600);

  const ids2 = JSON.parse(window.localStorage.getItem("docdiff_demo_index_v1"));
  check(ids2.length === 2, `两次比对生成两个会话（实际 ${ids2.length} 个）`);

  console.log("\n=== 步骤 4：审核历史（列表 / 搜索 / 恢复 / 删除）===");
  $("#nav-history").click();
  await sleep(100);
  check(visible("history-view"), "历史视图已显示");
  let items = document.querySelectorAll(".history-item");
  check(items.length === 2, `历史列表显示 2 条（实际 ${items.length} 条）`);
  const firstTitle = items[0].querySelector(".history-item-title").textContent;
  console.log("     首条标题:", firstTitle);
  check(firstTitle.includes("采购合同"), "列表按最近更新倒序，合同会话排在最前");
  check(/\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(items[0].querySelector(".history-item-time").textContent), "列表项显示更新时间");
  check(items[0].querySelector(".history-item-badges").textContent.includes("💬 3"), "列表项显示消息数 3");

  // 按对话内容搜索（只能命中聊天里出现过的词）
  $("#history-search").value = "风险点";
  $("#history-search").dispatchEvent(new window.Event("input", { bubbles: true }));
  await sleep(450);
  check(document.querySelectorAll(".history-item").length === 1, "按对话内容搜索命中 1 条");

  $("#history-search").value = "不存在的关键词xyz";
  $("#history-search").dispatchEvent(new window.Event("input", { bubbles: true }));
  await sleep(450);
  check($("#history-list").textContent.includes("没有匹配的会话"), "无结果时给出空态提示");

  $("#history-search").value = "";
  $("#history-search").dispatchEvent(new window.Event("input", { bubbles: true }));
  await sleep(450);

  // 恢复第一条第（合同场景）
  items = document.querySelectorAll(".history-item");
  items[0].querySelector(".restore-btn").click();
  await sleep(500);
  check(visible("result-view"), "恢复会话后回到结果视图");
  check($("#compare-meta").textContent.includes("采购合同"), "恢复的是合同场景的比对结果");
  check(document.querySelectorAll(".chat-bubble").length === 3, "恢复后对话记录一并还原");
  check($("#report-body").innerHTML.includes("字符级对比"), "恢复后报告可正常查看");

  // 删除
  $("#nav-history").click();
  await sleep(100);
  document.querySelectorAll(".history-item")[1].querySelector(".delete-btn").click();
  await sleep(100);
  check(document.querySelectorAll(".history-item").length === 1, "删除后列表剩 1 条");
  check(JSON.parse(window.localStorage.getItem("docdiff_demo_index_v1")).length === 1, "删除同步写入本地存储");

  console.log("\n=== 步骤 5：重新比对（状态复位）===");
  $("#nav-expert").click();
  $("#restart-btn") && $("#restart-btn").click();
  await sleep(100);
  check(visible("upload-view"), "重新比对后回到上传视图");
  check(text("#old-name") === "", "文件名已清空");
  check($("#trace").style.display === "none", "执行过程记录已隐藏");

  console.log(`\n===== 结果：${failed === 0 ? "全部通过" : failed + " 项失败"} =====`);
  window.close();
  process.exit(failed === 0 ? 0 : 1);
})().catch((err) => {
  console.error("FAIL 执行异常:", err);
  process.exit(1);
});

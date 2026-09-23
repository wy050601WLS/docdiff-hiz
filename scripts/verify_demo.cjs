/**
 * 离线校验 samples/ui-demo.html 中内联的比对引擎（不启动服务，也不需要浏览器）。
 * 做法：把 HTML 里的 <script> 内容抽出来，在 node 里 eval（UI 部分被 typeof document 守卫跳过），
 * 然后用内置的两套示例场景各跑一遍完整链路，打印统计结果。
 *
 * 用法: node scripts/verify_demo.cjs
 */
const fs = require("fs");
const path = require("path");

const htmlPath = path.join(__dirname, "..", "samples", "ui-demo.html");
const html = fs.readFileSync(htmlPath, "utf8");

const m = html.match(/<script>([\s\S]*?)<\/script>\s*<\/body>/);
if (!m) {
  console.error("FAIL: 未在 HTML 中找到内联脚本");
  process.exit(1);
}

const sandboxModule = { exports: {} };
new Function("module", "exports", "performance", m[1])(
  sandboxModule,
  sandboxModule.exports,
  { now: () => Date.now() }
);
const engine = sandboxModule.exports;

console.log("=== 引擎函数自检 ===");
console.log("相似度(完全相同)      =", engine.similarity("合同金额为 100 万元。", "合同金额为 100 万元。"));
console.log("相似度(金额改动)      =", engine.similarity("合同金额为 100 万元。", "合同金额为 150 万元。").toFixed(3));
console.log("相似度(完全不同)      =", engine.similarity("应用服务器数量：1 台。", "违约责任按合同总金额的 5% 计算。").toFixed(3));
console.log(
  "字符级 diff 示例      =",
  JSON.stringify(engine.charDiff("并发能力要求：不低于 200 QPS。", "并发能力要求：不低于 500 QPS。").filter((o) => o.type !== "equal"))
);

const LABEL = { similar: "一致", modified: "修改", added: "新增", deleted: "删除" };
let failed = 0;
const check = (ok, msg) => {
  if (!ok) failed++;
  console.log(`  ${ok ? "✓" : "✗ FAIL"} ${msg}`);
};

Object.entries(engine.SCENARIOS).forEach(([key, sc]) => {
  console.log(`\n================ 场景 ${key}：${sc.label} ================`);
  console.log(`文件：${sc.fileA}  vs  ${sc.fileB}`);

  const t0 = Date.now();
  const result = engine.computeDiff(sc.old, sc.new, { threshold: 0.6, window: 5 });
  const ms = Date.now() - t0;

  console.log("可比对:", result.comparable, "| 风险等级:", result.riskLevel, "| 耗时:", ms, "ms");
  console.log("统计:", JSON.stringify(result.stats));
  console.log("结论:", result.summary);

  const points = engine.collectRiskPoints(result.items);
  console.log("风险点:", points.length, "个 ->", points.slice(0, 4).map((p) => `[${p.seq}]${p.rule}`).join(" "));

  console.log("差异明细（前 10 条）：");
  result.items.slice(0, 10).forEach((it) => {
    const txt = it.status === "added" ? it.newText : it.status === "deleted" ? it.oldText : `${it.oldText} → ${it.newText}`;
    console.log(`  [${it.seq}] ${LABEL[it.status]}(${Math.round(it.score * 100)}%) ${txt}`);
  });

  const rep = engine.generateReport(result, [sc.fileA, sc.fileB]);
  console.log("报告章节:", rep.markdown.split("\n").filter((l) => l.startsWith("##")).join(" / "));
  console.log("HTML 长度:", rep.html.length, "| 含 <del>:", rep.html.includes("<del"), "| 含 <ins>:", rep.html.includes("<ins"));

  ["这两份文档有什么差别？", "金额有什么变化？", "有哪些风险点？", "有没有被删掉的条款？"].forEach((q) => {
    console.log(`  Q: ${q}\n  A: ${engine.answerQuestion(q, result).split("\n").join(" ⏎ ").slice(0, 120)}`);
  });

  console.log("断言：");
  check(result.comparable === true, "同源文档应判为可比对");
  check(result.stats.total === result.items.length, "统计总数与差异条目数一致");
  check(result.stats.total === Math.max(sc.old.length, sc.new.length) || result.stats.total <= sc.old.length + sc.new.length, "条目数在合理范围内");
  check(result.stats.modified > 0, "应识别出修改段落");
  check(result.stats.added > 0, "应识别出新增段落");
  check(rep.html.includes("<ins"), "报告 HTML 含字符级新增高亮 <ins>");
  check(engine.answerQuestion("金额有什么变化？", result).includes("["), "金额问答带 [n] 引用序号");
});

console.log(`\n===== 结果：${failed === 0 ? "全部通过" : failed + " 项失败"} =====`);
process.exit(failed === 0 ? 0 : 1);

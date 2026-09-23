"""离线验证脚本：不启动 Web 服务，直接跑通「解析 → 比对 → 报告」全链路。

用法:
    python scripts/verify_pipeline.py

用途:
    - 面试前自检环境是否可用
    - 对比对效果做快速验收
产物:
    samples/示例比对报告.md
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from docdiff.services.diff_engine import compute_diff  # noqa: E402
from docdiff.services.pdf_parser import parse_pdf  # noqa: E402
from docdiff.services.report_generator import generate_report  # noqa: E402
from docdiff.models.schemas import CompareResult  # noqa: E402


def main() -> int:
    """跑通全链路并打印关键指标。"""
    old_pdf = ROOT / "samples" / "技术规格说明书_Rev01.pdf"
    new_pdf = ROOT / "samples" / "技术规格说明书_Rev03.pdf"

    if not old_pdf.exists() or not new_pdf.exists():
        print("示例 PDF 不存在，请先执行: python scripts/make_samples.py")
        return 1

    old_paras, old_meta = parse_pdf(old_pdf)
    new_paras, new_meta = parse_pdf(new_pdf)
    print(f"[解析] 旧版 {old_meta['paragraphs']} 段（parser={old_meta['parser']}）")
    print(f"[解析] 新版 {new_meta['paragraphs']} 段（parser={new_meta['parser']}）")

    comparable, risk, summary, diffs = compute_diff(old_paras, new_paras)
    print(f"[比对] comparable={comparable} risk={risk}")
    print(f"[比对] {summary}")

    stats = {
        "similar": sum(1 for d in diffs if d.status.value == "similar"),
        "modified": sum(1 for d in diffs if d.status.value == "modified"),
        "added": sum(1 for d in diffs if d.status.value == "added"),
        "deleted": sum(1 for d in diffs if d.status.value == "deleted"),
        "total": len(diffs),
    }
    print(f"[比对] stats={stats}")

    result = CompareResult(
        comparable=comparable,
        summary=summary,
        risk_level=risk,
        stats=stats,
        diffs=diffs,
        old_meta=old_meta,
        new_meta=new_meta,
    )
    # 离线模式生成报告，不依赖本地模型是否在跑
    _, md = generate_report(result, use_llm=False)
    out = ROOT / "samples" / "示例比对报告.md"
    out.write_text(md, encoding="utf-8")
    print(f"[报告] 已写出 {out}")

    # 简单断言：应当识别出修改/新增/删除
    ok = comparable and (stats["modified"] + stats["added"]) > 0
    print("[结果] " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

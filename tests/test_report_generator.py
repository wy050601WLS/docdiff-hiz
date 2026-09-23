"""报告生成（离线规则引擎）单元测试。"""

from docdiff.models.schemas import CompareResult, DiffStatus, ParagraphDiff
from docdiff.services.report_generator import generate_report


def _make_result(comparable: bool = True) -> CompareResult:
    """构造一个包含风险关键词的比对结果。"""
    diffs = [
        ParagraphDiff(
            index=1,
            status=DiffStatus.SIMILAR,
            old_text="第一条 服务范围",
            new_text="第一条 服务范围",
            reason="基本一致",
        ),
        ParagraphDiff(
            index=2,
            status=DiffStatus.MODIFIED,
            old_text="合同金额为 100 万元。",
            new_text="合同金额为 150 万元。",
            reason="内容有改动",
            char_diff_html='合同金额为 <del class="diff-del">100</del><ins class="diff-ins">150</ins> 万元。',
        ),
        ParagraphDiff(
            index=3,
            status=DiffStatus.DELETED,
            old_text="保密期限为五年。",
            new_text=None,
            reason="旧版删除段落",
        ),
        ParagraphDiff(
            index=4,
            status=DiffStatus.ADDED,
            old_text=None,
            new_text="新增：验收标准需第三方检测。",
            reason="新版新增段落",
        ),
    ]
    return CompareResult(
        comparable=comparable,
        summary="共比对 4 组段落，风险等级中。",
        risk_level="中",
        stats={"similar": 1, "modified": 1, "added": 1, "deleted": 1, "total": 4},
        diffs=diffs,
        old_meta={"filename": "旧版.pdf"},
        new_meta={"filename": "新版.pdf"},
    )


def test_rule_report_contains_sections() -> None:
    """离线报告应包含核心结论、规则统计、差异明细等章节。"""
    html, md = generate_report(_make_result(), use_llm=False)
    for section in ["综合审核结论", "规则统计", "规则引擎分析", "差异明细"]:
        assert section in md
    assert "<h1>" in html


def test_rule_report_flags_risk_keywords() -> None:
    """命中「金额」关键词时应提示风险点。"""
    _, md = generate_report(_make_result(), use_llm=False)
    assert "金额" in md
    assert "风险点" in md


def test_uncomparable_report() -> None:
    """异源文档报告应给出不通过结论。"""
    _, md = generate_report(_make_result(comparable=False), use_llm=False)
    assert "不通过" in md
    assert "重新提交" in md or "核对文件" in md

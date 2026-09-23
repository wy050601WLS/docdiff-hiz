"""差异引擎单元测试。"""

from docdiff.services.diff_engine import compute_diff
from docdiff.services.pdf_parser import Paragraph


def test_similar_documents() -> None:
    """同一份文档应判定为基本一致。"""
    paragraphs = [Paragraph("第一条 服务范围"), Paragraph("乙方提供 AI 应用开发服务。")]
    comparable, risk, summary, diffs = compute_diff(paragraphs, paragraphs)
    assert comparable is True
    assert risk == "低"
    assert all(d.status.value == "similar" for d in diffs)


def test_modified_document() -> None:
    """单句插入式修改应被识别，并生成字符级 diff 标记。"""
    old = [Paragraph("乙方提供 AI 应用开发服务。")]
    new = [Paragraph("乙方提供 AI 应用开发与交付服务。")]
    comparable, risk, summary, diffs = compute_diff(old, new)
    assert comparable is True
    assert diffs[0].status.value == "modified"
    html = diffs[0].char_diff_html or ""
    # 插入式改动只会有 diff-ins，替换式改动会同时有 diff-del
    assert "diff-ins" in html or "diff-del" in html


def test_added_and_deleted() -> None:
    """新增与删除应分别识别。"""
    old = [Paragraph("旧条款 A"), Paragraph("共同条款")]
    new = [Paragraph("共同条款"), Paragraph("新条款 B")]
    comparable, risk, summary, diffs = compute_diff(old, new)
    statuses = [d.status.value for d in diffs]
    assert "deleted" in statuses
    assert "added" in statuses


def test_version_pair_with_changes() -> None:
    """同源版本对（少量改动）不应被误判为异源。"""
    old = [
        Paragraph("第一条 服务范围"),
        Paragraph("乙方提供 AI 应用开发服务，服务周期为 12 个月。"),
        Paragraph("第二条 交付标准"),
        Paragraph("交付物应通过甲方验收测试，性能指标不低于 200 QPS。"),
    ]
    new = [
        Paragraph("第一条 服务范围"),
        Paragraph("乙方提供 AI 应用开发与交付服务，服务周期为 18 个月。"),
        Paragraph("第二条 交付标准"),
        Paragraph("交付物应通过甲方验收测试，性能指标不低于 500 QPS。"),
    ]
    comparable, risk, summary, diffs = compute_diff(old, new)
    assert comparable is True
    assert any(d.status.value == "modified" for d in diffs)


def test_uncomparable_documents() -> None:
    """完全异源文档应判为不可比对。"""
    old = [Paragraph("服务器配置：CPU 8 核，内存 32GB，操作系统 Ubuntu 22.04。")]
    new = [Paragraph("个人简历：张三，5 年 Python 开发经验，期望薪资 25K。")]
    comparable, risk, summary, diffs = compute_diff(old, new)
    assert comparable is False
    assert risk == "高"
    assert "无法判定" in summary or "无对应关系" in summary

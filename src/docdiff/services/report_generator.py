"""报告生成服务。

两段式设计：
1. **规则引擎**（离线可用）——由差异明细直接推导结论、风险点与改进建议，
   不依赖大模型，保证系统在无网/无模型时依然可用。
2. **大模型润色**（可选）——在规则结论基础上生成更自然的审阅意见，
   失败时自动降级回规则版本，不会阻塞主流程。
"""

from typing import List, Tuple

from docdiff.models.schemas import CompareResult, DiffStatus, ParagraphDiff
from docdiff.services.llm_client import LLMClient, LLMUnavailableError


STATUS_LABEL = {
    DiffStatus.SIMILAR: "相似",
    DiffStatus.MODIFIED: "修改",
    DiffStatus.ADDED: "新增",
    DiffStatus.DELETED: "删除",
}

# 规则引擎：命中关键词即提示风险（对应「AI 除幻 = 规则引擎兜底」的思路）
RISK_KEYWORDS = {
    "金额": "涉及金额字段，需核对是否与审批口径一致",
    "价格": "涉及价格字段，需确认是否已走完定价审批",
    "交付": "交付相关条款变更，需同步项目排期与验收标准",
    "工期": "工期变更，需评估是否影响里程碑承诺",
    "责任": "责任条款变更，需法务确认权责边界",
    "违约": "违约条款变更，需重点复核罚则计算方式",
    "保密": "保密条款变更，需确认保密范围与期限",
    "验收": "验收标准变更，需确认可量化指标是否被稀释",
    "性能": "技术指标变更，需确认是否可达成",
    "数量": "数量字段变更，需与采购清单交叉核对",
}


def _hit_keywords(text: str) -> List[str]:
    """扫描文本命中的风险关键词。"""
    return [kw for kw in RISK_KEYWORDS if kw in text]


def _rule_based_analysis(result: CompareResult) -> str:
    """纯规则引擎：不依赖大模型，直接产出结构化审阅意见。"""
    stats = result.stats
    similar = stats.get("similar", 0)
    modified = stats.get("modified", 0)
    added = stats.get("added", 0)
    deleted = stats.get("deleted", 0)
    total = stats.get("total", 0) or 1
    change_rate = (modified + added + deleted) / total

    lines: List[str] = []
    lines.append(f"本次比对共覆盖 {total} 组段落，其中一致 {similar} 组，改动率约 {change_rate:.0%}。")

    if change_rate == 0:
        lines.append("两份文档内容一致，未发现实质性变更。")
        return "\n".join(lines)

    risk_points: List[str] = []
    for d in result.diffs:
        if d.status == DiffStatus.SIMILAR:
            continue
        text = f"{d.old_text or ''}{d.new_text or ''}"
        for kw in _hit_keywords(text):
            tip = RISK_KEYWORDS[kw]
            if tip not in risk_points:
                risk_points.append(f"[{d.index}] {tip}")
        # 大段删除单独提示
        if d.status == DiffStatus.DELETED and len(d.old_text or "") > 80:
            risk_points.append(f"[{d.index}] 存在大段内容被整段删除，需确认是否为误删")

    if risk_points:
        lines.append("")
        lines.append("需重点复核的风险点：")
        lines.extend(f"- {p}" for p in risk_points[:8])
    else:
        lines.append("未命中预设风险关键词，但仍建议人工复核改动段落。")

    if deleted > added and deleted > 0:
        lines.append("")
        lines.append("提示：删除条目多于新增条目，请确认新版是否遗漏了必要条款。")

    return "\n".join(lines)


def _format_diffs_for_llm(diffs: List[ParagraphDiff], limit: int = 60) -> str:
    """把差异列表整理成给 LLM 的文本（超长时截断，避免撑爆本地模型上下文）。"""
    lines: List[str] = []
    count = 0
    for d in diffs:
        if d.status == DiffStatus.SIMILAR:
            continue
        if count >= limit:
            lines.append(f"…… 其余 {sum(1 for x in diffs if x.status != DiffStatus.SIMILAR) - limit} 条差异已省略")
            break
        label = STATUS_LABEL.get(d.status, d.status)
        lines.append(f"[{d.index}] {label}：{d.reason}")
        if d.old_text:
            lines.append(f"  旧版：{d.old_text[:200]}")
        if d.new_text:
            lines.append(f"  新版：{d.new_text[:200]}")
        count += 1
    return "\n".join(lines) or "无明显差异"


def generate_report(result: CompareResult, *, use_llm: bool = True) -> Tuple[str, str]:
    """生成 HTML / Markdown 格式报告。

    Args:
        result: 比对结果
        use_llm: 是否允许调用大模型做增强。测试或离线演示可传 False。

    Returns:
        (html, markdown)
    """
    if not result.comparable:
        md = _uncomparable_report(result)
        return _markdown_to_html(md), md

    rule_text = _rule_based_analysis(result)

    # 大模型为可选增强；本地模型不在线或调用失败时自动降级
    llm_text = ""
    client = LLMClient()
    if use_llm and client.is_available():
        system_prompt = (
            "你是一名专业的文档审阅专家。请根据两份 PDF 文档的比对结果，"
            "用中文写一段 200 字以内的审阅意见，说明本次改动的性质、可能的风险以及建议。"
            "要求：结论先行、不要编造原文没有的信息、不要重复罗列差异清单。"
        )
        user_prompt = (
            f"综合结论：{result.summary}\n"
            f"风险等级：{result.risk_level}\n"
            f"统计：{result.stats}\n"
            f"规则引擎分析：\n{rule_text}\n\n"
            f"差异明细：\n{_format_diffs_for_llm(result.diffs)}"
        )
        try:
            llm_text = client.chat(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
            )
        except LLMUnavailableError:
            llm_text = ""

    markdown = _assemble_markdown(result, rule_text, llm_text)
    return _markdown_to_html(markdown), markdown


def _uncomparable_report(result: CompareResult) -> str:
    """异源文档时的兜底报告。"""
    return (
        "# 版本差异对比报告\n\n"
        "## 综合审核结论\n\n"
        "- 审核结果：不通过\n"
        "- 总体风险等级：高\n"
        f"- 结论：{result.summary}\n\n"
        "## 建议\n\n"
        "请确认上传的两份 PDF 是否为同一文档的不同版本。"
        "当前两份文档主题、结构完全无对应关系，系统无法提供有效的版本差异分析。"
        "建议核对文件选择是否正确后重新提交。"
    )


def _assemble_markdown(result: CompareResult, rule_text: str, llm_text: str) -> str:
    """组装最终 Markdown 报告。"""
    stats = result.stats
    passed = result.risk_level == "低"
    lines = [
        "# 版本差异对比报告",
        "",
        f"（{result.old_meta.get('filename', '旧版')} vs {result.new_meta.get('filename', '新版')}）",
        "",
        "## 综合审核结论",
        "",
        f"- 审核结果：{'通过' if passed else '不通过'}",
        f"- 总体风险等级：{result.risk_level}",
        f"- 结论：{result.summary}",
        "",
        "## 规则统计",
        "",
        f"- 共比对：{stats.get('total', 0)} 组",
        f"- 一致：{stats.get('similar', 0)}",
        f"- 修改：{stats.get('modified', 0)}",
        f"- 新增：{stats.get('added', 0)}",
        f"- 删除：{stats.get('deleted', 0)}",
        "",
        "## 规则引擎分析",
        "",
        rule_text,
        "",
    ]

    if llm_text:
        lines += ["## 大模型审阅意见", "", llm_text, ""]
    else:
        lines += [
            "## 大模型审阅意见",
            "",
            "（本地模型未启用或当前不可用，本次报告由规则引擎生成，不影响差异结论。）",
            "",
        ]

    lines += ["## 差异明细", ""]
    shown = 0
    for d in result.diffs:
        if d.status == DiffStatus.SIMILAR:
            continue
        label = STATUS_LABEL.get(d.status, d.status)
        lines.append(f"### {d.index}. {label} — {d.reason}")
        if d.old_text:
            lines.append(f"- 旧版：{d.old_text[:400]}")
        if d.new_text:
            lines.append(f"- 新版：{d.new_text[:400]}")
        if d.char_diff_html:
            lines.append(f"- 字符级对比：{d.char_diff_html}")
        lines.append("")
        shown += 1
        if shown >= 40:
            lines.append(f"…… 其余 {sum(1 for x in result.diffs if x.status != DiffStatus.SIMILAR) - shown} 条差异略")
            break

    return "\n".join(lines)


def _markdown_to_html(md: str) -> str:
    """极简 Markdown → HTML（标题 / 列表 / 加粗 / 段落）。"""
    html: List[str] = []
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            html.append("</ul>")
            in_list = False

    for line in md.splitlines():
        stripped = line.strip()
        if stripped.startswith("### "):
            close_list()
            html.append(f"<h3>{_inline_format(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            close_list()
            html.append(f"<h2>{_inline_format(stripped[3:])}</h2>")
        elif stripped.startswith("# "):
            close_list()
            html.append(f"<h1>{_inline_format(stripped[2:])}</h1>")
        elif stripped.startswith("- "):
            if not in_list:
                html.append("<ul>")
                in_list = True
            html.append(f"<li>{_inline_format(stripped[2:])}</li>")
        elif stripped == "":
            close_list()
        else:
            close_list()
            html.append(f"<p>{_inline_format(stripped)}</p>")
    close_list()
    return "\n".join(html)


def _inline_format(text: str) -> str:
    """行内加粗。"""
    import re

    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)

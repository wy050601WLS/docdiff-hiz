"""差异比对引擎：段落级匹配 + 字符级 diff。"""

import difflib
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from docdiff.config import settings
from docdiff.models.schemas import DiffStatus, ParagraphDiff
from docdiff.services.pdf_parser import Paragraph


def _normalize(text: str) -> str:
    """归一化文本用于相似度计算。"""
    text = re.sub(r"\s+", "", text)
    return text.lower()


def _paragraph_similarity(a: str, b: str) -> float:
    """基于 difflib 的字符级相似度，避免引入 embedding 模型依赖。"""
    return difflib.SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def _char_diff_html(old: str, new: str) -> str:
    """生成字符级 diff HTML（删除红底、新增绿底）。"""
    sm = difflib.SequenceMatcher(None, old, new)
    html_parts: List[str] = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            html_parts.append(old[i1:i2])
        elif op == "delete":
            html_parts.append(f'<del class="diff-del">{old[i1:i2]}</del>')
        elif op == "insert":
            html_parts.append(f'<ins class="diff-ins">{new[j1:j2]}</ins>')
        elif op == "replace":
            html_parts.append(f'<del class="diff-del">{old[i1:i2]}</del>')
            html_parts.append(f'<ins class="diff-ins">{new[j1:j2]}</ins>')
    return "".join(html_parts)


def _classify_pair(
    old: Optional[Paragraph],
    new: Optional[Paragraph],
) -> Tuple[DiffStatus, str, Optional[str]]:
    """对单个段落对做分类，并生成字符级 diff。"""
    if old is None and new is None:
        raise ValueError("old 和 new 不能同时为空")

    if old is None:
        return DiffStatus.ADDED, "新版新增段落", None
    if new is None:
        return DiffStatus.DELETED, "旧版删除段落", None

    sim = _paragraph_similarity(old.text, new.text)
    if sim >= 0.95:
        return DiffStatus.SIMILAR, f"基本一致（相似度 {sim:.0%}）", None
    if sim < settings.diff_similarity_threshold:
        # 相似度太低，视为无法对应
        return DiffStatus.MODIFIED, f"内容差异较大（相似度 {sim:.0%}）", _char_diff_html(old.text, new.text)

    return DiffStatus.MODIFIED, f"内容有改动（相似度 {sim:.0%}）", _char_diff_html(old.text, new.text)


def compute_diff(
    old_paragraphs: List[Paragraph],
    new_paragraphs: List[Paragraph],
) -> Tuple[bool, str, str, List[ParagraphDiff]]:
    """计算两份文档的差异。

    策略：
    1. 先按顺序做局部滑动窗口匹配（段落往往顺序一致）。
    2. 未匹配的段落按最近邻补充配对。
    3. 对整体做同源判定：若有效匹配率过低，判为异源文档。

    Returns:
        (是否可比对, 风险等级, 综合结论, 差异明细)
    """
    # 简单滑动窗口匹配
    matched_old = set()
    matched_new = set()
    pairs: List[Tuple[Optional[Paragraph], Optional[Paragraph]]] = []
    matched_scores: List[float] = []  # 记录所有配对段落的相似度，用于同源判定

    window = 5
    for i, op in enumerate(old_paragraphs):
        if i in matched_old:
            continue
        best_j: Optional[int] = None
        best_score = -1.0
        start = max(0, i - window)
        end = min(len(new_paragraphs), i + window + 1)
        for j in range(start, end):
            if j in matched_new:
                continue
            score = _paragraph_similarity(op.text, new_paragraphs[j].text)
            if score > best_score:
                best_score = score
                best_j = j
        if best_j is not None:
            # 无论是否达到阈值都记录分数：低于阈值说明是「强行配对」，
            # 这个分数是同源判定的关键依据
            matched_scores.append(best_score)
        if best_j is not None and best_score >= settings.diff_similarity_threshold:
            matched_old.add(i)
            matched_new.add(best_j)
            pairs.append((op, new_paragraphs[best_j]))

    # 处理未匹配的段落
    for i, op in enumerate(old_paragraphs):
        if i not in matched_old:
            pairs.insert(min(i, len(pairs)), (op, None))
    for j, np in enumerate(new_paragraphs):
        if j not in matched_new:
            # 找一个合适的位置插入
            insert_pos = min(j, len(pairs))
            pairs.insert(insert_pos, (None, np))

    # 生成差异项
    diffs: List[ParagraphDiff] = []
    idx = 1
    for old, new in pairs:
        status, reason, diff_html = _classify_pair(old, new)
        diffs.append(
            ParagraphDiff(
                index=idx,
                status=status,
                old_title=(f"{'#' * old.level} {old.text[:60]}" if old and old.level else None),
                old_text=old.text if old else None,
                new_title=(f"{'#' * new.level} {new.text[:60]}" if new and new.level else None),
                new_text=new.text if new else None,
                reason=reason,
                char_diff_html=diff_html,
            )
        )
        idx += 1

    # 同源判定
    total_pairs = len([d for d in diffs if d.status != DiffStatus.UNCOMPARABLE])
    if total_pairs == 0:
        return False, "高", "两份文档均无可识别文本内容，无法比对。", diffs

    modified = sum(1 for d in diffs if d.status == DiffStatus.MODIFIED)
    added = sum(1 for d in diffs if d.status == DiffStatus.ADDED)
    deleted = sum(1 for d in diffs if d.status == DiffStatus.DELETED)
    similar = sum(1 for d in diffs if d.status == DiffStatus.SIMILAR)

    # 同源判定：核心看「配对段落平均相似度」与「是否存在相似段落」
    # - 无任何相似段落，且平均相似度很低 → 两份文档没有对应关系，判为异源
    # - 平均相似度中等以上 → 视为同源版本对，差异是版本演进
    avg_score = sum(matched_scores) / len(matched_scores) if matched_scores else 0.0
    thin_match = similar == 0 and avg_score < 0.4
    if thin_match:
        relatedness = avg_score
        conclusion = (
            f"两份文档主题、结构无对应关系，平均段落相似度仅 {relatedness:.0%}，"
            f"无法判定为同一文档的不同版本（主题相关度约 {relatedness:.0%}）。"
            f"建议核对文件，上传同一文档的旧版与新版。"
        )
        return False, "高", conclusion, diffs

    risk = "低"
    if added + deleted > modified + similar:
        risk = "高"
    elif modified > similar:
        risk = "中"

    match_rate = similar / total_pairs if total_pairs else 0
    conclusion = (
        f"共比对 {total_pairs} 组段落：相似 {similar} 处、修改 {modified} 处、"
        f"新增 {added} 处、删除 {deleted} 处，平均段落相似度 {avg_score:.0%}，"
        f"整体匹配率约 {match_rate:.0%}，风险等级 {risk}。"
    )
    return True, risk, conclusion, diffs

"""对话服务：基于比对结果上下文回答问题。"""

import re
from datetime import datetime
from typing import List

from docdiff.models.schemas import ChatRequest, ChatResponse, CompareResult, DiffStatus
from docdiff.services.llm_client import LLMClient, LLMUnavailableError


def _build_context(result: CompareResult, limit: int = 40) -> str:
    """把比对结果压缩成对话上下文（限制条数，避免超出本地模型上下文窗口）。"""
    lines = [
        f"综合结论：{result.summary}",
        f"风险等级：{result.risk_level}",
        f"统计：相似 {result.stats.get('similar', 0)}，修改 {result.stats.get('modified', 0)}，"
        f"新增 {result.stats.get('added', 0)}，删除 {result.stats.get('deleted', 0)}",
        "差异明细（仅列出非相似项）：",
    ]
    count = 0
    for d in result.diffs:
        if d.status == DiffStatus.SIMILAR:
            continue
        if count >= limit:
            break
        old = (d.old_text or "")[:200]
        new = (d.new_text or "")[:200]
        lines.append(f"[{d.index}] {d.status.value}：{d.reason} | 旧版：{old} | 新版：{new}")
        count += 1
    return "\n".join(lines)


def _extract_references(answer: str) -> List[int]:
    """从回答中抽取引用的差异序号（如 [1]、[3]）。"""
    refs = re.findall(r"\[(\d+)\]", answer)
    return sorted({int(r) for r in refs})


def _offline_answer(request: ChatRequest) -> str:
    """大模型不可用时的离线兜底回答：直接把差异清单命中项返回给用户。"""
    if not request.context:
        return "本地模型当前不可用，且没有比对结果上下文，无法回答。"

    question = request.question
    hits: List[str] = []
    for d in request.context.diffs:
        if d.status == DiffStatus.SIMILAR:
            continue
        text = f"{d.old_text or ''}{d.new_text or ''}{d.reason}"
        # 简单关键词命中：把问题里的连续中文片段拿去匹配
        tokens = [t for t in re.findall(r"[\u4e00-\u9fa5]{2,}", question) if len(t) >= 2]
        if any(t in text for t in tokens):
            hits.append(f"[{d.index}] {d.reason}")

    if hits:
        return "（本地模型不可用，以下为规则引擎检索结果）\n" + "\n".join(hits[:10])
    return (
        "（本地模型不可用）本次比对共发现 "
        f"{request.context.stats.get('modified', 0)} 处修改、"
        f"{request.context.stats.get('added', 0)} 处新增、"
        f"{request.context.stats.get('deleted', 0)} 处删除，"
        f"整体风险等级为 {request.context.risk_level}。请确认本地 Ollama 服务已启动后重试。"
    )


def answer(request: ChatRequest) -> ChatResponse:
    """基于差异上下文回答用户问题。

    Args:
        request: 对话请求（含问题、比对上下文、历史消息）

    Returns:
        ChatResponse，包含回答文本与引用的差异序号
    """
    context = _build_context(request.context) if request.context else ""

    system_prompt = (
        "你是一名文档审阅助手。请根据提供的「PDF 差异比对结果」回答用户问题。"
        "回答需简明扼要，引用差异时请使用 [序号] 格式标注来源。"
        "如果问题超出比对结果范围，请明确说明。"
    )

    messages = [{"role": "system", "content": system_prompt}]
    if context:
        messages.append({"role": "system", "content": f"比对结果上下文：\n{context}"})
    # 只保留最近 6 条历史，避免本地模型上下文溢出
    for msg in request.history[-6:]:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": request.question})

    client = LLMClient()
    # 先用 3 秒快速探活：服务没起就立刻走离线兜底，
    # 而不是等 httpx 的 connect 超时（10 秒）甚至推理超时（300 秒）
    if not client.is_available():
        answer_text = _offline_answer(request)
    else:
        try:
            answer_text = client.chat(messages)
        except LLMUnavailableError:
            answer_text = _offline_answer(request)

    return ChatResponse(
        answer=answer_text,
        references=_extract_references(answer_text),
        ts=datetime.now().astimezone().isoformat(timespec="seconds"),
    )

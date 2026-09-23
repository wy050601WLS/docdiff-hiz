"""请求/响应模型。"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class DiffStatus(str, Enum):
    """差异类型。"""

    SIMILAR = "similar"  # 基本一致
    MODIFIED = "modified"  # 段落内容有改动
    ADDED = "added"  # 新版新增
    DELETED = "deleted"  # 旧版删除
    UNCOMPARABLE = "uncomparable"  # 无法比对（异源文档）


class ParagraphDiff(BaseModel):
    """单个段落的差异项。"""

    index: int = Field(..., description="差异序号")
    status: DiffStatus = Field(..., description="差异类型")
    old_title: Optional[str] = Field(None, description="旧版段落标题/定位")
    old_text: Optional[str] = Field(None, description="旧版段落原文")
    new_title: Optional[str] = Field(None, description="新版段落标题/定位")
    new_text: Optional[str] = Field(None, description="新版段落原文")
    reason: str = Field("", description="差异原因简述")
    char_diff_html: Optional[str] = Field(None, description="字符级 diff HTML")
    old_page: Optional[int] = Field(None, description="旧版所在页码（1 起，拿不到时为空）")
    new_page: Optional[int] = Field(None, description="新版所在页码（1 起，拿不到时为空）")


class CompareResult(BaseModel):
    """比对结果。"""

    comparable: bool = Field(..., description="是否可以比对")
    summary: str = Field(..., description="综合结论")
    risk_level: str = Field("低", description="总体风险等级")
    stats: dict = Field(default_factory=dict, description="差异统计")
    diffs: List[ParagraphDiff] = Field(default_factory=list, description="差异明细")
    old_meta: dict = Field(default_factory=dict, description="旧版文档元信息")
    new_meta: dict = Field(default_factory=dict, description="新版文档元信息")
    session_id: Optional[str] = Field(None, description="关联的会话 ID（持久化后回传）")


class ReportOut(BaseModel):
    """报告输出。"""

    report_html: str = Field(..., description="完整报告 HTML")
    report_markdown: str = Field(..., description="完整报告 Markdown")
    result: CompareResult = Field(..., description="结构化结果")


class ChatMessage(BaseModel):
    """对话消息。"""

    role: str = Field(..., description="user / assistant")
    content: str = Field(..., description="消息内容")
    ts: Optional[str] = Field(None, description="消息时间戳（持久化时由服务端生成）")


class ChatRequest(BaseModel):
    """对话请求。"""

    question: str = Field(..., description="用户问题")
    context: Optional[CompareResult] = Field(None, description="比对结果上下文")
    history: List[ChatMessage] = Field(default_factory=list, description="历史消息")
    session_id: Optional[str] = Field(None, description="会话 ID；传入则本次问答持久化到该会话")


class ChatResponse(BaseModel):
    """对话响应。"""

    answer: str = Field(..., description="模型回答")
    references: List[int] = Field(default_factory=list, description="引用的差异项序号")
    ts: Optional[str] = Field(None, description="回答时间戳（持久化时由服务端生成）")


class SessionSummary(BaseModel):
    """会话列表条目（不含差异明细大字段）。"""

    session_id: str = Field(..., description="会话 ID")
    title: str = Field("", description="会话标题")
    created_at: str = Field("", description="创建时间")
    updated_at: str = Field("", description="最近更新时间")
    summary: str = Field("", description="综合结论")
    risk_level: str = Field("", description="风险等级")
    stats: dict = Field(default_factory=dict, description="差异统计")
    message_count: int = Field(0, description="对话消息数")


class SessionDetail(BaseModel):
    """会话完整内容（用于恢复会话）。"""

    session_id: str = Field(..., description="会话 ID")
    title: str = Field("", description="会话标题")
    created_at: str = Field("", description="创建时间")
    updated_at: str = Field("", description="最近更新时间")
    compare: Optional[CompareResult] = Field(None, description="比对结果")
    report_html: str = Field("", description="报告 HTML")
    report_markdown: str = Field("", description="报告 Markdown")
    messages: List[ChatMessage] = Field(default_factory=list, description="全部对话消息")

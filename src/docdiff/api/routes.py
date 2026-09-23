"""FastAPI 路由。"""

import shutil
import uuid
from pathlib import Path
from typing import Annotated, List

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from docdiff.config import settings
from docdiff.models.schemas import (
    ChatRequest,
    ChatResponse,
    CompareResult,
    ReportOut,
    SessionDetail,
    SessionSummary,
)
from docdiff.services.chat_service import answer as chat_answer
from docdiff.services.diff_engine import compute_diff
from docdiff.services.history_store import HistoryStore
from docdiff.services.pdf_parser import parse_pdf
from docdiff.services.report_generator import generate_report

router = APIRouter(prefix="/api")
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
history = HistoryStore()


@router.post("/compare", response_model=CompareResult)
async def compare_pdfs(
    old_pdf: Annotated[UploadFile, File(description="旧版 PDF")],
    new_pdf: Annotated[UploadFile, File(description="新版 PDF")],
) -> CompareResult:
    """上传两份 PDF，返回结构化比对结果，并自动创建持久化会话。"""
    old_path = _save_upload(old_pdf)
    new_path = _save_upload(new_pdf)
    old_filename = old_pdf.filename or "文档A.pdf"
    new_filename = new_pdf.filename or "文档B.pdf"

    try:
        old_paragraphs, old_meta = parse_pdf(
            old_path, max_pages=settings.parse_max_pages, prefer=settings.parse_prefer
        )
        new_paragraphs, new_meta = parse_pdf(
            new_path, max_pages=settings.parse_max_pages, prefer=settings.parse_prefer
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        # 解析完即可删除临时文件
        old_path.unlink(missing_ok=True)
        new_path.unlink(missing_ok=True)

    comparable, risk, summary, diffs = compute_diff(old_paragraphs, new_paragraphs)
    stats = {
        "similar": sum(1 for d in diffs if d.status.value == "similar"),
        "modified": sum(1 for d in diffs if d.status.value == "modified"),
        "added": sum(1 for d in diffs if d.status.value == "added"),
        "deleted": sum(1 for d in diffs if d.status.value == "deleted"),
        "total": len(diffs),
    }

    result = CompareResult(
        comparable=comparable,
        summary=summary,
        risk_level=risk,
        stats=stats,
        diffs=diffs,
        old_meta=old_meta,
        new_meta=new_meta,
    )

    # 持久化：每次比对都落一个会话，服务重启不丢
    try:
        result.session_id = history.create(result, title=f"{old_filename} vs {new_filename}")
    except Exception:  # noqa: BLE001
        # 历史记录写失败不影响比对主流程
        pass
    return result


@router.post("/report", response_model=ReportOut)
async def generate_report_endpoint(result: CompareResult) -> ReportOut:
    """根据比对结果生成 HTML / Markdown 报告，并回存到所属会话。"""
    html, md = generate_report(result)
    if result.session_id:
        try:
            history.set_report(result.session_id, html, md)
        except Exception:  # noqa: BLE001
            pass
    return ReportOut(report_html=html, report_markdown=md, result=result)


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    """基于比对结果进行对话，问答双方都追加进会话历史。"""
    resp = chat_answer(request)
    if request.session_id:
        try:
            # 会话不存在（如已被删除）时 append 返回 False，静默跳过即可
            history.append_chat(request.session_id, "user", request.question)
            history.append_chat(request.session_id, "assistant", resp.answer)
        except Exception:  # noqa: BLE001
            pass
    return resp


@router.get("/sessions", response_model=List[SessionSummary])
async def list_sessions(q: str = "") -> List[SessionSummary]:
    """会话列表（按最近更新倒序），q 为关键词时按标题/结论/对话内容检索。"""
    return [SessionSummary(**item) for item in history.list_sessions(q=q)]


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(session_id: str) -> SessionDetail:
    """读取会话完整内容，用于恢复历史会话。"""
    record = history.get(session_id)
    if record is None:
        raise HTTPException(status_code=404, detail="会话不存在或已被删除")
    return SessionDetail(**record)


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict:
    """删除会话。"""
    if not history.delete(session_id):
        raise HTTPException(status_code=404, detail="会话不存在或已被删除")
    return {"deleted": True, "session_id": session_id}


@router.get("/health")
async def health() -> dict:
    """健康检查 + 运行环境自检，方便演示前确认环境就绪。"""
    from docdiff.services.llm_client import LLMClient
    from docdiff.services.pdf_parser import _HAS_DOCLING, _HAS_PYPDF

    client = LLMClient()
    return {
        "status": "ok",
        "parser": {"docling": _HAS_DOCLING, "pypdf": _HAS_PYPDF, "prefer": settings.parse_prefer},
        "llm": {
            "base_url": settings.llm_base_url,
            "model": settings.llm_model,
            "enabled": settings.llm_enabled,
            "online": client.is_available(),
        },
    }


@router.post("/compare-and-report", response_class=HTMLResponse)
async def compare_and_report(
    old_pdf: Annotated[UploadFile, File(description="旧版 PDF")],
    new_pdf: Annotated[UploadFile, File(description="新版 PDF")],
) -> str:
    """上传 → 比对 → 直接返回 HTML 报告。"""
    result = await compare_pdfs(old_pdf, new_pdf)
    html, _ = generate_report(result)
    return _wrap_html(html)


def _save_upload(file: UploadFile) -> Path:
    """保存上传文件到临时目录。"""
    ext = Path(file.filename or "doc.pdf").suffix or ".pdf"
    dest = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    with dest.open("wb") as buf:
        shutil.copyfileobj(file.file, buf)
    return dest


def _wrap_html(body: str) -> str:
    """把报告 body 包成完整 HTML 页面。"""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>版本差异对比报告</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; line-height: 1.7; color: #333; }}
h1 {{ color: #1a1a1a; border-bottom: 2px solid #e0e0e0; padding-bottom: 10px; }}
h2 {{ color: #333; margin-top: 30px; }}
h3 {{ color: #555; }}
ul {{ padding-left: 20px; }}
.diff-del {{ background: #ffe6e6; text-decoration: line-through; }}
.diff-ins {{ background: #e6ffe6; text-decoration: underline; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""

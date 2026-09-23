"""PDF 解析服务：优先用 Docling 抽取结构化段落，缺失时降级为 pypdf。"""

import re
from pathlib import Path
from typing import List, Optional, Tuple

# Docling 依赖较重（会拉 torch）。做成可选依赖：
# 装在就用结构化解析，没装就退到 pypdf 纯文本解析，保证项目在任何环境都能跑起来。
try:  # pragma: no cover - 取决于运行环境
    from docling.datamodel.base_models import ConversionStatus
    from docling.document_converter import DocumentConverter

    _HAS_DOCLING = True
except Exception:  # pragma: no cover
    _HAS_DOCLING = False

try:  # pragma: no cover
    from pypdf import PdfReader

    _HAS_PYPDF = True
except Exception:  # pragma: no cover
    _HAS_PYPDF = False


class Paragraph:
    """段落对象。"""

    def __init__(self, text: str, level: int = 0, label: str = "", page: Optional[int] = None) -> None:
        self.text = text.strip()
        self.level = level  # 标题层级，0 表示正文
        self.label = label  # 解析器给出的标签
        self.page = page  # 所在页码（1 起）；拿不到时为 None，前端就不显示定位

    def __repr__(self) -> str:  # pragma: no cover
        return f"Paragraph(level={self.level}, page={self.page}, text={self.text[:40]!r})"


def _is_meaningful(text: str, min_len: int = 6) -> bool:
    """过滤无意义片段（页眉页脚、页码、空行）。"""
    if not text:
        return False
    stripped = text.strip()
    if len(stripped) < min_len:
        return False
    if re.fullmatch(r"[\d\s\-—/]+", stripped):  # 纯页码或分隔符
        return False
    return True


def _split_paragraphs(text: str) -> List[str]:
    """把整段文本按空行/换行切分为候选段落，并做长度合并。

    很多 PDF 一行就是一个视觉行，直接按行切会切得太碎；
    这里把过短的行向上合并，尽量还原段落的语义边界。
    """
    raw_lines = [ln.strip() for ln in text.splitlines()]
    paragraphs: List[str] = []
    buffer = ""

    for line in raw_lines:
        if not line:
            if _is_meaningful(buffer):
                paragraphs.append(buffer)
            buffer = ""
            continue
        # 短行（< 20 字）认为是段内换行，向上合并
        if buffer and len(line) < 20 and not line.endswith(("。", "；", "：", ".", ";", ":")):
            buffer += line
        else:
            if _is_meaningful(buffer):
                paragraphs.append(buffer)
            buffer = line

    if _is_meaningful(buffer):
        paragraphs.append(buffer)
    return paragraphs


def _paragraphs_from_markdown(md: str) -> List[Paragraph]:
    """Markdown 导出件里还原段落（拿不到页码，page 为 None）。"""
    paragraphs: List[Paragraph] = []
    for line in md.splitlines():
        line = line.strip()
        if not _is_meaningful(line):
            continue
        level = 0
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            line = line.lstrip("#").strip()
        paragraphs.append(Paragraph(text=line, level=level, label="heading" if level else "text"))
    return paragraphs


def _parse_with_docling(path: Path) -> Tuple[List[Paragraph], dict]:
    """Docling 结构化解析。

    优先用 iterate_items 逐块取文本，这样能带出页码（原文定位要用）；
    接口对不上就退回 Markdown 导出件，功能不受影响，只是没有页码。
    """
    converter = DocumentConverter()
    result = converter.convert(str(path))
    if result.status == ConversionStatus.FAILURE:
        raise ValueError(f"Docling 解析失败: {path}")

    doc = result.document
    paragraphs: List[Paragraph] = []
    try:
        for item, _level in doc.iterate_items():
            text = getattr(item, "text", None)
            if not text or not _is_meaningful(text):
                continue
            prov = getattr(item, "prov", None) or []
            page = getattr(prov[0], "page_no", None) if prov else None
            label = str(getattr(item, "label", "text") or "text").lower()
            level = 1 if ("heading" in label or "title" in label) else 0
            paragraphs.append(Paragraph(text=str(text), level=level, label=label, page=page))
    except Exception:  # pragma: no cover - 取决于 docling 版本
        paragraphs = []

    if not paragraphs:
        paragraphs = _paragraphs_from_markdown(doc.export_to_markdown())

    metadata = {
        "filename": path.name,
        "pages": len(doc.pages) if getattr(doc, "pages", None) else 1,
        "paragraphs": len(paragraphs),
        "parser": "docling",
    }
    return paragraphs, metadata


def _parse_with_pypdf(path: Path) -> Tuple[List[Paragraph], dict]:
    """pypdf 纯文本降级解析。"""
    if not _HAS_PYPDF:
        raise ValueError("Docling 与 pypdf 均不可用，无法解析 PDF")

    reader = PdfReader(str(path))

    paragraphs: List[Paragraph] = []
    # 逐页解析，页码记到段落上，差异项才能回指到原文位置
    for page_no, page in enumerate(reader.pages, start=1):
        for para in _split_paragraphs(page.extract_text() or ""):
            # 纯文本解析拿不到标题层级，用「短句 + 以数字/第X章开头」粗略识别
            is_heading = len(para) < 40 and bool(
                re.match(r"^(第[一二三四五六七八九十百]+[章节条]|[0-9]+(\.[0-9]+)*[、.\s])", para)
            )
            paragraphs.append(
                Paragraph(
                    text=para,
                    level=1 if is_heading else 0,
                    label="heading" if is_heading else "text",
                    page=page_no,
                )
            )

    metadata = {
        "filename": path.name,
        "pages": len(reader.pages),
        "paragraphs": len(paragraphs),
        "parser": "pypdf",
    }
    return paragraphs, metadata


def parse_pdf(path: Path, *, max_pages: int = 0, prefer: str = "docling") -> Tuple[List[Paragraph], dict]:
    """解析 PDF，返回段落列表与元信息。

    Args:
        path: PDF 文件路径
        max_pages: 最大解析页数，0 表示不限制
        prefer: 优先使用的解析器，"docling" 或 "pypdf"

    Returns:
        (paragraphs, metadata)，metadata 含 filename / pages / paragraphs / parser

    Raises:
        ValueError: 两种解析器均失败
    """
    order = ["docling", "pypdf"] if prefer == "docling" else ["pypdf", "docling"]
    last_error: Exception | None = None

    for name in order:
        try:
            if name == "docling" and _HAS_DOCLING:
                paragraphs, metadata = _parse_with_docling(path)
            elif name == "pypdf" and _HAS_PYPDF:
                paragraphs, metadata = _parse_with_pypdf(path)
            else:
                continue

            if max_pages and len(paragraphs) > max_pages * 50:
                paragraphs = paragraphs[: max_pages * 50]
                metadata["paragraphs"] = len(paragraphs)

            if paragraphs:
                return paragraphs, metadata
        except Exception as exc:  # 某个解析器失败就换下一个
            last_error = exc
            continue

    raise ValueError(f"PDF 解析失败: {path}（{last_error}）")

"""生成两份示例 PDF（同一份技术规格说明书的新旧版本），用于演示比对功能。

用法:
    python scripts/make_samples.py

产出:
    samples/技术规格说明书_Rev01.pdf   （旧版）
    samples/技术规格说明书_Rev03.pdf   （新版）
"""

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

# reportlab 内置的中日韩字体，免额外字体文件
pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

OUT_DIR = Path(__file__).resolve().parent.parent / "samples"

TITLE_STYLE = ParagraphStyle(
    "Title", fontName="STSong-Light", fontSize=18, leading=26, spaceAfter=14
)
H2_STYLE = ParagraphStyle(
    "H2", fontName="STSong-Light", fontSize=13, leading=20, spaceBefore=10, spaceAfter=6
)
BODY_STYLE = ParagraphStyle(
    "Body", fontName="STSong-Light", fontSize=10.5, leading=17, spaceAfter=4
)


def _build(path: Path, title: str, sections: list[tuple[str, list[str]]]) -> None:
    """把章节列表渲染成 PDF。"""
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=22 * mm,
        rightMargin=22 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=title,
    )
    story = [Paragraph(title, TITLE_STYLE)]
    for heading, paragraphs in sections:
        story.append(Paragraph(heading, H2_STYLE))
        for para in paragraphs:
            story.append(Paragraph(para, BODY_STYLE))
        story.append(Spacer(1, 6))
    doc.build(story)
    print(f"generated: {path}")


OLD_SECTIONS = [
    (
        "第一条 项目概述",
        [
            "本文件为 301 项目运行环境的技术规格说明，用于明确硬件配置、"
            "操作系统、数据库及软件依赖等技术参数。",
            "本版本为 Rev 01，发布日期为 2026 年 3 月 1 日。",
        ],
    ),
    (
        "第二条 硬件配置要求",
        [
            "应用服务器数量：1 台。",
            "应用服务器配置：CPU 8 核，内存 32GB，系统盘 500GB SSD，数据盘 2TB。",
            "数据库服务器配置：CPU 16 核，内存 64GB，数据盘 4TB SSD。",
        ],
    ),
    (
        "第三条 软件与操作系统",
        [
            "操作系统：Ubuntu 22.04.5 LTS。",
            "数据库：MySQL 8.0.35。",
            "运行时：Python 3.10，Docker 24.0。",
        ],
    ),
    (
        "第四条 性能指标",
        [
            "系统在标准负载下单接口响应时间不超过 800 毫秒。",
            "并发能力要求：不低于 200 QPS。",
        ],
    ),
    (
        "第五条 项目工期与交付",
        [
            "项目总工期为 12 个月，自合同生效日起算。",
            "合同金额为 100 万元，按四期分期支付。",
            "保密期限为五年，自项目验收之日起算。",
        ],
    ),
]

NEW_SECTIONS = [
    (
        "第一条 项目概述",
        [
            "本文件为 301 项目运行环境的技术规格说明，用于明确硬件配置、"
            "操作系统、数据库及软件依赖等技术参数。",
            "本版本为 Rev 03，发布日期为 2026 年 9 月 15 日。",
        ],
    ),
    (
        "第二条 硬件配置要求",
        [
            "应用服务器数量：2 台。",
            "应用服务器配置：CPU 16 核，内存 64GB，系统盘 500GB SSD，数据盘 2TB。",
            "数据库服务器配置：CPU 16 核，内存 64GB，数据盘 4TB SSD。",
            "新增：配置负载均衡设备 1 台，型号 F5-BIG-LTM。",
        ],
    ),
    (
        "第三条 软件与操作系统",
        [
            "操作系统：Ubuntu 24.04.1 LTS。",
            "数据库：MySQL 8.4.2。",
            "运行时：Python 3.12，Docker 27.1。",
        ],
    ),
    (
        "第四条 性能指标",
        [
            "系统在标准负载下单接口响应时间不超过 500 毫秒。",
            "并发能力要求：不低于 500 QPS。",
        ],
    ),
    (
        "第五条 项目工期与交付",
        [
            "项目总工期为 18 个月，自合同生效日起算。",
            "合同金额为 150 万元，按五期分期支付。",
            "新增：验收标准需通过第三方性能检测机构出具报告。",
            "新增：违约责任按合同总金额的 5% 计算。",
        ],
    ),
]


def main() -> None:
    """生成两份示例 PDF。"""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _build(OUT_DIR / "技术规格说明书_Rev01.pdf", "301 项目运行环境技术规格说明书（Rev 01）", OLD_SECTIONS)
    _build(OUT_DIR / "技术规格说明书_Rev03.pdf", "301 项目运行环境技术规格说明书（Rev 03）", NEW_SECTIONS)


if __name__ == "__main__":
    main()

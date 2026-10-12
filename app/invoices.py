"""Invoice PDF generation (reportlab) with bundled Noto Sans Bengali font."""
from __future__ import annotations

import io
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.config import get_settings
from app.models import Sale, SaleLine
from app.money import format_money

_FONT_NAME = "NotoBengali"
_FONT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "assets",
    "fonts",
    "NotoSansBengali-Regular.ttf",
)
_FONT_REGISTERED = False


def _ensure_font() -> None:
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return
    if not os.path.exists(_FONT_PATH):
        raise FileNotFoundError(f"font not found at {_FONT_PATH}")
    pdfmetrics.registerFont(TTFont(_FONT_NAME, _FONT_PATH))
    _FONT_REGISTERED = True


def render_invoice_pdf(sale: Sale, lines: list[SaleLine], customer_name: str | None = None) -> bytes:
    """Render a Sale + lines into a PDF byte string."""
    _ensure_font()
    settings = get_settings()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
    )
    style_h = ParagraphStyle("h", fontName=_FONT_NAME, fontSize=18, leading=22, spaceAfter=6)
    style_n = ParagraphStyle("n", fontName=_FONT_NAME, fontSize=10, leading=12)
    style_t = ParagraphStyle("t", fontName=_FONT_NAME, fontSize=11, leading=13)
    story: list = []
    story.append(Paragraph(settings.shop_name or "Shop", style_h))
    if settings.shop_address:
        story.append(Paragraph(settings.shop_address, style_n))
    if settings.shop_phone:
        story.append(Paragraph(f"Phone: {settings.shop_phone}", style_n))
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"<b>Invoice {sale.sale_number}</b>", style_t))
    story.append(Paragraph(f"Date: {sale.created_at.isoformat()}", style_n))
    if customer_name:
        story.append(Paragraph(f"Customer: {customer_name}", style_n))
    story.append(Spacer(1, 8))
    sym = settings.currency_symbol
    data: list[list] = [["Item", "Qty", "Unit", "Total"]]
    for ln in lines:
        data.append(
            [
                ln.product_name,
                str(ln.quantity),
                format_money(ln.unit_price, sym),
                format_money(ln.line_total, sym),
            ]
        )
    data.append(
        [
            "Subtotal",
            "",
            "",
            format_money(sale.subtotal, sym),
        ]
    )
    data.append(["Discount", "", "", format_money(sale.discount, sym)])
    data.append(["Total", "", "", format_money(sale.total, sym)])
    data.append(["Paid", "", "", format_money(sale.paid, sym)])
    data.append(["Due", "", "", format_money(sale.due, sym)])
    table = Table(data, colWidths=[80 * mm, 18 * mm, 30 * mm, 32 * mm])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), _FONT_NAME),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.black),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
                ("LINEABOVE", (0, -4), (-1, -4), 0.3, colors.grey),
                ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 12))
    story.append(Paragraph(settings.invoice_footer, style_n))
    doc.build(story)
    return buf.getvalue()

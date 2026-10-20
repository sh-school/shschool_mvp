"""عدّةُ اختبار الرسم الحقيقيّ للمحرّك — تُحوّل `Layout` إلى HTML وتقيسُه بتخطيط WeasyPrint نفسِه (الحَكَم، المواصفة §٣-٣ و§٨-٢).

لا تقرأ القوالبَ الفعليّة (لا مستهلكَ بعدُ): تُرسم مناطقُ `fit` بأرقامها **تحت الإطار المركزيّ الحقيقيّ** (`{% print_frame_css %}` وترويسةٌ وتذييل) فيُقاس:
عددُ الصفحات، وأصغرُ خطٍّ مرسومٍ في المتن، وارتفاعُ كلّ منطقةٍ مقابل ما حسبه المحرّك، ونسبةُ امتلاء الصفحة الأولى.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import weasyprint
from django.template import engines
from weasyprint.formatting_structure import boxes

from core import print_frame as pf
from core.print_fit import capacity as cap
from core.print_fit import fit as fitmod
from core.print_fit import text_metrics as tm
from core.print_fit.fit import Continuation, FitZone, Layout, Page

ROOT = pathlib.Path(__file__).resolve().parent.parent
MM_PX = 96 / 25.4
PT_PX = 96 / 72

DOC = """{% load print_frame %}<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
{% print_frame_css paper orient %}
<style>{{ fonts|safe }}
body { font-family: 'Tajawal', sans-serif; direction: rtl; margin: 0; }
.z { margin: 0; padding: 0; } .z p { position: relative; margin: 0; } .z .n { position: absolute; inset-inline-start: 0; }
table.t { border-collapse: collapse; border-spacing: 0; } table.t td { padding: 0; }
.cont { break-before: page; }
</style></head><body>
{% print_frame_header paper orient school "عنوان الوثيقة" "العام الدراسي 2026-2027" True %}
{% print_frame_footer paper orient school %}
{{ body|safe }}
</body></html>"""


@dataclass(frozen=True)
class Measured:
    pages: int
    min_font_pt: float
    zone_heights_mm: dict[str, float]
    fill: float
    last_bottom_mm: float


def _zone_html(z: FitZone, zl: Any, layout: Layout, rows: int | None) -> str:
    key = z.key
    if z.kind == "fixed":
        return f'<div class="z" data-key="{key}" style="height:{z.height_mm}mm"></div>'
    if z.kind == "fill":
        return f'<div class="z" data-key="{key}" style="height:{zl.height_mm * 0.98:.3f}mm"></div>'
    pt = zl.font_pt
    lh = z.line_height
    style = f"font-family:'{'Tajawal' if z.font == 'tajawal' else 'Noto Naskh Arabic'}';font-size:{pt}pt;line-height:{lh};font-weight:{z.weight}"
    if z.kind == "table":
        n_rows = z.rows if z.rows is not None else int(rows or 0)
        worst = max(
            z.cell_texts, key=lambda t: len(tm.wrap(t, z.cell_width_mm, pt, z.font, z.weight))
        )
        pad = z.row_pad_mm / 2
        rows = "".join(
            f'<tr><td style="padding:{pad}mm 0;{style}">{worst}</td></tr>' for _ in range(n_rows)
        )
        return (
            f'<div class="z" data-key="{key}"><div style="height:{z.header_mm}mm"></div>'
            f'<table class="t" style="width:{z.cell_width_mm}mm">{rows}</table></div>'
        )
    # text
    prefix = (
        cap.prefix_mm(fitmod._cap_zone(z), len([p for p in z.paragraphs if p.strip()]), pt)
        if z.numbered
        else 0.0
    )
    pad = (
        (z.min_pad_mm if z.min_pad_mm is not None else z.pad_mm)
        if layout.report.steps_taken[-1] >= fitmod.STEP_WHITESPACE
        else z.pad_mm
    )
    paras = "".join(
        f'<p style="padding-inline-start:{prefix:.4f}mm;margin-bottom:{z.paragraph_gap_mm if i < len(zl.paragraphs) else 0}mm">'
        f'{f"<span class=n>{i}.</span>" if z.numbered else ""}{text}</p>'
        for i, text in enumerate(zl.paragraphs, 1)
    )
    return f'<div class="z" data-key="{key}" style="width:{z.width_mm}mm;{style};padding:{pad / 2}mm 0">{paras}</div>'


def _continuation_html(z: FitZone, c: Continuation, pt: float, first: bool) -> str:
    style = f"font-family:'Tajawal';font-size:{pt}pt;line-height:{z.line_height}"
    prefix = cap.prefix_mm(fitmod._cap_zone(z), len(z.paragraphs), pt) if z.numbered else 0.0
    parts = []
    for i, text in enumerate(c.paragraphs):
        number = c.first_number + i
        first_is_tail = i == 0 and c.continues_paragraph
        label = "" if (not z.numbered or first_is_tail) else f"<span class=n>{number}.</span>"
        parts.append(
            f'<p style="padding-inline-start:{prefix:.4f}mm;margin-bottom:{z.paragraph_gap_mm}mm">{label}{text}</p>'
        )
    return f'<div class="z{' cont' if first else ''}" data-key="{c.zone}-cont" style="width:{z.width_mm}mm;{style}"><h4 style="margin:0 0 2mm">{c.label}</h4>{"".join(parts)}</div>'


def render(
    zones: list[FitZone], layout: Layout, page: Page, rows: int | None = None
) -> weasyprint.Document:
    from core.pdf_utils import _font_face_css_weasyprint

    by_key = {z.key: z for z in zones}
    gap = layout.gap_mm
    body = ""
    for i, zl in enumerate(layout.zones):
        z = by_key[zl.key]
        if i:
            body += f'<div style="height:{gap}mm"></div>'
        body += _zone_html(z, zl, layout, rows)
        if zl.extra_mm and z.kind == "text":
            body += f'<div style="height:{zl.extra_mm * 0.98:.3f}mm"></div>'
    for i, c in enumerate(layout.continuation):
        z = by_key[c.zone]
        body += _continuation_html(z, c, layout.zone(c.zone).font_pt or 10.0, first=i == 0)
    school = SimpleNamespace(name="مدرسة اختبار", phone="", email="", city="الشحانية", vision="")
    html = (
        engines["django"]
        .from_string(DOC)
        .render(
            {
                "paper": page.paper,
                "orient": page.orient,
                "school": school,
                "fonts": _font_face_css_weasyprint(),
                "body": body,
            }
        )
    )
    return weasyprint.HTML(string=html, base_url=str(ROOT)).render()


def _walk(box: Any, in_margin: bool = False):
    if type(box).__name__ == "MarginBox":
        in_margin = True
    yield box, in_margin
    for child in getattr(box, "children", ()):
        yield from _walk(child, in_margin)


def measure(doc: weasyprint.Document) -> Measured:
    min_font = 1e9
    heights: dict[str, float] = {}
    for page in doc.pages:
        for box, in_margin in _walk(page._page_box):
            if (
                isinstance(box, boxes.TextBox)
                and not in_margin
                and len((box.text or "").strip()) >= 3
            ):
                min_font = min(min_font, box.style["font_size"] / PT_PX)
            el = getattr(box, "element", None)
            key = el.get("data-key") if el is not None else None
            if key and isinstance(box, boxes.BlockBox):
                heights[key] = heights.get(key, 0.0) + box.margin_height() / MM_PX
    first = doc.pages[0]._page_box
    body_top, body_bottom = first.content_box_y(), first.content_box_y() + first.height
    bottoms = [
        b.position_y + b.margin_height()
        for b, m in _walk(first)
        if not m
        and isinstance(b, boxes.BlockBox)
        and (b.element is not None and b.element.get("data-key"))
    ]
    fill = (max(bottoms, default=body_top) - body_top) / max(body_bottom - body_top, 1)
    return Measured(
        pages=len(doc.pages),
        min_font_pt=round(min_font, 2) if min_font < 1e9 else 0.0,
        zone_heights_mm={k: round(v, 2) for k, v in heights.items()},
        fill=round(fill, 3),
        last_bottom_mm=round(max(bottoms, default=body_top) / MM_PX, 2),
    )


def frame_body_bottom_mm(paper: str, orient: str) -> float:
    fr = pf.frame(paper, orient)
    return fr.top_total + fr.body_height

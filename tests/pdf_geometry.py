"""قياساتٌ على PDF مرسومٍ بالفعل — لا على HTML ولا CSS: نصٌّ مقصوص، ومركزُ رمزٍ في خليّته، وإحداثيّاتُ سطرٍ.

`tests/test_schedule_a3_sheet.py` يستعملها: ما يُحكم عليه هو ما يراه القارئُ في الورقة (بلاغاتُ المالك 2026-09-27: اسمٌ مقصوص،
تذييلٌ بأكثر من سطر، رمزٌ لا يتوسّط خليّته). pypdf يقرأ النصَّ وإحداثيّاتِه، وpypdfium2 يرسم الصفحةَ فتُقاس حدودُ الخلايا بالبكسل.
"""

from __future__ import annotations

import io
import re
import statistics
from collections.abc import Iterable

import pypdf
import pypdfium2

#: بكسلٌ للنقطة عند القياس (≈ 0.059مم للبكسل) — يكفي لدقّة ±0.1مم.
SCALE = 6
PT_MM = 0.3528
_TASHKEEL = re.compile("[ً-ٰٟـ]")


def page_texts(pdf: bytes) -> list[str]:
    return [page.extract_text() for page in pypdf.PdfReader(io.BytesIO(pdf)).pages]


def text_chunks(pdf: bytes, page_no: int = 0) -> list[tuple[str, float, float, float]]:
    """(النصّ، x، y، حجمُ الخطّ بالنقطة) لكلّ قطعةِ نصٍّ في الصفحة — y من أسفل الصفحة."""
    page = pypdf.PdfReader(io.BytesIO(pdf)).pages[page_no]
    found: list[tuple[str, float, float, float]] = []

    def visit(text, cm, tm, font, size):
        if text.strip():
            found.append(
                (
                    text.strip(),
                    tm[4] * cm[0] + cm[4],
                    tm[5] * cm[3] + cm[5],
                    abs(size * tm[3] * cm[3]),
                )
            )

    page.extract_text(visitor_text=visit)
    return found


def missing_names(pdf: bytes, names: Iterable[str]) -> list[str]:
    """أسماءٌ لا تظهر كاملةً في نصّ الـPDF المرسوم = مقصوصةٌ بحدّ الخليّة.

    ولا يُستخرَج حرفُ «الله» الملتصقُ (لِغةُ الخطّ ترسمه ولا يعطي نصّاً)، فيُسقَط من الطرفين قبل المقارنة.
    """

    def flat(value: str) -> str:
        return _TASHKEEL.sub("", value).replace("الله", "")

    text = flat("\n".join(page_texts(pdf)))
    return [name for name in names if flat(name) not in text]


def center_offsets_mm(pdf: bytes, limit: int = 60) -> list[tuple[float, float]]:
    """(فرقُ مركزِ الرمز عن مركز خليّته بالملّيمتر، ارتفاعُ الخليّة) لعيّنةٍ من خلايا الحصص «12.4».

    موجبٌ = النصُّ أدنى من المركز. الحدّان أقربُ خطَّين أفقيَّين داكنَين فوق خطّ الأساس وتحته في عمودٍ خالٍ يسارَ الرمز.
    """
    reader = pypdf.PdfReader(io.BytesIO(pdf))
    height = float(reader.pages[0].mediabox.height)
    cells = [
        (text, x, y, size)
        for text, x, y, size in text_chunks(pdf)
        if re.fullmatch(r"\d{1,2}\.\d", text)
    ]
    if not cells:
        return []
    px = pypdfium2.PdfDocument(pdf)[0].render(scale=SCALE).to_pil().convert("L").load()
    reach = 8 * SCALE  # مدى البحث عن الحدّ بالبكسل (8 نقاط)
    out: list[tuple[float, float]] = []
    for text, x, y, size in cells[:: max(1, len(cells) // limit)]:
        x0 = int((x - 3.0) * SCALE)
        base = int((height - y) * SCALE)

        def dark(yy: int, xx: int = x0) -> bool:
            return px[xx, yy] < 120

        up = next((yy for yy in range(base, base - reach, -1) if dark(yy)), None)
        down = next((yy for yy in range(base, base + reach) if dark(yy)), None)
        if up is None or down is None:
            continue
        top, bottom = float(up), float(down)
        while dark(int(top) - 1):
            top -= 1
        while dark(int(bottom) + 1):
            bottom += 1
        top, bottom = (up + top) / 2, (down + bottom) / 2
        left, right = int(x * SCALE), int((x + size * 0.55 * len(text)) * SCALE)
        ink = [
            yy
            for yy in range(int(top) + 3, int(bottom) - 2)
            if any(px[xx, yy] < 110 for xx in range(left, right, 2))
        ]
        if ink:
            out.append(
                (
                    ((ink[0] + ink[-1]) / 2 - (top + bottom) / 2) / SCALE * PT_MM,
                    (bottom - top) / SCALE * PT_MM,
                )
            )
    return out


def median_center_offset_mm(pdf: bytes) -> float:
    """وسيطُ الفرق على الصفوف العاديّة فقط (ارتفاعٌ 2.8–3.5مم): صفوفُ القسم الضيّق المرتفعةُ ولقطاتُ الحدّ الملتبسة خارجَه."""
    normal = [offset for offset, h in center_offsets_mm(pdf) if 2.8 <= h <= 3.5]
    return statistics.median(normal)

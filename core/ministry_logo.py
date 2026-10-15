"""شعارُ الوزارة الأصليّ للمخرجات وحدَها: PDF والطباعة وExcel والمصدَّر (W-20261014-009، قرار المالك 10-14؛ يُنهي D-409م ويعدّل D-386م/D-387م).

يبقى الملفُّ `core/assets/ministry_logo.png` **خارجَ `static/`** عمداً: لا رابطَ له فلا تعرضه صفحةٌ حيّةٌ من المنصّة أبداً، ولا يصل إلى
المتصفّح إلّا مضمَّناً (`data:`) داخل وثيقةٍ تُطبع. يحرس ذلك `tests/test_ministry_logo_exports_only.py`.

ثلاثةُ وجوهٍ للأصل نفسِه:
- HTML/PDF: `data:` URI فلا يطلب WeasyPrint ولا Playwright شبكةً ولا مساراً نسبيّاً.
- الطباعةُ من المتصفّح: الصنفُ `ministry-logo` مخفيٌّ على الشاشة ويظهر عند الطباعة وحدَها (`20-components.css`).
- Excel: `openpyxl.drawing.image.Image` من البايتات نفسِها بحجمٍ ثابتٍ بالبكسل — فلا تتغيّر الصفوفُ.
"""

from __future__ import annotations

import base64
import functools
import io
from pathlib import Path
from typing import Any

from django.conf import settings

#: ضلعُ الشعار في Excel بالبكسل (يسكن ارتفاعَ صفّ العنوان الأوّل 40pt ≈ 53px بلا تغيير عددِ الصفوف).
EXCEL_SIDE_PX = 48


def _file() -> Path:
    path = Path(settings.BASE_DIR) / "core" / "assets" / "ministry_logo.png"
    if not path.is_file():  # لا يُسقط التصديرَ: الشعارُ زينةٌ لا بيان
        raise FileNotFoundError(path)
    return path


@functools.lru_cache(maxsize=1)
def logo_bytes() -> bytes:
    """بايتاتُ PNG الأصل (تُقرأ مرّةً لكلّ عمليّة)."""
    return _file().read_bytes()


def logo_data_uri() -> str:
    """الشعارُ مضمَّناً في HTML للمخرجات — يعمل بلا شبكةٍ ولا مسارٍ نسبيّ."""
    return "data:image/png;base64," + base64.b64encode(logo_bytes()).decode("ascii")


def logo_excel_image(side_px: int = EXCEL_SIDE_PX) -> Any:
    """`openpyxl` Image بحجمٍ ثابتٍ، أو `None` إن غاب الأصلُ أو Pillow (فيُصدَّر الملفُّ بلا شعار بدل أن يسقط)."""
    try:
        from openpyxl.drawing.image import Image

        image = Image(io.BytesIO(logo_bytes()))
    except (FileNotFoundError, ImportError):
        return None
    image.width = image.height = side_px
    return image

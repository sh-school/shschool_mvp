"""شعارُ المدرسة «ش» (v3) — مصدرٌ واحدٌ للشاشة وPDF وExcel (W-20261012-012، قرار المالك D-404م).

الأصلُ الوحيدُ `static/icons/v3/icon-192.png` (الكوفيّ المربّع «ش» أبيضَ على العنّابيّ `core.brand.MAROON`؛ لا النسخةُ maskable لأنّ حشوتَها تُصغّر الحرف).
وهو غيرُ شعار الوزارة الذي أُزيل (D-386م/D-387م) ولا يعود: `tests/test_school_logo.py` يحرس حضورَ هذا وغيابَ ذاك.

ثلاثةُ وجوهٍ للأصل نفسِه:
- الشاشةُ: رابطُ الملفّ الثابت (`logo_static_path` يمرّ بوسم `{% static %}` فيبصمه الإنتاجُ بمحتواه).
- PDF: `data:` URI مضمَّنٌ في HTML فلا يطلب WeasyPrint ولا Playwright شبكةً ولا مساراً نسبيّاً.
- Excel: `openpyxl.drawing.image.Image` من البايتات نفسِها بحجمٍ ثابتٍ بالبكسل — فلا تتغيّر الصفوفُ.

والعرضُ في القوالب بالوسم `{% school_logo "nav" %}` (`core/templatetags/school_logo.py`) والمكوّن `components/school_logo.html`.
"""

from __future__ import annotations

import base64
import functools
import io
from pathlib import Path

from django.conf import settings

#: مسارُ الأصل داخل `static/` — يمرّ به `{% static %}` للشاشة.
LOGO_STATIC_PATH = "icons/v3/icon-192.png"

#: أضلاعُ الشعار بالبكسل على الشاشة بحسب الموضع (مربّعٌ دائماً). تُقرأ في CSS من أصنافٍ لا من هنا؛ وهنا للـ PDF وExcel وحارس الاختبار.
SIZES_PX = {"nav": 32, "inline": 28, "login": 56, "error": 48, "print": 40, "sheet": 48}

#: ضلعُ الشعار في Excel بالبكسل (صفُّ العنوان يتّسع له دون تغيير عددِ الصفوف: يُضبط ارتفاعُه لا تُضاف صفوف).
EXCEL_SIDE_PX = 48


def _logo_file() -> Path:
    from django.contrib.staticfiles import finders

    found = finders.find(LOGO_STATIC_PATH)
    path = (
        Path(found)
        if isinstance(found, str)
        else Path(settings.BASE_DIR) / "static" / LOGO_STATIC_PATH
    )
    if not path.is_file():  # لا يُسقط التصديرَ ولا الصفحةَ: الشعارُ زينةٌ لا بيان
        raise FileNotFoundError(path)
    return path


@functools.lru_cache(maxsize=1)
def logo_bytes() -> bytes:
    """بايتاتُ PNG الأصل (تُقرأ مرّةً لكلّ عمليّة)."""
    return _logo_file().read_bytes()


def logo_data_uri() -> str:
    """الشعارُ مضمَّناً في HTML لـPDF — يعمل بلا شبكةٍ ولا مسارٍ نسبيّ."""
    return "data:image/png;base64," + base64.b64encode(logo_bytes()).decode("ascii")


def logo_excel_image(side_px: int = EXCEL_SIDE_PX):
    """`openpyxl` Image بحجمٍ ثابتٍ، أو `None` إن غاب الأصلُ أو Pillow (فيُصدَّر الملفُّ بلا شعار بدل أن يسقط)."""
    try:
        from openpyxl.drawing.image import Image

        image = Image(io.BytesIO(logo_bytes()))
    except (FileNotFoundError, ImportError):
        return None
    image.width = image.height = side_px
    return image

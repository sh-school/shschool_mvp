"""أصولُ وثائق PDF في وحدة الجودة — الشعارُ المعتمدُ مضمَّناً في الصفحة لا مُشاراً إليه برابط.

استمارةُ الزيارة الصفّيّة بلا ترويسةٍ مرفوعةٍ ولا `School.logo` تُطبع بشعار الدولة المعتمد `static/brand/logoMaroon.png` (العنّابيّ) —
وهو الذي تستعمله وثائقُ PDF الأخرى في المنصّة. فلا تحتاج مدرسةٌ إلى رفع شيءٍ لتظهر الاستمارةُ بشعارٍ.
ويُقرأ الملفُّ ويُضمَّن (data URI) كصور المدرسة: WeasyPrint يحلّ الروابطَ النسبيّة على القرص من مجلّد العمل، ورابطُ `{% static %}` في
الإنتاج يحمل بصمةً لا وجودَ لها إلّا في `staticfiles/` — فالتضمينُ لا يعتمد على أيٍّ منهما.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

BRAND_LOGO = Path("static") / "brand" / "logoMaroon.png"


def brand_logo_data_uri() -> str:
    """الشعارُ المعتمدُ مضمَّناً — أو نصٌّ فارغ (تُطبع الترويسةُ النصّيّةُ وحدَها) إن تعذّرت قراءتُه."""
    path = Path(settings.BASE_DIR) / BRAND_LOGO
    try:
        payload = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        logger.warning("تعذّرت قراءة الشعار المعتمد %s — تُطبع الترويسةُ بنصٍّ وحدَه", BRAND_LOGO)
        return ""
    return f"data:image/png;base64,{payload}"

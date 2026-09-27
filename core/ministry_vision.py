"""نصُّ رؤية الوزارة كنصٍّ عارٍ — للمخرجات التي لا ترسم قالباً (ذيلُ طباعة Excel).

المصدرُ الواحد هو الجزئيّة `templates/components/ministry_vision.html` (تقرأ `school.vision` وتحتفظ بالنصّ الافتراضيّ احتياطاً) — لا نسخةَ ثانيةً هنا،
وإلّا تحدّث نصُّ الوزارة في مكانٍ وبقي في آخر (`tests/test_ministry_vision_footer.py::test_the_vision_has_one_source`). فالنصُّ يُستخرج بتصيير الجزئيّة نفسِها
ونزعِ وسمها، كما يفعل ذيلُ سجلّ الأجنحة (`wings/register.py`) والإطارُ المطبوع (`core/templatetags/print_frame.py`).
"""

from __future__ import annotations

import re
from typing import Any

from django.template.loader import render_to_string

_TAGS = re.compile(r"<[^>]+>")


def ministry_vision_text(school: Any = None) -> str:
    """رؤيةُ الوزارة كما تعتمدها `school` (أو النصّ الافتراضيّ إن غابت) بلا وسوم."""
    return _TAGS.sub(
        "", render_to_string("components/ministry_vision.html", {"school": school})
    ).strip()

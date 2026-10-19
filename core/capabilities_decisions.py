"""قدرةُ سجلّ قرارات المالك (W-20260928-019).

مفصولةٌ عن `core/capabilities.py` حتى لا يتجاوز سقفَ 1000 سطر (`tests/test_file_size.py`)؛
يستدعيها السجلُّ بمصنع `_cap` فلا استيرادَ دائريّ.
"""

from collections.abc import Callable
from typing import Any


def decisions_capabilities(cap: Callable[..., Any]) -> list[Any]:
    """المديرُ وحدَه يرى نصوصَ القرارات (و0101 عبر المدير)."""
    return [
        cap(
            "decisions.view",
            "الاطّلاعُ على سجلّ قرارات المالك",
            {"principal"},
            basis="قرارُ المالك: يرى نصوصَ القرارات المديرُ و0101 وحدَهما (W-20260928-019)",
        ),
    ]

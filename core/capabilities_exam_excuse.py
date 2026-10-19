"""قدرةُ قرار عذر الغياب عن الاختبار (W-20261001-012).

مفصولةٌ عن `core/capabilities.py` حتى لا يتجاوز سقفَ 1000 سطر (`tests/test_file_size.py`)؛
يستدعيها السجلُّ بمصنع `_cap` ووحدة الصلاحيّات فلا استيرادَ دائريّ.
"""

from collections.abc import Callable
from types import ModuleType
from typing import Any


def exam_excuse_capabilities(cap: Callable[..., Any], perms: ModuleType) -> list[Any]:
    """القرارُ لخمسة أدوار لا للمعلّم."""
    return [
        cap(
            "assessments.decide_excuse",
            "قرارُ عذر الغياب عن الاختبار",
            perms.ASSESSMENT_DECIDE_EXCUSE,
            basis="قرار المالك D-402م؛ الدليل 04b ص. 28: تقديرُ الأعذار والقائمةُ المغلقة",
        ),
    ]

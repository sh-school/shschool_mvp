"""لونُ الرقم — سُلَّمٌ واحدٌ بدل سلسلة `if` في كلّ عرض.

كان الحكمُ «أخضر إن بلغ 90، وكهرمانيّ إن بلغ 75، وإلّا أحمر» يُكتب في
خمسةٍ وعشرين موضعاً بصيغٍ ثلاث (`if/elif`، شرطٌ ثلاثيٌّ متداخل، `min`/`max`)
وبأسماءِ ألوانٍ تختلف باختلاف الوسم (`green`/`success`). فالسلَّمُ هنا
بياناتٌ: أزواجُ (عتبة، لون) من الأعلى إلى الأدنى، وآخرُها `(None, لون)` لما
دون كلّ العتبات. والحكمُ دالّةٌ واحدة.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import TypeVar, overload

from core.domain.attendance import ATTENDANCE_GOOD, ATTENDANCE_WARN

T = TypeVar("T")

#: سُلَّم: `((90, "green"), (75, "amber"), (None, "red"))` — العتباتُ تنازليّاً،
#: والأخيرُ بلا عتبةٍ هو الحكمُ الافتراضيّ.
Scale = Sequence[tuple[int | float | None, T]]

MUTED = "muted"


@overload
def tone_for(value: int | float | Decimal | None, scale: Scale[T]) -> T | str: ...
@overload
def tone_for(value: int | float | Decimal | None, scale: Scale[T], *, empty: T) -> T: ...
def tone_for(
    value: int | float | Decimal | None, scale: Scale[T], *, empty: T | str = MUTED
) -> T | str:
    """أوّلُ لونٍ لا تقلّ القيمةُ عن عتبته، و`empty` لقيمةٍ غائبة.

    >>> ATTENDANCE = ((90, "green"), (75, "amber"), (None, "red"))
    >>> tone_for(90, ATTENDANCE), tone_for(89.9, ATTENDANCE), tone_for(10, ATTENDANCE)
    ('green', 'amber', 'red')
    >>> tone_for(None, ATTENDANCE)
    'muted'
    """
    if value is None:
        return empty
    number = float(value)
    fallback: T | None = None
    for threshold, tone in scale:
        if threshold is None:
            fallback = tone
        elif number >= threshold:
            return tone
    if fallback is None:
        raise ValueError("السُّلَّمُ بلا حكمٍ افتراضيّ — أضف `(None, لون)` في آخره")
    return fallback


# ── السلالمُ المشتركة ──────────────────────────────────────────────────

#: نسبةُ الحضور في بطاقة رقم (`{% kpi %}`): 90 أخضر، 75 كهرمانيّ، ودونها أحمر.
ATTENDANCE_KPI: Scale[str] = ((ATTENDANCE_GOOD, "green"), (ATTENDANCE_WARN, "amber"), (None, "red"))

#: نسبةُ الحضور في ملخّصات شؤون الطلبة — العتباتُ نفسُها بألوان تلك الصفحات:
#: (لونُ البطاقة، صنفُ الشارة).
ATTENDANCE_SUMMARY: Scale[tuple[str, str]] = (
    (ATTENDANCE_GOOD, ("green", "status-success")),
    (ATTENDANCE_WARN, ("orange", "status-warning")),
    (None, ("red", "status-danger")),
)

#: مجموعٌ من مئة (أو نسبتُه من قصواه) في خانة درجة: 80 نجاح، 65 معلومة، 50 تحذير.
GRADE_CELL: Scale[str] = ((80, "success"), (65, "info"), (50, "warning"), (None, "danger"))

#: متوسّطُ الدرجات في بطاقة رقم: 80 أخضر، 60 كهرمانيّ، ودونها أحمر.
AVERAGE_KPI: Scale[str] = ((80, "green"), (60, "amber"), (None, "red"))

#: نسبةٌ من مئة في بطاقة رقم (المخالفاتُ المحلولة، درجةُ السلوك): 80 · 50.
SHARE_KPI: Scale[str] = ((80, "green"), (50, "amber"), (None, "red"))

"""نسبةُ الحضور — صيغةٌ واحدةٌ وعتبتان.

الصيغةُ `present * 100 / total` لا `present / total * 100`: الأولى قسمةٌ
واحدةٌ فناتجُها أقربُ عددٍ عشريٍّ إلى القيمة الحقيقيّة، والثانيةُ قسمةٌ ثمّ
ضربٌ فتُخطئ عند الأنصاف — `23 / 40 * 100` يخرج `57.49999…` فيُقرَّب إلى 57،
والحقيقةُ 57.5 فتُقرَّب إلى 58 (تقريبُ بايثون إلى الزوجيّ). والفرقُ نادر —
اثنتا عشرةَ حالةً في كلّ الأزواج حتّى 400 — لكنّه فرقٌ بين موضعين يعرضان
الرقمَ نفسَه.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, overload

#: من 90% فأعلى حضورٌ منتظم (أخضر)، ومن 75% تنبيه (كهرمانيّ)، ودونها خطر.
#: العتبتان اللتان كانتا في بطاقات وليّ الأمر وملخّصات شؤون الطلبة.
ATTENDANCE_GOOD = 90
ATTENDANCE_WARN = 75

Number = int | float | Decimal


@overload
def percent(
    part: Number | None, whole: Number | None, *, digits: Literal[0] = 0, empty: int = 0
) -> int: ...
@overload
def percent(
    part: Number | None, whole: Number | None, *, digits: Literal[0] = 0, empty: None
) -> int | None: ...
@overload
def percent(
    part: Number | None, whole: Number | None, *, digits: Literal[1, 2, 3], empty: int = 0
) -> float: ...
@overload
def percent(
    part: Number | None, whole: Number | None, *, digits: Literal[1, 2, 3], empty: None
) -> float | None: ...
def percent(
    part: Number | None, whole: Number | None, *, digits: int = 0, empty: int | None = 0
) -> int | float | None:
    """نسبةُ `part` من `whole` بالمئة، مقرَّبةً إلى `digits` منازل.

    `digits=0` يُعيد عدداً صحيحاً (كـ`round(x)`)، وغيرُه عدداً عشريّاً
    (كـ`round(x, digits)`). و`whole` صفرٌ أو فارغ → `empty` كما هو —
    فالمواضعُ تختلف فيما تعرضه حين لا شيءَ يُقاس: صفرٌ أو `None` أو 100.
    """
    if not whole:
        return empty
    value = float(part or 0) * 100 / float(whole)
    return round(value) if digits == 0 else round(value, digits)


@overload
def attendance_rate(
    present: Number | None, total: Number | None, *, digits: Literal[0] = 0, empty: int = 0
) -> int: ...
@overload
def attendance_rate(
    present: Number | None, total: Number | None, *, digits: Literal[0] = 0, empty: None
) -> int | None: ...
@overload
def attendance_rate(
    present: Number | None, total: Number | None, *, digits: Literal[1, 2, 3], empty: int = 0
) -> float: ...
@overload
def attendance_rate(
    present: Number | None, total: Number | None, *, digits: Literal[1, 2, 3], empty: None
) -> float | None: ...
def attendance_rate(
    present: Number | None, total: Number | None, *, digits: int = 0, empty: int | None = 0
) -> int | float | None:
    """نسبةُ الحضور: الحاضرون من المرصودين، بالمئة.

    >>> attendance_rate(23, 40)
    58
    >>> attendance_rate(0, 0)
    0
    >>> attendance_rate(1, 3, digits=1)
    33.3
    """
    if not total:
        return empty
    value = float(present or 0) * 100 / float(total)
    return round(value) if digits == 0 else round(value, digits)

"""الاستطلاعُ الحيّ لشبكة الصفّ (W-20261012-015 المرحلة 1، D-410م): JSON خفيفٌ بلا أسماء فوق ذاكرةٍ مشتركةٍ بمفتاح الشعبة واليوم.

الصلاحيّةُ تُفحص أوّلاً بـ`class_grid._readable_class` (لا يُقرأ المخزَّنُ قبلها) فيصل غريبٌ عن الشعبة إلى `GridNotFoundError`؛
والمخزَّنُ بالنطاق (شعبة + يوم) لا بالمستخدم، فيشترك معلّمٌ ومشرفٌ وقيادةٌ في حسابٍ واحد. ولا اسمَ ولا رقماً شخصيّاً في الحمولة:
معرّفُ الطالب (UUID) ورقمُ الحصّة ورأسُ سلسلة الخليّة وحالتُها فقط؛ والأسماءُ والأوقاتُ تبقى في الصفحة المرسومة.
استعلاماتُها ثابتةٌ لا تتبع عددَ الطلبة: الحصصُ باستعلامٍ واحدٍ ورؤوسُ الخلايا باستعلامٍ واحد.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.core.cache import cache

from operations.attendance_policy import grid_now, grid_window
from operations.attendance_selectors import column_heads

from . import class_grid, provisional_session

#: عمرُ الحمولة في الذاكرة المشتركة (ثانية) — كاليوم في `day_selectors.LIVE_TTL`.
LIVE_TTL = 20
#: الفاصلُ من الخادم (قرارُ المالك D-410م: 60 ثانيةً للصفحات الأربع، ولوحةُ المدير تبقى 45).
LIVE_NEXT_IN = 60
LIVE_SCHEMA = 1


def _phase(day: dt.date, moment: dt.datetime) -> str:
    """`live` لليوم الجاري قبل إغلاق نافذة المعلّم؛ وما سواه `final` فيتوقّف العميل (التعديلُ بعد ذلك بتحديث الصفحة)."""
    _opens, closes = grid_window(day)
    return "live" if day == moment.date() and moment <= closes else "final"


def _compute(klass: Any, day: dt.date, school: Any, moment: dt.datetime) -> dict[str, Any]:
    bell = provisional_session.bell_periods(school, klass, day)
    sessions = class_grid._column_sessions(klass, day, bell)
    number_of = {session.pk: number for number, session in sessions.items()}
    cells = [
        {"c": number_of[session_id], "s": str(student_id), "h": cell.head_id, "st": cell.status}
        for (session_id, student_id), cell in column_heads(list(number_of)).items()
    ]
    # ترتيبٌ ثابتٌ فتتطابق الحمولتان لو لم يتغيّر شيء.
    cells.sort(key=lambda item: (item["c"], item["s"]))
    return {
        "schema": LIVE_SCHEMA,
        "next_in": LIVE_NEXT_IN,
        "phase": _phase(day, moment),
        "day": day.isoformat(),
        "generated_at": int(moment.timestamp()),
        "cells": cells,
    }


def live_payload(
    user: Any, school: Any, class_id: Any, on: dt.date | None = None
) -> dict[str, Any]:
    """حمولةُ الشعبة واليوم: تُحسب بقفل `cache.add` وتُخزَّن 20 ث، ومن فاته القفلُ قرأ آخرَ نسخةٍ قديمة.

    يرفع `GridNotFoundError` لمن لا يقرأ الشعبة — قبل أيّ قراءةٍ من الذاكرة.
    """
    klass, day, _roles = class_grid._readable_class(user, school, class_id, on)
    key = f"cglive:{school.pk}:{klass.pk}:{day.isoformat()}"
    data = cache.get(key)
    if data is not None:
        return data  # type: ignore[no-any-return]
    last = cache.get(f"{key}:last")
    if cache.add(f"{key}:lock", 1, 10) or last is None:
        try:
            data = _compute(klass, day, school, grid_now())
            cache.set(key, data, LIVE_TTL)
            cache.set(f"{key}:last", data, LIVE_TTL * 6)
        finally:
            cache.delete(f"{key}:lock")
        return data
    return last  # type: ignore[no-any-return]

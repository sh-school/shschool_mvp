"""تعريفٌ واحدٌ لسقف فراغ المعلّم يقرؤه الحلّال والمُقيِّم (W-20261012-023).

الفراغُ هو **أوسعُ فراغٍ مفردٍ** بين حصّتين مشغولتين متتاليتين في اليوم، كما في وصف الحقل
`TeacherPreference.max_gap` وفي الشاشة؛ لا مجموعُ الفراغات. وكان الحلّالُ يعدّ المجموعَ والمُقيِّمُ يعدّ
الأوسعَ فتتناقض الجودةُ المعلنة. فهذا الملفُّ مصدرُ التعريف: المُقيِّمُ يستدعي `widest_gap_of_positions`
والحلّالُ يرمّز النافذةَ نفسَها في `scheduler_v2/hard_constraints.py`، واختبارُ التكافؤ يطابق الاثنين.

والسقفُ المحفوظ مقرونٌ براية `PREF_MAX_GAP_ACTIVE` (مطفأةٌ افتراضاً، D-418م): قيمةٌ محفوظةٌ سابقاً لا تكسر
التوليدَ، وتبقى في القاعدة كما هي، ويعود أثرُها حين يفتح المالكُ الراية بعد إعادة القياس.
"""

from __future__ import annotations

from collections.abc import Iterable


def widest_gap(occupied: Iterable[bool]) -> int:
    """أوسعُ تتابعِ فراغاتٍ بين أوّل مشغولٍ وآخرِ مشغولٍ في أعلامِ إشغالٍ مرتَّبةٍ بالزمن (0 إن قلّ المشغول عن اثنين)."""
    widest = run = 0
    seen = False
    for flag in occupied:
        if flag:
            widest = max(widest, run)
            run, seen = 0, True
        elif seen:
            run += 1
    return widest


def widest_gap_of_positions(positions: Iterable[int]) -> int:
    """أوسعُ فراغٍ بين أرقام حصصٍ مشغولة (الفراغُ = ما بين رقمين متتاليين من الحصص الفارغة)."""
    ordered = sorted(set(positions))
    if len(ordered) < 2:
        return 0
    return max(b - a - 1 for a, b in zip(ordered, ordered[1:], strict=False))


def effective_max_gap(value: int | None) -> int | None:
    """السقفُ الذي يعمل به المحرّكان: ``None`` ما دامت ``PREF_MAX_GAP_ACTIVE`` مطفأة (الافتراضيّ).

    القارئُ الوحيدُ لـ``max_gap`` في الحلّال والمُقيِّم؛ و``max_consecutive`` لا يمرّ به فالإداريّ يرخّي به HC5.
    """
    from django.conf import settings

    return value if getattr(settings, "PREF_MAX_GAP_ACTIVE", False) else None

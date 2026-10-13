"""سعةُ قيود المعلّم: كم حصّةً تسعها تفضيلاتُه في اليوم وفي الأسبوع.

«لا حصّتان متتاليتان» (متتالية = 1) و«لا فراغَ البتّة» (فراغ = 0) لا يجتمعان
إلّا بحصّةٍ واحدةٍ في اليوم: الثانيةُ إمّا ملاصقةٌ للأولى أو بينهما فراغ. فمن
حفظ هذين معاً ونصابُه اثنتا عشرةَ حصّةً أعطاه المولّدُ خمساً (واحدةً كلَّ يوم)
وترك سبعاً بلا موضع، وقال «تعذّر وضع» سبعَ مرّات بلا سبب. والسببُ حسابٌ
بسيطٌ يُقال قبل الحفظ وقبل التوليد.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .scheduler_constraints import MAX_CONSECUTIVE

if TYPE_CHECKING:
    from django.http import HttpRequest

LAST_PERIOD = 7
WEEK_DAYS = 5


def effective_run_cap(max_consecutive: int | None) -> int:
    """سقفُ التتالي الساري: الشخصيُّ إن كُتب، وإلا العامُّ (`None` = لا قرارَ شخصيَّ، W-20261003-037)."""
    return max_consecutive if max_consecutive else MAX_CONSECUTIVE


def exceeds_general_run_cap(max_consecutive: int | None) -> bool:
    """أيُرخي السقفُ الشخصيُّ HC5 لصاحبه؟ — أعلى من العامّ."""
    return max_consecutive is not None and max_consecutive > MAX_CONSECUTIVE


def record_run_cap_above_general(request: HttpRequest, pref: Any, channel: str) -> None:
    """تنبيهٌ ظاهرٌ وأثرٌ مدقَّق حين يُحفظ سقفٌ شخصيٌّ فوق العامّ — قبولٌ لا رفض (توصيةُ 0301، 10-10).

    الأثرُ قيمتان ومعرّفُ الصفّ والقناةُ (شاشةُ المعلّم أو الأدمن) — لا اسمُ المعلّم (PDPPL).
    """
    from django.contrib import messages

    from core.models import AuditLog

    messages.warning(
        request,
        f"تنبيه: سقفُ التتالي {pref.max_consecutive} أعلى من السقف العامّ ({MAX_CONSECUTIVE}) — "
        "سيُعتمد في التوليد مكانَ العامّ ويُرخي قيد التلاصق لهذا المعلّم. تُرك فارغاً لاعتماد العامّ.",
    )
    AuditLog.objects.create(
        school=pref.school,
        user=request.user,
        action="update",
        model_name="other",
        object_id=str(pref.pk),
        object_repr=f"سقفُ التتالي الشخصيّ فوق العامّ {pref.academic_year}",
        changes={
            "event": "teacher_run_cap_above_general",
            "channel": channel,
            "value": pref.max_consecutive,
            "general": MAX_CONSECUTIVE,
        },
    )


def record_free_day_change(
    request: HttpRequest, pref: Any, before: int | None, change: bool
) -> None:
    """يومُ التفريغ قرارٌ إداريّ (W-20261010-025): تغييرُه من الأدمن يُثبَّت قيمتين قبل وبعد ومعرّفَ الصفّ.

    لا اسمَ معلّم (PDPPL) — كسقف السابعة الإداريّ.
    """
    from core.models import AuditLog

    actor: Any = request.user
    AuditLog.objects.create(
        school=pref.school,
        user=actor,
        action="update" if change else "create",
        model_name="other",
        object_id=str(pref.pk),
        object_repr=f"يومُ التفريغ الإداريّ {pref.academic_year}",
        changes={"event": "teacher_free_day_changed", "before": before, "after": pref.free_day},
    )


def save_teacher_preferences(request: HttpRequest, pref: Any) -> None:
    """حفظُ شاشة المعلّم: الحقولُ التي يحرّرها وحدَها، وسقفٌ فوق العامّ يُنبَّه إليه ويُسجَّل."""
    pref.save(update_fields=pref.TEACHER_EDITABLE_FIELDS)
    if exceeds_general_run_cap(pref.max_consecutive):
        record_run_cap_above_general(request, pref, "teacher_preferences")


def daily_capacity(
    max_daily: int,
    max_consecutive: int | None,
    max_gap: int | None,
    free_periods: int = LAST_PERIOD,
) -> int:
    """أكثرُ ما يُوضع للمعلّم في يومٍ واحدٍ تحت قيوده.

    - بلا سقفِ فراغ: السقفُ اليوميّ وحدَه (الفراغُ ترجيحٌ مرنٌ لا قيد).
    - فراغ = 0: كتلةٌ واحدةٌ متّصلة، طولُها سقفُ التتالي.
    - فراغ ≥ 1: كتلٌ بطول التتالي يفصل بينها فراغٌ واحد (أضيقُ فاصلٍ مسموح)،
      تُرَصّ في خانات اليوم المتاحة.
    """
    free = max(0, min(free_periods, LAST_PERIOD))
    if max_gap is None:
        return min(max_daily, free)
    run = max(1, effective_run_cap(max_consecutive))
    if max_gap == 0:
        return min(max_daily, run, free)
    count, position = 0, 0
    while position < free:
        block = min(run, free - position)
        count += block
        position += block + 1
    return min(max_daily, count)


def weekly_capacity(
    max_daily: int,
    max_consecutive: int | None,
    max_gap: int | None,
    free_day: int | None = None,
    free_per_day: dict[int, int] | None = None,
) -> int:
    """مجموعُ السعة اليوميّة على أيّام الأسبوع — بعد يوم التفريغ وبعد التفريغات.

    `free_per_day`: خاناتُ كلّ يومٍ غيرُ المحجوبة بالتفريغات، وإلّا فسبعٌ.
    """
    total = 0
    for day in range(WEEK_DAYS):
        if free_day is not None and day == free_day:
            continue
        free = LAST_PERIOD if free_per_day is None else free_per_day.get(day, LAST_PERIOD)
        total += daily_capacity(max_daily, max_consecutive, max_gap, free)
    return total


def explain_shortfall(name: str, capacity: int, load: int, pref: Any) -> str:
    """جملةٌ تقول الحسابَ لا الحكمَ وحدَه — ليعرف صاحبُها أيَّ رقمٍ يغيّر."""
    parts = [f"يومي {pref.max_daily_periods}", f"متتالية {effective_run_cap(pref.max_consecutive)}"]
    if pref.max_gap is not None:
        parts.append(f"فراغ {pref.max_gap}")
    if pref.free_day is not None:
        parts.append("يوم تفريغ")
    hint = ""
    if pref.max_gap == 0 and effective_run_cap(pref.max_consecutive) == 1:
        hint = " — «متتالية 1» مع «فراغ 0» = حصّةٌ واحدةٌ في اليوم"
    return f"قيودُ {name} ({'، '.join(parts)}) تسع {capacity} حصّةً في الأسبوع ونصابُه {load}{hint}"

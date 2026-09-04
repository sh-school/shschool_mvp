"""سعةُ قيود المعلّم: كم حصّةً تسعها تفضيلاتُه في اليوم وفي الأسبوع.

«لا حصّتان متتاليتان» (متتالية = 1) و«لا فراغَ البتّة» (فراغ = 0) لا يجتمعان
إلّا بحصّةٍ واحدةٍ في اليوم: الثانيةُ إمّا ملاصقةٌ للأولى أو بينهما فراغ. فمن
حفظ هذين معاً ونصابُه اثنتا عشرةَ حصّةً أعطاه المولّدُ خمساً (واحدةً كلَّ يوم)
وترك سبعاً بلا موضع، وقال «تعذّر وضع» سبعَ مرّات بلا سبب. والسببُ حسابٌ
بسيطٌ يُقال قبل الحفظ وقبل التوليد.
"""

from __future__ import annotations

LAST_PERIOD = 7
WEEK_DAYS = 5


def daily_capacity(
    max_daily: int, max_consecutive: int, max_gap: int | None, free_periods: int = LAST_PERIOD
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
    run = max(1, max_consecutive)
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
    max_consecutive: int,
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


def explain_shortfall(name: str, capacity: int, load: int, pref) -> str:
    """جملةٌ تقول الحسابَ لا الحكمَ وحدَه — ليعرف صاحبُها أيَّ رقمٍ يغيّر."""
    parts = [f"يومي {pref.max_daily_periods}", f"متتالية {pref.max_consecutive}"]
    if pref.max_gap is not None:
        parts.append(f"فراغ {pref.max_gap}")
    if pref.free_day is not None:
        parts.append("يوم تفريغ")
    hint = ""
    if pref.max_gap == 0 and pref.max_consecutive == 1:
        hint = " — «متتالية 1» مع «فراغ 0» = حصّةٌ واحدةٌ في اليوم"
    return f"قيودُ {name} ({'، '.join(parts)}) تسع {capacity} حصّةً في الأسبوع ونصابُه {load}{hint}"

"""scheduler_bell.py — أتتّصل حصّتان بالساعة؟ (SCH-18).

قرارُ المالك 2026-09-24: «الفسحة والصلاة تفصلان، لا تُعدّ تلاصقاً». فالتلاصقُ الذي
يُتعب المعلّمَ أن يقف حصّتين بلا استراحةٍ بينهما، وحصّتان تفصلهما فسحةٌ (عشرون
دقيقة) أو صلاةٌ ليستا كذلك — وإن تجاورتا رقماً.

وكان المولّدُ والمختبرُ والمحسّنُ والمدقّقُ يحكمون بالرقم: 13 من 46 «تلاصقاً» في
الجدول المعتمد (2026-09-24) تعبر فسحةً أو صلاة، وتُعدّ مخالفةً وهي ليست كذلك،
ويُحرَم المولّدُ من خاناتٍ صالحةٍ خوفاً منها.

فالحكمُ هنا واحدٌ لكلّ من يسأل: حصّتان متّصلتان إن كان الفاصلُ بين نهاية الأولى
وبداية الثانية `JOINABLE_GAP_MINUTES` فأقلّ — وهو التعريفُ نفسُه الذي تُعرَف به
الحصّةُ المزدوجة (`joinable_pairs`). ومن لا جرسَ معروفاً له يُحكم برقم الحصّة
كما كان: الصمتُ لا يُقرأ فصلاً.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .scheduler import ScheduleGrid

#: أطولُ فاصلٍ بين حصّتين يبقيان معه متّصلتين (بالدقائق).
#: فخمسُ دقائقَ انتقالٌ بين صفّين، وعشرون فسحةٌ وخمسَ عشرةَ صلاة.
JOINABLE_GAP_MINUTES = 10

Interval = tuple[time, time]

#: آخرُ حصّةٍ في اليوم — كما في `scheduler_constraints.LAST_PERIOD`.
LAST_PERIOD = 7


def _minutes(moment: time) -> int:
    return moment.hour * 60 + moment.minute


def are_joined(before: Interval | None, after: Interval | None) -> bool:
    """أتتّصل هذه الحصّةُ بالتي بعدها؟ — وبلا جرسٍ معروفٍ تتّصلان."""
    if before is None or after is None:
        return True
    return _minutes(after[0]) - _minutes(before[1]) <= JOINABLE_GAP_MINUTES


def cells_joined(
    grid: ScheduleGrid, day: int, first: int, first_band: str, second: int, second_band: str
) -> bool:
    """أتتّصل خانتان متجاورتان رقماً في هذا اليوم؟ — لكلٍّ نطاقُه فجرسُه."""
    if first > second:
        first, first_band, second, second_band = second, second_band, first, first_band
    return are_joined(
        grid.interval(first_band, day, first), grid.interval(second_band, day, second)
    )


def longest_run(
    cells: Iterable[tuple[int, str]], interval_of: Callable[[str, int], Interval | None]
) -> int:
    """أطولُ تتابعٍ متّصل — من (حصّة، نطاق) لمعلّمٍ في يوم، و`interval_of(نطاق، حصّة)` جرسُه."""
    ordered = sorted(set(cells))
    best = run = 1 if ordered else 0
    for (earlier, earlier_band), (later, later_band) in zip(ordered, ordered[1:], strict=False):
        joined = later == earlier + 1 and are_joined(
            interval_of(earlier_band, earlier), interval_of(later_band, later)
        )
        run = run + 1 if joined else 1
        best = max(best, run)
    return best


def grid_run(grid: ScheduleGrid, teacher_id: str, day: int) -> int:
    """أطولُ تتابعٍ متّصلٍ لمعلّمٍ في يومه — من الشبكة الموضوعة."""
    cells = []
    for period in set(grid.teacher_periods_on(teacher_id, day)):
        task = grid.teacher_task_at(teacher_id, day, period)
        cells.append((period, getattr(task, "band_id", "") or ""))
    return longest_run(cells, lambda band, period: grid.interval(band, day, period))


#: أزواجُ الجرس المحفوظةُ لمدّة توليدٍ واحد — `None` خارجَ التوليد.
#:
#: `joinable_pairs` تُسأل عند كلّ مرشَّحٍ لحصّةٍ مزدوجة: في الوضع الجشع،
#: وفي كلّ إزاحةٍ بعمقٍ ثلاث، وفي كلّ محاولةٍ من الثماني. وعددُها يتبع
#: ضيقَ البحث لا حجمَ المدرسة — على صورةٍ مطابقةٍ لبيانات الإنتاج
#: (2026-09-03) كانت 6,168 استعلاماً في التوليد الواحد، نحوَ ثلث زمنه.
#: والجرسُ لا يتغيّر في أثناء التوليد، فيُقرأ مرّةً عند بدئه ويُنسى عند
#: انتهائه.
#:
#: وهو سياقٌ لا ذاكرةٌ عامّة: مَن ينادي الدالّةَ منفردةً — الاختباراتُ
#: تُبدّل الجرسَ بين نداءين — يقرأ القاعدةَ كما كان.
_PAIRS_CACHE: ContextVar[dict | None] = ContextVar("joinable_pairs_cache", default=None)


@contextmanager
def joinable_pairs_cached():
    """يفتح ذاكرةَ أزواج الجرس لمدّة الكتلة — يستدعيه `generate_schedule`."""
    token = _PAIRS_CACHE.set({})
    try:
        yield
    finally:
        _PAIRS_CACHE.reset(token)


def joinable_pairs(school, band_id: str = "") -> set:
    """أزواجُ الحصص المتلاصقةِ فعلاً — من جرس نطاق الشعبة لا من الكود.

    الحصّةُ المزدوجةُ حصّتان لا تقطعهما فسحةٌ ولا صلاة. والفسحةُ في الطابق
    الأرضيّ بعد الثالثة وفي العلويّ بعد الرابعة — فالثالثةُ والرابعةُ كتلةٌ
    في العلويّ وليستا كتلةً في الأرضيّ. وكان الجرسُ يُقرأ للمدرسة كلِّها
    فتختلط أجراسُ النطاقات، ويُجاز تلاصقٌ عبر فسحةٍ لا يعرفها.

    ومدرسةٌ لم تُدخل أوقاتَها بعد: لا كتلَ تُعرَف، فلا يُمنع تجاورٌ بحجّة
    فاصلٍ لا نعرفه. والصمتُ لا يُقرأ منعاً.
    """
    cache = _PAIRS_CACHE.get()
    key = (getattr(school, "pk", school), band_id or "")
    if cache is not None and key in cache:
        return cache[key]
    pairs = _joinable_pairs_from_bell(school, band_id)
    if cache is not None:
        cache[key] = pairs
    return pairs


def _joinable_pairs_from_bell(school, band_id: str = "") -> set:
    from operations.models import TimeSlotConfig

    bell = TimeSlotConfig.objects.filter(school=school, day_type="regular", is_break=False)
    rows = list(bell.filter(band_id=band_id).order_by("period_number")) if band_id else []
    if not rows:
        # جرسُ المدرسة الافتراضيّ لمن لا نطاقَ له، أو لنطاقٍ بلا جرس.
        rows = list(bell.filter(band__isnull=True).order_by("period_number"))
    if not rows:
        return {(p, p + 1) for p in range(1, LAST_PERIOD)}

    pairs = set()
    for earlier, later in zip(rows, rows[1:], strict=False):
        if later.period_number != earlier.period_number + 1:
            continue
        gap = (later.start_time.hour * 60 + later.start_time.minute) - (
            earlier.end_time.hour * 60 + earlier.end_time.minute
        )
        if gap <= JOINABLE_GAP_MINUTES:
            pairs.add((earlier.period_number, later.period_number))
    return pairs

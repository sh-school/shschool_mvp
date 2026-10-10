"""
scheduler.py — خوارزمية التوليد الذكية للجدول الأسبوعي
Greedy + Backtracking + Local Search
قطر
"""

from __future__ import annotations

import logging
import random
import time
from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from core.models import School

from . import constraint_registry
from .models import (
    ScheduleGeneration,
    ScheduleSlot,
)
from .scheduler_advice import _capacity_shortfalls, _day_coverage, _slack_advice
from .scheduler_audit import unplaced_message
from .scheduler_clock import Deadline
from .scheduler_constraints import (
    calculate_quality_score,
    evaluate_soft_constraints,
    is_slot_valid,
    joinable_pairs_cached,
)
from .scheduler_persist import slots_from_grid
from .scheduling_inputs import (  # noqa: F401  (يُعاد تصديرها: انتقلت إلى وحدة محايدة، W-20261010-004)
    DAY_NAMES,
    DAYS,
    DEFAULT_TIMES,
    LAST_PERIOD,
    Member,
    ScheduleGrid,
    Task,
    _to_tasks,
    bell_lookup,
    build_tasks,
    load_band_times,
    load_break_times,
    load_inputs,
)

logger = logging.getLogger(__name__)

#: كم محاولةً تُجرَّب قبل اختيار أفضلها.
#:
#: وتتوقّف السلسلةُ عند أوّل محاولةٍ كاملة، فالثمنُ لا يُدفع إلّا عند الحاجة:
#: بقيودٍ يسعها الجدولُ تنتهي المحاولةُ الأولى في ثانية، وبقيودٍ تضيق عنه
#: تُجرَّب الثلاثُ في نحوِ دقيقة.
#: ثمانِ محاولات. والعددُ مقيسٌ لا مُخمَّن: بثلاثٍ بقيت مزدوجةُ التكنولوجيا
#: في الثامن/4 بلا موضعٍ فاحتاجت رخصةً غالية، وبثمانٍ ظهرت بذرةٌ تُغلق الجدولَ
#: كلَّه بالتلاصق وحدَه — بلا كثافةٍ ولا سابعةٍ ثالثة. فالبحثُ أرخصُ من التنازل.
#: محاولاتُ التوليد: بذورٌ متعاقبةٌ داخل ميزانيةٍ زمنيّة — لا عددٌ ثابت.
#: أقلُّها ثلاثٌ (للمقارنة)، وأكثرُها عشرون، وتتوقّف حين لا يتحسّن الأفضلُ في
#: ثلاثٍ متتالية أو تنفد الميزانية (`SCHEDULE_TIME_BUDGET_SECONDS`، 60 افتراضاً).
#: فالجدولُ الكاملُ ليس بالضرورة الأفضل — وكان البحثُ يقف عند أوّل كامل.
MIN_ATTEMPTS = 3
MAX_ATTEMPTS = 20
PATIENCE = 3


#: خاناتُ الأسبوع للمعلّم الواحد — خمسةُ أيّامٍ في سبع حصص.
WEEK_SLOTS = len(DAYS) * LAST_PERIOD


def sort_tasks(
    tasks: list[Task], blocked_slots: set[tuple[str, int, int | None]] | None = None
) -> list[Task]:
    """ترتيب المهام: الأصعب أولاً (Most Constrained First).

    والأصعبُ يُقاس أوّلاً بضيق خانات المعلّم لا بمادّته: معلّمٌ حُجبت عنه
    إحدى وعشرون خانةً من خمسٍ وثلاثين ونصابُه اثنتا عشرةَ حصّةً — له خانتان
    فائضتان في الأسبوع كلِّه. وكان الترتيبُ يبدأ بعدد معلّمي المادّة، فتأتي
    مهامُّه — والرياضياتُ كثيرةُ المعلّمين — بعد أن تأخذ شُعبُه خاناتِه
    القليلةَ لموادَّ أخرى، فتبقى له حصّةٌ بلا موضع (10/3، 2026-09-03) ويُصرَف
    عليها ملاذُ الكثافة. والمعلّمُ بلا حجبٍ فائضُه ثلاثٌ وعشرون فأكثر، فلا
    يتقدّم على أحد.
    """
    # عد كم معلم فريد لكل مادة
    subject_teacher_count = defaultdict(set)
    teacher_load: dict[str, int] = defaultdict(int)
    for t in tasks:
        subject_teacher_count[t.subject_id].add(t.teacher_id)
        for m in t.members:
            teacher_load[m.teacher_id] += t.span

    blocked_count: dict[str, int] = defaultdict(int)
    for teacher_id, _day, _period in blocked_slots or ():
        blocked_count[teacher_id] += 1

    def slack(teacher_id: str) -> int:
        return WEEK_SLOTS - blocked_count[teacher_id] - teacher_load[teacher_id]

    def priority(task: Task) -> tuple:
        teacher_count = len(subject_teacher_count[task.subject_id])
        return (
            min(slack(m.teacher_id) for m in task.members),  # أضيقُ المعلّمين خاناتٍ أوّلاً
            teacher_count,  # معلم وحيد أولاً (1 < 2 < ...)
            -task.weekly_periods,  # نصاب أعلى أولاً
            -int(task.requires_lab),  # المعامل أولاً
        )

    return sorted(tasks, key=priority)


def get_available_slots(
    grid: ScheduleGrid,
    task: Task,
    blocked_slots: set[tuple[str, int, int | None]] | None = None,
    school=None,
    allow_adjacent: bool = False,
    allow_dense: bool = False,
) -> list[tuple[int, int]]:
    """الخانات المتاحة (تحقق قيود صلبة + تفريغات + كتلة المزدوجة)"""
    from .scheduler_constraints import get_max_periods_for_day, joinable_pairs

    available = []
    level_type = getattr(task, "level_type", "")
    #: الحصّةُ المزدوجةُ لا تقطعها فسحةٌ ولا صلاة — والكتلُ من جرس المدرسة.
    pairs = joinable_pairs(school, task.band_id) if task.span > 1 and school is not None else None

    for day in DAYS:
        max_p = get_max_periods_for_day(day, level_type)
        for period in range(1, max_p - task.span + 2):
            slots = list(task.slots(period))
            if pairs is not None and tuple(slots) not in pairs:
                continue
            if any(grid.class_busy(task.class_id, day, slot) for slot in slots):
                continue
            if blocked_slots and any(
                (m.teacher_id, day, slot) in blocked_slots for m in task.members for slot in slots
            ):
                continue
            if any(
                grid.teacher_busy(m.teacher_id, day, slot) for m in task.members for slot in slots
            ):
                continue
            if all(
                is_slot_valid(grid, day, slot, task, allow_adjacent, allow_dense) for slot in slots
            ):
                available.append((day, period))
    return available


def rank_slots(
    grid: ScheduleGrid,
    task: Task,
    available: list[tuple[int, int]],
    preferences: dict | None = None,
    rng=None,
) -> list[tuple[int, int, float]]:
    """ترتيب الخانات حسب أقلّ عقوباتٍ مرنة — والمتساوياتُ تُخلط.

    والخلطُ ليس زينة: الخاناتُ المتساويةُ في العقوبة كثيرة، وترتيبُها الثابتُ
    يجعل المحرّكَ يسلك الطريقَ نفسَه في كلّ محاولة. فإن أفضى إلى انسدادٍ أفضى
    إليه دائماً — ولو أُعيد ألفَ مرّة.
    """
    ranked = []
    for day, period in available:
        penalty = evaluate_soft_constraints(grid, day, period, task, preferences)
        ranked.append((day, period, penalty.total))
    if rng is not None:
        rng.shuffle(ranked)
    ranked.sort(key=lambda x: x[2])
    return ranked


def _greedy_pass(grid, tasks, blocked, preferences, school=None, rng=None, allow_adjacent=False):
    """يضع ما يستطيع، ويُعيد ما تعذّر — بلا تراجعٍ ولا محاولاتٍ ضائعة.

    وكان هنا تراجعٌ أعمى: يرفع **آخرَ** ما وُضع وقد لا يكون له بالانسداد صلة،
    ثمّ يعود فيجرّب. فاستُهلكت المحاولاتُ في دورةٍ لا تُقرّب من حلّ — ورفعُ
    حدّها من خمسمئةٍ إلى ثلاثين ألفاً أعطى نتيجةً **أسوأ** على بيانات المدرسة.
    فالبحثُ الأعمى لا يُصلحه الإكثارُ منه.
    """
    leftovers = []
    for task in tasks:
        ranked = rank_slots(
            grid,
            task,
            get_available_slots(grid, task, blocked, school, allow_adjacent),
            preferences,
            rng,
        )
        if ranked:
            day, period, _ = ranked[0]
            grid.place(day, period, task)
        else:
            leftovers.append(task)
    return leftovers


def _blockers(grid, task, day, period, blocked):
    """مَن يسدّ هذه الخانةَ عن هذه المهمّة — أو `None` إن كان السدُّ لا يُرفع.

    فتفريغُ المعلّم قرارٌ إداريٌّ لا يُزاح، وتجاوزُ سقف اليوم أو التوزيع قيدٌ
    لا يُحلّ بإخراج ساكن. أمّا الشاغلُ — شعبةً أو معلّماً — فيُزاح إن وُجد له
    بديل.
    """
    slots = list(task.slots(period))
    if any((m.teacher_id, day, slot) in blocked for m in task.members for slot in slots):
        return None

    occupants = []
    seen = set()
    for slot in slots:
        occupant = grid.get_task_at(task.class_id, day, slot)
        if occupant is not None and id(occupant) not in seen:
            occupants.append(occupant)
            seen.add(id(occupant))
        for member in task.members:
            busy = grid.teacher_task_at(member.teacher_id, day, slot)
            if busy is not None and id(busy) not in seen:
                occupants.append(busy)
                seen.add(id(busy))
    return occupants


def _repair_pass(
    grid,
    leftovers,
    blocked,
    preferences,
    budget,
    school=None,
    allow_adjacent=False,
    allow_dense=False,
    depth: int = 3,
    deadline: Deadline | None = None,
):
    """الإزاحةُ الموجَّهة: أخرِج ساكنَ الخانة، وأنزِل المتعذّرة، ثمّ أعِد الساكن.

    والفرقُ عن التراجع الأعمى أنّ الإزاحةَ تعرف **من** يسدّ الطريق بعينه: خانةٌ
    واحدةٌ ممكنةٌ لمعلّمٍ مقيَّد، شغلها زميلٌ يملك أربعاً وثلاثين غيرَها.

    والحركةُ ذرّيّة: إن تعذّر إعادةُ أحد المُزاحين رُدَّ كلُّ شيءٍ إلى مكانه.
    فلا تُبدَّل حصّةٌ متعذّرةٌ بأخرى.
    """
    #: ثلاثُ جولاتٍ بعمقِ ثلاث. والعمقُ يُقاس ولا يُخمَّن: بعمقين يبقى أربعَ
    #: عشرةَ متعذّرةً في ثانية، وبثلاثةٍ خمسٌ في ستّ ثوانٍ — وستُّ ثوانٍ ثمنٌ
    #: مقبولٌ لعمليّةٍ تُجرى مرّةً في الفصل. وبأربعةٍ يبلغ الزمنُ دقيقةً بلا
    #: مكسبٍ يُذكر.
    remaining = list(leftovers)
    for _ in range(3):
        still = []
        for position, task in enumerate(remaining):
            if deadline is not None and deadline.expired():
                # نفدت الميزانيةُ: ما بقي يبقى متعذّراً بموضعه — لا يُترك بلا ذكر (يُسجَّل `budget_cut`).
                still.extend(remaining[position:])
                break
            if budget <= 0 or not _try_eject(
                grid,
                task,
                blocked,
                preferences,
                depth,
                school,
                allow_adjacent,
                allow_dense,
                deadline,
            ):
                still.append(task)
            else:
                budget -= 1
        if len(still) == len(remaining) or (deadline is not None and deadline.hit):
            return still
        remaining = still
    return remaining


def _try_eject(
    grid,
    task,
    blocked,
    preferences,
    depth=1,
    school=None,
    allow_adjacent=False,
    allow_dense=False,
    deadline=None,
):
    """يُخرج ساكنَ الخانةِ لينزل فيها المتعذّر — ثمّ يُعيد الساكنَ إلى بديل.

    و`depth` عمقُ السلسلة: بعمقٍ واحدٍ يجب أن يجد المُزاحُ خانةً فارغةً له،
    وبعمقين يجوز أن يُزيح هو الآخرُ ساكناً. وأبعدُ من ذلك يُقلّب الجدولَ أكثرَ
    ممّا يُصلح، وقد كفى العمقان: اثنتان بقيتا من ثمانٍ وخمسين.
    """
    for day, period in _candidate_starts(grid, task, blocked, school):
        # الساعةُ داخل السلسلة نفسِها لا بين المتعذّرات وحدَها: إزاحةٌ واحدةٌ بعمق 4 قاست 39 ثانيةً (W-20261002-033).
        # والفحصُ هنا قبل `grid.begin()` فلا حركةَ مفتوحة: يفشل هذا المستوى فيتراجع المُنادي ذرّيّاً كأيّ فشل.
        if deadline is not None and deadline.expired():
            return False
        evicted = _blockers(grid, task, day, period, blocked)
        #: إزاحةُ أكثرَ من ساكنَين تُقلّب الجدولَ أكثرَ ممّا تُصلح.
        if evicted is None or not evicted or len(evicted) > 2:
            continue

        homes = [(e, _home_of(grid, e)) for e in evicted]
        if any(home is None for _, home in homes):
            continue

        grid.begin()
        for occupant, home in homes:
            grid.remove(occupant.class_id, home[0], home[1])

        slots = list(task.slots(period))
        if all(
            is_slot_valid(grid, day, slot, task, allow_adjacent, allow_dense) for slot in slots
        ) and not any(
            grid.teacher_busy(m.teacher_id, day, slot) for m in task.members for slot in slots
        ):
            grid.place(day, period, task)
            if _rehome_all(
                grid,
                [e for e, _ in homes],
                blocked,
                preferences,
                depth,
                school,
                allow_adjacent,
                allow_dense,
                deadline,
            ):
                grid.commit()
                return True

        grid.rollback()
    return False


def _candidate_starts(grid, task, blocked, school):
    """مواضعُ البدء الممكنةُ للإزاحة — بصرف النظر عمّن يشغلها الآن.

    فالفرقُ عن `get_available_slots` أنّ هذه تشمل المشغولَ عمداً: الإزاحةُ
    تبحث عمّن يسدّ الطريقَ لتُخرجه. أمّا التفريغُ وكتلةُ المزدوجة وسقفُ اليوم
    فحدودٌ لا يرفعها إخراجُ ساكن.
    """
    from .scheduler_constraints import get_max_periods_for_day, joinable_pairs

    pairs = joinable_pairs(school, task.band_id) if task.span > 1 and school is not None else None
    for day in DAYS:
        max_p = get_max_periods_for_day(day, task.level_type)
        for period in range(1, max_p - task.span + 2):
            slots = list(task.slots(period))
            if pairs is not None and tuple(slots) not in pairs:
                continue
            if blocked and any(
                (m.teacher_id, day, slot) in blocked for m in task.members for slot in slots
            ):
                continue
            yield day, period


def _home_of(grid, task):
    """موضعُ المهمّة في الشبكة — من سجلّ الساكنين لا بمسح خمسٍ وثلاثين خانة.

    فالمسحُ كان يُستدعى 668 ألفَ مرّةٍ في توليدٍ واحد: عُشرُ زمنه.
    """
    return grid.home_of(task)


def _rehome_all(
    grid,
    tasks,
    blocked,
    preferences,
    depth=1,
    school=None,
    allow_adjacent=False,
    allow_dense=False,
    deadline=None,
):
    """يُعيد المُزاحين إلى خاناتٍ صحيحة، أو يُعلن الفشلَ ليتراجع المُنادي.

    والتراجعُ عند المُنادي بسجلّ الشبكة — لا هنا: فالسلسلةُ العميقةُ تُحرّك ما
    لم يضعه هذا المستوى، ولا يعرف كلُّ مستوىً إلّا ما فعله هو.
    """
    for task in tasks:
        ranked = rank_slots(
            grid,
            task,
            get_available_slots(grid, task, blocked, school, allow_adjacent, allow_dense),
            preferences,
        )
        if ranked:
            day, period, _ = ranked[0]
            grid.place(day, period, task)
            continue
        # لا خانةَ فارغةً له — فليُزِح هو الآخرُ إن بقي في العمق سعة.
        if depth > 1 and _try_eject(
            grid,
            task,
            blocked,
            preferences,
            depth - 1,
            school,
            allow_adjacent,
            allow_dense,
            deadline,
        ):
            continue
        return False
    return True


#: شكلُ النتيجة حين لا يبلغ التوليدُ مداه. والمفاتيحُ كلُّها حاضرةٌ عمداً:
#: كان الخروجُ المبكّرُ يعود بمفتاحين، ويقرأ المُستدعي `result["quality"]`
#: فيسقط بـ`KeyError` وصفحةِ خطأ — عقوبةُ الحالة المتوقَّعة أن تُعامَل كعطب.
def _empty_result(errors: list[str]) -> dict:
    return {
        "success": False,
        "grid": None,
        "quality": {
            "score": 0,
            "total_slots": 0,
            "total_required": 0,
            "placed_ratio": 0,
            "violations": {},
        },
        "generation": None,
        "errors": errors,
        "elapsed_ms": 0,
        "total_tasks": 0,
        "repaired": 0,
        "relaxed": 0,
        "densed": 0,
    }


#: ما يُقال حين يوقف المستخدمُ التوليد — والصفُّ يحمله من لحظة الإيقاف.
GENERATION_STOPPED = "أُوقف التوليدُ يدويّاً — لم يُكتب منه شيء."


class GenerationStoppedError(Exception):
    """أوقف المستخدمُ التوليدَ قبل الحفظ — فلا يُكتب شيء."""


def _stopped_result() -> dict:
    return dict(_empty_result([GENERATION_STOPPED]), stopped=True)


def _run_attempt(
    grid: ScheduleGrid,
    sorted_tasks,
    blocked_slots,
    preferences,
    prefs_qs,
    school,
    rng,
    max_backtrack,
    deadline: Deadline | None = None,
) -> tuple:
    """محاولةٌ واحدة: الدقيقُ للضيّقين، فالجشع، فالإصلاح، فالرخصتان، فالإنقاذ.

    تُعيد (المتعذّر، المُصلَح، المسترخى، المكثَّف، نتيجةُ الدقيق).
    """
    # المعلّمون بلا هامشٍ يُوضعون أوّلاً بالبحث الدقيق — ثمّ الجشعُ للباقين.
    from .scheduler_tight import place_tight

    tight_done = place_tight(grid, sorted_tasks, blocked_slots, prefs_qs, rng)
    pending = [t for t in sorted_tasks if grid.home_of(t) is None]
    leftovers = _greedy_pass(grid, pending, blocked_slots, preferences, school, rng)
    before_repair = len(leftovers)
    leftovers = _repair_pass(
        grid, leftovers, blocked_slots, preferences, max_backtrack, school, deadline=deadline
    )
    repaired = before_repair - len(leftovers)

    # الرخصةُ الأولى: زوجٌ واحدٌ متلاصق. والقياسُ هو الذي فرض تأخيرَها —
    # السماحُ بالتلاصق من البداية يُنتج ثمانيةً وتسعين زوجاً عند خمسةٍ
    # وأربعين معلّماً، والاسترخاءُ في آخر خطوةٍ يُنتج زوجاً لكلّ متعذّرة.
    relaxed = 0
    if leftovers:
        before = len(leftovers)
        leftovers = _repair_pass(
            grid,
            leftovers,
            blocked_slots,
            preferences,
            max_backtrack,
            school,
            allow_adjacent=True,
            deadline=deadline,
        )
        relaxed = before - len(leftovers)

    # الرخصةُ الثانية — ملاذٌ أخير: يومٌ يأخذ حصّةً زائدةً عن قسمة الأسبوع،
    # أو معلّمٌ يأخذ سابعةً ثالثة.
    #
    # وحالةُ المدرسة هي التي فرضتها: المزدوجةُ الأخيرةُ في الثامن/4 خانتاها
    # الشاغرتان في يومين مختلفين، فلا زوجَ متلاصقٌ يقبلها. وكلُّ إزاحةٍ
    # جُرِّبت اصطدمت بقيدَي التوزيع والسابعة لا بقيد التلاصق: الرياضياتُ
    # خمسُ حصصٍ في خمسة أيّام، فنقلُها يجعل يوماً يومَين رياضيات، والخانةُ
    # البديلةُ الوحيدةُ سابعةٌ عند معلّمٍ بلغ حصّتَه منها.
    #
    # ونصابُ الشعبة أربعٌ وثلاثون لا يُمَسّ — فالثمنُ يُدفع من ترتيب اليوم
    # لا من المنهج، ولمعلّمٍ واحدٍ في شعبةٍ واحدة.
    densed = 0
    if leftovers:
        before = len(leftovers)
        leftovers = _repair_pass(
            grid,
            leftovers,
            blocked_slots,
            preferences,
            max_backtrack,
            school,
            allow_adjacent=True,
            allow_dense=True,
            deadline=deadline,
        )
        densed = before - len(leftovers)

    # جولةُ الإنقاذ: متعذّرةٌ أو اثنتان بعد كلّ الرخص — سلاسلُ إزاحةٍ أعمق (أربع).
    # بأربعٍ على أربعَ عشرةَ متعذّرةً دقيقةٌ بلا مكسب، وعلى واحدةٍ ثوانٍ قد تُنقذها:
    # الشعبةُ بلا خانةٍ فائضةٍ ومعلّمُها مقيَّدٌ يحتاجان سلسلةً أطولَ لا رخصةً أخرى.
    if 0 < len(leftovers) <= 2:
        leftovers = _repair_pass(
            grid,
            leftovers,
            blocked_slots,
            preferences,
            max_backtrack,
            school,
            allow_adjacent=True,
            allow_dense=True,
            depth=4,
            deadline=deadline,
        )

    # والمفاضلةُ بالثمن لا بالعدد وحدَه: جدولٌ تامٌّ بلا رخصةِ كثافةٍ خيرٌ
    # من جدولٍ تامٍّ اشترى خانتَه بيومٍ مكدَّس. فالترتيب: المتعذّرُ أوّلاً،
    # ثمّ الرخصةُ الغالية، ثمّ الرخيصة.
    # ويومٌ فارغٌ لمعلّمٍ تامّ النصاب (HC14 حين تنازل في الملاذ الأخير) يُحسب
    # قبل رخصة الكثافة: محاولةٌ تُغطّي الأيّامَ كلَّها خيرٌ من محاولةٍ لا تفعل.
    return leftovers, repaired, relaxed, densed, tight_done


def _search_exhausted(done: int, elapsed: float, budget: float, idle: int, complete: bool) -> bool:
    """متى يقف البحثُ عن محاولةٍ أفضل.

    بعد الحدّ الأدنى: حين تنفد الميزانيةُ أو يُبلغ الأقصى، أو يثبت الأفضلُ
    ثلاثَ محاولاتٍ متتالية وهو تامّ. وما دام في الأفضل متعذّرٌ لا يُقطع البحثُ
    على الصبر وحده — بل على الميزانية.
    """
    # وما دام الأفضلُ ناقصاً تُمَدّ الميزانيةُ إلى ضعفها: حصّةٌ بلا موضعٍ أغلى من دقيقة.
    limit = budget if complete else 2 * budget
    # الحدُّ الأدنى للمقارنة (ثلاثُ محاولات) يسقط حين تنفد الميزانية: محاولةٌ واحدةٌ على الأقلّ لا ثلاثٌ مهما طالت
    # الأولى (قرارُ المالك W-20261002-033) — فمحاولاتٌ سريعةٌ لا تبلغ الميزانيةَ فلا يتغيّر شيءٌ.
    if done >= MAX_ATTEMPTS or (done >= 1 and elapsed >= limit):
        return True
    return done >= MIN_ATTEMPTS and idle >= PATIENCE and complete


def _empty_day_reports(grid: ScheduleGrid, tasks: list[Task], skip: set | None = None) -> list[str]:
    """معلّمون بقي لهم يومٌ فارغٌ رغم أنّ نصابَهم يبلغ أيّامَهم — يُقالون بالاسم."""
    names = {m.teacher_id: m.teacher_name for t in tasks for m in t.members}
    day_names = dict(ScheduleSlot.DAYS)
    found = []
    for tid, (placements, _periods, days) in sorted(
        grid.coverage.items(), key=lambda kv: names.get(kv[0], "")
    ):
        if placements < len(days) or (skip and tid in skip):
            continue
        empty = grid.teacher_empty_days(tid, sorted(days))
        if empty:
            found.append(
                f"يومٌ بلا حصّة لـ{names.get(tid, tid)}: "
                + "، ".join(day_names.get(d, str(d)) for d in empty)
            )
    return found


#: فعاد الجرسُ يُسأل آلافَ المرّات في جولة الإصلاح — 4,136 استعلاماً في توليدٍ
#: واحد، وعلى الإنتاج كلُّ استعلامٍ رحلةٌ إلى قاعدةٍ في خادمٍ آخر.
def _feasibility_snapshot(school, academic_year: str) -> dict:
    """حكمُ فحص الجدوى كما كان لحظةَ التوليد — ولا يُسقط التوليدَ إن تعذّر."""
    try:
        from .schedule_feasibility import check

        return check(school, academic_year).as_dict()
    except Exception:  # pragma: no cover - لقطةٌ للسجلّ لا شرطٌ للتوليد
        logger.exception("تعذّر حساب فحص الجدوى للقطة التوليد")
        return {}


@joinable_pairs_cached()
def generate_schedule(
    school: School,
    academic_year: str,
    user=None,
    max_backtrack: int = 500,
    generation=None,
    publish: bool = True,
    should_stop=None,
) -> dict:
    """
    التوليد الرئيسي — Greedy + Backtracking

    Args:
        generation: صفُّ `ScheduleGeneration` أُنشئ قبل البدء ليحمل حالةَ
            «قيد التوليد». إن مُرِّر حُدِّث مكانَه، وإلّا أُنشئ صفٌّ جديدٌ عند
            النجاح — والحالتان قائمتان: الاستدعاءُ من العامل يمرّره، ومن
            سطر الأوامر لا يمرّره.
        publish: أتُفعَّل الحصصُ المولَّدةُ فوراً محلَّ الجدول القائم؟
            `True` هو السلوكُ القديم (سطرُ الأوامر والاختبارات). و`False`
            هو ما تفعله الواجهة: مسودّةٌ مربوطةٌ بصفّ التوليد، لا تمسّ
            الجدولَ الحيَّ حتّى يعتمدها من يملك اعتمادَها — فكان المعلّمون
            يرون الجدولَ الجديدَ قبل أن يُقرَّر فيه شيء.

        should_stop: يُسأل بين المراحل — «أأوقفه المستخدم؟» — فيقف التوليدُ عند
            حدٍّ آمن ولا يكتب شيئاً. والإيقافُ تعاونيٌّ لا قتلُ عامل: قتلُه في
            منتصف الكتابة يترك جدولاً نصفَ مكتوب.

    Returns:
        dict with keys: success, grid, quality, generation, errors
    """
    stopped = should_stop or (lambda: False)
    start_time = time.time()
    errors = []

    # 1. بناء المهام
    tasks = build_tasks(school, academic_year)
    if not tasks:
        return _empty_result(["لا توجد توزيعات مواد (SubjectClassAssignment). أضف التوزيعات أولاً."])

    # 2. التفضيلاتُ والتفريغات — والمحمِّلُ نفسُه يخدم سدادَ الجدول الحيّ.
    prefs_qs, preferences, blocked_slots = load_inputs(school, academic_year)

    # 2c. قيودٌ لا تسع نصابَ صاحبها تُقال باسمها قبل أن تُقال «تعذّر وضع»
    # سبعَ مرّات: «متتالية 1» مع «فراغ 0» حصّةٌ واحدةٌ في اليوم.
    errors.extend(_capacity_shortfalls(tasks, prefs_qs, blocked_slots))

    # 3. ترتيب المهام — والتفريغاتُ تدخل في الترتيب: الأضيقُ خاناتٍ أوّلاً
    sorted_tasks = sort_tasks(tasks, blocked_slots)

    # 4. التوليد: محاولاتٌ متعدّدةٌ يُختار أفضلُها
    #
    # جدولُ هذه المدرسة إشغالُه تسعةٌ وتسعون بالمئة، وثلاثٌ وعشرون شعبةً من
    # خمسٍ وعشرين ممتلئةٌ تماماً — أي أنّ كلَّ خانةٍ فيها يجب أن تُملأ بالحصّة
    # الصحيحة. وفي مثل هذا الضيق تكون المحاولةُ الواحدةُ رهانَ حظّ: طريقٌ
    # واحدٌ إن انسدّ انسدّ.
    #
    # والمحاولاتُ تختلف بخلطِ الخانات المتساوية في العقوبة وحدَها — فالقيودُ
    # والأوزانُ لا تتغيّر، وإنّما يتغيّر أيُّ المتساويات يُجرَّب أوّلاً.
    # وكلُّ محاولةٍ تُقاس بنتيجتها **النهائيّة** — بعد استرخائها لا قبله. فقد
    # تنتهي محاولتان إلى خمسَ عشرةَ متعذّرةً ثمّ تُغلق إحداهما بالرخصة وتعجز
    # الأخرى: فاختيارُ الأفضل قبل الرخصة اختيارٌ بمقياسٍ ليس هو المطلوب.
    best = None
    band_times = load_band_times(school)
    break_times = load_break_times(school)
    coverage = _day_coverage(tasks, blocked_slots)
    from django.conf import settings as _settings

    from operations.schedule_lab import grid_lab_score, load_context

    budget = float(getattr(_settings, "SCHEDULE_TIME_BUDGET_SECONDS", 60))
    # سقفُ البحث الصلب ضعفُ الميزانية (كما في `_search_exhausted` لما بقي متعذّرٌ): الإصلاحُ يقف عنده داخل المحاولة.
    search_deadline = Deadline(2 * budget)
    lab_ctx = load_context(school, academic_year)
    attempt_log: list[dict] = []
    since_improvement = 0
    attempt = -1
    while True:
        if stopped():
            return _stopped_result()
        attempt += 1
        attempt_started = time.time()
        search_deadline.attempt = attempt + 1
        rng = random.Random(attempt)
        grid = ScheduleGrid(
            band_times=band_times,
            coverage=coverage,
            break_times=break_times,
            policy=constraint_registry.resolve(school, academic_year),
        )
        leftovers, repaired, relaxed, densed, tight_done = _run_attempt(
            grid,
            sorted_tasks,
            blocked_slots,
            preferences,
            prefs_qs,
            school,
            rng,
            max_backtrack,
            search_deadline,
        )
        uncovered = len(
            _empty_day_reports(grid, tasks, {m.teacher_id for t in leftovers for m in t.members})
        )
        # ثمّ درجةُ المختبر نفسِه الذي يقيس الجدولَ الحيّ — لا عددُ الرخص وحدَه:
        # محاولتان تامّتان بلا كثافةٍ تتفاضلان بما يراه النائبُ في المختبر.
        lab_score, _metrics = grid_lab_score(grid, lab_ctx)
        cost = (len(leftovers), uncovered, densed, -lab_score)
        improved = best is None or cost < best[0]
        if improved:
            best = (cost, grid, leftovers, repaired, relaxed, densed, attempt)
            since_improvement = 0
        else:
            since_improvement += 1
        attempt_log.append(
            {
                "seed": attempt,
                "tight": {k[:8]: v for k, v in tight_done.items()},
                "leftovers": len(leftovers),
                "uncovered": uncovered,
                "densed": densed,
                "relaxed": relaxed,
                "score": lab_score,
                "ms": int((time.time() - attempt_started) * 1000),
                # الساعةُ رتيبةُ الانقضاء: ما انقضى بعد هذه المحاولة فقد انقضى فيها أو قبلها، فتكون مقطوعةَ
                # الإصلاح (والرخصُ لم تُجرَّب إن سبق القطعُ بدايتَها). وتامّةٌ قبل الموعد ⇒ `cut=False`.
                "cut": search_deadline.hit,
            }
        )
        # «تامّ» هنا: لا متعذّرَ ولا يومَ فارغاً ولا رخصةَ كثافة — فما دون ذلك يستحقّ
        # محاولةً أخرى ما بقيت ميزانية.
        clean = best[0][0] == 0 and best[0][1] == 0 and best[0][2] == 0
        if _search_exhausted(
            attempt + 1, time.time() - start_time, budget, since_improvement, clean
        ):
            break

    _, grid, leftovers, repaired, relaxed, densed, chosen = best
    chosen_cut = bool(attempt_log[chosen]["cut"])
    if search_deadline.hit:
        logger.warning(
            "قُطع إصلاحُ التوليد بنفاد الميزانية (%.0f ثانية) بعد %d محاولة — متعذّرات: %d",
            budget,
            attempt + 1,
            len(leftovers),
        )

    # التحسينُ المحلّيّ على الجدول الكامل: نقلٌ أو تبديلٌ يُقبل إن رفع درجةَ
    # المختبر بلا كسر قيد — فيما بقي من الميزانية، وربعُها على الأقلّ.
    # ويجري ولو بقيت حصّةٌ متعذّرة: ما وُضع يُحسَّن، والمتعذّرُ يبقى مذكوراً.
    from .scheduler_audit import grid_breaches, summary
    from .scheduler_improve import improve
    from .scheduler_settle import settle_safely

    if stopped():
        return _stopped_result()
    # السدادُ قبل التحسين وبعده (SCH-03): ما كُسر برخصةٍ يُعاد إليه أوّلاً، فالصلبُ قبل المرن.
    settled = [
        settle_safely(grid, tasks, blocked_slots, preferences, school, time.time() + budget / 4)
    ]
    if stopped():
        return _stopped_result()
    deadline = max(start_time + budget, time.time() + budget * 0.5)
    improvement = improve(
        grid, tasks, blocked_slots, preferences, lab_ctx, deadline, random.Random(101)
    )
    settled.append(
        settle_safely(grid, tasks, blocked_slots, preferences, school, time.time() + budget / 4)
    )
    breaches = summary(grid_breaches(grid, tasks, blocked_slots))

    for task in leftovers:
        errors.append(unplaced_message(grid, task, blocked_slots))
    errors.extend(_slack_advice(leftovers, prefs_qs, blocked_slots, tasks))
    # ومن بقيت له حصّةٌ متعذّرةٌ لا يُقال عنه «يومٌ فارغ» — فالفراغُ أثرُها.
    errors.extend(
        _empty_day_reports(grid, tasks, {m.teacher_id for t in leftovers for m in t.members})
    )

    elapsed_ms = int((time.time() - start_time) * 1000)

    # 5. حساب الجودة
    # المطلوبُ بحصص التوزيعات — الوحدةُ نفسُها التي يُعَدّ بها الموضوع.
    required_periods = sum(t.span * len(t.members) for t in sorted_tasks)
    quality = calculate_quality_score(grid, preferences, total_required=required_periods)

    # 6. حفظ النتائج — والإيقافُ يُسأل مرّةً أخيرةً تحت قفل الصفّ، فلا يسبقه الحفظُ ولا يكتب فوقه.
    if not errors or quality["total_slots"] > 0:
        try:
            with transaction.atomic():
                if should_stop is not None and generation is not None:
                    running = ScheduleGeneration.objects.select_for_update().filter(
                        pk=generation.pk, status="running"
                    )
                    if not running.exists():
                        raise GenerationStoppedError
                # صفُّ التوليد قبل حصصه: الحصّةُ تحمل مرجعَ توليدها، فلا بدّ أن
                # يكون له مفتاحٌ قبل `bulk_create`.
                if generation is None:
                    generation = ScheduleGeneration.objects.create(
                        school=school,
                        academic_year=academic_year,
                        generated_by=user,
                        status="running",
                    )

                if publish:
                    # حذف الجدول القديم — النشرُ الفوريّ
                    ScheduleSlot.objects.filter(
                        school=school, academic_year=academic_year, is_active=True
                    ).update(is_active=False)

                # صفٌّ لكلّ (خانة × ساكن) بوقته من الجرس ووسمه — الكتابةُ نفسُها
                # التي يكتب بها سدادُ الجدول الحيّ مسودّتَه (`scheduler_persist`).
                ScheduleSlot.objects.bulk_create(
                    slots_from_grid(school, academic_year, grid, generation, publish)
                )

                # سجل التوليد — تحديثُ الصفّ القائم إن مُرِّر، وإنشاؤه إن لم يُمرَّر.
                fields = {
                    "status": "draft",
                    "quality_score": quality["score"],
                    # رقمٌ واحدٌ من مصدرٍ واحد: عددُ مخالفات المُقيِّم نفسُه الذي تقرؤه بوّابةُ الاعتماد
                    # (`config_snapshot["breaches"]["count"]`). وكان `len(errors)` يُضاف إليه — وهو نصوصٌ
                    # (نصائحُ الهامش وتقاريرُ «يومٌ فارغ» وسطرٌ لكلّ متعذّرة) لا مخالفات، فيظهر 8 والإقرارُ عن 1.
                    "hard_violations": breaches["count"],
                    "soft_violations": quality["violations"],
                    "total_slots_created": quality["total_slots"],
                    "generation_time_ms": elapsed_ms,
                    "finished_at": timezone.now(),
                    "error_message": "",
                    "config_snapshot": {
                        "total_tasks": len(tasks),
                        # كم محاولةً من الثماني أُنفقت — فالزمنُ يُقرأ بها لا بالثواني
                        # وحدَها: محاولتان في ستّين ثانيةً غيرُ ثمانٍ في اثنتي عشرةَ دقيقة.
                        "attempts": attempt + 1,
                        "chosen_attempt": chosen,
                        "budget_seconds": budget,
                        #: قُطع إصلاحُ **المحاولة المختارة** بنفاد الميزانية — فمتعذّراتُها قد تكون من قطعٍ لا من استحالة.
                        #: (لا العلمُ العامّ: محاولةٌ تامّةٌ قبل الموعد اختيرت ثمّ قُطعت التي بعدها ⇒ `False`.)
                        "budget_cut": chosen_cut,
                        #: ولو قُطعت المحاولةُ المختارة فالرخصتان (التلاصق، الكثافة) **لم تُجرَّبا** — و`relaxed`/`densed`
                        #: صفرٌ حينها لا لأنّ الرخصةَ لم تنفع بل لأنّها لم تُجرَّب.
                        "licences_tried": not chosen_cut,
                        #: وبيانُ القطع العامّ للبحث: أيُّ محاولةٍ أوّلاً وبعد كم ثانية (للتشخيص — قد لا تكون المختارة).
                        "search_budget_exhausted": search_deadline.hit,
                        "budget_cut_attempt": search_deadline.hit_attempt,
                        "budget_cut_after_s": search_deadline.hit_after,
                        "attempt_log": attempt_log,
                        "improvement": improvement,
                        #: ما بقي مكسوراً بعد السداد — بموضعه، لبوّابة الاعتماد (SCH-04).
                        "settlement": settled,
                        "breaches": breaches,
                        #: المهامُّ التي لم تجد موضعاً — رقمٌ مستقلٌّ لا يدخل عدّادَ المخالفات.
                        "unplaced": len(leftovers),
                        "repaired": repaired,
                        "relaxed": relaxed,
                        "densed": densed,
                        "preferences_count": len(preferences),
                        #: حكمُ العدّ يومَ التوليد — فجدولٌ نصفُ تامٍّ يُقرأ بعد
                        #: أشهرٍ ولا يُعرف أكان المولّدُ عاجزاً أم الطلبُ فوقَ
                        #: الطاقة. راجع `schedule_feasibility`.
                        "feasibility": _feasibility_snapshot(school, academic_year),
                        #: رتبُ الكسر السارية يومَ التوليد — فجدولٌ فيه تلاصقٌ
                        #: يُقرأ بعد أشهرٍ ويُعرف أكان رخصةَ ضرورةٍ أم قراراً.
                        "constraints": grid.policy.as_dict(),
                    },
                }
                for key, value in fields.items():
                    setattr(generation, key, value)
                generation.save(update_fields=list(fields))
        except GenerationStoppedError:
            return _stopped_result()
        except Exception as exc:
            logger.exception("فشل حفظ الجدول المولَّد: %s", exc)
            # نصُّ الاستثناء للسجلّ لا للواجهة: هذه القائمةُ تصير `error_message`
            # وتُبثّ JSON إلى المتصفّح، وقد تحمل مساراتٍ أو أسماءَ جداولَ أو
            # جزءاً من تتبّع المكدّس. فيُقال للمستخدم ما يفعله لا ما رآه النظام.
            errors.append("فشل حفظ الجدول المولَّد — سُجّلت التفاصيلُ للمشغّل.")

    return {
        "success": len(errors) == 0,
        "grid": grid,
        "quality": quality,
        "generation": generation,
        "errors": errors,
        #: المهامُّ نفسُها والمتعذّرُ منها — للتشخيص والاختبار، لا للحفظ.
        "tasks": tasks,
        "leftover_tasks": leftovers,
        "elapsed_ms": elapsed_ms,
        "total_tasks": len(tasks),
        "repaired": repaired,
        "relaxed": relaxed,
        "densed": densed,
        "breaches": breaches,
    }

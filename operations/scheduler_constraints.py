"""
scheduler_constraints.py — القيود الصلبة والمرنة للجدولة الذكية
قطر
═══════════════════════════════════════════════════════════════

المرحلة 5: تحديث القيود حسب الخطة المتفق عليها:
  HC4 (تحديث): الخميس إعدادي=6, ثانوي=7
  HC5 (جديد): حد أقصى 3 حصص متتالية (صلب)
  HC6 (جديد): مادة 5+/أسبوع: حد أقصى 2 بنفس اليوم
  SC1 (تحديث): تفضيل 2 متتاليتين كحد أقصى
  SC1b (جديد): PE والعلوم المعملية لا تُحسب ضمن المتتالية
  SC7 (جديد): حصة مزدوجة لـ ART و TECH فقط
  SC8 (جديد): مادة 5+/أسبوع بنفس اليوم يجب ألا تكون متتالية
  HC10 (جديد): فراغُ المعلّم بين حصّتين لا يتجاوز سقفَه الشخصيّ (صلب لصاحبه)
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .scheduler import ScheduleGrid, Task


# ── أكواد المواد الخاصة ─────────────────────────────────────
# المواد التي تُعيد عدّاد الحصص المتتالية (لا تُحسب ضمن التتابع)
CONSECUTIVE_RESET_CODES = {"PE", "SCI"}  # بدنية + علوم معملية

#: الازدواجُ يُقرأ من `Subject.requires_double_period` وحدَه — أي من شاشة
#: إعدادات الجدول التي يملكها النائبُ الأكاديميّ.
#:
#: وكانت هنا مجموعةُ رموزٍ محفورةٌ `{"ART", "TECH"}` تُقرأ إلى جانب الحقل،
#: فيصير زرُّ الشاشة كذبةً في حقّ مادّتين: يُطفئه النائبُ فلا ينطفئ الازدواج.
#: وقرّرت الإدارةُ (2026-09-02) ألّا تُزدوَج التكنولوجيا، فلم يكن للقرار
#: طريقٌ إلى الجدول ما دام الرمزُ يفرضه من الشيفرة.
#:
#: فمصدرٌ واحدٌ لا مصدران: ما في القاعدة هو الحكم.

# المواد الأساسية (تُفضّل في الحصص الأولى)
CORE_CODES = {"ARA", "ENG", "MAT", "SCI", "CHM", "PHY", "BIO"}

# عتبة المادة ذات النصاب العالي (5+ حصص/أسبوع)
HIGH_WEEKLY_THRESHOLD = 5

#: أوزانُ القيود المرنة — تُقاس ولا تُخمَّن.
#:
#: كانت محفورةً في مواضعها، فلم يكن أحدٌ يستطيع أن يجرّب وزناً ويقيس أثرَه.
#: وأوّلُ قياسٍ بعد جمعها هنا كشف أنّ الجدولَ المولَّد يفوق المستوردَ في
#: التتابع (249 زوجاً مقابل 142) — أي أنّ وزنَ عشرةٍ للتتابع لم يكن كافياً
#: لمقاومة ترتيبٍ جشعٍ يملأ اليومَ حصّةً إثر حصّة.
WEIGHTS = {
    "consecutive": 10,
    "gap": 8,
    "subject_spread": 6,
    "daily_load": 5,
    "core_early": 3,
    "pe_after_break": 2,
    "double_bonus": -5,
    "high_weekly_adjacent": 7,
    #: الحصّةُ السابعةُ آخرُ اليوم وأثقلُه. والقاعدةُ المطلوبة «سابعةٌ واحدةٌ
    #: للمعلّم في الأسبوع»، ولا تُبلَغ بالمنع: في المدرسة مئةٌ واثنتا عشرةَ
    #: خانةً سابعةً وثلاثةٌ وسبعون معلّماً — أي سابعةٌ ونصفٌ لكلٍّ في المتوسّط،
    #: فالواحدةُ مستحيلةٌ حسابيّاً. فيُثقَّل الوزنُ ليقترب منها ما أمكن.
    "extra_last_period": 12,
}


# ══════════════════════════════════════════════════════════════
# 1. القيود الصلبة (Hard Constraints)
# ══════════════════════════════════════════════════════════════


def check_teacher_conflict(grid: ScheduleGrid, day: int, period: int, teacher_id) -> bool:
    """HC1: المعلم لا يُدرّس فصلين في نفس الوقت"""
    return not grid.teacher_busy(teacher_id, day, period)


def check_class_conflict(grid: ScheduleGrid, day: int, period: int, class_id) -> bool:
    """HC2: الفصل لا يأخذ مادتين في نفس الوقت

    والشعبتانِ في التوقيت نفسه توازٍ لا تعارض: هذا هو معنى المدرسة. فيُسأل عن
    خانةِ الشعبة وحدَها، لا عن ساكنِ التوقيت في المدرسة كلِّها.
    """
    return not grid.class_busy(class_id, day, period)


def check_period_variety(grid: ScheduleGrid, period: int, task: Task) -> bool:
    """HC7: لا تُكدَّس المادّةُ في حصّةٍ واحدةٍ من اليوم طوالَ الأسبوع.

    كان الجدولُ يُخرج الرياضياتِ للثاني عشر/4 في الحصّة الخامسة **كلَّ يوم** —
    وذلك لأنّ لا شيءَ كان يمنعه: القيودُ تنظر إلى اليوم ولا تنظر إلى موقع
    الحصّة فيه.

    والحدُّ مرّتان لا مرّة: أسبوعٌ بخمسة أيّامٍ ونصابٌ ستُّ حصصٍ لا يسع تنويعاً
    كاملاً حين تضيق الخانات، ومنعُ التكرار بالكلّيّة يجعل الجدولَ متعذّراً في
    مدرسةٍ إشغالُها ثمانيةٌ وتسعون بالمئة.
    """
    return grid.subject_at_period(task.class_id, task.subject_id, period) < MAX_SAME_PERIOD


def check_resource_capacity(grid: ScheduleGrid, day: int, period: int, task: Task) -> bool:
    """HC9: لا تتجاوز الحصصُ سعةَ المورد في التوقيت الواحد.

    القيدُ على **المكان** لا على المعلّم ولا على الشعبة: خمسةُ معلّمي بدنيّةٍ
    وملعبان، فلا تقع ثالثةٌ مهما كان المعلّمون فارغين. ومعملا حاسبٍ يتقاسمهما
    أكثرُ من مادّة، فالسقفُ عليهما مجتمعَين.
    """
    return all(
        grid.resource_load(resource_id, day, period) < capacity
        for resource_id, capacity, *_ in task.resources
    )


def check_resource_level_homogeneity(grid: ScheduleGrid, day: int, period: int, task: Task) -> bool:
    """HC11: موردٌ لا يجمع مرحلتين في التوقيت الواحد.

    الملعبانِ يتقاسمهما الإعداديّ والثانويّ، لكنّ حصّتَي بدنيّةٍ متزامنتين
    تكونان من مرحلةٍ واحدة (قرار الإدارة 2026-09-03). السعةُ تقول «اثنتان»،
    وهذا يقول «اثنتان من جنسٍ واحد». والمهمّةُ بلا مرحلةٍ معروفة تُعامَل
    جنساً قائماً بذاته، فلا تُخلط بغيرها.
    """
    for resource_id, _capacity, same_level in task.resources:
        if not same_level:
            continue
        others = grid.resource_levels(resource_id, day, period) - {task.level_type}
        if others:
            return False
    return True


def check_last_period_share(grid: ScheduleGrid, period: int, task: Task) -> bool:
    """HC8: لا تتكدّس الحصّةُ السابعةُ على معلّمٍ بعينه.

    والقاعدةُ المطلوبةُ «سابعةٌ واحدةٌ في الأسبوع»، ولا تُبلَغ بالمنع: في
    المدرسة مئةٌ واثنتا عشرةَ خانةً سابعةً وثلاثةٌ وسبعون معلّماً، فالواحدةُ
    مستحيلةٌ حسابيّاً. فالحدُّ اثنتان — وهو أقربُ ما يُبلَغ — والوزنُ المرنُ
    المتصاعدُ يدفع نحو الواحدة داخل هذا الحدّ.
    """
    if period != LAST_PERIOD:
        return True
    for m in task.members:
        if grid.teacher_last_periods(m.teacher_id) >= MAX_LAST_PERIODS:
            return False
        #: وسابعتا المعلّم لا تقعان على شعبةٍ واحدة: آخرُ اليوم أثقلُ ما فيه،
        #: فإن تكرّر على الشعبة نفسها حمَلت وحدَها ضعفَ ما تحمله أخواتُها من
        #: تعبِ ذلك المعلّم. فالثقلُ يُقسَم على الشُّعب كما يُقسَم على الأيّام.
        if task.class_id in grid.teacher_last_period_classes(m.teacher_id):
            return False
    return True


def check_subject_distribution(
    grid: ScheduleGrid, day: int, task: Task, allow_dense: bool = False
) -> bool:
    """HC6: المادّةُ تُوزَّع على أيّام الأسبوع بالقسمة، لا تُكدَّس.

        perDayCap = ⌈W / D⌉        daysAtCap = W mod D

    فمادّةٌ بستّ حصصٍ في أسبوعٍ خماسيّ: أربعةُ أيّامٍ بحصّة، ويومٌ واحدٌ
    بحصّتين. ومعلّمٌ مفرَّغٌ يوماً يعمل أربعةَ أيّام، فيصير المزدوجُ يومين.

    وشرطان لا واحد: لا يومَ يتجاوز السقف، ولا عددَ الأيّام البالغةِ السقفَ
    يتجاوز حصّتَه. فبالأوّل وحدَه يجوز 2+2+2 في ثلاثة أيّامٍ ويومان فارغان —
    توزيعٌ يستوفي السقفَ ويُخالف القسمة.

    وكان هنا قيدٌ أضيق: «مادّةُ 5+ حصصٍ لا تتجاوز حصّتين في اليوم». وهو صحيحٌ
    في نتيجته لهذه الحالة، وصامتٌ عمّا دونها وعن عدد الأيّام.
    """
    #: `allow_dense` رخصةٌ تُصرَف في الجولة الأخيرة وحدَها: تسمح ليومٍ واحدٍ
    #: بحصّةٍ زائدةٍ عن القسمة — مادّةٌ مرّتين في يومٍ ولا شيءَ منها في آخر.
    #: وهي أغلى من رخصة التلاصق، فلا تُصرَف إلّا بعد أن تعجز تلك.
    cap = task.per_day_cap + (1 if allow_dense else 0)
    today = grid.subject_on_day(task.class_id, task.subject_id, day)
    if today + 1 > cap:
        return False

    if today + 1 < cap:
        return True

    # هذه الحصّةُ تُبلغ اليومَ سقفَه — فهل بقي في الحصّة يومٌ يبلغه؟
    from .scheduler import DAYS

    at_cap = sum(
        1
        for d in DAYS
        if d != day and grid.subject_on_day(task.class_id, task.subject_id, d) >= cap
    )
    return at_cap + 1 <= task.days_allowed_at_cap


#: أقصى ما يُقبل من حصصٍ متلاصقةٍ للمعلّم الواحد — واحدةٌ أي: لا تلاصقَ.
#:
#: كان ثلاثاً، فأخرج المولّدُ إحدى وعشرين ثلاثيّةً بينما في الجدول المستورد —
#: الذي وضعه بشرٌ — أربع. فصار اثنتين فسقطت الثلاثيّاتُ كلُّها، ثمّ قرّرت
#: الإدارةُ ألّا تلاصقَ أصلاً فصار واحدة.
#:
#: والاستثناءُ الوحيد الحصّةُ المزدوجةُ المقصودة — أي مادّةٌ وُسِمت بالازدواج
#: في إعدادات الجدول: المعلّمُ باقٍ مع شعبته في غرفته، وذلك هو الغرضُ لا
#: عَرَضٌ يُتعب.
MAX_CONSECUTIVE = 1

#: أكثرُ ما تتكرّر المادّةُ الواحدةُ في الموضع نفسِه من اليوم خلال الأسبوع.
MAX_SAME_PERIOD = 2

#: آخرُ حصّةٍ في اليوم.
LAST_PERIOD = 7

#: أطولُ فاصلٍ بين حصّتين يبقيان معه في كتلةٍ واحدة (بالدقائق).
#: فخمسُ دقائقَ انتقالٌ بين صفّين، وعشرون فسحةٌ وخمسَ عشرةَ صلاة.
JOINABLE_GAP_MINUTES = 10

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


def joinable_pairs(school) -> set:
    """أزواجُ الحصص المتلاصقةِ فعلاً — من جرس المدرسة لا من الكود.

    الحصّةُ المزدوجةُ حصّتان لا تقطعهما فسحةٌ ولا صلاة. وبين الثالثة والرابعة
    في الشحانية عشرون دقيقة، وبين الخامسة والسادسة خمسَ عشرة — فالتلاصقُ
    عبرهما تلاصقٌ في الورق لا في اليوم.

    ومدرسةٌ لم تُدخل أوقاتَها بعد: لا كتلَ تُعرَف، فلا يُمنع تجاورٌ بحجّة
    فاصلٍ لا نعرفه. والصمتُ لا يُقرأ منعاً.
    """
    cache = _PAIRS_CACHE.get()
    key = getattr(school, "pk", school)
    if cache is not None and key in cache:
        return cache[key]
    pairs = _joinable_pairs_from_bell(school)
    if cache is not None:
        cache[key] = pairs
    return pairs


def _joinable_pairs_from_bell(school) -> set:
    from operations.models import TimeSlotConfig

    rows = list(
        TimeSlotConfig.objects.filter(school=school, day_type="regular", is_break=False).order_by(
            "period_number"
        )
    )
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


#: أكثرُ ما يُقبل من حصصٍ سابعةٍ للمعلّم في الأسبوع.
#:
#: المطلوبُ واحدة، وهي مستحيلةٌ حسابيّاً في هذه المدرسة: مئةٌ واثنتا عشرةَ
#: خانةً سابعةً وثلاثةٌ وسبعون معلّماً — أي سابعةٌ ونصفٌ لكلٍّ في المتوسّط.
#: فالحدُّ اثنتان، والوزنُ المتصاعدُ يدفع نحو الواحدة ما أمكن.
MAX_LAST_PERIODS = 2


def _wants_adjacency(grid: ScheduleGrid, task: Task, day: int, period: int) -> bool:
    """الحصّةُ المزدوجةُ المقصودة: نفسُ المادّةِ لنفس الشعبة، ومادّةٌ تُزاوَج.

    فالمعلّمُ يبقى مع شعبته في غرفته — وهذا هو الغرضُ لا عَرَضٌ يُتعب.
    """
    if not getattr(task, "prefers_double", False):
        return False
    return _neighbour_is_same_lesson(grid, task, day, period)


def check_max_consecutive(
    grid: ScheduleGrid, day: int, period: int, task: Task, allow_adjacent: bool = False
) -> bool:
    """HC5: لا أكثرَ من حصّتين متلاصقتين للمعلّم.

    و`PE`/`SCI` تُعيد العدّاد: البدنيّةُ والعلومُ المعمليّةُ تغيّران المكانَ
    والنشاطَ، فلا تُحسبان امتداداً لما قبلهما.

    ويُسأل عن كلّ ساكنٍ في الشعبة المنقسمة: المعلّمانِ يعملان معاً، فتتابعُ
    كلٍّ منهما تتابعُه هو.
    """
    if _wants_adjacency(grid, task, day, period):
        return True
    #: `allow_adjacent` تُرفع للمتعذّرات وحدَها في الجولة الأخيرة: زوجٌ يُسمح
    #: به هنا خيرٌ من حصّةٍ تُترك بلا مكان — والثلاثيّةُ ممنوعةٌ في الحالين.
    #:
    #: أمّا سقفُ معلّمٍ بعينه فلا يُرفع بحال: قرارٌ في حقّه أثقلُ من سقفٍ عامٍّ
    #: وُضع ليُقارَب. فمن مُنع من التجاور مُنع ولو بقيت حصّةٌ بلا مكان.
    #: قرارٌ في حقّ الشخص يسبق كلَّ رخصةٍ عامّةٍ أو موضعيّة.
    if task.consecutive_cap:
        return all(
            _run_length(grid, m.teacher_id, day, period) < task.consecutive_cap
            for m in task.members
        )

    limit = MAX_CONSECUTIVE + 1 if allow_adjacent else MAX_CONSECUTIVE
    for member in task.members:
        run = _run_length(grid, member.teacher_id, day, period)
        if run < limit:
            continue
        # الرخصةُ الموضعيّة: زوجٌ واحدٌ في الأسبوع لمن استحقّها — ولا ثلاثيّة.
        allowance = task.adjacency_allowance
        if not allowance or run >= MAX_CONSECUTIVE + 1:
            return False
        if grid.teacher_adjacent_pairs(member.teacher_id) >= allowance:
            return False
    return True


def check_max_gap(grid: ScheduleGrid, day: int, period: int, task: Task) -> bool:
    """HC10: فراغُ المعلّم بين حصّتين لا يتجاوز سقفَه الشخصيّ.

    والفراغُ لعامّة الكادر ترجيحٌ مرنٌ (SC2): يُثقَّل ولا يُمنع، لأنّ منعَه
    للجميع يُغلق جدولاً إشغالُه ثمانيةٌ وتسعون بالمئة. أمّا من قرّرت الإدارةُ
    في حقّه سقفاً فسقفُه صلبٌ لا يُرفع في الاسترخاء — شأنَ `consecutive_cap`.

    ومعلّمٌ سقفُه فراغٌ واحدٌ ولا تلاصقَ له: حصصُه في اليوم تتباعد حصّةً حصّة
    — الثانيةُ فالرابعةُ فالسادسة، لا الثالثةُ فالسادسة.

    والقياسُ على اليوم كلِّه بعد الوضع، لا على الجارِ وحدَه: خانةٌ تُوضع بين
    حصّتين متباعدتين تُضيّق الفراغَ ولا توسّعه، فلا يصحّ أن تُمنع.
    """
    if task.gap_cap is None:
        return True
    slots = list(task.slots(period))
    return all(
        grid.teacher_widest_gap_with(m.teacher_id, day, slots) <= task.gap_cap for m in task.members
    )


def _run_length(grid: ScheduleGrid, teacher_id: str, day: int, period: int) -> int:
    """طولُ التلاصق حول هذه الخانة — بلا استثناءِ مادّةٍ ولا صنف.

    و`teacher_consecutive_counted` تُعفي `PE`/`SCI` من العدّ، وهو تخفيفٌ يليق
    بترجيحٍ مرن. أمّا المنعُ الصلبُ فيسأل سؤالاً واحداً: أيقف المعلّمُ حصّتين
    متلاصقتين أم لا؟ والبدنيّةُ حصّةٌ يقفها كغيرها.
    """
    count = 0
    for step in (-1, 1):
        neighbour = period + step
        while 1 <= neighbour <= 7 and grid.teacher_busy(teacher_id, day, neighbour):
            count += 1
            neighbour += step
    return count


def check_high_weekly_daily_limit(grid: ScheduleGrid, day: int, task: Task) -> bool:
    """
    HC6 (جديد): مادة 5+ حصص/أسبوع: حد أقصى 2 حصص بنفس اليوم للشعبة.
    """
    if task.weekly_periods < HIGH_WEEKLY_THRESHOLD:
        return True  # لا ينطبق على مواد أقل من 5
    count = grid.subject_on_day(task.class_id, task.subject_id, day)
    return count < 2


#: سقفُ حصص الشعبة في اليوم مصونٌ بهذا المدى وحده.
#:
#: كان هنا `check_day_capacity` تعدّ حصصَ الشعبة وتقارنها بالسقف، ولم تكن
#: تُستدعى من أيّ موضع. وحُذفت لأنّها لا تضيف ثابتاً مستقلّاً: الشعبةُ لا تشغل
#: خانتين في الحصّة الواحدة (`check_class_conflict`)، والحصصُ محدودةٌ بالمدى
#: أدناه — فعددُها في اليوم لا يتجاوزه بحال. ودالّةٌ تبدو حارساً وليست في
#: المسار فخٌّ لمن يقرأ بعدنا.
def get_max_periods_for_day(day: int, level_type: str = "") -> int:
    """
    HC4 (تحديث): الحد الأقصى لحصص اليوم.
    الخميس (day=4): إعدادي=6, ثانوي=7.
    باقي الأيام: 7 دائماً.
    """
    if day != 4:
        return 7
    if level_type == "prep":
        return 6
    if level_type == "sec":
        return 7
    return 6  # default = 6 (الأكثر تقييداً)


def is_slot_valid(
    grid: ScheduleGrid,
    day: int,
    period: int,
    task: Task,
    allow_adjacent: bool = False,
    allow_dense: bool = False,
) -> bool:
    """تحقق من كل القيود الصلبة لخانة معينة"""
    level_type = getattr(task, "level_type", "")
    max_p = get_max_periods_for_day(day, level_type)
    if period > max_p:
        return False
    if not check_teacher_conflict(grid, day, period, task.teacher_id):
        return False
    if not check_class_conflict(grid, day, period, task.class_id):
        return False
    if not check_max_consecutive(grid, day, period, task, allow_adjacent):
        return False
    if not check_subject_distribution(grid, day, task, allow_dense):
        return False
    if not check_period_variety(grid, period, task):
        return False
    if not check_last_period_share(grid, period, task):
        return False
    if not check_resource_capacity(grid, day, period, task):
        return False
    if not check_resource_level_homogeneity(grid, day, period, task):
        return False
    if not check_max_gap(grid, day, period, task):
        return False
    return True


# ══════════════════════════════════════════════════════════════
# 2. القيود المرنة (Soft Constraints)
# ══════════════════════════════════════════════════════════════


@dataclass
class SoftPenalty:
    """نتيجة تقييم القيود المرنة لخانة"""

    total: float = 0.0
    details: dict = field(default_factory=dict)

    def add(self, name: str, weight: float, violated: bool):
        if violated:
            self.total += weight
            self.details[name] = weight


def _neighbour_is_same_lesson(grid: ScheduleGrid, task: Task, day: int, period: int) -> bool:
    """هل جارُ هذه الخانة — قبلَها أو بعدَها — نفسُ المادّة لنفس الشعبة؟"""
    for step in (-1, 1):
        neighbour = period + step
        if 1 <= neighbour <= 7:
            other = grid.get_task_at(task.class_id, day, neighbour)
            if other is not None and other.subject_id == task.subject_id:
                return True
    return False


def evaluate_soft_constraints(
    grid: ScheduleGrid,
    day: int,
    period: int,
    task: Task,
    preferences: dict | None = None,
) -> SoftPenalty:
    """تقييم القيود المرنة لتحديد أفضل خانة"""
    penalty = SoftPenalty()

    # ── SC1 (تحديث): تتابع الحصص — تفضيل 2 كحد أقصى (3 = عقوبة) ──
    consecutive = grid.teacher_consecutive_counted(task.teacher_id, day, period)
    # الحصّةُ المزدوجةُ استثناءٌ مقصود: مادّةٌ وُسِمت بالازدواج تُرجَّح متجاورةً
    # لأنّ المعلّمَ يبقى مع الشعبة نفسها في الغرفة نفسها — فليست تتابعاً
    # يُتعب، بل هي الغرضُ نفسُه. وما عداها يُعاقَب من أوّل تلاصق.
    wants_adjacent = getattr(task, "prefers_double", False) and _neighbour_is_same_lesson(
        grid, task, day, period
    )
    penalty.add("consecutive", WEIGHTS["consecutive"], consecutive >= 1 and not wants_adjacent)

    # ── SC2: فراغات المعلم — تقليل الفجوات ──
    creates_gap = grid.would_create_gap(task.teacher_id, day, period)
    penalty.add("gap", WEIGHTS["gap"], creates_gap)

    # ── SC3: التوزيعُ يملأ الأيّامَ الفارغةَ قبل أن يُضاعف ──
    #
    # كان يعاقب **كلَّ** حصّةٍ ثانيةٍ في اليوم، فسجّل ٧٩٢ «مخالفة» في جدولٍ
    # صحيح: لأنّ كلَّ مادّةٍ سداسيّةٍ يلزمها يومٌ مزدوجٌ بالضرورة، فكان
    # المقياسُ يعاقب الصوابَ ويسمّيه خطأً.
    #
    # والقسمةُ الآن قيدٌ صلب (`check_subject_distribution`)، فلم يبقَ لهذا
    # الوزن إلّا ترتيبُ الأفضليّة: املأ يوماً فارغاً قبل أن تُضاعف يوماً عامراً.
    # العدُّ يستثني المهمّةَ نفسَها حين تكون موضوعةً سلفاً.
    #
    # فالدالّةُ تُستدعى مرّتين: قبل الوضع لترجيح الخانة — والمهمّةُ حينها ليست
    # في الشبكة — وبعد التوليد لحساب الجودة، وهي حينها فيها. فبلا هذا
    # الاستثناء يصير «عندي حصّةٌ اليوم» صادقاً عن نفسه دائماً، فتُحسب مخالفةٌ
    # لكلّ حصّةٍ في المدرسة.
    same_subject_today = grid.subject_on_day(task.class_id, task.subject_id, day)
    if grid.get_task_at(task.class_id, day, period) is task:
        same_subject_today -= 1

    is_double = getattr(task, "prefers_double", False)
    if not is_double:
        from .scheduler import DAYS

        empty_days = sum(
            1
            for d in DAYS
            if grid.subject_on_day(task.class_id, task.subject_id, d) == 0 and d != day
        )
        penalty.add(
            "subject_spread", WEIGHTS["subject_spread"], same_subject_today > 0 and empty_days > 0
        )

    # ── SC4: موازنة الأحمال — تقليل فرق الحصص اليومية للمعلم ──
    teacher_today = grid.teacher_periods_on_day(task.teacher_id, day)
    max_daily = 5
    if preferences and task.teacher_id in preferences:
        max_daily = preferences[task.teacher_id].get("max_daily", 5)
    penalty.add("daily_load", WEIGHTS["daily_load"], teacher_today >= max_daily)

    # ── SC9: سابعةٌ واحدةٌ للمعلّم ما أمكن ──
    if period == LAST_PERIOD:
        # العقوبةُ تتصاعد: من عنده ثلاثُ سوابعَ يُثقَّل أكثرَ ممّن عنده واحدة،
        # فتنساب السوابعُ على الكادر بدل أن تتكدّس على قلّةٍ منه.
        already = max(grid.teacher_last_periods(m.teacher_id) for m in task.members)
        penalty.add("extra_last_period", WEIGHTS["extra_last_period"] * already, already >= 1)

    # ── SC5: المواد الأساسية في الحصص الأولى ──
    is_core = task.subject_code in CORE_CODES
    penalty.add("core_early", WEIGHTS["core_early"], is_core and period >= 6)

    # ── SC6: البدنية بعد الاستراحة ──
    is_pe = task.subject_code == "PE"
    penalty.add("pe_after_break", WEIGHTS["pe_after_break"], is_pe and period not in (4, 5))

    # ── SC7: مكافأة الحصة المزدوجة (DB + كود) ──
    if is_double and same_subject_today == 1:
        # المعلم لديه حصة واحدة لهذه المادة اليوم — مكافأة إذا متتالية
        # المزاوجةُ صفةُ شعبةٍ ومادّة — تُقرأ داخل شعبتها لا في التوقيت العامّ.
        prev_task = grid.get_task_at(task.class_id, day, period - 1) if period > 1 else None
        if prev_task and prev_task.subject_id == task.subject_id:
            penalty.add("double_bonus", WEIGHTS["double_bonus"], True)  # مكافأة (قيمة سالبة)

    # ── SC8 (جديد): مادة 5+/أسبوع — الحصتان بنفس اليوم لا تكونان متتاليتين ──
    if task.weekly_periods >= HIGH_WEEKLY_THRESHOLD and same_subject_today == 1:
        prev_task = grid.get_task_at(task.class_id, day, period - 1) if period > 1 else None
        next_task = grid.get_task_at(task.class_id, day, period + 1) if period < 7 else None
        is_adj_same = (prev_task and prev_task.subject_id == task.subject_id) or (
            next_task and next_task.subject_id == task.subject_id
        )
        penalty.add("high_weekly_adjacent", WEIGHTS["high_weekly_adjacent"], is_adj_same)

    return penalty


# ══════════════════════════════════════════════════════════════
# 3. حساب نقاط الجودة الإجمالية
# ══════════════════════════════════════════════════════════════


def calculate_quality_score(
    grid: ScheduleGrid, preferences: dict | None = None, total_required: int | None = None
) -> dict:
    """نقاطُ الجودة، ونسبةُ ما وُضِع من المطلوب — رقمان لا واحد.

    فالنقاطُ تقيس جمالَ ما وُضع: تتابعاً وفجواتٍ وتوزيعاً. وجدولٌ فيه خمسٌ
    وثلاثون حصّةً من ثمانمئةٍ وتسعٍ وأربعين قد يكون «جميلاً» بهذا المقياس —
    وأُعلن مرّةً بـ«85.1%» وهو أربعةٌ في المئة من المطلوب. فالنسبةُ تُعلن
    مستقلّةً كي لا يستر أحدُ الرقمين الآخر.
    """
    violations = {
        "consecutive": 0,
        "gap": 0,
        "subject_spread": 0,
        "daily_load": 0,
        "core_early": 0,
        "pe_after_break": 0,
        "double_bonus": 0,
        "high_weekly_adjacent": 0,
    }
    total_penalty = 0.0
    total_slots = 0

    for entry in grid.all_entries():
        total_slots += 1
        task = entry["task"]
        day = entry["day"]
        period = entry["period"]
        p = evaluate_soft_constraints(grid, day, period, task, preferences)
        total_penalty += p.total
        for k, v in p.details.items():
            violations[k] = violations.get(k, 0) + 1

    # نقاط الجودة: 100 - (العقوبات المرجحة / العدد الكلي)
    # مجموعُ الأوزان الموجبة — يتبع `WEIGHTS` ولا يُكتب رقماً جامداً.
    ceiling = sum(w for w in WEIGHTS.values() if w > 0)
    max_possible = total_slots * ceiling
    if max_possible == 0:
        score = 100.0
    else:
        score = max(0, 100 * (1 - total_penalty / max_possible))

    required = total_required if total_required is not None else total_slots
    placed_ratio = round(100 * total_slots / required, 1) if required else 100.0

    return {
        "score": round(score, 1),
        "total_slots": total_slots,
        "total_required": required,
        "placed_ratio": placed_ratio,
        "total_penalty": round(total_penalty, 1),
        "violations": violations,
    }

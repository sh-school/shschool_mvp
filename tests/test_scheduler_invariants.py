"""[SCHEDULER] ثوابتُ الجدول المولَّد — لا تغطيةً بل صلاحيةَ الناتج.

`operations/scheduler.py` (٢٢٩ عبارة) و`operations/scheduler_constraints.py`
(١٠١) كانا بصفرٍ بالمئة تغطيةً، وهما اللذان يُنتجان جدولَ المدرسة كلِّه ويحلّان
تعارضاتِه. وخطأُ الجدولة لا ينهار: يُخرج جدولاً معقولَ المظهر لا يُكتشف عيبُه
إلّا حين يقف معلّمٌ أمام صفّين في التوقيت نفسه.

فالهدفُ هنا ليس رفعَ رقم، بل **إثباتُ صلاحيةِ ما يخرج**. وخمسةُ ثوابت:

  ١) لا معلّمَ في مكانين في التوقيت نفسه.
  ٢) لا شعبةَ في مادّتين في التوقيت نفسه.
  ٣) لا تجاوزَ لسقف حصص اليوم.
  ٤) لا حصّةَ في وقتِ إعفاء.
  ٥) كلُّ حصّةٍ مطلوبةٍ إمّا أُسندت مرّةً واحدةً أو خرجت فشلاً صريحاً
     مُفسَّراً — لا تختفي بصمت.

ولكلّ ثابتٍ دعوى إيجابيّةٌ تُثبت أنّه يُصان، ودعوى **سلبيّةٌ تكسره عمداً**
وتُثبت أنّ الحارسَ يرفض — فحارسٌ لم يُختبَر رفضُه ليس حارساً.
"""

import pytest

from operations.scheduler import DAYS, ScheduleGrid, Task
from operations.scheduler_constraints import (
    check_class_conflict,
    check_high_weekly_daily_limit,
    check_max_consecutive,
    check_teacher_conflict,
    get_max_periods_for_day,
    is_slot_valid,
)

TEACHER = "t-1"
OTHER_TEACHER = "t-2"
CLASS = "c-1"
OTHER_CLASS = "c-2"


def make_task(
    *,
    teacher=TEACHER,
    klass=CLASS,
    subject="s-1",
    code="MAT",
    weekly=4,
    level_type="prep",
):
    return Task(
        class_id=klass,
        class_name="7/1",
        subject_id=subject,
        subject_name="رياضيات",
        subject_code=code,
        teacher_id=teacher,
        teacher_name="معلّم",
        weekly_periods=weekly,
        level_type=level_type,
    )


# ══════════════════════════════════════════════════════════════
#  الثابت ١ — لا معلّمَ في مكانين
# ══════════════════════════════════════════════════════════════


def test_a_teacher_may_not_stand_before_two_sections_at_once():
    """الخطأُ الذي يظهر في القاعة لا في السجلّ."""
    grid = ScheduleGrid()
    grid.place(0, 1, make_task())

    intruder = make_task(klass=OTHER_CLASS)

    assert not check_teacher_conflict(grid, 0, 1, TEACHER)
    assert not is_slot_valid(grid, 0, 1, intruder)


def test_the_same_teacher_may_teach_the_next_period():
    grid = ScheduleGrid()
    grid.place(0, 1, make_task())

    assert is_slot_valid(grid, 0, 2, make_task(klass=OTHER_CLASS))


def test_another_teacher_may_not_take_an_occupied_slot():
    """الخانةُ مشغولةٌ بمعلّمٍ آخر — والمانعُ هنا تعارضُ الشعبة لا المعلّم."""
    grid = ScheduleGrid()
    grid.place(0, 1, make_task())

    assert not is_slot_valid(grid, 0, 1, make_task(teacher=OTHER_TEACHER))


# ══════════════════════════════════════════════════════════════
#  الثابت ٢ — لا شعبةَ في مادّتين
# ══════════════════════════════════════════════════════════════


def test_a_section_may_not_receive_two_subjects_at_once():
    grid = ScheduleGrid()
    grid.place(0, 1, make_task())

    second = make_task(teacher=OTHER_TEACHER, subject="s-2", code="ENG")

    assert not check_class_conflict(grid, 0, 1, CLASS)
    assert not is_slot_valid(grid, 0, 1, second)


def test_two_sections_may_be_taught_in_parallel():
    """شعبتان مختلفتان ومعلّمان مختلفان في التوقيت نفسه — مشروع."""
    grid = ScheduleGrid()
    grid.place(0, 1, make_task())

    assert is_slot_valid(grid, 0, 1, make_task(teacher=OTHER_TEACHER, klass=OTHER_CLASS))


# ══════════════════════════════════════════════════════════════
#  الثابت ٣ — سقفُ حصص اليوم
# ══════════════════════════════════════════════════════════════


@pytest.mark.parametrize("day", [0, 1, 2, 3])
def test_the_ordinary_day_holds_seven_periods(day):
    assert get_max_periods_for_day(day, "prep") == 7
    assert get_max_periods_for_day(day, "sec") == 7


def test_thursday_is_shorter_for_preparatory():
    """الخميس: إعداديٌّ ستٌّ وثانويٌّ سبع — قرارُ المدرسة."""
    assert get_max_periods_for_day(4, "prep") == 6
    assert get_max_periods_for_day(4, "sec") == 7


def test_an_unknown_level_takes_the_stricter_thursday():
    """الجهلُ بالمرحلة يُؤخذ بالأضيق لا بالأوسع."""
    assert get_max_periods_for_day(4, "") == 6


def test_a_period_beyond_the_day_cap_is_refused():
    grid = ScheduleGrid()

    assert not is_slot_valid(grid, 4, 7, make_task(level_type="prep"))
    assert is_slot_valid(grid, 4, 7, make_task(level_type="sec"))


def test_a_full_day_admits_no_more_periods_for_the_section():
    """سبعُ حصصٍ لشعبةٍ في يوم — والثامنةُ لا موضعَ لها."""
    grid = ScheduleGrid()
    for period in range(1, 8):
        grid.place(0, period, make_task(subject=f"s-{period}"))

    assert grid.class_periods_on_day(CLASS, 0) == 7
    assert not any(is_slot_valid(grid, 0, p, make_task()) for p in range(1, 8))


# ══════════════════════════════════════════════════════════════
#  الثابت ٤ — الإعفاءات
# ══════════════════════════════════════════════════════════════


def test_an_exempt_slot_is_never_offered(db, school):
    """التفريغُ يُحترم في `get_available_slots` قبل القيود الصلبة."""
    from operations.scheduler import get_available_slots

    grid = ScheduleGrid()
    task = make_task()
    blocked = {(TEACHER, 0, p) for p in range(1, 8)}

    available = get_available_slots(grid, task, blocked)

    assert all(day != 0 for day, _period in available), "يومُ التفريغ لا يُعرض"
    assert available, "وباقي الأيّام تبقى متاحة"


def test_a_single_exempt_period_blocks_only_itself(db, school):
    from operations.scheduler import get_available_slots

    grid = ScheduleGrid()
    available = get_available_slots(grid, make_task(), {(TEACHER, 0, 3)})

    assert (0, 3) not in available
    assert (0, 2) in available and (0, 4) in available


def test_an_exemption_binds_the_exempt_teacher_alone(db, school):
    """تفريغُ معلّمٍ لا يُغلق الخانةَ على زميله."""
    from operations.scheduler import get_available_slots

    grid = ScheduleGrid()
    available = get_available_slots(grid, make_task(teacher=OTHER_TEACHER), {(TEACHER, 0, 3)})

    assert (0, 3) in available


# ══════════════════════════════════════════════════════════════
#  الثابت ٥ — لا حصّةَ تختفي بصمت
# ══════════════════════════════════════════════════════════════


@pytest.fixture
def tiny_school(db, school):
    """مدرسةٌ صغيرةٌ قابلةٌ للجدولة: شعبةٌ ومعلّمٌ ومادّةٌ بأربع حصص."""
    from core.models import ClassGroup, CustomUser
    from operations.models import Subject, SubjectClassAssignment

    teacher = CustomUser.objects.create(national_id="28800000201", full_name="معلّم الرياضيات")
    group = ClassGroup.objects.create(
        school=school, grade="G7", section="1", level_type="prep", academic_year="2026-2027"
    )
    subject = Subject.objects.create(school=school, name_ar="رياضيات", code="MAT")
    SubjectClassAssignment.objects.create(
        school=school,
        class_group=group,
        subject=subject,
        teacher=teacher,
        weekly_periods=4,
        academic_year="2026-2027",
    )
    return {"school": school, "group": group, "subject": subject, "teacher": teacher}


def test_every_required_period_becomes_exactly_one_task(tiny_school):
    """نصابٌ أربعُ حصصٍ ← أربعُ مهامّ. لا ثلاثٌ ولا خمس."""
    from operations.scheduler import build_tasks

    tasks = build_tasks(tiny_school["school"], "2026-2027")

    assert len(tasks) == 4
    assert {t.subject_code for t in tasks} == {"MAT"}


def test_an_assignment_without_a_teacher_is_skipped_not_scheduled(tiny_school):
    """توزيعٌ بلا معلّم لا يُجدوَل — ولا يُخترَع له معلّم."""
    from core.models import ClassGroup
    from operations.models import SubjectClassAssignment
    from operations.scheduler import build_tasks

    other = ClassGroup.objects.create(
        school=tiny_school["school"],
        grade="G8",
        section="1",
        level_type="prep",
        academic_year="2026-2027",
    )
    SubjectClassAssignment.objects.create(
        school=tiny_school["school"],
        class_group=other,
        subject=tiny_school["subject"],
        teacher=None,
        weekly_periods=3,
        academic_year="2026-2027",
    )

    tasks = build_tasks(tiny_school["school"], "2026-2027")

    assert len(tasks) == 4, "الثلاثُ بلا معلّمٍ لا تُضاف"


def test_a_schedulable_school_places_every_period_once(tiny_school):
    """الثابتُ الخامس في حالته السعيدة: أربعُ حصصٍ ← أربعُ خانات، بلا خطأ."""
    from operations.scheduler import generate_schedule

    result = generate_schedule(tiny_school["school"], "2026-2027")

    assert result["errors"] == []
    assert result["success"] is True
    assert result["total_tasks"] == 4
    assert len(result["grid"].all_entries()) == 4


def test_placed_periods_never_repeat_a_slot(tiny_school):
    """خانةٌ واحدةٌ لا تحمل حصّتين — ولا حصّةٌ تُوضع مرّتين."""
    from operations.scheduler import generate_schedule

    result = generate_schedule(tiny_school["school"], "2026-2027")

    slots = [(e["day"], e["period"]) for e in result["grid"].all_entries()]
    assert len(slots) == len(set(slots))


def test_an_impossible_demand_is_reported_not_dropped(tiny_school):
    """النصابُ أكبرُ من أيّامِ الأسبوع ساعاتٍ — فما لم يوضع يُسمّى.

    وهذا هو جوهرُ الثابت الخامس: الحصّةُ التي لا تُوضع يجب أن تخرج فشلاً
    مُفسَّراً باسم المادّة والشعبة والمعلّم، لا أن تسقط بلا خبر.
    """
    from operations.models import SubjectClassAssignment
    from operations.scheduler import generate_schedule

    SubjectClassAssignment.objects.filter(school=tiny_school["school"]).update(weekly_periods=40)

    result = generate_schedule(tiny_school["school"], "2026-2027")

    placed = len(result["grid"].all_entries())
    assert result["total_tasks"] == 40
    assert placed < 40, "الطلبُ فوق الطاقة"
    assert result["errors"], "وما لم يوضع لا يسقط صامتاً"
    assert result["success"] is False
    assert any("رياضيات" in e for e in result["errors"]), "الخطأُ يسمّي المادّة"


def test_nothing_is_scheduled_when_there_is_nothing_to_schedule(db, school):
    """لا توزيعات ← فشلٌ معلَّلٌ لا جدولٌ فارغٌ يُوهم بالنجاح."""
    from operations.scheduler import generate_schedule

    result = generate_schedule(school, "2026-2027")

    assert result["success"] is False
    assert result["errors"]


# ══════════════════════════════════════════════════════════════
#  قيودٌ أخرى قائمةٌ في المحرّك — تُثبَّت كما هي
# ══════════════════════════════════════════════════════════════


def test_a_teacher_is_capped_at_three_consecutive_periods():
    grid = ScheduleGrid()
    for period in (1, 2, 3):
        grid.place(0, period, make_task(klass=f"c-{period}", subject=f"s-{period}"))

    assert not check_max_consecutive(grid, 0, 4, make_task(klass="c-9"))


def test_physical_education_resets_the_consecutive_count():
    """البدنيّةُ والعلومُ المعمليّة تُعيد العدّاد — قرارٌ تربويٌّ مكتوب."""
    grid = ScheduleGrid()
    grid.place(0, 1, make_task(klass="c-a", code="MAT", subject="s-a"))
    grid.place(0, 2, make_task(klass="c-b", code="PE", subject="s-b"))
    grid.place(0, 3, make_task(klass="c-c", code="MAT", subject="s-c"))

    assert check_max_consecutive(grid, 0, 4, make_task(klass="c-d"))


def test_a_heavy_subject_gets_at_most_two_periods_a_day():
    """مادّةٌ نصابُها خمسٌ فأكثر: حصّتان في اليوم للشعبة الواحدة."""
    grid = ScheduleGrid()
    heavy = make_task(weekly=6)
    grid.place(0, 1, heavy)
    grid.place(0, 2, heavy)

    assert not check_high_weekly_daily_limit(grid, 0, heavy)
    assert check_high_weekly_daily_limit(grid, 1, heavy), "واليومُ التالي مفتوح"


def test_a_light_subject_is_not_bound_by_that_rule():
    grid = ScheduleGrid()
    light = make_task(weekly=2)
    grid.place(0, 1, light)
    grid.place(0, 2, light)

    assert check_high_weekly_daily_limit(grid, 0, light)


# ══════════════════════════════════════════════════════════════
#  الشبكةُ نفسها: الفهارسُ تصدق بعد الإضافة والحذف
# ══════════════════════════════════════════════════════════════


def test_removing_a_period_restores_the_grid_exactly():
    """التراجعُ يجب أن يُعيد الحالةَ كما كانت، وإلّا فسدت فهارسُ التعارض."""
    grid = ScheduleGrid()
    task = make_task()
    grid.place(0, 1, task)
    grid.remove(0, 1)

    assert grid.get_task_at(0, 1) is None
    assert grid.teacher_periods_on_day(TEACHER, 0) == 0
    assert grid.class_periods_on_day(CLASS, 0) == 0
    assert grid.subject_on_day(CLASS, "s-1", 0) == 0
    assert grid.all_entries() == []
    assert is_slot_valid(grid, 0, 1, make_task(teacher=OTHER_TEACHER, klass=OTHER_CLASS))


def test_removing_an_empty_slot_is_harmless():
    grid = ScheduleGrid()
    grid.place(0, 1, make_task())

    grid.remove(0, 2)

    assert len(grid.all_entries()) == 1


def test_the_week_is_sunday_to_thursday():
    """أسبوعُ قطر — وأيُّ يومٍ سادسٍ يعني جدولاً لا يوجد له تقويم."""
    assert DAYS == [0, 1, 2, 3, 4]


# ══════════════════════════════════════════════════════════════
#  المرحلةُ تُقرأ ولا تُشتقّ — عيبٌ كشفه أوّلُ مسبار
# ══════════════════════════════════════════════════════════════


@pytest.fixture
def two_stage_school(db, school):
    """شعبتان: إعداديّةٌ وثانويّة — والفرقُ بينهما يظهر يوم الخميس."""
    from core.models import ClassGroup, CustomUser
    from operations.models import Subject, SubjectClassAssignment

    subject = Subject.objects.create(school=school, name_ar="فيزياء", code="PHY")
    made = {}
    for key, grade, level, nid in (
        ("prep", "G8", "prep", "28800000301"),
        ("sec", "G11", "sec", "28800000302"),
    ):
        teacher = CustomUser.objects.create(national_id=nid, full_name=f"معلّم {key}")
        group = ClassGroup.objects.create(
            school=school,
            grade=grade,
            section="1",
            level_type=level,
            academic_year="2026-2027",
        )
        SubjectClassAssignment.objects.create(
            school=school,
            class_group=group,
            subject=subject,
            teacher=teacher,
            weekly_periods=1,
            academic_year="2026-2027",
        )
        made[key] = group
    return school, made


@pytest.mark.parametrize(("stage", "expected"), [("prep", "prep"), ("sec", "sec")])
def test_the_stage_comes_from_the_section_not_from_a_derivation(two_stage_school, stage, expected):
    """كان المحرّك يقارن `grade` النصّيّ («G11») بأعدادٍ صحيحة `(10, 11, 12)`،
    فلا تصدق المقارنةُ أبداً ويخرج `level_type` فارغاً لكلّ شعبة.

    ولا يظهر ذلك تعارضاً في الجدول: يظهر طاقةً أقلَّ يوم الخميس — الثانويُّ
    يخسر حصّتَه السابعة — فيبدو الجدولُ معقولاً وهو مخالفٌ لقرار المدرسة.
    """
    from operations.scheduler import build_tasks

    school, groups = two_stage_school
    tasks = build_tasks(school, "2026-2027")

    by_class = {t.class_id: t.level_type for t in tasks}
    assert by_class[str(groups[stage].id)] == expected


def test_the_secondary_keeps_its_seventh_thursday_period(two_stage_school):
    """أثرُ العيب مقيساً حيث يقع: خانةُ الخميس السابعة."""
    from operations.scheduler import build_tasks, get_available_slots

    school, groups = two_stage_school
    tasks = {t.class_id: t for t in build_tasks(school, "2026-2027")}
    grid = ScheduleGrid()

    sec_slots = get_available_slots(grid, tasks[str(groups["sec"].id)])
    prep_slots = get_available_slots(grid, tasks[str(groups["prep"].id)])

    assert (4, 7) in sec_slots, "الثانويّ يبلغ السابعة يوم الخميس"
    assert (4, 7) not in prep_slots, "والإعداديُّ يقف عند السادسة"


# ══════════════════════════════════════════════════════════════
#  سقفُ اليوم مصونٌ بلا حارسٍ ثانٍ
# ══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(("level", "cap"), [("prep", 6), ("sec", 7)])
def test_a_section_cannot_exceed_its_day_cap_without_a_second_guard(level, cap):
    """حُذفت `check_day_capacity` لأنّها لم تكن تُستدعى ولا تضيف ثابتاً مستقلّاً.

    وهذه الدعوى تُثبت السلوكَ المطلوبَ من دونها: الشعبةُ لا تشغل خانتين في
    الحصّة الواحدة، والحصصُ محدودةٌ بمدى اليوم — فعددُها لا يتجاوز السقف.
    والاختبارُ على السلوك لا على استدعاء دالّة.
    """
    grid = ScheduleGrid()

    # معلّمٌ لكلّ حصّة: القياسُ هنا لسقف الشعبة، فلا يُخلَط بحدّ التتابع.
    for period in range(1, 8):
        task = make_task(level_type=level, subject=f"s-{period}", teacher=f"t-{period}")
        if is_slot_valid(grid, 4, period, task):
            grid.place(4, period, task)

    assert grid.class_periods_on_day(CLASS, 4) == cap
    assert not any(
        is_slot_valid(grid, 4, p, make_task(level_type=level, subject="s-x", teacher="t-x"))
        for p in range(1, 8)
    )


# ══════════════════════════════════════════════════════════════
#  معاني الحقول: تُثبَّت كما هي لا كما يوحي اسمُها
# ══════════════════════════════════════════════════════════════


def test_requiring_a_lab_reserves_no_room_because_rooms_are_not_modelled():
    """`requires_lab` **ليس شرطاً صلباً ولا يمكن أن يكون**: لا نموذجَ قاعاتٍ
    في المنصّة، فلا سعةَ تُحجَز ولا مكانَ يُخصَّص.

    وأثرُه الوحيد ترجيحُ الترتيب في `sort_tasks` — تُجدوَل أوّلاً. فمن قرأ
    الاسمَ وظنّه حجزاً لمعملٍ بنى على وهم.
    """
    from operations.scheduler import sort_tasks

    plain = make_task(subject="s-plain")
    lab = make_task(subject="s-lab")
    lab.requires_lab = True

    assert sort_tasks([plain, lab])[0] is lab, "المعامل تُجدوَل أوّلاً"

    grid = ScheduleGrid()
    assert is_slot_valid(grid, 0, 1, lab), "ولا قيدَ يمنعها من أيّ خانة"


def test_a_double_period_is_preferred_not_required():
    """`prefers_double` تفضيلٌ لا اشتراط — ولا قيدَ صلبٌ يفرض التجاور.

    وكان اسمُه `requires_double` فيوحي بضرورةٍ لا وجودَ لها. وأثرُه الحقيقيّ
    عقوبةٌ مرنة: تُلغى عقوبةُ تكرار المادّة في اليوم، وتُمنَح مكافأةٌ للتجاور.
    """
    from operations.scheduler_constraints import evaluate_soft_constraints

    art = make_task(code="ART", subject="s-art")
    grid = ScheduleGrid()
    grid.place(0, 1, art)

    assert is_slot_valid(grid, 3, 5, art), "لا شيءَ يمنع التفرّق"

    adjacent = evaluate_soft_constraints(grid, 0, 2, art).total
    apart = evaluate_soft_constraints(grid, 3, 5, art).total
    assert adjacent < apart, "التجاورُ مُرجَّحٌ لا مفروض"


def test_a_plain_subject_is_penalised_for_repeating_in_one_day():
    """وغيرُ المزدوجة يُعاقَب تكرارُها في اليوم — وهو الفرقُ بين المعنيين."""
    from operations.scheduler_constraints import evaluate_soft_constraints

    plain = make_task(code="GEO", subject="s-geo", weekly=2)
    grid = ScheduleGrid()
    grid.place(0, 1, plain)

    assert evaluate_soft_constraints(grid, 0, 2, plain).total > 0
    assert evaluate_soft_constraints(grid, 1, 1, plain).total == 0


# ══════════════════════════════════════════════════════════════
#  المركَّب: إعفاءٌ جزئيّ + سقفٌ يوميّ + مادّةٌ متعدّدة الحصص
# ══════════════════════════════════════════════════════════════


def test_a_partly_exempt_teacher_still_respects_every_other_rule(db, school):
    """ثلاثةُ قيودٍ معاً: يومٌ مفرَّغ، وسقفُ الخميس، وحدُّ التتابع.

    القيودُ المركّبة هي التي تُخطئ فيها المحرّكات: يُحترم قيدٌ فيُنسى آخر.
    """
    from operations.scheduler import get_available_slots

    grid = ScheduleGrid()
    task = make_task(level_type="prep", weekly=6)
    blocked = {(TEACHER, 1, p) for p in range(1, 8)}
    for period in (1, 2, 3):
        grid.place(0, period, make_task(klass=f"c-{period}", subject=f"s-{period}"))

    available = get_available_slots(grid, task, blocked)

    assert all(d != 1 for d, _ in available), "يومُ التفريغ مغلق"
    assert (0, 4) not in available, "والرابعةُ متتاليةٌ رابعة"
    assert (4, 7) not in available, "والخميسُ إعداديٌّ يقف عند السادسة"
    assert (2, 1) in available, "وما سوى ذلك مفتوح"


def test_a_heavy_subject_under_a_narrow_week_still_obeys_its_daily_cap(db, school):
    """مادّةٌ نصابُها ستٌّ لشعبةٍ إعداديّة: حصّتان في اليوم لا أكثر، ولو ضاق
    الأسبوعُ بتفريغ يوم."""
    from operations.scheduler import get_available_slots

    grid = ScheduleGrid()
    heavy = make_task(weekly=6, level_type="prep")
    grid.place(2, 1, heavy)
    grid.place(2, 3, heavy)

    available = get_available_slots(grid, heavy, {(TEACHER, 0, p) for p in range(1, 8)})

    assert all(d != 2 for d, _ in available), "بلغت اليومَ حدَّه"
    assert all(d != 0 for d, _ in available), "ويومُ التفريغ مغلق"
    assert available, "وبقيت أيّامٌ"


# ══════════════════════════════════════════════════════════════
#  التعذّرُ الكاذب — حلٌّ موجودٌ يحتاج تغييرَ قرارٍ سابق
# ══════════════════════════════════════════════════════════════


@pytest.fixture
def solvable_only_by_revising(db, school):
    """حالةٌ صغيرةٌ لها حلٌّ، لكنّه يوجب تغييرَ أوّل اختيارٍ اتُّخذ.

    شعبةٌ واحدة. مادّةٌ «جغرافيا» بحصّتين لمعلّمٍ حرّ، ومادّةٌ «تاريخ» بحصّةٍ
    واحدةٍ لمعلّمٍ مفرَّغٍ في الأسبوع كلِّه إلّا خانةً واحدة: الأحد/الأولى.

    والجغرافيا تُجدوَل أوّلاً (نصابُها أعلى) فتأخذ الأحد/الأولى — وهي الخانةُ
    الوحيدةُ الممكنةُ للتاريخ. والحلُّ قائم: تُزاح الجغرافيا حصّةً واحدة.
    """
    from core.models import ClassGroup, CustomUser
    from operations.models import Subject, SubjectClassAssignment, TeacherExemption

    free = CustomUser.objects.create(national_id="28800000401", full_name="معلّم الجغرافيا")
    bound = CustomUser.objects.create(national_id="28800000402", full_name="معلّم التاريخ")
    group = ClassGroup.objects.create(
        school=school, grade="G7", section="1", level_type="prep", academic_year="2026-2027"
    )
    for code, name, teacher, weekly in (
        ("GEO", "جغرافيا", free, 2),
        ("HIS", "تاريخ", bound, 1),
    ):
        subject = Subject.objects.create(school=school, name_ar=name, code=code)
        SubjectClassAssignment.objects.create(
            school=school,
            class_group=group,
            subject=subject,
            teacher=teacher,
            weekly_periods=weekly,
            academic_year="2026-2027",
        )

    # التاريخ: مفرَّغٌ كلَّ الأسبوع إلّا الأحد/الأولى.
    for day in DAYS:
        for period in range(1, 8):
            if (day, period) == (0, 1):
                continue
            TeacherExemption.objects.create(
                school=school,
                teacher=bound,
                exemption_type="period",
                day_of_week=day,
                period_number=period,
                academic_year="2026-2027",
            )
    return school


def test_a_solvable_week_is_not_declared_impossible(solvable_only_by_revising):
    """التراجعُ كان يُعيد المهمّةَ إلى الخانة نفسها، فيستهلك المحاولات بلا تقدّم
    ثمّ يُعلن التعذّر — و«تعذّرٌ» كاذبٌ عيبُ صحّةٍ لا أداء.

    ثلاثُ حصصٍ في أسبوعٍ فيه خمسةٌ وثلاثون خانة: لا عذرَ للفشل.
    """
    from operations.scheduler import generate_schedule

    result = generate_schedule(solvable_only_by_revising, "2026-2027")

    assert result["errors"] == [], "حلٌّ موجودٌ فلا يُعلَن تعذّر"
    assert len(result["grid"].all_entries()) == 3
    assert result["success"] is True


def test_backtracking_makes_progress_instead_of_repeating_itself(solvable_only_by_revising):
    """الدليلُ على أنّ العلّة عولجت في أصلها لا في عرضها: عددُ التراجعات صغير.

    كانت الدورةُ العقيمة تستهلك الخمسمئةَ كلَّها قبل أن تستسلم.
    """
    from operations.scheduler import generate_schedule

    result = generate_schedule(solvable_only_by_revising, "2026-2027")

    assert result["backtrack_count"] < 500, "لم تُستهلك الميزانيّة في دورةٍ عقيمة"


def test_the_generated_week_holds_every_invariant_at_once(db, school):
    """الفحصُ الجامع: مدرسةٌ بعدّة شعبٍ ومعلّمين، ثمّ تُقرأ نتيجتُها كلُّها.

    وهذه هي البوّابة: لا تعارضَ صلب، ولا مهمّةَ تختفي، ولا سقفَ يُتجاوز.
    """
    from collections import Counter

    from core.models import ClassGroup, CustomUser
    from operations.models import Subject, SubjectClassAssignment
    from operations.scheduler import build_tasks, generate_schedule
    from operations.scheduler_constraints import get_max_periods_for_day

    subjects = [
        Subject.objects.create(school=school, name_ar=name, code=code)
        for name, code in (("رياضيات", "MAT"), ("عربية", "ARA"), ("جغرافيا", "GEO"))
    ]
    # شعبتان لا ثلاث: سقفُ المحرّك ٣٥ حصّةً للمدرسة كلِّها (انظر الدعوى
    # الأخيرة في هذا الملفّ)، وثلاثُ شعبٍ تتجاوزه فيفشل لسببٍ آخر.
    for index, (grade, level) in enumerate((("G7", "prep"), ("G11", "sec"))):
        group = ClassGroup.objects.create(
            school=school,
            grade=grade,
            section="1",
            level_type=level,
            academic_year="2026-2027",
        )
        for offset, subject in enumerate(subjects):
            teacher = CustomUser.objects.create(
                national_id=f"2880000{index}{offset}50", full_name=f"معلّم {index}{offset}"
            )
            SubjectClassAssignment.objects.create(
                school=school,
                class_group=group,
                subject=subject,
                teacher=teacher,
                weekly_periods=4,
                academic_year="2026-2027",
            )

    result = generate_schedule(school, "2026-2027")
    entries = result["grid"].all_entries()

    assert result["errors"] == []
    assert len(entries) == len(build_tasks(school, "2026-2027")) == 24

    seen_teacher, seen_class, per_class_day = set(), set(), Counter()
    for entry in entries:
        task, day, period = entry["task"], entry["day"], entry["period"]
        assert (task.teacher_id, day, period) not in seen_teacher, "معلّمٌ في مكانين"
        assert (task.class_id, day, period) not in seen_class, "شعبةٌ في مادّتين"
        assert period <= get_max_periods_for_day(day, task.level_type), "تجاوزَ سقفَ اليوم"
        seen_teacher.add((task.teacher_id, day, period))
        seen_class.add((task.class_id, day, period))
        per_class_day[(task.class_id, day)] += 1

    for (class_id, day), count in per_class_day.items():
        task = next(e["task"] for e in entries if e["task"].class_id == class_id)
        assert count <= get_max_periods_for_day(day, task.level_type), "حصصُ اليوم فوق السقف"


# ══════════════════════════════════════════════════════════════
#  عيبٌ معلومٌ: الشبكةُ خانةٌ واحدةٌ للمدرسة كلِّها
# ══════════════════════════════════════════════════════════════


@pytest.mark.xfail(
    strict=True,
    reason=(
        "`ScheduleGrid._grid[day][period]` يحمل مهمّةً واحدةً للمدرسة كلِّها لا "
        "لكلّ شعبة، و`get_available_slots` يرفض أيَّ خانةٍ مشغولةٍ مهما كانت "
        "الشعبةُ والمعلّم. فسقفُ المحرّك ٣٥ حصّةً في الأسبوع — ومدرسةُ الشحانية "
        "تحتاج ٨٧٠. وإصلاحُه إعادةُ تصميمٍ للبنية لا تعديلُ سطر."
    ),
)
def test_two_sections_can_be_taught_in_the_same_period():
    """الصوابُ المطلوب: شعبتان مختلفتان بمعلّمين مختلفين تُدرَّسان معاً.

    و`is_slot_valid` يُجيزه فعلاً — القيودُ الصلبةُ سليمة. لكنّ
    `get_available_slots` لا يعرض الخانةَ أصلاً، فلا يبلغها القرار.

    وهذه الدعوى `xfail(strict=True)`: تُبقي العيبَ ظاهراً، وتفشل يوم يُصلَح
    فتُنبّه إلى رفع العلامة — فلا يصير الدينُ عقداً يحرسه اختبار.
    """
    grid = ScheduleGrid()
    grid.place(0, 1, make_task())

    from operations.scheduler import get_available_slots

    parallel = make_task(teacher=OTHER_TEACHER, klass=OTHER_CLASS)

    assert is_slot_valid(grid, 0, 1, parallel), "القيودُ الصلبةُ تُجيزه"
    assert (0, 1) in get_available_slots(grid, parallel), "والمحرّكُ لا يعرضه"


def test_the_engine_capacity_is_one_lesson_per_period_school_wide():
    """قياسُ السقف عدداً — ليُقارَن بحاجة المدرسة الحقيقيّة.

    خمسةُ أيّامٍ × سبعُ حصص = ٣٥ للمدرسة كلِّها. وجدولُ الشحانية المستورد
    ٨٧٠ حصّة. أي أنّ المحرّك يبلغ أربعةً بالمئة ممّا يلزم — وهذا يفسّر لماذا
    يُستورَد الجدولُ من برنامجٍ خارجيّ ولا يُولَّد.
    """
    from operations.scheduler import get_available_slots

    grid = ScheduleGrid()
    task = make_task(level_type="sec")

    assert len(get_available_slots(grid, task)) == 35

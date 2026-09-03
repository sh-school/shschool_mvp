"""[SCHEDULE] الحصّةُ المزدوجة: حصّتان متلاصقتان لا تقطعهما فسحةٌ ولا صلاة.

الفنّيّةُ في المرحلة الإعداديّة حصّتان متلاصقتان — والعملُ الفنّيُّ لا يُبدأ
ويُطوى في خمسٍ وأربعين دقيقة. وهذا موصوفٌ في نموذجنا منذ زمن:

    Subject.requires_double_period → «يتطلب حصتين متتاليتين بدون استراحة»

ولم يكن يُنفَّذ: المحرّكُ يُرجّح التجاورَ بوزنٍ مرنٍ ولا يشترطه، فتقع الحصّتان
متباعدتين ولا شيءَ يعترض.

وينقص الوصفَ شرطٌ لم يُذكر: **أيُّ** تجاورٍ يصلح. فبين الثالثة والرابعة فسحةٌ
عشرون دقيقة، وبين الخامسة والسادسة صلاةٌ خمسَ عشرة — فالتلاصقُ عبرهما تلاصقٌ
في الورق لا في اليوم:

    ح1–ح2  ✓      ح3–ح4  ✗ فسحة
    ح2–ح3  ✓      ح5–ح6  ✗ صلاة
    ح4–ح5  ✓
    ح6–ح7  ✓

والكتلُ تُقرأ من `TimeSlotConfig` — من جرس المدرسة — ولا تُحفر في الكود.
"""

import pytest

from operations.models import Subject, SubjectClassAssignment, TimeSlotConfig
from operations.scheduler import build_tasks, generate_schedule
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"

#: جرسُ الشحانية الحقيقيّ — فسحةٌ بعد الثالثة وصلاةٌ بعد الخامسة.
BELL = [
    (1, "07:10", "07:55"),
    (2, "08:00", "08:45"),
    (3, "08:50", "09:35"),
    (4, "09:55", "10:40"),
    (5, "10:45", "11:30"),
    (6, "11:45", "12:30"),
    (7, "12:35", "13:20"),
]


@pytest.fixture
def bell(school):
    from datetime import time

    def _t(text):
        hour, minute = text.split(":")
        return time(int(hour), int(minute))

    for period, start, end in BELL:
        for day_type in ("regular", "thursday"):
            TimeSlotConfig.objects.create(
                school=school,
                period_number=period,
                start_time=_t(start),
                end_time=_t(end),
                day_type=day_type,
            )
    return school


@pytest.fixture
def art_class(school, bell):
    role = RoleFactory(school=school, name="teacher")
    teacher = UserFactory(full_name="معلّمُ الفنون")
    MembershipFactory(user=teacher, school=school, role=role)
    group = ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year=YEAR)
    art = Subject.objects.create(
        school=school, name_ar="الفنون البصرية", code="", requires_double_period=True
    )
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=teacher,
        class_group=group,
        subject=art,
        weekly_periods=2,
        is_active=True,
    )
    return group, teacher, art


# ── الكتلُ تُقرأ من الجرس ────────────────────────────────────────────


def test_the_blocks_come_from_the_school_bell(bell):
    """الفاصلُ الطويلُ يقطع، والقصيرُ لا — والحدُّ يُقرأ من الأوقات لا يُحفر."""
    from operations.scheduler_constraints import joinable_pairs

    assert joinable_pairs(bell) == {(1, 2), (2, 3), (4, 5), (6, 7)}


def test_without_a_bell_every_neighbour_joins(school):
    """ومدرسةٌ لم تُدخل أوقاتَها بعد: لا كتلَ تُعرَف، فلا يُمنع تجاور."""
    from operations.scheduler_constraints import joinable_pairs

    assert (3, 4) in joinable_pairs(school)


def test_the_bell_is_read_once_per_generation(bell, django_assert_num_queries):
    """داخلَ التوليد يُسأل الجرسُ مرّةً — وكان يُسأل عند كلّ مرشَّح.

    آلافُ الاستعلامات في التوليد الواحد، نحوَ ثلث زمنه — والرقمُ بعينه في
    تعليق `_PAIRS_CACHE`. والجرسُ لا يتغيّر في أثناء التوليد.
    """
    from operations.scheduler_constraints import joinable_pairs, joinable_pairs_cached

    with joinable_pairs_cached(), django_assert_num_queries(1):
        first = joinable_pairs(bell)
        second = joinable_pairs(bell)

    assert first == second == {(1, 2), (2, 3), (4, 5), (6, 7)}


def test_outside_a_generation_every_call_reads_the_bell(bell, django_assert_num_queries):
    """والذاكرةُ سياقٌ لا حالةٌ عامّة: خارجَه تُقرأ القاعدةُ كما كانت."""
    from operations.scheduler_constraints import joinable_pairs

    with django_assert_num_queries(2):
        joinable_pairs(bell)
        joinable_pairs(bell)


def test_the_cache_does_not_outlive_its_block(bell, django_assert_num_queries):
    """وما حُفظ داخلَ التوليد يُنسى بانتهائه — لا يُورَّث لتوليدٍ لاحق."""
    from operations.scheduler_constraints import joinable_pairs, joinable_pairs_cached

    with joinable_pairs_cached():
        joinable_pairs(bell)
    with django_assert_num_queries(1):
        joinable_pairs(bell)


# ── المزدوجةُ تُبنى مهمّةً واحدة ─────────────────────────────────────


def test_a_double_subject_becomes_one_two_period_task(art_class, school):
    """حصّتان في مهمّةٍ واحدةٍ تشغل خانتين — لا مهمّتان تلتقيان بالصدفة."""
    tasks = build_tasks(school, YEAR)

    assert len(tasks) == 1, "مهمّةٌ واحدةٌ لا اثنتان"
    assert tasks[0].span == 2


def test_the_pair_lands_adjacent_and_inside_one_block(art_class, school):
    from operations.models import ScheduleSlot

    result = generate_schedule(school, YEAR)

    assert result["errors"] == [], result["errors"]
    rows = sorted(
        ScheduleSlot.objects.filter(school=school, academic_year=YEAR, is_active=True),
        key=lambda r: r.period_number,
    )
    assert len(rows) == 2
    assert rows[0].day_of_week == rows[1].day_of_week, "في يومٍ واحد"
    assert rows[1].period_number == rows[0].period_number + 1, "ومتلاصقتان"
    assert (rows[0].period_number, rows[1].period_number) in {(1, 2), (2, 3), (4, 5), (6, 7)}


def test_the_pair_never_straddles_the_break(art_class, school):
    """الاختبارُ الحاسم: لا تقع الحصّتان على طرفَي الفسحة أو الصلاة."""
    from operations.models import ScheduleSlot

    generate_schedule(school, YEAR)

    periods = sorted(
        r.period_number
        for r in ScheduleSlot.objects.filter(school=school, academic_year=YEAR, is_active=True)
    )
    assert tuple(periods) not in {(3, 4), (5, 6)}, "الفسحةُ والصلاةُ تقطعان"


def test_a_plain_subject_is_untouched(school, bell):
    """وغيرُ المزدوجة تبقى حصصاً مفردةً كما كانت."""
    role = RoleFactory(school=school, name="teacher")
    teacher = UserFactory(full_name="معلّمُ الرياضيات")
    MembershipFactory(user=teacher, school=school, role=role)
    group = ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year=YEAR)
    maths = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=teacher,
        class_group=group,
        subject=maths,
        weekly_periods=4,
        is_active=True,
    )

    tasks = build_tasks(school, YEAR)

    assert len(tasks) == 4
    assert all(t.span == 1 for t in tasks)


# ── الازدواجُ قرارُ الشاشة لا رمزُ المادّة ──────────────────────────────


def test_technology_is_no_longer_doubled_by_its_code(school, bell):
    """قرارُ الإدارة (2026-09-02): التكنولوجيا حصّتان متباعدتان لا مزدوجة.

    وكان الرمزُ «TECH» محفوراً في الشيفرة إلى جانب حقل القاعدة، فيُزدوَج وإن
    كان الحقلُ مطفأً — أي أنّ زرّ شاشة الإعدادات كان كذبةً في حقّه.
    """
    role = RoleFactory(school=school, name="teacher")
    teacher = UserFactory(full_name="معلّمُ التكنولوجيا")
    MembershipFactory(user=teacher, school=school, role=role)
    group = ClassGroupFactory(school=school, grade="G8", level_type="prep", academic_year=YEAR)
    tech = Subject.objects.create(
        school=school, name_ar="التكنولوجيا", code="TECH", requires_double_period=False
    )
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=teacher,
        class_group=group,
        subject=tech,
        weekly_periods=2,
        is_active=True,
    )

    tasks = build_tasks(school, YEAR)

    assert len(tasks) == 2, "حصّتان مفردتان لا خانةٌ مزدوجة"
    assert all(task.span == 1 for task in tasks)
    assert all(not task.prefers_double for task in tasks)


def test_the_two_technology_periods_land_on_different_days(school, bell):
    """وحصّتان في أسبوعٍ خماسيّ تُفرّقهما القسمةُ على الأيّام — فلا تتجاوران."""
    from operations.models import ScheduleSlot

    role = RoleFactory(school=school, name="teacher")
    teacher = UserFactory(full_name="معلّمُ التكنولوجيا")
    MembershipFactory(user=teacher, school=school, role=role)
    group = ClassGroupFactory(school=school, grade="G9", level_type="prep", academic_year=YEAR)
    tech = Subject.objects.create(
        school=school, name_ar="التكنولوجيا", code="TECH", requires_double_period=False
    )
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=teacher,
        class_group=group,
        subject=tech,
        weekly_periods=2,
        is_active=True,
    )

    generate_schedule(school, YEAR)

    placed = sorted(
        (r.day_of_week, r.period_number)
        for r in ScheduleSlot.objects.filter(school=school, academic_year=YEAR, is_active=True)
    )
    assert len(placed) == 2
    assert placed[0][0] != placed[1][0], "يومان لا يومٌ واحد"


def test_the_screen_switch_still_doubles_what_it_marks(school, bell):
    """والزرُّ يعمل في الاتّجاه الآخر: مادّةٌ وُسِمت تُزدوَج ولو لم يكن لها رمز."""
    role = RoleFactory(school=school, name="teacher")
    teacher = UserFactory(full_name="معلّمُ ورشة")
    MembershipFactory(user=teacher, school=school, role=role)
    group = ClassGroupFactory(school=school, grade="G8", level_type="prep", academic_year=YEAR)
    workshop = Subject.objects.create(
        school=school, name_ar="ورشة", code="", requires_double_period=True
    )
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=teacher,
        class_group=group,
        subject=workshop,
        weekly_periods=2,
        is_active=True,
    )

    tasks = build_tasks(school, YEAR)

    assert len(tasks) == 1 and tasks[0].span == 2


def test_a_class_may_override_the_subject_decision(school, bell):
    """قرارُ الشعبة يسبق قرارَ المادّة — فالمادّةُ الواحدةُ حالان بحسب الصفّ.

    التكنولوجيا من السابع إلى العاشر حصّتان متباعدتان، وهي في الحادي عشر/1
    نصفُ زوجٍ متوازٍ مع الفنّيّة المزدوجة — والمتوازيان في خانةٍ واحدة فشكلُهما
    واحد. وحقلُ المادّة وحده لا يسع الحالين: إشعالُه يُلصق حصص السابع،
    وإطفاؤه يفكّ زوجَ الحادي عشر.
    """
    role = RoleFactory(school=school, name="teacher")
    teacher = UserFactory(full_name="معلّمُ التكنولوجيا")
    MembershipFactory(user=teacher, school=school, role=role)
    tech = Subject.objects.create(
        school=school, name_ar="التكنولوجيا", code="TECH", requires_double_period=False
    )

    prep = ClassGroupFactory(school=school, grade="G8", level_type="prep", academic_year=YEAR)
    senior = ClassGroupFactory(school=school, grade="G11", level_type="sec", academic_year=YEAR)
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=teacher,
        class_group=prep,
        subject=tech,
        weekly_periods=2,
        is_active=True,
    )
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=teacher,
        class_group=senior,
        subject=tech,
        weekly_periods=2,
        double_period=True,
        is_active=True,
    )

    spans = {}
    for task in build_tasks(school, YEAR):
        spans.setdefault(task.class_id, []).append(task.span)

    assert sorted(spans[str(prep.id)]) == [1, 1], "الثامنُ حصّتان مفردتان"
    assert spans[str(senior.id)] == [2], "والحادي عشر خانةٌ مزدوجة"

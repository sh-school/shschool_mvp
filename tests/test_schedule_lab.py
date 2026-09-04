"""مختبرُ جودة الجدول: المؤشراتُ تُحسب من الحصص وتُقارَن بأساسٍ محفوظ.

الرقمُ الواحد «96» لا يقول لماذا — فهنا كلُّ مؤشرٍ يُختبر على جدولٍ صغير
معلومِ الشكل، ثمّ على توليدٍ كامل، ثمّ عبر الأمر والشاشة.
"""

import datetime as dt

import pytest
from django.core.management import call_command
from django.urls import reverse

from operations.models import (
    ScheduleBaseline,
    ScheduleGeneration,
    ScheduleSlot,
    Subject,
    SubjectClassAssignment,
    TeacherExemption,
    TeacherPreference,
)
from operations.schedule_lab import (
    CATALOG,
    Context,
    ScheduleLab,
    Slot,
    compare,
    ideal_pattern,
    store_metrics,
)
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db
YEAR = "2026-2027"


def slot(teacher="t1", klass="c1", subject="s1", day=0, period=1, **kw):
    return Slot(
        teacher_id=teacher,
        teacher_name=teacher,
        class_id=klass,
        class_name=klass,
        subject_id=subject,
        subject_code=kw.get("code", ""),
        pedagogy=kw.get("pedagogy", "regular"),
        requires_double=kw.get("double", False),
        day=day,
        period=period,
        band_id=kw.get("band", ""),
        elective_group=kw.get("elective", ""),
    )


# ── المؤشراتُ على جدولٍ صغير ──────────────────────────────────────


def test_ideal_patterns_follow_the_agreed_shapes():
    assert ideal_pattern(5, False) == [1, 1, 1, 1, 1]
    assert ideal_pattern(6, False) == [2, 1, 1, 1, 1]
    assert ideal_pattern(7, False) == [2, 2, 1, 1, 1]
    assert ideal_pattern(4, False) == [1, 1, 1, 1]
    assert ideal_pattern(2, True) == [2], "المزدوجةُ المطلوبة حصّتان في يوم"


def test_weighted_gap_squares_the_hole():
    """1,2,3,4 صفر؛ 1,2,4,5 فراغُ حصّة = 1/4؛ 1,4,7 فراغان بحصّتين = 8/3."""
    lab = ScheduleLab([slot(period=p) for p in (1, 2, 4, 5)], Context())
    avg, mx = lab.gaps()
    assert avg["value"] == 0.25 and mx["value"] == 0.25

    lab = ScheduleLab([slot(period=p) for p in (1, 4, 7)], Context())
    avg, _ = lab.gaps()
    assert avg["value"] == round(8 / 3, 2)


def test_compactness_is_span_over_periods():
    lab = ScheduleLab([slot(period=p) for p in (1, 3, 5, 7)], Context())
    assert lab.compactness()["value"] == 1.75
    lab = ScheduleLab([slot(period=p) for p in (1, 2, 3, 4)], Context())
    assert lab.compactness()["value"] == 1.0


def test_weekly_imbalance_is_zero_when_days_are_even():
    even = [slot(day=d, period=p) for d in range(5) for p in (1, 3)]
    assert ScheduleLab(even, Context()).weekly_imbalance()["value"] == 0.0
    skewed = [slot(day=0, period=p) for p in range(1, 7)] + [
        slot(day=d, period=1) for d in (1, 2, 3, 4)
    ]
    assert ScheduleLab(skewed, Context()).weekly_imbalance()["value"] > 1.5


def test_a_released_day_does_not_count_as_uncovered_or_unbalanced():
    ctx = Context()
    ctx.full_days["t1"].add(4)
    slots = [slot(day=d, period=p) for d in range(4) for p in (1, 2)]
    lab = ScheduleLab(slots, ctx)
    assert lab.uncovered_days()["value"] == 0
    assert lab.weekly_imbalance()["value"] == 0.0


def test_hard_conflicts_see_double_booking_and_exemptions():
    ctx = Context()
    ctx.blocked.add(("t1", 0, 3))
    slots = [
        slot(period=1, klass="c1"),
        slot(period=1, klass="c2"),  # المعلّمُ في شعبتين
        slot(period=3),  # حصّةٌ في خانةٍ مفرَّغة
        slot(teacher="t2", klass="c1", subject="s2", period=1),  # الشعبةُ بمادّتين بلا مجموعة
    ]
    detail = ScheduleLab(slots, ctx).hard_conflicts()["detail"]
    assert detail["teacher_double_booked"] == 1
    assert detail["class_double_booked"] == 1
    assert detail["exemption_breaches"] == 1


def test_a_parallel_elective_pair_is_not_a_class_conflict():
    slots = [
        slot(teacher="t1", subject="s1", period=1, elective="متوازي-1"),
        slot(teacher="t2", subject="s2", period=1, elective="متوازي-1"),
    ]
    assert ScheduleLab(slots, Context()).hard_conflicts()["value"] == 0


def test_clock_overlap_and_cross_floor_touch_are_read_from_the_bells():
    ctx = Context()
    t = dt.time
    ctx.bells.update(
        {
            ("g", "regular", 2): (t(8, 0), t(8, 50)),
            ("g", "regular", 5): (t(10, 50), t(11, 35)),
            ("u", "regular", 3): (t(8, 45), t(9, 35)),
            ("u", "regular", 6): (t(11, 35), t(12, 25)),
        }
    )
    overlap = [slot(period=2, band="g", klass="c1"), slot(period=3, band="u", klass="c2")]
    assert ScheduleLab(overlap, ctx).hard_conflicts()["detail"]["clock_overlaps"] == 1
    touch = [slot(period=5, band="g", klass="c1"), slot(period=6, band="u", klass="c2")]
    assert ScheduleLab(touch, ctx).hard_conflicts()["detail"]["cross_floor_touches"] == 1
    assert ScheduleLab(touch, ctx).transitions()[1]["value"] == 1


def test_subject_pattern_and_same_period_repetition():
    perfect = [slot(day=d, period=d + 1) for d in range(5)]
    match, same = ScheduleLab(perfect, Context()).subject_patterns()
    assert match["value"] == 100.0 and same["value"] == 1.0

    stacked = [slot(day=d, period=5) for d in range(5)]
    _, same = ScheduleLab(stacked, Context()).subject_patterns()
    assert same["value"] == 5.0 and same["detail"]["pairs_at_3_or_more"] == 1

    lumped = [slot(day=0, period=p) for p in range(1, 6)]
    match, _ = ScheduleLab(lumped, Context()).subject_patterns()
    assert match["value"] == 20.0, "خمسٌ في يومٍ واحد: حصّةٌ واحدةٌ في موضعها"


def test_pedagogy_timing_and_maths_late():
    slots = [
        slot(subject="m", code="MAT", pedagogy="heavy", day=0, period=2),
        slot(subject="m", code="MAT", pedagogy="heavy", day=1, period=7),
        slot(subject="pe", pedagogy="activity", day=2, period=6),
        slot(subject="pe", pedagogy="activity", day=3, period=1),
    ]
    lab = ScheduleLab(slots, Context())
    heavy, activity = lab.pedagogy_timing()
    assert heavy["value"] == 50.0 and activity["value"] == 50.0
    assert lab.class_pressure()[1]["value"] == 50.0


def test_edge_fairness_and_stress_name_the_worst():
    slots = [slot(teacher="a", klass="c1", day=d, period=1) for d in range(5)] + [
        slot(teacher="b", klass="c2", day=d, period=3) for d in range(5)
    ]
    lab = ScheduleLab(slots, Context())
    assert lab.edge_fairness()["value"] > 0.9, "أ كلُّ حصصه أولى، وب لا شيء"
    assert list(lab.stress()["detail"])[0] == "a"


def test_preference_satisfaction_counts_each_rule():
    ctx = Context()
    ctx.preferences["t1"] = {"max_daily": 2, "max_consecutive": 1, "max_gap": 0, "free_day": 4}
    slots = [slot(day=0, period=1), slot(day=0, period=2), slot(day=4, period=1)]
    result = ScheduleLab(slots, ctx).preference_satisfaction()
    # السقفُ اليومي ✓، التتالي ✗ (1,2)، الفراغ ✓، يوم التفريغ ✗ (الخميس مشغول)
    assert result["value"] == 50.0
    assert "التتالي" in result["detail"]["t1"]


def test_compare_marks_direction_by_catalog():
    current = {"teacher.gap_weighted_avg": {"value": 1.0}, "subject.pattern_match": {"value": 90}}
    baseline = {"teacher.gap_weighted_avg": {"value": 2.0}, "subject.pattern_match": {"value": 95}}
    rows = {r["key"]: r for r in compare(current, baseline)}
    assert rows["teacher.gap_weighted_avg"]["verdict"] == "better"
    assert rows["subject.pattern_match"]["verdict"] == "worse"
    assert len(rows) == len(CATALOG)


# ── على توليدٍ كامل وقاعدةٍ حقيقيّة ────────────────────────────────


def _teacher(school, name):
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


@pytest.fixture
def small_school(school):
    group = ClassGroupFactory(school=school, grade="G8", level_type="prep", academic_year=YEAR)
    maths = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    arabic = Subject.objects.create(school=school, name_ar="اللغة العربية", code="ARA")
    for subject, name in ((maths, "رياضيّ"), (arabic, "عربيّ")):
        SubjectClassAssignment.objects.create(
            school=school,
            academic_year=YEAR,
            teacher=_teacher(school, name),
            class_group=group,
            subject=subject,
            weekly_periods=5,
            is_active=True,
        )
    return school


def test_metrics_are_stored_on_generation_and_recomputed_on_command(small_school):
    from operations.scheduler import generate_schedule

    result = generate_schedule(small_school, YEAR)
    generation = result["generation"]
    metrics = store_metrics(generation)

    generation.refresh_from_db()
    assert generation.metrics["validity.completeness"]["value"] == 100.0
    assert generation.metrics["validity.hard_conflicts"]["value"] == 0
    assert metrics["_meta"]["slots"] == 10

    call_command("schedule_lab", "--live", "--save-baseline", "أساس الاختبار")
    baseline = ScheduleBaseline.objects.get(label="أساس الاختبار")
    assert baseline.metrics["validity.completeness"]["value"] == 100.0


def test_the_pedagogy_seed_reads_the_code(school):
    Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    Subject.objects.create(school=school, name_ar="التربية البدنية", code="PE")
    hand = Subject.objects.create(school=school, name_ar="التاريخ", code="HIS", pedagogy="heavy")

    call_command("seed_subject_pedagogy")

    assert Subject.objects.get(code="MAT").pedagogy == "heavy"
    assert Subject.objects.get(code="PE").pedagogy == "activity"
    hand.refresh_from_db()
    assert hand.pedagogy == "heavy", "ما ضُبط يدويّاً لا يُمَسّ"


def test_the_log_page_shows_metrics_against_the_baseline(client, small_school):
    from operations.scheduler import generate_schedule

    generation = generate_schedule(small_school, YEAR)["generation"]
    store_metrics(generation)
    ScheduleBaseline.objects.create(
        school=small_school,
        academic_year=YEAR,
        label="أساس",
        metrics={"teacher.gap_weighted_avg": {"value": 3.0}},
    )
    principal = UserFactory(full_name="المدير")
    MembershipFactory(
        user=principal, school=small_school, role=RoleFactory(school=small_school, name="principal")
    )
    client.force_login(principal)

    body = client.get(
        reverse("smart_schedule") + f"?year={YEAR}", HTTP_HOST="localhost"
    ).content.decode()

    assert "المؤشرات (" in body and "مقابل «أساس»" in body
    assert "الفراغ الموزون (متوسّط)" in body


def test_exemptions_and_preferences_reach_the_context(school):
    teacher = _teacher(school, "معلّم")
    TeacherExemption.objects.create(
        school=school,
        teacher=teacher,
        academic_year=YEAR,
        exemption_type="full_day",
        day_of_week=2,
        reason="دورة",
        source="school",
    )
    TeacherPreference.objects.create(
        teacher=teacher, school=school, academic_year=YEAR, max_daily_periods=4, max_gap=1
    )
    ctx = ScheduleLab.for_live(school, YEAR).ctx
    assert 2 in ctx.full_days[str(teacher.id)]
    assert (str(teacher.id), 2, 7) in ctx.blocked
    assert ctx.preferences[str(teacher.id)]["max_gap"] == 1
    assert ScheduleSlot.objects.count() == 0 and ScheduleGeneration.objects.count() == 0

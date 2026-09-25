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
    metric_score,
    overall_score,
    store_metrics,
)
from operations.schedule_lab_exceptions import exception_load
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


def test_a_single_period_gap_is_rest_and_only_the_excess_counts():
    """سياسةُ لا تلاصق: 1,3,5 صفر؛ 1,2,4,5 صفر (فراغُ حصّةٍ استراحة)؛ 1,4,7 فراغان بحصّتين = 2/3."""
    assert ScheduleLab([slot(period=p) for p in (1, 3, 5)], Context()).gaps()[0]["value"] == 0.0
    lab = ScheduleLab([slot(period=p) for p in (1, 2, 4, 5)], Context())
    avg, mx = lab.gaps()
    assert avg["value"] == 0.0 and mx["value"] == 0.0

    lab = ScheduleLab([slot(period=p) for p in (1, 4, 7)], Context())
    avg, _ = lab.gaps()
    assert avg["value"] == round(2 / 3, 2)


def test_compactness_is_measured_against_the_alternating_ideal():
    lab = ScheduleLab([slot(period=p) for p in (1, 3, 5, 7)], Context())
    assert lab.compactness()["value"] == 1.0, "التناوبُ التامّ مثاليّ"
    lab = ScheduleLab([slot(period=p) for p in (1, 2, 3, 4)], Context())
    assert lab.compactness()["value"] == 1.0, "التلاصقُ لا يُكافأ — يُعَدّ مخالفةً في مؤشره"
    lab = ScheduleLab([slot(period=p) for p in (1, 7)], Context())
    assert lab.compactness()["value"] == round(7 / 3, 2)


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


def _adjacent_pair(teacher, klass, day, subjects=("s1", "s2")):
    """حصّتان متّصلتان (1، 2) لمعلّمٍ في يوم — بمادّتين حتى لا تُعدّ على الشعبة."""
    return [
        slot(teacher=teacher, klass=klass, subject=subjects[0], day=day, period=1),
        slot(teacher=teacher, klass=klass, subject=subjects[1], day=day, period=2),
    ]


def test_exception_load_names_who_bears_the_most():
    """SCH-10: المعلّمُ الأكثرُ تحمّلاً يظهر باسمه — لا يذوب في العدد الكلّيّ."""
    slots = (
        _adjacent_pair("a", "c1", 0) + _adjacent_pair("a", "c1", 1) + _adjacent_pair("b", "c2", 0)
    )
    result = exception_load(ScheduleLab(slots, Context()))

    assert result["value"] == 2
    assert result["detail"]["معلّم — a"] == 2
    assert result["detail"]["معلّم — b"] == 1
    assert result["detail"]["أيّامُ معلّمين فيها استثناء"] == 3


def test_the_same_total_is_worse_when_it_lands_on_one_teacher():
    """ثلاثةُ أيّامٍ موزّعةٌ على ثلاثةِ معلّمين غيرُ ثلاثةٍ على معلّمٍ واحد."""
    spread = sum((_adjacent_pair(t, f"c{i}", 0) for i, t in enumerate("abc")), [])
    piled = sum((_adjacent_pair("a", "c1", d) for d in range(3)), [])

    assert exception_load(ScheduleLab(spread, Context()))["value"] == 1
    assert exception_load(ScheduleLab(piled, Context()))["value"] == 3


def _double(teacher, klass, day, first, subject="art"):
    """مزدوجةٌ مطلوبةٌ: حصّتان متّصلتان لمهمّةٍ واحدة."""
    return [
        slot(teacher=teacher, klass=klass, subject=subject, day=day, period=p, double=True)
        for p in (first, first + 1)
    ]


def test_a_required_double_is_one_task_not_a_run():
    """معلّمُ فنّيةٍ كلُّ أيّامه مزدوجةٌ لا يحمل استثناءً — كما يحكم HC5 في المولّد."""
    slots = sum((_double("a", f"c{d}", d, 1) for d in range(5)), [])
    result = exception_load(ScheduleLab(slots, Context()))

    assert result["value"] == 0
    assert result["detail"]["أيّامُ معلّمين فيها استثناء"] == 0


def test_a_double_followed_by_another_lesson_is_a_run_of_two_tasks():
    """المزدوجةُ لا تُعفي ما يليها: المزدوجةُ ثمّ حصّةٌ متّصلةٌ مهمّتان متّصلتان."""
    slots = _double("a", "c1", 0, 1) + [
        slot(teacher="a", klass="c2", subject="s2", day=0, period=3)
    ]
    assert exception_load(ScheduleLab(slots, Context()))["value"] == 1


def test_two_doubles_back_to_back_are_a_run_of_two_tasks():
    slots = _double("a", "c1", 0, 1) + _double("a", "c2", 0, 3, subject="art2")
    assert exception_load(ScheduleLab(slots, Context()))["value"] == 1


def test_exception_load_sees_a_class_that_bears_two_adjacent_lessons_of_one_subject():
    """الجانبُ الثاني: شعبةٌ فيها حصّتا مادّةٍ متجاورتان بمعلّمَين — لا تلاصقَ على أيٍّ منهما."""
    slots = [
        slot(teacher="t1", klass="c1", subject="s1", day=0, period=3),
        slot(teacher="t2", klass="c1", subject="s1", day=0, period=4),
    ]
    result = exception_load(ScheduleLab(slots, Context()))

    assert result["value"] == 1
    assert result["detail"]["شعبة — c1"] == 1
    assert result["detail"]["أيّامُ معلّمين فيها استثناء"] == 0


@pytest.mark.parametrize("kw", [{"double": True}, {"elective": "e"}])
def test_a_required_double_or_a_split_class_is_not_an_exception(kw):
    """المزدوجةُ المطلوبةُ متّصلةٌ عمداً، والمنقسمةُ معلّمان في الحصّة نفسِها."""
    slots = [
        slot(teacher="t1", klass="c1", subject="s1", day=0, period=3, **kw),
        slot(teacher="t2", klass="c1", subject="s1", day=0, period=4, **kw),
    ]
    result = exception_load(ScheduleLab(slots, Context()))

    assert result["value"] == 0
    assert result["detail"]["أيّامُ موادَّ في شعبٍ فيها استثناء"] == 0


def test_a_break_between_two_lessons_of_a_subject_is_not_adjacency():
    """قرارُ المالك 2026-09-24: الفسحةُ والصلاةُ تفصلان — والحكمُ بالساعة لا بالرقم."""
    ctx = Context()
    t = dt.time
    ctx.bells.update(
        {
            ("g", "regular", 3): (t(9, 0), t(9, 45)),
            ("g", "regular", 4): (t(10, 25), t(11, 10)),
        }
    )
    slots = [
        slot(teacher="t1", klass="c1", subject="s1", day=0, period=3, band="g"),
        slot(teacher="t2", klass="c1", subject="s1", day=0, period=4, band="g"),
    ]
    assert exception_load(ScheduleLab(slots, ctx))["value"] == 0


def test_exception_load_is_shown_not_judged_and_costs_the_generator_nothing():
    """عرضٌ لا حكم: لا يدخل الدرجةَ التي تقود المولّد، ولا يُحسب في قياس المحاولات."""
    key = "fairness.exception_load"
    slots = _adjacent_pair("a", "c1", 0) + _adjacent_pair("a", "c1", 1)
    lab = ScheduleLab(slots, Context())

    assert CATALOG[key][2] == "info"
    assert metric_score(key, 3) is None
    assert key in lab.compute()
    assert key not in lab.compute(display_only=False)
    assert overall_score(lab.compute()) == overall_score(lab.compute(display_only=False))
    assert exception_load(ScheduleLab([], Context()))["value"] == 0


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

    # جدولُ مؤشّراتٍ واحدٌ: عمودٌ للأساس المعتمَد وعمودٌ لكلّ توليد.
    assert "مؤشرات التوليد" in body and "أساس" in body
    assert '<th scope="col" class="num">الأساس</th>' in body
    assert "الفراغ الزائد عن الاستراحة" in body


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

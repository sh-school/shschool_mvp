"""معلّمٌ بلا هامشٍ يُوضع بالبحث الدقيق قبل الجشع.

سفيان (2026-09-05): اثنتا عشرةَ خانةً بلا تلاصقٍ لاثنتي عشرةَ حصّة — الجشعُ يُسقط
واحدةً في محاولاتٍ كثيرة وإن وُجد حلّ، والتراجعُ على مهامّه وحدَها يجده.
"""

import pytest

from operations.models import Subject, SubjectClassAssignment, TeacherExemption, TeacherPreference
from operations.scheduler import ScheduleGrid, build_tasks, generate_schedule
from operations.scheduler_tight import place_tight, tight_teachers
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db
YEAR = "2026-2027"


@pytest.fixture
def tight_school(school):
    """معلّمُ رياضياتٍ لشعبتين، ستٌّ لكلٍّ، مفرَّغٌ من الأولى والسابعة كلَّ يوم ومن
    الخميس 4–7 ومن الأحد والثلاثاء 5 و6 — بلا تلاصق: خاناتُه اثنتا عشرةَ بالضبط."""
    maths = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    teacher = UserFactory(full_name="سفيان")
    MembershipFactory(user=teacher, school=school, role=RoleFactory(school=school, name="teacher"))
    for _ in range(2):
        group = ClassGroupFactory(school=school, grade="G10", level_type="sec", academic_year=YEAR)
        SubjectClassAssignment.objects.create(
            school=school,
            academic_year=YEAR,
            teacher=teacher,
            class_group=group,
            subject=maths,
            weekly_periods=6,
            is_active=True,
        )
    blocked = {d: [1, 7] for d in range(4)}
    blocked[0] += [5, 6]
    blocked[2] += [5, 6]
    blocked[4] = [4, 5, 6, 7]
    for day, periods in blocked.items():
        for p in sorted(set(periods)):
            TeacherExemption.objects.create(
                school=school,
                teacher=teacher,
                academic_year=YEAR,
                exemption_type="specific_period",
                day_of_week=day,
                period_number=p,
                reason="قيد",
                source="school",
            )
    TeacherPreference.objects.create(
        teacher=teacher,
        school=school,
        academic_year=YEAR,
        max_daily_periods=3,
        max_consecutive=1,
        max_gap=1,
    )
    return school, teacher


def _blocked(school):
    return {
        (str(e.teacher_id), e.day_of_week, e.period_number)
        for e in TeacherExemption.objects.filter(school=school, academic_year=YEAR)
    }


def test_the_zero_slack_teacher_is_detected(tight_school):
    school, teacher = tight_school
    tasks = build_tasks(school, YEAR)
    prefs = list(TeacherPreference.objects.filter(school=school, academic_year=YEAR))

    assert tight_teachers(tasks, prefs, _blocked(school)) == [str(teacher.id)]


def test_exact_search_places_all_twelve(tight_school):
    school, teacher = tight_school
    tasks = build_tasks(school, YEAR)
    prefs = list(TeacherPreference.objects.filter(school=school, academic_year=YEAR))
    grid = ScheduleGrid()

    outcome = place_tight(grid, tasks, _blocked(school), prefs)

    assert outcome == {str(teacher.id): True}
    assert sum(1 for t in tasks if grid.home_of(t) is not None) == 12
    for day in range(5):
        periods = sorted(grid.teacher_periods_on(str(teacher.id), day))
        assert all(b - a >= 2 for a, b in zip(periods, periods[1:], strict=False)), periods


def test_generation_completes_for_the_tight_teacher(tight_school):
    school, _teacher = tight_school
    result = generate_schedule(school, YEAR)

    assert result["errors"] == [], result["errors"]
    log = result["generation"].config_snapshot["attempt_log"]
    assert all(a["leftovers"] == 0 for a in log), "كلُّ المحاولات تامّة لا واحدةٌ بالحظّ"
    assert all(all(v for v in a["tight"].values()) for a in log)

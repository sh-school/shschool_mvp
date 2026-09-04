"""سعةُ قيود المعلّم: «متتالية 1» مع «فراغ 0» = حصّةٌ في اليوم.

سفيان (2026-09-04): يومي 3، متتالية 1، فراغ 0، ونصابُه اثنتا عشرة — فوضع
المولّدُ خمساً وترك سبعاً وقال «تعذّر وضع» سبعَ مرّاتٍ بلا سبب. فالحسابُ يُقال
عند حفظ التفضيلات وفي سجلّ التوليد.
"""

import pytest
from django.urls import reverse

from operations.models import Subject, SubjectClassAssignment, TeacherPreference
from operations.preference_capacity import daily_capacity, weekly_capacity
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db
YEAR = "2026-2027"


def test_no_consecutive_and_no_gap_is_one_period_a_day():
    assert daily_capacity(3, 1, 0) == 1
    assert weekly_capacity(3, 1, 0) == 5


def test_one_gap_gives_the_alternating_pattern():
    """2·4·6: ثلاثٌ في اليوم بفراغٍ واحدٍ بين كلّ اثنتين."""
    assert daily_capacity(3, 1, 1) == 3
    assert daily_capacity(7, 1, 1) == 4, "1·3·5·7"
    assert daily_capacity(7, 2, 1) == 5, "12·45·7"


def test_without_a_gap_cap_only_the_daily_cap_counts():
    assert daily_capacity(4, 1, None) == 4
    assert weekly_capacity(4, 1, None, free_day=2) == 16


def test_blocked_periods_shrink_the_day():
    assert daily_capacity(3, 1, 1, free_periods=5) == 3
    assert daily_capacity(3, 1, 1, free_periods=2) == 1
    assert weekly_capacity(3, 1, 1, free_per_day={0: 2}) == 13


@pytest.fixture
def maths_teacher(school):
    user = UserFactory(full_name="معلّمُ رياضيات")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    maths = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    for _ in range(2):
        group = ClassGroupFactory(school=school, grade="G10", level_type="sec", academic_year=YEAR)
        SubjectClassAssignment.objects.create(
            school=school,
            academic_year=YEAR,
            teacher=user,
            class_group=group,
            subject=maths,
            weekly_periods=6,
            is_active=True,
        )
    return user


def test_the_generator_names_the_reason(school, maths_teacher):
    from operations.scheduler import generate_schedule

    TeacherPreference.objects.create(
        teacher=maths_teacher,
        school=school,
        academic_year=YEAR,
        max_daily_periods=3,
        max_consecutive=1,
        max_gap=0,
    )

    result = generate_schedule(school, YEAR)

    first = result["errors"][0]
    assert "تسع 5 حصّةً" in first and "نصابُه 12" in first and "حصّةٌ واحدةٌ في اليوم" in first


def test_saving_contradictory_preferences_is_refused(client, school, maths_teacher):
    client.force_login(maths_teacher)
    payload = {"max_daily_periods": "3", "max_consecutive": "1", "max_gap": "0", "free_day": ""}

    response = client.post(reverse("teacher_preferences") + f"?year={YEAR}", payload, follow=True)

    body = response.content.decode()
    assert "تسع 5 حصّةً" in body and "نصابُه 12" in body
    pref = TeacherPreference.objects.get(teacher=maths_teacher)
    assert (pref.max_consecutive, pref.max_gap) == (3, None), "لم يُحفظ المتناقض"


def test_a_feasible_preference_is_saved(client, school, maths_teacher):
    client.force_login(maths_teacher)
    payload = {"max_daily_periods": "3", "max_consecutive": "1", "max_gap": "1", "free_day": ""}

    client.post(reverse("teacher_preferences") + f"?year={YEAR}", payload, follow=True)

    pref = TeacherPreference.objects.get(teacher=maths_teacher, academic_year=YEAR)
    assert (pref.max_daily_periods, pref.max_consecutive, pref.max_gap) == (3, 1, 1)
    assert (
        TeacherPreference.objects.filter(teacher=maths_teacher).count() == 1
    ), "الرجوعُ يحمل العامَ فلا يُنشئ تفضيلاتِ عامٍ آخر"

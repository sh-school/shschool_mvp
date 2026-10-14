"""[SCHEDULE] شبكةُ تفضيل موضع الحصّة للمعلّم — المرحلة أ (W-20261010-032، D-330م).

أيامٌ × سبعُ حصصٍ بثلاث حالات (أفضّلها / محايدة / أتجنّبها): تُحفظ وتُعرض وتُسجَّل في الأدمن، والمحايدةُ لا تُخزَّن،
ولا يقرؤها أيُّ محرّكٍ بعد (الوزنُ في V2 بطاقةٌ لاحقة بعد استقرار V2).
"""

from pathlib import Path

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.urls import reverse

from operations.models import ScheduleSlot, TeacherPeriodPreference
from tests.conftest import MembershipFactory, RoleFactory, SchoolFactory, UserFactory

pytestmark = pytest.mark.django_db
YEAR = "2026-2027"
URL = reverse("teacher_preferences") + f"?year={YEAR}"
BASE = {"max_daily_periods": "5", "max_consecutive": "", "max_gap": "", "notes": ""}


@pytest.fixture
def teacher(client, school):
    user = UserFactory(full_name="معلّمُ الشبكة")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    client.force_login(user)
    return user


def _save(client, **cells):
    payload = {**BASE, "grid_present": "1", **cells}
    return client.post(URL, payload)


def _rows(teacher):
    return {
        (r.day_of_week, r.period_number): r.preference
        for r in TeacherPeriodPreference.objects.filter(teacher=teacher)
    }


def test_the_page_draws_the_whole_week_with_three_text_states(client, teacher):
    body = client.get(URL).content.decode()

    for day in range(5):
        for period in range(1, 8):
            assert f'name="cell_{day}_{period}"' in body
    for text in ("محايدة", "أفضّلها", "أتجنّبها"):
        assert text in body
    assert 'name="grid_present"' in body


def test_the_grid_is_saved_and_shown_as_saved(client, teacher):
    _save(client, cell_0_1="prefer", cell_2_7="avoid", cell_4_3="prefer")

    assert _rows(teacher) == {(0, 1): "prefer", (2, 7): "avoid", (4, 3): "prefer"}
    page = client.get(URL).content.decode()
    assert '<option value="prefer" selected>' in page and '<option value="avoid" selected>' in page


def test_neutral_is_never_stored_and_clears_a_previous_choice(client, teacher):
    _save(client, cell_0_1="prefer", cell_1_2="avoid")

    _save(client, cell_0_1="", cell_1_2="avoid")

    assert _rows(teacher) == {(1, 2): "avoid"}


def test_a_changed_choice_updates_the_same_row(client, teacher):
    _save(client, cell_3_4="prefer")
    row = TeacherPeriodPreference.objects.get(teacher=teacher)

    _save(client, cell_3_4="avoid")

    again = TeacherPeriodPreference.objects.get(teacher=teacher)
    assert again.pk == row.pk and again.preference == "avoid"


def test_cells_outside_the_week_and_unknown_values_are_refused(client, teacher):
    _save(
        client,
        cell_5_1="prefer",  # يومٌ خارج الأسبوع
        cell_0_8="prefer",  # حصّةٌ خارج الجدول
        cell_0_0="avoid",
        cell_1_1="maybe",  # قيمةٌ مجهولة
        cell_2_2="prefer",
    )

    assert _rows(teacher) == {(2, 2): "prefer"}


def test_a_post_without_the_grid_does_not_wipe_what_was_saved(client, teacher):
    _save(client, cell_0_1="prefer")

    client.post(URL, BASE)  # صفحةٌ قديمةٌ أو طلبٌ بلا شبكة

    assert _rows(teacher) == {(0, 1): "prefer"}


def test_a_teacher_cannot_touch_another_teachers_grid(client, school, teacher):
    other = UserFactory(full_name="معلّمٌ آخر")
    TeacherPeriodPreference.objects.create(
        school=school,
        teacher=other,
        academic_year=YEAR,
        day_of_week=0,
        period_number=1,
        preference="prefer",
    )

    _save(client, cell_0_1="avoid", teacher=str(other.pk), teacher_id=str(other.pk))

    assert _rows(other) == {(0, 1): "prefer"}
    assert _rows(teacher) == {(0, 1): "avoid"}


def test_a_failed_capacity_check_saves_no_grid(client, teacher):
    """قيدٌ يُردّ بحسابه لا يحفظ شيئاً — ولا الشبكةَ معه."""
    from operations.models import Subject, SubjectClassAssignment
    from tests.conftest import ClassGroupFactory

    school = teacher.memberships.first().school
    subject = Subject.objects.create(school=school, name_ar="مادة", code="G1")
    group = ClassGroupFactory(school=school, grade="G10", level_type="sec", academic_year=YEAR)
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=teacher,
        class_group=group,
        subject=subject,
        weekly_periods=30,
        is_active=True,
    )

    client.post(
        URL,
        {
            **BASE,
            "max_daily_periods": "5",
            "max_consecutive": "1",
            "max_gap": "0",
            "grid_present": "1",
        }
        | {"cell_0_1": "prefer"},
    )

    assert _rows(teacher) == {}


def test_the_database_forbids_a_duplicate_cell(school):
    teacher = UserFactory()
    kwargs = {
        "school": school,
        "teacher": teacher,
        "academic_year": YEAR,
        "day_of_week": 1,
        "period_number": 3,
    }
    TeacherPeriodPreference.objects.create(preference="prefer", **kwargs)

    with pytest.raises(IntegrityError), transaction.atomic():
        TeacherPeriodPreference.objects.create(preference="avoid", **kwargs)


@pytest.mark.parametrize(
    "day, period, state, ok",
    [
        (0, 1, "prefer", True),
        (4, 7, "avoid", True),
        (5, 1, "prefer", False),
        (0, 0, "prefer", False),
        (0, 8, "avoid", False),
        (0, 1, "neutral", False),
    ],
)
def test_the_model_validates_its_range(school, day, period, state, ok):
    row = TeacherPeriodPreference(
        school=school,
        teacher=UserFactory(),
        academic_year=YEAR,
        day_of_week=day,
        period_number=period,
        preference=state,
    )

    if ok:
        row.full_clean()
    else:
        with pytest.raises(ValidationError):
            row.full_clean()


def test_the_periods_follow_the_single_source_of_the_bell():
    from operations.period_preferences import wanted_from_post

    assert ScheduleSlot.PERIODS == list(range(1, 8))
    assert wanted_from_post({f"cell_0_{p}": "prefer" for p in range(1, 10)}).keys() == {
        (0, p) for p in ScheduleSlot.PERIODS
    }


def test_the_table_is_in_the_admin(client, developer_user, school):
    developer_user.is_staff = developer_user.is_superuser = True
    developer_user.must_change_password = False
    developer_user.save()
    client.force_login(developer_user)
    TeacherPeriodPreference.objects.create(
        school=school,
        teacher=UserFactory(),
        academic_year=YEAR,
        day_of_week=0,
        period_number=2,
        preference="avoid",
    )

    page = client.get(reverse("admin:operations_teacherperiodpreference_changelist"))

    assert page.status_code == 200 and "أتجنّبها" in page.content.decode()


def test_the_table_has_the_canonical_school_policy():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relrowsecurity FROM pg_class WHERE oid = 'public.operations_teacherperiodpreference'::regclass"
        )
        assert cursor.fetchone()[0] is True
        cursor.execute(
            "SELECT policyname FROM pg_policies WHERE tablename = 'operations_teacherperiodpreference'"
        )
        assert [row[0] for row in cursor.fetchall()] == ["school_isolation"]


def test_no_engine_reads_the_grid_yet():
    """المرحلة أ: لا أثرَ على التوليد. الوزنُ في V2 بطاقةٌ مستقلّة بعد استقرار V2."""
    root = Path(__file__).resolve().parent.parent / "operations"
    engines = [root / "scheduler.py", *sorted((root / "scheduler_v2").glob("*.py"))]

    readers = [
        path.name
        for path in engines
        if "TeacherPeriodPreference" in path.read_text(encoding="utf-8")
        or "period_preferences" in path.read_text(encoding="utf-8")
    ]

    assert readers == []


def test_a_school_sees_only_its_own_cells(school):
    other_school = SchoolFactory()
    teacher = UserFactory()
    TeacherPeriodPreference.objects.create(
        school=school,
        teacher=teacher,
        academic_year=YEAR,
        day_of_week=0,
        period_number=1,
        preference="prefer",
    )
    TeacherPeriodPreference.objects.create(
        school=other_school,
        teacher=teacher,
        academic_year=YEAR,
        day_of_week=0,
        period_number=1,
        preference="avoid",
    )
    from operations.period_preferences import stored_grid

    assert stored_grid(teacher, school, YEAR) == {(0, 1): "prefer"}

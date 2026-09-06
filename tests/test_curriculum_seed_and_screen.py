"""[CURRICULUM] بذرُ الخطّة من الدليل، ومنظوراها في المرصد.

    HistoricalAssignment → DepartmentHint     (وليس → Demand)

فالأرقامُ من الدليل المنشور، والإسنادُ القائمُ يُستشار في القسم وحدَه. وأخطرُ
ما يُحرَس هنا أنّ الأمرَ **لا يكتب بلا `--apply`**: خطّةٌ تُبذر بالخطأ تصير
مرجعاً تُقاس عليه السنةُ كلُّها.
"""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from academic_management.models import CurriculumPlan

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"

PREP_CODES = {
    "ISL": "التربية الإسلامية",
    "ARA": "اللغة العربية",
    "ENG": "اللغة الإنجليزية",
    "MAT": "الرياضيات",
    "SCI": "العلوم",
    "SOC": "الدراسات الاجتماعية",
    "TECH": "التكنولوجيا",
    "PE": "التربية البدنية",
    "ART": "الفنون البصرية",
    "LFS": "المهارات الحياتية والمهنية",
}


# ── تجهيز ────────────────────────────────────────────────────────────


@pytest.fixture
def school(db):
    from core.models import School

    return School.objects.create(name="مدرسة الشحانية", code="SHH-S")


@pytest.fixture
def subjects(db, school):
    from operations.models import Subject

    return {
        code: Subject.objects.create(school=school, name_ar=name, code=code)
        for code, name in PREP_CODES.items()
    }


@pytest.fixture
def seventh(db, school):
    from core.models import ClassGroup

    return ClassGroup.objects.create(
        school=school, grade="G7", section="1", level_type="prep", academic_year=YEAR
    )


def seed(**kw):
    call_command("seed_curriculum", year=YEAR, verbosity=0, **kw)


# ── البذرُ لا يكتب إلّا بأمر ─────────────────────────────────────────


def test_the_seeder_writes_nothing_without_apply(school, subjects, seventh):
    seed()
    assert CurriculumPlan.objects.count() == 0, "التقريرُ يُطبع والقاعدةُ لا تُمسّ"


def test_the_seeder_writes_the_guide_numbers_with_their_page(school, subjects, seventh):
    seed(apply=True)

    rows = {r.subject.code: r for r in CurriculumPlan.objects.all()}
    assert rows["MAT"].weekly_periods == 5
    assert rows["ISL"].weekly_periods == 4
    assert rows["ART"].weekly_periods == 2
    assert "ص14" in rows["MAT"].source_reference, "رقمٌ بلا صفحةٍ ادّعاءُ مصدر"
    assert sum(r.weekly_periods for r in rows.values()) == 34


def test_running_the_seeder_twice_changes_nothing(school, subjects, seventh):
    seed(apply=True)
    first = {(r.pk, r.weekly_periods) for r in CurriculumPlan.objects.all()}

    seed(apply=True)
    second = {(r.pk, r.weekly_periods) for r in CurriculumPlan.objects.all()}

    assert first == second, "الأمرُ متعادل — تشغيلُه مرّتين لا يُنشئ سجلّاً ثانياً"


def test_a_missing_subject_stops_the_write(school, seventh):
    """مادّةٌ في الدليل ولا سجلَّ لها هنا — تُوقف البذر ولا تُتجاوز بصمت."""
    from operations.models import Subject

    Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")

    with pytest.raises(CommandError):
        seed(apply=True)
    assert CurriculumPlan.objects.count() == 0


def test_a_grade_without_sections_is_skipped(school, subjects, seventh):
    """لا شعبةَ للحادي عشر — فلا خطّةَ له، ولا تُبذر أرقامٌ لا تُقاس."""
    seed(apply=True)
    assert set(CurriculumPlan.objects.values_list("grade", flat=True)) == {"G7"}


def test_the_tenth_grade_is_seeded_as_a_pilot(school, subjects, seventh):
    """تجربةُ العلوم الموحّدة تُوسم — كي لا تُقرأ قاعدةً مستقرّة."""
    from core.models import ClassGroup

    ClassGroup.objects.create(
        school=school, grade="G10", section="1", level_type="sec", academic_year=YEAR
    )
    seed(apply=True)

    tenth = CurriculumPlan.objects.filter(grade="G10")
    assert tenth.exists()
    assert all(r.is_pilot for r in tenth), "كلُّ صفوف العاشر تجريبيّة"
    assert tenth.get(subject__code="SCI").weekly_periods == 6
    assert tenth.get(subject__code="ARA").weekly_periods == 6
    assert sum(r.weekly_periods for r in tenth) == 35


def test_a_section_with_its_own_timetable_gets_no_plan(school, subjects):
    """شعبةُ التربية الخاصّة وحدَها في الصفّ — فلا خطّةَ تُبذر له."""
    from core.models import ClassGroup

    ClassGroup.objects.create(
        school=school,
        grade="G9",
        section="ESE",
        level_type="prep",
        academic_year=YEAR,
        has_own_timetable=True,
    )
    seed(apply=True)

    assert not CurriculumPlan.objects.filter(grade="G9").exists()


# ── المرصد: منظورا الخطّة والميزان ───────────────────────────────────


@pytest.fixture
def principal(db, school):
    from tests.conftest import MembershipFactory, RoleFactory, UserFactory

    role = RoleFactory(school=school, name="principal")
    user = UserFactory(full_name="مدير المدرسة")
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def as_principal(client_as, principal):
    return client_as(principal)


def body_of(client, view):
    response = client.get(f"{reverse('academic_management:workload')}?view={view}&year={YEAR}")
    assert response.status_code == 200
    return response.content.decode()


def test_the_curriculum_view_says_so_when_no_plan_is_seeded(as_principal, school, seventh):
    assert "لا خطّةَ دراسيّةً لهذا العام" in body_of(as_principal, "curriculum")


def test_the_curriculum_view_shows_the_plan_and_its_source(as_principal, school, subjects, seventh):
    seed(apply=True)
    body = body_of(as_principal, "curriculum")

    assert "الخطّة الدراسيّة" in body
    assert "ص14" in body, "المرجعُ معروضٌ مع الرقم"
    assert "الرياضيات" in body


def test_the_curriculum_view_reports_a_gap(as_principal, school, subjects, seventh):
    from operations.models import SubjectClassAssignment

    seed(apply=True)
    SubjectClassAssignment.objects.create(
        school=school,
        class_group=seventh,
        subject=subjects["MAT"],
        weekly_periods=3,
        academic_year=YEAR,
    )
    body = body_of(as_principal, "curriculum")

    assert "أقلُّ من الخطّة" in body
    assert "فجواتُ التغطية" in body


def test_the_balance_view_renders_the_departments(as_principal, school, subjects, seventh):
    seed(apply=True)
    body = body_of(as_principal, "balance")

    assert "الطلبُ مقابل العرض" in body
    assert "غيرُ معلوم" in body, "بلا أهدافٍ معتمَدةٍ لا يُقال إنّ القسمَ عاجز"


def test_an_unknown_view_falls_back_to_the_teachers(as_principal, school, seventh):
    body = body_of(as_principal, "nonsense")
    assert 'aria-current="page"' in body
    assert "المعلّمون" in body

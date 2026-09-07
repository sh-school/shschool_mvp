"""[DEPARTMENTS] تسجيلُ الأقسام في القاعدة — والاشتقاقُ يصير مصدراً مرّةً واحدة.

الثوابتُ التي تحرسها هذه الاختبارات:

    DerivedDepartment → RegisteredDepartment      (مرّةً، لا في كلّ طلب)
    BusinessTeacher   → ChemistryDepartment       (قرارُ المدير 2026-09-06)
    FillSubject       → مرجوحةٌ لا مُلغاة
    بلا --apply لا تُمسّ القاعدة

وأخطرُ ما يُحرَس أنّ الأمرَ **متعادل**: تشغيلُه مرّتين لا يُنشئ قسماً ثانياً —
فبذرةٌ تتضاعف تعني قسمين باسمٍ واحدٍ ومعلّمين موزّعين بينهما.
"""

import pytest
from django.core.management import call_command

from core.models import Department, Membership

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"


# ── تجهيز ────────────────────────────────────────────────────────────


@pytest.fixture
def school(db):
    from core.models import School

    return School.objects.create(name="مدرسة الشحانية", code="SHH-DEP")


@pytest.fixture
def subjects(db, school):
    from operations.models import Subject

    return {
        code: Subject.objects.create(school=school, name_ar=name, code=code)
        for code, name in (
            ("MAT", "الرياضيات"),
            ("CHE", "الكيمياء"),
            ("BUS", "إدارة الأعمال"),
            ("LFS", "المهارات الحياتية والمهنية"),
        )
    }


def a_teacher(school, name, role_name="teacher"):
    from tests.conftest import MembershipFactory, RoleFactory, UserFactory

    role = RoleFactory(school=school, name=role_name)
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=role)
    return user


def assign(school, teacher, subject, *, periods, grade="G7", level="prep", section="1"):
    from core.models import ClassGroup
    from operations.models import SubjectClassAssignment

    group, _ = ClassGroup.objects.get_or_create(
        school=school,
        grade=grade,
        section=section,
        academic_year=YEAR,
        defaults={"level_type": level},
    )
    return SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=teacher,
        class_group=group,
        subject=subject,
        weekly_periods=periods,
        is_active=True,
    )


def seed(**kw):
    call_command("seed_departments", school="SHH-DEP", year=YEAR, verbosity=0, **kw)


def department_of(user, school):
    return (
        Membership.objects.filter(user=user, school=school, is_active=True)
        .select_related("department_obj")
        .first()
        .department_obj
    )


# ══════════════════════════════════════════════════════════════════════
#  لا كتابةَ إلّا بأمر
# ══════════════════════════════════════════════════════════════════════


def test_the_command_writes_nothing_without_apply(school, subjects):
    teacher = a_teacher(school, "معلّم الرياضيات")
    assign(school, teacher, subjects["MAT"], periods=15)

    seed()

    assert Department.objects.count() == 0, "التقريرُ يُطبع والقاعدةُ لا تُمسّ"


def test_running_it_twice_creates_no_second_department(school, subjects):
    teacher = a_teacher(school, "معلّم الرياضيات")
    assign(school, teacher, subjects["MAT"], periods=15)

    seed(apply=True)
    first = set(Department.objects.values_list("pk", flat=True))
    seed(apply=True)

    assert set(Department.objects.values_list("pk", flat=True)) == first


# ══════════════════════════════════════════════════════════════════════
#  إلى أين ينتمي كلُّ معلّم
# ══════════════════════════════════════════════════════════════════════


def test_a_teacher_lands_in_the_department_of_their_heaviest_subject(school, subjects):
    teacher = a_teacher(school, "معلّم الرياضيات")
    assign(school, teacher, subjects["MAT"], periods=15)

    seed(apply=True)

    assert department_of(teacher, school).code == "math"


def test_the_business_teacher_belongs_to_chemistry(school, subjects):
    """قرارُ مدير المدرسة: إدارةُ الأعمال تتبع الكيمياءَ إداريّاً — لا قسمَ برجل."""
    business = a_teacher(school, "معلّم إدارة الأعمال")
    chemist = a_teacher(school, "معلّم الكيمياء")
    assign(school, business, subjects["BUS"], periods=12, grade="G11", level="sec")
    assign(school, chemist, subjects["CHE"], periods=12, grade="G11", level="sec", section="2")

    seed(apply=True)

    assert department_of(business, school).code == "chemistry"
    assert not Department.objects.filter(code="business").exists(), "لا يُنشأ قسمٌ برجلٍ واحد"


def test_a_fill_subject_counts_only_when_there_is_nothing_else(school, subjects):
    """حصّتا «مهارات» لمعلّم رياضياتٍ لا تنقلانه؛ ومن كلُّ نصابه منها فهو من أهلها."""
    mathematician = a_teacher(school, "معلّم الرياضيات")
    assign(school, mathematician, subjects["MAT"], periods=12)
    assign(school, mathematician, subjects["LFS"], periods=2, grade="G8", section="1")

    dedicated = a_teacher(school, "معلّم المهارات")
    assign(school, dedicated, subjects["LFS"], periods=18, grade="G9", section="1")

    seed(apply=True)

    assert department_of(mathematician, school).code == "math"
    assert department_of(dedicated, school).code == "life_skills"


def test_a_teacher_without_any_assignment_is_parked_not_dropped(school, subjects):
    """من لا حصصَ له يُسجَّل في «غير محدَّد» — ولا يسقط من السجلّ."""
    idle = a_teacher(school, "معلّمٌ بلا إسناد")

    seed(apply=True)

    assert department_of(idle, school).code == "other"


def test_the_coordinator_becomes_the_head_of_their_department(school, subjects):
    coordinator = a_teacher(school, "منسّق الرياضيات", role_name="coordinator")
    assign(school, coordinator, subjects["MAT"], periods=10)

    seed(apply=True)

    assert Department.objects.get(code="math").head == coordinator


def test_the_registered_department_names_match_the_approved_sheet(school, subjects):
    """أسماءُ السجلّ هي أسماءُ ورقة الجدول العام — مصدرٌ واحدٌ للتسمية."""
    from operations.departments import DEPARTMENT_NAMES

    teacher = a_teacher(school, "معلّم الكيمياء")
    assign(school, teacher, subjects["CHE"], periods=12, grade="G11", level="sec")

    seed(apply=True)

    department = Department.objects.get(code="chemistry")
    assert department.name == DEPARTMENT_NAMES["chemistry"]


# ══════════════════════════════════════════════════════════════════════
#  الانتماءُ لا يخالف المسمّى الوظيفيّ
# ══════════════════════════════════════════════════════════════════════


def test_a_non_teaching_role_cannot_hold_an_academic_department(school, subjects):
    """الممرّضُ وأمينُ المكتبة موظّفان في المدرسة ولا قسمَ أكاديميَّ لهما."""
    from django.core.exceptions import ValidationError

    from core.models import Membership

    teacher = a_teacher(school, "معلّم الرياضيات")
    assign(school, teacher, subjects["MAT"], periods=12)
    seed(apply=True)
    maths = Department.objects.get(code="math")

    nurse = a_teacher(school, "الممرّض", role_name="nurse")
    membership = Membership.objects.get(user=nurse, school=school)
    membership.department_obj = maths

    with pytest.raises(ValidationError):
        membership.full_clean(exclude=["user", "school", "role"])


def test_the_department_is_written_on_the_teaching_membership_only(school, subjects):
    """معلّمٌ ابنُه في المدرسة له عضويّتان — والقسمُ لعضويّة التدريس وحدَها."""
    from core.models import Membership
    from tests.conftest import MembershipFactory, RoleFactory

    teacher = a_teacher(school, "معلّمٌ ووليُّ أمر")
    parent_role = RoleFactory(school=school, name="parent")
    MembershipFactory(user=teacher, school=school, role=parent_role)
    assign(school, teacher, subjects["MAT"], periods=12)

    seed(apply=True)

    carried = Membership.objects.filter(
        user=teacher, school=school, department_obj__isnull=False
    ).select_related("role")
    assert [m.role.name for m in carried] == ["teacher"]


def test_the_governing_membership_prefers_staff_over_parent(school, subjects):
    """وكان الاختيارُ بلا ترتيبٍ فيظهر معلّمُ الرياضيات «وليَّ أمرٍ» بلا قسم."""
    from tests.conftest import MembershipFactory, RoleFactory

    teacher = a_teacher(school, "معلّمٌ ووليُّ أمر")
    MembershipFactory(user=teacher, school=school, role=RoleFactory(school=school, name="parent"))
    assign(school, teacher, subjects["MAT"], periods=12)
    seed(apply=True)

    teacher.invalidate_active_membership()
    assert teacher.get_role() == "teacher"
    assert teacher.department_obj.code == "math", "والقسمُ يُقرأ من العضويّة التي تحمله"

"""صفحةُ إدخال الدرجات: الدرجةُ المحفوظة تظهر في الحقل الرقميّ ولا تُمحى بـ«حفظ الكل».

اللغةُ `ar` تُعرِّب الـDecimal فتُنتج `value="14,00"`، وحقلُ `type="number"` يرفض الفاصلةَ فيعرض نفسَه فارغاً؛
فيرى المعلّمُ درجاتِه المحفوظةَ ضائعةً، و«حفظ الكل» يُرسل حقولاً فارغةً (مفتاحٌ موجودٌ وقيمةٌ فارغة = مسحٌ صريح)
فتُمحى الدرجاتُ فعلاً. الإصلاحُ عند المصدر: `|unlocalize` في القالب.
"""

import re
from decimal import Decimal

import pytest

from assessments.models import (
    Assessment,
    AssessmentPackage,
    StudentAssessmentGrade,
    SubjectClassSetup,
)
from operations.models import Subject
from tests.conftest import ClassGroupFactory, StudentEnrollmentFactory, UserFactory

pytestmark = pytest.mark.django_db

_VALUE = re.compile(r'<input[^>]*name="grade"[^>]*value="([^"]*)"')
_NUMERIC = re.compile(r"^\d+(\.\d+)?$")


@pytest.fixture
def assessment(school, teacher_user):
    group = ClassGroupFactory(school=school)
    subject = Subject.objects.create(school=school, name_ar="العلوم", code="SCI")
    setup = SubjectClassSetup.objects.create(
        school=school,
        subject=subject,
        class_group=group,
        teacher=teacher_user,
        academic_year="2025-2026",
    )
    package = AssessmentPackage.objects.create(
        setup=setup,
        school=school,
        package_type="P1",
        semester="S1",
        weight=Decimal("50"),
        semester_max_grade=Decimal("40"),
    )
    return Assessment.objects.create(
        package=package,
        school=school,
        title="اختبار قصير",
        max_grade=Decimal("20"),
        weight_in_package=Decimal("100"),
        status="published",
    )


@pytest.fixture
def graded_student(assessment, teacher_user):
    kid = UserFactory()
    StudentEnrollmentFactory(student=kid, class_group=assessment.class_group)
    StudentAssessmentGrade.objects.create(
        school=assessment.school,
        assessment=assessment,
        student=kid,
        grade=Decimal("14.00"),
        entered_by=teacher_user,
    )
    return kid


def _page(client_as, teacher_user, assessment):
    response = client_as(teacher_user).get(f"/assessments/assessment/{assessment.id}/")
    assert response.status_code == 200
    return response.content.decode()


def test_saved_grade_renders_as_a_plain_number(client_as, teacher_user, assessment, graded_student):
    values = _VALUE.findall(_page(client_as, teacher_user, assessment))
    assert values, "لم يظهر حقلُ الدرجة"
    assert all(_NUMERIC.match(v) for v in values if v), values
    assert "14.00" in values


def test_save_all_keeps_the_grade_the_page_rendered(
    client_as, teacher_user, assessment, graded_student
):
    """يُعيد ما عرضته الصفحةُ كما يفعل المتصفّح: قيمةٌ يرفضها type=number تصير حقلاً فارغاً فتُمحى الدرجة."""
    (shown,) = _VALUE.findall(_page(client_as, teacher_user, assessment))
    if not _NUMERIC.match(shown):
        shown = ""
    sid = str(graded_student.id)
    response = client_as(teacher_user).post(
        f"/assessments/assessment/{assessment.id}/save-all/",
        {f"grade_{sid}": shown, f"absent_{sid}": "0", f"excused_{sid}": "0", f"notes_{sid}": ""},
    )
    assert response.status_code == 302
    saved = StudentAssessmentGrade.objects.get(assessment=assessment, student=graded_student)
    assert saved.grade == Decimal("14.00")

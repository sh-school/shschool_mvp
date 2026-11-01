"""فجوات التخويل والخصوصيّة في المسارات الساخنة (W-20261101-007، مراجعة 2026-11-01 البند 1-2).

لكلّ موضعٍ اختبارُ رفضٍ (403/404) واختبارُ قبولٍ لمن يملك الحقّ، فلا يُحلّ الأمنُ بإغلاقٍ شامل.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.urls import reverse

from assessments.models import Assessment, AssessmentPackage, SubjectClassSetup
from assessments.services import AssessmentClosedError, GradeService
from core.exports.services import _audit_repr
from operations.models import ScheduleSlot, Subject
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    SchoolFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


def _member(school, role, name):
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


def _teach(school, teacher, student):
    """يجعل الطالبَ في جدول المعلّم."""
    group = ClassGroupFactory(school=school)
    StudentEnrollmentFactory(student=student, class_group=group)
    ScheduleSlot.objects.create(
        school=school,
        teacher=teacher,
        class_group=group,
        day_of_week=1,
        period_number=2,
        start_time=dt.time(8, 20),
        end_time=dt.time(9, 5),
    )
    return group


@pytest.fixture
def other_school(db):
    return SchoolFactory()


# ── كشوف الطالب الفردية: معلّمٌ يدرّسه فقط ──────────────────────────────
STUDENT_PDFS = ["student_result_pdf", "student_annual_result_pdf", "student_certificate_pdf"]


@pytest.mark.parametrize("name", STUDENT_PDFS)
def test_a_teacher_who_does_not_teach_the_student_gets_403(
    client_as, teacher_user, student_user, name
):
    response = client_as(teacher_user).get(reverse(name, args=[student_user.id]))

    assert response.status_code == 403


@pytest.mark.parametrize("name", ["student_result_pdf"])
def test_the_teacher_of_the_student_still_opens_the_report(
    client_as, school, teacher_user, student_user, name
):
    _teach(school, teacher_user, student_user)

    response = client_as(teacher_user).get(reverse(name, args=[student_user.id]) + "?preview=1")

    assert response.status_code == 200


# ── REST: طالبٌ من مدرسةٍ أخرى لا يُقرأ بمعرّفه ───────────────────────────
@pytest.mark.parametrize("name", ["student-grades", "student-attendance"])
def test_the_api_does_not_read_a_student_of_another_school(
    client_as, principal_user, other_school, name
):
    outsider = _member(other_school, "student", "طالبٌ غريب")

    response = client_as(principal_user).get(reverse(f"api_v1:{name}", args=[outsider.id]))

    assert response.status_code == 404


# ── HTMX جدول الملاحظة: بالقدرة والعضويّة ──────────────────────────────────
def _schedule_url(**params):
    from urllib.parse import urlencode

    return reverse("observation_teacher_schedule") + "?" + urlencode(params)


def test_the_schedule_partial_refuses_whoever_lacks_the_capability(client_as, school, teacher_user):
    other = _member(school, "teacher", "زميل")

    response = client_as(teacher_user).get(
        _schedule_url(teacher=other.id, observation_date="2026-09-20")
    )

    assert response.status_code == 404


def test_the_schedule_partial_refuses_a_teacher_of_another_school(
    client_as, principal_user, other_school
):
    outsider = _member(other_school, "teacher", "معلّمٌ غريب")

    response = client_as(principal_user).get(
        _schedule_url(teacher=outsider.id, observation_date="2026-09-20")
    )

    assert response.status_code == 404


def test_the_observer_reads_a_teacher_of_the_school(client_as, school, principal_user):
    mine = _member(school, "teacher", "معلّم المدرسة")

    response = client_as(principal_user).get(
        _schedule_url(teacher=mine.id, observation_date="2026-09-20")
    )

    assert response.status_code == 200


# ── الإسناد: صفُّ مدرسةٍ أخرى 404 ────────────────────────────────────────────
@pytest.mark.parametrize(
    "name",
    [
        "assignment_update_periods",
        "assignment_toggle_double",
        "assignment_set_parallel",
        "assignment_remove_row",
    ],
)
def test_an_assignment_row_of_another_school_is_not_found(
    client_as, principal_user, other_school, name
):
    from operations.models import SubjectClassAssignment

    teacher = _member(other_school, "teacher", "معلّم غريب")
    subject = Subject.objects.create(school=other_school, name_ar="علوم", code="SCI")
    row = SubjectClassAssignment.objects.create(
        school=other_school,
        class_group=ClassGroupFactory(school=other_school),
        subject=subject,
        teacher=teacher,
        weekly_periods=3,
        academic_year="2025-2026",
        is_active=True,
    )
    url = reverse(f"academic_management:{name}", args=[row.id])

    response = client_as(principal_user).post(url, {"weekly_periods": "4"})

    assert response.status_code == 404


# ── التقييم المغلق: لا كتابة ────────────────────────────────────────────────
@pytest.fixture
def closed_assessment(school, class_group, teacher_user):
    subject = Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")
    setup = SubjectClassSetup.objects.create(
        school=school,
        subject=subject,
        class_group=class_group,
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
        title="اختبارٌ مقفل",
        max_grade=Decimal("20"),
        weight_in_package=Decimal("100"),
        status="closed",
    )


def test_a_closed_assessment_refuses_a_single_grade(closed_assessment, student_user):
    with pytest.raises(AssessmentClosedError):
        GradeService.save_grade(
            assessment=closed_assessment, student=student_user, grade=Decimal("10")
        )


def test_a_closed_assessment_is_not_reopened_by_a_bulk_save(
    closed_assessment, enrolled_student, teacher_user
):
    post = {f"grade_{enrolled_student.student_id}": "15"}

    with pytest.raises(AssessmentClosedError):
        GradeService.save_all_from_post(closed_assessment, post, teacher_user)

    closed_assessment.refresh_from_db()
    assert closed_assessment.status == "closed"


# ── سجلّ التصدير: أسماءُ المعاملات بلا قيمها ───────────────────────────────
def test_the_export_audit_keeps_parameter_names_but_no_values():
    repr_ = _audit_repr("reports.x", "national_id=29000000001&year=2026-2027&q=")

    assert "29000000001" not in repr_ and "2026" not in repr_
    assert repr_ == "reports.x?national_id&q&year"
    assert _audit_repr("reports.x", "") == "reports.x"

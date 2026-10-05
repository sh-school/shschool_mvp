"""[SECURITY] مواضعُ الكتابة لا تقبل مستخدماً من مدرسةٍ أخرى بمعرّفه (`docs/privacy/tenant_isolation_audit_2026-10-05.md`).

`core_customuser` عالميٌّ بالتصميم فلا تحميه RLS؛ فكلُّ عرضٍ يجلب مستخدماً بمعرّفٍ من الطلب يمرّ بـ`core.user_selectors`.
كان ربطُ غريبٍ بسجلّ مدرستك ممكناً بمعرّفٍ (UUID) — وهنا يثبت الرفضُ، ويثبت أنّ مستخدمَ مدرستك ما زال مقبولاً.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.http import Http404
from django.urls import reverse

from assessments.models import Assessment, AssessmentPackage, SubjectClassSetup
from core.user_selectors import school_user_or_404, school_user_or_none
from exam_control.models import ExamSession, ExamSupervisor
from operations.models import Subject
from quality.models import ExecutorMapping, QualityCommitteeMember
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    SchoolFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

FOREIGN_NAME = "غريبٌ_عن_المدرسة_QQ"


@pytest.fixture
def foreign(db):
    """مستخدمٌ عضوٌ في مدرسةٍ أخرى وحدَها."""
    other = SchoolFactory()
    user = UserFactory(full_name=FOREIGN_NAME)
    MembershipFactory(user=user, school=other, role=RoleFactory(school=other, name="teacher"))
    return user


# ── المنفذُ نفسُه ────────────────────────────────────────────────────────────


def test_selector_returns_a_member_of_the_school(school, teacher_user):
    assert school_user_or_404(school, teacher_user.pk) == teacher_user
    assert school_user_or_none(school, str(teacher_user.pk)) == teacher_user


def test_selector_treats_a_foreign_user_as_missing(school, foreign):
    with pytest.raises(Http404):
        school_user_or_404(school, foreign.pk)
    assert school_user_or_none(school, foreign.pk) is None


@pytest.mark.parametrize("bad", ["not-a-uuid", "", None, "123"])
def test_selector_treats_a_malformed_id_as_missing_not_a_500(school, bad):
    with pytest.raises(Http404):
        school_user_or_404(school, bad)
    assert school_user_or_none(school, bad) is None


def test_selector_returns_one_row_for_a_person_with_two_memberships(school, teacher_user):
    MembershipFactory(
        user=teacher_user, school=school, role=RoleFactory(school=school, name="parent")
    )
    assert school_user_or_404(school, teacher_user.pk) == teacher_user


def test_selector_ever_includes_a_departed_member(school):
    gone = UserFactory()
    MembershipFactory(
        user=gone, school=school, role=RoleFactory(school=school, name="teacher"), is_active=False
    )
    assert school_user_or_none(school, gone.pk) is None
    assert school_user_or_none(school, gone.pk, ever=True) == gone


# ── الجودة: ربطُ المنفِّذ وعضوُ اللجنة ──────────────────────────────────────


def test_executor_mapping_rejects_a_foreign_user(client_as, principal_user, foreign):
    response = client_as(principal_user).post(
        reverse("save_executor_mapping"),
        {"executor_norm": "x", "user_id": str(foreign.id), "year": "2025-2026"},
    )
    assert response.status_code == 404
    assert not ExecutorMapping.objects.filter(user=foreign).exists()


def test_executor_mapping_accepts_a_member(client_as, principal_user, teacher_user):
    response = client_as(principal_user).post(
        reverse("save_executor_mapping"),
        {"executor_norm": "x", "user_id": str(teacher_user.id), "year": "2025-2026"},
    )
    assert response.status_code in (200, 302)
    assert ExecutorMapping.objects.filter(user=teacher_user).exists()


def test_committee_member_rejects_a_foreign_user(client_as, principal_user, foreign):
    response = client_as(principal_user).post(
        reverse("add_committee_member"),
        {
            "year": "2025-2026",
            "user_id": str(foreign.id),
            "job_title": "معلم",
            "committee_type": QualityCommitteeMember.REVIEW,
        },
    )
    assert response.status_code == 404
    assert not QualityCommitteeMember.objects.filter(user=foreign).exists()


# ── الكنترول: مشرفُ اللجنة ───────────────────────────────────────────────────


@pytest.fixture
def exam_session(school, principal_user):
    return ExamSession.objects.create(
        school=school,
        name="اختبار",
        session_type="final",
        academic_year="2025-2026",
        start_date=date.today(),
        end_date=date.today() + timedelta(days=14),
        created_by=principal_user,
    )


def test_exam_supervisor_rejects_a_foreign_user(client_as, principal_user, exam_session, foreign):
    response = client_as(principal_user).post(
        f"/exam-control/session/{exam_session.pk}/supervisors/",
        {"staff_id": str(foreign.id), "role": "supervisor"},
    )
    assert response.status_code == 404
    assert not ExamSupervisor.objects.filter(staff=foreign).exists()


def test_exam_supervisor_accepts_a_member(client_as, principal_user, exam_session, teacher_user):
    response = client_as(principal_user).post(
        f"/exam-control/session/{exam_session.pk}/supervisors/",
        {"staff_id": str(teacher_user.id), "role": "supervisor"},
    )
    assert response.status_code == 302
    assert ExamSupervisor.objects.filter(staff=teacher_user, session=exam_session).exists()


# ── التقييمات: إسنادُ المعلّم وحفظُ الدرجة ──────────────────────────────────


def test_subject_setup_rejects_a_foreign_teacher(client_as, principal_user, school, foreign):
    subject = Subject.objects.create(school=school, name_ar="كيمياء", code="CHEM")
    group = ClassGroupFactory(school=school)
    response = client_as(principal_user).post(
        "/assessments/setup/",
        {
            "subject": str(subject.id),
            "class_group": str(group.id),
            "teacher": str(foreign.id),
            "academic_year": "2025-2026",
        },
    )
    assert response.status_code == 404
    assert not SubjectClassSetup.objects.filter(teacher=foreign).exists()


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


def _grade(client, assessment, student_id):
    return client.post(
        f"/assessments/assessment/{assessment.id}/save-single/",
        {"student_id": str(student_id), "grade": "18"},
    )


def test_single_grade_accepts_a_student_enrolled_in_the_assessment_class(
    client_as, teacher_user, assessment
):
    kid = UserFactory()
    StudentEnrollmentFactory(student=kid, class_group=assessment.class_group)
    assert _grade(client_as(teacher_user), assessment, kid.id).status_code == 200


def test_single_grade_rejects_a_student_of_another_school(
    client_as, teacher_user, assessment, foreign
):
    assert _grade(client_as(teacher_user), assessment, foreign.id).status_code == 404
    assert not foreign.assessment_grades.exists() if hasattr(foreign, "assessment_grades") else True


def test_single_grade_rejects_a_student_of_another_class_in_the_same_school(
    client_as, teacher_user, assessment, school
):
    other_class_kid = UserFactory()
    StudentEnrollmentFactory(student=other_class_kid, class_group=ClassGroupFactory(school=school))
    assert _grade(client_as(teacher_user), assessment, other_class_kid.id).status_code == 404


# ── الأجنحة: بديلُ الجناح ────────────────────────────────────────────────────


def test_wing_coverage_rejects_a_foreign_substitute(client_as, principal_user, school, foreign):
    from core.academic_calendar import academic_year_for_school
    from core.models import Wing, WingCoverage

    wing = Wing.objects.create(
        school=school,
        code="w9",
        name="جناحٌ للاختبار",
        academic_year=academic_year_for_school(school),
    )
    client = client_as(principal_user)

    rejected = client.post(
        reverse("wings:coverage_assign", args=[wing.code]), {"substitute": str(foreign.id)}
    )
    assert rejected.status_code == 302  # «اختر البديل» — كأنّه لم يُرسَل
    assert not WingCoverage.objects.filter(substitute=foreign).exists()

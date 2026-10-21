"""ملاحظاتُ المراجعة الأمنية لـ#1180 (قرارُ المالك 2026-10-20): تشفيرُ المرجع، واستثناءُ المطوّر، وعزلُ المدارس، وأثرُ المحاولة المتأخّرة، وN+1.

بياناتُ الاختبار مصنَّعة كلُّها (PDPPL).
"""

import pytest
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.test.utils import CaptureQueriesContext

from assessments.models import StudentAssessmentGrade
from assessments.services import GradeService
from core.capabilities import has_capability
from core.models import AuditLog
from tests.conftest import MembershipFactory, RoleFactory, SchoolFactory, UserFactory
from tests.test_exam_excuse_decision import _decide, _row, _staff, absent  # noqa: F401
from tests.test_grade_save_all import assessment  # noqa: F401

pytestmark = pytest.mark.django_db

SECRET = "مرجع-مصنَّع-للتشفير-فقط"


def test_the_excuse_reference_is_encrypted_in_the_database_and_plain_through_the_orm(
    school,
    assessment,  # noqa: F811
    student_user,
    absent,  # noqa: F811
):
    GradeService.decide_excuse(
        assessment, student_user, "illness", SECRET, _staff(school, "social_worker")
    )
    row = _row(assessment, student_user)
    with connection.cursor() as cur:
        cur.execute(
            "SELECT excuse_reference FROM assessments_studentassessmentgrade WHERE id = %s",
            [row.pk],
        )
        raw = cur.fetchone()[0]
    assert SECRET not in raw
    assert StudentAssessmentGrade.objects.get(pk=row.pk).excuse_reference == SECRET


def test_the_platform_developer_does_not_hold_the_excuse_decision():
    from core.unrestricted_role import DEVELOPER_EXCLUDED_CAPABILITIES

    assert "assessments.decide_excuse" in DEVELOPER_EXCLUDED_CAPABILITIES


def test_a_holder_from_another_school_is_refused_and_nothing_changes(
    client_as,
    school,
    assessment,  # noqa: F811
    student_user,
    absent,  # noqa: F811
):
    other = SchoolFactory()
    outsider = UserFactory(full_name="موظف مدرسة أخرى")
    MembershipFactory(
        user=outsider, school=other, role=RoleFactory(school=other, name="social_worker")
    )
    assert has_capability(outsider, "assessments.decide_excuse")

    with pytest.raises(PermissionDenied):
        GradeService.decide_excuse(assessment, student_user, "illness", "x", outsider)
    resp = _decide(client_as(outsider), assessment, student_user)

    assert resp.status_code == 404
    row = _row(assessment, student_user)
    assert row.is_excused is False and row.excuse_decided_by is None


def test_the_late_attempt_audit_points_at_the_students_row(
    school,
    assessment,  # noqa: F811
    student_user,
    absent,  # noqa: F811
):
    from datetime import date

    by = _staff(school, "social_worker")
    deadline = (date(2026, 1, 15), date(2026, 1, 12))
    GradeService._audit_late_excuse(assessment, student_user, by, date(2026, 1, 20), deadline)

    log = AuditLog.objects.filter(user=by, changes__excuse_attempt="rejected_after_deadline").get()
    assert log.model_name == "StudentAssessmentGrade"
    assert str(log.object_id) == str(absent.pk)


def test_the_deadline_is_queried_once_per_school_year_and_date(assessment):  # noqa: F811
    cache: dict = {}
    GradeService.excuse_deadline(assessment, cache)
    with CaptureQueriesContext(connection) as ctx:
        GradeService.excuse_deadline(assessment, cache)
        GradeService.excuse_deadline(assessment, cache)
    assert len(ctx) == 0

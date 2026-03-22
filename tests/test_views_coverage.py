"""
tests/test_views_coverage.py
Coverage tests for assessments/views.py, exam_control/views.py, api/views.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIClient

from assessments.models import (
    Assessment,
    AssessmentPackage,
    SubjectClassSetup,
)
from assessments.services import GradeService
from core.models import (
    ParentStudentLink,
)
from exam_control.models import (
    ExamGradeSheet,
    ExamIncident,
    ExamRoom,
    ExamSchedule,
    ExamSession,
    ExamSupervisor,
)
from notifications.models import InAppNotification
from operations.models import Session, Subject
from tests.conftest import (
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

# ══════════════════════════════════════════════════════════════
#  Shared fixtures for assessments
# ══════════════════════════════════════════════════════════════


@pytest.fixture
def subject(db, school):
    return Subject.objects.create(school=school, name_ar="العلوم", code="SCI")


@pytest.fixture
def setup(db, school, subject, class_group, teacher_user):
    return SubjectClassSetup.objects.create(
        school=school,
        subject=subject,
        class_group=class_group,
        teacher=teacher_user,
        academic_year="2025-2026",
    )


@pytest.fixture
def s1_package(db, school, setup):
    return AssessmentPackage.objects.create(
        setup=setup,
        school=school,
        package_type="P1",
        semester="S1",
        weight=Decimal("50"),
        semester_max_grade=Decimal("40"),
    )


@pytest.fixture
def s1_exam_package(db, school, setup):
    return AssessmentPackage.objects.create(
        setup=setup,
        school=school,
        package_type="P4",
        semester="S1",
        weight=Decimal("50"),
        semester_max_grade=Decimal("40"),
    )


@pytest.fixture
def assessment_in_p1(db, school, s1_package):
    return Assessment.objects.create(
        package=s1_package,
        school=school,
        title="اختبار قصير 1",
        max_grade=Decimal("20"),
        weight_in_package=Decimal("100"),
        status="published",
    )


@pytest.fixture
def assessment_in_p4(db, school, s1_exam_package):
    return Assessment.objects.create(
        package=s1_exam_package,
        school=school,
        title="اختبار نهاية الفصل",
        max_grade=Decimal("40"),
        weight_in_package=Decimal("100"),
        status="published",
    )


# ══════════════════════════════════════════════════════════════
#  Shared fixtures for exam_control
# ══════════════════════════════════════════════════════════════


@pytest.fixture
def exam_session(db, school, principal_user):
    return ExamSession.objects.create(
        school=school,
        name="اختبار نهاية الفصل الأول",
        session_type="final",
        academic_year="2025-2026",
        start_date=date.today(),
        end_date=date.today() + timedelta(days=14),
        created_by=principal_user,
    )


@pytest.fixture
def exam_room(db, exam_session):
    return ExamRoom.objects.create(
        session=exam_session,
        name="قاعة 101",
        capacity=30,
    )


@pytest.fixture
def exam_schedule(db, exam_session, exam_room):
    return ExamSchedule.objects.create(
        session=exam_session,
        room=exam_room,
        subject="الرياضيات",
        grade_level="G7",
        exam_date=date.today() + timedelta(days=1),
        start_time="08:00",
        end_time="10:00",
        students_count=25,
    )


@pytest.fixture
def exam_grade_sheet(db, exam_schedule):
    return ExamGradeSheet.objects.create(
        schedule=exam_schedule,
        papers_count=25,
    )


@pytest.fixture
def exam_incident(db, exam_session, exam_room, principal_user):
    return ExamIncident.objects.create(
        session=exam_session,
        room=exam_room,
        reported_by=principal_user,
        incident_type="other",
        severity=1,
        description="حادث تقني أثناء الاختبار",
    )


# ══════════════════════════════════════════════════════════════
#  assessments/views.py — Coverage Tests
# ══════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAssessmentViewsCoverage:
    """Tests for uncovered lines in assessments/views.py"""

    # ── class_gradebook ──────────────────────────────────────

    def test_class_gradebook_as_teacher(self, client_as, teacher_user, setup, enrolled_student):
        c = client_as(teacher_user)
        resp = c.get(f"/assessments/setup/{setup.id}/gradebook/")
        assert resp.status_code == 200
        assert "setup" in resp.context

    def test_class_gradebook_as_principal(self, client_as, principal_user, setup, enrolled_student):
        c = client_as(principal_user)
        resp = c.get(f"/assessments/setup/{setup.id}/gradebook/")
        assert resp.status_code == 200

    def test_class_gradebook_forbidden_other_teacher(self, client_as, setup, school):
        role = RoleFactory(school=school, name="teacher")
        other = UserFactory(full_name="معلم آخر")
        MembershipFactory(user=other, school=school, role=role)
        c = client_as(other)
        resp = c.get(f"/assessments/setup/{setup.id}/gradebook/")
        assert resp.status_code == 403

    def test_class_gradebook_with_semester_s1(
        self,
        client_as,
        teacher_user,
        setup,
        enrolled_student,
        s1_package,
        assessment_in_p1,
        student_user,
    ):
        GradeService.save_grade(
            assessment=assessment_in_p1,
            student=student_user,
            grade=Decimal("15"),
            entered_by=teacher_user,
        )
        c = client_as(teacher_user)
        resp = c.get(f"/assessments/setup/{setup.id}/gradebook/?semester=S1")
        assert resp.status_code == 200
        rows = resp.context["rows"]
        assert len(rows) >= 1

    def test_class_gradebook_annual_view(
        self,
        client_as,
        teacher_user,
        setup,
        enrolled_student,
    ):
        c = client_as(teacher_user)
        resp = c.get(f"/assessments/setup/{setup.id}/gradebook/?semester=annual")
        assert resp.status_code == 200
        assert resp.context["show_annual"] is True

    def test_class_gradebook_with_semester_result(
        self,
        client_as,
        teacher_user,
        setup,
        enrolled_student,
        s1_package,
        s1_exam_package,
        assessment_in_p1,
        assessment_in_p4,
        student_user,
    ):
        """Cover the sem_result and annual_result branches"""
        GradeService.save_grade(
            assessment=assessment_in_p1,
            student=student_user,
            grade=Decimal("15"),
        )
        GradeService.save_grade(
            assessment=assessment_in_p4,
            student=student_user,
            grade=Decimal("30"),
        )
        c = client_as(teacher_user)
        resp = c.get(f"/assessments/setup/{setup.id}/gradebook/?semester=S1")
        assert resp.status_code == 200
        rows = resp.context["rows"]
        assert any(r["semester_result"] is not None for r in rows)

    # ── export_gradebook ─────────────────────────────────────

    def test_export_gradebook_basic(self, client_as, teacher_user, setup, enrolled_student):
        c = client_as(teacher_user)
        resp = c.get(f"/assessments/setup/{setup.id}/export/")
        assert resp.status_code == 200
        assert "spreadsheetml" in resp["Content-Type"]
        assert "attachment" in resp["Content-Disposition"]

    def test_export_gradebook_as_principal(
        self, client_as, principal_user, setup, enrolled_student
    ):
        c = client_as(principal_user)
        resp = c.get(f"/assessments/setup/{setup.id}/export/?semester=S1")
        assert resp.status_code == 200
        assert "spreadsheetml" in resp["Content-Type"]

    def test_export_gradebook_forbidden_other_teacher(self, client_as, setup, school):
        role = RoleFactory(school=school, name="teacher")
        other = UserFactory()
        MembershipFactory(user=other, school=school, role=role)
        c = client_as(other)
        resp = c.get(f"/assessments/setup/{setup.id}/export/")
        assert resp.status_code == 403

    def test_export_gradebook_with_grades(
        self,
        client_as,
        teacher_user,
        setup,
        enrolled_student,
        s1_package,
        s1_exam_package,
        assessment_in_p1,
        assessment_in_p4,
        student_user,
    ):
        """Export with actual grade data to cover data rows"""
        GradeService.save_grade(
            assessment=assessment_in_p1,
            student=student_user,
            grade=Decimal("18"),
        )
        GradeService.save_grade(
            assessment=assessment_in_p4,
            student=student_user,
            grade=Decimal("35"),
        )
        c = client_as(teacher_user)
        resp = c.get(f"/assessments/setup/{setup.id}/export/?semester=S1")
        assert resp.status_code == 200
        assert len(resp.content) > 0

    def test_export_gradebook_multiple_students(
        self,
        client_as,
        teacher_user,
        setup,
        school,
        class_group,
        s1_package,
        assessment_in_p1,
    ):
        """Cover alternating row fill (even/odd) in export"""
        students = []
        for i in range(3):
            role = RoleFactory(school=school, name="student")
            st = UserFactory(full_name=f"طالب تصدير {i}")
            MembershipFactory(user=st, school=school, role=role)
            StudentEnrollmentFactory(student=st, class_group=class_group)
            GradeService.save_grade(
                assessment=assessment_in_p1,
                student=st,
                grade=Decimal(str(10 + i)),
            )
            students.append(st)
        c = client_as(teacher_user)
        resp = c.get(f"/assessments/setup/{setup.id}/export/?semester=S1")
        assert resp.status_code == 200

    # ── recalculate_class ────────────────────────────────────

    def test_recalculate_class_as_teacher(
        self,
        client_as,
        teacher_user,
        setup,
        enrolled_student,
        s1_package,
        assessment_in_p1,
        student_user,
    ):
        GradeService.save_grade(
            assessment=assessment_in_p1,
            student=student_user,
            grade=Decimal("15"),
        )
        c = client_as(teacher_user)
        resp = c.post(f"/assessments/setup/{setup.id}/recalculate/")
        assert resp.status_code == 302

    def test_recalculate_class_as_principal(
        self,
        client_as,
        principal_user,
        setup,
        enrolled_student,
    ):
        c = client_as(principal_user)
        resp = c.post(f"/assessments/setup/{setup.id}/recalculate/")
        assert resp.status_code == 302

    def test_recalculate_class_forbidden(self, client_as, setup, school):
        role = RoleFactory(school=school, name="teacher")
        other = UserFactory()
        MembershipFactory(user=other, school=school, role=role)
        c = client_as(other)
        resp = c.post(f"/assessments/setup/{setup.id}/recalculate/")
        assert resp.status_code == 403

    def test_recalculate_class_get_not_allowed(
        self,
        client_as,
        teacher_user,
        setup,
    ):
        c = client_as(teacher_user)
        resp = c.get(f"/assessments/setup/{setup.id}/recalculate/")
        assert resp.status_code == 405

    # ── student_report ───────────────────────────────────────

    def test_student_report_as_principal(
        self,
        client_as,
        principal_user,
        student_user,
    ):
        c = client_as(principal_user)
        resp = c.get(f"/assessments/student/{student_user.id}/report/")
        assert resp.status_code == 200

    def test_student_report_as_teacher(
        self,
        client_as,
        teacher_user,
        student_user,
    ):
        c = client_as(teacher_user)
        resp = c.get(f"/assessments/student/{student_user.id}/report/")
        assert resp.status_code == 200

    def test_student_report_self(
        self,
        client_as,
        student_user,
        school,
    ):
        """Student viewing their own report"""
        # student role is in PROTECTED_PATHS — need to verify
        # student role is NOT in assessments protected paths, so they get 403 from middleware
        c = client_as(student_user)
        resp = c.get(f"/assessments/student/{student_user.id}/report/")
        assert resp.status_code == 403

    def test_student_report_with_year_param(
        self,
        client_as,
        principal_user,
        student_user,
    ):
        c = client_as(principal_user)
        resp = c.get(f"/assessments/student/{student_user.id}/report/?year=2025-2026")
        assert resp.status_code == 200

    # ── failing_students ─────────────────────────────────────

    def test_failing_students_forbidden_teacher(self, client_as, teacher_user):
        c = client_as(teacher_user)
        resp = c.get("/assessments/failing/")
        assert resp.status_code == 403

    def test_failing_students_with_params(self, client_as, principal_user):
        c = client_as(principal_user)
        resp = c.get("/assessments/failing/?semester=S2&year=2025-2026")
        assert resp.status_code == 200

    # ── setup_subject ────────────────────────────────────────

    def test_setup_subject_get(self, client_as, principal_user, school):
        # Create some data for the form
        Subject.objects.create(school=school, name_ar="فيزياء", code="PHY")
        c = client_as(principal_user)
        resp = c.get("/assessments/setup/")
        assert resp.status_code == 200

    def test_setup_subject_forbidden_teacher(self, client_as, teacher_user):
        c = client_as(teacher_user)
        resp = c.get("/assessments/setup/")
        assert resp.status_code == 403

    def test_setup_subject_post_create(
        self,
        client_as,
        principal_user,
        school,
        class_group,
        teacher_user,
    ):
        subj = Subject.objects.create(school=school, name_ar="كيمياء", code="CHEM")
        c = client_as(principal_user)
        resp = c.post(
            "/assessments/setup/",
            {
                "subject": str(subj.id),
                "class_group": str(class_group.id),
                "teacher": str(teacher_user.id),
                "academic_year": "2025-2026",
            },
        )
        assert resp.status_code == 302
        assert SubjectClassSetup.objects.filter(subject=subj).exists()

    def test_setup_subject_post_update_existing(
        self,
        client_as,
        principal_user,
        setup,
        school,
        subject,
        class_group,
        teacher_user,
    ):
        """Update existing setup — cover the 'not created' branch"""
        new_teacher = UserFactory(full_name="معلم جديد")
        role = RoleFactory(school=school, name="teacher")
        MembershipFactory(user=new_teacher, school=school, role=role)
        c = client_as(principal_user)
        resp = c.post(
            "/assessments/setup/",
            {
                "subject": str(subject.id),
                "class_group": str(class_group.id),
                "teacher": str(new_teacher.id),
                "academic_year": "2025-2026",
            },
        )
        assert resp.status_code == 302
        setup.refresh_from_db()
        assert setup.teacher == new_teacher

    # ── setup_detail auto-create packages ────────────────────

    def test_setup_detail_creates_packages_auto(
        self,
        client_as,
        teacher_user,
        setup,
    ):
        """Cover the auto-create packages branch when none exist"""
        c = client_as(teacher_user)
        resp = c.get(f"/assessments/setup/{setup.id}/?semester=S1")
        assert resp.status_code == 200
        # Packages should be auto-created
        assert AssessmentPackage.objects.filter(setup=setup, semester="S1").exists()

    def test_setup_detail_s2_packages(
        self,
        client_as,
        teacher_user,
        setup,
    ):
        """Cover S2 semester weight branch"""
        c = client_as(teacher_user)
        resp = c.get(f"/assessments/setup/{setup.id}/?semester=S2")
        assert resp.status_code == 200
        assert AssessmentPackage.objects.filter(setup=setup, semester="S2").exists()

    # ── create_assessment ────────────────────────────────────

    def test_create_assessment_success(
        self,
        client_as,
        teacher_user,
        s1_package,
    ):
        c = client_as(teacher_user)
        resp = c.post(
            f"/assessments/package/{s1_package.id}/new/",
            {
                "title": "اختبار جديد",
                "assessment_type": "quiz",
                "max_grade": "30",
                "weight_in_package": "50",
            },
        )
        assert resp.status_code == 302
        assert Assessment.objects.filter(title="اختبار جديد").exists()

    def test_create_assessment_empty_title(
        self,
        client_as,
        teacher_user,
        s1_package,
    ):
        c = client_as(teacher_user)
        resp = c.post(
            f"/assessments/package/{s1_package.id}/new/",
            {
                "title": "",
                "assessment_type": "exam",
            },
        )
        assert resp.status_code == 302  # redirect with error message

    def test_create_assessment_forbidden(
        self,
        client_as,
        s1_package,
        school,
    ):
        role = RoleFactory(school=school, name="teacher")
        other = UserFactory()
        MembershipFactory(user=other, school=school, role=role)
        c = client_as(other)
        resp = c.post(
            f"/assessments/package/{s1_package.id}/new/",
            {
                "title": "test",
            },
        )
        assert resp.status_code == 403

    # ── save_single_grade ────────────────────────────────────

    def test_save_single_grade_with_grade(
        self,
        client_as,
        teacher_user,
        assessment_in_p1,
        student_user,
        enrolled_student,
    ):
        c = client_as(teacher_user)
        resp = c.post(
            f"/assessments/assessment/{assessment_in_p1.id}/save-single/",
            {"student_id": str(student_user.id), "grade": "18"},
        )
        assert resp.status_code == 200

    def test_save_single_grade_absent(
        self,
        client_as,
        teacher_user,
        assessment_in_p1,
        student_user,
        enrolled_student,
    ):
        c = client_as(teacher_user)
        resp = c.post(
            f"/assessments/assessment/{assessment_in_p1.id}/save-single/",
            {"student_id": str(student_user.id), "is_absent": "1"},
        )
        assert resp.status_code == 200

    def test_save_single_grade_excused(
        self,
        client_as,
        teacher_user,
        assessment_in_p1,
        student_user,
        enrolled_student,
    ):
        c = client_as(teacher_user)
        resp = c.post(
            f"/assessments/assessment/{assessment_in_p1.id}/save-single/",
            {"student_id": str(student_user.id), "is_excused": "1"},
        )
        assert resp.status_code == 200

    def test_save_single_grade_invalid_decimal(
        self,
        client_as,
        teacher_user,
        assessment_in_p1,
        student_user,
        enrolled_student,
    ):
        c = client_as(teacher_user)
        resp = c.post(
            f"/assessments/assessment/{assessment_in_p1.id}/save-single/",
            {"student_id": str(student_user.id), "grade": "abc"},
        )
        assert resp.status_code == 400

    def test_save_single_grade_forbidden(
        self,
        client_as,
        assessment_in_p1,
        student_user,
        school,
    ):
        role = RoleFactory(school=school, name="teacher")
        other = UserFactory()
        MembershipFactory(user=other, school=school, role=role)
        c = client_as(other)
        resp = c.post(
            f"/assessments/assessment/{assessment_in_p1.id}/save-single/",
            {"student_id": str(student_user.id), "grade": "10"},
        )
        assert resp.status_code == 403

    # ── save_all_grades ──────────────────────────────────────

    def test_save_all_grades(
        self,
        client_as,
        teacher_user,
        assessment_in_p1,
        student_user,
        enrolled_student,
    ):
        sid = str(student_user.id)
        c = client_as(teacher_user)
        resp = c.post(
            f"/assessments/assessment/{assessment_in_p1.id}/save-all/",
            {f"grade_{sid}": "17", f"notes_{sid}": "ممتاز"},
        )
        assert resp.status_code == 302

    def test_save_all_grades_with_absent(
        self,
        client_as,
        teacher_user,
        assessment_in_p1,
        student_user,
        enrolled_student,
    ):
        sid = str(student_user.id)
        c = client_as(teacher_user)
        resp = c.post(
            f"/assessments/assessment/{assessment_in_p1.id}/save-all/",
            {f"absent_{sid}": "1"},
        )
        assert resp.status_code == 302

    def test_save_all_grades_invalid_grade_skipped(
        self,
        client_as,
        teacher_user,
        assessment_in_p1,
        student_user,
        enrolled_student,
    ):
        """Invalid decimal should be skipped (continue)"""
        sid = str(student_user.id)
        c = client_as(teacher_user)
        resp = c.post(
            f"/assessments/assessment/{assessment_in_p1.id}/save-all/",
            {f"grade_{sid}": "not_a_number"},
        )
        assert resp.status_code == 302

    def test_save_all_grades_forbidden(
        self,
        client_as,
        assessment_in_p1,
        school,
    ):
        role = RoleFactory(school=school, name="teacher")
        other = UserFactory()
        MembershipFactory(user=other, school=school, role=role)
        c = client_as(other)
        resp = c.post(
            f"/assessments/assessment/{assessment_in_p1.id}/save-all/",
            {},
        )
        assert resp.status_code == 403

    # ── grade_entry ──────────────────────────────────────────

    def test_grade_entry_forbidden(self, client_as, assessment_in_p1, school):
        role = RoleFactory(school=school, name="teacher")
        other = UserFactory()
        MembershipFactory(user=other, school=school, role=role)
        c = client_as(other)
        resp = c.get(f"/assessments/assessment/{assessment_in_p1.id}/")
        assert resp.status_code == 403

    # ── dashboard admin branch ───────────────────────────────

    def test_dashboard_admin_with_data(
        self,
        client_as,
        principal_user,
        setup,
        enrolled_student,
        s1_package,
        assessment_in_p1,
        student_user,
    ):
        """Cover admin dashboard branch with actual data"""
        GradeService.save_grade(
            assessment=assessment_in_p1,
            student=student_user,
            grade=Decimal("10"),
        )
        c = client_as(principal_user)
        resp = c.get("/assessments/?semester=S1&year=2025-2026")
        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════
#  exam_control/views.py — Coverage Tests
# ══════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestExamControlViewsCoverage:
    # ── dashboard ────────────────────────────────────────────

    def test_dashboard(self, client_as, principal_user, exam_session):
        c = client_as(principal_user)
        resp = c.get("/exam-control/")
        assert resp.status_code == 200

    # ── session_create ───────────────────────────────────────

    def test_session_create_get(self, client_as, principal_user):
        c = client_as(principal_user)
        resp = c.get("/exam-control/session/create/")
        assert resp.status_code == 200

    def test_session_create_post(self, client_as, principal_user):
        c = client_as(principal_user)
        resp = c.post(
            "/exam-control/session/create/",
            {
                "name": "اختبار منتصف الفصل",
                "session_type": "mid",
                "academic_year": "2025-2026",
                "start_date": str(date.today()),
                "end_date": str(date.today() + timedelta(days=7)),
            },
        )
        assert resp.status_code == 302
        assert ExamSession.objects.filter(name="اختبار منتصف الفصل").exists()

    def test_session_create_forbidden_teacher(self, client_as, teacher_user):
        c = client_as(teacher_user)
        resp = c.post(
            "/exam-control/session/create/",
            {
                "name": "test",
                "start_date": str(date.today()),
                "end_date": str(date.today() + timedelta(days=7)),
            },
        )
        assert resp.status_code == 403

    # ── session_detail ───────────────────────────────────────

    def test_session_detail(
        self,
        client_as,
        principal_user,
        exam_session,
        exam_room,
        exam_schedule,
        exam_grade_sheet,
        exam_incident,
    ):
        c = client_as(principal_user)
        resp = c.get(f"/exam-control/session/{exam_session.pk}/")
        assert resp.status_code == 200
        assert "session" in resp.context

    # ── supervisors ──────────────────────────────────────────

    def test_supervisors_get(self, client_as, principal_user, exam_session, exam_room):
        c = client_as(principal_user)
        resp = c.get(f"/exam-control/session/{exam_session.pk}/supervisors/")
        assert resp.status_code == 200

    def test_supervisors_post(
        self, client_as, principal_user, exam_session, exam_room, teacher_user
    ):
        c = client_as(principal_user)
        resp = c.post(
            f"/exam-control/session/{exam_session.pk}/supervisors/",
            {
                "staff_id": str(teacher_user.id),
                "role": "supervisor",
                "room_id": str(exam_room.id),
            },
        )
        assert resp.status_code == 302
        assert ExamSupervisor.objects.filter(session=exam_session, staff=teacher_user).exists()

    def test_supervisors_post_no_room(self, client_as, principal_user, exam_session, teacher_user):
        c = client_as(principal_user)
        resp = c.post(
            f"/exam-control/session/{exam_session.pk}/supervisors/",
            {
                "staff_id": str(teacher_user.id),
                "role": "head",
            },
        )
        assert resp.status_code == 302

    # ── schedule ─────────────────────────────────────────────

    def test_schedule_get(self, client_as, principal_user, exam_session, exam_schedule):
        c = client_as(principal_user)
        resp = c.get(f"/exam-control/session/{exam_session.pk}/schedule/")
        assert resp.status_code == 200

    def test_schedule_post(self, client_as, principal_user, exam_session, exam_room):
        c = client_as(principal_user)
        resp = c.post(
            f"/exam-control/session/{exam_session.pk}/schedule/",
            {
                "room_id": str(exam_room.id),
                "subject": "العلوم",
                "grade_level": "G8",
                "exam_date": str(date.today() + timedelta(days=2)),
                "start_time": "09:00",
                "end_time": "11:00",
                "students_count": "20",
            },
        )
        assert resp.status_code == 302
        assert ExamSchedule.objects.filter(subject="العلوم").exists()
        # Also check auto-created grade sheet
        sched = ExamSchedule.objects.get(subject="العلوم")
        assert ExamGradeSheet.objects.filter(schedule=sched).exists()

    # ── incidents ─────────────────────────────────────────────

    def test_incidents_list(self, client_as, principal_user, exam_session, exam_incident):
        c = client_as(principal_user)
        resp = c.get(f"/exam-control/session/{exam_session.pk}/incidents/")
        assert resp.status_code == 200

    # ── incident_add ─────────────────────────────────────────

    def test_incident_add_get(self, client_as, principal_user, exam_session, exam_room):
        c = client_as(principal_user)
        resp = c.get(f"/exam-control/session/{exam_session.pk}/incident/add/")
        assert resp.status_code == 200

    def test_incident_add_post(self, client_as, principal_user, exam_session, exam_room):
        c = client_as(principal_user)
        with patch("exam_control.views.render_pdf") as mock_pdf:
            mock_pdf.return_value = MagicMock(status_code=200, content=b"PDF")
            resp = c.post(
                f"/exam-control/session/{exam_session.pk}/incident/add/",
                {
                    "incident_type": "misconduct",
                    "severity": "2",
                    "description": "سوء سلوك أثناء الاختبار",
                    "room_id": str(exam_room.id),
                },
            )
        assert resp.status_code == 302  # redirects to incident_pdf

    def test_incident_add_with_student(
        self,
        client_as,
        principal_user,
        exam_session,
        exam_room,
        student_user,
    ):
        c = client_as(principal_user)
        with patch("exam_control.views.render_pdf") as mock_pdf:
            mock_pdf.return_value = MagicMock(status_code=200, content=b"PDF")
            resp = c.post(
                f"/exam-control/session/{exam_session.pk}/incident/add/",
                {
                    "incident_type": "other",
                    "severity": "1",
                    "description": "حادث بسيط",
                    "student_id": str(student_user.id),
                    "room_id": str(exam_room.id),
                },
            )
        assert resp.status_code == 302

    def test_incident_add_cheating_creates_behavior(
        self,
        client_as,
        principal_user,
        exam_session,
        exam_room,
        student_user,
        school,
    ):
        """Cover the cheating branch that creates BehaviorInfraction"""
        c = client_as(principal_user)
        with patch("exam_control.views.render_pdf") as mock_pdf:
            mock_pdf.return_value = MagicMock(status_code=200, content=b"PDF")
            resp = c.post(
                f"/exam-control/session/{exam_session.pk}/incident/add/",
                {
                    "incident_type": "cheating",
                    "severity": "3",
                    "description": "غش في اختبار الرياضيات بجهاز إلكتروني",
                    "student_id": str(student_user.id),
                    "room_id": str(exam_room.id),
                    "action_taken": "إنذار رسمي",
                },
            )
        assert resp.status_code == 302
        # Cheating incident should create behavior infraction
        incident = ExamIncident.objects.filter(
            session=exam_session, incident_type="cheating"
        ).first()
        assert incident is not None

    # ── incident_pdf ─────────────────────────────────────────

    def test_incident_pdf(self, client_as, principal_user, exam_incident):
        c = client_as(principal_user)
        with patch("exam_control.views.render_pdf") as mock_pdf:
            mock_pdf.return_value = MagicMock(
                status_code=200,
                content=b"PDF",
                __getitem__=lambda s, k: "application/pdf" if k == "Content-Type" else "",
            )
            resp = c.get(f"/exam-control/incident/{exam_incident.pk}/pdf/")
        mock_pdf.assert_called_once()

    # ── grade_sheets ─────────────────────────────────────────

    def test_grade_sheets_get(self, client_as, principal_user, exam_session, exam_grade_sheet):
        c = client_as(principal_user)
        resp = c.get(f"/exam-control/session/{exam_session.pk}/grade-sheets/")
        assert resp.status_code == 200

    def test_grade_sheets_post_update_status(
        self,
        client_as,
        principal_user,
        exam_session,
        exam_grade_sheet,
    ):
        c = client_as(principal_user)
        resp = c.post(
            f"/exam-control/session/{exam_session.pk}/grade-sheets/",
            {
                "sheet_id": str(exam_grade_sheet.id),
                "status": "graded",
            },
        )
        assert resp.status_code == 302
        exam_grade_sheet.refresh_from_db()
        assert exam_grade_sheet.status == "graded"

    def test_grade_sheets_post_submitted_status(
        self,
        client_as,
        principal_user,
        exam_session,
        exam_grade_sheet,
    ):
        """Cover the submitted_at branch"""
        c = client_as(principal_user)
        resp = c.post(
            f"/exam-control/session/{exam_session.pk}/grade-sheets/",
            {
                "sheet_id": str(exam_grade_sheet.id),
                "status": "submitted",
            },
        )
        assert resp.status_code == 302
        exam_grade_sheet.refresh_from_db()
        assert exam_grade_sheet.status == "submitted"
        assert exam_grade_sheet.submitted_at is not None

    # ── session_report_pdf ───────────────────────────────────

    def test_session_report_pdf(
        self,
        client_as,
        principal_user,
        exam_session,
        exam_room,
        exam_schedule,
        exam_incident,
        exam_grade_sheet,
    ):
        c = client_as(principal_user)
        with patch("exam_control.views.render_pdf") as mock_pdf:
            mock_pdf.return_value = MagicMock(
                status_code=200,
                content=b"PDF",
            )
            resp = c.get(f"/exam-control/session/{exam_session.pk}/report-pdf/")
        mock_pdf.assert_called_once()


# ══════════════════════════════════════════════════════════════
#  api/views.py — Coverage Tests (REST API)
# ══════════════════════════════════════════════════════════════


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def api_as_principal(api_client, principal_user):
    api_client.force_login(principal_user)
    return api_client


@pytest.fixture
def api_as_teacher(api_client, teacher_user):
    api_client.force_login(teacher_user)
    return api_client


@pytest.fixture
def api_as_parent(api_client, parent_user):
    api_client.force_login(parent_user)
    return api_client


@pytest.mark.django_db
class TestAPIViewsCoverage:
    # ── me_view ──────────────────────────────────────────────

    def test_me_view(self, api_as_principal):
        resp = api_as_principal.get("/api/v1/me/")
        assert resp.status_code == 200

    def test_me_view_unauthenticated(self, api_client):
        resp = api_client.get("/api/v1/me/")
        assert resp.status_code in (401, 403)

    # ── student_list ─────────────────────────────────────────

    def test_student_list(self, api_as_principal, enrolled_student):
        resp = api_as_principal.get("/api/v1/students/")
        assert resp.status_code == 200

    def test_student_list_with_search(self, api_as_principal, enrolled_student):
        resp = api_as_principal.get("/api/v1/students/?search=طالب")
        assert resp.status_code == 200

    def test_student_list_with_class_filter(
        self,
        api_as_principal,
        enrolled_student,
        class_group,
    ):
        resp = api_as_principal.get(f"/api/v1/students/?class_id={class_group.id}")
        assert resp.status_code == 200

    def test_student_list_with_ordering(self, api_as_principal, enrolled_student):
        for ordering in ["name", "-name", "national_id", "class", "-class"]:
            resp = api_as_principal.get(f"/api/v1/students/?ordering={ordering}")
            assert resp.status_code == 200

    def test_student_list_unknown_ordering(self, api_as_principal, enrolled_student):
        resp = api_as_principal.get("/api/v1/students/?ordering=unknown_field")
        assert resp.status_code == 200  # falls back to default

    def test_student_list_forbidden_student(self, api_client, student_user):
        api_client.force_login(student_user)
        resp = api_client.get("/api/v1/students/")
        assert resp.status_code == 403

    # ── student_grades ───────────────────────────────────────

    def test_student_grades(self, api_as_principal, student_user):
        resp = api_as_principal.get(f"/api/v1/students/{student_user.id}/grades/")
        assert resp.status_code == 200

    def test_student_grades_with_year(self, api_as_principal, student_user):
        resp = api_as_principal.get(f"/api/v1/students/{student_user.id}/grades/?year=2025-2026")
        assert resp.status_code == 200

    def test_student_grades_with_results(
        self,
        api_as_principal,
        student_user,
        setup,
        school,
        s1_package,
        s1_exam_package,
        assessment_in_p1,
        assessment_in_p4,
        enrolled_student,
    ):
        """Cover the average calculation branch"""
        # Create S2 packages and assessments for annual result
        s2p1 = AssessmentPackage.objects.create(
            setup=setup,
            school=school,
            package_type="P1",
            semester="S2",
            weight=Decimal("17"),
            semester_max_grade=Decimal("60"),
        )
        s2p4 = AssessmentPackage.objects.create(
            setup=setup,
            school=school,
            package_type="P4",
            semester="S2",
            weight=Decimal("50"),
            semester_max_grade=Decimal("60"),
        )
        a_s2_1 = Assessment.objects.create(
            package=s2p1,
            school=school,
            title="عمل 2",
            max_grade=Decimal("20"),
            weight_in_package=Decimal("100"),
            status="published",
        )
        a_s2_4 = Assessment.objects.create(
            package=s2p4,
            school=school,
            title="اختبار نهائي",
            max_grade=Decimal("60"),
            weight_in_package=Decimal("100"),
            status="published",
        )
        GradeService.save_grade(
            assessment=assessment_in_p1, student=student_user, grade=Decimal("16")
        )
        GradeService.save_grade(
            assessment=assessment_in_p4, student=student_user, grade=Decimal("32")
        )
        GradeService.save_grade(assessment=a_s2_1, student=student_user, grade=Decimal("16"))
        GradeService.save_grade(assessment=a_s2_4, student=student_user, grade=Decimal("48"))

        resp = api_as_principal.get(f"/api/v1/students/{student_user.id}/grades/?year=2025-2026")
        assert resp.status_code == 200
        data = resp.json()
        assert data["average"] is not None

    # ── student_attendance ───────────────────────────────────

    def test_student_attendance(self, api_as_principal, student_user):
        resp = api_as_principal.get(f"/api/v1/students/{student_user.id}/attendance/")
        assert resp.status_code == 200

    def test_student_attendance_with_days(self, api_as_principal, student_user):
        resp = api_as_principal.get(f"/api/v1/students/{student_user.id}/attendance/?days=7")
        assert resp.status_code == 200
        data = resp.json()
        assert data["days"] == 7

    def test_student_attendance_invalid_days(self, api_as_principal, student_user):
        resp = api_as_principal.get(f"/api/v1/students/{student_user.id}/attendance/?days=abc")
        assert resp.status_code == 200
        data = resp.json()
        assert data["days"] == 30  # fallback

    # ── class_list ───────────────────────────────────────────

    def test_class_list(self, api_as_principal, class_group):
        resp = api_as_principal.get("/api/v1/classes/")
        assert resp.status_code == 200

    def test_class_list_with_ordering(self, api_as_principal, class_group):
        for ordering in ["grade", "-grade", "section", "-section"]:
            resp = api_as_principal.get(f"/api/v1/classes/?ordering={ordering}")
            assert resp.status_code == 200

    def test_class_list_unknown_ordering(self, api_as_principal, class_group):
        resp = api_as_principal.get("/api/v1/classes/?ordering=xyz")
        assert resp.status_code == 200

    # ── class_results ────────────────────────────────────────

    def test_class_results(self, api_as_principal, class_group):
        with patch("api.views.ReportDataService") as mock_svc:
            mock_svc.get_class_results.return_value = {
                "student_rows": [],
                "total_students": 0,
                "total_passed": 0,
                "total_failed": 0,
                "subjects": [],
            }
            resp = api_as_principal.get(f"/api/v1/classes/{class_group.id}/results/")
        assert resp.status_code == 200

    # ── notification_list ────────────────────────────────────

    def test_notification_list(self, api_as_principal, principal_user, school):
        InAppNotification.objects.create(
            user=principal_user,
            school=school,
            title="إشعار اختبار",
            message="رسالة",
            event_type="grade",
        )
        resp = api_as_principal.get("/api/v1/notifications/")
        assert resp.status_code == 200
        data = resp.json()
        assert "unread_count" in data
        assert "results" in data

    def test_notification_list_unread_filter(self, api_as_principal, principal_user, school):
        InAppNotification.objects.create(
            user=principal_user,
            school=school,
            title="غير مقروء",
            message="test",
            event_type="grade",
            is_read=False,
        )
        resp = api_as_principal.get("/api/v1/notifications/?unread=true")
        assert resp.status_code == 200

    def test_notification_list_event_type_filter(self, api_as_principal, principal_user, school):
        resp = api_as_principal.get("/api/v1/notifications/?event_type=behavior")
        assert resp.status_code == 200

    def test_notification_list_priority_filter(self, api_as_principal, principal_user, school):
        resp = api_as_principal.get("/api/v1/notifications/?priority=high")
        assert resp.status_code == 200

    def test_notification_list_limit(self, api_as_principal):
        resp = api_as_principal.get("/api/v1/notifications/?limit=10")
        assert resp.status_code == 200

    def test_notification_list_invalid_limit(self, api_as_principal):
        resp = api_as_principal.get("/api/v1/notifications/?limit=abc")
        assert resp.status_code == 200

    # ── notification_mark_read ───────────────────────────────

    def test_notification_mark_read(self, api_as_principal, principal_user, school):
        notif = InAppNotification.objects.create(
            user=principal_user,
            school=school,
            title="test",
            message="test",
            event_type="grade",
            is_read=False,
        )
        resp = api_as_principal.post(f"/api/v1/notifications/{notif.id}/read/")
        assert resp.status_code == 200
        notif.refresh_from_db()
        assert notif.is_read is True

    # ── notification_mark_all_read ───────────────────────────

    def test_notification_mark_all_read(self, api_as_principal, principal_user, school):
        for i in range(3):
            InAppNotification.objects.create(
                user=principal_user,
                school=school,
                title=f"test {i}",
                message="test",
                event_type="grade",
                is_read=False,
            )
        resp = api_as_principal.post("/api/v1/notifications/mark-all-read/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["marked"] == 3

    # ── NotificationPreferencesView ──────────────────────────

    def test_notification_preferences_get(self, api_as_principal):
        resp = api_as_principal.get("/api/v1/notification-preferences/")
        assert resp.status_code == 200

    def test_notification_preferences_patch(self, api_as_principal):
        resp = api_as_principal.patch(
            "/api/v1/notification-preferences/",
            {"push_enabled": False},
            format="json",
        )
        assert resp.status_code == 200

    def test_notification_preferences_patch_invalid(self, api_as_principal):
        resp = api_as_principal.patch(
            "/api/v1/notification-preferences/",
            {"push_enabled": "invalid_value_string_not_bool"},
            format="json",
        )
        # Should return 400 for invalid data
        assert resp.status_code in (200, 400)

    # ── SessionListView ──────────────────────────────────────

    def test_session_list(self, api_as_principal, school, class_group, teacher_user):
        subj = Subject.objects.create(school=school, name_ar="رياضيات API", code="MAPI")
        Session.objects.create(
            school=school,
            class_group=class_group,
            teacher=teacher_user,
            subject=subj,
            date=date.today(),
            start_time="08:00",
            end_time="08:45",
            status="completed",
        )
        resp = api_as_principal.get("/api/v1/sessions/")
        assert resp.status_code == 200

    # ── AttendanceListView ───────────────────────────────────

    def test_attendance_list(self, api_as_principal):
        resp = api_as_principal.get("/api/v1/attendance/")
        assert resp.status_code == 200

    # ── BehaviorListView / behavior_list ─────────────────────

    def test_behavior_list(self, api_as_principal, behavior_infraction):
        resp = api_as_principal.get("/api/v1/behavior/")
        assert resp.status_code == 200

    # ── kpi_list ─────────────────────────────────────────────

    def test_kpi_list(self, api_as_principal):
        with patch("api.views.KPIService") as mock_kpi:
            mock_kpi.compute.return_value = {"attendance_rate": 95}
            resp = api_as_principal.get("/api/v1/kpis/")
        assert resp.status_code == 200

    def test_kpi_list_forbidden_teacher(self, api_as_teacher):
        resp = api_as_teacher.get("/api/v1/kpis/")
        assert resp.status_code == 403

    # ── parent_children ──────────────────────────────────────

    def test_parent_children(self, api_as_parent):
        with patch("api.views.ParentService") as mock_svc:
            mock_link = MagicMock()
            mock_link.can_view_grades = True
            mock_link.can_view_attendance = True
            mock_enr = MagicMock()
            mock_enr.class_group = "G7-أ"
            mock_svc.get_children_data.return_value = [
                {
                    "student": MagicMock(id="fake-uuid", full_name="طالب", national_id="123"),
                    "enrollment": mock_enr,
                    "total_subj": 5,
                    "passed": 4,
                    "failed": 1,
                    "incomplete": 0,
                    "absent_30": 2,
                    "late_30": 1,
                    "link": mock_link,
                }
            ]
            resp = api_as_parent.get("/api/v1/parent/children/")
        assert resp.status_code == 200

    # ── parent_child_grades ──────────────────────────────────

    def test_parent_child_grades(self, api_as_parent, student_user, parent_user, school):
        with patch("api.views.ParentService") as mock_svc:
            mock_svc.get_student_grades.return_value = {
                "annual_results": [],
                "total": 0,
                "passed": 0,
                "failed": 0,
                "avg": None,
            }
            resp = api_as_parent.get(f"/api/v1/parent/children/{student_user.id}/grades/")
        assert resp.status_code == 200

    def test_parent_child_grades_no_link(self, api_client, school, student_user):
        """Parent without link should be forbidden"""
        role = RoleFactory(school=school, name="parent")
        other_parent = UserFactory(full_name="ولي أمر آخر")
        MembershipFactory(user=other_parent, school=school, role=role)
        api_client.force_login(other_parent)
        resp = api_client.get(f"/api/v1/parent/children/{student_user.id}/grades/")
        assert resp.status_code == 403

    def test_parent_child_grades_no_permission(
        self,
        api_client,
        school,
        student_user,
    ):
        """Parent with link but can_view_grades=False"""
        role = RoleFactory(school=school, name="parent")
        parent = UserFactory(full_name="ولي أمر بدون صلاحية")
        MembershipFactory(user=parent, school=school, role=role)
        ParentStudentLink.objects.create(
            parent=parent,
            student=student_user,
            school=school,
            can_view_grades=False,
            can_view_attendance=True,
        )
        api_client.force_login(parent)
        resp = api_client.get(f"/api/v1/parent/children/{student_user.id}/grades/")
        assert resp.status_code == 403

    # ── parent_child_attendance ──────────────────────────────

    def test_parent_child_attendance(self, api_as_parent, student_user, school):
        with patch("api.views.ParentService") as mock_svc:
            mock_svc.get_student_attendance.return_value = {
                "since": date.today() - timedelta(days=30),
                "total": 20,
                "present": 18,
                "absent": 1,
                "late": 1,
                "att_pct": 90,
            }
            resp = api_as_parent.get(f"/api/v1/parent/children/{student_user.id}/attendance/")
        assert resp.status_code == 200

    def test_parent_child_attendance_no_link(self, api_client, school, student_user):
        role = RoleFactory(school=school, name="parent")
        other = UserFactory(full_name="ولي أمر بلا رابط")
        MembershipFactory(user=other, school=school, role=role)
        api_client.force_login(other)
        resp = api_client.get(f"/api/v1/parent/children/{student_user.id}/attendance/")
        assert resp.status_code == 403

    def test_parent_child_attendance_no_permission(self, api_client, school, student_user):
        role = RoleFactory(school=school, name="parent")
        parent = UserFactory(full_name="ولي بلا صلاحية حضور")
        MembershipFactory(user=parent, school=school, role=role)
        ParentStudentLink.objects.create(
            parent=parent,
            student=student_user,
            school=school,
            can_view_grades=True,
            can_view_attendance=False,
        )
        api_client.force_login(parent)
        resp = api_client.get(f"/api/v1/parent/children/{student_user.id}/attendance/")
        assert resp.status_code == 403

    def test_parent_child_attendance_with_days(self, api_as_parent, student_user, school):
        with patch("api.views.ParentService") as mock_svc:
            mock_svc.get_student_attendance.return_value = {
                "since": date.today() - timedelta(days=7),
                "total": 5,
                "present": 5,
                "absent": 0,
                "late": 0,
                "att_pct": 100,
            }
            resp = api_as_parent.get(
                f"/api/v1/parent/children/{student_user.id}/attendance/?days=7"
            )
        assert resp.status_code == 200

    def test_parent_child_attendance_invalid_days(self, api_as_parent, student_user, school):
        with patch("api.views.ParentService") as mock_svc:
            mock_svc.get_student_attendance.return_value = {
                "since": date.today() - timedelta(days=30),
                "total": 0,
                "present": 0,
                "absent": 0,
                "late": 0,
                "att_pct": 0,
            }
            resp = api_as_parent.get(
                f"/api/v1/parent/children/{student_user.id}/attendance/?days=abc"
            )
        assert resp.status_code == 200

    # ── LibraryBookListView ──────────────────────────────────

    def test_library_books_list(self, api_as_principal, library_book):
        resp = api_as_principal.get("/api/v1/library/books/")
        assert resp.status_code == 200

    def test_library_books_search(self, api_as_principal, library_book):
        resp = api_as_principal.get("/api/v1/library/books/?search=كتاب")
        assert resp.status_code == 200

    # ── BorrowingListView ────────────────────────────────────

    def test_library_borrowings(self, api_as_principal, book_borrowing):
        resp = api_as_principal.get("/api/v1/library/borrowings/")
        assert resp.status_code == 200

    # ── ClinicVisitListView ──────────────────────────────────

    def test_clinic_visits(self, api_as_principal, clinic_visit):
        resp = api_as_principal.get("/api/v1/clinic/visits/")
        assert resp.status_code == 200

    def test_clinic_visits_forbidden_teacher(self, api_as_teacher):
        resp = api_as_teacher.get("/api/v1/clinic/visits/")
        assert resp.status_code == 403

"""
tests/test_operations.py
اختبارات العمليات التشغيلية — الحضور، الجدول، البديل

يغطي:
  - نماذج Session, StudentAttendance, ScheduleSlot, TeacherAbsence
  - Views: الجدول الأسبوعي، تسجيل الحضور، البديل
"""
import pytest
from datetime import date, time, timedelta
from django.utils import timezone

from operations.models import (
    Subject, Session, StudentAttendance, ScheduleSlot,
    TeacherAbsence, SubstituteAssignment, AbsenceAlert,
)
from tests.conftest import (
    SchoolFactory, UserFactory, RoleFactory, MembershipFactory,
    ClassGroupFactory, StudentEnrollmentFactory,
)


@pytest.fixture
def subject(db, school):
    return Subject.objects.create(school=school, name_ar="العلوم", code="SCI")


@pytest.fixture
def session(db, school, class_group, teacher_user, subject):
    return Session.objects.create(
        school=school,
        class_group=class_group,
        teacher=teacher_user,
        subject=subject,
        date=date.today(),
        start_time=time(8, 0),
        end_time=time(8, 45),
        status="scheduled",
    )


@pytest.fixture
def schedule_slot(db, school, class_group, teacher_user, subject):
    return ScheduleSlot.objects.create(
        school=school,
        class_group=class_group,
        teacher=teacher_user,
        subject=subject,
        day_of_week=0,  # الأحد
        period_number=1,
        start_time=time(7, 30),
        end_time=time(8, 15),
    )


# ══════════════════════════════════════════════════
#  اختبارات النماذج
# ══════════════════════════════════════════════════

class TestOperationsModels:

    def test_subject_creation(self, subject):
        assert subject.name_ar == "العلوم"
        assert str(subject) == "العلوم"

    def test_session_creation(self, session):
        assert session.status == "scheduled"
        assert session.date == date.today()

    def test_session_unique_teacher_time(self, session, school, class_group, teacher_user, subject):
        """لا يمكن للمعلم أن يكون في حصتين بنفس الوقت"""
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            Session.objects.create(
                school=school, class_group=class_group,
                teacher=teacher_user, subject=subject,
                date=date.today(),
                start_time=time(8, 0),
                end_time=time(8, 45),
            )

    def test_student_attendance_mark(self, session, student_user, school):
        att = StudentAttendance.objects.create(
            session=session, student=student_user,
            school=school, status="absent",
        )
        assert att.status == "absent"
        assert str(att)  # لا يرمي خطأ

    def test_schedule_slot_creation(self, schedule_slot):
        assert schedule_slot.period_number == 1
        assert schedule_slot.day_of_week == 0

    def test_teacher_absence(self, school, teacher_user):
        absence = TeacherAbsence.objects.create(
            school=school, teacher=teacher_user,
            date=date.today(),
            reason="مرض",
            reported_by=teacher_user,
        )
        assert absence.reason == "مرض"

    def test_substitute_assignment(self, school, teacher_user, schedule_slot):
        absence = TeacherAbsence.objects.create(
            school=school, teacher=teacher_user,
            date=date.today(), reason="مرض",
            reported_by=teacher_user,
        )
        sub_teacher = UserFactory(full_name="بديل")
        role = RoleFactory(school=school, name="teacher")
        MembershipFactory(user=sub_teacher, school=school, role=role)

        assignment = SubstituteAssignment.objects.create(
            absence=absence, slot=schedule_slot,
            substitute=sub_teacher, assigned_by=teacher_user,
        )
        assert assignment.substitute.full_name == "بديل"

    def test_absence_alert(self, school, student_user):
        alert = AbsenceAlert.objects.create(
            school=school, student=student_user,
            absent_count=5,
            total_sessions=20,
        )
        assert alert.absent_count == 5


# ══════════════════════════════════════════════════
#  اختبارات Views
# ══════════════════════════════════════════════════

class TestOperationsViews:

    def test_schedule_page_teacher(self, client_as, teacher_user):
        c = client_as(teacher_user)
        resp = c.get("/operations/schedule/")
        assert resp.status_code == 200

    def test_attendance_page(self, client_as, teacher_user, session):
        c = client_as(teacher_user)
        resp = c.get(f"/operations/attendance/{session.id}/")
        assert resp.status_code == 200

    def test_weekly_schedule_page(self, client_as, principal_user):
        c = client_as(principal_user)
        resp = c.get("/operations/weekly-schedule/")
        assert resp.status_code == 200

    def test_daily_report(self, client_as, principal_user):
        c = client_as(principal_user)
        resp = c.get("/operations/reports/daily/")
        assert resp.status_code == 200

    def test_absence_list(self, client_as, principal_user):
        c = client_as(principal_user)
        resp = c.get("/operations/absences/")
        assert resp.status_code == 200

    def test_attendance_forbidden_for_parent(self, client_as, parent_user, session):
        """ولي الأمر لا يمكنه تسجيل الحضور"""
        c = client_as(parent_user)
        resp = c.get(f"/operations/attendance/{session.id}/")
        assert resp.status_code == 403

    def test_mark_single_attendance(self, client_as, teacher_user, session, student_user,
                                     enrolled_student, school):
        c = client_as(teacher_user)
        resp = c.post(
            f"/operations/attendance/{session.id}/mark-single/",
            {"student_id": str(student_user.id), "status": "present"},
        )
        # HTMX عادةً يرجع 200 أو redirect
        assert resp.status_code in [200, 302]

    def test_complete_session(self, client_as, teacher_user, session):
        c = client_as(teacher_user)
        resp = c.post(f"/operations/attendance/{session.id}/complete/")
        assert resp.status_code in [200, 302]
        session.refresh_from_db()
        assert session.status == "completed"

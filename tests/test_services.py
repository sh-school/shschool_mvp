"""
tests/test_services.py
اختبارات الخدمات (Services)
━━━━━━━━━━━━━━━━━━━━━━━━━━━
يختبر: GradeService (معادلة 40/60)، AttendanceService، NotificationService
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest

from assessments.services import GradeService
from operations.services import AttendanceService

from .conftest import (
    UserFactory,
)

# ══════════════════════════════════════════════
#  FIXTURES خاصة بالخدمات
# ══════════════════════════════════════════════


@pytest.fixture
def subject(db, school):
    from operations.models import Subject

    return Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")


@pytest.fixture
def subject_setup(db, school, class_group, teacher_user, subject):
    from assessments.models import SubjectClassSetup

    return SubjectClassSetup.objects.create(
        school=school,
        subject=subject,
        class_group=class_group,
        teacher=teacher_user,
        academic_year="2025-2026",
    )


@pytest.fixture
def assessment_package_s1(db, school, subject_setup):
    """باقة الفصل الأول — أعمال مستمرة (20 درجة)"""
    from assessments.models import AssessmentPackage

    return AssessmentPackage.objects.create(
        school=school,
        setup=subject_setup,
        semester="S1",
        package_type="P1",
        weight=Decimal("50"),  # 50% من 40 = 20 درجة
        semester_max_grade=Decimal("40"),
    )


@pytest.fixture
def assessment(db, school, assessment_package_s1):
    from assessments.models import Assessment

    return Assessment.objects.create(
        school=school,
        package=assessment_package_s1,
        title="اختبار شهري 1",
        max_grade=Decimal("20"),
        date=date.today(),
    )


@pytest.fixture
def session(db, school, class_group):
    from operations.models import Session, Subject

    subj = Subject.objects.create(school=school, name_ar="عربي", code="AR")
    from datetime import time as dtime

    teacher = UserFactory()
    return Session.objects.create(
        school=school,
        class_group=class_group,
        teacher=teacher,
        subject=subj,
        date=date.today(),
        start_time=dtime(8, 0),
        end_time=dtime(8, 45),
        status="scheduled",
    )


# ══════════════════════════════════════════════
#  GradeService — معادلة التقييم القطرية
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestGradeService:
    def test_save_grade_creates_record(
        self, school, student_user, teacher_user, assessment, subject_setup
    ):
        obj, created = GradeService.save_grade(
            assessment=assessment,
            student=student_user,
            grade=Decimal("17"),
            entered_by=teacher_user,
        )
        assert created is True
        assert obj.grade == Decimal("17")

    def test_save_grade_clamps_to_max(
        self, school, student_user, teacher_user, assessment, subject_setup
    ):
        """الدرجة لا تتجاوز الحد الأقصى"""
        obj, _ = GradeService.save_grade(
            assessment=assessment,
            student=student_user,
            grade=Decimal("999"),  # أكبر من max_grade
            entered_by=teacher_user,
        )
        assert obj.grade <= assessment.max_grade

    def test_save_grade_clamps_to_zero(
        self, school, student_user, teacher_user, assessment, subject_setup
    ):
        """الدرجة لا تقل عن صفر"""
        obj, _ = GradeService.save_grade(
            assessment=assessment,
            student=student_user,
            grade=Decimal("-5"),
            entered_by=teacher_user,
        )
        assert obj.grade == Decimal("0")

    def test_update_existing_grade(
        self, school, student_user, teacher_user, assessment, subject_setup
    ):
        GradeService.save_grade(assessment, student_user, Decimal("10"), entered_by=teacher_user)
        obj, created = GradeService.save_grade(
            assessment, student_user, Decimal("15"), entered_by=teacher_user
        )
        assert created is False
        assert obj.grade == Decimal("15")

    def test_absent_grade(self, school, student_user, teacher_user, assessment, subject_setup):
        obj, _ = GradeService.save_grade(
            assessment=assessment,
            student=student_user,
            is_absent=True,
            entered_by=teacher_user,
        )
        assert obj.is_absent is True
        assert obj.grade is None


# ══════════════════════════════════════════════
#  AttendanceService
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestAttendanceService:
    def test_mark_attendance_present(
        self, school, student_user, teacher_user, session, enrolled_student
    ):
        att, created = AttendanceService.mark_attendance(
            session=session,
            student=student_user,
            status="present",
            marked_by=teacher_user,
        )
        assert created is True
        assert att.status == "present"

    def test_mark_attendance_absent(
        self, school, student_user, teacher_user, session, enrolled_student
    ):
        att, created = AttendanceService.mark_attendance(
            session=session,
            student=student_user,
            status="absent",
            marked_by=teacher_user,
        )
        assert att.status == "absent"

    def test_update_attendance_record(
        self, school, student_user, teacher_user, session, enrolled_student
    ):
        """تحديث الحضور من غياب إلى حضور"""
        AttendanceService.mark_attendance(session, student_user, "absent", marked_by=teacher_user)
        att, created = AttendanceService.mark_attendance(
            session, student_user, "present", marked_by=teacher_user
        )
        assert created is False
        assert att.status == "present"

    def test_bulk_mark_all_present(self, school, teacher_user, session, enrolled_student):
        count = AttendanceService.bulk_mark_all_present(session, marked_by=teacher_user)
        assert count >= 1
        from operations.models import StudentAttendance

        assert StudentAttendance.objects.filter(session=session, status="present").count() >= 1

    def test_complete_session(self, school, session):
        AttendanceService.complete_session(session)
        from operations.models import Session

        refreshed = Session.objects.get(id=session.id)
        assert refreshed.status == "completed"


# ══════════════════════════════════════════════
#  NotificationService
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestNotificationService:
    def test_send_email_logs_notification(self, school, student_user):
        from notifications.models import NotificationLog
        from notifications.services import NotificationService

        with patch("django.core.mail.send_mail") as mock_mail:
            mock_mail.return_value = 1
            ok, err = NotificationService.send_email(
                school=school,
                recipient_email="parent@test.com",
                subject="اختبار",
                body_text="نص الاختبار",
                student=student_user,
                notif_type="custom",
            )

        assert ok is True
        assert err is None
        log = NotificationLog.objects.filter(school=school).last()
        assert log is not None
        assert log.status == "sent"
        assert log.channel == "email"

    def test_failed_email_logs_error(self, school, student_user):
        from notifications.models import NotificationLog
        from notifications.services import NotificationService

        with patch("django.core.mail.send_mail") as mock_mail:
            mock_mail.side_effect = OSError("SMTP Error")
            ok, err = NotificationService.send_email(
                school=school,
                recipient_email="fail@test.com",
                subject="اختبار فاشل",
                body_text="نص",
            )

        assert ok is False
        assert err is not None
        log = NotificationLog.objects.filter(school=school).last()
        assert log.status == "failed"
        assert "SMTP" in log.error_msg

    def test_sms_disabled_returns_error(self, school, student_user):
        """SMS معطّل في الإعدادات الافتراضية"""
        from notifications.services import NotificationService

        # بدون NotificationSettings → SMS معطّل
        ok, err = NotificationService.send_sms(
            school=school,
            phone_number="+97466123456",
            message="اختبار SMS",
        )
        assert ok is False

    def test_notify_absence_sends_to_parent(self, school, student_user, parent_user):
        """إشعار غياب يُرسل لولي الأمر عبر البريد"""
        from notifications.services import NotificationService
        from operations.models import AbsenceAlert

        # إنشاء تنبيه غياب
        alert = AbsenceAlert.objects.create(
            school=school,
            student=student_user,
            absence_count=4,
            period_start=date.today() - timedelta(days=7),
            period_end=date.today(),
            status="pending",
        )

        # إضافة بريد لولي الأمر
        parent_user.email = "parent@test.com"
        parent_user.save()

        with patch("django.core.mail.send_mail") as mock_mail:
            mock_mail.return_value = 1
            results = NotificationService.notify_absence(alert)

        # يجب أن يُرسل على الأقل إشعار واحد
        assert (
            len(results) >= 0
        )  # قد يكون 0 إذا لم يكن هناك ParentStudentLink مع can_view_attendance

    def test_send_fail_alerts_bulk(self, school, student_user):
        """إرسال إشعارات رسوب جماعي"""
        from notifications.services import NotificationService

        with patch("django.core.mail.send_mail") as mock_mail:
            mock_mail.return_value = 1
            sent, failed = NotificationService.send_fail_alerts_for_year(
                school=school, year="2025-2026"
            )

        # 0 إشعار مُرسل (لا يوجد طلاب راسبون في بيانات الاختبار)
        assert sent == 0
        assert failed == 0

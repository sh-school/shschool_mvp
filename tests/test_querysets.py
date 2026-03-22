"""
tests/test_querysets.py
اختبارات Custom QuerySets — operations / quality / notifications
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
يغطي:
  - operations/querysets.py : SessionQuerySet, AttendanceQuerySet, AbsenceAlertQuerySet
  - quality/querysets.py    : ProcedureQuerySet, DomainQuerySet
  - notifications/querysets.py : InAppNotificationQuerySet, NotificationLogQuerySet

ملاحظة: هذه القرايست ليست مرتبطة بـ model managers — تُختبر بـ direct instantiation
"""
import pytest
from datetime import date, time, timedelta
from django.utils import timezone

from operations.models import Subject, Session, StudentAttendance, AbsenceAlert
from notifications.models import InAppNotification, NotificationLog
from operations.querysets import (
    SessionQuerySet, AttendanceQuerySet, AbsenceAlertQuerySet,
)
from quality.querysets import ProcedureQuerySet, DomainQuerySet
from notifications.querysets import InAppNotificationQuerySet, NotificationLogQuerySet

from tests.conftest import (
    SchoolFactory, UserFactory, RoleFactory, MembershipFactory, ClassGroupFactory,
)


# ══════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════

def make_teacher(school):
    role = RoleFactory(school=school, name="teacher")
    user = UserFactory(full_name="معلم")
    MembershipFactory(user=user, school=school, role=role)
    return user


def make_student(school):
    role = RoleFactory(school=school, name="student")
    user = UserFactory(full_name="طالب")
    MembershipFactory(user=user, school=school, role=role)
    return user


def make_subject(school):
    return Subject.objects.create(school=school, name_ar="رياضيات", code="MATH")


_session_time_offset = 0


def make_session(school, teacher, class_group, subject,
                 session_date=None, status="scheduled"):
    global _session_time_offset
    _session_time_offset += 1
    # وقت مختلف لكل حصة لتجنب تعارض UniqueConstraint
    start_hour = 7 + (_session_time_offset % 8)
    return Session.objects.create(
        school=school,
        class_group=class_group,
        teacher=teacher,
        subject=subject,
        date=session_date or date.today(),
        start_time=time(start_hour, 0),
        end_time=time(start_hour, 45),
        status=status,
    )


def make_attendance(school, session, student, status="present"):
    return StudentAttendance.objects.create(
        school=school,
        session=session,
        student=student,
        status=status,
    )


def session_qs(school):
    """إنشاء SessionQuerySet مرتبط بـ Session model"""
    return SessionQuerySet(model=Session, using="default").filter(school=school)


def attendance_qs(school):
    return AttendanceQuerySet(model=StudentAttendance, using="default").filter(school=school)


def alert_qs(school):
    return AbsenceAlertQuerySet(model=AbsenceAlert, using="default").filter(school=school)


def procedure_qs(school):
    from quality.models import OperationalProcedure
    return ProcedureQuerySet(model=OperationalProcedure, using="default").filter(school=school)


def domain_qs(school):
    from quality.models import OperationalDomain
    return DomainQuerySet(model=OperationalDomain, using="default").filter(school=school)


def notif_qs():
    return InAppNotificationQuerySet(model=InAppNotification, using="default")


def log_qs(school):
    return NotificationLogQuerySet(model=NotificationLog, using="default").filter(school=school)


# ══════════════════════════════════════════════════════════════
#  SessionQuerySet
# ══════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestSessionQuerySet:

    def test_today_returns_todays_sessions(self, school):
        teacher     = make_teacher(school)
        cg          = ClassGroupFactory(school=school)
        subj        = make_subject(school)
        s_today = make_session(school, teacher, cg, subj, date.today())
        s_old   = make_session(school, teacher, cg, subj,
                               date.today() - timedelta(days=5))
        qs = session_qs(school).today()
        assert s_today in qs
        assert s_old   not in qs

    def test_this_week_returns_within_week(self, school):
        teacher = make_teacher(school)
        cg      = ClassGroupFactory(school=school)
        subj    = make_subject(school)
        today   = date.today()
        # this_week() يُعيد الاثنين–الجمعة — نستخدم يوم الاثنين دائماً
        monday  = today - timedelta(days=today.weekday())
        s_week  = make_session(school, teacher, cg, subj, monday)
        s_old   = make_session(school, teacher, cg, subj, today - timedelta(days=14))
        qs = session_qs(school).this_week()
        assert s_week in qs
        assert s_old  not in qs

    def test_date_range(self, school):
        teacher = make_teacher(school)
        cg      = ClassGroupFactory(school=school)
        subj    = make_subject(school)
        today   = date.today()
        s_in  = make_session(school, teacher, cg, subj, today)
        s_out = make_session(school, teacher, cg, subj, today - timedelta(days=30))
        qs = session_qs(school).date_range(today - timedelta(days=7), today)
        assert s_in  in qs
        assert s_out not in qs

    def test_for_teacher(self, school):
        t1   = make_teacher(school)
        t2   = make_teacher(school)
        cg   = ClassGroupFactory(school=school)
        subj = make_subject(school)
        s1 = make_session(school, t1, cg, subj)
        s2 = make_session(school, t2, cg, subj)
        qs = session_qs(school).for_teacher(t1)
        assert s1 in qs
        assert s2 not in qs

    def test_for_class(self, school):
        t    = make_teacher(school)
        cg1  = ClassGroupFactory(school=school)
        cg2  = ClassGroupFactory(school=school)
        subj = make_subject(school)
        s1 = make_session(school, t, cg1, subj)
        s2 = make_session(school, t, cg2, subj)
        qs = session_qs(school).for_class(cg1)
        assert s1 in qs
        assert s2 not in qs

    def test_for_subject(self, school):
        t     = make_teacher(school)
        cg    = ClassGroupFactory(school=school)
        subj1 = Subject.objects.create(school=school, name_ar="علوم", code="SCI")
        subj2 = Subject.objects.create(school=school, name_ar="تاريخ", code="HIS")
        s1 = make_session(school, t, cg, subj1)
        s2 = make_session(school, t, cg, subj2)
        qs = session_qs(school).for_subject(subj1)
        assert s1 in qs
        assert s2 not in qs

    def test_status_filters(self, school):
        t    = make_teacher(school)
        cg   = ClassGroupFactory(school=school)
        subj = make_subject(school)
        s_comp  = make_session(school, t, cg, subj, status="completed")
        s_sched = make_session(school, t, cg, subj, status="scheduled")
        s_canc  = make_session(school, t, cg, subj, status="cancelled")
        s_prog  = make_session(school, t, cg, subj, status="in_progress")

        assert s_comp  in session_qs(school).completed()
        assert s_sched in session_qs(school).scheduled()
        assert s_canc  in session_qs(school).cancelled()
        assert s_prog  in session_qs(school).in_progress()

    def test_with_details_no_error(self, school):
        t    = make_teacher(school)
        cg   = ClassGroupFactory(school=school)
        subj = make_subject(school)
        make_session(school, t, cg, subj)
        sessions = list(session_qs(school).with_details())
        assert len(sessions) >= 1

    def test_attendance_summary_annotates(self, school):
        t       = make_teacher(school)
        student = make_student(school)
        cg      = ClassGroupFactory(school=school)
        subj    = make_subject(school)
        sess    = make_session(school, t, cg, subj)
        make_attendance(school, sess, student, "present")
        qs = session_qs(school).attendance_summary()
        s  = qs.get(id=sess.id)
        assert s.att_present == 1
        assert s.att_absent  == 0


# ══════════════════════════════════════════════════════════════
#  AttendanceQuerySet
# ══════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestAttendanceQuerySet:

    @pytest.fixture(autouse=True)
    def setup(self, db, school):
        self.school  = school
        self.teacher = make_teacher(school)
        self.student = make_student(school)
        self.cg      = ClassGroupFactory(school=school)
        self.subj    = make_subject(school)
        self.sess    = make_session(school, self.teacher, self.cg, self.subj)

    def test_for_student(self):
        s2 = make_student(self.school)
        a1 = make_attendance(self.school, self.sess, self.student, "present")
        a2 = make_attendance(self.school, self.sess, s2, "present")
        qs = attendance_qs(self.school).for_student(self.student)
        assert a1 in qs
        assert a2 not in qs

    def test_for_session(self):
        sess2 = make_session(self.school, self.teacher, self.cg, self.subj)
        a1 = make_attendance(self.school, self.sess,  self.student, "present")
        a2 = make_attendance(self.school, sess2, self.student, "present")
        qs = attendance_qs(self.school).for_session(self.sess)
        assert a1 in qs
        assert a2 not in qs

    def test_for_class(self):
        a = make_attendance(self.school, self.sess, self.student, "present")
        qs = attendance_qs(self.school).for_class(self.cg)
        assert a in qs

    def test_status_filters(self):
        s2, s3, s4 = make_student(self.school), make_student(self.school), make_student(self.school)
        a_p = make_attendance(self.school, self.sess, self.student, "present")
        a_a = make_attendance(self.school, self.sess, s2, "absent")
        a_l = make_attendance(self.school, self.sess, s3, "late")
        a_e = make_attendance(self.school, self.sess, s4, "excused")
        assert a_p in attendance_qs(self.school).present()
        assert a_a in attendance_qs(self.school).absent()
        assert a_l in attendance_qs(self.school).late()
        assert a_e in attendance_qs(self.school).excused()

    def test_unexcused(self):
        a = make_attendance(self.school, self.sess, self.student, "absent")
        qs = attendance_qs(self.school).unexcused()
        assert a in qs

    def test_date_range(self):
        today = date.today()
        sess_old = make_session(self.school, self.teacher, self.cg, self.subj,
                                today - timedelta(days=30))
        a_now = make_attendance(self.school, self.sess, self.student, "present")
        a_old = make_attendance(self.school, sess_old, self.student, "present")
        qs = attendance_qs(self.school).date_range(today - timedelta(days=7), today)
        assert a_now in qs
        assert a_old not in qs

    def test_last_days(self):
        a = make_attendance(self.school, self.sess, self.student, "present")
        assert a in attendance_qs(self.school).last_days(30)

    def test_with_details_no_error(self):
        make_attendance(self.school, self.sess, self.student, "present")
        rows = list(attendance_qs(self.school).with_details())
        assert len(rows) >= 1

    def test_rate_for_student(self):
        make_attendance(self.school, self.sess, self.student, "present")
        sess2 = make_session(self.school, self.teacher, self.cg, self.subj)
        make_attendance(self.school, sess2, self.student, "absent")
        rate = attendance_qs(self.school).rate_for_student(self.student)
        assert rate["total"]   == 2
        assert rate["present"] == 1
        assert rate["rate"]    == 50.0

    def test_rate_for_student_no_records(self):
        new_student = make_student(self.school)
        rate = attendance_qs(self.school).rate_for_student(new_student)
        assert rate["rate"] == 0

    def test_absence_streak(self):
        a = make_attendance(self.school, self.sess, self.student, "absent")
        qs = attendance_qs(self.school).absence_streak(self.student)
        assert a in qs


# ══════════════════════════════════════════════════════════════
#  AbsenceAlertQuerySet
# ══════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestAbsenceAlertQuerySet:

    def test_pending_and_notified(self, school):
        student = make_student(school)
        today = date.today()
        a1 = AbsenceAlert.objects.create(
            school=school, student=student, status="pending",
            absence_count=3, period_start=today, period_end=today,
        )
        a2 = AbsenceAlert.objects.create(
            school=school, student=student, status="notified",
            absence_count=5, period_start=today, period_end=today,
        )
        assert a1 in alert_qs(school).pending()
        assert a2 in alert_qs(school).notified()

    def test_for_student(self, school):
        s1 = make_student(school)
        s2 = make_student(school)
        today = date.today()
        a1 = AbsenceAlert.objects.create(
            school=school, student=s1, status="pending",
            absence_count=3, period_start=today, period_end=today,
        )
        a2 = AbsenceAlert.objects.create(
            school=school, student=s2, status="pending",
            absence_count=3, period_start=today, period_end=today,
        )
        qs = alert_qs(school).for_student(s1)
        assert a1 in qs
        assert a2 not in qs

    def test_with_details_no_error(self, school):
        student = make_student(school)
        today = date.today()
        AbsenceAlert.objects.create(
            school=school, student=student, status="pending",
            absence_count=3, period_start=today, period_end=today,
        )
        rows = list(alert_qs(school).with_details())
        assert len(rows) == 1


# ══════════════════════════════════════════════════════════════
#  ProcedureQuerySet
# ══════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestProcedureQuerySet:

    # رقم متتالي لتجنب تعارض UniqueConstraint
    _proc_seq = 0

    def _make_proc(self, school, teacher, status="Not Started", deadline=None):
        from quality.models import (
            OperationalDomain, OperationalTarget,
            OperationalIndicator, OperationalProcedure,
        )
        TestProcedureQuerySet._proc_seq += 1
        seq = TestProcedureQuerySet._proc_seq
        domain = OperationalDomain.objects.create(
            school=school,
            name=f"المجال {seq}",
            academic_year="2025-2026",
        )
        target = OperationalTarget.objects.create(
            domain=domain, number=str(seq), text="هدف تجريبي",
        )
        indicator = OperationalIndicator.objects.create(
            target=target, number=str(seq), text="مؤشر تجريبي",
        )
        return OperationalProcedure.objects.create(
            school=school,
            indicator=indicator,
            number=str(seq),
            text="نص الإجراء",
            executor_norm="تجريبي",
            status=status,
            executor_user=teacher,
            deadline=deadline or (date.today() + timedelta(days=30)),
        )

    def test_status_filters(self, school):
        t = make_teacher(school)
        p_ns = self._make_proc(school, t, "Not Started")
        p_ip = self._make_proc(school, t, "In Progress")
        p_pr = self._make_proc(school, t, "Pending Review")
        p_co = self._make_proc(school, t, "Completed")
        p_ca = self._make_proc(school, t, "Cancelled")

        assert p_ns in procedure_qs(school).not_started()
        assert p_ip in procedure_qs(school).in_progress()
        assert p_pr in procedure_qs(school).pending_review()
        assert p_co in procedure_qs(school).completed()
        assert p_ca in procedure_qs(school).cancelled()

    def test_active_excludes_done_and_cancelled(self, school):
        t = make_teacher(school)
        p_act = self._make_proc(school, t, "In Progress")
        p_co  = self._make_proc(school, t, "Completed")
        p_ca  = self._make_proc(school, t, "Cancelled")

        qs = procedure_qs(school).active()
        assert p_act in qs
        assert p_co  not in qs
        assert p_ca  not in qs

    def test_overdue(self, school):
        t = make_teacher(school)
        p_over = self._make_proc(school, t, "In Progress",
                                 deadline=date.today() - timedelta(days=1))
        p_ok   = self._make_proc(school, t, "In Progress",
                                 deadline=date.today() + timedelta(days=10))
        assert p_over in procedure_qs(school).overdue()
        assert p_ok   not in procedure_qs(school).overdue()

    def test_due_soon(self, school):
        t = make_teacher(school)
        p_soon  = self._make_proc(school, t, "Not Started",
                                  deadline=date.today() + timedelta(days=3))
        p_later = self._make_proc(school, t, "Not Started",
                                  deadline=date.today() + timedelta(days=30))
        assert p_soon  in procedure_qs(school).due_soon(7)
        assert p_later not in procedure_qs(school).due_soon(7)

    def test_due_this_month(self, school):
        t = make_teacher(school)
        p = self._make_proc(school, t, "Not Started", deadline=date.today())
        assert p in procedure_qs(school).due_this_month()

    def test_for_executor(self, school):
        t1 = make_teacher(school)
        t2 = make_teacher(school)
        p1 = self._make_proc(school, t1)
        p2 = self._make_proc(school, t2)
        assert p1 in procedure_qs(school).for_executor(t1)
        assert p2 not in procedure_qs(school).for_executor(t1)

    def test_completion_rate(self, school):
        t = make_teacher(school)
        self._make_proc(school, t, "Completed")
        self._make_proc(school, t, "Not Started")
        rate = procedure_qs(school).completion_rate()
        assert rate == 50.0

    def test_completion_rate_empty(self, school):
        rate = procedure_qs(school).completion_rate()
        assert rate == 0.0

    def test_summary_by_status(self, school):
        t = make_teacher(school)
        self._make_proc(school, t, "Completed")
        self._make_proc(school, t, "In Progress")
        summary = list(procedure_qs(school).summary_by_status())
        statuses = [s["status"] for s in summary]
        assert "Completed"   in statuses
        assert "In Progress" in statuses

    def test_executor_ranking(self, school):
        t = make_teacher(school)
        self._make_proc(school, t, "Completed")
        self._make_proc(school, t, "Completed")
        ranking = list(procedure_qs(school).executor_ranking())
        assert len(ranking) == 1
        assert ranking[0]["done"] == 2

    def test_with_details_no_error(self, school):
        t = make_teacher(school)
        self._make_proc(school, t)
        rows = list(procedure_qs(school).with_details())
        assert len(rows) == 1


# ══════════════════════════════════════════════════════════════
#  DomainQuerySet
# ══════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestDomainQuerySet:

    _domain_seq = 0

    def _make_domain(self, school):
        from quality.models import OperationalDomain
        TestDomainQuerySet._domain_seq += 1
        return OperationalDomain.objects.create(
            school=school,
            name=f"مجال {TestDomainQuerySet._domain_seq}",
            academic_year="2025-2026",
        )

    def test_with_progress_annotates(self, school):
        self._make_domain(school)
        rows = list(domain_qs(school).with_progress())
        assert len(rows) >= 1
        assert hasattr(rows[0], "total_procs")
        assert hasattr(rows[0], "completed_procs")

    def test_with_all_prefetches(self, school):
        self._make_domain(school)
        rows = list(domain_qs(school).with_all())
        assert len(rows) >= 1


# ══════════════════════════════════════════════════════════════
#  InAppNotificationQuerySet
# ══════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestInAppNotificationQuerySet:

    @pytest.fixture(autouse=True)
    def setup(self, db, school):
        self.school = school
        self.user   = make_student(school)

    def _make_notif(self, user=None, school=None, is_read=False,
                    priority="medium", event_type="general", days_ago=0):
        n = InAppNotification.objects.create(
            school=school or self.school,
            user=user or self.user,
            title="إشعار",
            body="رسالة",
            is_read=is_read,
            priority=priority,
            event_type=event_type,
        )
        if days_ago:
            InAppNotification.objects.filter(id=n.id).update(
                created_at=timezone.now() - timedelta(days=days_ago)
            )
            n.refresh_from_db()
        return n

    def test_for_user(self):
        u2 = make_student(self.school)
        n1 = self._make_notif()
        n2 = self._make_notif(user=u2)
        qs = notif_qs().for_user(self.user)
        assert n1 in qs
        assert n2 not in qs

    def test_for_school(self):
        school2 = SchoolFactory()
        n1 = self._make_notif()
        u2 = UserFactory()
        n2 = InAppNotification.objects.create(
            school=school2, user=u2, title="إشعار", body="رسالة",
            is_read=False, priority="low", event_type="general",
        )
        assert n1 in notif_qs().for_school(self.school)
        assert n2 not in notif_qs().for_school(self.school)

    def test_unread_and_read(self):
        n_unread = self._make_notif(is_read=False)
        n_read   = self._make_notif(is_read=True)
        assert n_unread in notif_qs().unread()
        assert n_read   in notif_qs().read()
        assert n_unread not in notif_qs().read()

    def test_priority_filter(self):
        n_high = self._make_notif(priority="high")
        n_low  = self._make_notif(priority="low")
        qs = notif_qs().priority("high")
        assert n_high in qs
        assert n_low  not in qs

    def test_urgent(self):
        n_urgent = self._make_notif(priority="urgent")
        n_high   = self._make_notif(priority="high")
        n_medium = self._make_notif(priority="medium")
        qs = notif_qs().urgent()
        assert n_urgent in qs
        assert n_high   in qs
        assert n_medium not in qs

    def test_event_type(self):
        n_abs = self._make_notif(event_type="absence")
        n_gen = self._make_notif(event_type="general")
        qs = notif_qs().event_type("absence")
        assert n_abs in qs
        assert n_gen not in qs

    def test_recent(self):
        n_new = self._make_notif(days_ago=1)
        n_old = self._make_notif(days_ago=30)
        qs = notif_qs().recent(7)
        assert n_new in qs
        assert n_old not in qs

    def test_unread_count_for_user(self):
        self._make_notif(is_read=False)
        self._make_notif(is_read=False)
        self._make_notif(is_read=True)
        count = notif_qs().unread_count_for_user(self.user)
        assert count == 2

    def test_mark_all_read(self):
        self._make_notif(is_read=False)
        self._make_notif(is_read=False)
        updated = notif_qs().mark_all_read(self.user)
        assert updated == 2
        assert InAppNotification.objects.filter(user=self.user, is_read=False).count() == 0


# ══════════════════════════════════════════════════════════════
#  NotificationLogQuerySet
# ══════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestNotificationLogQuerySet:

    @pytest.fixture(autouse=True)
    def setup(self, db, school):
        self.school  = school
        self.student = make_student(school)

    def _make_log(self, status="sent", channel="email", student=None):
        return NotificationLog.objects.create(
            school=self.school,
            student=student or self.student,
            channel=channel,
            status=status,
            recipient="test@school.qa",
            body="رسالة اختبار",
        )

    def test_status_filters(self):
        l_sent    = self._make_log(status="sent")
        l_failed  = self._make_log(status="failed")
        l_pending = self._make_log(status="pending")
        assert l_sent    in log_qs(self.school).sent()
        assert l_failed  in log_qs(self.school).failed()
        assert l_pending in log_qs(self.school).pending()

    def test_channel_filter(self):
        l_email = self._make_log(channel="email")
        l_sms   = self._make_log(channel="sms")
        assert l_email in log_qs(self.school).channel("email")
        assert l_sms   not in log_qs(self.school).channel("email")

    def test_for_student(self):
        s2 = make_student(self.school)
        l1 = self._make_log()
        l2 = self._make_log(student=s2)
        qs = log_qs(self.school).for_student(self.student)
        assert l1 in qs
        assert l2 not in qs

    def test_this_month(self):
        l = self._make_log()
        assert l in log_qs(self.school).this_month()

    def test_failure_summary(self):
        self._make_log(status="failed", channel="email")
        self._make_log(status="failed", channel="email")
        self._make_log(status="failed", channel="sms")
        summary = list(log_qs(self.school).failure_summary())
        assert len(summary) >= 1
        assert summary[0]["channel"] == "email"
        assert summary[0]["count"]   == 2

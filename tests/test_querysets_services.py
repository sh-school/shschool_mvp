"""
tests/test_querysets_services.py
اختبارات شاملة لـ:
  - quality/querysets.py    : ProcedureQuerySet, DomainQuerySet
  - notifications/querysets.py : InAppNotificationQuerySet, NotificationLogQuerySet
  - quality/services.py    : QualityService
  - quality/employee_evaluation.py : EmployeeEvaluation, EvaluationCycle

(كانت تشمل أيضاً operations/querysets.py: SessionQuerySet وAttendanceQuerySet
وAbsenceAlertQuerySet — حُذفت مع الوحدة نفسها؛ لم تكن مربوطةً بأيّ نموذج ولا
يستعملها أحدٌ غير هذا الملفّ.)
"""

from datetime import date, timedelta

import pytest
from django.utils import timezone

from notifications.models import InAppNotification, NotificationLog
from notifications.querysets import (
    InAppNotificationQuerySet,
    NotificationLogQuerySet,
)
from quality.models import (
    EmployeeEvaluation,
    EvaluationCycle,
    ExecutorMapping,
    OperationalDomain,
    OperationalIndicator,
    OperationalProcedure,
    OperationalTarget,
    QualityCommitteeMember,
)
from quality.querysets import DomainQuerySet, ProcedureQuerySet
from quality.services import QualityService
from tests.conftest import SchoolFactory, UserFactory

# ══════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════


_proc_seq = 0


def _make_procedure(
    school, indicator, user=None, status="In Progress", executor_norm="معلم", deadline=None
):
    global _proc_seq
    _proc_seq += 1
    return OperationalProcedure.objects.create(
        school=school,
        indicator=indicator,
        number=f"P-{_proc_seq:04d}",
        text=f"إجراء {_proc_seq}",
        executor_norm=executor_norm,
        executor_user=user,
        status=status,
        deadline=deadline,
    )


def _make_quality_hierarchy(school, domain_name="مجال 1"):
    """Creates Domain -> Target -> Indicator and returns all three."""
    domain = OperationalDomain.objects.create(
        school=school,
        name=domain_name,
        order=1,
    )
    target = OperationalTarget.objects.create(
        domain=domain,
        number="T-1",
        text="هدف 1",
    )
    indicator = OperationalIndicator.objects.create(
        target=target,
        number="I-1",
        text="مؤشر 1",
    )
    return domain, target, indicator


# ══════════════════════════════════════════════════════════════
#  1. ProcedureQuerySet
# ══════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestProcedureQuerySet:
    @pytest.fixture(autouse=True)
    def setup(self, school, teacher_user):
        self.school = school
        self.user = teacher_user
        self.domain, self.target, self.indicator = _make_quality_hierarchy(
            school,
            "مجال اختبار الإجراءات",
        )
        self.qs = ProcedureQuerySet(
            model=OperationalProcedure,
            using="default",
        ).filter(school=school)

    def test_status_filters(self):
        p1 = _make_procedure(self.school, self.indicator, status="Not Started")
        p2 = _make_procedure(self.school, self.indicator, status="In Progress")
        p3 = _make_procedure(self.school, self.indicator, status="Pending Review")
        p4 = _make_procedure(self.school, self.indicator, status="Completed")
        p5 = _make_procedure(self.school, self.indicator, status="Cancelled")

        assert p1 in self.qs.not_started()
        assert p2 in self.qs.in_progress()
        assert p3 in self.qs.pending_review()
        assert p4 in self.qs.completed()
        assert p5 in self.qs.cancelled()

    def test_active(self):
        p_active = _make_procedure(self.school, self.indicator, status="In Progress")
        p_done = _make_procedure(self.school, self.indicator, status="Completed")
        p_cancel = _make_procedure(self.school, self.indicator, status="Cancelled")
        result = self.qs.active()
        assert p_active in result
        assert p_done not in result
        assert p_cancel not in result

    def test_overdue(self):
        yesterday = timezone.now().date() - timedelta(days=1)
        tomorrow = timezone.now().date() + timedelta(days=1)
        p_overdue = _make_procedure(
            self.school,
            self.indicator,
            status="In Progress",
            deadline=yesterday,
        )
        p_future = _make_procedure(
            self.school,
            self.indicator,
            status="In Progress",
            deadline=tomorrow,
        )
        result = self.qs.overdue()
        assert p_overdue in result
        assert p_future not in result

    def test_due_soon(self):
        today = timezone.now().date()
        in_3_days = today + timedelta(days=3)
        in_20_days = today + timedelta(days=20)
        p_soon = _make_procedure(
            self.school,
            self.indicator,
            status="Not Started",
            deadline=in_3_days,
        )
        p_far = _make_procedure(
            self.school,
            self.indicator,
            status="Not Started",
            deadline=in_20_days,
        )
        result = self.qs.due_soon(days=7)
        assert p_soon in result
        assert p_far not in result

    def test_due_this_month(self):
        today = timezone.now().date()
        this_month = today.replace(day=15)
        p = _make_procedure(
            self.school,
            self.indicator,
            status="In Progress",
            deadline=this_month,
        )
        result = self.qs.due_this_month()
        assert p in result

    def test_for_executor(self):
        p = _make_procedure(
            self.school,
            self.indicator,
            user=self.user,
        )
        result = self.qs.for_executor(self.user)
        assert p in result

    def test_for_domain(self):
        p = _make_procedure(self.school, self.indicator)
        result = self.qs.for_domain(self.domain)
        assert p in result

    def test_with_details(self):
        _make_procedure(self.school, self.indicator, user=self.user)
        result = self.qs.with_details()
        assert result.count() >= 1

    def test_completion_rate(self):
        _make_procedure(self.school, self.indicator, status="Completed")
        _make_procedure(self.school, self.indicator, status="Completed")
        _make_procedure(self.school, self.indicator, status="In Progress")
        _make_procedure(self.school, self.indicator, status="Not Started")
        rate = self.qs.completion_rate()
        assert rate == 50.0

    def test_completion_rate_empty(self):
        # No procedures yet for a fresh qs
        fresh_qs = ProcedureQuerySet(
            model=OperationalProcedure,
            using="default",
        ).filter(school__code="NONEXISTENT")
        assert fresh_qs.completion_rate() == 0.0

    def test_summary_by_status(self):
        _make_procedure(self.school, self.indicator, status="Completed")
        _make_procedure(self.school, self.indicator, status="Completed")
        _make_procedure(self.school, self.indicator, status="In Progress")
        result = list(self.qs.summary_by_status())
        statuses = {r["status"] for r in result}
        assert "Completed" in statuses

    def test_executor_ranking(self):
        _make_procedure(
            self.school,
            self.indicator,
            user=self.user,
            status="Completed",
        )
        _make_procedure(
            self.school,
            self.indicator,
            user=self.user,
            status="In Progress",
        )
        result = list(self.qs.executor_ranking())
        assert len(result) >= 1
        entry = [r for r in result if r["executor_user__id"] == self.user.pk]
        assert len(entry) == 1
        assert entry[0]["done"] == 1
        assert entry[0]["total"] == 2


# ══════════════════════════════════════════════════════════════
#  2. DomainQuerySet
# ══════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestDomainQuerySet:
    @pytest.fixture(autouse=True)
    def setup(self, school):
        self.school = school
        self.qs = DomainQuerySet(
            model=OperationalDomain,
            using="default",
        ).filter(school=school)

    def test_with_progress(self):
        domain, target, indicator = _make_quality_hierarchy(
            self.school,
            "مجال التقدم",
        )
        _make_procedure(self.school, indicator, status="Completed")
        _make_procedure(self.school, indicator, status="In Progress")

        result = self.qs.with_progress()
        d = result.get(pk=domain.pk)
        assert d.total_procedures == 2
        assert d.completed_procedures == 1

    def test_with_all(self):
        domain, target, indicator = _make_quality_hierarchy(
            self.school,
            "مجال الكل",
        )
        _make_procedure(self.school, indicator)
        result = self.qs.with_all()
        assert result.count() >= 1

    def test_with_progress_empty(self):
        domain = OperationalDomain.objects.create(
            school=self.school,
            name="مجال فارغ",
            order=99,
        )
        result = self.qs.with_progress()
        d = result.get(pk=domain.pk)
        assert d.total_procedures == 0
        assert d.completed_procedures == 0


# ══════════════════════════════════════════════════════════════
#  3. InAppNotificationQuerySet
# ══════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestInAppNotificationQuerySet:
    @pytest.fixture(autouse=True)
    def setup(self, school, teacher_user):
        self.school = school
        self.user = teacher_user
        self.qs = InAppNotificationQuerySet(
            model=InAppNotification,
            using="default",
        )

    def _notif(
        self, user=None, is_read=False, priority="medium", event_type="general", created_at=None
    ):
        n = InAppNotification.objects.create(
            user=user or self.user,
            school=self.school,
            title="إشعار اختبار",
            body="نص الإشعار",
            event_type=event_type,
            priority=priority,
            is_read=is_read,
        )
        if created_at:
            InAppNotification.objects.filter(pk=n.pk).update(created_at=created_at)
            n.refresh_from_db()
        return n

    def test_for_user(self):
        n1 = self._notif(user=self.user)
        other = UserFactory(full_name="آخر")
        n2 = self._notif(user=other)
        result = self.qs.for_user(self.user)
        assert n1 in result
        assert n2 not in result

    def test_for_school(self):
        n = self._notif()
        result = self.qs.for_school(self.school)
        assert n in result

    def test_unread_and_read(self):
        n_unread = self._notif(is_read=False)
        n_read = self._notif(is_read=True)
        assert n_unread in self.qs.unread()
        assert n_read in self.qs.read()
        assert n_unread not in self.qs.read()
        assert n_read not in self.qs.unread()

    def test_priority(self):
        n_med = self._notif(priority="medium")
        n_high = self._notif(priority="high")
        assert n_med in self.qs.priority("medium")
        assert n_high not in self.qs.priority("medium")

    def test_urgent(self):
        n_high = self._notif(priority="high")
        n_urgent = self._notif(priority="urgent")
        n_low = self._notif(priority="low")
        result = self.qs.urgent()
        assert n_high in result
        assert n_urgent in result
        assert n_low not in result

    def test_event_type(self):
        n = self._notif(event_type="behavior")
        result = self.qs.event_type("behavior")
        assert n in result

    def test_recent(self):
        n_recent = self._notif()
        old_date = timezone.now() - timedelta(days=30)
        n_old = self._notif(created_at=old_date)
        result = self.qs.recent(days=7)
        assert n_recent in result
        assert n_old not in result

    def test_unread_count_for_user(self):
        self._notif(is_read=False)
        self._notif(is_read=False)
        self._notif(is_read=True)
        count = self.qs.unread_count_for_user(self.user)
        assert count == 2

    def test_mark_all_read(self):
        self._notif(is_read=False)
        self._notif(is_read=False)
        updated = self.qs.mark_all_read(self.user)
        assert updated == 2
        assert self.qs.for_user(self.user).unread().count() == 0


# ══════════════════════════════════════════════════════════════
#  4. NotificationLogQuerySet
# ══════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestNotificationLogQuerySet:
    @pytest.fixture(autouse=True)
    def setup(self, school, student_user):
        self.school = school
        self.student = student_user
        self.qs = NotificationLogQuerySet(
            model=NotificationLog,
            using="default",
        ).filter(school=school)

    def _log(self, status="sent", channel="email", student=None, error_msg=""):
        return NotificationLog.objects.create(
            school=self.school,
            student=student or self.student,
            recipient="parent@test.qa",
            channel=channel,
            notif_type="absence_alert",
            subject="غياب",
            body="محتوى",
            status=status,
            error_msg=error_msg,
        )

    def test_sent(self):
        log = self._log(status="sent")
        assert log in self.qs.sent()

    def test_failed(self):
        log = self._log(status="failed")
        assert log in self.qs.failed()

    def test_pending(self):
        log = self._log(status="pending")
        assert log in self.qs.pending()

    def test_channel(self):
        log_email = self._log(channel="email")
        log_sms = self._log(channel="sms")
        assert log_email in self.qs.channel("email")
        assert log_sms not in self.qs.channel("email")

    def test_for_student(self):
        log = self._log()
        other = UserFactory(full_name="آخر")
        log2 = self._log(student=other)
        result = self.qs.for_student(self.student)
        assert log in result
        assert log2 not in result

    def test_this_month(self):
        log = self._log()
        result = self.qs.this_month()
        assert log in result

    def test_failure_summary(self):
        self._log(status="failed", channel="email", error_msg="timeout")
        self._log(status="failed", channel="email", error_msg="timeout")
        self._log(status="failed", channel="sms", error_msg="invalid number")
        result = list(self.qs.failure_summary())
        assert len(result) >= 2
        email_failures = [r for r in result if r["channel"] == "email"]
        assert email_failures[0]["count"] == 2


# ══════════════════════════════════════════════════════════════
#  5. QualityService
# ══════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestQualityService:
    @pytest.fixture(autouse=True)
    def setup(self, school, teacher_user):
        self.school = school
        self.user = teacher_user
        self.domain, self.target, self.indicator = _make_quality_hierarchy(
            school,
            "مجال الخدمات",
        )

    def test_get_plan_stats(self):
        _make_procedure(self.school, self.indicator, status="Completed")
        _make_procedure(self.school, self.indicator, status="Completed")
        _make_procedure(self.school, self.indicator, status="In Progress")
        _make_procedure(self.school, self.indicator, status="Pending Review")
        stats = QualityService.get_plan_stats(self.school)
        assert stats["total"] == 4
        assert stats["completed"] == 2
        assert stats["in_progress"] == 1
        assert stats["pending_review"] == 1
        assert stats["pct"] == 50

    def test_get_plan_stats_empty(self):
        other_school = SchoolFactory()
        stats = QualityService.get_plan_stats(other_school)
        assert stats["total"] == 0
        assert stats["pct"] == 0

    def test_get_unmapped_count(self):
        _make_procedure(
            self.school,
            self.indicator,
            executor_norm="مشرف",
            user=None,
        )
        _make_procedure(
            self.school,
            self.indicator,
            executor_norm="معلم",
            user=self.user,
        )
        # Map the "معلم" executor
        ExecutorMapping.objects.create(
            school=self.school,
            executor_norm="معلم",
            user=self.user,
        )
        count = QualityService.get_unmapped_count(self.school)
        # "مشرف" is unmapped
        assert count == 1

    def test_get_my_procedures(self):
        p1 = _make_procedure(
            self.school,
            self.indicator,
            user=self.user,
            status="In Progress",
        )
        p2 = _make_procedure(
            self.school,
            self.indicator,
            user=None,
            status="Completed",
        )
        result = QualityService.get_my_procedures(self.user, self.school)
        assert p1 in result
        assert p2 not in result

    def test_get_domain_procedures(self):
        _make_procedure(
            self.school,
            self.indicator,
            status="Completed",
            executor_norm="معلم رياضيات",
        )
        _make_procedure(
            self.school,
            self.indicator,
            status="In Progress",
            executor_norm="معلم عربي",
        )
        result = QualityService.get_domain_procedures(self.school, self.domain)
        assert result["total"] == 2
        assert result["completed"] == 1
        assert result["pct"] == 50
        assert result["targets"].count() >= 1

    def test_get_domain_procedures_with_filters(self):
        _make_procedure(
            self.school,
            self.indicator,
            status="Completed",
            executor_norm="معلم رياضيات",
        )
        _make_procedure(
            self.school,
            self.indicator,
            status="In Progress",
            executor_norm="معلم عربي",
        )
        result = QualityService.get_domain_procedures(
            self.school,
            self.domain,
            status_filter="Completed",
            executor_filter="رياضيات",
        )
        # Stats are domain-level (unfiltered), so total == 2
        assert result["total"] == 2

    def test_get_progress_report_data(self):
        _make_procedure(self.school, self.indicator, status="Completed")
        _make_procedure(self.school, self.indicator, status="In Progress")
        report = QualityService.get_progress_report_data(self.school)
        assert "domain_stats" in report
        assert "overall" in report
        assert len(report["domain_stats"]) >= 1
        ds = report["domain_stats"][0]
        assert ds["total"] == 2
        assert ds["completed"] == 1

    def test_get_executor_committee_data(self):
        member = QualityCommitteeMember.objects.create(
            school=self.school,
            user=self.user,
            job_title="معلم",
            responsibility="عضو",
            committee_type="executor",
            is_active=True,
        )
        _make_procedure(
            self.school,
            self.indicator,
            user=self.user,
            status="Completed",
        )
        data = QualityService.get_executor_committee_data(self.school)
        assert "member_stats" in data
        assert len(data["member_stats"]) >= 1
        ms = data["member_stats"][0]
        assert ms["total"] == 1
        assert ms["completed"] == 1

    def test_get_executor_committee_data_unmapped_member(self):
        member = QualityCommitteeMember.objects.create(
            school=self.school,
            user=None,
            job_title="وظيفة شاغرة",
            responsibility="عضو",
            committee_type="executor",
            is_active=True,
        )
        data = QualityService.get_executor_committee_data(self.school)
        ms = [m for m in data["member_stats"] if m.get("unmapped")]
        assert len(ms) >= 1
        assert ms[0]["total"] == 0

    def test_get_executor_detail(self):
        member = QualityCommitteeMember.objects.create(
            school=self.school,
            user=self.user,
            job_title="معلم",
            responsibility="عضو",
            committee_type="executor",
        )
        _make_procedure(
            self.school,
            self.indicator,
            user=self.user,
            status="Completed",
        )
        _make_procedure(
            self.school,
            self.indicator,
            user=self.user,
            status="In Progress",
        )
        detail = QualityService.get_executor_detail(member, self.school)
        assert detail["total"] == 2
        assert detail["completed"] == 1
        assert detail["in_progress"] == 1
        assert detail["pct"] == 50
        assert len(detail["by_domain"]) >= 1


# ══════════════════════════════════════════════════════════════
#  6. EmployeeEvaluation & EvaluationCycle
# ══════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestEmployeeEvaluation:
    @pytest.fixture(autouse=True)
    def setup(self, school, teacher_user, principal_user):
        self.school = school
        self.employee = teacher_user
        self.evaluator = principal_user

    def _eval(self, prof=20, commit=20, team=20, dev=20, period="S1", **kw):
        return EmployeeEvaluation.objects.create(
            school=self.school,
            employee=self.employee,
            evaluator=self.evaluator,
            period=period,
            axis_professional=prof,
            axis_commitment=commit,
            axis_teamwork=team,
            axis_development=dev,
            **kw,
        )

    def test_calculate_total_excellent(self):
        ev = self._eval(prof=25, commit=25, team=22, dev=23)
        assert ev.total_score == 95
        assert ev.rating == "excellent"

    def test_calculate_total_very_good(self):
        ev = self._eval(prof=20, commit=20, team=20, dev=20)
        assert ev.total_score == 80
        assert ev.rating == "very_good"

    def test_calculate_total_acceptable(self):
        ev = self._eval(prof=15, commit=15, team=15, dev=18)
        assert ev.total_score == 63
        assert ev.rating == "acceptable"

    def test_calculate_total_weak(self):
        ev = self._eval(prof=10, commit=10, team=10, dev=10)
        assert ev.total_score == 40
        assert ev.rating == "weak"

    def test_boundary_90(self):
        ev = self._eval(prof=25, commit=25, team=25, dev=15)
        assert ev.total_score == 90
        assert ev.rating == "excellent"

    def test_boundary_75(self):
        ev = self._eval(prof=20, commit=20, team=20, dev=15)
        assert ev.total_score == 75
        assert ev.rating == "good"

    def test_boundary_60(self):
        ev = self._eval(prof=15, commit=15, team=15, dev=15)
        assert ev.total_score == 60
        assert ev.rating == "acceptable"

    def test_boundary_59(self):
        ev = self._eval(prof=15, commit=15, team=15, dev=14)
        assert ev.total_score == 59
        assert ev.rating == "acceptable"

    def test_str(self):
        ev = self._eval()
        s = str(ev)
        assert self.employee.full_name in s
        assert "2025-2026" in s

    def test_acknowledge(self):
        ev = self._eval(status="submitted")
        ev.acknowledge()
        ev.refresh_from_db()
        assert ev.status == "acknowledged"
        assert ev.acknowledged_at is not None

    def test_save_recalculates(self):
        ev = self._eval(prof=10, commit=10, team=10, dev=10)
        assert ev.total_score == 40
        ev.axis_professional = 25
        ev.axis_commitment = 25
        ev.axis_teamwork = 25
        ev.axis_development = 25
        ev.save()
        ev.refresh_from_db()
        assert ev.total_score == 100
        assert ev.rating == "excellent"

    def test_unique_constraint(self):
        self._eval(period="S2")
        with pytest.raises(Exception):
            self._eval(period="S2")


@pytest.mark.django_db
class TestEvaluationCycle:
    @pytest.fixture(autouse=True)
    def setup(self, school, principal_user, teacher_user):
        self.school = school
        self.principal = principal_user
        self.teacher = teacher_user

    def test_str(self):
        cycle = EvaluationCycle.objects.create(
            school=self.school,
            period="S1",
            deadline=date(2026, 1, 15),
            created_by=self.principal,
        )
        s = str(cycle)
        assert self.school.code in s
        assert "2025-2026" in s

    def test_completion_rate_no_staff(self):
        other_school = SchoolFactory()
        cycle = EvaluationCycle.objects.create(
            school=other_school,
            period="S1",
            deadline=date(2026, 1, 15),
            created_by=self.principal,
        )
        assert cycle.completion_rate == 0

    def test_completion_rate_with_staff(self):
        # The teacher_user already has a 'teacher' membership
        cycle = EvaluationCycle.objects.create(
            school=self.school,
            period="S1",
            deadline=date(2026, 1, 15),
            created_by=self.principal,
        )
        # No evaluations yet
        assert cycle.completion_rate == 0

        # Submit an evaluation for the teacher
        EmployeeEvaluation.objects.create(
            school=self.school,
            employee=self.teacher,
            evaluator=self.principal,
            period="S1",
            status="submitted",
            axis_professional=20,
            axis_commitment=20,
            axis_teamwork=20,
            axis_development=20,
        )
        # Now 1 out of 1 teacher staff = 100%
        # (principal has role 'principal' which is not in the staff list)
        # Re-fetch to clear cached_property
        cycle = EvaluationCycle.objects.get(pk=cycle.pk)
        assert cycle.completion_rate == 100

    def test_unique_constraint(self):
        EvaluationCycle.objects.create(
            school=self.school,
            period="S2",
            deadline=date(2026, 6, 15),
            created_by=self.principal,
        )
        with pytest.raises(Exception):
            EvaluationCycle.objects.create(
                school=self.school,
                period="S2",
                deadline=date(2026, 6, 20),
                created_by=self.principal,
            )

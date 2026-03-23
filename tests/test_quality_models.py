"""
tests/test_quality_models.py
اختبارات النماذج والـ QuerySets لمنظومة الجودة
"""

import itertools
from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import CustomUser, Membership, Role, School
from quality.models import (
    ExecutorMapping,
    OperationalDomain,
    OperationalIndicator,
    OperationalProcedure,
    OperationalTarget,
    ProcedureEvidence,
    ProcedureStatusLog,
    QualityCommitteeMember,
)

# ══════════════════════════════════════════════
#  HELPER FACTORIES
# ══════════════════════════════════════════════

_seq = itertools.count(1)


def _n():
    return next(_seq)


def make_admin(school):
    """ينشئ مستخدماً بدور principal (admin)"""
    role, _ = Role.objects.get_or_create(school=school, name="principal")
    n = _n()
    user = CustomUser.objects.create_user(
        national_id=f"ADM{n:08d}",
        full_name="مدير المدرسة",
        email=f"admin_{n}@school.qa",
        password="pass123",
    )
    Membership.objects.create(user=user, school=school, role=role, is_active=True)
    return user


def make_teacher(school, suffix=None):
    """ينشئ مستخدماً بدور teacher"""
    role, _ = Role.objects.get_or_create(school=school, name="teacher")
    n = _n()
    s = suffix or str(n)
    user = CustomUser.objects.create_user(
        national_id=f"TCH{n:08d}",
        full_name=f"معلم {s}",
        email=f"teacher_{n}@school.qa",
        password="pass123",
    )
    Membership.objects.create(user=user, school=school, role=role, is_active=True)
    return user


def make_domain(school, name=None, year="2025-2026"):
    n = _n()
    domain_name = name or f"المجال التجريبي {n}"
    return OperationalDomain.objects.create(
        school=school, name=domain_name, academic_year=year, order=1
    )


def make_procedure(
    school,
    domain,
    executor_user=None,
    status="In Progress",
    executor_norm="معلم الرياضيات",
    deadline=None,
    follow_up="",
    reviewed_by=None,
):
    """ينشئ إجراء تشغيلي مع دعم كامل لكل الحقول المطلوبة في الاختبارات."""
    n = _n()
    target, _ = OperationalTarget.objects.get_or_create(
        domain=domain, number="1.1", defaults={"text": "هدف تجريبي"}
    )
    indicator, _ = OperationalIndicator.objects.get_or_create(
        target=target, number="1.1.1", defaults={"text": "مؤشر تجريبي"}
    )
    return OperationalProcedure.objects.create(
        indicator=indicator,
        school=school,
        number=f"1.1.1.{n}",
        text=f"إجراء تجريبي {n}",
        executor_norm=executor_norm,
        executor_user=executor_user,
        status=status,
        academic_year="2025-2026",
        deadline=deadline,
        follow_up=follow_up,
        reviewed_by=reviewed_by,
    )


def make_committee_member(
    school,
    user,
    committee_type=QualityCommitteeMember.REVIEW,
    can_review=True,
    year="2025-2026",
):
    return QualityCommitteeMember.objects.create(
        school=school,
        user=user,
        job_title=user.full_name,
        responsibility="عضو",
        committee_type=committee_type,
        academic_year=year,
        is_active=True,
        can_review=can_review,
    )


# ══════════════════════════════════════════════
#  1. TestOperationalProcedureProperties
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestOperationalProcedureProperties:
    """اختبار الـ properties المحسوبة على OperationalProcedure."""

    # ── is_overdue ──────────────────────────────────────────────

    def test_is_overdue_true(self, school):
        """إجراء بموعد أمس وحالة In Progress → True"""
        domain = make_domain(school)
        proc = make_procedure(
            school, domain,
            deadline=timezone.now().date() - timedelta(days=1),
            status="In Progress",
        )
        assert proc.is_overdue is True

    def test_is_overdue_false_completed(self, school):
        """إجراء بموعد أمس لكن حالته Completed → False"""
        domain = make_domain(school)
        proc = make_procedure(
            school, domain,
            deadline=timezone.now().date() - timedelta(days=1),
            status="Completed",
        )
        assert proc.is_overdue is False

    def test_is_overdue_false_no_deadline(self, school):
        """إجراء بدون موعد نهائي → False"""
        domain = make_domain(school)
        proc = make_procedure(school, domain, deadline=None, status="In Progress")
        assert proc.is_overdue is False

    # ── is_due_soon ────────────────────────────────────────────

    def test_is_due_soon_true(self, school):
        """موعد نهائي بعد 5 أيام → True (ضمن 7 أيام)"""
        domain = make_domain(school)
        proc = make_procedure(
            school, domain,
            deadline=timezone.now().date() + timedelta(days=5),
            status="In Progress",
        )
        assert proc.is_due_soon is True

    def test_is_due_soon_false_far(self, school):
        """موعد نهائي بعد 30 يوماً → False"""
        domain = make_domain(school)
        proc = make_procedure(
            school, domain,
            deadline=timezone.now().date() + timedelta(days=30),
            status="In Progress",
        )
        assert proc.is_due_soon is False

    # ── is_due_urgent ──────────────────────────────────────────

    def test_is_due_urgent_true(self, school):
        """موعد نهائي بعد يومين → True (ضمن 3 أيام)"""
        domain = make_domain(school)
        proc = make_procedure(
            school, domain,
            deadline=timezone.now().date() + timedelta(days=2),
            status="In Progress",
        )
        assert proc.is_due_urgent is True

    def test_is_due_urgent_false(self, school):
        """موعد نهائي بعد 5 أيام → False (خارج 3 أيام)"""
        domain = make_domain(school)
        proc = make_procedure(
            school, domain,
            deadline=timezone.now().date() + timedelta(days=5),
            status="In Progress",
        )
        assert proc.is_due_urgent is False

    # ── days_overdue ───────────────────────────────────────────

    def test_days_overdue(self, school):
        """موعد نهائي قبل 10 أيام → 10"""
        domain = make_domain(school)
        proc = make_procedure(
            school, domain,
            deadline=timezone.now().date() - timedelta(days=10),
            status="In Progress",
        )
        assert proc.days_overdue == 10

    def test_days_overdue_not_overdue(self, school):
        """موعد نهائي في المستقبل → 0"""
        domain = make_domain(school)
        proc = make_procedure(
            school, domain,
            deadline=timezone.now().date() + timedelta(days=5),
            status="In Progress",
        )
        assert proc.days_overdue == 0

    # ── committee_decision_display ─────────────────────────────

    def test_committee_decision_completed(self, school):
        """حالة Completed + مُراجع → 'معتمد'"""
        domain = make_domain(school)
        reviewer = make_teacher(school)
        proc = make_procedure(
            school, domain,
            status="Completed",
            reviewed_by=reviewer,
        )
        assert proc.committee_decision_display == "معتمد"

    def test_committee_decision_returned(self, school):
        """حالة In Progress + مُراجع → 'مُعاد للمنفذ'"""
        domain = make_domain(school)
        reviewer = make_teacher(school)
        proc = make_procedure(
            school, domain,
            status="In Progress",
            reviewed_by=reviewer,
        )
        assert proc.committee_decision_display == "مُعاد للمنفذ"

    def test_committee_decision_pending(self, school):
        """حالة Pending Review → 'بانتظار القرار'"""
        domain = make_domain(school)
        proc = make_procedure(school, domain, status="Pending Review")
        assert proc.committee_decision_display == "بانتظار القرار"

    def test_committee_decision_none(self, school):
        """حالة Not Started بدون مُراجع → 'بدون قرار'"""
        domain = make_domain(school)
        proc = make_procedure(school, domain, status="Not Started")
        assert proc.committee_decision_display == "بدون قرار"

    # ── follow_up_display ──────────────────────────────────────

    def test_follow_up_display_empty(self, school):
        """follow_up فارغ → 'لم يتم الإنجاز'"""
        domain = make_domain(school)
        proc = make_procedure(school, domain, follow_up="")
        assert proc.follow_up_display == "لم يتم الإنجاز"

    def test_follow_up_display_value(self, school):
        """follow_up='تم الإنجاز' → 'تم الإنجاز'"""
        domain = make_domain(school)
        proc = make_procedure(school, domain, follow_up="تم الإنجاز")
        assert proc.follow_up_display == "تم الإنجاز"


# ══════════════════════════════════════════════
#  2. TestProcedureQuerySet
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestProcedureQuerySet:
    """اختبار QuerySet المخصص لـ OperationalProcedure."""

    def test_overdue_returns_past_deadline(self, school):
        """overdue() يُرجع فقط الإجراءات المتأخرة"""
        domain = make_domain(school)
        today = timezone.now().date()
        overdue_proc = make_procedure(
            school, domain,
            deadline=today - timedelta(days=3),
            status="In Progress",
        )
        future_proc = make_procedure(
            school, domain,
            deadline=today + timedelta(days=10),
            status="In Progress",
        )
        qs = OperationalProcedure.objects.filter(school=school).overdue()
        assert overdue_proc in qs
        assert future_proc not in qs

    def test_overdue_excludes_completed(self, school):
        """overdue() يستثني المكتملة حتى لو تجاوزت الموعد"""
        domain = make_domain(school)
        proc = make_procedure(
            school, domain,
            deadline=timezone.now().date() - timedelta(days=5),
            status="Completed",
        )
        qs = OperationalProcedure.objects.filter(school=school).overdue()
        assert proc not in qs

    def test_due_soon_returns_upcoming(self, school):
        """due_soon() يُرجع الإجراءات القريبة"""
        domain = make_domain(school)
        today = timezone.now().date()
        soon_proc = make_procedure(
            school, domain,
            deadline=today + timedelta(days=3),
            status="In Progress",
        )
        far_proc = make_procedure(
            school, domain,
            deadline=today + timedelta(days=30),
            status="In Progress",
        )
        qs = OperationalProcedure.objects.filter(school=school).due_soon()
        assert soon_proc in qs
        assert far_proc not in qs

    def test_completed_filter(self, school):
        """completed() يُرجع فقط المكتملة"""
        domain = make_domain(school)
        p_completed = make_procedure(school, domain, status="Completed")
        p_progress = make_procedure(school, domain, status="In Progress")
        p_not_started = make_procedure(school, domain, status="Not Started")
        qs = OperationalProcedure.objects.filter(school=school).completed()
        assert p_completed in qs
        assert p_progress not in qs
        assert p_not_started not in qs

    def test_pending_review_filter(self, school):
        """pending_review() يُرجع فقط بانتظار المراجعة"""
        domain = make_domain(school)
        p_pending = make_procedure(school, domain, status="Pending Review")
        p_other = make_procedure(school, domain, status="In Progress")
        qs = OperationalProcedure.objects.filter(school=school).pending_review()
        assert p_pending in qs
        assert p_other not in qs

    def test_active_excludes_completed_cancelled(self, school):
        """active() يستثني المكتملة والملغاة"""
        domain = make_domain(school)
        p_active = make_procedure(school, domain, status="In Progress")
        p_completed = make_procedure(school, domain, status="Completed")
        p_cancelled = make_procedure(school, domain, status="Cancelled")
        qs = OperationalProcedure.objects.filter(school=school).active()
        assert p_active in qs
        assert p_completed not in qs
        assert p_cancelled not in qs

    def test_for_executor_filter(self, school):
        """for_executor() يُرجع إجراءات المنفذ المحدد"""
        domain = make_domain(school)
        teacher = make_teacher(school)
        other = make_teacher(school)
        p_teacher = make_procedure(school, domain, executor_user=teacher)
        p_other = make_procedure(school, domain, executor_user=other)
        qs = OperationalProcedure.objects.filter(school=school).for_executor(teacher)
        assert p_teacher in qs
        assert p_other not in qs

    def test_for_domain_filter(self, school):
        """for_domain() يُرجع إجراءات المجال المحدد"""
        domain1 = make_domain(school)
        domain2 = make_domain(school)
        p_d1 = make_procedure(school, domain1)
        p_d2 = make_procedure(school, domain2)
        qs = OperationalProcedure.objects.filter(school=school).for_domain(domain1)
        assert p_d1 in qs
        assert p_d2 not in qs

    def test_with_details_prefetches(self, school):
        """with_details() يُرجع النتائج بنجاح مع select_related/prefetch"""
        domain = make_domain(school)
        make_procedure(school, domain)
        qs = OperationalProcedure.objects.filter(school=school).with_details()
        assert qs.count() == 1
        proc = qs.first()
        # التحقق من أن العلاقات محمّلة
        assert proc.indicator is not None
        assert proc.indicator.target is not None
        assert proc.indicator.target.domain is not None

    def test_completion_rate(self, school):
        """completion_rate() — 2 مكتملة من 3 → 66.7"""
        domain = make_domain(school)
        make_procedure(school, domain, status="Completed")
        make_procedure(school, domain, status="Completed")
        make_procedure(school, domain, status="In Progress")
        rate = OperationalProcedure.objects.filter(school=school).completion_rate()
        assert rate == 66.7

    def test_completion_rate_empty(self, school):
        """completion_rate() بدون إجراءات → 0.0"""
        rate = OperationalProcedure.objects.filter(school=school).completion_rate()
        assert rate == 0.0

    def test_summary_by_status(self, school):
        """summary_by_status() يُعيد تجميع حسب الحالة"""
        domain = make_domain(school)
        make_procedure(school, domain, status="Completed")
        make_procedure(school, domain, status="Completed")
        make_procedure(school, domain, status="In Progress")
        summary = list(
            OperationalProcedure.objects.filter(school=school).summary_by_status()
        )
        status_map = {item["status"]: item["count"] for item in summary}
        assert status_map["Completed"] == 2
        assert status_map["In Progress"] == 1


# ══════════════════════════════════════════════
#  3. TestDomainQuerySet
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestDomainQuerySet:
    """اختبار QuerySet المخصص لـ OperationalDomain."""

    def test_with_progress_annotates(self, school):
        """with_progress() يُضيف total_procedures و completed_procedures"""
        domain = make_domain(school)
        make_procedure(school, domain, status="Completed")
        make_procedure(school, domain, status="Completed")
        make_procedure(school, domain, status="In Progress")

        qs = OperationalDomain.objects.filter(school=school).with_progress()
        d = qs.get(pk=domain.pk)
        assert d.total_procedures == 3
        assert d.completed_procedures == 2

    def test_with_progress_empty_domain(self, school):
        """مجال بدون إجراءات → total=0, completed=0"""
        domain = make_domain(school)

        qs = OperationalDomain.objects.filter(school=school).with_progress()
        d = qs.get(pk=domain.pk)
        assert d.total_procedures == 0
        assert d.completed_procedures == 0


# ══════════════════════════════════════════════
#  4. TestProcedureStatusLog
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestProcedureStatusLog:
    """اختبار سجل تغييرات الحالة."""

    def test_create_log(self, school):
        """إنشاء سجل تغيير حالة والتحقق من الحقول"""
        domain = make_domain(school)
        user = make_teacher(school)
        proc = make_procedure(school, domain)

        log = ProcedureStatusLog.objects.create(
            procedure=proc,
            old_status="Not Started",
            new_status="In Progress",
            changed_by=user,
            note="بدء التنفيذ",
        )

        assert log.procedure == proc
        assert log.old_status == "Not Started"
        assert log.new_status == "In Progress"
        assert log.changed_by == user
        assert log.note == "بدء التنفيذ"
        assert log.created_at is not None

    def test_ordering(self, school):
        """الترتيب: الأحدث أولاً"""
        domain = make_domain(school)
        proc = make_procedure(school, domain)

        log1 = ProcedureStatusLog.objects.create(
            procedure=proc,
            old_status="Not Started",
            new_status="In Progress",
        )
        import time
        time.sleep(0.01)  # ensure different created_at timestamps
        log2 = ProcedureStatusLog.objects.create(
            procedure=proc,
            old_status="In Progress",
            new_status="Completed",
        )

        logs = list(ProcedureStatusLog.objects.filter(procedure=proc))
        # الأحدث (log2) يأتي أولاً بسبب ordering = ["-created_at"]
        assert logs[0].pk == log2.pk
        assert logs[1].pk == log1.pk

    def test_str_representation(self, school):
        """__str__ يُنسّق بالشكل: رقم_الإجراء: القديم → الجديد"""
        domain = make_domain(school)
        proc = make_procedure(school, domain)

        log = ProcedureStatusLog.objects.create(
            procedure=proc,
            old_status="Not Started",
            new_status="In Progress",
        )
        expected = f"{proc.number}: Not Started → In Progress"
        assert str(log) == expected

    def test_cascade_delete(self, school):
        """حذف الإجراء يحذف سجلات الحالة المرتبطة"""
        domain = make_domain(school)
        admin = make_admin(school)
        proc = make_procedure(school, domain)
        ProcedureStatusLog.objects.create(
            procedure=proc,
            old_status="A",
            new_status="B",
            changed_by=admin,
        )
        proc.delete()
        assert ProcedureStatusLog.objects.count() == 0


# ══════════════════════════════════════════════
#  5. TestExecutorMapping
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestExecutorMapping:
    """اختبار ربط المنفذين."""

    def test_apply_mapping(self, school):
        """apply_mapping() يُحدّث executor_user في الإجراءات المطابقة"""
        domain = make_domain(school)
        teacher = make_teacher(school)

        norm = "مشرف الجودة"
        # إنشاء إجراءات بنفس executor_norm
        p1 = make_procedure(school, domain, executor_norm=norm)
        p2 = make_procedure(school, domain, executor_norm=norm)
        # إجراء بمسمى مختلف — يجب ألا يتأثر
        p3 = make_procedure(school, domain, executor_norm="معلم آخر")

        mapping = ExecutorMapping.objects.create(
            school=school,
            executor_norm=norm,
            user=teacher,
            academic_year="2025-2026",
        )
        mapping.apply_mapping()

        p1.refresh_from_db()
        p2.refresh_from_db()
        p3.refresh_from_db()
        assert p1.executor_user == teacher
        assert p2.executor_user == teacher
        assert p3.executor_user is None  # لم يتأثر

    def test_apply_mapping_different_year(self, school):
        """apply_mapping() لا يُحدّث إجراءات من عام دراسي مختلف"""
        domain = make_domain(school)
        teacher = make_teacher(school)
        norm = "مشرف الجودة"

        # إجراء من عام مختلف
        target, _ = OperationalTarget.objects.get_or_create(
            domain=domain, number="1.1", defaults={"text": "هدف تجريبي"}
        )
        indicator, _ = OperationalIndicator.objects.get_or_create(
            target=target, number="1.1.1", defaults={"text": "مؤشر تجريبي"}
        )
        n = _n()
        old_proc = OperationalProcedure.objects.create(
            indicator=indicator,
            school=school,
            number=f"1.1.1.{n}",
            text="إجراء قديم",
            executor_norm=norm,
            status="In Progress",
            academic_year="2024-2025",
        )

        mapping = ExecutorMapping.objects.create(
            school=school,
            executor_norm=norm,
            user=teacher,
            academic_year="2025-2026",
        )
        mapping.apply_mapping()

        old_proc.refresh_from_db()
        assert old_proc.executor_user is None

    def test_str_representation(self, school):
        """__str__ يُنسّق بالشكل: المسمى → اسم_الموظف"""
        teacher = make_teacher(school)
        mapping = ExecutorMapping.objects.create(
            school=school,
            executor_norm="منسق الجودة",
            user=teacher,
            academic_year="2025-2026",
        )
        result = str(mapping)
        assert "منسق الجودة" in result
        assert teacher.full_name in result

    def test_str_unlinked(self, school):
        """__str__ بدون مستخدم مربوط → 'غير مربوط'"""
        mapping = ExecutorMapping.objects.create(
            school=school,
            executor_norm="منسق الجودة",
            user=None,
            academic_year="2025-2026",
        )
        assert "غير مربوط" in str(mapping)


# ══════════════════════════════════════════════
#  6. TestNewFields (defaults and choices)
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestNewFields:
    """اختبار القيم الافتراضية والخيارات للحقول الجديدة."""

    def test_evidence_request_status_default(self, school):
        """القيمة الافتراضية لحالة طلب الدليل هي 'not_requested'"""
        domain = make_domain(school)
        proc = make_procedure(school, domain)
        assert proc.evidence_request_status == "not_requested"

    def test_quality_rating_default(self, school):
        """القيمة الافتراضية للتقييم النوعي هي سلسلة فارغة"""
        domain = make_domain(school)
        proc = make_procedure(school, domain)
        assert proc.quality_rating == ""

    def test_evidence_request_choices(self, school):
        """يمكن تعيين جميع خيارات حالة طلب الدليل"""
        domain = make_domain(school)
        for value, _label in OperationalProcedure.EVIDENCE_REQUEST_STATUS:
            proc = make_procedure(school, domain)
            proc.evidence_request_status = value
            proc.save()
            proc.refresh_from_db()
            assert proc.evidence_request_status == value

    def test_quality_rating_choices(self, school):
        """يمكن تعيين جميع خيارات التقييم النوعي"""
        domain = make_domain(school)
        for value, _label in OperationalProcedure.QUALITY_RATING:
            proc = make_procedure(school, domain)
            proc.quality_rating = value
            proc.save()
            proc.refresh_from_db()
            assert proc.quality_rating == value

    def test_evidence_request_note_set(self, school):
        """يمكن تعيين ملاحظات طلب الدليل"""
        domain = make_domain(school)
        proc = make_procedure(school, domain)
        proc.evidence_request_status = "requested"
        proc.evidence_request_note = "يرجى رفع محضر الاجتماع"
        proc.save()
        proc.refresh_from_db()
        assert proc.evidence_request_status == "requested"
        assert "محضر" in proc.evidence_request_note

    def test_follow_up_choices(self, school):
        """يمكن تعيين جميع خيارات المتابعة"""
        domain = make_domain(school)
        for value, _label in OperationalProcedure.FOLLOW_UP_CHOICES:
            proc = make_procedure(school, domain)
            proc.follow_up = value
            proc.save()
            proc.refresh_from_db()
            assert proc.follow_up == value

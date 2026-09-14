"""حضورُ الموظّفين (1.1) والأذوناتُ القصيرة (1.3) — القواعدُ من النصّ حرفاً.

المرجع: ``AAdocs/ministry_data/2026_2027/06_attendance_performance_review.md`` §1
«سياسة وضوابط الحضور والانصراف» (ت/د: 2027/01 بتاريخ 2026-08-23، مدرسة الشحانية —
وثيقةٌ من صفحتين)، و``07_forms_catalog.md`` جدول 1 بند 02.

    البند 1.1 «يبدأ الدوام الرسمي لموظفي المدرسة من الساعة السابعة صباحاً»
    البند 2.1 «يعتبر الموظف متأخراً إذا حضر بعد الساعة 7:00 صباحاً»
    البند 2.4 «يعتبر الموظف غائباً إذا حضر بعد الساعة التاسعة صباحاً دون إذن أو عذر مقبول»
    البند 4.1 «لا يجوز الاعتداد بالإذن إلا بعد اعتماده من الرئيس المباشر»
    البند 4.2 «يكون الحد الأقصى للأذونات بواقع (7) ساعات في الشهر»
    البند 4.3 «لا يجوز الإذن أكثر من مرة واحدة في اليوم الواحد»
    البند 4.4 «يكون الحد الأقصى للإذن ساعتين في المرة الواحدة»

    07_forms_catalog.md:13 (نموذج 02) «المسؤول المباشر (موافق/غير موافق) ← النائب المسؤول
    ← السكرتارية (تسجّل رصيد الساعات) ← الإدارة … ولا يخرج الموظف فعلياً إلا بعد اعتماد
    مدير المدرسة»، ومثله 07b_forms_catalog_thirdpass.md:13؛ والمسؤولُ المباشر من
    «reports_to» في rbac_roles.json.
    03_job_descriptions_rbac.md:101 السكرتير «متابعة الحضور والانصراف للموظفين».

«بعد» في 2.1 (06:31) و2.4 (06:34) تعني أنّ 7:00 بالضبط حاضر و9:00 بالضبط متأخّر لا غائب.
والأشخاصُ هنا اصطناعيّون: لا رقمَ شخصيّاً يُكتب، والرقمُ الوظيفيُّ «T-000n».
"""

from __future__ import annotations

import json
from datetime import date, time
from pathlib import Path

import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse

from core.models import AuditLog
from core.models.access import Membership, Role
from staff_affairs.attendance import (
    LINE_MANAGER,
    MONTHLY_PERMIT_CAP,
    PermitService,
    PolicyError,
    StaffAttendanceService,
    classify_arrival,
    minutes_between,
)
from staff_affairs.models import PermitRequest, StaffAttendance
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

FEB = date(2026, 2, 1)


def _staff(school, n, role="teacher"):
    user = UserFactory(full_name=f"موظف اصطناعي {n}", employee_number=f"T-{n:04d}")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


#: أرقامٌ وظيفيّةٌ اصطناعيّة لأصحاب المراحل — لا تتصادم مع T-000n.
ACTOR_NUMBERS = {"principal": 901, "vice_admin": 902, "vice_academic": 903, "secretary": 904}


def _actor(school, role):
    """صاحبُ الدور في المدرسة — الموجودُ إن كان، وإلّا يُنشأ."""
    member = (
        Membership.objects.filter(school=school, role__name=role, is_active=True)
        .select_related("user")
        .first()
    )
    return member.user if member else _staff(school, ACTOR_NUMBERS[role], role)


def _through(permit, approve=True, reason="غير مناسب"):
    """يمرّ الطلبُ بمراحل نموذج 02 كلِّها — أو يُرفض في مرحلته الأولى."""
    while permit.status == "pending":
        actor = _actor(permit.school, PermitService.required_role(permit))
        PermitService.act(permit, actor=actor, approve=approve, reason=reason)
        permit.refresh_from_db()
    return permit


def _permit(school, staff, day, start, end, kind="during_day", approve=True):
    permit = PermitService.submit(
        school=school,
        staff=staff,
        permit_type=kind,
        day=day,
        start_time=start,
        end_time=end,
        reason="ظرف عائلي",
    )
    if approve is not None:
        _through(permit, approve=approve)
    return permit


def _mark(school, staff, actor, day, status, check_in=None):
    return StaffAttendanceService.mark(
        school=school, staff=staff, day=day, status=status, actor=actor, check_in=check_in
    )


# ══════════════════════════════════════════════════════════════════════
#  التصنيف — البنود 2.1 و2.4
# ══════════════════════════════════════════════════════════════════════


class TestClassifyArrival:
    @pytest.mark.parametrize(
        ("check_in", "expected"),
        [
            (time(6, 45), ("present", 0)),
            (time(7, 0), ("present", 0)),  # 2.1: «بعد 7:00» — فالسابعةُ نفسُها حضور
            (time(7, 1), ("late", 1)),
            (time(8, 59), ("late", 119)),
            (time(9, 0), ("late", 120)),  # 2.4: «بعد التاسعة» — فالتاسعةُ نفسُها تأخّر
            (time(9, 1), ("absent", 0)),
            (time(11, 30), ("absent", 0)),
        ],
    )
    def test_the_boundaries_read_after_as_strictly_after(self, check_in, expected):
        assert classify_arrival(check_in) == expected

    def test_an_approved_late_arrival_permit_covers_and_lifts_absence(self):
        # 2.4: «دون إذن» — فالمستأذنُ حتّى 9:30 لا يُعدّ غائباً.
        assert classify_arrival(time(9, 20), covered_until=time(9, 30)) == ("permitted", 0)
        assert classify_arrival(time(9, 40), covered_until=time(9, 30)) == ("late", 10)

    def test_minutes_between_is_whole_minutes_and_never_negative(self):
        assert minutes_between(time(7, 0), time(8, 30)) == 90
        assert minutes_between(time(9, 0), time(8, 0)) == 0


# ══════════════════════════════════════════════════════════════════════
#  الرصد (1.1)
# ══════════════════════════════════════════════════════════════════════


class TestMark:
    def test_on_time(self, school, principal_user):
        staff = _staff(school, 1)
        record = _mark(school, staff, principal_user, FEB, "present", time(6, 55))

        assert (record.status, record.late_minutes) == ("present", 0)
        assert record.created_by == principal_user

    def test_late_before_nine(self, school, principal_user):
        staff = _staff(school, 1)
        record = _mark(school, staff, principal_user, FEB, "late", time(8, 40))

        assert (record.status, record.late_minutes) == ("late", 100)

    def test_after_nine_is_absence(self, school, principal_user):
        staff = _staff(school, 1)
        record = _mark(school, staff, principal_user, FEB, "absent", time(9, 1))

        assert record.status == "absent"

    def test_a_click_that_contradicts_the_time_is_refused_by_name(self, school, principal_user):
        staff = _staff(school, 1)

        with pytest.raises(PolicyError, match="متأخّر"):
            _mark(school, staff, principal_user, FEB, "present", time(8, 10))
        assert not StaffAttendance.objects.exists()

    def test_permitted_needs_an_approved_permit(self, school, principal_user):
        staff = _staff(school, 1)
        with pytest.raises(PolicyError, match="4.1"):
            _mark(school, staff, principal_user, FEB, "permitted")

        _permit(school, staff, FEB, time(7, 0), time(8, 30), "late_arrival")
        record = _mark(school, staff, principal_user, FEB, "permitted", time(8, 15))

        assert (record.status, record.permit_minutes) == ("permitted", 90)

    def test_remarking_the_same_is_idempotent_and_a_change_is_audited(self, school, principal_user):
        staff = _staff(school, 1)
        _mark(school, staff, principal_user, FEB, "absent")
        _mark(school, staff, principal_user, FEB, "absent")
        _mark(school, staff, principal_user, FEB, "late", time(7, 30))

        assert StaffAttendance.objects.count() == 1
        logged = list(
            AuditLog.objects.filter(object_repr__startswith="StaffAttendance").values_list(
                "action", flat=True
            )
        )
        assert sorted(logged) == ["create", "update"]

    def test_future_days_unknown_statuses_and_outsiders_are_refused(
        self, school, principal_user, student_user
    ):
        staff = _staff(school, 1)
        with pytest.raises(PolicyError):
            _mark(school, staff, principal_user, date(2099, 1, 1), "present")
        with pytest.raises(PolicyError):
            _mark(school, staff, principal_user, FEB, "holiday")
        with pytest.raises(PolicyError, match="كادر"):
            _mark(school, student_user, principal_user, FEB, "present")

    def test_approving_a_permit_updates_an_already_marked_day(self, school, principal_user):
        staff = _staff(school, 1)
        record = _mark(school, staff, principal_user, FEB, "present", time(6, 50))
        _permit(school, staff, FEB, time(12, 0), time(13, 0), "early_departure")

        record.refresh_from_db()
        assert record.permit_minutes == 60


# ══════════════════════════════════════════════════════════════════════
#  الأذونات (1.3) — البنود 4.1 إلى 4.4
# ══════════════════════════════════════════════════════════════════════


class TestPermits:
    def test_a_permit_within_the_cap_deducts_exactly_its_minutes_on_approval(
        self, school, principal_user
    ):
        staff = _staff(school, 1)
        permit = _permit(school, staff, FEB, time(10, 0), time(11, 15), approve=None)

        # 4.1: لا يُعتدّ به قبل الاعتماد — معلَّقٌ لا يخصم.
        pending = PermitService.balance(school, staff, FEB)
        assert (pending.approved, pending.pending, pending.remaining) == (0, 75, 420)

        _through(permit)
        after = PermitService.balance(school, staff, FEB)
        assert (after.approved, after.pending, after.remaining) == (75, 0, 345)

    def test_exactly_two_hours_passes_and_one_minute_more_is_refused(self, school, principal_user):
        staff = _staff(school, 1)
        _permit(school, staff, FEB, time(10, 0), time(12, 0))

        with pytest.raises(PolicyError, match="4.4"):
            _permit(school, staff, date(2026, 2, 2), time(10, 0), time(12, 1))

    def test_a_permit_that_exceeds_the_monthly_cap_is_refused(self, school, principal_user):
        staff = _staff(school, 1)
        for day in (2, 3, 4):  # 3 × 120 = 360
            _permit(school, staff, date(2026, 2, day), time(10, 0), time(12, 0))
        _permit(school, staff, date(2026, 2, 5), time(10, 0), time(11, 0))
        assert PermitService.balance(school, staff, FEB).remaining == 0  # 420 كاملةً جائزة

        with pytest.raises(PolicyError, match="4.2"):
            _permit(school, staff, date(2026, 2, 9), time(10, 0), time(10, 1))
        # الشهرُ التالي رصيدٌ جديد.
        _permit(school, staff, date(2026, 3, 1), time(10, 0), time(12, 0))

    def test_pending_requests_count_against_the_cap_at_submission(self, school, principal_user):
        staff = _staff(school, 1)
        for day in (2, 3, 4):
            _permit(
                school,
                staff,
                date(2026, 2, day),
                time(10, 0),
                time(12, 0),
                approve=None,
            )
        with pytest.raises(PolicyError, match="4.2"):
            _permit(
                school,
                staff,
                date(2026, 2, 5),
                time(10, 0),
                time(11, 1),
                approve=None,
            )

    @staticmethod
    def _approved_elsewhere(school, staff, day):
        """إذنٌ اعتُمد من طريقٍ آخر بين التقديم والمرحلة (سباقٌ أو إدخالٌ يدويّ)."""
        PermitRequest.objects.create(
            school=school,
            staff=staff,
            permit_type="during_day",
            date=day,
            start_time=time(10, 0),
            end_time=time(11, 0),
            duration_minutes=60,
            reason="x",
            status="approved",
            stage="closed",
            supervisor_role="vice_academic",
        )

    def test_the_secretary_records_the_balance_and_an_overflow_is_refused_by_name(self, school):
        staff = _staff(school, 1)
        for day in (2, 3, 4):  # 360 معتمدة
            _permit(school, staff, date(2026, 2, day), time(10, 0), time(12, 0))
        waiting = _permit(school, staff, date(2026, 2, 9), time(10, 0), time(11, 0), approve=None)
        PermitService.act(waiting, actor=_actor(school, "vice_academic"), approve=True)
        self._approved_elsewhere(school, staff, date(2026, 2, 10))  # 420 معتمدة الآن

        PermitService.act(waiting, actor=_actor(school, "secretary"), approve=True)

        waiting.refresh_from_db()
        assert (waiting.status, waiting.rejected_stage) == ("rejected", "secretary")
        assert waiting.recorded_balance_minutes == 0
        assert "4.2" in waiting.rejection_reason

    def test_the_principal_rechecks_the_cap_before_approving(self, school):
        staff = _staff(school, 1)
        for day in (2, 3, 4):
            _permit(school, staff, date(2026, 2, day), time(10, 0), time(12, 0))
        waiting = _permit(school, staff, date(2026, 2, 9), time(10, 0), time(11, 0), approve=None)
        PermitService.act(waiting, actor=_actor(school, "vice_academic"), approve=True)
        PermitService.act(waiting, actor=_actor(school, "secretary"), approve=True)
        waiting.refresh_from_db()
        assert (waiting.stage, waiting.recorded_balance_minutes) == ("principal", 60)
        self._approved_elsewhere(school, staff, date(2026, 2, 10))

        with pytest.raises(PolicyError, match="4.2"):  # 420 + 60 = 480
            PermitService.act(waiting, actor=_actor(school, "principal"), approve=True)
        waiting.refresh_from_db()
        assert (waiting.status, waiting.stage) == ("pending", "principal")

    def test_one_permit_per_day(self, school, principal_user):
        staff = _staff(school, 1)
        _permit(school, staff, FEB, time(7, 0), time(7, 30), "late_arrival")

        with pytest.raises(PolicyError, match="4.3"):
            _permit(school, staff, FEB, time(12, 0), time(12, 30), "early_departure")

    def test_the_database_holds_one_approved_per_day_and_two_hours(self, school, principal_user):
        staff = _staff(school, 1)
        first = _permit(school, staff, FEB, time(7, 0), time(7, 30))
        fields = {
            "school": school,
            "staff": staff,
            "permit_type": "during_day",
            "date": FEB,
            "start_time": time(10, 0),
            "end_time": time(10, 30),
            "duration_minutes": 30,
            "reason": "x",
        }
        with pytest.raises(IntegrityError), transaction.atomic():
            PermitRequest.objects.create(**fields, status="approved")
        with pytest.raises(IntegrityError), transaction.atomic():
            PermitRequest.objects.create(
                **{**fields, "date": date(2026, 2, 2), "duration_minutes": 121}
            )
        assert first.status == "approved"

    def test_nobody_acts_on_their_own_permit_and_decisions_are_final(self, school, principal_user):
        manager = _staff(school, 9, role="vice_admin")
        permit = _permit(school, manager, FEB, time(10, 0), time(11, 0), approve=None)
        assert permit.supervisor_role == "principal"  # rbac_roles.json:21-23

        with pytest.raises(PolicyError, match="4.1"):
            PermitService.act(permit, actor=manager, approve=True)

        PermitService.act(permit, actor=principal_user, approve=False, reason="تعارض مع حصة")
        permit.refresh_from_db()
        assert (permit.status, permit.rejected_stage, permit.rejection_reason) == (
            "rejected",
            "supervisor",
            "تعارض مع حصة",
        )
        with pytest.raises(PolicyError):
            PermitService.act(permit, actor=principal_user, approve=True)
        # المرفوضُ لا يحجز اليوم.
        assert _permit(school, manager, FEB, time(12, 0), time(12, 30)).status == "approved"

    def test_the_form_02_stages_run_in_order_and_only_the_last_deducts(self, school):
        teacher = _staff(school, 1)
        vice_academic, vice_admin = _actor(school, "vice_academic"), _actor(school, "vice_admin")
        secretary, principal = _actor(school, "secretary"), _actor(school, "principal")
        permit = _permit(school, teacher, FEB, time(12, 0), time(13, 30), approve=None)
        assert (permit.stage, permit.supervisor_role) == ("supervisor", "vice_academic")

        for outsider in (vice_admin, secretary, principal):  # ليست مرحلتَهم
            with pytest.raises(PolicyError, match="بانتظار"):
                PermitService.act(permit, actor=outsider, approve=True)

        PermitService.act(permit, actor=vice_academic, approve=True)
        permit.refresh_from_db()
        assert (permit.stage, permit.supervisor_by) == ("secretary", vice_academic)
        with pytest.raises(PolicyError, match="بانتظار"):
            PermitService.act(permit, actor=principal, approve=True)

        PermitService.act(permit, actor=secretary, approve=True)
        permit.refresh_from_db()
        assert (permit.stage, permit.secretary_by, permit.recorded_balance_minutes) == (
            "principal",
            secretary,
            420,
        )
        assert PermitService.balance(school, teacher, FEB).approved == 0  # 4.1: لم يُعتمد بعد

        PermitService.act(permit, actor=principal, approve=True)
        permit.refresh_from_db()
        assert (permit.status, permit.stage, permit.reviewed_by) == (
            "approved",
            "closed",
            principal,
        )
        assert PermitService.balance(school, teacher, FEB).approved == 90
        stages = [
            (log.action, (log.changes or {}).get("stage"))
            for log in AuditLog.objects.filter(object_id=str(permit.pk)).order_by("timestamp")
        ]
        assert stages == [
            ("create", None),
            ("update", "supervisor"),
            ("update", "secretary"),
            ("update", "principal"),
        ]

    def test_each_viewer_sees_only_the_requests_in_their_stage(self, school):
        teacher, observer = _staff(school, 1), _staff(school, 2, role="student_observer")
        for_academic = _permit(school, teacher, FEB, time(10, 0), time(11, 0), approve=None)
        for_admin = _permit(school, observer, FEB, time(10, 0), time(11, 0), approve=None)

        def waiting(role):
            return set(PermitService.awaiting(school, _actor(school, role)))

        assert waiting("vice_academic") == {for_academic}
        assert waiting("vice_admin") == {for_admin}  # rbac_roles.json:133 ملاحظ طلبة
        assert waiting("secretary") == waiting("principal") == set()
        PermitService.act(for_admin, actor=_actor(school, "vice_admin"), approve=True)
        assert waiting("secretary") == {for_admin}

    def test_a_role_the_job_cards_do_not_name_cannot_submit(self, school):
        accountant = _staff(school, 1, role="accountant")  # لا بطاقةَ «محاسب» في rbac_roles.json

        with pytest.raises(PolicyError, match="rbac_roles.json"):
            _permit(school, accountant, FEB, time(10, 0), time(11, 0), approve=None)

    def test_the_line_manager_table_is_the_source_reports_to(self):
        source = json.loads(
            Path("AAdocs/ministry_data/2026_2027/rbac_roles.json").read_text(encoding="utf-8")
        )
        reports_to = {r["title"]: r["reports_to"] for r in source["roles"]}
        deputy = {
            "مدير المدرسة": "principal",
            "نائب المدير للشؤون الإدارية وشؤون الطالب": "vice_admin",
            "نائب المدير للشؤون الأكاديمية": "vice_academic",
        }
        title_of = {
            "vice_admin": "نائب المدير للشؤون الإدارية وشؤون الطالب",
            "vice_academic": "نائب المدير للشؤون الأكاديمية",
            "secretary": "سكرتير مدرسة",
            "social_worker": "أخصائي اجتماعي",
            "psychologist": "أخصائي نفسي",
            "storekeeper": "أمين مخزن",
            "services_worker": "عامل خدمات",
            "lab_technician": "محضر مختبر",
            "support_companion": "مرافق الدعم",
            "it_technician": "مسؤول تقنية معلومات",
            "librarian": "مسؤول مركز مصادر التعلم",
            "admin_supervisor": "مشرف اداري",
            "canteen_supervisor": "مشرف مقصف",
            "ese_teacher": "معلم دعم تعليمي إضافي",
            "teacher": "معلم",
            "student_observer": "ملاحظ طلبة",
            "nurse": "ممرض",
            "messenger": "مندوب",
            "e_projects_coordinator": "منسق المشاريع الالكترونية",
            "coordinator": "منسق مادة",
            "receptionist": "موظف استقبال",
        }
        assert set(LINE_MANAGER) == set(title_of)
        assert set(LINE_MANAGER) <= {name for name, _ in Role.ROLES}
        for role, manager in LINE_MANAGER.items():
            assert deputy[reports_to[title_of[role]]] == manager, role

    def test_malformed_requests_are_refused(self, school):
        staff = _staff(school, 1)
        base = {"school": school, "staff": staff, "day": FEB, "reason": "سبب"}
        with pytest.raises(PolicyError):
            PermitService.submit(
                **base, permit_type="vacation", start_time=time(9), end_time=time(10)
            )
        with pytest.raises(PolicyError):
            PermitService.submit(
                **base, permit_type="during_day", start_time=time(10), end_time=time(9)
            )
        with pytest.raises(PolicyError):
            PermitService.submit(
                **{**base, "reason": "  "},
                permit_type="during_day",
                start_time=time(9),
                end_time=time(10),
            )


# ══════════════════════════════════════════════════════════════════════
#  التقرير الشهريّ — خمسةُ موظّفين بحسابٍ يدويّ
# ══════════════════════════════════════════════════════════════════════


class TestMonthlyReport:
    def test_five_staff_match_the_hand_computation(self, school, principal_user):
        a, b, c, d, e = (_staff(school, n) for n in range(1, 6))
        p = principal_user

        # (أ) ثلاثةُ أيّام حضور، ويومُ تأخّرٍ 7:25 ← 25 دقيقة.
        _mark(school, a, p, date(2026, 2, 1), "present", time(7, 0))
        _mark(school, a, p, date(2026, 2, 2), "present", time(6, 50))
        _mark(school, a, p, date(2026, 2, 3), "present")
        _mark(school, a, p, date(2026, 2, 4), "late", time(7, 25))
        # (ب) 8:59 ← 119، و9:00 ← 120 (تأخّرٌ لا غياب)، و9:01 ← غياب.
        _mark(school, b, p, date(2026, 2, 1), "late", time(8, 59))
        _mark(school, b, p, date(2026, 2, 2), "late", time(9, 0))
        _mark(school, b, p, date(2026, 2, 3), "absent", time(9, 1))
        # (ج) إذنُ تأخيرٍ 7:00–8:30 (90) وحضر 8:15 ← مستأذن؛ وإذنُ خروجٍ 12:00–14:00 (120)
        #     وحضر 6:55 ← حاضر؛ وطلبٌ معلَّقٌ 60 دقيقة لا يُحسب.
        _permit(school, c, date(2026, 2, 3), time(7, 0), time(8, 30), "late_arrival")
        _mark(school, c, p, date(2026, 2, 3), "permitted", time(8, 15))
        _permit(school, c, date(2026, 2, 4), time(12, 0), time(14, 0), "early_departure")
        _mark(school, c, p, date(2026, 2, 4), "present", time(6, 55))
        _permit(school, c, date(2026, 2, 5), time(10, 0), time(11, 0), approve=None)
        # (د) يوما غياب، وإذنٌ مرفوضٌ 60 دقيقة لا يُحسب.
        _mark(school, d, p, date(2026, 2, 1), "absent")
        _mark(school, d, p, date(2026, 2, 2), "absent")
        _permit(school, d, date(2026, 2, 10), time(10, 0), time(11, 0), approve=False)
        # (هـ) لا رصد؛ إذنٌ معتمدٌ 60 في فبراير يُحسب بلا رصد، وإذنُ يناير 120 لا يُحسب.
        _permit(school, e, date(2026, 1, 29), time(10, 0), time(12, 0))
        _permit(school, e, date(2026, 2, 20), time(10, 0), time(11, 0))

        report = StaffAttendanceService.monthly_report(school, 2026, 2)
        rows = {r["employee_number"]: r for r in report["rows"]}

        #          حاضر متأخّر غائب مستأذن دقائقُ التأخّر دقائقُ الإذن المتبقّي
        expected = {
            "T-0001": (3, 1, 0, 0, 25, 0, 420),
            "T-0002": (0, 2, 1, 0, 239, 0, 420),
            "T-0003": (1, 0, 0, 1, 0, 210, 210),
            "T-0004": (0, 0, 2, 0, 0, 0, 420),
            "T-0005": (0, 0, 0, 0, 0, 60, 360),
        }
        keys = (
            "present",
            "late",
            "absent",
            "permitted",
            "late_minutes",
            "permit_minutes",
            "permit_remaining",
        )
        for number, values in expected.items():
            assert tuple(rows[number][k] for k in keys) == values, number
        # والمديرُ والنائبُ الأكاديميّ والسكرتيرُ (أصحابُ المراحل) من الكادر: ثلاثةُ صفوفٍ أصفار.
        assert len(report["rows"]) == 8
        assert report["totals"] == {
            "present": 4,
            "late": 3,
            "absent": 3,
            "permitted": 1,
            "late_minutes": 264,
            "permit_minutes": 270,
        }
        assert (report["first"], report["last"]) == (date(2026, 2, 1), date(2026, 2, 28))
        assert MONTHLY_PERMIT_CAP == 420

    def test_the_workbook_carries_the_employee_number_not_the_personal_one(self, school):
        staff = _staff(school, 7)
        report = StaffAttendanceService.monthly_report(school, 2026, 2)
        ws = StaffAttendanceService.monthly_workbook(report).active

        values = [c for row in ws.iter_rows(values_only=True) for c in row]
        assert ws.cell(1, 1).value == "الرقم الوظيفي"
        assert "T-0007" in values
        assert staff.national_id not in values

    def test_the_daily_board_counts_every_status_and_the_unmarked(self, school, principal_user):
        a, b = _staff(school, 1), _staff(school, 2)
        _mark(school, a, principal_user, FEB, "late", time(7, 5))

        board = StaffAttendanceService.daily_board(school, FEB)

        assert board["counts"] == {
            "present": 0,
            "late": 1,
            "absent": 0,
            "permitted": 0,
            "unmarked": 2,
        }
        assert {row["staff"].pk for row in board["rows"]} == {a.pk, b.pk, principal_user.pk}


# ══════════════════════════════════════════════════════════════════════
#  الشاشات — الحراسةُ والتدقيق
# ══════════════════════════════════════════════════════════════════════


class TestScreens:
    def test_the_secretary_records_and_the_deputies_read_the_report(
        self, client, school, teacher_user, principal_user
    ):
        board, report = (
            reverse("staff_affairs:attendance_board"),
            reverse("staff_affairs:attendance_report"),
        )
        expected = {  # 03:101 السكرتير يرصد، والنائبان يقرآن للتقييم (06b:178)
            "teacher": (teacher_user, False, False),
            "principal": (principal_user, True, True),
            "secretary": (_actor(school, "secretary"), True, True),
            "vice_admin": (_actor(school, "vice_admin"), False, True),
            "vice_academic": (_actor(school, "vice_academic"), False, True),
        }
        for role, (user, can_record, can_read) in expected.items():
            client.force_login(user)
            assert (client.get(board).status_code == 200) is can_record, role
            assert (client.get(report).status_code == 200) is can_read, role

    def test_a_click_marks_and_returns_the_row(self, client_as, school, principal_user):
        staff = _staff(school, 1)
        client = client_as(principal_user)
        url = reverse("staff_affairs:attendance_mark")

        ok = client.post(
            url, {"staff_id": staff.pk, "date": "2026-02-02", "status": "late", "check_in": "07:40"}
        )
        refused = client.post(
            url,
            {"staff_id": staff.pk, "date": "2026-02-03", "status": "present", "check_in": "09:30"},
        )

        assert ok.status_code == 200 and f"sa-att-{staff.pk}" in ok.content.decode()
        assert StaffAttendance.objects.get(date=date(2026, 2, 2)).late_minutes == 40
        assert "غائب" in refused.content.decode()
        assert not StaffAttendance.objects.filter(date=date(2026, 2, 3)).exists()

    def test_another_schools_staff_cannot_be_marked(self, client_as, school, principal_user):
        from tests.conftest import SchoolFactory

        outsider = _staff(SchoolFactory(), 3)
        response = client_as(principal_user).post(
            reverse("staff_affairs:attendance_mark"),
            {"staff_id": outsider.pk, "date": "2026-02-02", "status": "present"},
        )
        assert response.status_code == 404

    def test_the_report_and_its_excel_are_audited(self, client_as, school, principal_user):
        _staff(school, 1)
        client = client_as(principal_user)

        page = client.get(reverse("staff_affairs:attendance_report"), {"month": "2026-02"})
        xlsx = client.get(reverse("staff_affairs:attendance_report_xlsx"), {"month": "2026-02"})

        assert page.status_code == 200 and "T-0001" in page.content.decode()
        assert xlsx.status_code == 200
        assert "spreadsheetml" in xlsx["Content-Type"]
        log = AuditLog.objects.get(action="export")
        assert log.changes == {
            "kind": "staff_affairs.attendance_month_xlsx",
            "rows": 2,
            "full_national_id": False,
        }

    def test_a_teacher_requests_for_themself_and_the_three_stages_act_from_their_queue(
        self, client_as, school, teacher_user, principal_user
    ):
        mine = reverse("staff_affairs:my_permits")
        teacher = client_as(teacher_user)
        assert teacher.get(mine).status_code == 200
        response = teacher.post(
            mine,
            {
                "permit_type": "early_departure",
                "date": "2026-02-02",
                "start_time": "12:30",
                "end_time": "14:00",
                "reason": "موعد طبي",
            },
        )
        assert response.status_code == 302
        refused = teacher.post(
            mine,
            {
                "permit_type": "during_day",
                "date": "2026-02-02",
                "start_time": "09:00",
                "end_time": "09:30",
                "reason": "آخر",
            },
        )
        assert "4.3" in refused.content.decode()
        queue = reverse("staff_affairs:permit_queue")
        assert teacher.get(queue).status_code in (302, 403)

        permit = PermitRequest.objects.get(staff=teacher_user)
        review = reverse("staff_affairs:permit_review", args=[permit.pk])
        for role in ("vice_academic", "secretary", "principal"):
            staff_client = client_as(_actor(school, role))
            assert "موعد طبي" in staff_client.get(queue).content.decode(), role
            staff_client.post(review, {"decision": "approve"})

        permit.refresh_from_db()
        assert (permit.status, permit.reviewed_by, permit.duration_minutes) == (
            "approved",
            principal_user,
            90,
        )
        assert AuditLog.objects.filter(object_id=str(permit.pk), action="update").exists()

    def test_students_cannot_request_permits(self, client_as, student_user):
        response = client_as(student_user).get(reverse("staff_affairs:my_permits"))
        assert response.status_code in (302, 403)

"""حضورُ الموظّفين والأذوناتُ القصيرة — قاعدةً قاعدةً من المواصفة.

المرجعُ الحاكم: ``docs/compliance/staff_attendance_spec.md`` (م-1 … م-36)، وكلُّ اختبارٍ
هنا يسمّي رقمَ القاعدة وموضعَها في المصدر:

    السياسة (``data/2026-2027/05-السياسات الداخلية/01-2027 سياسة وضوابط الحضور
    والانصراف.pdf``، ت/د 01/2027 بتاريخ 2026-08-23، صفحتان):
      1.1 «يبدأ الدوام الرسمي لموظفي المدرسة من الساعة السابعة صباحاً وينتهي في تمام
          الثانية ظهراً»
      2.1 «يعتبر الموظف متأخراً إذا حضر بعد الساعة 7:00 صباحاً»
      2.4 «يعتبر الموظف غائبا إذا حضر بعد الساعة التاسعة صباحاً دون إذن أو عذر مقبول»
      4.1 «لا يجوز الاعتداد بالإذن الا بعد اعتماده من الرئيس المباشر»
      4.2 «يكون الحد الأقصى للأذونات بواقع (7) ساعات في الشهر»
      4.3 «لا يجوز الاذن أكثر من مرة واحدة في اليوم الواحد»
      4.4 «يكون الحد الاقصى للإذن ساعتين في المرة الواحدة»
      5.1 «سيتم الخصم من الراتب بعد اشعار الموظف على البريد الالكتروني بداية كل شهر
          بتقرير أيام الغياب عن الشهر السابق»
      5.3 «يجب على الموظف تغطيه أيام غيابه قبل يوم (15) من الشهر وإلا يتم تنفيذ الخصم»

    نموذج 02 (``07-نماذج المدرسة/02) نموذج طلب تأخير - استئذان - خروج مبكر.pdf`` ص1):
      مربّعاتُه بالترتيب — بيانات الموظّف، «استخدام السكرتارية» (رصيد الساعات، الاسم،
      توقيت تقديم)، «استخدام المسؤول المباشر والنائب المسؤول» عمودين، «استخدام
      الإدارة»، «مدير المدرسة». وحاشيتُه: «في حال تقديم الطلب فإنه يتعين على الموظف عدم
      الخروج إلا بعد اعتماده وإخطاره من قبل السكرتارية بالموافقة على طلب الاجازة»،
      و«لا يعتبر الطلب معتمداً الا باعتماد مدير المدرسة وتوقيعه عليه».

    نموذج 03 (``07-نماذج المدرسة/03) نموذج طلب.pdf`` ص1): «يجب ارفاق مع طلب استثناء
      الخروج المبكر أو التأخير الصباحي ما يثبت حاجة الموظف لذلك»، و«استخدام مدير
      المدرسة: التغذية الراجعة … تاريخ التغذية الراجعة».

    البطاقات (``02- شؤون الموظفين/05- الوصف الوظيفي/*.pdf``): «المسؤول المباشر» في
      ترويسة كلّ بطاقة (م-21)، وبطاقةُ نائب الشؤون الإدارية وحدَها فيها «الإنابة عن
      المدير في مهامه في حال غيابه» (م-24).

والأشخاصُ هنا اصطناعيّون: لا رقمَ شخصيّاً يُكتب، والرقمُ الوظيفيُّ «T-000n».
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from datetime import date, datetime, time
from pathlib import Path

import pytest
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import AuditLog
from core.models.access import Membership, Role
from staff_affairs.attendance import (
    LINE_MANAGER,
    MONTHLY_PERMIT_CAP,
    PERMIT_MAX_MINUTES,
    WORK_END,
    WORK_START,
    PermitService,
    PolicyError,
    StaffAttendanceService,
    classify_arrival,
    coverage_deadline,
    minutes_between,
)
from staff_affairs.models import PERMIT_STAGES, PERMIT_TYPES, PermitRequest, StaffAttendance
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

FEB = date(2026, 2, 1)
MORNING = time(6, 0)

#: «الآن» في الخدمة أثناء الاختبارات — منتصفُ فبراير، فأيّامُ الرصد قبله وشهرُه مفتوح.
DEFAULT_NOW = datetime(2026, 2, 15, 12, 0)
_CLOCK = {"now": DEFAULT_NOW}


@pytest.fixture(autouse=True)
def _service_clock(monkeypatch):
    """ساعةُ الخدمة مضبوطة: الإذنُ يُحكم بتاريخه من «الآن» (م-18أ وم-18ب)."""
    from django.utils import timezone

    import staff_affairs.attendance as attendance_module

    _CLOCK["now"] = DEFAULT_NOW
    monkeypatch.setattr(
        attendance_module,
        "_now",
        lambda: timezone.localtime(timezone.make_aware(_CLOCK["now"])),
        raising=False,
    )


@contextmanager
def _at(moment):
    """لحظةٌ بعينها للتقديم والاعتماد — ثمّ تعود الساعة."""
    before = _CLOCK["now"]
    _CLOCK["now"] = moment
    try:
        yield
    finally:
        _CLOCK["now"] = before


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


#: صاحبُ كلّ مربّعٍ بصفته الطبيعيّة — لتُكمَل مدرسةُ الاختبار به فلا يُختبر هنا الرفعُ (م-28).
NATURAL = {
    "secretary": "secretary",  # pragma: allowlist secret
    "external": "secretary",  # pragma: allowlist secret
    "principal": "principal",
}


def _through(permit, approve=True, reason="غير مناسب"):
    """يمرّ الطلبُ بمربّعات نموذج 02 كلِّها صباحَ يومه — أو يُرفض في أوّل مربّع قرار.

    والسكرتاريةُ تُثبت الرصيد ولا تقرّر (م-19)، فالرفضُ يبدأ من المربّع الذي بعدها.
    """
    with _at(datetime.combine(permit.date, MORNING)):
        while permit.status == "pending":
            _actor(permit.school, NATURAL.get(permit.stage, permit.deputy_role or "principal"))
            actor = PermitService.eligible_actors(permit)[0]
            note = "بريد رئيس المدير" if permit.stage == "external" and approve else reason
            PermitService.act(
                permit,
                actor=actor,
                approve=approve or permit.stage == "secretary",
                reason=note,
            )
            permit.refresh_from_db()
    return permit


def _permit(school, staff, day, start, end, kind="during_day", approve=True):
    """طلبٌ يُقدَّم صباحَ يومه قبل وقته (م-18ب) — ويمرّ بمربّعاته إن طُلب."""
    with _at(datetime.combine(day, MORNING)):
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


def _assign(school, principal, assignee, start=None, end=None):
    """تكليفُ المدير موظّفاً بأعباء وظيفته اليومَ (م-43) — قرارُ المدرسة."""
    from staff_affairs.attendance import AssignmentService

    day = DEFAULT_NOW.date()
    return AssignmentService.assign(
        school=school,
        assigner=principal,
        assignee=assignee,
        start=start or day,
        end=end or day,
        reason="غيابُ المدير في مهمّة",
    )


def _mark(school, staff, actor, day, status, check_in=None):
    return StaffAttendanceService.mark(
        school=school, staff=staff, day=day, status=status, actor=actor, check_in=check_in
    )


def _eligible(permit):
    return {user.pk for user in PermitService.eligible_actors(permit)}


def _evidence():
    """مرفقُ نموذج 03 (م-31) — ملفٌّ اصطناعيّ."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile("evidence.pdf", b"%PDF-1.4 synthetic", content_type="application/pdf")


def _exception(school, staff, principal, kind, start, end, boundary, approve=True):
    """استثناءُ نموذج 03 — يقرّره المديرُ وحدَه بتغذيةٍ راجعة (م-29 وم-31)."""
    from staff_affairs.attendance import ExceptionService

    request = ExceptionService.submit(
        school=school,
        staff=staff,
        exception_type=kind,
        start_date=start,
        end_date=end,
        boundary=boundary,
        content="ظرفٌ لأيّام",
        evidence="تقرير",
        evidence_file=_evidence(),
    )
    if approve is not None:
        ExceptionService.decide(
            request, actor=principal, approve=approve, feedback="اطّلعتُ على المرفق"
        )
    return request


# ══════════════════════════════════════════════════════════════════════
#  التصنيف — م-3 وم-4 وم-5 وم-6
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
        """م-3 وم-4 (السياسة 2.1 و2.4): «بعد» تعني ما جاوز الحدّ لا الحدَّ نفسَه."""
        assert classify_arrival(check_in) == expected

    def test_seconds_are_dropped_to_the_whole_minute(self):
        """م-2 (صامت، اختيارٌ هندسيّ): المقارنةُ بالدقيقة — 07:00:59 سابعةٌ تماماً، و09:00:59
        تاسعةٌ تماماً؛ وحدّا م-3 وم-4 من السياسة 2.1 و2.4."""
        assert classify_arrival(time(7, 0, 59)) == ("present", 0)
        assert classify_arrival(time(7, 1, 0)) == ("late", 1)
        assert classify_arrival(time(9, 0, 59)) == ("late", 120)
        assert classify_arrival(time(9, 1, 30)) == ("absent", 0)

    def test_an_approved_late_arrival_permit_covers_its_window_only(self):
        """م-5: التغطيةُ تغطّي نافذتَها وحدَها — والحضورُ بعدها وبعد التاسعة غياب."""
        assert classify_arrival(time(8, 40), covered_until=time(9, 0)) == ("permitted", 0)
        assert classify_arrival(time(8, 40), covered_until=time(8, 30)) == ("late", 10)
        assert classify_arrival(time(9, 1), covered_until=time(9, 0)) == ("absent", 0)
        # 2.4 «أو عذر مقبول»: العذرُ يجعل الحضورَ بعد التاسعة تأخّراً بدقائقه من نهاية إذنه.
        assert classify_arrival(time(9, 30), covered_until=time(9, 0), excused=True) == ("late", 30)

    @pytest.mark.parametrize(
        ("covered_until", "check_in", "excused", "expected"),
        [
            (time(8, 0), time(13, 0), False, ("absent", 0)),  # إذن 07:00–08:00
            (time(9, 0), time(9, 1), False, ("absent", 0)),
            (time(9, 0), time(9, 30), True, ("late", 30)),
            (time(9, 30), time(9, 20), False, ("permitted", 0)),  # استثناء ن03
            (time(9, 30), time(9, 45), False, ("absent", 0)),
        ],
    )
    def test_the_binding_table_of_rule_four(self, covered_until, check_in, excused, expected):
        """م-5: الأمثلةُ الخمسةُ الملزمة في جدول المواصفة."""
        assert classify_arrival(check_in, covered_until, excused) == expected

    def test_minutes_are_counted_from_the_end_of_the_cover(self):
        """م-6: الدقائقُ من الأكبر بين 7:00 ونهاية التغطية — فلا تُعدّ مرّتين."""
        assert classify_arrival(time(8, 40), covered_until=time(8, 0)) == ("late", 40)
        assert classify_arrival(time(9, 30), excused=True) == ("late", 150)

    def test_minutes_between_is_whole_minutes_and_never_negative(self):
        assert minutes_between(time(7, 0), time(8, 30)) == 90
        assert minutes_between(time(9, 0), time(8, 0)) == 0

    def test_the_official_day_is_seven_to_two(self):
        """م-1 (السياسة 1.1): «من الساعة السابعة صباحاً وينتهي في تمام الثانية ظهراً»."""
        assert (WORK_START, WORK_END) == (time(7, 0), time(14, 0))


# ══════════════════════════════════════════════════════════════════════
#  الرصد
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
        """م-17: لا أثرَ للإذن قبل الاعتماد النهائيّ، وبه يصير الحضورُ في نافذته «مستأذناً»."""
        staff = _staff(school, 1)
        pending = _permit(school, staff, FEB, time(7, 0), time(8, 30), "late_arrival", approve=None)
        with pytest.raises(PolicyError, match="متأخّر"):
            _mark(school, staff, principal_user, FEB, "permitted", time(8, 15))

        _through(pending)
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
        _permit(school, staff, FEB, time(13, 0), time(14, 0), "early_departure")

        record.refresh_from_db()
        assert record.permit_minutes == 60


# ══════════════════════════════════════════════════════════════════════
#  الأذونات — م-12 … م-20
# ══════════════════════════════════════════════════════════════════════


class TestPermits:
    def test_the_three_types_are_the_form_types(self):
        """م-12: «نوع الطلب: تأخير — استئذان — خروج مبكر» (ن02، والسياسة عنوان البند 4)."""
        assert [key for key, _label in PERMIT_TYPES] == [
            "late_arrival",
            "during_day",
            "early_departure",
        ]

    def test_a_permit_within_the_cap_deducts_exactly_its_minutes_on_approval(
        self, school, principal_user
    ):
        """م-17 وم-15: المعلَّقُ يُعرض ولا يخصم، والاعتمادُ النهائيّ وحدَه يخصم."""
        staff = _staff(school, 1)
        permit = _permit(school, staff, FEB, time(10, 0), time(11, 15), approve=None)

        pending = PermitService.balance(school, staff, FEB)
        assert (pending.approved, pending.pending, pending.remaining) == (0, 75, 600)

        _through(permit)
        after = PermitService.balance(school, staff, FEB)
        assert (after.approved, after.pending, after.remaining) == (75, 0, 525)

    def test_three_hours_passes_and_one_minute_more_needs_a_written_approval(self, school):
        """م-13 (م.79/3 من قانون 15/2016): 180 دقيقة جائزة، وما فوقها يُعلَّم ولا يُعتمد بلا مرجع."""
        staff = _staff(school, 1)
        assert PERMIT_MAX_MINUTES == 180
        within = _permit(school, staff, FEB, time(10, 0), time(13, 0))
        assert within.over_limit is False

        over = _permit(school, staff, date(2026, 2, 2), time(10, 0), time(13, 1), approve=None)
        assert over.over_limit is True
        with _at(datetime(2026, 2, 2, 6, 0)):
            PermitService.act(over, actor=_actor(school, "secretary"), approve=True)
            PermitService.act(over, actor=_actor(school, "vice_academic"), approve=True)
            principal = _actor(school, "principal")
            with pytest.raises(PolicyError, match="موافقةٍ كتابيّة"):
                PermitService.act(over, actor=principal, approve=True)
            over.refresh_from_db()
            assert (over.status, over.stage) == ("pending", "principal")
            PermitService.act(over, actor=principal, approve=True, written_approval="كتاب 12/2026")
        over.refresh_from_db()
        assert (over.status, over.written_approval_ref) == ("approved", "كتاب 12/2026")

    def test_a_permit_that_exceeds_the_monthly_cap_is_flagged_not_refused(
        self, school, principal_user
    ):
        """م-15 (م.79/3): 600 دقيقةً في شهر تاريخ الإذن، وما فوقها يُعلَّم؛ والشهرُ التالي رصيدٌ جديد."""
        staff = _staff(school, 1)
        for day in (2, 3, 4):  # 3 × 180 = 540
            _permit(school, staff, date(2026, 2, day), time(10, 0), time(13, 0))
        within = _permit(school, staff, date(2026, 2, 5), time(10, 0), time(11, 0))
        assert PermitService.balance(school, staff, FEB).remaining == 0  # 600 كاملةً بلا موافقة
        assert within.over_limit is False

        over = _permit(school, staff, date(2026, 2, 9), time(10, 0), time(10, 1), approve=None)
        assert over.over_limit is True
        assert (
            _permit(school, staff, date(2026, 3, 1), time(10, 0), time(13, 0)).over_limit is False
        )

    def test_pending_requests_count_against_the_cap_at_submission(self, school, principal_user):
        """م-16 وم-15 (م.79/3): عند التقديم يُحسب المعتمدُ ومعه قيدُ الإجراء — فيُعلَّم ما جاوز."""
        staff = _staff(school, 1)
        for day in (2, 3, 4):  # 3 × 180 معلَّقة
            _permit(
                school, staff, date(2026, 2, day), time(7, 0), time(10, 0), "late_arrival", None
            )
        flagged = _permit(
            school, staff, date(2026, 2, 5), time(7, 0), time(8, 1), "late_arrival", None
        )
        assert flagged.over_limit is True

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
            deputy_role="vice_academic",
        )

    def test_the_secretary_records_the_balance_and_does_not_decide(self, school):
        """م-19: مربّعُ السكرتارية إثباتُ رصيدٍ واسمٍ وتوقيت — لا قرارَ فيه ولا خصم."""
        staff = _staff(school, 1)
        for day in (2, 3, 4):  # 360 معتمدة
            _permit(school, staff, date(2026, 2, day), time(10, 0), time(12, 0))
        waiting = _permit(school, staff, date(2026, 2, 9), time(10, 0), time(11, 0), approve=None)
        secretary = _actor(school, "secretary")

        with _at(datetime(2026, 2, 9, 6, 0)):
            with pytest.raises(PolicyError, match="لا تقرّر"):
                PermitService.act(waiting, actor=secretary, approve=False, reason="لا رصيد")
            PermitService.act(waiting, actor=secretary, approve=True)

        waiting.refresh_from_db()
        assert (waiting.stage, waiting.status) == ("supervisor", "pending")
        assert (waiting.recorded_balance_minutes, waiting.secretary_by) == (240, secretary)
        assert PermitService.balance(school, staff, FEB).approved == 360  # لا خصمَ بعد

    def test_the_principal_rechecks_the_cap_before_approving(self, school):
        """م-16 وم-15 (م.79/3): عند الاعتماد النهائيّ يُعاد الفحصُ على المعتمَد وحدَه."""
        staff = _staff(school, 1)
        for day in (2, 3, 4):  # 3 × 180 = 540 معتمدة
            _permit(school, staff, date(2026, 2, day), time(10, 0), time(13, 0))
        waiting = _permit(school, staff, date(2026, 2, 9), time(10, 0), time(10, 30), approve=None)
        assert waiting.over_limit is False  # 540 + 30 = 570 ≤ 600 يومَ التقديم
        with _at(datetime(2026, 2, 9, 6, 0)):
            PermitService.act(waiting, actor=_actor(school, "secretary"), approve=True)
            PermitService.act(waiting, actor=_actor(school, "vice_academic"), approve=True)
            waiting.refresh_from_db()
            assert (waiting.stage, waiting.recorded_balance_minutes) == ("principal", 60)
            self._approved_elsewhere(school, staff, date(2026, 2, 10))  # +60 ← 600

            principal = _actor(school, "principal")
            with pytest.raises(PolicyError, match="موافقةٍ كتابيّة"):  # 600 + 30 = 630
                PermitService.act(waiting, actor=principal, approve=True)
        waiting.refresh_from_db()
        assert (waiting.status, waiting.stage) == ("pending", "principal")

    def test_one_permit_per_day(self, school, principal_user):
        """م-14 (السياسة 4.3): «لا يجوز الاذن أكثر من مرة واحدة في اليوم الواحد»."""
        staff = _staff(school, 1)
        _permit(school, staff, FEB, time(7, 0), time(7, 30), "late_arrival")

        with pytest.raises(PolicyError, match="4.3"):
            _permit(school, staff, FEB, time(13, 30), time(14, 0), "early_departure")

    def test_the_database_holds_one_approved_per_day_and_the_workday_ceiling(
        self, school, principal_user
    ):
        staff = _staff(school, 1)
        first = _permit(school, staff, FEB, time(7, 0), time(7, 30), "late_arrival")
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
                **{**fields, "date": date(2026, 2, 2), "duration_minutes": 421}
            )
        assert first.status == "approved"

    def test_nobody_acts_on_their_own_permit_and_decisions_are_final(self, school, principal_user):
        """م-19 وم-20: لا أحدَ في طلبه، والرفضُ ينهيه، والمرفوضُ لا يحجز يومَه (م-14)."""
        manager = _staff(school, 9, role="vice_admin")
        permit = _permit(school, manager, FEB, time(7, 0), time(8, 0), "late_arrival", approve=None)
        assert permit.deputy_role == "principal"  # م-21: النائبان مسؤولُهما المدير

        with pytest.raises(PolicyError, match="4.1"):
            PermitService.act(permit, actor=manager, approve=True)

        PermitService.act(permit, actor=principal_user, approve=True)  # مربّع السكرتارية
        permit.refresh_from_db()
        assert permit.stage == "principal"  # م-19 (3): خطوةُ المسؤول مدمجةٌ في مربّع المدير
        PermitService.act(permit, actor=principal_user, approve=False, reason="تعارض مع حصة")
        permit.refresh_from_db()
        assert (permit.status, permit.rejected_stage, permit.rejection_reason) == (
            "rejected",
            "principal",
            "تعارض مع حصة",
        )
        with pytest.raises(PolicyError):
            PermitService.act(permit, actor=principal_user, approve=True)
        assert _permit(school, manager, FEB, time(12, 0), time(12, 30)).status == "approved"

    def test_the_form_02_boxes_run_in_the_order_of_the_paper(self, school):
        """م-19: السكرتارية ← المسؤول المباشر والنائب المسؤول ← مدير المدرسة."""
        teacher = _staff(school, 1)
        vice_academic, vice_admin = _actor(school, "vice_academic"), _actor(school, "vice_admin")
        secretary, principal = _actor(school, "secretary"), _actor(school, "principal")
        permit = _permit(school, teacher, FEB, time(12, 0), time(13, 30), approve=None)
        assert (permit.stage, permit.deputy_role) == ("secretary", "vice_academic")

        with _at(datetime.combine(FEB, MORNING)):
            for outsider in (vice_admin, vice_academic):  # ليست مرحلتَهم
                with pytest.raises(PolicyError, match="بانتظار"):
                    PermitService.act(permit, actor=outsider, approve=True)

            PermitService.act(permit, actor=secretary, approve=True)
            permit.refresh_from_db()
            assert (permit.stage, permit.secretary_by, permit.recorded_balance_minutes) == (
                "supervisor",
                secretary,
                600,
            )
            with pytest.raises(PolicyError, match="بانتظار"):
                PermitService.act(permit, actor=principal, approve=True)

            PermitService.act(permit, actor=vice_academic, approve=True)
            permit.refresh_from_db()
            # عمودا الورقة بتوقيعٍ واحدٍ لأنّ صاحبَهما واحد (م-19 وم-21).
            assert (permit.stage, permit.supervisor_by, permit.deputy_by) == (
                "principal",
                vice_academic,
                vice_academic,
            )
            assert PermitService.balance(school, teacher, FEB).approved == 0  # م-17

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
            ("update", "secretary"),
            ("update", "supervisor"),
            ("update", "principal"),
        ]

    def test_the_stage_list_follows_the_paper(self):
        """م-19: ``PERMIT_STAGES`` بترتيب مربّعات الورقة ([ن02] ص1)، ومنسّقُ المادّة قبل النائب."""
        assert [key for key, _label in PERMIT_STAGES][:4] == [
            "secretary",
            "coordinator",
            "supervisor",
            "principal",
        ]

    def test_each_viewer_sees_only_the_requests_in_their_stage(self, school):
        teacher, observer = _staff(school, 1), _staff(school, 2, role="student_observer")
        for_academic = _permit(
            school, teacher, FEB, time(7, 0), time(8, 0), "late_arrival", approve=None
        )
        for_admin = _permit(
            school, observer, FEB, time(7, 0), time(8, 0), "late_arrival", approve=None
        )
        secretary = _actor(school, "secretary")

        def waiting(role):
            return set(PermitService.awaiting(school, _actor(school, role)))

        assert waiting("secretary") == {for_academic, for_admin}
        assert waiting("vice_academic") == waiting("vice_admin") == set()
        for permit in (for_academic, for_admin):
            PermitService.act(permit, actor=secretary, approve=True)
        assert waiting("vice_academic") == {for_academic}
        assert waiting("vice_admin") == {for_admin}  # rbac_roles.json:133 ملاحظ طلبة
        assert waiting("principal") == set()

    def test_a_role_the_job_cards_do_not_name_goes_to_the_principal(self, school):
        """م-22: لا بطاقةَ «محاسب» — فمسؤولُه المدير، ولا يُرفض طلبُه."""
        accountant = _staff(school, 1, role="accountant")

        permit = _permit(school, accountant, FEB, time(10, 0), time(11, 0), approve=None)
        assert (permit.deputy_role, permit.status) == ("principal", "pending")

    def test_the_line_manager_table_is_the_job_cards(self):
        """م-21: «المسؤول المباشر» في ترويسة البطاقات — ويوافقه «reports_to»."""
        by_card = {
            "vice_academic": (
                "teacher",
                "ese_teacher",
                "coordinator",
                "e_projects_coordinator",
                "lab_technician",
                "librarian",
            ),
            "vice_admin": (
                "admin_supervisor",
                "services_worker",
                "storekeeper",
                "it_technician",
                "receptionist",
                "messenger",
                "nurse",
                "student_observer",
                "canteen_supervisor",
                "support_companion",
                "social_worker",
                "psychologist",
            ),
            "principal": ("secretary", "vice_admin", "vice_academic"),
        }
        for manager, roles in by_card.items():
            for role in roles:
                assert LINE_MANAGER[role] == manager, role
        assert set(LINE_MANAGER) == {role for roles in by_card.values() for role in roles}

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
#  التقرير الشهريّ — م-36 … م-36
# ══════════════════════════════════════════════════════════════════════


class TestMonthlyReport:
    def test_five_staff_match_the_hand_computation(self, school, principal_user):
        a, b, c, d, e = (_staff(school, n) for n in range(1, 6))
        p = principal_user

        # (أ) ثلاثةُ أيّام حضور، ويومُ تأخّرٍ 7:25 ← 25 دقيقة.
        _mark(school, a, p, date(2026, 2, 1), "present", time(7, 0))
        _mark(school, a, p, date(2026, 2, 2), "present", time(6, 50))
        _mark(school, a, p, date(2026, 2, 3), "present", time(6, 40))
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
        _permit(school, c, date(2026, 2, 5), time(7, 0), time(8, 0), "late_arrival", approve=None)
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
            "T-0001": (3, 1, 0, 0, 25, 0, 600),
            "T-0002": (0, 2, 1, 0, 239, 0, 600),
            "T-0003": (1, 0, 0, 1, 0, 210, 390),
            "T-0004": (0, 0, 2, 0, 0, 0, 600),
            "T-0005": (0, 0, 0, 0, 0, 60, 540),
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
            "absent_uncovered": 3,
            "covered_late": 0,
            "exception_days": 0,
            "late_minutes": 264,
            "early_leave_minutes": 0,
            "permit_minutes": 270,
        }
        assert (report["first"], report["last"]) == (date(2026, 2, 1), date(2026, 2, 28))
        assert MONTHLY_PERMIT_CAP == 600

    def test_the_workbook_carries_the_employee_number_not_the_personal_one(self, school):
        """م-36 (السياسة 5.1): تقريرُ الشهر بالرقم الوظيفيّ — ولا رقمَ شخصيّاً فيه."""
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
        expected = {
            "teacher": (teacher_user, False, False),
            "principal": (principal_user, True, True),
            "secretary": (_actor(school, "secretary"), True, True),
            # تُفتح له الشاشةُ بلا كادرٍ حتّى تقوم الإنابة (م-24؛ جولة 4، TestRoundFour).
            "vice_admin": (_actor(school, "vice_admin"), True, True),
            # والنائبُ الأكاديميّ يفتحها لأكاديميّيه وحدَهم (قرارُ 2026-09-19: يقبل عذرَهم).
            "vice_academic": (_actor(school, "vice_academic"), True, True),
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

    def test_a_teacher_requests_for_themself_and_the_three_boxes_act_from_their_queue(
        self, client_as, school, teacher_user, principal_user
    ):
        with _at(datetime(2026, 2, 1, 6, 0)):  # قبل الخروج (حاشية نموذج 02)
            self._request_and_approve(client_as, school, teacher_user, principal_user)

    @staticmethod
    def _request_and_approve(client_as, school, teacher_user, principal_user):
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
        for role in ("secretary", "vice_academic", "principal"):
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


# ══════════════════════════════════════════════════════════════════════
#  جولتا الإصلاح 1 و2 — العيوبُ التي عولجت قبلُ، بأحكام المواصفة الآن
# ══════════════════════════════════════════════════════════════════════


def _hrefs(response, prefix="/staff-affairs/"):
    return set(re.findall(rf'href="({prefix}[^"?#]*)', response.content.decode()))


class TestEarlierRounds:
    # ── الاعتمادُ بعد الرصد يُعيد تصنيفَ اليوم ────────────────────────────
    def test_approving_after_marking_reclassifies_the_day(self, school, principal_user):
        staff = _staff(school, 1)
        permit = _permit(school, staff, FEB, time(7, 0), time(8, 30), "late_arrival", approve=None)
        record = _mark(school, staff, principal_user, FEB, "late", time(8, 15))
        assert (record.status, record.late_minutes) == ("late", 75)

        _through(permit)

        record.refresh_from_db()
        assert (record.status, record.late_minutes, record.permit_minutes) == ("permitted", 0, 90)
        assert AuditLog.objects.filter(
            object_id=str(record.pk), changes__status=["late", "permitted"]
        ).exists()

    # ── م-5: الإذنُ يغطّي نافذتَه، وما بعدها تأخّرٌ أو غياب ────────────────
    def test_a_short_late_permit_counts_the_minutes_after_its_end(self):
        assert classify_arrival(time(12, 30), covered_until=time(7, 15)) == ("absent", 0)
        assert classify_arrival(time(8, 0), covered_until=time(7, 15)) == ("late", 45)

    def test_a_marked_arrival_long_after_a_short_permit_is_absence(self, school, principal_user):
        staff = _staff(school, 1)
        _permit(school, staff, FEB, time(7, 0), time(7, 15), "late_arrival")
        record = _mark(school, staff, principal_user, FEB, "absent", time(12, 30))
        assert (record.status, record.late_minutes) == ("absent", 0)

    # ── وقتُ الإذن مقيَّدٌ بنوعه وبساعات الدوام (م-1 وم-12 وم-13) ────────────
    @pytest.mark.parametrize(
        ("kind", "start", "end"),
        [
            ("late_arrival", time(8, 0), time(9, 0)),  # التأخيرُ يُعدّ من 7:00 (2.1)
            ("late_arrival", time(8, 50), time(9, 0)),
            ("early_departure", time(15, 0), time(17, 0)),  # بعد نهاية الدوام 14:00
            ("early_departure", time(12, 0), time(13, 0)),  # الخروجُ المبكر ينتهي بنهايته
            ("during_day", time(7, 0), time(8, 0)),  # هذا تأخيرٌ لا استئذان
            ("during_day", time(6, 0), time(7, 30)),
        ],
    )
    def test_the_window_must_fit_its_type_and_the_working_day(self, school, kind, start, end):
        staff = _staff(school, 1)
        with pytest.raises(PolicyError, match=r"1\.1|2\.1"):
            _permit(school, staff, date(2026, 2, 20), start, end, kind, approve=None)

    # ── الانصرافُ والخروجُ المبكر ──────────────────────────────────────
    def test_leaving_before_two_without_a_permit_is_counted(self, school, principal_user):
        a, b = _staff(school, 1), _staff(school, 2)
        _permit(school, b, FEB, time(13, 0), time(14, 0), "early_departure")

        marked = [
            StaffAttendanceService.mark(
                school=school,
                staff=person,
                day=FEB,
                status="present",
                actor=principal_user,
                check_in=time(6, 50),
                check_out=time(11, 0),
            )
            for person in (a, b)
        ]

        assert (marked[0].check_out, marked[0].early_leave_minutes) == (time(11, 0), 180)
        assert marked[1].early_leave_minutes == 120  # الإذنُ غطّى 13:00–14:00 وحدَها
        rows = {
            r["employee_number"]: r
            for r in StaffAttendanceService.monthly_report(school, 2026, 2)["rows"]
        }
        assert (rows["T-0001"]["early_leave_minutes"], rows["T-0002"]["early_leave_minutes"]) == (
            180,
            120,
        )

    # ── «أو عذر مقبول» ─────────────────────────────────────────────────
    def test_an_accepted_excuse_turns_an_after_nine_arrival_into_lateness(
        self, school, principal_user
    ):
        staff = _staff(school, 1)
        record = StaffAttendanceService.mark(
            school=school,
            staff=staff,
            day=FEB,
            status="late",
            actor=principal_user,
            check_in=time(9, 30),
            accepted_excuse="تعطّل السيارة — أُبلغ المسؤول بالبريد 06:40",
        )
        assert (record.status, record.late_minutes) == ("late", 150)
        assert record.accepted_excuse.startswith("تعطّل")

    # ── نوعُ الغياب من سجلّ الغياب المدرسيّ ─────────────────────────────
    def test_an_absence_carries_its_type_and_the_report_separates_the_uncovered(
        self, school, principal_user
    ):
        staff = _staff(school, 1)
        StaffAttendanceService.mark(
            school=school,
            staff=staff,
            day=date(2026, 2, 1),
            status="absent",
            actor=principal_user,
            absence_type="sick",
        )
        _mark(school, staff, principal_user, date(2026, 2, 2), "absent")

        row = next(
            r
            for r in StaffAttendanceService.monthly_report(school, 2026, 2)["rows"]
            if r["employee_number"] == "T-0001"
        )
        assert (row["absent"], row["absent_uncovered"], row["absence_sick"]) == (2, 1, 1)
        with pytest.raises(PolicyError):
            StaffAttendanceService.mark(
                school=school,
                staff=staff,
                day=date(2026, 2, 3),
                status="late",
                actor=principal_user,
                check_in=time(7, 30),
                absence_type="sick",
            )

    # ── النائبُ يقرأ تقريرَ من يتبعه وحدَهم ─────────────────────────────
    def test_a_deputy_reads_only_the_staff_who_report_to_them(self, school, principal_user):
        teacher, worker = _staff(school, 1), _staff(school, 2, role="services_worker")
        vice_academic, vice_admin = _actor(school, "vice_academic"), _actor(school, "vice_admin")
        secretary = _actor(school, "secretary")

        def numbers(viewer):
            report = StaffAttendanceService.monthly_report(school, 2026, 2, viewer=viewer)
            return {r["employee_number"] for r in report["rows"]}

        assert numbers(vice_academic) == {teacher.employee_number}
        assert numbers(vice_admin) == {worker.employee_number}
        everyone = {
            u.employee_number
            for u in (teacher, worker, vice_academic, vice_admin, secretary, principal_user)
        }
        assert numbers(principal_user) == numbers(secretary) == everyone

    # ── طلبُ السكرتير لا يعلق، والمعلَّقُ يُسحب ──────────────────────────
    def test_the_only_secretarys_request_is_recorded_by_the_principal(self, school, principal_user):
        """م-28: مربّعٌ صاحبُه هو صاحبُ الطلب يرتفع إلى المدير."""
        secretary = _actor(school, "secretary")
        permit = _permit(school, secretary, FEB, time(7, 0), time(8, 0), "late_arrival", None)
        assert _eligible(permit) == {principal_user.pk}
        assert permit in set(PermitService.awaiting(school, principal_user))

        _through(permit)
        assert (permit.status, permit.secretary_by) == ("approved", principal_user)

    def test_the_applicant_withdraws_a_pending_request_and_frees_the_day(self, school):
        """م-20: السحبُ قبل الاعتماد النهائيّ يُفرج عن اليوم (م-14) والدقائق (م-15)."""
        teacher, other = _staff(school, 1), _staff(school, 2)
        permit = _permit(school, teacher, FEB, time(7, 0), time(8, 0), "late_arrival", None)

        with pytest.raises(PolicyError):
            PermitService.cancel(permit, actor=other)
        PermitService.cancel(permit, actor=teacher)

        permit.refresh_from_db()
        assert (permit.status, permit.stage) == ("cancelled", "closed")
        assert _permit(school, teacher, FEB, time(12, 0), time(12, 30), approve=None)

    # ── لا يرصد أحدٌ نفسَه، ولا حضورَ بلا وقت ────────────────────────────
    def test_nobody_marks_themself(self, school, principal_user):
        with pytest.raises(PolicyError, match="نفس"):
            _mark(school, principal_user, principal_user, FEB, "present", time(6, 50))

    @pytest.mark.parametrize("status", ["present", "late", "permitted"])
    def test_arrival_statuses_need_the_arrival_time(self, school, principal_user, status):
        staff = _staff(school, 1)
        _permit(school, staff, FEB, time(7, 0), time(8, 0), "late_arrival")
        with pytest.raises(PolicyError, match="وقت الحضور"):
            _mark(school, staff, principal_user, FEB, status)

    # ── من غادر يبقى في تقرير شهره ────────────────────────────────────
    def test_a_departed_member_stays_in_the_month_they_were_marked(self, school, principal_user):
        staff = _staff(school, 1)
        _mark(school, staff, principal_user, date(2026, 2, 1), "absent")
        Membership.objects.filter(user=staff, school=school).update(is_active=False)

        report = StaffAttendanceService.monthly_report(school, 2026, 2)
        row = next(r for r in report["rows"] if r["employee_number"] == "T-0001")
        assert row["absent"] == 1 and report["totals"]["absent"] == 1

    # ── التدقيقُ يحمل كلَّ ما تغيّر ─────────────────────────────────────
    def test_the_audit_keeps_the_old_minutes_when_the_status_stays(self, school, principal_user):
        staff = _staff(school, 1)
        record = _mark(school, staff, principal_user, FEB, "late", time(8, 10))
        _mark(school, staff, principal_user, FEB, "late", time(7, 5))

        log = AuditLog.objects.filter(object_id=str(record.pk), action="update").get()
        assert log.changes["late_minutes"] == [70, 5]
        assert log.changes["check_in"] == ["08:10", "07:05"]

    # ── لا رابطَ في الشاشة يردّه الحارس ─────────────────────────────────
    def test_every_staff_affairs_link_on_the_new_screens_opens_for_its_viewer(
        self, client, school, principal_user
    ):
        pages = {
            "vice_admin": ("staff_affairs:permit_queue", "staff_affairs:attendance_report"),
            "vice_academic": ("staff_affairs:permit_queue", "staff_affairs:attendance_report"),
            "secretary": ("staff_affairs:attendance_board", "staff_affairs:permit_queue"),
        }
        for role, names in pages.items():
            client.force_login(_actor(school, role))
            for name in names:
                page = client.get(reverse(name))
                assert page.status_code == 200, (role, name)
                for href in _hrefs(page):
                    assert client.get(href).status_code != 403, (role, name, href)

    def test_the_principal_is_offered_his_own_permits_link(self, client_as, school, principal_user):
        page = client_as(principal_user).get(reverse("staff_affairs:attendance_board"))
        assert reverse("staff_affairs:my_permits") in page.content.decode()

    # ── سطرُ الرصد يلتفّ على الجوال ─────────────────────────────────────
    def test_the_staff_row_wraps_on_narrow_screens(self, client_as, school, principal_user):
        _staff(school, 1)
        page = client_as(principal_user).get(reverse("staff_affairs:attendance_board"))
        assert "att-row att-row--staff" in page.content.decode()
        from tests.css_source import read_css

        css = read_css()
        rule = re.search(r"\.att-row--staff\s*\{([^}]*)\}", css)
        assert rule and "flex-wrap: wrap" in rule.group(1)

    # ── نموذج 03: الاستثناءُ بقرار المدير وحدَه ───────────────────────────
    def test_an_exception_from_the_principal_covers_the_days_and_spares_the_cap(
        self, school, principal_user
    ):
        from staff_affairs.attendance import ExceptionService

        staff = _staff(school, 1)
        request = ExceptionService.submit(
            school=school,
            staff=staff,
            exception_type="early_departure",
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
            boundary=time(13, 15),
            content="مرافقة ابني لجلسات العلاج",
            evidence="تقرير طبي",
            evidence_file=_evidence(),
        )
        with pytest.raises(PolicyError):
            ExceptionService.decide(
                request, actor=_actor(school, "vice_admin"), approve=True, feedback="موافق"
            )
        ExceptionService.decide(request, actor=principal_user, approve=True, feedback="موافق")

        leaving = [
            StaffAttendanceService.mark(
                school=school,
                staff=staff,
                day=date(2026, 2, day),
                status="present",
                actor=principal_user,
                check_in=time(6, 50),
                check_out=out,
            ).early_leave_minutes
            for day, out in ((2, time(13, 15)), (3, time(13, 0)))
        ]
        assert leaving == [0, 15]
        assert PermitService.balance(school, staff, FEB).approved == 0

    def test_a_late_exception_moves_the_counted_start(self, school, principal_user):
        staff = _staff(school, 1)
        _exception(
            school, staff, principal_user, "late_arrival", FEB, date(2026, 2, 10), time(7, 30)
        )

        on_time = _mark(school, staff, principal_user, date(2026, 2, 2), "permitted", time(7, 20))
        late = _mark(school, staff, principal_user, date(2026, 2, 3), "late", time(7, 40))
        assert (on_time.late_minutes, late.late_minutes) == (0, 10)

    def test_approving_an_exception_reclassifies_marked_days(self, school, principal_user):
        """م-32 ([س] 2.4 «عذر مقبول» قياساً): عند اعتماد الاستثناء تُعاد مطابقةُ أيّامه."""
        staff = _staff(school, 1)
        record = _mark(school, staff, principal_user, date(2026, 2, 2), "late", time(7, 20))
        _exception(
            school, staff, principal_user, "late_arrival", FEB, date(2026, 2, 10), time(7, 30)
        )

        record.refresh_from_db()
        assert (record.status, record.late_minutes) == ("permitted", 0)

    def test_an_exception_needs_its_evidence(self, school):
        from staff_affairs.attendance import ExceptionService

        with pytest.raises(PolicyError, match="يثبت"):
            ExceptionService.submit(
                school=school,
                staff=_staff(school, 1),
                exception_type="early_departure",
                start_date=FEB,
                end_date=FEB,
                boundary=time(13, 0),
                content="ظرف",
                evidence="",
                evidence_file=None,
            )

    # ── حاشيةُ نموذج 02: «عدم الخروج إلا بعد اعتماده» ──────────────────
    @pytest.mark.parametrize(
        ("kind", "day", "start", "end"),
        [
            ("early_departure", date(2026, 2, 14), time(12, 0), time(14, 0)),  # أمس
            ("early_departure", date(2026, 2, 15), time(11, 0), time(14, 0)),  # بدأ قبل الآن
            ("early_departure", date(2026, 2, 15), time(12, 0), time(14, 0)),  # يبدأ الآن تماماً
            ("during_day", date(2026, 2, 1), time(10, 0), time(11, 0)),
        ],
    )
    def test_leaving_permits_are_not_accepted_after_their_time(self, school, kind, day, start, end):
        with pytest.raises(PolicyError, match="اعتماده"):
            PermitService.submit(
                school=school,
                staff=_staff(school, 1),
                permit_type=kind,
                day=day,
                start_time=start,
                end_time=end,
                reason="سبب",
            )

    def test_a_late_arrival_may_follow_the_morning_and_a_leave_may_precede_it(self, school):
        staff, other = _staff(school, 1), _staff(school, 2)
        base = {"school": school, "reason": "سبب"}
        PermitService.submit(
            **base,
            staff=staff,
            permit_type="late_arrival",
            day=date(2026, 2, 14),
            start_time=time(7, 0),
            end_time=time(8, 0),
        )
        PermitService.submit(
            **base,
            staff=other,
            permit_type="early_departure",
            day=date(2026, 2, 15),
            start_time=time(13, 0),
            end_time=time(14, 0),
        )

    # ── يومُ الغياب لا يحمل دقائقَ انصرافٍ مبكر (م-9) ─────────────────────
    def test_an_absent_day_carries_no_early_leave_minutes(self, school, principal_user):
        staff = _staff(school, 1)
        record = StaffAttendanceService.mark(
            school=school,
            staff=staff,
            day=FEB,
            status="absent",
            actor=principal_user,
            check_in=time(9, 30),
            check_out=time(13, 0),
        )
        assert (record.status, record.early_leave_minutes) == ("absent", 0)
        row = next(
            r
            for r in StaffAttendanceService.monthly_report(school, 2026, 2)["rows"]
            if r["employee_number"] == "T-0001"
        )
        assert (row["absent"], row["early_leave_minutes"]) == (1, 0)

    # ── لا يعلق طلبٌ في مرحلةٍ شغر دورُها أو غاب صاحبُه (م-28) ─────────────
    def test_a_vacant_deputy_passes_to_the_principal(self, school, principal_user):
        teacher = _staff(school, 1)  # لا نائبَ أكاديميّاً في المدرسة
        permit = _permit(school, teacher, FEB, time(7, 0), time(8, 0), "late_arrival", None)
        PermitService.act(permit, actor=_actor(school, "secretary"), approve=True)
        permit.refresh_from_db()

        assert permit in set(PermitService.awaiting(school, principal_user))
        PermitService.act(permit, actor=principal_user, approve=True)
        permit.refresh_from_db()
        assert permit.stage == "principal"

    def test_an_absent_deputy_passes_to_the_principal(self, school, principal_user):
        teacher, vice_academic = _staff(school, 1), _actor(school, "vice_academic")
        _mark(school, vice_academic, principal_user, DEFAULT_NOW.date(), "absent")
        permit = _permit(school, teacher, FEB, time(7, 0), time(8, 0), "late_arrival", None)
        PermitService.act(permit, actor=_actor(school, "secretary"), approve=True)
        permit.refresh_from_db()

        assert principal_user.pk in _eligible(permit)
        PermitService.act(permit, actor=principal_user, approve=True)

    def test_no_secretary_passes_the_balance_to_the_principal(self, school, principal_user):
        worker = _staff(school, 1, role="services_worker")
        permit = _permit(school, worker, FEB, time(7, 0), time(8, 0), "late_arrival", None)

        PermitService.act(permit, actor=principal_user, approve=True)
        permit.refresh_from_db()
        assert (permit.stage, permit.secretary_by) == ("supervisor", principal_user)
        assert AuditLog.objects.filter(
            object_id=str(permit.pk), changes__on_behalf_of="secretary"
        ).exists()

    # ── رسالةُ الخطأ لا تمسح ما كُتب ──────────────────────────────────────
    def test_a_refused_click_keeps_what_was_typed(self, client_as, school, principal_user):
        staff = _staff(school, 1)
        response = client_as(principal_user).post(
            reverse("staff_affairs:attendance_mark"),
            {
                "staff_id": staff.pk,
                "date": "2026-02-03",
                "status": "late",
                "check_in": "09:30",
                "check_out": "13:10",
            },
        )
        html = response.content.decode()
        assert 'role="alert"' in html
        assert 'value="09:30"' in html and 'value="13:10"' in html


# ══════════════════════════════════════════════════════════════════════
#  جولةُ الإصلاح 3 — مطابقةُ المواصفة قاعدةً قاعدة
# ══════════════════════════════════════════════════════════════════════


class TestSpecRules:
    # ── م-7: العذرُ المقبول يقبله المديرُ أو من ينوب عنه ─────────────────
    def test_only_the_principal_side_accepts_an_excuse(self, school, principal_user):
        staff, secretary = _staff(school, 1), _actor(school, "secretary")
        typed = {
            "school": school,
            "staff": staff,
            "day": FEB,
            "status": "late",
            "check_in": time(9, 30),
            "accepted_excuse": "مراجعة مستشفى",
        }

        with pytest.raises(PolicyError, match="ينوب"):
            StaffAttendanceService.mark(**typed, actor=secretary)
        record = StaffAttendanceService.mark(**typed, actor=principal_user)

        assert (record.status, record.late_minutes) == ("late", 150)

    def test_the_audit_trail_never_carries_the_text_of_an_excuse(self, school, principal_user):
        """م-7 مع سجلٍّ ثابتٍ لا يُحذف: يُسجَّل أنّ عذراً قُبل، لا نصُّه."""
        staff = _staff(school, 1)
        record = StaffAttendanceService.mark(
            school=school,
            staff=staff,
            day=FEB,
            status="late",
            actor=principal_user,
            check_in=time(9, 30),
            accepted_excuse="مراجعة مستشفى — جلسة علاج",
        )

        logs = AuditLog.objects.filter(object_id=str(record.pk))
        assert logs.exists()
        assert all("مستشفى" not in json.dumps(log.changes, ensure_ascii=False) for log in logs)
        assert logs.first().changes["accepted_excuse"] is True
        assert record.accepted_excuse.startswith("مراجعة")

    # ── م-10: الإذنُ المعتمد يبقى محسوباً ولو انتهى يومُه غياباً ────────────
    def test_an_approved_permit_stays_counted_on_a_day_that_ended_absent(
        self, school, principal_user
    ):
        staff = _staff(school, 1)
        _permit(school, staff, FEB, time(7, 0), time(8, 0), "late_arrival")
        _mark(school, staff, principal_user, FEB, "absent", time(12, 0))

        assert PermitService.balance(school, staff, FEB).approved == 60

    # ── م-4 وم-35: الإذنُ وحدَه لا يرفع غيابَ الحضور بعد التاسعة ────────────────
    def test_a_permit_alone_does_not_lift_an_after_nine_absence(self, school, principal_user):
        staff = _staff(school, 1)
        _permit(school, staff, FEB, time(7, 0), time(9, 0), "late_arrival")

        with pytest.raises(PolicyError, match="غائب"):
            _mark(school, staff, principal_user, FEB, "late", time(9, 30))
        record = _mark(school, staff, principal_user, FEB, "absent", time(9, 30))
        assert record.status == "absent"

        covered = StaffAttendanceService.mark(
            school=school,
            staff=staff,
            day=FEB,
            status="late",
            actor=principal_user,
            check_in=time(9, 30),
            accepted_excuse="عذرٌ قُبل",
        )
        assert (covered.status, covered.late_minutes) == ("late", 30)

    # ── م-18أ: نافذةُ تقديم إذن التأخير الصباحيّ ────────────────────────────
    @pytest.mark.parametrize(
        ("today", "day", "accepted"),
        [
            (datetime(2026, 2, 14, 12, 0), date(2026, 1, 20), True),  # الشهرُ السابق ويومُنا 14
            (datetime(2026, 2, 15, 12, 0), date(2026, 1, 20), False),  # جاوز الرابعَ عشر
            (datetime(2026, 2, 15, 12, 0), date(2026, 2, 1), True),  # الشهرُ الجاري
            (datetime(2026, 2, 5, 12, 0), date(2025, 12, 20), False),  # شهران مضيا
            (datetime(2026, 2, 15, 12, 0), date(2026, 2, 20), True),  # قبل وقوعه
        ],
    )
    def test_a_late_arrival_permit_may_follow_its_day_until_the_fourteenth(
        self, school, today, day, accepted
    ):
        staff = _staff(school, 1)
        request = {
            "school": school,
            "staff": staff,
            "permit_type": "late_arrival",
            "day": day,
            "start_time": time(7, 0),
            "end_time": time(8, 0),
            "reason": "سبب",
        }
        with _at(today):
            if accepted:
                assert PermitService.submit(**request).status == "pending"
            else:
                with pytest.raises(PolicyError, match="5.1|5.3"):
                    PermitService.submit(**request)

    # ── م-18ب: ما لم يُعتمد قبل بدئه ينتهي ──────────────────────────────────
    def test_a_leaving_permit_not_approved_before_its_start_expires(self, school, principal_user):
        staff = _staff(school, 1)
        permit = _permit(
            school, staff, date(2026, 2, 15), time(13, 0), time(14, 0), "early_departure", None
        )
        PermitService.act(permit, actor=_actor(school, "secretary"), approve=True)

        with _at(datetime(2026, 2, 15, 13, 0)):
            assert PermitService.awaiting(school, _actor(school, "vice_academic")) == []
            permit.refresh_from_db()
            assert (permit.status, permit.stage) == ("expired", "closed")
            with pytest.raises(PolicyError, match="منتهٍ"):
                PermitService.act(permit, actor=principal_user, approve=True)

        assert PermitService.balance(school, staff, date(2026, 2, 15)).pending == 0
        assert AuditLog.objects.filter(
            object_id=str(permit.pk), changes__cause="not_approved_before_start"
        ).exists()

    def test_an_expired_request_frees_the_day_for_another(self, school):
        """م-14: المنتهي لا يمنع طلباً جديداً في اليوم نفسه."""
        staff = _staff(school, 1)
        _permit(school, staff, date(2026, 2, 15), time(10, 0), time(11, 0), approve=None)

        with _at(datetime(2026, 2, 15, 11, 30)):
            fresh = PermitService.submit(
                school=school,
                staff=staff,
                permit_type="early_departure",
                day=date(2026, 2, 15),
                start_time=time(13, 0),
                end_time=time(14, 0),
                reason="سبب",
            )
        assert fresh.status == "pending"
        assert PermitRequest.objects.filter(staff=staff, status="expired").count() == 1

    # ── م-11: طلبُ الغد في أيّ ساعة ────────────────────────────────────────
    def test_a_permit_for_tomorrow_is_accepted_at_any_hour(self, school):
        staff = _staff(school, 1)
        with _at(datetime(2026, 2, 15, 23, 30)):  # بعد الدوام اضطراراً (السياسة 4.6)
            permit = PermitService.submit(
                school=school,
                staff=staff,
                permit_type="during_day",
                day=date(2026, 2, 16),
                start_time=time(10, 0),
                end_time=time(11, 0),
                reason="سبب",
            )
        assert permit.status == "pending"

    # ── م-19: إخطارُ الموظّف باسم السكرتارية عند الاعتماد ────────────────────
    def test_the_final_approval_notifies_the_employee_and_records_its_time(self, school):
        from notifications.models import InAppNotification

        staff = _staff(school, 1)
        permit = _permit(school, staff, FEB, time(7, 0), time(8, 0), "late_arrival")

        assert permit.notified_at is not None
        notice = InAppNotification.objects.get(user=staff)
        assert "السكرتارية" in notice.title
        assert notice.related_object_id == str(permit.pk)

    # ── م-21: منسّقُ القسم ليس مرحلةً ─────────────────────────────────────
    # ── م-23: إذنُ المدير نفسِه ────────────────────────────────────────────
    def test_the_principals_permit_is_recorded_and_decided_from_outside(
        self, school, principal_user
    ):
        secretary = _actor(school, "secretary")
        permit = _permit(school, principal_user, FEB, time(7, 0), time(8, 0), "late_arrival", None)
        assert permit.stage == "secretary"

        with pytest.raises(PolicyError, match="4.1"):
            PermitService.act(permit, actor=principal_user, approve=True)
        PermitService.act(permit, actor=secretary, approve=True)
        permit.refresh_from_db()
        assert (permit.stage, permit.recorded_balance_minutes) == ("external", 600)
        with pytest.raises(PolicyError, match="مرجع"):
            PermitService.act(permit, actor=secretary, approve=True, reason=" ")

        PermitService.act(permit, actor=secretary, approve=True, reason="بريد الإدارة 2026-02-01")
        permit.refresh_from_db()
        assert (permit.status, permit.external_reference) == ("approved", "بريد الإدارة 2026-02-01")
        assert PermitService.balance(school, principal_user, FEB).approved == 60

    def test_the_principal_does_not_file_form_03_for_himself(self, school, principal_user):
        """م-34 ([ن03]: خطابٌ «إلى مدير المدرسة»): لا يقدّمه المديرُ لنفسه."""
        from staff_affairs.attendance import ExceptionService

        with pytest.raises(PolicyError, match="نموذج 03"):
            ExceptionService.submit(
                school=school,
                staff=principal_user,
                exception_type="late_arrival",
                start_date=FEB,
                end_date=FEB,
                boundary=time(7, 30),
                content="ظرف",
                evidence="مرفق",
                evidence_file=_evidence(),
            )

    def test_the_principal_is_offered_the_permit_form(self, client_as, school, principal_user):
        page = client_as(principal_user).get(reverse("staff_affairs:my_permits"))
        assert 'name="permit_type"' in page.content.decode()

    # ── م-24 وم-25: الإنابةُ نافذةٌ بحكم الوظيفة ───────────────────────────
    def test_a_deputy_tasked_by_the_principal_approves_in_his_box(self, school, principal_user):
        """م-43: التكليفُ قرارٌ صريحٌ من المدير — لا يقوم برصد غيابه وحدَه."""
        teacher = _staff(school, 1)
        vice_admin, secretary = _actor(school, "vice_admin"), _actor(school, "secretary")
        permit = _permit(school, teacher, FEB, time(7, 0), time(8, 0), "late_arrival", None)
        for actor in (secretary, _actor(school, "vice_academic")):
            PermitService.act(permit, actor=actor, approve=True)
            permit.refresh_from_db()

        _mark(school, principal_user, secretary, DEFAULT_NOW.date(), "absent")
        assert vice_admin.pk not in _eligible(permit)  # غيابُ المدير لا يُنيب أحداً
        assignment = _assign(school, principal_user, vice_admin)

        assert permit in set(PermitService.awaiting(school, vice_admin))
        PermitService.act(permit, actor=vice_admin, approve=True)
        permit.refresh_from_db()
        assert (permit.status, permit.reviewed_by, permit.decided_on_behalf) == (
            "approved",
            vice_admin,
            True,
        )
        entry = AuditLog.objects.get(object_id=str(permit.pk), changes__on_behalf_of="principal")
        assert entry.changes["assignment"] == str(assignment.pk)
        assert entry.changes["acting_role"] == "principal"

    def test_with_no_active_principal_the_admin_deputy_signs(self, school, principal_user):
        """م-26 (قياساً على بطاقة 1034 «في حال غيابه»): الشغورُ كالغياب."""
        teacher = _staff(school, 1)
        vice_admin = _actor(school, "vice_admin")
        permit = _permit(school, teacher, FEB, time(7, 0), time(8, 0), "late_arrival", None)
        for actor in (_actor(school, "secretary"), _actor(school, "vice_academic")):
            PermitService.act(permit, actor=actor, approve=True)
            permit.refresh_from_db()
        Membership.objects.filter(school=school, user=principal_user).update(is_active=False)

        PermitService.act(permit, actor=vice_admin, approve=True)
        permit.refresh_from_db()
        assert (permit.status, permit.decided_on_behalf) == ("approved", True)

    def test_the_academic_deputy_stands_in_for_the_principal_only_when_tasked(
        self, school, principal_user
    ):
        """قرارُ المدرسة: المديرُ يكلّف النائبَ الأكاديميّ أو الإداريّ — لا أحدَ بلا تكليف."""
        teacher = _staff(school, 1)
        vice_academic, secretary = _actor(school, "vice_academic"), _actor(school, "secretary")
        permit = _permit(school, teacher, FEB, time(7, 0), time(8, 0), "late_arrival", None)
        PermitService.act(permit, actor=secretary, approve=True)
        permit.refresh_from_db()
        PermitService.act(permit, actor=vice_academic, approve=True)
        permit.refresh_from_db()
        _mark(school, principal_user, secretary, DEFAULT_NOW.date(), "absent")

        with pytest.raises(PolicyError, match="بانتظار"):
            PermitService.act(permit, actor=vice_academic, approve=True)
        _assign(school, principal_user, vice_academic)
        PermitService.act(permit, actor=vice_academic, approve=True)
        permit.refresh_from_db()
        assert permit.status == "approved"

    def test_a_tasking_is_accepted_while_the_principal_is_present(self, school, principal_user):
        teacher = _staff(school, 1)
        vice_admin = _actor(school, "vice_admin")
        permit = _permit(school, teacher, FEB, time(7, 0), time(8, 0), "late_arrival", None)
        for actor in (_actor(school, "secretary"), _actor(school, "vice_academic")):
            PermitService.act(permit, actor=actor, approve=True)
            permit.refresh_from_db()

        assert vice_admin.pk not in _eligible(permit)
        _assign(school, principal_user, vice_admin)
        assert vice_admin.pk in _eligible(permit)

    # ── المواصفةُ صامتة (م-21 وم-24): التوقيعان من شخصٍ واحد ──────────────────────────────────────
    def test_one_person_may_sign_the_boxes_and_approve_on_behalf(self, school, principal_user):
        worker = _staff(school, 1, role="services_worker")  # مسؤولُه النائبُ الإداريّ
        vice_admin, secretary = _actor(school, "vice_admin"), _actor(school, "secretary")
        permit = _permit(school, worker, FEB, time(7, 0), time(8, 0), "late_arrival", None)
        PermitService.act(permit, actor=secretary, approve=True)
        permit.refresh_from_db()
        PermitService.act(permit, actor=vice_admin, approve=True)
        permit.refresh_from_db()
        _assign(school, principal_user, vice_admin)

        PermitService.act(permit, actor=vice_admin, approve=True)

        permit.refresh_from_db()
        assert (permit.status, permit.deputy_by, permit.reviewed_by) == (
            "approved",
            vice_admin,
            vice_admin,
        )
        assert AuditLog.objects.filter(object_id=str(permit.pk), changes__same_signer=True).exists()

    # ── م-27: غيابُهما معاً ───────────────────────────────────────────────
    def test_when_both_are_absent_the_request_waits_in_the_principal_box(
        self, school, principal_user
    ):
        teacher = _staff(school, 1)
        vice_admin, secretary = _actor(school, "vice_admin"), _actor(school, "secretary")
        permit = _permit(school, teacher, FEB, time(7, 0), time(8, 0), "late_arrival", None)
        for actor in (secretary, _actor(school, "vice_academic")):
            PermitService.act(permit, actor=actor, approve=True)
            permit.refresh_from_db()
        for person in (principal_user, vice_admin):
            _mark(school, person, secretary, DEFAULT_NOW.date(), "absent")

        with pytest.raises(PolicyError, match="بانتظار"):
            PermitService.act(permit, actor=vice_admin, approve=True)
        permit.refresh_from_db()
        assert (permit.status, permit.stage) == ("pending", "principal")
        # والمديرُ نفسُه يعود فيعتمد.
        PermitService.act(permit, actor=principal_user, approve=True)
        permit.refresh_from_db()
        assert permit.status == "approved"

    # ── م-30: التغذيةُ الراجعة لازمةٌ للقرارين ────────────────────────────
    def test_an_exception_decision_needs_its_feedback(self, school, principal_user):
        from staff_affairs.attendance import ExceptionService

        staff = _staff(school, 1)
        request = _exception(
            school, staff, principal_user, "late_arrival", FEB, FEB, time(7, 30), approve=None
        )

        with pytest.raises(PolicyError, match="التغذية"):
            ExceptionService.decide(request, actor=principal_user, approve=True)
        with pytest.raises(PolicyError, match="التغذية"):
            ExceptionService.decide(request, actor=principal_user, approve=False, feedback=" ")
        ExceptionService.decide(
            request, actor=principal_user, approve=False, feedback="لا يظهر من المرفق ما يوجبه"
        )
        request.refresh_from_db()
        assert (request.status, request.feedback) == ("rejected", "لا يظهر من المرفق ما يوجبه")

    def test_an_exception_covers_its_window_only(self, school, principal_user):
        """م-5 وم-31: استثناءٌ حتّى 9:30 — 9:20 مستأذن، و9:45 غائب."""
        staff = _staff(school, 1)
        _exception(
            school, staff, principal_user, "late_arrival", FEB, date(2026, 2, 10), time(9, 30)
        )

        inside = _mark(school, staff, principal_user, date(2026, 2, 2), "permitted", time(9, 20))
        outside = _mark(school, staff, principal_user, date(2026, 2, 3), "absent", time(9, 45))
        assert (inside.status, outside.status) == ("permitted", "absent")

    # ── م-35: التغطيةُ بعد المهلة تُسجَّل وتُوسم ─────────────────────────────
    def test_the_deadline_is_the_fourteenth_of_the_next_month(self):
        assert coverage_deadline(date(2026, 1, 20)) == date(2026, 2, 14)
        assert coverage_deadline(date(2026, 12, 3)) == date(2027, 1, 14)

    def test_covering_an_absence_after_the_deadline_is_recorded_and_flagged(
        self, school, principal_user
    ):
        staff = _staff(school, 1)
        with _at(datetime(2026, 1, 22, 12, 0)):
            _mark(school, staff, principal_user, date(2026, 1, 20), "absent")
            _mark(school, staff, principal_user, date(2026, 1, 21), "absent")

        with _at(datetime(2026, 2, 10, 9, 0)):  # قبل المهلة
            StaffAttendanceService.mark(
                school=school,
                staff=staff,
                day=date(2026, 1, 20),
                status="absent",
                actor=principal_user,
                absence_type="sick",
            )
        with _at(datetime(2026, 2, 20, 9, 0)):  # بعد المهلة
            StaffAttendanceService.mark(
                school=school,
                staff=staff,
                day=date(2026, 1, 21),
                status="absent",
                actor=principal_user,
                absence_type="casual",
            )

        report = StaffAttendanceService.monthly_report(school, 2026, 1)
        row = next(r for r in report["rows"] if r["employee_number"] == "T-0001")
        assert (row["absent"], row["absent_uncovered"], row["covered_late"]) == (2, 0, 1)
        assert report["deadline"] == date(2026, 2, 14)

    def test_an_exception_approved_next_month_still_reclassifies_the_month_it_covers(
        self, school, principal_user
    ):
        """م-35: لا يُغلق الشهرُ المنقضي دون تغطيةٍ — تُسجَّل وتُوسم."""
        staff = _staff(school, 1)
        with _at(datetime(2026, 1, 25, 12, 0)):
            record = _mark(school, staff, principal_user, date(2026, 1, 20), "absent", time(9, 20))
            request = _exception(
                school,
                staff,
                principal_user,
                "late_arrival",
                date(2026, 1, 18),
                date(2026, 1, 31),
                time(9, 30),
                approve=None,
            )
        with _at(datetime(2026, 2, 20, 9, 0)):
            from staff_affairs.attendance import ExceptionService

            ExceptionService.decide(
                request, actor=principal_user, approve=True, feedback="اطّلعتُ على المرفق"
            )

        record.refresh_from_db()
        assert record.status == "permitted"
        row = next(
            r
            for r in StaffAttendanceService.monthly_report(school, 2026, 1)["rows"]
            if r["employee_number"] == "T-0001"
        )
        assert (row["absent"], row["covered_late"]) == (0, 1)

    def test_a_permit_approved_in_the_next_month_is_not_refused(self, school, principal_user):
        """م-35: اعتمادُ إذنِ تأخيرٍ لشهرٍ مضى لا يُمنع ما دام في المهلة (كان يعلق)."""
        staff = _staff(school, 1)
        with _at(datetime(2026, 1, 30, 9, 0)):
            record = _mark(school, staff, principal_user, date(2026, 1, 30), "late", time(8, 30))
            permit = PermitService.submit(
                school=school,
                staff=staff,
                permit_type="late_arrival",
                day=date(2026, 1, 30),
                start_time=time(7, 0),
                end_time=time(8, 30),
                reason="سبب",
            )
            for role in ("secretary", "vice_academic"):
                PermitService.act(permit, actor=_actor(school, role), approve=True)
                permit.refresh_from_db()

        with _at(datetime(2026, 2, 3, 9, 0)):
            PermitService.act(permit, actor=principal_user, approve=True)

        permit.refresh_from_db()
        record.refresh_from_db()
        assert permit.status == "approved"
        assert (record.status, record.late_minutes) == ("permitted", 0)

    # ── ز من المواصفة: تصحيحاتُ الاستخراج ─────────────────────────────────────────
    def test_the_extraction_is_corrected_to_the_originals(self):
        base = Path("AAdocs/ministry_data/2026_2027")
        forms = (base / "07_forms_catalog.md").read_text(encoding="utf-8")
        form_02 = next(line for line in forms.splitlines() if line.startswith("| 02 |"))
        assert "المسؤول المباشر (موافق/غير موافق) ← النائب المسؤول" not in form_02  # ز-1
        assert "السكرتارية (رصيد الساعات + الاسم + توقيت تقديم) ← المسؤول المباشر" in forms
        assert "نموذج طلب (عام)" not in forms and "التأخير الصباحي المتكرر" not in forms
        third = (base / "07b_forms_catalog_thirdpass.md").read_text(encoding="utf-8")
        third_02 = next(line for line in third.splitlines() if line.startswith("| 02 |"))
        assert "التسلسل مطابق تماماً" not in third_02  # ز-2
        policy = (base / "06_attendance_performance_review.md").read_text(encoding="utf-8")
        assert "بذات مقدار مدة الخصم" in policy
        deep = (base / "06b_attendance_performance_thirdpass.md").read_text(encoding="utf-8")
        assert "مهلة الخصم\nحتى يوم 15" not in deep and "قبل يوم 15 من الشهر" in deep
        cards = (base / "03_job_descriptions_rbac.md").read_text(encoding="utf-8")
        assert "صلاحية الإشراف وتقييم أداء فريق (معلمي/معلمات) الدعم الإضافي" not in cards
        assert "يشارك (لا ينفرد)" not in cards
        roles = (base / "rbac_roles.json").read_text(encoding="utf-8")
        assert "الإشراف وتقييم أداء فريق معلمي الدعم الإضافي التابعين له — صراحة" not in roles

    def test_the_spec_travels_with_the_code(self):
        spec = Path("docs/compliance/staff_attendance_spec.md").read_text(encoding="utf-8")
        assert "**م-36." in spec and "مواصفة حضور الموظّفين والأذونات" in spec
        assert "ق-36" not in spec


# ══════════════════════════════════════════════════════════════════════
#  جولةُ الإصلاح 3 — عيوبُ المراجعة العدائيّة الثالثة
# ══════════════════════════════════════════════════════════════════════


class TestRoundThreeFixes:
    def test_marking_takes_the_same_row_lock_the_approval_takes(self, school, principal_user):
        """سباقُ الرصد والاعتماد: كلاهما يقفل صفَّ الموظّف، فلا يكتب أحدُهما فوق الآخر."""
        staff = _staff(school, 1)
        with CaptureQueriesContext(connection) as captured:
            _mark(school, staff, principal_user, FEB, "late", time(7, 30))

        locking = [q["sql"] for q in captured.captured_queries if "FOR UPDATE" in q["sql"].upper()]
        assert locking, "الرصدُ يكتب بلا قفلٍ — فيتسابق مع اعتماد الإذن"

    def test_a_simultaneous_second_marking_is_refused_by_name_not_by_five_hundred(
        self, school, principal_user, monkeypatch
    ):
        """القيدُ الفريدُ (school, staff, date) يُترجَم رسالةَ سياسةٍ لا خطأً غيرَ ملتقَط."""
        staff = _staff(school, 1)
        _mark(school, staff, principal_user, FEB, "late", time(7, 30))
        monkeypatch.setattr(
            StaffAttendanceService, "_locked_record", staticmethod(lambda *a, **k: None)
        )

        with pytest.raises(PolicyError, match="أعد تحميل"):
            _mark(school, staff, principal_user, FEB, "late", time(7, 40))


# ══════════════════════════════════════════════════════════════════════
#  جولةُ الإصلاح 3 — مطابقةُ المواصفة (م-1 … م-36) حيث خالفها الفرع
# ══════════════════════════════════════════════════════════════════════


def _approved_window(school, staff, day, start, end, kind="during_day"):
    """إذنٌ معتمدٌ بلا مرور بالمربّعات — لاختبار الحساب وحدَه."""
    return PermitRequest.objects.create(
        school=school,
        staff=staff,
        permit_type=kind,
        date=day,
        start_time=start,
        end_time=end,
        duration_minutes=minutes_between(start, end),
        reason="x",
        status="approved",
        stage="closed",
        deputy_role="vice_academic",
    )


class TestSpecAlignment:
    # ── م-8: الخروجُ المبكر يُعدّ حتّى أقرب اللحظتين: 14:00 أو بدءِ التغطية ──
    @pytest.mark.parametrize(
        ("check_out", "windows", "expected"),
        [
            (time(11, 0), [], 180),  # بلا تغطية: حتّى 14:00 (السياسة 1.1)
            (time(9, 30), [(time(10, 0), time(11, 0))], 210),  # م-5: الاستئذانُ يغطّي ساعتَه وحدَها
            (time(11, 0), [(time(13, 0), time(14, 0))], 120),  # حتّى بدء الخروج المبكر
            (time(12, 30), [(time(12, 0), time(14, 0))], 0),  # انصرف داخل نافذته
            (time(12, 0), [(time(10, 0), time(11, 0))], 120),  # نافذةٌ انقضت قبل انصرافه
        ],
    )
    def test_early_leave_counts_what_no_window_covers_until_two(self, check_out, windows, expected):
        """م-8 وم-5 (السياسة 1.1 «وينتهي في تمام الثانية ظهراً» وعنوان البند 4): التغطيةُ
        الممتدّة إلى 14:00 تحدّ العدَّ عند بدئها (نصّ م-8)، والنافذةُ في وسط الدوام تغطّي
        دقائقَها وحدَها (م-5)."""
        from staff_affairs.attendance import early_leave_minutes

        assert early_leave_minutes(check_out, windows) == expected

    def test_a_departure_before_a_day_permit_counts_all_but_its_window(
        self, school, principal_user
    ):
        """م-8 وم-5 على الرصد: استئذانٌ 10:00–11:00 معتمد وانصرافٌ 9:30 ← 270 − 60 = 210."""
        staff = _staff(school, 1)
        _approved_window(school, staff, FEB, time(10, 0), time(11, 0))
        record = StaffAttendanceService.mark(
            school=school,
            staff=staff,
            day=FEB,
            status="present",
            actor=principal_user,
            check_in=time(6, 50),
            check_out=time(9, 30),
        )
        assert record.early_leave_minutes == 210

    # ── م-9: يومُ الغياب بلا دقائق تأخّرٍ ولا خروجٍ مبكر ─────────────────────
    def test_an_absent_day_carries_neither_late_nor_early_minutes(self, school, principal_user):
        """م-9 (السياسة 5.1 و5.3): للغياب بابُه، فلا يُعدّ معه تأخّرٌ ولا انصراف."""
        staff = _staff(school, 1)
        record = StaffAttendanceService.mark(
            school=school,
            staff=staff,
            day=FEB,
            status="absent",
            actor=principal_user,
            check_in=time(10, 0),
            check_out=time(12, 0),
        )
        assert (record.late_minutes, record.early_leave_minutes) == (0, 0)

    # ── م-19 (3): من مسؤولُه المديرُ تُدمج خطوتُه في الاعتماد النهائيّ ───────
    @pytest.mark.parametrize("role", ["secretary", "vice_admin", "vice_academic", "accountant"])
    def test_whoever_reports_to_the_principal_meets_him_once(self, school, principal_user, role):
        """م-19 (3) وم-21 وم-22: السكرتير والنائبان وما لا بطاقةَ له — مسؤولُهم المدير،
        فخطوةُ «المسؤول المباشر والنائب المسؤول» تُدمج في مربّع المدير ولا تتكرّر."""
        applicant = _staff(school, 30, role=role)
        permit = _permit(school, applicant, FEB, time(7, 0), time(8, 0), "late_arrival", None)
        with _at(datetime.combine(FEB, MORNING)):
            recorder = PermitService.eligible_actors(permit)[0]
            PermitService.act(permit, actor=recorder, approve=True)
            permit.refresh_from_db()
            assert permit.stage == "principal"
            PermitService.act(permit, actor=principal_user, approve=True)
        permit.refresh_from_db()
        assert (permit.status, permit.reviewed_by) == ("approved", principal_user)
        assert (permit.supervisor_by, permit.deputy_by) == (principal_user, principal_user)
        decisions = AuditLog.objects.filter(
            object_id=str(permit.pk), action="update", user=principal_user
        ).exclude(changes__stage="secretary")
        assert decisions.count() == 1

    # ── م-19 (3 و4): «سبب الرفض» في مربّع الإدارة وحدَه ─────────────────────
    def test_a_line_manager_may_refuse_without_a_reason(self, school):
        """م-19 (3): «غير موافق» تُنهي الطلبَ مرفوضاً، والسببُ اختياريّ — مع الاسم والوقت."""
        staff, vice_academic = _staff(school, 1), _actor(school, "vice_academic")
        permit = _permit(school, staff, FEB, time(7, 0), time(8, 0), "late_arrival", None)
        with _at(datetime.combine(FEB, MORNING)):
            PermitService.act(permit, actor=_actor(school, "secretary"), approve=True)
            permit.refresh_from_db()
            PermitService.act(permit, actor=vice_academic, approve=False, reason="")
        permit.refresh_from_db()
        assert (permit.status, permit.rejected_stage, permit.rejection_reason) == (
            "rejected",
            "supervisor",
            "",
        )
        assert permit.supervisor_by == vice_academic and permit.supervisor_at is not None

    def test_the_principals_refusal_needs_its_reason(self, school):
        """م-19 (4): [ن02] مربّع «استخدام الإدارة»: موافق، غير موافق، «سبب الرفض» — إلزاميّ."""
        staff, principal = _staff(school, 1), _actor(school, "principal")
        permit = _permit(school, staff, FEB, time(7, 0), time(8, 0), "late_arrival", None)
        with _at(datetime.combine(FEB, MORNING)):
            for role in ("secretary", "vice_academic"):
                PermitService.act(permit, actor=_actor(school, role), approve=True)
                permit.refresh_from_db()
            with pytest.raises(PolicyError, match="سببُ الرفض"):
                PermitService.act(permit, actor=principal, approve=False, reason="  ")
            PermitService.act(permit, actor=principal, approve=False, reason="نصابٌ لا يُغطّى")
        permit.refresh_from_db()
        assert (permit.status, permit.rejected_stage, permit.reviewed_by) == (
            "rejected",
            "principal",
            principal,
        )

    # ── ز-8: لا مرحلةَ «deputy» مستقلّة ───────────────────────────────────
    def test_there_is_no_separate_deputy_stage(self):
        """م-19 (3) وز-8: المسؤولُ المباشر والنائبُ المسؤول خطوةٌ واحدة."""
        assert [key for key, _label in PERMIT_STAGES] == [
            "secretary",
            "coordinator",
            "supervisor",
            "principal",
            "external",
            "closed",
        ]

    # ── م-20: إلغاءُ الإذن المعتمد قبل بدء نافذته ─────────────────────────
    def test_an_approved_permit_is_cancelled_before_its_window_and_the_balance_returns(
        self, school
    ):
        """م-20 وم-10: يلغي الموظّفُ إذنَه المعتمد قبل بدء نافذته، فيُستردّ الرصيد ويُحفظ السجلّ."""
        staff = _staff(school, 1)
        permit = _permit(school, staff, date(2026, 2, 16), time(10, 0), time(11, 0))
        assert PermitService.balance(school, staff, FEB).approved == 60

        PermitService.cancel(permit, actor=staff)  # «الآن» 15 فبراير — قبل النافذة
        permit.refresh_from_db()
        assert (permit.status, permit.stage) == ("cancelled", "closed")
        assert PermitService.balance(school, staff, FEB).approved == 0
        assert PermitRequest.objects.filter(pk=permit.pk).exists()
        assert AuditLog.objects.filter(
            object_id=str(permit.pk), changes__status="cancelled"
        ).exists()

    def test_an_approved_permit_whose_window_began_is_not_cancelled(self, school):
        """م-20: الإلغاءُ قبل بدء النافذة وحدَه — وما بدأ يبقى محسوباً (م-10)."""
        staff = _staff(school, 1)
        permit = _permit(school, staff, date(2026, 2, 15), time(10, 0), time(11, 0))

        with _at(datetime(2026, 2, 15, 10, 0)), pytest.raises(PolicyError, match="بدء"):
            PermitService.cancel(permit, actor=staff)
        permit.refresh_from_db()
        assert permit.status == "approved"

    # ── م-25: الإنابةُ بغياب المدير المرصود أو بإنابةٍ صريحة — لا بنافذة إذنه ─
    def test_a_principal_inside_his_permit_window_is_not_replaced(self, school, principal_user):
        """م-25: «متى ثبت غياب المدير في رصد اليوم، غائباً أو في إجازة» — والإذنُ ليس منهما."""
        teacher, vice_admin = _staff(school, 1), _actor(school, "vice_admin")
        _approved_window(school, principal_user, DEFAULT_NOW.date(), time(10, 0), time(12, 0))
        permit = _permit(school, teacher, FEB, time(7, 0), time(8, 0), "late_arrival", None)
        for role in ("secretary", "vice_academic"):
            PermitService.act(permit, actor=_actor(school, role), approve=True)
            permit.refresh_from_db()

        with _at(datetime(2026, 2, 15, 10, 30)):
            assert vice_admin.pk not in _eligible(permit)
            with pytest.raises(PolicyError, match="بانتظار"):
                PermitService.act(permit, actor=vice_admin, approve=True)

    def test_a_principal_on_leave_is_replaced_only_by_a_tasking(self, school, principal_user):
        """م-43: غيابُ المدير في إجازةٍ لا يُنيب أحداً — التكليفُ قرارٌ صريحٌ منه."""
        teacher, vice_admin = _staff(school, 1), _actor(school, "vice_admin")
        permit = _permit(school, teacher, FEB, time(7, 0), time(8, 0), "late_arrival", None)
        for role in ("secretary", "vice_academic"):
            PermitService.act(permit, actor=_actor(school, role), approve=True)
            permit.refresh_from_db()
        StaffAttendanceService.mark(
            school=school,
            staff=principal_user,
            day=DEFAULT_NOW.date(),
            status="absent",
            actor=_actor(school, "secretary"),
            absence_type="casual",
        )
        assert vice_admin.pk not in _eligible(permit)
        _assign(school, principal_user, vice_admin)
        assert vice_admin.pk in _eligible(permit)

    def test_the_principal_tasks_a_deputy_from_the_assignments_screen(
        self, client_as, school, principal_user
    ):
        """م-43: شاشةُ «التكليفات» — المديرُ يكلّف نائبَه، والسجلُّ يبقى، ورسالتُها بلا «03:401»."""
        from staff_affairs.models import StaffAssignment

        vice_academic = _actor(school, "vice_academic")
        client = client_as(principal_user)
        page = client.get(reverse("staff_affairs:assignments"))
        assert page.status_code == 200 and "تكليفٌ جديد" in page.content.decode()
        response = client.post(
            reverse("staff_affairs:assignments"),
            {
                "assignee": str(vice_academic.pk),
                "start_date": "2026-02-15",
                "end_date": "2026-02-16",
                "reason": "مهمّةٌ خارج المدرسة",
            },
        )
        assert response.status_code == 302
        row = StaffAssignment.objects.get(school=school)
        assert (row.assignee, row.assigned_by, row.acting_role) == (
            vice_academic,
            principal_user,
            "principal",
        )
        client.post(reverse("staff_affairs:assignment_revoke", args=[row.pk]))
        row.refresh_from_db()
        assert row.revoked_by == principal_user  # يبقى في السجلّ ولا يُحذف
        source = Path("staff_affairs/views_attendance.py").read_text(encoding="utf-8")
        assert "03:401" not in source

    # ── م-24 وم-30: نموذج 03 يقرّره المديرُ أو من ينوب عنه ───────────────────
    def test_a_tasked_deputy_decides_form_03(self, school, principal_user):
        """م-30 وم-43: نموذج 03 يقرّره المديرُ أو من كلّفه بأعباء وظيفته."""
        from staff_affairs.attendance import ExceptionService

        staff, vice_admin = _staff(school, 1), _actor(school, "vice_admin")
        request = _exception(
            school, staff, principal_user, "late_arrival", FEB, FEB, time(7, 30), approve=None
        )
        with pytest.raises(PolicyError):
            ExceptionService.decide(request, actor=vice_admin, approve=True, feedback="موافق")
        assert request not in set(ExceptionService.awaiting(school, vice_admin))

        _assign(school, principal_user, vice_admin)
        assert request in set(ExceptionService.awaiting(school, vice_admin))
        ExceptionService.decide(request, actor=vice_admin, approve=True, feedback="موافق")
        request.refresh_from_db()
        assert (request.status, request.reviewed_by, request.decided_on_behalf) == (
            "approved",
            vice_admin,
            True,
        )
        with pytest.raises(PolicyError):
            ExceptionService.decide(
                _exception(
                    school,
                    _staff(school, 2),
                    principal_user,
                    "late_arrival",
                    FEB,
                    FEB,
                    time(7, 30),
                    approve=None,
                ),
                actor=_actor(school, "vice_academic"),
                approve=True,
                feedback="موافق",
            )

    # ── م-7: يُسجَّل مع العذر من قبله ووقتُ القبول ─────────────────────────
    def test_an_accepted_excuse_records_who_accepted_it_and_when(self, school, principal_user):
        """م-7: «ويُسجَّل مع العذر سببُه ومن قبله ووقتُ القبول» — وبالإنابة يُوسم (م-25)."""
        staff, vice_admin = _staff(school, 1), _actor(school, "vice_admin")
        record = StaffAttendanceService.mark(
            school=school,
            staff=staff,
            day=FEB,
            status="late",
            actor=principal_user,
            check_in=time(9, 30),
            accepted_excuse="تعطّل السيارة",
        )
        assert record.excuse_accepted_by == principal_user
        assert record.excuse_accepted_at is not None and record.excuse_on_behalf is False

        other = _staff(school, 2)
        _assign(school, principal_user, vice_admin)
        by_deputy = StaffAttendanceService.mark(
            school=school,
            staff=other,
            day=FEB,
            status="late",
            actor=vice_admin,
            check_in=time(9, 30),
            accepted_excuse="مراجعة",
        )
        assert (by_deputy.excuse_accepted_by, by_deputy.excuse_on_behalf) == (vice_admin, True)

    def test_a_recorder_may_rewrite_a_row_whose_excuse_was_already_accepted(
        self, school, principal_user
    ):
        """م-7: القبولُ للمدير — وإعادةُ السكرتير كتابةَ السطر بالعذر نفسِه ليست قبولاً جديداً."""
        staff, secretary = _staff(school, 1), _actor(school, "secretary")
        base = {
            "school": school,
            "staff": staff,
            "day": FEB,
            "status": "late",
            "check_in": time(9, 30),
            "accepted_excuse": "تعطّل السيارة",
        }
        StaffAttendanceService.mark(**base, actor=principal_user)
        record = StaffAttendanceService.mark(**base, actor=secretary, check_out=time(13, 30))
        assert (record.check_out, record.excuse_accepted_by) == (time(13, 30), principal_user)
        with pytest.raises(PolicyError, match="ينوب"):
            StaffAttendanceService.mark(**{**base, "accepted_excuse": "عذرٌ آخر"}, actor=secretary)

    # ── م-31: المرفقُ إلزاميّ ──────────────────────────────────────────────
    def test_an_exception_needs_an_attached_file(self, school):
        """م-31 ([ن03]): «يجب ارفاق مع طلب استثناء الخروج المبكر أو التأخير الصباحي ما يثبت
        حاجة الموظف لذلك» — ملفٌّ مرفق، لا وصفٌ نصّيّ."""
        from staff_affairs.attendance import ExceptionService

        base = {
            "school": school,
            "staff": _staff(school, 1),
            "exception_type": "early_departure",
            "start_date": FEB,
            "end_date": FEB,
            "boundary": time(13, 0),
            "content": "ظرف",
        }
        with pytest.raises(PolicyError, match="يثبت"):
            ExceptionService.submit(**base, evidence="وصفٌ بلا ملف", evidence_file=None)
        created = ExceptionService.submit(**base, evidence="", evidence_file=_evidence())
        assert created.evidence_file.name

    def test_the_attachment_is_served_to_the_owner_and_the_leadership_only(
        self, client, school, principal_user, teacher_user
    ):
        """م-31 مع حماية البيانات: المرفقُ قد يكون تقريراً طبيّاً — لصاحبه والمدير ونائبه."""
        from staff_affairs.attendance import ExceptionService

        owner = _staff(school, 1)
        created = ExceptionService.submit(
            school=school,
            staff=owner,
            exception_type="early_departure",
            start_date=FEB,
            end_date=FEB,
            boundary=time(13, 0),
            content="ظرف",
            evidence="",
            evidence_file=_evidence(),
        )
        url = created.evidence_file.url
        for user, allowed in (
            (owner, True),
            (principal_user, True),
            (_actor(school, "vice_admin"), True),
            (teacher_user, False),
            (_actor(school, "secretary"), False),
        ):
            client.force_login(user)
            assert (client.get(url).status_code == 200) is allowed, user

    # ── م-33: الاستثناءُ في التقرير مستقلّاً عن الأذونات ─────────────────────
    def test_the_report_shows_exception_days_apart_from_permits(self, school, principal_user):
        """م-33: لا يُحتسب من سقف 600، ويُعرض في التقرير الشهريّ مستقلّاً."""
        staff = _staff(school, 1)
        _exception(
            school,
            staff,
            principal_user,
            "early_departure",
            date(2026, 2, 1),  # الأحد
            date(2026, 2, 7),  # السبت — الجمعةُ والسبتُ خارج الدوام
            time(13, 0),
        )
        report = StaffAttendanceService.monthly_report(school, 2026, 2)
        row = next(r for r in report["rows"] if r["employee_number"] == "T-0001")
        assert (row["exception_days"], row["permit_minutes"], row["permit_remaining"]) == (
            5,
            0,
            600,
        )
        headers = [c.value for c in StaffAttendanceService.monthly_workbook(report).active[1]]
        assert "أيام الاستثناء (نموذج 03)" in headers

    def test_the_report_page_renders_with_its_cards(self, client_as, school, principal_user):
        """م-36: صفحةُ التقرير تُفتح (كان شريطُ البطاقات يتجاوز حدَّه فيسقط)."""
        _staff(school, 1)
        page = client_as(principal_user).get(
            reverse("staff_affairs:attendance_report"), {"month": "2026-02"}
        )
        html = page.content.decode()
        assert page.status_code == 200
        assert "بعد المهلة" in html and "أيام الاستثناء" in html

    # ── ز: تصحيحاتُ الاستخراج الباقية ─────────────────────────────────────
    def test_the_remaining_extraction_corrections_are_in(self):
        """ز-2 وز-3 وز-5 وز-6 وز-7 من المواصفة."""
        base = Path("AAdocs/ministry_data/2026_2027")
        third = (base / "07b_forms_catalog_thirdpass.md").read_text(encoding="utf-8")
        assert "| 03 | نموذج طلب (عام)" not in third  # ز-3
        assert "(وقت معالجة السكرتارية للطلب)" not in third  # ز-2
        policy = (base / "06_attendance_performance_review.md").read_text(encoding="utf-8")
        assert "الرئيس المباشر حصراً" not in policy  # ز-5
        roles = (base / "rbac_roles.json").read_text(encoding="utf-8")
        assert "يشارك (لا ينفرد)" not in roles  # ز-6
        matrix = (base / "rbac_permissions_matrix.md").read_text(encoding="utf-8")
        assert "إنابة كاملة *(تفسير المستخرِج" in matrix  # ز-7
        cards = (base / "03_job_descriptions_rbac.md").read_text(encoding="utf-8")
        assert "صلاحية إنابة صريحة عن مدير المدرسة** في حال غيابه *(تفسير المستخرِج" in cards


# ══════════════════════════════════════════════════════════════════════
#  جولةُ الإصلاح 4 — عيوبُ المراجعة، كلٌّ باختبارٍ يسقط قبل الإصلاح
# ══════════════════════════════════════════════════════════════════════

#: نوعُ يوم غيابٍ من سجلّ الغياب («عارضة»).
ABSENCE_KEY = "casual"


class TestRoundFour:
    # ── م-7 وم-24: النائبُ الإداريّ يقبل العذرَ من الشاشة حين ينوب ─────────────
    def test_the_admin_deputy_accepts_an_excuse_from_the_board_when_standing_in(
        self, client_as, school, principal_user
    ):
        """م-24 (بطاقة 1034: «الإنابة عن المدير في مهامه في حال غيابه») تشمل قبولَ العذر
        في م-7 — فالشاشةُ تُفتح له حين تقوم الإنابة، وتُغلق دونه والمديرُ حاضر."""
        staff, vice_admin = _staff(school, 1), _actor(school, "vice_admin")
        client = client_as(vice_admin)
        url = reverse("staff_affairs:attendance_mark")
        post = {
            "staff_id": staff.pk,
            "date": "2026-02-15",
            "status": "late",
            "check_in": "09:30",
            "accepted_excuse": "تعطّل السيارة",
        }

        board = client.get(reverse("staff_affairs:attendance_board"), {"date": "2026-02-15"})
        assert board.status_code == 200 and f"sa-att-{staff.pk}" not in board.content.decode()
        assert client.post(url, post).status_code == 403
        with pytest.raises(PolicyError, match="ينوب"):
            _mark(school, _staff(school, 2), vice_admin, FEB, "absent")

        _assign(school, principal_user, vice_admin)
        board = client.get(reverse("staff_affairs:attendance_board"), {"date": "2026-02-15"})
        assert f"sa-att-{staff.pk}" in board.content.decode()
        assert client.post(url, post).status_code == 200
        record = StaffAttendance.objects.get(staff=staff, date=DEFAULT_NOW.date())
        assert (record.status, record.late_minutes) == ("late", 150)
        assert (record.excuse_accepted_by, record.excuse_on_behalf) == (vice_admin, True)
        assert AuditLog.objects.filter(
            object_id=str(record.pk), changes__acting_role="principal"
        ).exists()

    # ── م-8 وم-5: لا يُسقط استئذانٌ بعد الانصراف بقيّةَ اليوم ─────────────────
    @pytest.mark.parametrize(
        ("check_out", "windows", "expected"),
        [
            (time(10, 5), [(time(10, 0), time(11, 0))], 180),  # 11:00–14:00 بلا إذن
            (time(9, 30), [(time(9, 31), time(9, 32))], 269),  # إذنُ دقيقةٍ يغطّي دقيقة
            (time(11, 0), [(time(12, 0), time(14, 0)), (time(13, 0), time(14, 0))], 60),
            (time(14, 0), [], 0),
        ],
    )
    def test_a_window_covers_its_own_minutes_only(self, check_out, windows, expected):
        """م-5: «الإذن يغطّي نافذته المعتمدة وحدها، ولا يلحق اليوم كلّه» — وم-8 بتناظر م-6."""
        from staff_affairs.attendance import early_leave_minutes

        assert early_leave_minutes(check_out, windows) == expected

    # ── م-30: قرارُ نموذج 03 لا يكتب فوق قرارٍ سبقه ────────────────────────
    def test_a_form_03_decision_does_not_overwrite_a_simultaneous_one(
        self, school, principal_user, monkeypatch
    ):
        """م-30 وم-24: المديرُ ونائبُه في غيابه يريان الطلبَ معاً — فالقرارُ الثاني يُردّ."""
        from staff_affairs.attendance import ExceptionService
        from staff_affairs.models import AttendanceException

        staff = _staff(school, 1)
        request = _exception(
            school, staff, principal_user, "late_arrival", FEB, FEB, time(7, 30), approve=None
        )
        real = ExceptionService._deciders

        def _approved_meanwhile(school_, applicant):
            AttendanceException.objects.filter(pk=request.pk).update(
                status="approved", feedback="سبقه قرار"
            )
            return real(school_, applicant)

        monkeypatch.setattr(ExceptionService, "_deciders", staticmethod(_approved_meanwhile))
        with CaptureQueriesContext(connection) as queries:
            with pytest.raises(PolicyError, match="للتوّ"):
                ExceptionService.decide(request, actor=principal_user, approve=False, feedback="لا")
        request.refresh_from_db()
        # الكتابةُ المحاكاةُ في المعاملة نفسِها فتُطوى معها — والمهمّ أنّ «مرفوض» لم يُكتب.
        assert request.status != "rejected"
        assert any(
            "FOR UPDATE" in q["sql"] and "staff_affairs_attendanceexception" in q["sql"]
            for q in queries.captured_queries
        )

    # ── م-7: قبولُ العذر لا يُنقل إلى وقتٍ آخر ─────────────────────────────
    def test_a_recorder_cannot_move_an_accepted_excuse_to_another_time(
        self, school, principal_user
    ):
        """م-7: جهةُ القبول المديرُ أو من ينوب عنه — وقبولُه لحضور 09:10 لا يمتدّ إلى 13:30."""
        staff, secretary = _staff(school, 1), _actor(school, "secretary")
        base = {
            "school": school,
            "staff": staff,
            "day": FEB,
            "status": "late",
            "accepted_excuse": "تعطّل السيارة",
        }
        StaffAttendanceService.mark(**base, actor=principal_user, check_in=time(9, 10))
        with pytest.raises(PolicyError, match="قبولاً جديداً"):
            StaffAttendanceService.mark(**base, actor=secretary, check_in=time(13, 30))
        record = StaffAttendance.objects.get(staff=staff, date=FEB)
        assert (record.check_in, record.late_minutes) == (time(9, 10), 130)

        # ولا يمحو الراصدُ العذرَ ليمرّ الوقتُ الجديد — رفعُه لجهة القبول (جولة 5).
        without = {**base, "status": "absent", "accepted_excuse": ""}
        with pytest.raises(PolicyError, match="ينوب"):
            StaffAttendanceService.mark(**without, actor=secretary, check_in=time(13, 30))
        record = StaffAttendanceService.mark(**without, actor=principal_user, check_in=time(13, 30))
        assert (record.status, record.excuse_accepted_by) == ("absent", None)
        record = StaffAttendanceService.mark(**base, actor=principal_user, check_in=time(13, 30))
        assert (record.status, record.late_minutes) == ("late", 390)
        assert record.excuse_accepted_by == principal_user

    # ── م-25 وم-4: رصدُ المدير غائباً يُقيم الإنابة — فيُقيَّد ويُكشف ────────────
    def test_absence_is_not_marked_for_today_before_nine_without_its_type(
        self, school, principal_user
    ):
        """م-4 (السياسة 2.4 «إذا حضر بعد الساعة التاسعة»): قبل التاسعة لا غيابَ ثابتاً
        لليوم — إلّا بنوعه من سجلّ الغياب — فلا تقوم به إنابةٌ مبكّرة (م-25)."""
        secretary, vice_admin = _actor(school, "secretary"), _actor(school, "vice_admin")
        with _at(datetime(2026, 2, 15, 8, 30)):
            with pytest.raises(PolicyError, match="التاسعة"):
                _mark(school, principal_user, secretary, date(2026, 2, 15), "absent")
            assert not StaffAttendanceService.can_record(school, vice_admin)
            on_leave = StaffAttendanceService.mark(
                school=school,
                staff=principal_user,
                day=date(2026, 2, 15),
                status="absent",
                actor=secretary,
                absence_type=ABSENCE_KEY,
            )
            assert on_leave.absence_type == ABSENCE_KEY
            _mark(school, _staff(school, 1), secretary, date(2026, 2, 14), "absent")  # يومٌ مضى

    # ── م-35 وم-36: بطاقاتُ التقرير لا تُقصّ ──────────────────────────────
    def test_each_report_card_carries_one_short_figure(self, client_as, school, principal_user):
        """م-35 وم-36: «غُطّي بعد المهلة» رقمٌ في بطاقته — لا ذيلٌ يُقصّ بنقاط في حاشية."""
        _staff(school, 1)
        html = (
            client_as(principal_user)
            .get(reverse("staff_affairs:attendance_report"), {"month": "2026-02"})
            .content.decode()
        )
        subs = re.findall(r'class="ui-kpi__sub">([^<]*)<', html)
        labels = re.findall(r'class="ui-kpi__label">([^<]*)<', html)
        assert "غُطّي بعد المهلة" in labels
        assert subs and all("·" not in sub and len(sub) <= 20 for sub in subs), subs

    # ── الهجرة: أثرُ 0003_wave3g المحذوفة في قواعد الجلسات الشقيقة ─────────────
    def test_the_orphan_wave3g_migration_is_cleared_before_the_tables_are_built(self):
        """قواعدُ جلساتٍ طُبّقت فيها 0003_wave3g (644e2880) تسقط بـ«already exists» — فتُزال
        جداولُها الفارغة وسجلُّها، ويتوقّف الحذفُ متى وُجدت بيانات."""
        import importlib

        module = importlib.import_module(
            "staff_affairs.migrations.0003_squashed_0010_staff_attendance_and_permits"
        )
        probe, name = "zz_orphan_probe", "0000_orphan_probe"
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE TABLE {probe} (id integer)")
            cursor.execute(
                "INSERT INTO django_migrations (app, name, applied) VALUES (%s, %s, now())",
                ["staff_affairs", name],
            )
            cursor.execute(f"INSERT INTO {probe} VALUES (1)")
        with pytest.raises(RuntimeError, match="session-db"):
            module.clear_orphan(connection, name, (probe,))
        with connection.cursor() as cursor:
            assert probe in connection.introspection.table_names(cursor)
            cursor.execute(f"DELETE FROM {probe}")

        module.clear_orphan(connection, name, (probe,))
        with connection.cursor() as cursor:
            assert probe not in connection.introspection.table_names(cursor)
            cursor.execute(
                "SELECT count(*) FROM django_migrations WHERE app = %s AND name = %s",
                ["staff_affairs", name],
            )
            assert cursor.fetchone()[0] == 0
        module.clear_orphan(connection, name, (probe,))  # بلا سجلٍّ: لا شيء


# ══════════════════════════════════════════════════════════════════════
#  جولة الإصلاح 4 (ب) — قيدُ العذر لا تمحوه إعادةُ الحساب
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestExcuseSurvivesReconcile:
    def test_an_approved_exception_keeps_the_accepted_excuse_on_record(
        self, school, principal_user
    ):
        """م-7 ([س] 2.4 «عذر مقبول»): «ويُسجَّل مع العذر سببُه ومن قبله ووقتُ القبول» — ومبدأ
        الاختيارات الهندسيّة «ولا تُفقد بيانات». استثناءُ نموذج 03 (م-32) يُعتمد بعد القبول
        فيُعيد التصنيفَ «مستأذن»، والعذرُ يبقى بقابله ووقته، ساكناً لا يُحتسب."""
        staff = _staff(school, 1)
        record = StaffAttendanceService.mark(
            school=school,
            staff=staff,
            day=FEB,
            status="late",
            actor=principal_user,
            check_in=time(9, 30),
            accepted_excuse="مراجعة مستشفى",
        )
        accepted_at = record.excuse_accepted_at
        assert (record.status, record.late_minutes) == ("late", 150)

        _exception(school, staff, principal_user, "late_arrival", FEB, FEB, time(10, 0))
        record.refresh_from_db()
        assert (record.status, record.late_minutes) == ("permitted", 0)
        assert record.accepted_excuse == "مراجعة مستشفى"
        assert (record.excuse_accepted_by, record.excuse_accepted_at) == (
            principal_user,
            accepted_at,
        )
        assert record.excuse_on_behalf is False

        # والسكرتيرُ يعيد كتابةَ السطر بالعذر الساكن نفسِه (اللوحةُ تملؤه) — فلا يُرفض ولا يُمحى.
        secretary = _actor(school, "secretary")
        record = StaffAttendanceService.mark(
            school=school,
            staff=staff,
            day=FEB,
            status="permitted",
            actor=secretary,
            check_in=time(9, 30),
            check_out=time(14, 0),
            accepted_excuse="مراجعة مستشفى",
        )
        assert (record.status, record.excuse_accepted_by) == ("permitted", principal_user)
        # وعذرٌ جديدٌ لا حاجةَ إليه يبقى مرفوضاً ولو من المدير.
        with pytest.raises(PolicyError, match="بلا إذنٍ يغطّيه"):
            StaffAttendanceService.mark(
                school=school,
                staff=staff,
                day=FEB,
                status="permitted",
                actor=principal_user,
                check_in=time(9, 30),
                accepted_excuse="عذرٌ آخر",
            )

    def test_a_kept_excuse_does_not_ride_on_an_absence_without_arrival(
        self, school, principal_user
    ):
        """م-7 ([س] 2.4): العذرُ يجعل «الحضورَ» بعد 9:00 تأخّراً — فلا يُحمل على يومٍ مُحي وقتُ
        حضوره فصار غياباً بلا وقت."""
        staff, secretary = _staff(school, 1), _actor(school, "secretary")
        base = {"school": school, "staff": staff, "day": FEB, "accepted_excuse": "تعطّل السيارة"}
        StaffAttendanceService.mark(
            **base, status="late", actor=principal_user, check_in=time(9, 30)
        )
        with pytest.raises(PolicyError):
            StaffAttendanceService.mark(**base, status="absent", actor=secretary)


class TestRoundFive:
    # ── م-7: رفعُ العذر المقبول قرارٌ في العذر — لجهة القبول وحدَها ────────────
    @pytest.mark.parametrize("check_in", [time(9, 30), None])
    def test_a_recorder_cannot_withdraw_an_excuse_the_principal_accepted(
        self, school, principal_user, check_in
    ):
        """م-7: «جهة القبول: المدير، أو من ينوب عنه وفق م-24» — فمحوُ العذر الذي قبِله
        نقضٌ لقراره، لا يملكه من يرصد الوقت. ولا يُفقد قيدُه (درجات الثقة: «ولا تُفقد
        بيانات»)، وإلّا صار اليومُ غياباً يُخصم (البند 5.3)."""
        staff, secretary = _staff(school, 1), _actor(school, "secretary")
        accepted = StaffAttendanceService.mark(
            school=school,
            staff=staff,
            day=FEB,
            status="late",
            actor=principal_user,
            check_in=time(9, 30),
            accepted_excuse="مراجعة مستشفى",
        )
        with pytest.raises(PolicyError, match="ينوب"):
            StaffAttendanceService.mark(
                school=school,
                staff=staff,
                day=FEB,
                status="absent",
                actor=secretary,
                check_in=check_in,
                accepted_excuse="",
            )
        record = StaffAttendance.objects.get(staff=staff, date=FEB)
        assert (record.status, record.late_minutes, record.accepted_excuse) == (
            "late",
            150,
            "مراجعة مستشفى",
        )
        assert (record.excuse_accepted_by, record.excuse_accepted_at) == (
            principal_user,
            accepted.excuse_accepted_at,
        )

    def test_the_principal_side_withdraws_an_excuse_and_the_trail_names_both(
        self, school, principal_user
    ):
        """م-7 وم-24 وم-25: المديرُ — أو نائبُه الإداريّ في غيابه — يرفع العذر، ويبقى في
        التدقيق من قبِله ومتى ومن رفعه، وبالإنابة يُوسم."""
        staff, vice_admin = _staff(school, 1), _actor(school, "vice_admin")
        base = {"school": school, "staff": staff, "day": FEB, "check_in": time(9, 30)}
        StaffAttendanceService.mark(
            **base, status="late", actor=principal_user, accepted_excuse="تعطّل السيارة"
        )
        record = StaffAttendanceService.mark(**base, status="absent", actor=principal_user)
        assert (record.status, record.accepted_excuse, record.excuse_accepted_by) == (
            "absent",
            "",
            None,
        )
        trail = AuditLog.objects.get(object_id=str(record.pk), changes__excuse_withdrawn=True)
        assert trail.user == principal_user
        assert trail.changes["excuse_accepted_by_id"][0] == str(principal_user.pk)
        assert trail.changes["accepted_excuse"] == [True, False]

        other = _staff(school, 2)
        StaffAttendanceService.mark(
            **{**base, "staff": other},
            status="late",
            actor=principal_user,
            accepted_excuse="مراجعة",
        )
        with pytest.raises(PolicyError, match="ينوب"):
            StaffAttendanceService.mark(
                **{**base, "staff": other}, status="absent", actor=vice_admin
            )
        _assign(school, principal_user, vice_admin)
        record = StaffAttendanceService.mark(
            **{**base, "staff": other}, status="absent", actor=vice_admin
        )
        assert record.status == "absent"
        assert AuditLog.objects.filter(
            object_id=str(record.pk),
            changes__excuse_withdrawn=True,
            changes__acting_role="principal",
        ).exists()

    # ── م-18ب وم-17: الكنسُ لا يكتب «منتهٍ» فوق اعتمادٍ سبقه ────────────────
    def test_the_sweep_does_not_expire_a_permit_approved_meanwhile(
        self, school, principal_user, monkeypatch
    ):
        """م-18ب: الإغلاقُ الآليّ لما «بقي معلَّقاً حتى بدأت نافذته» وحدَه — فالمعتمدُ قبل
        بدئها يبقى معتمداً، ومحسوباً من الرصيد (م-17) ومن الإذن الواحد (م-14)."""
        staff = _staff(school, 1)
        day = date(2026, 2, 15)
        permit = _permit(school, staff, day, time(10, 0), time(11, 0), approve=None)
        real = PermitService._expire

        def _approved_meanwhile(stale, request=None):
            # قرأ الكنسُ الطلبَ معلَّقاً، ثمّ التزم اعتمادُ المدير قبل أن يكتب.
            PermitRequest.objects.filter(pk=stale.pk).update(status="approved", stage="closed")
            return real(stale, request)

        monkeypatch.setattr(PermitService, "_expire", staticmethod(_approved_meanwhile))
        with _at(datetime(2026, 2, 15, 10, 0)):
            assert PermitService.expire_due(school) == 0
        permit.refresh_from_db()
        assert (permit.status, permit.stage) == ("approved", "closed")
        assert not AuditLog.objects.filter(
            object_id=str(permit.pk), changes__cause="not_approved_before_start"
        ).exists()
        assert PermitService.balance(school, staff, day).approved == 60

    def test_a_decision_locks_the_permit_row_itself(self, school):
        """م-18ب: القرارُ يقفل صفَّ الطلب — فكنسٌ لا يأخذ قفلَ الموظّف ينتظره ثمّ يجده مقرَّراً."""
        staff = _staff(school, 1)
        permit = _permit(school, staff, date(2026, 2, 15), time(10, 0), time(11, 0), approve=None)
        with _at(datetime(2026, 2, 15, 6, 0)):
            with CaptureQueriesContext(connection) as queries:
                PermitService.act(permit, actor=_actor(school, "secretary"), approve=True)
            with CaptureQueriesContext(connection) as cancelled:
                PermitService.cancel(permit, actor=staff)
        for captured in (queries, cancelled):
            assert any(
                "FOR UPDATE" in q["sql"] and "staff_affairs_permitrequest" in q["sql"]
                for q in captured.captured_queries
            )


class TestRoundSix:
    # ── م-25 وم-20: الإنابةُ الصريحةُ أثرٌ لا يُمحى، ويسمّي النائبَ بعينه ─────────
    def test_revoking_an_assignment_keeps_its_record_and_names_the_assignee(
        self, school, principal_user
    ):
        """م-43 وم-20: «لا يُحذف أيّ طلبٍ ولا قرار» — والتكليفُ المرفوعُ يبقى باسم من كُلّف."""
        from staff_affairs.attendance import AssignmentService
        from staff_affairs.models import StaffAssignment

        teacher, vice_admin = _staff(school, 1), _actor(school, "vice_admin")
        permit = _permit(school, teacher, FEB, time(7, 0), time(8, 0), "late_arrival", None)
        for actor in (_actor(school, "secretary"), _actor(school, "vice_academic")):
            PermitService.act(permit, actor=actor, approve=True)
            permit.refresh_from_db()
        assignment = _assign(school, principal_user, vice_admin)
        PermitService.act(permit, actor=vice_admin, approve=True)
        decision = AuditLog.objects.get(object_id=str(permit.pk), changes__on_behalf_of="principal")
        assert decision.changes["assignment"] == str(assignment.pk)

        AssignmentService.revoke(assignment, actor=principal_user)

        kept = StaffAssignment.objects.get(pk=assignment.pk)
        assert (kept.assignee, kept.revoked_by) == (vice_admin, principal_user)
        assert kept.revoked_at is not None
        trail = AuditLog.objects.filter(object_id=str(assignment.pk)).order_by("timestamp")
        assert [entry.changes.get("assignee") for entry in trail] == [str(vice_admin.pk)] * 2
        assert trail.last().changes.get("revoked") is True
        other = _permit(
            school, _staff(school, 2), FEB, time(7, 0), time(8, 0), "late_arrival", None
        )
        for actor in (_actor(school, "secretary"), _actor(school, "vice_academic")):
            PermitService.act(other, actor=actor, approve=True)
            other.refresh_from_db()
        assert vice_admin.pk not in _eligible(other)

    def test_each_deputy_tasks_only_his_own_people(self, school, principal_user):
        """قرارُ المدرسة: النائبُ الأكاديميّ يكلّف المنسّقين، والنائبُ الإداريّ من تحته، والمديرُ
        نائبَيه — ولا يكلّف غيرَهما إلّا إن غاب النائبان معاً."""
        from staff_affairs.attendance import AssignmentService

        vice_admin, vice_academic = _actor(school, "vice_admin"), _actor(school, "vice_academic")
        coordinator = _staff(school, 50, "coordinator")
        supervisor = _staff(school, 51, "admin_supervisor")
        teacher = _staff(school, 52)
        day = DEFAULT_NOW.date()

        def take(assigner, assignee):
            return AssignmentService.assign(
                school=school,
                assigner=assigner,
                assignee=assignee,
                start=day,
                end=day,
                reason="غياب",
            )

        assert take(vice_academic, coordinator).acting_role == "vice_academic"
        assert take(vice_admin, supervisor).acting_role == "vice_admin"
        with pytest.raises(PolicyError, match="المنسّقين"):
            take(vice_academic, teacher)
        with pytest.raises(PolicyError, match="تحت مسؤوليته"):
            take(vice_admin, teacher)
        with pytest.raises(PolicyError, match="نائبَيه"):
            take(principal_user, teacher)  # النائبان حاضران
        with pytest.raises(PolicyError, match="لا يكلّف الموظّفُ نفسَه"):
            take(vice_admin, vice_admin)
        assert take(principal_user, vice_academic).acting_role == "principal"

        secretary = _actor(school, "secretary")
        for deputy in (vice_admin, vice_academic):  # غاب النائبان معاً
            StaffAttendanceService.mark(
                school=school,
                staff=deputy,
                day=day,
                status="absent",
                actor=secretary,
                absence_type="sick",
            )
        assert take(principal_user, teacher).acting_role == "principal"

    def test_an_assignment_never_exceeds_an_academic_year_or_reaches_back(
        self, school, principal_user
    ):
        from datetime import timedelta

        from staff_affairs.attendance import AssignmentService

        vice_admin = _actor(school, "vice_admin")
        day = DEFAULT_NOW.date()
        base = {"school": school, "assigner": principal_user, "assignee": vice_admin}
        with pytest.raises(PolicyError, match="رجعيّ"):
            AssignmentService.assign(**base, start=day - timedelta(days=1), end=day, reason="غياب")
        with pytest.raises(PolicyError, match="عاماً"):
            AssignmentService.assign(
                **base, start=day, end=day + timedelta(days=365), reason="غياب"
            )
        with pytest.raises(PolicyError, match="سببُ"):
            AssignmentService.assign(**base, start=day, end=day, reason=" ")

    # ── م-4 وم-8 وم-25: لا يُرصد اليومَ وقتٌ لم يأتِ بعد ─────────────────────
    def test_today_a_time_that_has_not_come_yet_is_refused(self, school, principal_user):
        """م-4 ([س] 2.4 «إذا حضر بعد الساعة التاسعة»): الغيابُ بحضورٍ بعد 9:00 لا يُعرف
        قبل أن يقع — فلا يُرصد في الثامنة حضورٌ في 9:30، ولا تقوم به إنابةٌ (م-25). وم-8
        ([س] 1.1): لا يُكتب في العاشرة انصرافٌ في 14:00."""
        from notifications.models import InAppNotification

        secretary, staff = _actor(school, "secretary"), _staff(school, 1)
        today = DEFAULT_NOW.date()
        with _at(datetime.combine(today, time(8, 0))):
            with pytest.raises(PolicyError, match="لم يأتِ"):
                _mark(school, principal_user, secretary, today, "absent", time(9, 30))
            assert not StaffAttendance.objects.filter(staff=principal_user).exists()
            assert not InAppNotification.objects.filter(user=principal_user).exists()
            # الدقيقةُ نفسُها جائزة (م-2)
            assert _mark(school, staff, secretary, today, "late", time(8, 0)).late_minutes == 60
        with _at(datetime.combine(today, time(10, 0))):
            with pytest.raises(PolicyError, match="لم يأتِ"):
                StaffAttendanceService.mark(
                    school=school,
                    staff=staff,
                    day=today,
                    status="late",
                    actor=secretary,
                    check_in=time(8, 0),
                    check_out=time(14, 0),
                )
        # ويومٌ مضى يُرصد بأوقاته كلّها
        record = StaffAttendanceService.mark(
            school=school,
            staff=staff,
            day=FEB,
            status="present",
            actor=secretary,
            check_in=time(7, 0),
            check_out=time(14, 0),
        )
        assert record.early_leave_minutes == 0

    # ── م-36: بطاقةُ «أيام حضور» على قدر الجدول ────────────────────────────
    def test_the_attendance_card_does_not_claim_to_include_permitted_days(
        self, client_as, school, principal_user
    ):
        """م-36 ([س] 5.1 و5.2): التقريرُ سندُ الإشعار بالخصم — فبطاقتُه تعدّ ما يعدّه
        الجدول: «حاضر» وحدَه، و«مستأذن» منفصلاً."""
        staff = _staff(school, 1)
        for n, status in enumerate(["present"] * 3 + ["permitted"] * 2, start=2):
            StaffAttendance.objects.create(
                school=school, staff=staff, date=date(2026, 2, n), status=status
            )
        page = (
            client_as(principal_user)
            .get(reverse("staff_affairs:attendance_report"), {"month": "2026-02"})
            .content.decode()
        )
        card = re.search(
            r'<div class="ui-kpi[^>]*><span class="ui-kpi__label">أيام حضور</span>.*?</div>',
            page,
            re.S,
        )
        assert card, "بطاقةُ أيّام الحضور"
        text = card.group(0)
        assert "ومنها" not in text
        assert '<span class="ui-kpi__value">3</span>' in text
        sub = re.search(r'ui-kpi__sub">([^<]*)<', text)
        assert sub and sub.group(1).endswith("2")
        assert "منفصل" in text

    # ── م-7: نصُّ العذر لجهة القبول وحدَها، والراصدُ يكتب الوقت ────────────────
    def test_the_recorder_neither_sees_nor_is_offered_the_excuse_text(
        self, client_as, school, principal_user
    ):
        """م-7: «جهة القبول: المدير، أو من ينوب عنه وفق م-24» — فحقلُ العذر لها، ونصُّه قد
        يحمل بيانةً صحّيّة (PDPPL م.16) فلا يُعرض لمن يرصد الوقت. ويبقى للراصد أن يكتب
        الانصراف في سطرٍ قُبل عذرُه (م-8) دون أن يُعدّ ذلك رفعاً للعذر."""
        staff, secretary = _staff(school, 1), _actor(school, "secretary")
        secret = "مراجعة طبية اصطناعية"
        StaffAttendanceService.mark(
            school=school,
            staff=staff,
            day=FEB,
            status="late",
            actor=principal_user,
            check_in=time(9, 30),
            accepted_excuse=secret,
        )
        board = reverse("staff_affairs:attendance_board")
        as_secretary = client_as(secretary).get(board, {"date": "2026-02-01"}).content.decode()
        assert secret not in as_secretary
        assert 'name="accepted_excuse"' not in as_secretary
        assert "بعذر" in as_secretary

        clicked = client_as(secretary).post(
            reverse("staff_affairs:attendance_mark"),
            {
                "staff_id": staff.pk,
                "date": "2026-02-01",
                "status": "late",
                "check_in": "09:30",
                "check_out": "13:00",
            },
        )
        body = clicked.content.decode()
        assert 'role="alert"' not in body and secret not in body
        record = StaffAttendance.objects.get(staff=staff, date=FEB)
        assert (record.accepted_excuse, record.early_leave_minutes, record.status) == (
            secret,
            60,
            "late",
        )
        # ومن أرسل الحقلَ فارغاً عمداً — لا من الواجهة — فهو رفعٌ يُردّ عليه باسم م-7.
        crafted = client_as(secretary).post(
            reverse("staff_affairs:attendance_mark"),
            {
                "staff_id": staff.pk,
                "date": "2026-02-01",
                "status": "absent",
                "check_in": "09:30",
                "accepted_excuse": "",
            },
        )
        assert "ينوب" in crafted.content.decode()
        assert secret not in crafted.content.decode()

        as_principal = client_as(principal_user).get(board, {"date": "2026-02-01"}).content.decode()
        assert secret in as_principal and 'name="accepted_excuse"' in as_principal

    def test_the_retention_register_names_the_sensitive_free_text(self):
        """م-7 وم-12: العذرُ المقبول وسببُ الإذن نصّان حرّان قد يحملان بيانةً صحّيّة، وم-25:
        الإنابةُ المرفوعةُ تبقى."""
        register = Path("docs/privacy/data_retention.md").read_text(encoding="utf-8")
        rows = {
            line.split("|")[1].strip(" `"): line
            for line in register.splitlines()
            if line.startswith("| `staff_affairs_")
        }
        assert "PDPPL" in rows["staff_affairs_staffattendance"]
        assert "من ينوب عنه" in rows["staff_affairs_staffattendance"]
        assert "سبب" in rows["staff_affairs_permitrequest"]
        assert "PDPPL" in rows["staff_affairs_permitrequest"]
        assert "الرفعُ لا يحذف" in rows["staff_affairs_staffassignment"]


class TestRoundSeven:
    # ── م-4 وم-5 وم-6: كلُّ نافذةٍ معتمدةٍ تغطّي لحظةَ الحضور، أيّاً كان نوعُها ──────
    @pytest.mark.parametrize(
        ("windows", "check_in", "excused", "expected"),
        [
            # م-5 «الحضور داخل النافذة: مستأذن» — ولو جاوز التاسعة (م-4 «إلّا … أن يغطّي
            # إذنٌ معتمد لحظةَ حضوره»)؛ وما قبل بدء النافذة غيرُ مأذونٍ فيُعدّ (حجّة م-6).
            ([(time(7, 30), time(9, 30))], time(9, 20), False, ("permitted", 30)),
            ([(time(7, 15), time(8, 0))], time(7, 50), False, ("permitted", 15)),
            # م-6 «من اللحظة الأبعد بين 07:00 ونهاية آخر تغطيةٍ معتمدة حتى وقت الحضور».
            ([(time(7, 30), time(8, 0))], time(8, 40), False, ("late", 40)),
            # م-5 «بعد نهاية النافذة وبعد 09:00: غائب، ما لم يوجد عذرٌ مقبول» — وم-7.
            ([(time(7, 30), time(9, 30))], time(9, 40), False, ("absent", 0)),
            ([(time(7, 30), time(9, 30))], time(10, 0), True, ("late", 30)),
            # نافذةٌ لم تبدأ لا تغطّي شيئاً، والتي تبدأ لحظةَ الحضور لم تُستعمل.
            ([(time(10, 0), time(11, 0))], time(8, 0), False, ("late", 60)),
            ([(time(9, 0), time(10, 0))], time(9, 0), False, ("late", 120)),
        ],
    )
    def test_any_approved_window_covers_the_arrival(self, windows, check_in, excused, expected):
        """م-5: «الإذن يغطّي نافذته المعتمدة وحدها … الحضور داخل النافذة: «مستأذن»» — بلا
        تفريقٍ بين الأنواع؛ والسياسة 2.4: «غائبا إذا حضر بعد الساعة التاسعة صباحاً دون إذن»."""
        assert classify_arrival(check_in, excused=excused, windows=windows) == expected

    def test_arriving_inside_an_approved_during_day_permit_is_not_absence(
        self, school, principal_user
    ):
        """م-4 وم-5 (السياسة 2.4 و4.1، ونموذج 02 «أثناء الدوام»): استئذانٌ معتمدٌ 07:30–09:30
        وحضورٌ 09:20 — «مستأذن» لا غائب، ولا يُعدّ من دقائقه المأذونة شيءٌ تأخّراً (م-6)."""
        staff = _staff(school, 1)
        _permit(school, staff, FEB, time(7, 30), time(9, 30))
        with pytest.raises(PolicyError, match="مستأذن"):
            _mark(school, staff, principal_user, FEB, "absent", time(9, 20))
        record = _mark(school, staff, principal_user, FEB, "permitted", time(9, 20))
        assert (record.status, record.late_minutes, record.permit_minutes) == (
            "permitted",
            30,
            120,
        )

    def test_approving_a_during_day_permit_does_not_count_its_minutes_twice(
        self, school, principal_user
    ):
        """م-6: «ألّا تُخصم الدقائق المأذونة مرّتين» — إذنٌ 07:15–08:00 وحضورٌ 07:50 رُصد قبل
        اعتماده متأخّراً 50 دقيقة، فإذا اعتُمد صار مستأذناً بربع ساعةٍ غير مأذونة (م-32:
        «وعند اعتماده تُعاد مطابقة أيّامه»)."""
        staff = _staff(school, 1)
        permit = _permit(school, staff, FEB, time(7, 15), time(8, 0), approve=None)
        record = _mark(school, staff, principal_user, FEB, "late", time(7, 50))
        assert (record.status, record.late_minutes) == ("late", 50)

        _through(permit)

        record.refresh_from_db()
        assert (record.status, record.late_minutes, record.permit_minutes) == (
            "permitted",
            15,
            45,
        )

    # ── م-24 وم-25: من ينوب لا يرصد المدير، والمديرُ يرفع غياباً رُصد عليه ─────────


# ══════════════════════════════════════════════════════════════════════
#  مربّع منسّق المادّة — قرارُ المدرسة (2026-09-19)
# ══════════════════════════════════════════════════════════════════════


def _teacher_in_department(school, n, coordinator):
    """معلّمٌ في قسمٍ رئيسُه ``coordinator`` — بالرقم الوظيفيّ الاصطناعيّ."""
    from core.models.department import Department

    dept, _ = Department.objects.get_or_create(
        school=school, code="math", defaults={"name": "رياضيات", "head": coordinator}
    )
    user = UserFactory(full_name=f"معلّم اصطناعي {n}", employee_number=f"T-{n:04d}")
    MembershipFactory(
        user=user,
        school=school,
        role=RoleFactory(school=school, name="teacher"),
        department_obj=dept,
    )
    return user


class TestCoordinatorBox:
    """المنسّقُ يوقّع استئذانَ المعلّم قبل النائب الأكاديميّ — قرارٌ مدرسيّ أكاديميّ."""

    def test_a_teachers_permit_passes_the_coordinator_before_the_academic_deputy(self, school):
        coordinator = _staff(school, 50, "coordinator")
        teacher = _teacher_in_department(school, 51, coordinator)
        permit = _permit(school, teacher, FEB, time(10, 0), time(11, 0), approve=None)

        with _at(datetime.combine(FEB, MORNING)):
            PermitService.act(permit, actor=_actor(school, "secretary"), approve=True)
            permit.refresh_from_db()
            assert (permit.stage, permit.coordinator) == ("coordinator", coordinator)
            assert _eligible(permit) == {coordinator.pk}

            deputy = _actor(school, "vice_academic")
            with pytest.raises(PolicyError, match="بانتظار"):
                PermitService.act(permit, actor=deputy, approve=True)
            PermitService.act(permit, actor=coordinator, approve=True)
            permit.refresh_from_db()
            assert (permit.stage, permit.coordinator_by) == ("supervisor", coordinator)
            assert permit.coordinator_at is not None
            PermitService.act(permit, actor=deputy, approve=True)
            PermitService.act(permit, actor=_actor(school, "principal"), approve=True)
        permit.refresh_from_db()
        assert permit.status == "approved"

    def test_the_coordinator_can_refuse_and_the_refusal_names_his_box(self, school):
        coordinator = _staff(school, 50, "coordinator")
        teacher = _teacher_in_department(school, 51, coordinator)
        permit = _permit(school, teacher, FEB, time(10, 0), time(11, 0), approve=None)
        with _at(datetime.combine(FEB, MORNING)):
            PermitService.act(permit, actor=_actor(school, "secretary"), approve=True)
            PermitService.act(permit, actor=coordinator, approve=False, reason="حصصٌ لا بديلَ لها")
        permit.refresh_from_db()
        assert (permit.status, permit.rejected_stage) == ("rejected", "coordinator")

    def test_no_coordinator_box_without_a_department_head_or_for_the_coordinator_himself(
        self, school
    ):
        loose = _staff(school, 52)  # معلّمٌ بلا قسم
        permit = _permit(school, loose, FEB, time(10, 0), time(11, 0), approve=None)
        with _at(datetime.combine(FEB, MORNING)):
            PermitService.act(permit, actor=_actor(school, "secretary"), approve=True)
        permit.refresh_from_db()
        assert permit.stage == "supervisor"

        coordinator = _staff(school, 53, "coordinator")
        own = _permit(school, coordinator, date(2026, 2, 2), time(10, 0), time(11, 0), approve=None)
        with _at(datetime.combine(date(2026, 2, 2), MORNING)):
            PermitService.act(own, actor=_actor(school, "secretary"), approve=True)
        own.refresh_from_db()
        assert own.stage == "supervisor"  # مسؤولُه المباشر النائبُ الأكاديميّ لا منسّقٌ فوقه

    def test_the_academic_deputy_signs_the_box_of_an_absent_coordinator(self, school):
        coordinator = _staff(school, 50, "coordinator")
        teacher = _teacher_in_department(school, 51, coordinator)
        permit = _permit(school, teacher, FEB, time(10, 0), time(11, 0), approve=None)
        secretary = _actor(school, "secretary")
        with _at(datetime.combine(FEB, MORNING)):
            PermitService.act(permit, actor=secretary, approve=True)
            StaffAttendanceService.mark(
                school=school,
                staff=coordinator,
                day=FEB,
                status="absent",
                actor=secretary,
                absence_type="sick",
            )
            deputy = _actor(school, "vice_academic")
            assert _eligible(permit) == {deputy.pk}
            PermitService.act(permit, actor=deputy, approve=True)
        permit.refresh_from_db()
        assert permit.stage == "supervisor"


# ══════════════════════════════════════════════════════════════════════
#  المسؤولُ المباشر يقبل العذر — قرارُ المالك 2026-09-19
# ══════════════════════════════════════════════════════════════════════


class TestLineManagerExcuse:
    """المديرُ، أو النائبُ الإداريّ للكادر الإداريّ، أو النائبُ الأكاديميّ للكادر الأكاديميّ."""

    BASE = {
        "day": FEB,
        "status": "late",
        "check_in": time(9, 30),
        "accepted_excuse": "تعطّل السيارة",
    }

    def test_each_deputy_accepts_excuses_for_his_own_people_only(self, school, principal_user):
        vice_admin, vice_academic = _actor(school, "vice_admin"), _actor(school, "vice_academic")
        teacher, worker = _staff(school, 1), _staff(school, 2, "services_worker")

        record = StaffAttendanceService.mark(
            school=school, staff=teacher, actor=vice_academic, **self.BASE
        )
        assert (record.excuse_accepted_by, record.excuse_on_behalf) == (vice_academic, False)
        record = StaffAttendanceService.mark(
            school=school, staff=worker, actor=vice_admin, **self.BASE
        )
        assert (record.excuse_accepted_by, record.excuse_on_behalf) == (vice_admin, False)

        with pytest.raises(PolicyError, match="رصدُ الحضور"):
            StaffAttendanceService.mark(
                school=school, staff=worker, actor=vice_academic, **self.BASE
            )
        with pytest.raises(PolicyError, match="رصدُ الحضور"):
            StaffAttendanceService.mark(school=school, staff=teacher, actor=vice_admin, **self.BASE)

    def test_the_secretary_still_writes_the_time_only(self, school, principal_user):
        teacher, secretary = _staff(school, 1), _actor(school, "secretary")
        with pytest.raises(PolicyError, match="مسؤولُه المباشر"):
            StaffAttendanceService.mark(school=school, staff=teacher, actor=secretary, **self.BASE)

    def test_a_deputys_board_lists_only_the_people_under_him(self, school, principal_user):
        vice_admin, vice_academic = _actor(school, "vice_admin"), _actor(school, "vice_academic")
        teacher, worker = _staff(school, 1), _staff(school, 2, "services_worker")
        day = DEFAULT_NOW.date()

        def names(viewer):
            rows = StaffAttendanceService.daily_board(school, day, viewer=viewer)["rows"]
            return {row["staff"].pk for row in rows}

        assert teacher.pk in names(vice_academic) and worker.pk not in names(vice_academic)
        assert worker.pk in names(vice_admin) and teacher.pk not in names(vice_admin)
        assert {teacher.pk, worker.pk} <= names(_actor(school, "secretary"))

    def test_a_deputy_opens_the_board_and_a_stranger_does_not(
        self, client_as, school, principal_user
    ):
        vice_academic = _actor(school, "vice_academic")
        teacher = _staff(school, 1)
        page = client_as(vice_academic).get(
            reverse("staff_affairs:attendance_board"), {"date": "2026-02-15"}
        )
        assert page.status_code == 200 and f"sa-att-{teacher.pk}" in page.content.decode()
        worker = _staff(school, 2, "services_worker")
        response = client_as(vice_academic).post(
            reverse("staff_affairs:attendance_mark"),
            {"staff_id": worker.pk, "date": "2026-02-15", "status": "present", "check_in": "06:55"},
        )
        assert response.status_code == 403

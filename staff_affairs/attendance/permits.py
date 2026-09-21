"""الأذونات — نموذج 02: المراحلُ والرصيدُ والاعتماد.

من تفكيك ``staff_affairs/attendance.py`` (الحزمةُ تُصدّر الأسماءَ نفسَها في ``__init__``).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.http import HttpRequest
from django.utils import timezone

import staff_affairs.attendance as _pkg
from core.models.access import Membership
from core.models.school import School
from core.models.user import CustomUser
from staff_affairs.models import (
    PERMIT_TYPES,
    PermitRequest,
)

from .context import (
    LINE_MANAGER,
    NON_STAFF_ROLES,
    PRINCIPAL,
    PRINCIPAL_DELEGATE,
    PolicyError,
    _active_role_holders,
    _audit,
    _minute,
    _role_of,
    _StageDay,
    minutes_between,
)
from .rules import (
    LEAVING_PERMIT_TYPES,
    MONTHLY_PERMIT_CAP,
    PERMIT_MAX_MINUTES,
    _check_timing,
    _check_window,
    month_bounds,
)

# ══════════════════════════════════════════════════════════════════════
#  الأذونات — نموذج 02
# ══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class PermitBalance:
    cap: int
    approved: int
    pending: int

    @property
    def remaining(self) -> int:
        return max(0, self.cap - self.approved)


#: أدوارُ المعلّمين الذين يوقّع منسّقُ قسمهم إذنَهم قبل النائب الأكاديميّ (قرار المدرسة).
COORDINATED_ROLES = frozenset({"teacher", "ese_teacher"})


def department_coordinator(school: School, staff: CustomUser) -> CustomUser | None:
    """منسّقُ قسم المعلّم — رئيسُ القسم (``Department.head``)، إن وُجد وكان غيرَه.

    ومن لا قسمَ له أو لقسمه رئيسٌ فارغ لا مربّعَ منسّقٍ له، فلا يعلق طلبُه.
    """
    if _role_of(staff) not in COORDINATED_ROLES:
        return None
    membership = (
        Membership.objects.current()
        .filter(user=staff, school=school, is_active=True, department_obj__isnull=False)
        .select_related("department_obj__head")
        .first()
    )
    head = membership.department_obj.head if membership else None
    return head if head is not None and head.pk != staff.pk else None


def can_submit_permits(user: CustomUser) -> bool:
    """أيُقدَّم إذنُ هذا المستخدم في المنصّة؟ — كلُّ الكادر، والمديرُ منهم (م-23).

    سجلُّ الاستئذانات المدرسيّ (``07-نماذج المدرسة/07) سجل الاستئذانات.xlsx``، ورقة
    «تأخير - يناير») أوّلُ صفوفه مديرُ المدرسة (B3:C3) — فالمدرسةُ تتتبّع أذوناتِه.
    """
    return _role_of(user) not in NON_STAFF_ROLES


def deputy_role_for(role: str) -> str:
    """م-21 وم-22: دورُ «المسؤول المباشر والنائب المسؤول» — والمديرُ لا مسؤولَ فوقه (فارغ).

    وما لا بطاقةَ لمسمّاه — وسجلُّ الاستئذانات المدرسيّ يتتبّع أذوناتِ المرشد الأكاديميّ
    والمحاسب وغيرهم — فمسؤولُه مديرُ المدرسة، ولا يُرفض طلبُه.
    """
    if role == PRINCIPAL:
        return ""
    return LINE_MANAGER.get(role, PRINCIPAL)


class PermitService:
    @staticmethod
    def _month_minutes(
        school: School,
        staff: CustomUser,
        day: date,
        statuses: Iterable[str],
        exclude_pk: Any = None,
    ) -> int:
        first, last = month_bounds(day)
        qs = PermitRequest.objects.filter(
            school=school, staff=staff, date__range=(first, last), status__in=statuses
        )
        if exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        total: int | None = qs.aggregate(total=Sum("duration_minutes"))["total"]
        return total or 0

    @staticmethod
    def balance(school: School, staff: CustomUser, day: date) -> PermitBalance:
        """م-15: رصيدُ شهر ``day`` — المعتمدُ يخصم، والمعلَّقُ يُعرض ولا يخصم (م-17)."""
        first, last = month_bounds(day)
        sums = PermitRequest.objects.filter(
            school=school, staff=staff, date__range=(first, last)
        ).aggregate(
            approved=Sum("duration_minutes", filter=Q(status="approved")),
            pending=Sum("duration_minutes", filter=Q(status="pending")),
        )
        return PermitBalance(MONTHLY_PERMIT_CAP, sums["approved"] or 0, sums["pending"] or 0)

    # ── م-18ب: ما لم يُعتمد قبل وقت بدئه ينتهي ───────────────────────────

    @staticmethod
    def _lock(permit: PermitRequest) -> None:
        """يقفل صفَّ الطلب نفسَه ويقرؤه من جديد — وراء قفل صفّ الموظّف.

        قفلُ الموظّف يرتّب القرارات فيما بينها، لكنّ الكنسَ (``expire_due``) يمرّ على طلبات
        المدرسة كلِّها بلا قفل موظّف؛ فبقفل الصفّ ينتظر أحدُهما الآخر، ويجد الثاني الحالةَ
        التي التزمها الأوّل (م-18ب).
        """
        PermitRequest.objects.select_for_update().filter(pk=permit.pk).first()
        permit.refresh_from_db()

    @staticmethod
    def _overdue(permit: PermitRequest, now: datetime) -> bool:
        return permit.permit_type in LEAVING_PERMIT_TYPES and (permit.date, permit.start_time) <= (
            now.date(),
            now.time(),
        )

    @staticmethod
    def _expire(permit: PermitRequest, request: HttpRequest | None = None) -> bool:
        """م-18ب: طلبُ خروجٍ أو استئذانٍ مضى وقتُ بدئه ولم يُعتمد — «منتهٍ» بلا أثرٍ في الرصيد.

        الكتابةُ مشروطةٌ بأنّه ما زال معلَّقاً في القاعدة لا في النسخة المقروءة: فالكنسُ
        (``expire_due``) يقرأ بلا قفل، وقد يلتزم بين قراءته وكتابته اعتمادٌ قُرّر قبل بدء
        النافذة — فلا يُكتب «منتهٍ» فوقه (م-17 وم-14). ويُرجع هل أُغلق الطلبُ فعلاً.
        """
        stage = permit.stage
        closed = PermitRequest.objects.filter(pk=permit.pk, status="pending").update(
            status="expired", stage="closed", updated_at=timezone.now()
        )
        if not closed:
            permit.refresh_from_db()
            return False
        permit.status, permit.stage = "expired", "closed"
        _audit(
            None,
            "update",
            permit,
            {"stage": stage, "status": "expired", "cause": "not_approved_before_start"},
            request,
        )
        return True

    @staticmethod
    def expire_due(
        school: School,
        now: datetime | None = None,
        staff: CustomUser | None = None,
        request: HttpRequest | None = None,
    ) -> int:
        """كنسُ ما انتهى وقتُه من الطلبات المعلّقة — يُستدعى قبل كلّ قراءةٍ أو قرار.

        لا مهمّةَ مجدولةٌ تحمله: الحالةُ تُحسب عند أوّل مَسٍّ للطلب، فلا يبقى في طابورٍ
        ولا يُعتمد بعد وقته (م-18ب)، ولا يحجز يومَه (م-14) ولا دقائقَه (م-15).
        """
        now = now or _pkg._now()
        qs = PermitRequest.objects.filter(
            school=school, status="pending", permit_type__in=LEAVING_PERMIT_TYPES
        ).filter(Q(date__lt=now.date()) | Q(date=now.date(), start_time__lte=now.time()))
        if staff is not None:
            qs = qs.filter(staff=staff)
        expired = 0
        for permit in qs.select_related("school"):
            expired += PermitService._expire(permit, request)
        return expired

    @staticmethod
    def _check_rules(
        school: School,
        staff: CustomUser,
        day: date,
        duration: int,
        *,
        open_statuses: tuple[str, ...],
        exclude_pk: Any = None,
    ) -> bool:
        """يفحص «مرّةً في اليوم» (البند 4.3) ويُرجع أيتجاوز الطلبُ حدَّ المرّة أو الشهر.

        التجاوزُ لا يُرفض: المادّة 79/3 تجيزه «بموافقة كتابية من الرئيس» — فيُعلَّم الطلبُ
        (``over_limit``) ولا يُعتمد إلّا بمرجع تلك الموافقة (``PermitService.act``).
        """
        same_day = PermitRequest.objects.filter(
            school=school, staff=staff, date=day, status__in=open_statuses
        )
        if exclude_pk is not None:
            same_day = same_day.exclude(pk=exclude_pk)
        if same_day.exists():
            raise PolicyError("لا يجوز الإذنُ أكثرَ من مرّةٍ في اليوم الواحد (البند 4.3).")
        used = PermitService._month_minutes(school, staff, day, open_statuses, exclude_pk)
        return duration > PERMIT_MAX_MINUTES or used + duration > MONTHLY_PERMIT_CAP

    @staticmethod
    @transaction.atomic
    def submit(
        *,
        school: School,
        staff: CustomUser,
        permit_type: str,
        day: date,
        start_time: time,
        end_time: time,
        reason: str,
        request: HttpRequest | None = None,
    ) -> PermitRequest:
        """يقدّم الموظّفُ طلبَه لنفسه — وأوّلُ مربّعاته «استخدام السكرتارية» (م-19).

        ويُرفض ما لو اعتُمد لخالف السياسة — فالطابورُ لا يحمل طلباً مصيرُه الرفض:
        المعلَّقُ يُحسب مع المعتمد في فحص اليوم (م-14) والشهر (م-15).
        """
        if permit_type not in {key for key, _label in PERMIT_TYPES}:
            raise PolicyError("نوعُ طلبٍ غيرُ معروف.")
        if end_time <= start_time:
            raise PolicyError("«إلى الساعة» يجب أن تكون بعد «من الساعة».")
        if not reason.strip():
            raise PolicyError("سببُ الطلب مطلوب (نموذج 02).")
        role = _role_of(staff)
        if role in NON_STAFF_ROLES:
            raise PolicyError("نموذج 02 للموظّفين.")
        now = _pkg._now()
        _check_window(permit_type, start_time, end_time)
        _check_timing(permit_type, day, start_time, now)
        CustomUser.objects.select_for_update().filter(pk=staff.pk).first()
        PermitService.expire_due(school, now, staff, request)
        duration = minutes_between(start_time, end_time)
        over_limit = PermitService._check_rules(
            school, staff, day, duration, open_statuses=("pending", "approved")
        )
        permit = PermitRequest.objects.create(
            over_limit=over_limit,
            school=school,
            staff=staff,
            permit_type=permit_type,
            date=day,
            start_time=start_time,
            end_time=end_time,
            duration_minutes=duration,
            reason=reason.strip()[:500],
            stage="secretary",
            deputy_role=deputy_role_for(role),
            created_by=staff,
            updated_by=staff,
        )
        _audit(
            staff,
            "create",
            permit,
            {"type": permit_type, "minutes": duration, "over_limit": over_limit},
            request,
        )
        return permit

    # ── من يعمل في مرحلة الطلب ─────────────────────────────────────────

    @staticmethod
    def _principal_side(day: _StageDay, applicant: Any) -> set[Any]:
        """من يعمل بصفة المدير الآن: المديرُ، ومن كلّفه بأعباء وظيفته (م-43).

        قرارُ المدرسة (2026-09-19): لا إنابةَ تلقائيّةً بغياب المدير أو بالأقدميّة — التكليفُ
        قرارٌ صريحٌ منه، فالمرصودُ غائباً منهم لا يعمل وإن بقي بلا مكلَّفٍ عنه بقي المربّعُ
        معلّقاً حتى يكلّف. واستثناءٌ واحد: شغورُ المنصب (لا مديرَ في المدرسة أصلاً، م-26)
        فيعمل نائبُ الشؤون الإدارية ومن كُلّف عنه.
        """
        real = _active_role_holders(day.school, PRINCIPAL)
        tasked = set(day.assigned(PRINCIPAL)) - day.absent()
        if real or tasked:
            # المديرُ نفسُه دائماً (وإن رُصد غائباً خطأً فلا يُحجب عن مربّعه)، ومعه المكلَّفون.
            side = real | tasked
        else:
            side = day.holders(PRINCIPAL_DELEGATE) - day.absent()
        return side - {applicant}

    @staticmethod
    def _available(day: _StageDay, role: str, applicant: Any) -> set[Any]:
        """حاملو الدور نشطين، غيرُ صاحب الطلب ولا المرصودين غائبين اليوم."""
        return day.holders(role) - day.absent() - {applicant}

    @staticmethod
    def _eligible(permit: PermitRequest, day: _StageDay) -> tuple[set[Any], str]:
        """(من يعمل الآن، الدورُ الذي تُنسب إليه المرحلة).

        م-28: لا يعلق طلبٌ بلا من يوقّعه — مربّعٌ شغر صاحبُه أو غاب اليومَ يُؤدّى من جهة
        المدير (المدير أو نائبُه وفق م-24)، ويُوسم «بالنيابة» في التدقيق (``on_behalf_of``).
        وهذا اجتهادٌ لا نصّ: المصدرُ صامتٌ في التصعيد، والأصلُ في الشغور الندبُ بقرار
        المدير (المادّة 43 من النظام الوظيفيّ)، وهذه القاعدةُ تُكمله ولا تحلّ محلّه.

        ومن مسؤولُه المباشرُ المديرُ (م-21 وم-22) لا يمرّ بمربّع «supervisor» أصلاً:
        خطوتُه مدمجةٌ في مربّع المدير (م-19، الخطوة 3؛ ``_record_balance``).
        """
        applicant = permit.staff_id
        if permit.stage == "secretary":
            secretaries = PermitService._available(day, "secretary", applicant)
            if secretaries:
                return secretaries, "secretary"
            if permit.is_principals_own:
                # طلبُ المدير نفسِه: لا يُثبت رصيدَه بيده (م-23).
                return day.holders(PRINCIPAL_DELEGATE) - day.absent() - {applicant}, "secretary"
            return PermitService._principal_side(day, applicant), "secretary"
        if permit.stage == "coordinator":
            coordinators = {permit.coordinator_id} - day.absent() - {applicant}
            if coordinators:
                return coordinators, "coordinator"
            # المنسّقُ غائبٌ اليوم: يوقّع مربّعَه النائبُ الأكاديميّ بالنيابة (م-28).
            return PermitService._available(day, "vice_academic", applicant) or (
                PermitService._principal_side(day, applicant)
            ), "coordinator"
        if permit.stage == "supervisor":
            role = permit.deputy_role
            if role == PRINCIPAL or not role:
                return PermitService._principal_side(day, applicant), PRINCIPAL
            deputies = PermitService._available(day, role, applicant)
            if deputies:
                return deputies, role
            return PermitService._principal_side(day, applicant), role
        if permit.stage == "external":
            secretaries = PermitService._available(day, "secretary", applicant)
            if secretaries:
                return secretaries, "secretary"
            return day.holders(PRINCIPAL_DELEGATE) - day.absent() - {applicant}, "secretary"
        if permit.stage == "principal":
            return PermitService._principal_side(day, applicant), PRINCIPAL
        return set(), ""

    @staticmethod
    def eligible_actors(permit: PermitRequest) -> list[CustomUser]:
        """من يعمل في مرحلة الطلب الآن — أشخاصاً."""
        ids, _role = PermitService._eligible(permit, _StageDay(permit.school, _pkg._now()))
        return list(CustomUser.objects.filter(pk__in=ids).order_by("full_name"))

    @staticmethod
    def _natural(actor: CustomUser, stage_role: str) -> bool:
        """أيعمل بصفته هو؟ — وإلّا فبالنيابة أو بالرفع، ويُكتب ذلك في التدقيق (م-25 وم-28)."""
        return _role_of(actor) == stage_role

    @staticmethod
    @transaction.atomic
    def act(
        permit: PermitRequest,
        *,
        actor: CustomUser,
        approve: bool,
        reason: str = "",
        written_approval: str = "",
        request: HttpRequest | None = None,
    ) -> PermitRequest:
        """مربّعٌ واحدٌ من نموذج 02 — تحت قفل صفّ الموظّف فلا تتسابق مرحلتان.

        الترتيبُ ترتيبُ الورقة (م-19):

        * الخطوة 2 «استخدام السكرتارية»: تُثبت رصيدَ الساعات المتبقّي قبل هذا الطلب
          واسمَها ووقتَها. لا قرارَ لها ولا خصم — فلا تَرفض.
        * الخطوة 3 «استخدام المسؤول المباشر والنائب المسؤول»: عمودان يوقّعهما النائبُ
          المختصّ بتوقيعٍ واحدٍ لأنّه صاحبُهما معاً (م-21). و«غير موافق» تُنهي الطلبَ
          مرفوضاً، والسببُ اختياريّ. ومن مسؤولُه المديرُ تُدمج خطوتُه في الخطوة 4.
        * الخطوة 4 «استخدام الإدارة» و«مدير المدرسة» مرحلةٌ واحدة (س-2): الاعتمادُ
          النهائيّ، وبه وحدَه يدخل الإذنُ في الرصيد (م-17)، ويصدر إخطارُ الموظّف (الخطوة
          5). و«سبب الرفض» إلزاميٌّ هنا وحدَه — فهو في مربّع الإدارة من الورقة.
        * إذنُ المدير نفسِه: اعتمادٌ من خارج المدرسة تُثبته السكرتاريةُ بمرجعه (م-23).
        """
        from .daily import StaffAttendanceService

        CustomUser.objects.select_for_update().filter(pk=permit.staff_id).first()
        PermitService._lock(permit)
        if permit.status != "pending":
            raise PolicyError(f"الطلبُ «{permit.get_status_display()}» — لا يُراجَع ثانيةً.")
        now = _pkg._now()
        if PermitService._overdue(permit, now):
            PermitService._expire(permit, request)
            return permit
        if actor.pk == permit.staff_id:
            raise PolicyError("لا يعمل أحدٌ في طلبه هو (البند 4.1: الاعتمادُ من غيره).")
        stage_day = _StageDay(permit.school, now)
        eligible, stage_role = PermitService._eligible(permit, stage_day)
        if actor.pk not in eligible:
            raise PolicyError(f"الطلبُ بانتظار «{permit.get_stage_display()}» لا دورك.")
        on_behalf = "" if PermitService._natural(actor, stage_role) else stage_role
        stage = permit.stage
        if stage == "secretary":
            if not approve:
                raise PolicyError(
                    "السكرتاريةُ تُثبت رصيدَ الساعات ولا تقرّر في الطلب (مربّع «استخدام "
                    "السكرتارية» في نموذج 02) — والرفضُ في مربّع الإدارة."
                )
            PermitService._record_balance(permit, actor, now)
        elif stage == "external" and not reason.strip():
            raise PolicyError(
                "القرارُ الوارد من خارج المدرسة يُثبَت بمرجعه (بريدٌ أو كتابٌ وتاريخُه) — "
                "فالسكرتاريةُ تُوثّق ولا تقرّر (م-23)."
            )
        elif not approve:
            if stage == "principal" and not reason.strip():
                raise PolicyError(
                    "سببُ الرفض مطلوبٌ في مربّع الإدارة (نموذج 02: «موافق، غير موافق، "
                    "سبب الرفض») — م-19، الخطوة 4."
                )
            PermitService._sign(permit, stage, actor, now)
            permit.status, permit.rejected_stage, permit.stage = "rejected", stage, "closed"
            permit.rejection_reason = reason.strip()[:300]
            if stage == "external":
                permit.external_reference = permit.rejection_reason
            permit.decided_on_behalf = bool(on_behalf) and stage == "principal"
        elif stage == "coordinator":
            PermitService._sign(permit, stage, actor, now)
            permit.stage = "supervisor"
        elif stage == "supervisor":
            PermitService._sign(permit, stage, actor, now)
            permit.stage = "principal"
        elif stage in ("principal", "external"):
            permit.over_limit = PermitService._check_rules(
                permit.school,
                permit.staff,
                permit.date,
                permit.duration_minutes,
                open_statuses=("approved",),
                exclude_pk=permit.pk,
            )
            if permit.over_limit and stage == "principal":
                # المادّة 79/3: ما جاوز ثلاثَ ساعاتٍ للمرّة أو عشراً في الشهر لا يُعتمد بلا
                # «موافقة كتابية من الرئيس» — فيُثبَت مرجعُها (كتابٌ أو بريدٌ وتاريخُه).
                if not written_approval.strip():
                    raise PolicyError(
                        "الإذنُ يجاوز حدَّ 3 ساعات للمرّة أو 10 ساعات في الشهر — لا يُعتمد إلّا "
                        "بموافقةٍ كتابيّة؛ اكتب مرجعَها (رقمُ الكتاب أو البريد وتاريخُه)."
                    )
                permit.written_approval_ref = written_approval.strip()[:300]
            PermitService._sign(permit, stage, actor, now)
            permit.status, permit.stage = "approved", "closed"
            permit.decided_on_behalf = bool(on_behalf) and stage == "principal"
            permit.notified_at = now
            if stage == "external":
                permit.external_reference = reason.strip()[:300]
        permit.updated_by = actor
        try:
            with transaction.atomic():
                permit.save()
        except IntegrityError as exc:
            raise PolicyError("لا يجوز الإذنُ أكثرَ من مرّةٍ في اليوم الواحد (البند 4.3).") from exc
        changes: dict[str, Any] = {"stage": stage, "status": permit.status}
        if on_behalf:
            changes["on_behalf_of"] = on_behalf
            changes.update(stage_day.assignment_basis(actor))
        # من يوقّع مربّعَ مسؤوله ثمّ يعتمد بالتكليف عن المدير: المواصفةُ لا تمنعه، فيُقبل
        # ويُكتب في التدقيق أنّ التوقيعين من يدٍ واحدة.
        if (
            permit.status == "approved"
            and permit.deputy_role != PRINCIPAL
            and permit.reviewed_by_id == permit.deputy_by_id
        ):
            changes["same_signer"] = True
        _audit(actor, "update", permit, changes, request)
        if permit.status == "approved":
            PermitService._notify(permit)
            StaffAttendanceService.reconcile(
                permit.school, permit.staff, permit.date, actor=actor, request=request
            )
        return permit

    @staticmethod
    def _sign(permit: PermitRequest, stage: str, actor: CustomUser, now: datetime) -> None:
        """م-19: الاسمُ ووقتُ القرار في المربّع الذي قرّر فيه — موافقاً أو غيرَ موافق.

        عمودا «المسؤول المباشر والنائب المسؤول» بتوقيعٍ واحد (الخطوة 3). ومن مسؤولُه
        المديرُ يملأ توقيعُ المدير المربّعين كذلك، فالخطوةُ مدمجةٌ ولا تتكرّر.
        """
        if stage == "coordinator":
            permit.coordinator_by, permit.coordinator_at = actor, now
        if stage == "supervisor" or (stage == "principal" and permit.deputy_role == PRINCIPAL):
            permit.supervisor_by, permit.supervisor_at = actor, now
            permit.deputy_by, permit.deputy_at = actor, now
        if stage in ("principal", "external"):
            permit.reviewed_by, permit.reviewed_at = actor, now

    @staticmethod
    def _notify(permit: PermitRequest) -> None:
        """م-19: إخطارُ الموظّف باسم السكرتارية عند الاعتماد النهائيّ — بلا مرحلةٍ تُعلِّق.

        حاشيةُ ن02: «يتعين على الموظف عدم الخروج إلا بعد اعتماده وإخطاره من قبل
        السكرتارية بالموافقة» — فالإخطارُ لازمٌ للخروج، ووقتُه في ``notified_at``.
        """
        from notifications.models import InAppNotification

        InAppNotification.objects.create(
            user=permit.staff,
            school=permit.school,
            title="السكرتارية: اعتُمد طلبُ الإذن",
            body=(
                f"{permit.get_permit_type_display()} يوم {permit.date:%Y-%m-%d} "
                f"من {permit.start_time:%H:%M} إلى {permit.end_time:%H:%M} — "
                "اعتمده مدير المدرسة، ولا خروجَ قبل هذا الإخطار (حاشية نموذج 02)."
            ),
            event_type="general",
            related_object_id=str(permit.pk),
            related_url="/staff-affairs/permits/mine/",
        )
        if permit.staff.email:
            # البريدُ خلفيّاً بعد الإيداع (الطلبُ لا ينتظر مزوّداً)، بلا سببِ الإذن (بيانةٌ محتملة).
            from notifications.tasks import send_email_task

            transaction.on_commit(
                lambda: send_email_task.delay(
                    school_id=str(permit.school_id),
                    recipient_email=permit.staff.email,
                    subject="السكرتارية: اعتُمد طلبُ الإذن",
                    body_text=(
                        f"{permit.get_permit_type_display()} يوم {permit.date:%Y-%m-%d} "
                        f"من {permit.start_time:%H:%M} إلى {permit.end_time:%H:%M} — اعتمده "
                        "مدير المدرسة، ولا خروجَ قبل هذا الإخطار."
                    ),
                    notif_type="custom",
                )
            )

    @staticmethod
    @transaction.atomic
    def cancel(
        permit: PermitRequest, *, actor: CustomUser, request: HttpRequest | None = None
    ) -> PermitRequest:
        """م-20: يلغي صاحبُ الطلب طلبَه المعلَّق، أو إذنَه المعتمدَ قبل بدء نافذته.

        فيُفرج عن يومه (م-14) ويُستردّ رصيدُه (م-10)، ويبقى الصفُّ بحالة «ملغى» وقيدُه في
        التدقيق — لا يُحذف طلبٌ ولا قرار.
        """
        from .daily import StaffAttendanceService

        CustomUser.objects.select_for_update().filter(pk=permit.staff_id).first()
        PermitService._lock(permit)
        if actor.pk != permit.staff_id:
            raise PolicyError("لا يلغي الطلبَ إلّا صاحبُه.")
        now = _pkg._now()
        was = permit.status
        if was == "approved":
            if (permit.date, permit.start_time) <= (now.date(), _minute(now.time())):
                raise PolicyError(
                    "الإذنُ المعتمد يُلغى قبل بدء نافذته وحدَه — وما بدأ يبقى محسوباً (م-20)."
                )
        elif was != "pending":
            raise PolicyError(f"الطلبُ «{permit.get_status_display()}» — لا يُلغى.")
        elif PermitService._overdue(permit, now):
            PermitService._expire(permit, request)
            return permit
        stage = permit.stage
        permit.status, permit.stage, permit.updated_by = "cancelled", "closed", actor
        permit.save(update_fields=["status", "stage", "updated_by", "updated_at"])
        _audit(
            actor,
            "update",
            permit,
            {"stage": stage, "status": "cancelled", "was": was},
            request,
        )
        if was == "approved":
            StaffAttendanceService.reconcile(
                permit.school,
                permit.staff,
                permit.date,
                actor=actor,
                request=request,
                cause="permit_cancelled",
            )
        return permit

    @staticmethod
    def _record_balance(permit: PermitRequest, actor: CustomUser, now: datetime) -> None:
        """مربّعُ السكرتارية (م-19): الرصيدُ المتبقّي قبل هذا الطلب، والاسمُ والتوقيت.

        لقطةٌ لما رأته يومَ سجّلت، لا عدّادٌ ولا خصم — والخصمُ لا يكون إلّا بالاعتماد
        النهائيّ (م-17)، وفحصُ السقف (م-15) هناك.
        """
        used = PermitService._month_minutes(
            permit.school, permit.staff, permit.date, ("approved",), permit.pk
        )
        permit.recorded_balance_minutes = max(0, MONTHLY_PERMIT_CAP - used)
        permit.secretary_by, permit.secretary_at = actor, now
        if permit.is_principals_own:
            permit.stage = "external"  # م-23
        elif permit.deputy_role == PRINCIPAL:
            permit.stage = "principal"  # م-19 (3): خطوةُ المسؤول مدمجةٌ في مربّع المدير
        else:
            coordinator = department_coordinator(permit.school, permit.staff)
            if coordinator is not None:
                permit.coordinator = coordinator
                permit.stage = "coordinator"  # قرار المدرسة: المنسّق قبل النائب الأكاديميّ
            else:
                permit.stage = "supervisor"

    @staticmethod
    def own_permits(school: School, staff: CustomUser) -> list[PermitRequest]:
        """طلباتُ الموظّف — بعد كنس ما انتهى وقتُه (م-18ب)، وكلٌّ معلَّمٌ بما يُلغى (م-20)."""
        now = _pkg._now()
        PermitService.expire_due(school, now, staff=staff)
        permits = list(
            PermitRequest.objects.filter(school=school, staff=staff).order_by(
                "-date", "-created_at"
            )[:50]
        )
        started = (now.date(), _minute(now.time()))
        for permit in permits:
            permit.cancellable = permit.status == "pending" or (  # type: ignore[attr-defined]
                permit.status == "approved" and (permit.date, permit.start_time) > started
            )
        return permits

    @staticmethod
    def awaiting(school: School, user: CustomUser) -> list[PermitRequest]:
        """الطلباتُ المعلّقةُ في مرحلةٍ يعمل فيها هذا المستخدم الآن — لا طلبُه هو.

        يُحكم على كلّ طلبٍ بـ``_eligible`` نفسِها التي تحكم القرار، فلا يعرض الطابورُ ما
        يردّه الاعتماد، ولا يُخفي ما يقبله. وما مضى وقتُ بدئه يُكنس قبلها (م-18ب).
        """
        now = _pkg._now()
        PermitService.expire_due(school, now)
        day = _StageDay(school, now)
        pending = (
            PermitRequest.objects.filter(school=school, status="pending")
            .exclude(staff=user)
            .select_related("staff")
            .order_by("date", "created_at")
        )
        return [p for p in pending if user.pk in PermitService._eligible(p, day)[0]]

    @staticmethod
    def pending_one(school: School, pk: Any) -> PermitRequest:
        return PermitRequest.objects.select_related("staff", "school").get(school=school, pk=pk)

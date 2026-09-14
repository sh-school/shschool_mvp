"""حضورُ الموظّفين والأذوناتُ القصيرة — القواعدُ والخدمة.

المرجع الوحيد: ``AAdocs/ministry_data/2026_2027/06_attendance_performance_review.md``
§1 «سياسة وضوابط الحضور والانصراف» (ت/د: 2027/01 بتاريخ 2026-08-23، مدرسة
الشحانية)، و``07_forms_catalog.md`` جدول 1 بند 02 (نموذج طلب تأخير / استئذان /
خروج مبكر). وأرقامُ البنود أدناه أرقامُ الوثيقة نفسِها.

الفلسفة: **يحسب ولا ينفّذ آليّاً** — تُصنَّف الحالةُ وتُعدّ الدقائق، ولا خصمَ ولا
جزاءَ يُطلقه النظام؛ الخصمُ (البند 5) قرارٌ إداريٌّ على التقرير الشهريّ.

قراءةُ الحدود من النصّ حرفاً:

* البند 2.1 «يعتبر الموظف متأخراً إذا حضر **بعد** الساعة 7:00 صباحاً» ← 7:00
  بالضبط حاضر، و7:01 متأخّر.
* البند 2.4 «يعتبر الموظف غائباً إذا حضر **بعد** الساعة التاسعة صباحاً دون إذن
  أو عذر مقبول» ← 9:00 بالضبط متأخّرٌ لا غائب، و9:01 غائب؛ والإذنُ المعتمد يرفع
  الغياب.
* البند 4.2 (ومثله 3.4) «الحد الأقصى للأذونات بواقع (7) ساعات في الشهر» ← 420
  دقيقةً في الشهر الميلاديّ، والسبعُ كاملةً جائزة.
* البند 4.3 (ومثله 3.5) «لا يجوز الإذن أكثر من مرة واحدة في اليوم الواحد».
* البند 4.4 (ومثله 3.6) «الحد الأقصى للإذن ساعتين في المرة الواحدة» ← 120 دقيقة
  جائزة، و121 مرفوضة.
* البند 4.1 «لا يجوز الاعتداد بالإذن إلا بعد اعتماده من الرئيس المباشر» ← الرصيدُ
  يُخصم بالاعتماد لا بالتقديم.

انحرافٌ مؤقّتٌ ينتظر قرارَ المالك: البند 4.1 ونموذج 02 يجعلان الاعتمادَ للرئيس
المباشر ثمّ النائب ثمّ السكرتارية ثمّ الإدارة. والمنصّةُ لا تعرف «الرئيسَ المباشر»
لكلّ موظّف، فالاعتمادُ هنا لحاملي قدرة ``staff_affairs.manage`` في خطوةٍ واحدة،
ولا يعتمد أحدٌ إذنَه هو — افتراضُ المنصّة، لا قرارٌ مسجَّل.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Count, Q, QuerySet, Sum
from django.http import HttpRequest
from django.utils import timezone

from core.models.access import Membership
from core.models.audit import AuditLog
from core.models.school import School
from core.models.user import CustomUser
from staff_affairs.models import PERMIT_TYPES, PermitRequest, StaffAttendance

#: البندان 1.1 و2.1 — بدايةُ الدوام، وما بعدها تأخّر.
WORK_START = time(7, 0)
#: البند 2.4 — ما بعدها غيابٌ ما لم يكن إذن.
ABSENT_AFTER = time(9, 0)
#: البند 4.2 — سبعُ ساعاتٍ في الشهر.
MONTHLY_PERMIT_CAP = 7 * 60
#: البند 4.4 — ساعتان للمرّة.
PERMIT_MAX_MINUTES = 2 * 60

STATUSES = ("present", "late", "absent", "permitted")
STATUS_LABELS = {"present": "حاضر", "late": "متأخّر", "absent": "غائب", "permitted": "مستأذن"}
NON_STAFF_ROLES = ("student", "parent")


class PolicyError(ValueError):
    """مخالفةٌ لبندٍ من السياسة — ورسالتُها تسمّي البند."""


# ══════════════════════════════════════════════════════════════════════
#  القواعدُ الصافية
# ══════════════════════════════════════════════════════════════════════


def minutes_between(start: time, end: time) -> int:
    """الدقائقُ الكاملة من ``start`` إلى ``end`` في اليوم نفسه — والسالبُ صفر."""
    delta = datetime.combine(date.min, end) - datetime.combine(date.min, start)
    return max(0, int(delta.total_seconds() // 60))


def classify_arrival(check_in: time, covered_until: time | None = None) -> tuple[str, int]:
    """(الحالة، دقائقُ التأخّر) لوقت حضورٍ — البنود 2.1 و2.4 و4.1.

    ``covered_until`` نهايةُ إذنِ «تأخيرٍ صباحيّ» معتمدٍ لليوم إن وُجد: من حضر حتّى
    نهايته مستأذن، ومن جاوزها متأخّرٌ تُحسب دقائقُه من نهاية إذنه — والإذنُ يرفع
    الغيابَ (2.4 «دون إذن»)، فلا يصير غائباً.
    """
    if check_in <= WORK_START:
        return "present", 0
    if covered_until is not None:
        if check_in <= covered_until:
            return "permitted", 0
        return "late", minutes_between(max(WORK_START, covered_until), check_in)
    if check_in <= ABSENT_AFTER:
        return "late", minutes_between(WORK_START, check_in)
    return "absent", 0


def month_bounds(day: date) -> tuple[date, date]:
    last = calendar.monthrange(day.year, day.month)[1]
    return day.replace(day=1), day.replace(day=last)


def _audit(
    actor: CustomUser,
    action: str,
    obj: StaffAttendance | PermitRequest,
    changes: dict[str, Any],
    request: HttpRequest | None = None,
) -> None:
    """أثرٌ في سجلّ التدقيق بلا اسمٍ ولا رقمٍ شخصيّ — النوعُ والمعرّفُ والتغيير."""
    AuditLog.log(  # type: ignore[no-untyped-call]
        user=actor,
        action=action,
        model_name="other",
        object_id=obj.pk,
        object_repr=f"{type(obj).__name__} {obj.date:%Y-%m-%d}",
        changes=changes,
        school=obj.school,
        request=request,
    )


def staff_members(school: School) -> QuerySet[CustomUser]:
    """كادرُ المدرسة النشط — أشخاصٌ لا عضويّات، بلا طلبةٍ ولا أولياء."""
    member_ids = (
        Membership.objects.filter(school=school, is_active=True)
        .exclude(role__name__in=NON_STAFF_ROLES)
        .values("user_id")
    )
    return CustomUser.objects.filter(pk__in=member_ids, is_active=True).order_by("full_name")


# ══════════════════════════════════════════════════════════════════════
#  الأذونات (1.3)
# ══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class PermitBalance:
    cap: int
    approved: int
    pending: int

    @property
    def remaining(self) -> int:
        return max(0, self.cap - self.approved)


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
        """رصيدُ شهر ``day``: المعتمدُ يخصم (4.1)، والمعلَّقُ يُعرض ولا يخصم."""
        first, last = month_bounds(day)
        sums = PermitRequest.objects.filter(
            school=school, staff=staff, date__range=(first, last)
        ).aggregate(
            approved=Sum("duration_minutes", filter=Q(status="approved")),
            pending=Sum("duration_minutes", filter=Q(status="pending")),
        )
        return PermitBalance(MONTHLY_PERMIT_CAP, sums["approved"] or 0, sums["pending"] or 0)

    @staticmethod
    def _check_rules(
        school: School,
        staff: CustomUser,
        day: date,
        duration: int,
        *,
        open_statuses: tuple[str, ...],
        exclude_pk: Any = None,
    ) -> None:
        if duration > PERMIT_MAX_MINUTES:
            raise PolicyError(f"الإذنُ {duration} دقيقة — الحدُّ ساعتان في المرّة الواحدة (البند 4.4).")
        same_day = PermitRequest.objects.filter(
            school=school, staff=staff, date=day, status__in=open_statuses
        )
        if exclude_pk is not None:
            same_day = same_day.exclude(pk=exclude_pk)
        if same_day.exists():
            raise PolicyError("لا يجوز الإذنُ أكثرَ من مرّةٍ في اليوم الواحد (البند 4.3).")
        used = PermitService._month_minutes(school, staff, day, open_statuses, exclude_pk)
        if used + duration > MONTHLY_PERMIT_CAP:
            raise PolicyError(
                "يتجاوز سقفَ الأذونات الشهريّ (7 ساعات، البند 4.2): "
                f"المحسوبُ {used} دقيقة والمتبقّي {max(0, MONTHLY_PERMIT_CAP - used)}."
            )

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
        """يقدّم الموظّفُ طلبَه لنفسه.

        ويُرفض ما لو اعتُمد لخالف السياسة — فالطابورُ لا يحمل طلباً مصيرُه الرفض:
        المعلَّقُ يُحسب مع المعتمد في فحص اليوم (4.3) والشهر (4.2).
        """
        if permit_type not in {key for key, _label in PERMIT_TYPES}:
            raise PolicyError("نوعُ طلبٍ غيرُ معروف.")
        if end_time <= start_time:
            raise PolicyError("«إلى الساعة» يجب أن تكون بعد «من الساعة».")
        if not reason.strip():
            raise PolicyError("سببُ الطلب مطلوب (نموذج 02).")
        CustomUser.objects.select_for_update().filter(pk=staff.pk).first()
        duration = minutes_between(start_time, end_time)
        PermitService._check_rules(
            school, staff, day, duration, open_statuses=("pending", "approved")
        )
        permit = PermitRequest.objects.create(
            school=school,
            staff=staff,
            permit_type=permit_type,
            date=day,
            start_time=start_time,
            end_time=end_time,
            duration_minutes=duration,
            reason=reason.strip()[:500],
            created_by=staff,
            updated_by=staff,
        )
        _audit(staff, "create", permit, {"type": permit_type, "minutes": duration}, request)
        return permit

    @staticmethod
    @transaction.atomic
    def review(
        permit: PermitRequest,
        *,
        reviewer: CustomUser,
        approve: bool,
        reason: str = "",
        request: HttpRequest | None = None,
    ) -> PermitRequest:
        """اعتمادٌ أو رفض.

        الاعتمادُ يُعيد فحصَ البندين 4.3 و4.2 على المعتمَد وحده تحت قفل صفّ الموظّف،
        فاعتمادان متزامنان لا يتجاوزان السقف؛ والقيدُ في القاعدة يحسم ما فات القفل.
        """
        CustomUser.objects.select_for_update().filter(pk=permit.staff_id).first()
        permit.refresh_from_db()
        if permit.status != "pending":
            raise PolicyError(f"الطلبُ «{permit.get_status_display()}» — لا يُراجَع ثانيةً.")
        if reviewer.pk == permit.staff_id:
            raise PolicyError("لا يعتمد أحدٌ إذنَه (البند 4.1: الاعتمادُ من الرئيس المباشر).")
        if approve:
            PermitService._check_rules(
                permit.school,
                permit.staff,
                permit.date,
                permit.duration_minutes,
                open_statuses=("approved",),
                exclude_pk=permit.pk,
            )
        permit.status = "approved" if approve else "rejected"
        permit.reviewed_by = reviewer
        permit.reviewed_at = timezone.now()
        permit.rejection_reason = "" if approve else reason.strip()[:300]
        permit.updated_by = reviewer
        try:
            with transaction.atomic():
                permit.save()
        except IntegrityError as exc:
            raise PolicyError("لا يجوز الإذنُ أكثرَ من مرّةٍ في اليوم الواحد (البند 4.3).") from exc
        _audit(reviewer, "update", permit, {"status": ["pending", permit.status]}, request)
        if approve:
            StaffAttendanceService.sync_permit_minutes(permit.school, permit.staff, permit.date)
        return permit

    @staticmethod
    def own_permits(school: School, staff: CustomUser) -> QuerySet[PermitRequest]:
        return PermitRequest.objects.filter(school=school, staff=staff).order_by(
            "-date", "-created_at"
        )[:50]

    @staticmethod
    def pending(school: School) -> QuerySet[PermitRequest]:
        return (
            PermitRequest.objects.filter(school=school, status="pending")
            .select_related("staff")
            .order_by("date", "created_at")
        )

    @staticmethod
    def pending_one(school: School, pk: Any) -> PermitRequest:
        return PermitRequest.objects.select_related("staff", "school").get(school=school, pk=pk)


# ══════════════════════════════════════════════════════════════════════
#  الحضور (1.1)
# ══════════════════════════════════════════════════════════════════════


class StaffAttendanceService:
    @staticmethod
    def _approved_permits(school: School, staff: CustomUser, day: date) -> QuerySet[PermitRequest]:
        return PermitRequest.objects.filter(school=school, staff=staff, date=day, status="approved")

    @staticmethod
    def sync_permit_minutes(school: School, staff: CustomUser, day: date) -> None:
        """دقائقُ الإذن المعتمد في سجلّ اليوم — تُعاد من الأذونات لا تُجمع فوقها."""
        minutes = (
            StaffAttendanceService._approved_permits(school, staff, day).aggregate(
                total=Sum("duration_minutes")
            )["total"]
            or 0
        )
        StaffAttendance.objects.filter(school=school, staff=staff, date=day).update(
            permit_minutes=minutes
        )

    @staticmethod
    @transaction.atomic
    def mark(
        *,
        school: School,
        staff: CustomUser,
        day: date,
        status: str,
        actor: CustomUser,
        check_in: time | None = None,
        request: HttpRequest | None = None,
    ) -> StaffAttendance:
        """رصدُ حالة موظّفٍ في يوم — بنقرة، ووقتُ الحضور شاهدٌ إن كُتب.

        إن كُتب الوقتُ صنّفته القواعد، ونقرةٌ تخالف تصنيفَه تُرفض باسم البند — فلا
        يُكتب «حاضر» لمن حضر 8:10. و«مستأذن» بلا إذنٍ معتمدٍ لليوم مرفوضة (4.1).
        وتكرارُ الرصد نفسِه لا يغيّر شيئاً ولا يترك أثراً ثانياً.
        """
        if status not in STATUSES:
            raise PolicyError("حالةٌ غيرُ معروفة.")
        if day > timezone.localdate():
            raise PolicyError("لا رصدَ ليومٍ لم يأتِ بعد.")
        if not staff_members(school).filter(pk=staff.pk).exists():
            raise PolicyError("ليس من كادر هذه المدرسة.")
        permits = list(StaffAttendanceService._approved_permits(school, staff, day))
        late_minutes = 0
        if check_in is not None:
            cover = next((p.end_time for p in permits if p.permit_type == "late_arrival"), None)
            computed, late_minutes = classify_arrival(check_in, cover)
            if computed != status:
                raise PolicyError(
                    f"الحضورُ {check_in:%H:%M} يعني «{STATUS_LABELS[computed]}» "
                    "(البندان 2.1 و2.4) — لا يُرصد غيرُه."
                )
        elif status == "permitted" and not permits:
            raise PolicyError("لا إذنَ معتمدٌ لهذا اليوم (البند 4.1).")
        values: dict[str, Any] = {
            "status": status,
            "check_in": check_in,
            "late_minutes": late_minutes,
            "permit_minutes": sum(p.duration_minutes for p in permits),
        }
        record = StaffAttendance.objects.filter(school=school, staff=staff, date=day).first()
        if record is None:
            record = StaffAttendance.objects.create(
                school=school, staff=staff, date=day, created_by=actor, updated_by=actor, **values
            )
            _audit(actor, "create", record, {"status": status}, request)
            return record
        before = {key: getattr(record, key) for key in values}
        if before == values:
            return record
        for key, value in values.items():
            setattr(record, key, value)
        record.updated_by = actor
        record.save()
        _audit(actor, "update", record, {"status": [before["status"], status]}, request)
        return record

    @staticmethod
    def daily_board(school: School, day: date) -> dict[str, Any]:
        """لوحةُ اليوم: كلُّ موظّفٍ بسجلّه إن رُصد، وعددُ كلّ حالة."""
        staff = list(staff_members(school).only("id", "full_name", "employee_number"))
        records = {r.staff_id: r for r in StaffAttendance.objects.filter(school=school, date=day)}
        rows = [{"staff": s, "record": records.get(s.pk)} for s in staff]
        counts = dict.fromkeys(STATUSES, 0)
        for s in staff:
            if s.pk in records:
                counts[records[s.pk].status] += 1
        counts["unmarked"] = len(staff) - sum(counts.values())
        return {"rows": rows, "counts": counts}

    @staticmethod
    def board_row(school: School, staff_id: Any, day: date) -> dict[str, Any]:
        staff = staff_members(school).get(pk=staff_id)
        record = StaffAttendance.objects.filter(school=school, staff=staff, date=day).first()
        return {"staff": staff, "record": record}

    @staticmethod
    def monthly_report(school: School, year: int, month: int) -> dict[str, Any]:
        """تقريرُ الشهر لكلّ موظّف.

        أيّامُ كلّ حالة ودقائقُ التأخّر من سجلّ اليوم، والإذنُ المعتمد من الأذونات
        نفسِها (فإذنٌ في يومٍ لم يُرصد يُحسب)، والمتبقّي من السقف الشهريّ (4.2).
        """
        first, last = month_bounds(date(year, month, 1))
        attendance = {
            row["staff_id"]: row
            for row in StaffAttendance.objects.filter(school=school, date__range=(first, last))
            .values("staff_id")
            .annotate(
                **{key: Count("id", filter=Q(status=key)) for key in STATUSES},
                late_total=Sum("late_minutes"),
            )
        }
        permits = dict(
            PermitRequest.objects.filter(
                school=school, status="approved", date__range=(first, last)
            )
            .values("staff_id")
            .annotate(total=Sum("duration_minutes"))
            .values_list("staff_id", "total")
        )
        rows: list[dict[str, Any]] = []
        for person in staff_members(school).only("id", "full_name", "employee_number"):
            counted = attendance.get(person.pk, {})
            used = permits.get(person.pk, 0)
            rows.append(
                {
                    "employee_number": person.employee_number,
                    "full_name": person.full_name,
                    **{key: counted.get(key, 0) for key in STATUSES},
                    "late_minutes": counted.get("late_total") or 0,
                    "permit_minutes": used,
                    "permit_remaining": max(0, MONTHLY_PERMIT_CAP - used),
                }
            )
        keys = (*STATUSES, "late_minutes", "permit_minutes")
        totals = {key: sum(r[key] for r in rows) for key in keys}
        return {"first": first, "last": last, "rows": rows, "totals": totals}

    @staticmethod
    def monthly_workbook(report: dict[str, Any]) -> Any:
        """ورقةُ Excel للتقرير — بالرقم الوظيفيّ، ولا رقمَ شخصيّاً فيها أصلاً."""
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = f"{report['first']:%Y-%m}"
        ws.sheet_view.rightToLeft = True
        ws.append(
            [
                "الرقم الوظيفي",
                "الاسم",
                *(STATUS_LABELS[key] for key in STATUSES),
                "دقائق التأخّر",
                "دقائق الإذن المعتمد",
                "المتبقّي من سقف الأذونات",
            ]
        )
        for r in report["rows"]:
            ws.append(
                [
                    r["employee_number"],
                    r["full_name"],
                    *(r[key] for key in STATUSES),
                    r["late_minutes"],
                    r["permit_minutes"],
                    r["permit_remaining"],
                ]
            )
        return wb

"""حضورُ الموظّفين والأذوناتُ القصيرة — القواعدُ والخدمة.

المصادر (``AAdocs/ministry_data/2026_2027/``)، والأرقامُ بعد النقطتين أرقامُ الأسطر،
والحكمُ لأصل PDF (``data/2026-2027/05-السياسات الداخلية/01-2027 سياسة وضوابط الحضور
والانصراف.pdf``) إن خالفه الاستخراج:

* ``06_attendance_performance_review.md`` §1 «سياسة وضوابط الحضور والانصراف»
  (ت/د: 2027/01 بتاريخ 2026-08-23، مدرسة الشحانية). وأرقامُ البنود أرقامُ الوثيقة.
* ``07_forms_catalog.md:13`` و``07b_forms_catalog_thirdpass.md:13`` — نموذج 02
  (طلب تأخير / استئذان / خروج مبكر) ومراحلُ اعتماده.
* ``03_job_descriptions_rbac.md:101-102`` و``rbac_permissions_matrix.md:55`` — السكرتيرُ
  «متابعة الحضور والانصراف للموظفين» و«توثيق إجازات الموظفين» بصلاحية كتابة.
* ``rbac_roles.json`` — «reports_to» لكلّ مسمّى: من المسؤولُ المباشر.
* ``data/2026-2027/07-نماذج المدرسة/08) سجل الغياب.xlsx`` — أنواعُ أيّام الغياب
  (قائمةُ التحقّق في خلايا الأيّام E3:X122).

الفلسفة: **يحسب ولا ينفّذ آليّاً** — تُصنَّف الحالةُ وتُعدّ الدقائق، ولا خصمَ ولا
جزاءَ يُطلقه النظام؛ الخصمُ (البند 5، 06:67-69) قرارٌ إداريٌّ على التقرير الشهريّ.

قراءةُ الحدود من النصّ حرفاً:

* البند 1.1 (06:25، PDF ص1) «يبدأ الدوام الرسمي … من الساعة السابعة صباحاً وينتهي في
  تمام الثانية ظهراً» ← كلُّ نافذةِ إذنٍ بين 7:00 و14:00، والانصرافُ قبل 14:00 نقصٌ يُعدّ.
* البند 2.1 (06:31) «يعتبر الموظف متأخراً إذا حضر **بعد** الساعة 7:00 صباحاً» ←
  7:00 بالضبط حاضر، و7:01 متأخّر؛ فإذنُ التأخير يبدأ من 7:00.
* البند 2.4 (06:34) «يعتبر الموظف غائباً إذا حضر **بعد** الساعة التاسعة صباحاً دون
  إذن أو عذر مقبول» ← 9:00 بالضبط متأخّرٌ لا غائب، و9:01 غائب؛ إلّا أن يغطّي الإذنُ
  لحظةَ الحضور نفسَها، أو يُقبل عذرٌ فيُعدّ تأخّراً بدقائقه.
* البند 4.2 (06:57، ومثله 3.4 في 06:45) «الحد الأقصى للأذونات بواقع (7) ساعات في
  الشهر» ← 420 دقيقةً في الشهر الميلاديّ، والسبعُ كاملةً جائزة.
* البند 4.3 (06:58، ومثله 3.5 في 06:46) «لا يجوز الإذن أكثر من مرة واحدة في اليوم».
* البند 4.4 (06:59، ومثله 3.6 في 06:47) «الحد الأقصى للإذن ساعتين في المرة الواحدة»
  ← 120 دقيقة جائزة، و121 مرفوضة.
* البند 4.1 (06:56) «لا يجوز الاعتداد بالإذن إلا بعد اعتماده من الرئيس المباشر»،
  ونموذج 02 (07:13): «المسؤول المباشر ← النائب المسؤول ← السكرتارية (تسجّل رصيد
  الساعات) ← الإدارة … ولا يخرج الموظف فعلياً إلا بعد اعتماد مدير المدرسة» ← ثلاثُ
  مراحل (المسؤولُ المباشرُ هو النائبُ نفسُه في rbac_roles.json)، والرصيدُ يُخصم
  باعتماد المدير لا بالتقديم.
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
from staff_affairs.models import (
    ABSENCE_TYPES,
    PERMIT_TYPES,
    PermitRequest,
    StaffAttendance,
)

#: البندان 1.1 و2.1 — بدايةُ الدوام، وما بعدها تأخّر.
WORK_START = time(7, 0)
#: البند 1.1 — «وينتهي في تمام الثانية ظهراً».
WORK_END = time(14, 0)
#: البند 2.4 — ما بعدها غيابٌ ما لم يكن إذنٌ أو عذرٌ مقبول.
ABSENT_AFTER = time(9, 0)
#: البند 4.2 — سبعُ ساعاتٍ في الشهر.
MONTHLY_PERMIT_CAP = 7 * 60
#: البند 4.4 — ساعتان للمرّة.
PERMIT_MAX_MINUTES = 2 * 60

STATUSES = ("present", "late", "absent", "permitted")
STATUS_LABELS = {"present": "حاضر", "late": "متأخّر", "absent": "غائب", "permitted": "مستأذن"}
#: حالاتُ من حضر — لا تُرصد إلّا بوقت حضوره، فبه تُحسب دقائقُ التأخّر (2.1 و5.2).
ARRIVAL_STATUSES = ("present", "late", "permitted")
ABSENCE_TYPE_KEYS = tuple(key for key, _label in ABSENCE_TYPES)
NON_STAFF_ROLES = ("student", "parent")

#: rbac_roles.json:18 — مديرُ المدرسة «رأس الهيكل الذي يتبعه كل الأدوار أدناه مباشرة أو
#: عبر نائبيه»، ولا «reports_to» له داخل المدرسة.
PRINCIPAL = "principal"
#: 03_job_descriptions_rbac.md:401 و rbac_permissions_matrix.md:46 — نائبُ الشؤون الإدارية:
#: «الإنابة عن المدير في مهامه في حال غيابه».
PRINCIPAL_DELEGATE = "vice_admin"
#: من يقرأ تقريرَ الحضور للمدرسة كلّها: المديرُ رأسُ الهيكل (rbac_permissions_matrix.md:45)
#: والسكرتيرُ متابعُ الحضور (03:101). والنائبُ لمن يقيّمهم وحدَهم (:48 و:50).
REPORT_WHOLE_SCHOOL = frozenset({PRINCIPAL, "secretary"})


class PolicyError(ValueError):
    """مخالفةٌ لبندٍ من السياسة — ورسالتُها تسمّي البند."""


# ══════════════════════════════════════════════════════════════════════
#  القواعدُ الصافية
# ══════════════════════════════════════════════════════════════════════


def minutes_between(start: time, end: time) -> int:
    """الدقائقُ الكاملة من ``start`` إلى ``end`` في اليوم نفسه — والسالبُ صفر."""
    delta = datetime.combine(date.min, end) - datetime.combine(date.min, start)
    return max(0, int(delta.total_seconds() // 60))


def classify_arrival(
    check_in: time, covered_until: time | None = None, excused: bool = False
) -> tuple[str, int]:
    """(الحالة، دقائقُ التأخّر) لوقت حضورٍ — البنود 2.1 و2.4 و4.1.

    ``covered_until`` نهايةُ إذنِ «تأخيرٍ صباحيّ» معتمدٍ لليوم، ونافذتُه تبدأ من 7:00
    (``PermitService.submit``). من حضر حتّى نهايته مستأذن، ومن جاوزها تُحسب دقائقُه
    من نهاية إذنه. والإذنُ يغطّي نافذتَه لا ما بعدها: من حضر بعد التاسعة ولم يغطِّ
    الإذنُ لحظةَ حضوره غائب (2.4 «دون إذن»)، إلّا أن يُقبل عذرُه (``excused``، 2.4
    «أو عذر مقبول») فيُعدّ متأخّراً بدقائقه كاملةً.
    """
    if check_in <= WORK_START:
        return "present", 0
    if covered_until is not None and check_in <= covered_until:
        return "permitted", 0
    counted_from = max(WORK_START, covered_until or WORK_START)
    if check_in <= ABSENT_AFTER or excused:
        return "late", minutes_between(counted_from, check_in)
    return "absent", 0


def early_leave_minutes(check_out: time, windows: Iterable[tuple[time, time]] = ()) -> int:
    """دقائقُ ما بين الانصراف ونهاية الدوام (1.1) التي لا يغطّيها إذنٌ معتمد.

    ``windows`` نوافذُ أذونات اليوم المعتمدة (خروجٌ مبكر أو استئذان) — ولا يتداخل
    إذنان معتمدان في يومٍ واحد (4.3)، فتُطرح كلٌّ منها على حدة.
    """
    gap = minutes_between(check_out, WORK_END)
    covered = sum(
        minutes_between(max(start, check_out), min(end, WORK_END)) for start, end in windows
    )
    return max(0, gap - covered)


def month_bounds(day: date) -> tuple[date, date]:
    last = calendar.monthrange(day.year, day.month)[1]
    return day.replace(day=1), day.replace(day=last)


def _plain(value: Any) -> Any:
    """قيمةٌ تُكتب في سجلّ التدقيق (JSON): الوقتُ «HH:MM»."""
    if isinstance(value, time):
        return f"{value:%H:%M}"
    return value


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


def _role_of(user: CustomUser) -> str:
    """الدورُ الحاكمُ للمستخدم — ما يفحصه الحارسُ نفسُه."""
    return str(user.get_role())  # type: ignore[no-untyped-call]


def staff_members(school: School) -> QuerySet[CustomUser]:
    """كادرُ المدرسة النشط — أشخاصٌ لا عضويّات، بلا طلبةٍ ولا أولياء."""
    member_ids = (
        Membership.objects.filter(school=school, is_active=True)
        .exclude(role__name__in=NON_STAFF_ROLES)
        .values("user_id")
    )
    return CustomUser.objects.filter(pk__in=member_ids, is_active=True).order_by("full_name")


def _active_role_holders(school: School, role: str) -> set[Any]:
    return set(
        Membership.objects.filter(school=school, is_active=True, role__name=role).values_list(
            "user_id", flat=True
        )
    )


def principal_absent_today(school: School) -> bool:
    """أمرصودٌ مديرُ المدرسة غائباً اليوم؟ — شرطُ الإنابة «في حال غيابه» (03:401).

    الغيابُ من سجلّ الحضور نفسِه الذي ترصده السكرتارية، لا من دعوى من ينوب.
    """
    principals = _active_role_holders(school, PRINCIPAL)
    if not principals:
        return False
    absent = StaffAttendance.objects.filter(
        school=school, date=timezone.localdate(), status="absent", staff_id__in=principals
    ).count()
    return absent == len(principals)


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


#: المسؤولُ المباشر لكلّ دورٍ في المنصّة — من «reports_to» في rbac_roles.json، ورقمُ
#: السطر سطرُ «title» المسمّى هناك. والمسمّياتُ الوزاريّةُ التي لا دورَ لها في المنصّة
#: («منسق الدعم الإضافي» :154، «منسق شؤون الطالب» :173) لا تظهر هنا. وما لا بطاقةَ
#: لمسمّاه (مرشدٌ أكاديميّ، محاسب، …) يرفع إلى المدير — ``line_manager_role``.
LINE_MANAGER: dict[str, str] = {
    "vice_admin": "principal",  # :21 نائب المدير للشؤون الإدارية وشؤون الطالب
    "vice_academic": "principal",  # :28 نائب المدير للشؤون الأكاديمية
    "secretary": "principal",  # :36 سكرتير مدرسة
    "social_worker": "vice_admin",  # :43 أخصائي اجتماعي
    "psychologist": "vice_admin",  # :50 أخصائي نفسي
    "storekeeper": "vice_admin",  # :58 أمين مخزن
    "services_worker": "vice_admin",  # :65 عامل خدمات
    "lab_technician": "vice_academic",  # :72 محضر مختبر
    "support_companion": "vice_admin",  # :79 مرافق الدعم
    "it_technician": "vice_admin",  # :86 مسؤول تقنية معلومات
    "librarian": "vice_academic",  # :97 مسؤول مركز مصادر التعلم
    "admin_supervisor": "vice_admin",  # :105 مشرف اداري
    "canteen_supervisor": "vice_admin",  # :112 مشرف مقصف
    "ese_teacher": "vice_academic",  # :119 معلم دعم تعليمي إضافي
    "teacher": "vice_academic",  # :126 معلم
    "student_observer": "vice_admin",  # :133 ملاحظ طلبة
    "nurse": "vice_admin",  # :140 ممرض
    "messenger": "vice_admin",  # :147 مندوب
    "e_projects_coordinator": "vice_academic",  # :161 منسق المشاريع الالكترونية
    "coordinator": "vice_academic",  # :181 منسق مادة
    "receptionist": "vice_admin",  # :188 موظف استقبال
}

#: من يعمل في كلّ مرحلةٍ بعد الأولى — والأولى بحسب صاحب الطلب (``LINE_MANAGER``).
STAGE_ROLE = {"secretary": "secretary", "principal": "principal"}


def can_submit_permits(user: CustomUser) -> bool:
    """أيُقدَّم إذنُ هذا المستخدم في المنصّة؟ — لا للمدير (``line_manager_role``)."""
    return _role_of(user) != PRINCIPAL


def line_manager_role(role: str) -> str:
    """دورُ المسؤول المباشر لصاحب الدور.

    من «reports_to» حيث وُجدت بطاقتُه. وما لا بطاقةَ لمسمّاه — وسجلُّ الاستئذانات
    المدرسيّ (07-نماذج المدرسة/07) عمود المسمّى) يتتبّع أذوناتِ المرشد الأكاديميّ
    والمحاسب وأخصائيّ الأنشطة وغيرهم — فمسؤولُه مديرُ المدرسة: «رأس الهيكل الذي
    يتبعه كل الأدوار» (rbac_roles.json:18). والمديرُ نفسُه لا رئيسَ له داخل المدرسة،
    والبندُ 4.1 لا يعتدّ بإذنٍ إلّا باعتماد الرئيس المباشر، فلا يُقدَّم إذنُه هنا.
    """
    if role == PRINCIPAL:
        raise PolicyError(
            "إذنُ مدير المدرسة لا يُعتدّ به إلّا باعتماد رئيسه المباشر (البند 4.1)، "
            "ولا رئيسَ له داخل المدرسة (rbac_roles.json:18) — فلا يُقدَّم في المنصّة."
        )
    return LINE_MANAGER.get(role, PRINCIPAL)


def _check_window(permit_type: str, start: time, end: time) -> None:
    """نافذةُ الإذن داخلَ الدوام (1.1) وعلى قدر نوعه.

    التأخيرُ الصباحيّ يبدأ من 7:00 لأنّ التأخّرَ يُعدّ من بعدها (2.1)، والخروجُ المبكر
    ينتهي بنهاية الدوام 14:00 (1.1)، والاستئذانُ أثناء الدوام بينهما — فإذنٌ لا يبدأ
    من أوّل التأخّر لا يغطّيه، وإذنٌ بعد الدوام لا يستهلك من سقف الشهر بلا معنى.
    """
    if start < WORK_START or end > WORK_END:
        raise PolicyError("نافذةُ الإذن خارجَ الدوام الرسميّ 7:00–14:00 (البند 1.1).")
    if permit_type == "late_arrival" and start != WORK_START:
        raise PolicyError(
            "التأخيرُ الصباحيّ يبدأ من 7:00 — فالتأخّرُ يُعدّ من بعدها (البند 2.1)؛ "
            "وما يبدأ بعدها «استئذانٌ أثناء الدوام»."
        )
    if permit_type == "early_departure" and end != WORK_END:
        raise PolicyError(
            "الخروجُ المبكر ينتهي بنهاية الدوام 14:00 (البند 1.1)؛ "
            "وما ينتهي قبلها «استئذانٌ أثناء الدوام»."
        )
    if permit_type == "during_day" and (start == WORK_START or end == WORK_END):
        raise PolicyError(
            "استئذانٌ يبدأ 7:00 تأخيرٌ صباحيّ، وما ينتهي 14:00 خروجٌ مبكر (البندان 1.1 و2.1)."
        )


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
        supervisor_role = line_manager_role(_role_of(staff))
        _check_window(permit_type, start_time, end_time)
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
            supervisor_role=supervisor_role,
            created_by=staff,
            updated_by=staff,
        )
        _audit(staff, "create", permit, {"type": permit_type, "minutes": duration}, request)
        return permit

    @staticmethod
    def _lone_secretaries(school: School) -> set[Any]:
        """السكرتيرُ الوحيدُ في مدرسته — لا زميلَ يسجّل رصيدَ طلبه هو."""
        secretaries = _active_role_holders(school, "secretary")
        return secretaries if len(secretaries) == 1 else set()

    @staticmethod
    def required_role(permit: PermitRequest) -> str:
        """دورُ من يعمل في مرحلة الطلب الآن.

        ومربّعُ السكرتارية لطلب السكرتير نفسِه: يسجّله زميلُه إن كان، وإلّا فمديرُ
        المدرسة — فلا يعمل أحدٌ في طلبه (4.1)، ولا يعلق الطلبُ بلا من يسجّله.
        """
        if permit.stage == "supervisor":
            return permit.supervisor_role
        if permit.stage == "secretary" and permit.staff_id in PermitService._lone_secretaries(
            permit.school
        ):
            return PRINCIPAL
        return STAGE_ROLE.get(permit.stage, "")

    @staticmethod
    def _acting_roles(school: School, user: CustomUser) -> set[str]:
        """أدوارُ من يعمل: دورُه، والمديرُ معه لنائب الشؤون الإدارية حين يُرصد المديرُ غائباً."""
        role = _role_of(user)
        roles = {role}
        if role == PRINCIPAL_DELEGATE and principal_absent_today(school):
            roles.add(PRINCIPAL)
        return roles

    @staticmethod
    @transaction.atomic
    def act(
        permit: PermitRequest,
        *,
        actor: CustomUser,
        approve: bool,
        reason: str = "",
        request: HttpRequest | None = None,
    ) -> PermitRequest:
        """مرحلةٌ واحدةٌ من نموذج 02 — تحت قفل صفّ الموظّف فلا تتسابق مرحلتان.

        * المسؤولُ المباشر: موافق/غير موافق.
        * السكرتارية: تسجّل رصيدَ الساعات (المتبقّي قبل الطلب) واسمَها ووقتَها
          (07b:13)، ولا قرارَ لها في المصدر — فإن جاوز الطلبُ السقفَ (4.2) سُجّل
          رفضاً باسم البند لا بتقديرها.
        * مديرُ المدرسة: الاعتمادُ النهائيّ (07:13)، ويُعاد فحصُ 4.3 و4.2 على المعتمَد،
          وبه وحدَه يُخصم الرصيد (4.1). وينوب عنه نائبُ الشؤون الإدارية حين يُرصد غائباً.

        وبعد الاعتماد يُعاد تصنيفُ سجلّ حضور اليوم إن رُصد قبله.
        """
        CustomUser.objects.select_for_update().filter(pk=permit.staff_id).first()
        permit.refresh_from_db()
        if permit.status != "pending":
            raise PolicyError(f"الطلبُ «{permit.get_status_display()}» — لا يُراجَع ثانيةً.")
        if actor.pk == permit.staff_id:
            raise PolicyError("لا يعمل أحدٌ في طلبه هو (البند 4.1: الاعتمادُ من غيره).")
        needed = PermitService.required_role(permit)
        acting = PermitService._acting_roles(permit.school, actor)
        if needed not in acting:
            raise PolicyError(f"الطلبُ بانتظار «{permit.get_stage_display()}» لا دورك.")
        on_behalf = needed if needed != _role_of(actor) else ""
        stage, now = permit.stage, timezone.now()
        if stage == "secretary":
            approve, reason = PermitService._record_balance(permit, actor, now)
        if not approve:
            permit.status, permit.rejected_stage, permit.stage = "rejected", stage, "closed"
            permit.rejection_reason = reason.strip()[:300]
        elif stage == "supervisor":
            permit.supervisor_by, permit.supervisor_at, permit.stage = actor, now, "secretary"
        elif stage == "principal":
            PermitService._check_rules(
                permit.school,
                permit.staff,
                permit.date,
                permit.duration_minutes,
                open_statuses=("approved",),
                exclude_pk=permit.pk,
            )
            permit.status, permit.stage = "approved", "closed"
            permit.reviewed_by, permit.reviewed_at = actor, now
        permit.updated_by = actor
        try:
            with transaction.atomic():
                permit.save()
        except IntegrityError as exc:
            raise PolicyError("لا يجوز الإذنُ أكثرَ من مرّةٍ في اليوم الواحد (البند 4.3).") from exc
        changes: dict[str, Any] = {"stage": stage, "status": permit.status}
        if on_behalf:
            changes["on_behalf_of"] = on_behalf
        _audit(actor, "update", permit, changes, request)
        if permit.status == "approved":
            StaffAttendanceService.reconcile(
                permit.school, permit.staff, permit.date, actor=actor, request=request
            )
        return permit

    @staticmethod
    @transaction.atomic
    def cancel(
        permit: PermitRequest, *, actor: CustomUser, request: HttpRequest | None = None
    ) -> PermitRequest:
        """يسحب صاحبُ الطلب طلبَه ما دام معلَّقاً — فيُفرج عن يومه (4.3) ودقائقه (4.2)."""
        CustomUser.objects.select_for_update().filter(pk=permit.staff_id).first()
        permit.refresh_from_db()
        if actor.pk != permit.staff_id:
            raise PolicyError("لا يسحب الطلبَ إلّا صاحبُه.")
        if permit.status != "pending":
            raise PolicyError(f"الطلبُ «{permit.get_status_display()}» — لا يُسحب.")
        stage = permit.stage
        permit.status, permit.stage, permit.updated_by = "cancelled", "closed", actor
        permit.save(update_fields=["status", "stage", "updated_by", "updated_at"])
        _audit(actor, "update", permit, {"stage": stage, "status": "cancelled"}, request)
        return permit

    @staticmethod
    def _record_balance(
        permit: PermitRequest, actor: CustomUser, now: datetime
    ) -> tuple[bool, str]:
        """مربّعُ السكرتارية: الرصيدُ المتبقّي قبل الطلب، ثمّ المرحلةُ التالية أو الرفضُ بالبند."""
        used = PermitService._month_minutes(
            permit.school, permit.staff, permit.date, ("approved",), permit.pk
        )
        remaining = max(0, MONTHLY_PERMIT_CAP - used)
        permit.recorded_balance_minutes = remaining
        permit.secretary_by, permit.secretary_at = actor, now
        if permit.duration_minutes > remaining:
            return False, f"يتجاوز سقفَ الأذونات الشهريّ (البند 4.2): المتبقّي {remaining} دقيقة."
        permit.stage = "principal"
        return True, ""

    @staticmethod
    def own_permits(school: School, staff: CustomUser) -> QuerySet[PermitRequest]:
        return PermitRequest.objects.filter(school=school, staff=staff).order_by(
            "-date", "-created_at"
        )[:50]

    @staticmethod
    def awaiting(school: School, user: CustomUser) -> QuerySet[PermitRequest]:
        """الطلباتُ المعلّقةُ في مرحلةٍ يعمل فيها هذا المستخدم — لا طلبُه هو."""
        acting = PermitService._acting_roles(school, user)
        lone = PermitService._lone_secretaries(school)
        in_my_stage = Q(pk__in=[])
        for role in acting:
            in_my_stage |= Q(stage="supervisor", supervisor_role=role)
            if role == "secretary":
                in_my_stage |= Q(stage="secretary") & ~Q(staff_id__in=lone)
            if role == PRINCIPAL:
                in_my_stage |= Q(stage="principal") | Q(stage="secretary", staff_id__in=lone)
        return (
            PermitRequest.objects.filter(in_my_stage, school=school, status="pending")
            .exclude(staff=user)
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
    def _approved_permits(school: School, staff: CustomUser, day: date) -> list[PermitRequest]:
        return list(
            PermitRequest.objects.filter(school=school, staff=staff, date=day, status="approved")
        )

    @staticmethod
    def _derive(
        permits: list[PermitRequest],
        check_in: time | None,
        check_out: time | None,
        excused: bool,
    ) -> dict[str, Any]:
        """ما يُحسب من الأوقات والأذونات المعتمدة: التصنيفُ والدقائق."""
        cover = next((p.end_time for p in permits if p.permit_type == "late_arrival"), None)
        derived: dict[str, Any] = {
            "status": None,
            "late_minutes": 0,
            "permit_minutes": sum(p.duration_minutes for p in permits),
            "early_leave_minutes": 0,
            "excuse_used": False,
        }
        if check_in is not None:
            derived["status"], derived["late_minutes"] = classify_arrival(check_in, cover, excused)
            derived["excuse_used"] = excused and classify_arrival(check_in, cover)[0] == "absent"
        if check_out is not None:
            windows = [
                (p.start_time, p.end_time) for p in permits if p.permit_type != "late_arrival"
            ]
            derived["early_leave_minutes"] = early_leave_minutes(check_out, windows)
        return derived

    @staticmethod
    def _changes(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        return {
            key: [_plain(before[key]), _plain(value)]
            for key, value in after.items()
            if before[key] != value
        }

    @staticmethod
    @transaction.atomic
    def reconcile(
        school: School,
        staff: CustomUser,
        day: date,
        *,
        actor: CustomUser,
        request: HttpRequest | None = None,
    ) -> StaffAttendance | None:
        """يُعيد حسابَ سجلّ اليوم من أوقاته المرصودة وأذوناته المعتمدة الآن.

        يُستدعى باعتماد إذنٍ لليوم: فمن رُصد متأخّراً 8:15 ثمّ اعتُمد له تأخيرٌ إلى 8:30
        صار مستأذناً بلا دقائق تأخّر — لا متأخّراً ومستأذناً معاً. ومن لم يُكتب له
        وقتُ حضور (غائبٌ لم يحضر) تبقى حالتُه، وتتبدّل دقائقُ إذنه وحدَها.
        """
        record = (
            StaffAttendance.objects.select_for_update()
            .filter(school=school, staff=staff, date=day)
            .first()
        )
        if record is None:
            return None
        derived = StaffAttendanceService._derive(
            StaffAttendanceService._approved_permits(school, staff, day),
            record.check_in,
            record.check_out,
            bool(record.accepted_excuse),
        )
        status = derived["status"] or record.status
        values = {
            "status": status,
            "late_minutes": derived["late_minutes"],
            "permit_minutes": derived["permit_minutes"],
            "early_leave_minutes": derived["early_leave_minutes"],
            "absence_type": record.absence_type if status == "absent" else "",
        }
        before = {key: getattr(record, key) for key in values}
        changes = StaffAttendanceService._changes(before, values)
        if not changes:
            return record
        for key, value in values.items():
            setattr(record, key, value)
        record.updated_by = actor
        record.save()
        _audit(actor, "update", record, {**changes, "cause": "permit_approved"}, request)
        return record

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
        check_out: time | None = None,
        absence_type: str = "",
        accepted_excuse: str = "",
        request: HttpRequest | None = None,
    ) -> StaffAttendance:
        """رصدُ حالة موظّفٍ في يوم — بنقرة، ووقتُ الحضور شاهدُها.

        * لا يرصد أحدٌ نفسَه: السجلُّ سندُ الخصم (البند 5).
        * الحاضرُ والمتأخّرُ والمستأذنُ بوقت حضورهم، فبه تُحسب دقائقُ التأخّر (2.1 و5.2)،
          ونقرةٌ تخالف تصنيفَه تُرفض باسم البند. والغائبُ بلا وقتٍ جائز.
        * ``accepted_excuse`` (2.4 «أو عذر مقبول») يُكتب لمن حضر بعد 9:00 بلا إذنٍ يغطّيه،
          فيُعدّ متأخّراً بدقائقه لا غائباً.
        * ``absence_type`` نوعُ يوم الغياب من سجلّ الغياب المدرسيّ (إجازةٌ أو مهمّة)،
          والفارغُ غيابٌ لم يُغطَّ بعد (5.3).
        * ``check_out`` وقتُ الانصراف، وما بينه وبين 14:00 بلا إذنٍ يُعدّ (1.1).

        وتكرارُ الرصد نفسِه لا يغيّر شيئاً ولا يترك أثراً ثانياً، والتعديلُ يُدقَّق بكلّ
        ما تغيّر وقيمتِه قبل.
        """
        if status not in STATUSES:
            raise PolicyError("حالةٌ غيرُ معروفة.")
        if day > timezone.localdate():
            raise PolicyError("لا رصدَ ليومٍ لم يأتِ بعد.")
        if actor.pk == staff.pk:
            raise PolicyError("لا يرصد أحدٌ حضورَ نفسه — السجلُّ سندُ الخصم (البند 5).")
        if not staff_members(school).filter(pk=staff.pk).exists():
            raise PolicyError("ليس من كادر هذه المدرسة.")
        absence_type = absence_type or ""
        excuse = accepted_excuse.strip()[:300]
        if absence_type and absence_type not in ABSENCE_TYPE_KEYS:
            raise PolicyError("نوعُ غيابٍ غيرُ معروف (سجلّ الغياب).")
        if absence_type and status != "absent":
            raise PolicyError("نوعُ الغياب لا يُكتب إلّا لغائب (سجلّ الغياب).")
        if status in ARRIVAL_STATUSES and check_in is None:
            raise PolicyError(
                f"«{STATUS_LABELS[status]}» يُرصد بوقت الحضور — به تُحسب دقائقُ التأخّر "
                "(البندان 2.1 و5.2)."
            )
        if check_out is not None and (check_in is None or check_out <= check_in):
            raise PolicyError("وقتُ الانصراف يُكتب بعد وقت الحضور.")
        derived = StaffAttendanceService._derive(
            StaffAttendanceService._approved_permits(school, staff, day),
            check_in,
            check_out,
            bool(excuse),
        )
        if check_in is not None and derived["status"] != status:
            raise PolicyError(
                f"الحضورُ {check_in:%H:%M} يعني «{STATUS_LABELS[derived['status']]}» "
                "(البندان 2.1 و2.4) — لا يُرصد غيرُه."
            )
        if excuse and not derived["excuse_used"]:
            raise PolicyError("العذرُ المقبول يُكتب لمن حضر بعد 9:00 بلا إذنٍ يغطّيه وحدَه (البند 2.4).")
        values: dict[str, Any] = {
            "status": status,
            "check_in": check_in,
            "check_out": check_out,
            "late_minutes": derived["late_minutes"],
            "permit_minutes": derived["permit_minutes"],
            "early_leave_minutes": derived["early_leave_minutes"],
            "absence_type": absence_type,
            "accepted_excuse": excuse,
        }
        record = StaffAttendance.objects.filter(school=school, staff=staff, date=day).first()
        if record is None:
            record = StaffAttendance.objects.create(
                school=school, staff=staff, date=day, created_by=actor, updated_by=actor, **values
            )
            created = {key: _plain(value) for key, value in values.items() if value}
            _audit(actor, "create", record, {"status": status, **created}, request)
            return record
        before = {key: getattr(record, key) for key in values}
        changes = StaffAttendanceService._changes(before, values)
        if not changes:
            return record
        for key, value in values.items():
            setattr(record, key, value)
        record.updated_by = actor
        record.save()
        _audit(actor, "update", record, changes, request)
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
    def _report_people(
        school: School, first: date, last: date, viewer: CustomUser | None
    ) -> list[CustomUser]:
        """من يدخل تقريرَ الشهر: الكادرُ النشط، ومن له سجلٌّ أو إذنٌ معتمدٌ فيه وإن غادر.

        والنائبان يريان من يتبعهما وحدَهم: نائبُ الشؤون الإدارية «متابعة وتقييم أداء
        من يندرج تحت مسؤولياته» (rbac_permissions_matrix.md:48)، والأكاديميّ «تقييم
        المنسقين والمعلمين» (:50) — والتبعيّةُ من «reports_to» (``LINE_MANAGER``).
        """
        marked = StaffAttendance.objects.filter(school=school, date__range=(first, last)).values(
            "staff_id"
        )
        permitted = PermitRequest.objects.filter(
            school=school, status="approved", date__range=(first, last)
        ).values("staff_id")
        people = CustomUser.objects.filter(
            Q(pk__in=staff_members(school).values("pk")) | Q(pk__in=marked) | Q(pk__in=permitted)
        ).order_by("full_name")
        viewer_role = _role_of(viewer) if viewer is not None else PRINCIPAL
        if viewer_role in REPORT_WHOLE_SCHOOL or viewer_role not in LINE_MANAGER.values():
            return list(people.only("id", "full_name", "employee_number"))
        roles: dict[Any, set[str]] = {}
        for user_id, role in (
            Membership.objects.filter(school=school, user__in=people)
            .exclude(role__name__in=NON_STAFF_ROLES)
            .values_list("user_id", "role__name")
        ):
            roles.setdefault(user_id, set()).add(role)
        return [
            person
            for person in people.only("id", "full_name", "employee_number")
            if any(
                LINE_MANAGER.get(role, PRINCIPAL) == viewer_role
                for role in roles.get(person.pk, ())
            )
        ]

    @staticmethod
    def monthly_report(
        school: School, year: int, month: int, viewer: CustomUser | None = None
    ) -> dict[str, Any]:
        """تقريرُ الشهر لكلّ موظّفٍ في نطاق ``viewer`` (بلا ``viewer``: المدرسةُ كلُّها).

        أيّامُ كلّ حالة ودقائقُ التأخّر والانصراف المبكر من سجلّ اليوم، وأيّامُ الغياب
        بأنواعها وغيرُ المغطّى منها (5.3)، والإذنُ المعتمد من الأذونات نفسِها (فإذنٌ في
        يومٍ لم يُرصد يُحسب)، والمتبقّي من السقف الشهريّ (4.2).
        """
        first, last = month_bounds(date(year, month, 1))
        attendance = {
            row["staff_id"]: row
            for row in StaffAttendance.objects.filter(school=school, date__range=(first, last))
            .values("staff_id")
            .annotate(
                **{key: Count("id", filter=Q(status=key)) for key in STATUSES},
                **{
                    f"absence_{key}": Count("id", filter=Q(status="absent", absence_type=key))
                    for key in ABSENCE_TYPE_KEYS
                },
                absent_uncovered=Count("id", filter=Q(status="absent", absence_type="")),
                late_total=Sum("late_minutes"),
                early_total=Sum("early_leave_minutes"),
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
        for person in StaffAttendanceService._report_people(school, first, last, viewer):
            counted = attendance.get(person.pk, {})
            used = permits.get(person.pk, 0)
            rows.append(
                {
                    "employee_number": person.employee_number,
                    "full_name": person.full_name,
                    **{key: counted.get(key, 0) for key in STATUSES},
                    "absent_uncovered": counted.get("absent_uncovered", 0),
                    **{
                        f"absence_{key}": counted.get(f"absence_{key}", 0)
                        for key in ABSENCE_TYPE_KEYS
                    },
                    "late_minutes": counted.get("late_total") or 0,
                    "early_leave_minutes": counted.get("early_total") or 0,
                    "permit_minutes": used,
                    "permit_remaining": max(0, MONTHLY_PERMIT_CAP - used),
                }
            )
        keys = (
            *STATUSES,
            "absent_uncovered",
            "late_minutes",
            "early_leave_minutes",
            "permit_minutes",
        )
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
                "غياب غير مغطّى",
                *(f"غياب: {label}" for _key, label in ABSENCE_TYPES),
                "دقائق التأخّر",
                "دقائق الانصراف المبكر بلا إذن",
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
                    r["absent_uncovered"],
                    *(r[f"absence_{key}"] for key in ABSENCE_TYPE_KEYS),
                    r["late_minutes"],
                    r["early_leave_minutes"],
                    r["permit_minutes"],
                    r["permit_remaining"],
                ]
            )
        return wb

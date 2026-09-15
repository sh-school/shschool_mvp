"""حضورُ الموظّفين والأذوناتُ القصيرة — القواعدُ والخدمة.

المصادر (``AAdocs/ministry_data/2026_2027/``)، والأرقامُ بعد النقطتين أرقامُ الأسطر،
والحكمُ لأصل PDF (``data/2026-2027/05-السياسات الداخلية/01-2027 سياسة وضوابط الحضور
والانصراف.pdf``) إن خالفه الاستخراج:

* ``06_attendance_performance_review.md`` §1 «سياسة وضوابط الحضور والانصراف»
  (ت/د: 2027/01 بتاريخ 2026-08-23، سياسةٌ داخليّةٌ للمدرسة). وأرقامُ البنود أرقامُ الوثيقة.
* ``07_forms_catalog.md:13`` و``07b_forms_catalog_thirdpass.md:13`` وأصلُ النموذج
  (``data/2026-2027/07-نماذج المدرسة/02) نموذج طلب تأخير - استئذان - خروج مبكر.pdf``،
  ص1) — نموذج 02 ومربّعاتُه: «المسؤول المباشر» و«النائب المسؤول» عمودان منفصلان،
  ثمّ «استخدام السكرتارية» (رصيد الساعات، الاسم، التوقيت)، ثمّ «استخدام الإدارة».
* ``07_forms_catalog.md:14`` وأصلُه (``07-نماذج المدرسة/03) نموذج طلب.pdf``، ص1) —
  نموذج 03 الموجَّه إلى مدير المدرسة: «يجب ارفاق مع طلب استثناء الخروج المبكر أو
  التأخير الصباحي ما يثبت حاجة الموظف لذلك»، و«استخدام مدير المدرسة: التغذية الراجعة».
* ``03_job_descriptions_rbac.md:101-102`` و``rbac_permissions_matrix.md:55`` — السكرتيرُ
  «متابعة الحضور والانصراف للموظفين» و«توثيق إجازات الموظفين» بصلاحية كتابة.
* ``rbac_roles.json`` — «reports_to» لكلّ مسمّى: من النائبُ المسؤول.
* ``data/2026-2027/07-نماذج المدرسة/08) سجل الغياب.xlsx`` — أنواعُ أيّام الغياب
  (قائمةُ التحقّق في خلايا الأيّام E3:X122)، و``07) سجل الاستئذانات.xlsx`` — سجلٌّ
  تحفظه المدرسة لكلّ منتسبٍ وأوّلُ صفوفه مديرُ المدرسة (B3:C3، ورقة «تأخير - يناير»).

الفلسفة: **يحسب ولا ينفّذ آليّاً** — تُصنَّف الحالةُ وتُعدّ الدقائق، ولا خصمَ ولا
جزاءَ يُطلقه النظام؛ الخصمُ (البند 5، 06:67-69) قرارٌ إداريٌّ على التقرير الشهريّ.

قراءةُ الحدود من النصّ حرفاً:

* البند 1.1 (06:25، PDF ص1) «يبدأ الدوام الرسمي … من الساعة السابعة صباحاً وينتهي في
  تمام الثانية ظهراً» ← كلُّ نافذةِ إذنٍ بين 7:00 و14:00، والانصرافُ قبل 14:00 نقصٌ يُعدّ.
* البند 2.1 (06:31) «يعتبر الموظف متأخراً إذا حضر **بعد** الساعة 7:00 صباحاً» ←
  7:00 بالضبط حاضر، و7:01 متأخّر؛ فإذنُ التأخير يبدأ من 7:00.
* البند 2.4 (06:34) «يعتبر الموظف غائباً إذا حضر **بعد** الساعة التاسعة صباحاً دون
  إذن أو عذر مقبول» ← 9:00 بالضبط متأخّرٌ لا غائب، و9:01 غائب — إلّا أن يكون له إذنُ
  تأخيرٍ معتمدٌ لليوم («دون إذن») أو يُقبل عذرُه، فيُعدّ متأخّراً بدقائقه بعد إذنه.
* البند 4.2 (06:57، ومثله 3.4 في 06:45) «الحد الأقصى للأذونات بواقع (7) ساعات في
  الشهر» ← 420 دقيقةً في الشهر الميلاديّ، والسبعُ كاملةً جائزة.
* البند 4.3 (06:58، ومثله 3.5 في 06:46) «لا يجوز الإذن أكثر من مرة واحدة في اليوم».
* البند 4.4 (06:59، ومثله 3.6 في 06:47) «الحد الأقصى للإذن ساعتين في المرة الواحدة»
  ← 120 دقيقة جائزة، و121 مرفوضة.
* البند 4.1 (06:56) «لا يجوز الاعتداد بالإذن إلا بعد اعتماده من الرئيس المباشر»،
  وحاشيةُ نموذج 02 «يتعين على الموظف عدم الخروج إلا بعد اعتماده وإخطاره من قبل
  السكرتارية» و«لا يعتبر الطلب معتمداً الا باعتماد مدير المدرسة وتوقيعه عليه» ←
  الرصيدُ يُخصم بالاعتماد الأخير، والخروجُ والاستئذانُ يُطلبان قبل وقتهما.
* البند 5.1 (06:67) «الخصم … بعد إشعار الموظف … بداية كل شهر، بتقرير أيام الغياب عن
  الشهر السابق» ← شهرٌ مضى أُشعر بتقريره، فلا يُفتح بإذنٍ يُقدَّم أو يُعتمد بعده.
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
    EXCEPTION_TYPES,
    PERMIT_TYPES,
    AttendanceException,
    PermitRequest,
    PrincipalDelegation,
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
#: من مسؤولُه المباشرُ منسّقُ قسمه، ثمّ النائبُ المسؤول: المعلّمُ يُبلغ «منسّق المادة» ومعه
#: النائبَ الأكاديميّ (البند 2.3، 06:33)، ومنسّقُ المادة «يشارك … في تقييم أداء معلمي قسمه»
#: (03:374)، ومنسّقُ الدعم الإضافي «الإشراف وتقييم أداء فريق معلمي الدعم الإضافي» (03:325).
DEPARTMENT_LED_ROLES = ("teacher", "ese_teacher")


def _now() -> datetime:
    """الساعةُ المحلّيّة — منها وحدَها يُقرأ «اليوم» و«الآن» في القواعد."""
    return timezone.localtime()


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

    ``covered_until`` نهايةُ إذنِ «تأخيرٍ صباحيّ» معتمدٍ لليوم (نموذج 02 أو استثناءُ نموذج
    03)، ونافذتُه تبدأ من 7:00. من حضر حتّى نهايته مستأذن، ومن جاوزها تُحسب دقائقُه من
    نهاية إذنه — وإن حضر بعد التاسعة، فالغيابُ في 2.4 لمن حضر بعدها «دون إذن أو عذر
    مقبول»، وهذا له إذن. ومن لا إذنَ له وحضر بعد التاسعة غائب، إلّا أن يُقبل عذرُه
    (``excused``) فيُعدّ متأخّراً بدقائقه كاملةً.
    """
    if check_in <= WORK_START:
        return "present", 0
    if covered_until is not None and check_in <= covered_until:
        return "permitted", 0
    counted_from = max(WORK_START, covered_until or WORK_START)
    if check_in <= ABSENT_AFTER or covered_until is not None or excused:
        return "late", minutes_between(counted_from, check_in)
    return "absent", 0


def early_leave_minutes(check_out: time, windows: Iterable[tuple[time, time]] = ()) -> int:
    """دقائقُ ما بين الانصراف ونهاية الدوام (1.1) التي لا يغطّيها إذنٌ معتمد.

    ``windows`` نوافذُ اليوم المعتمدة (خروجٌ مبكر أو استئذانٌ من نموذج 02، أو استثناءُ
    خروجٍ من نموذج 03) — وقد تتداخل نافذةُ استثناءٍ ونافذةُ إذن، فتُطرح اتّحادُها مرّة.
    """
    gap = minutes_between(check_out, WORK_END)
    spans = sorted(
        (max(start, check_out), min(end, WORK_END))
        for start, end in windows
        if min(end, WORK_END) > max(start, check_out)
    )
    covered, reach = 0, check_out
    for start, end in spans:
        start = max(start, reach)
        if end > start:
            covered += minutes_between(start, end)
            reach = end
    return max(0, gap - covered)


def month_bounds(day: date) -> tuple[date, date]:
    last = calendar.monthrange(day.year, day.month)[1]
    return day.replace(day=1), day.replace(day=last)


def _check_open_month(day: date, now: datetime) -> None:
    """البند 5.1 (06:67): الخصمُ بإشعارٍ «بداية كل شهر، بتقرير أيام الغياب عن الشهر السابق».

    فشهرٌ انقضى أُشعر الموظّفُ بتقريره، ولا يُعاد تصنيفُ أيّامه بإذنٍ يُقدَّم أو يُعتمد
    بعد انقضائه.
    """
    if day < now.date().replace(day=1):
        raise PolicyError(
            f"شهرُ {day:%Y-%m} انقضى وأُشعر بتقريره بداية الشهر التالي (البند 5.1) — "
            "فلا إذنَ يُقدَّم له أو يُعتمد الآن."
        )


def _plain(value: Any) -> Any:
    """قيمةٌ تُكتب في سجلّ التدقيق (JSON): الوقتُ «HH:MM» والتاريخُ «YYYY-MM-DD»."""
    if isinstance(value, time):
        return f"{value:%H:%M}"
    if isinstance(value, date):
        return f"{value:%Y-%m-%d}"
    return value


def _audit(
    actor: CustomUser,
    action: str,
    obj: StaffAttendance | PermitRequest | AttendanceException | PrincipalDelegation,
    changes: dict[str, Any],
    request: HttpRequest | None = None,
) -> None:
    """أثرٌ في سجلّ التدقيق بلا اسمٍ ولا رقمٍ شخصيّ — النوعُ والمعرّفُ والتغيير."""
    day = obj.start_date if isinstance(obj, AttendanceException) else obj.date
    AuditLog.log(  # type: ignore[no-untyped-call]
        user=actor,
        action=action,
        model_name="other",
        object_id=obj.pk,
        object_repr=f"{type(obj).__name__} {day:%Y-%m-%d}",
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
        Membership.objects.filter(
            school=school, is_active=True, user__is_active=True, role__name=role
        ).values_list("user_id", flat=True)
    )


class _StageDay:
    """من يحضر مراحلَ الاعتماد في مدرسةٍ في يوم — يُقرأ مرّةً لكلّ طابور أو قرار.

    ثلاثةُ أسئلة: من يحمل الدورَ نشطاً، ومن رُصد غائباً اليوم، ومن أنابه المديرُ اليوم.
    """

    def __init__(self, school: School, today: date) -> None:
        self.school, self.today = school, today
        self._holders: dict[str, set[Any]] = {}
        self._absent: set[Any] | None = None
        self._delegates: set[Any] | None = None
        self._staff: set[Any] | None = None

    def holders(self, role: str) -> set[Any]:
        if role not in self._holders:
            self._holders[role] = _active_role_holders(self.school, role)
        return self._holders[role]

    def staff(self) -> set[Any]:
        if self._staff is None:
            self._staff = set(staff_members(self.school).values_list("pk", flat=True))
        return self._staff

    def absent(self) -> set[Any]:
        """المرصودون غائبين اليوم — للمراحل التي يُعرف صاحبُها بدوره."""
        if self._absent is None:
            self._absent = set(
                StaffAttendance.objects.filter(
                    school=self.school, date=self.today, status="absent"
                ).values_list("staff_id", flat=True)
            )
        return self._absent

    def delegates(self) -> set[Any]:
        """من أنابه المديرُ بنفسه لهذا اليوم (``DelegationService``) — ولا إنابةَ بغير قراره."""
        if self._delegates is None:
            named = set(
                PrincipalDelegation.objects.filter(school=self.school, date=self.today).values_list(
                    "delegate_id", flat=True
                )
            )
            self._delegates = named & self.holders(PRINCIPAL_DELEGATE)
        return self._delegates


# ══════════════════════════════════════════════════════════════════════
#  الأذونات (1.3) — نموذج 02
# ══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class PermitBalance:
    cap: int
    approved: int
    pending: int

    @property
    def remaining(self) -> int:
        return max(0, self.cap - self.approved)


#: النائبُ المسؤول لكلّ دورٍ في المنصّة — من «reports_to» في rbac_roles.json، ورقمُ
#: السطر سطرُ «title» المسمّى هناك. والمسمّياتُ الوزاريّةُ التي لا دورَ لها في المنصّة
#: («منسق الدعم الإضافي» :154، «منسق شؤون الطالب» :173) لا تظهر هنا. وما لا بطاقةَ
#: لمسمّاه (مرشدٌ أكاديميّ، محاسب، …) يرفع إلى المدير — ``deputy_role_for``.
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


def can_submit_permits(user: CustomUser) -> bool:
    """أيُقدَّم إذنُ هذا المستخدم في المنصّة؟ — كلُّ الكادر، والمديرُ منهم.

    سجلُّ الاستئذانات المدرسيّ (``07-نماذج المدرسة/07) سجل الاستئذانات.xlsx``، ورقة
    «تأخير - يناير») أوّلُ صفوفه مديرُ المدرسة (C3 «مدير مدرسة»، E3 «نوع الاذن»، E4
    «مدة الاذن»، Z4 مجموعُ الشهر) — فالمدرسةُ تتتبّع أذوناتِه في سقفها.
    """
    return _role_of(user) not in NON_STAFF_ROLES


def deputy_role_for(role: str) -> str:
    """دورُ «النائب المسؤول» لصاحب الدور — والمديرُ نفسُه لا نائبَ فوقه (فارغ).

    من «reports_to» حيث وُجدت بطاقتُه. وما لا بطاقةَ لمسمّاه — وسجلُّ الاستئذانات
    المدرسيّ (07-نماذج المدرسة/07) عمود المسمّى) يتتبّع أذوناتِ المرشد الأكاديميّ
    والمحاسب وأخصائيّ الأنشطة وغيرهم — فمسؤولُه مديرُ المدرسة: «رأس الهيكل الذي
    يتبعه كل الأدوار» (rbac_roles.json:18).
    """
    if role == PRINCIPAL:
        return ""
    return LINE_MANAGER.get(role, PRINCIPAL)


def direct_manager(school: School, staff: CustomUser) -> CustomUser | None:
    """«المسؤول المباشر» في نموذج 02 حين يكون غيرَ النائب: منسّقُ قسم المعلّم.

    ``DEPARTMENT_LED_ROLES`` وحدَها، ومنسّقُ القسم رأسُه (``Department.head``) نشطاً في
    المدرسة وغيرَ صاحب الطلب. ولمن سواهم فالمسؤولُ المباشرُ هو النائبُ المسؤولُ نفسُه —
    فيوقّع المربّعين معاً.
    """
    heads = (
        Membership.objects.filter(
            school=school,
            user=staff,
            is_active=True,
            role__name__in=DEPARTMENT_LED_ROLES,
            department_obj__is_active=True,
            department_obj__head__isnull=False,
        )
        .exclude(department_obj__head=staff)
        .order_by("department_obj__sort_order", "department_obj__name")
        .values_list("department_obj__head_id", flat=True)
    )
    active = staff_members(school)
    for head_id in heads:
        head = active.filter(pk=head_id).first()
        if head is not None:
            return head
    return None


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


def _check_timing(permit_type: str, day: date, start: time, now: datetime) -> None:
    """متى يُقدَّم الطلب.

    * شهرُه لم ينقضِ (البند 5.1، ``_check_open_month``).
    * الخروجُ المبكر والاستئذانُ قبل بدء نافذتهما: حاشيةُ نموذج 02 «يتعين على الموظف عدم
      الخروج إلا بعد اعتماده وإخطاره من قبل السكرتارية بالموافقة» (أصل PDF ص1، ومثله
      07_forms_catalog.md:13 «ولا يخرج الموظف فعلياً إلا بعد اعتماد مدير المدرسة») —
      فطلبٌ بعد الخروج طلبٌ بعد وقوعه.
    * والتأخيرُ الصباحيّ قد يُطلب بعد الصباح نفسِه: يُبلَّغ المسؤولُ لحظتَها بالبريد
      (البند 2.2، 06:32) ثمّ يُرفع الإذن (4.5، 06:60).
    """
    _check_open_month(day, now)
    if permit_type != "late_arrival" and (day, start) < (now.date(), now.time()):
        raise PolicyError(
            "الخروجُ والاستئذانُ يُطلبان قبل وقتهما — «يتعين على الموظف عدم الخروج إلا بعد "
            "اعتماده وإخطاره من قبل السكرتارية» (حاشية نموذج 02)."
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
        المعلَّقُ يُحسب مع المعتمد في فحص اليوم (4.3) والشهر (4.2). والمرحلةُ الأولى
        مربّعُ «المسؤول المباشر» إن كان للموظّف منسّقُ قسم، وإلّا «النائب المسؤول»؛
        وطلبُ المدير يبدأ بالسكرتارية، فلا مسؤولَ فوقه في المدرسة.
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
        _check_window(permit_type, start_time, end_time)
        _check_timing(permit_type, day, start_time, _now())
        CustomUser.objects.select_for_update().filter(pk=staff.pk).first()
        duration = minutes_between(start_time, end_time)
        PermitService._check_rules(
            school, staff, day, duration, open_statuses=("pending", "approved")
        )
        deputy_role = deputy_role_for(role)
        line_manager = direct_manager(school, staff) if deputy_role else None
        if not deputy_role:
            stage = "secretary"
        else:
            stage = "supervisor" if line_manager is not None else "deputy"
        permit = PermitRequest.objects.create(
            school=school,
            staff=staff,
            permit_type=permit_type,
            date=day,
            start_time=start_time,
            end_time=end_time,
            duration_minutes=duration,
            reason=reason.strip()[:500],
            stage=stage,
            deputy_role=deputy_role,
            line_manager=line_manager,
            created_by=staff,
            updated_by=staff,
        )
        _audit(staff, "create", permit, {"type": permit_type, "minutes": duration}, request)
        return permit

    # ── من يعمل في مرحلة الطلب ─────────────────────────────────────────

    @staticmethod
    def _principal_side(day: _StageDay, applicant: Any) -> set[Any]:
        """من يوقّع بصفة المدير: المديرُ نفسُه ومن أنابه اليوم بقراره.

        والإنابةُ «عن المدير في مهامه في حال غيابه» (03:401) قرارُه هو
        (``DelegationService``)، لا نقرةُ «غائب» في سجلٍّ يرصده غيرُه. فإن شغر منصبُه
        (لا مديرَ نشطاً) فالغيابُ ثابتٌ بلا قرار، وينوب نائبُ الشؤون الإدارية.
        """
        principals = day.holders(PRINCIPAL)
        side = (principals | day.delegates()) if principals else day.holders(PRINCIPAL_DELEGATE)
        return side - {applicant}

    @staticmethod
    def _available(day: _StageDay, role: str, applicant: Any) -> set[Any]:
        """حاملو الدور نشطين، غيرُ صاحب الطلب ولا المرصودين غائبين اليوم."""
        return day.holders(role) - day.absent() - {applicant}

    @staticmethod
    def _eligible(permit: PermitRequest, day: _StageDay) -> tuple[set[Any], str]:
        """(من يعمل الآن، الدورُ الذي تُنسب إليه المرحلة).

        لا يعلق طلبٌ بلا من يوقّعه: مربّعٌ شغر صاحبُه أو غاب اليومَ يرتفع إلى من فوقه —
        المسؤولُ المباشرُ إلى النائب المسؤول، والنائبُ والسكرتارية إلى المدير، فالمديرُ
        «رأس الهيكل الذي يتبعه كل الأدوار مباشرة أو عبر نائبيه» (rbac_roles.json:18).
        """
        applicant = permit.staff_id
        if permit.stage == "supervisor":
            manager = permit.line_manager_id
            if manager in day.staff() and manager not in day.absent() and manager != applicant:
                return {manager}, "line_manager"
            return PermitService._deputy_side(permit, day)
        if permit.stage == "deputy":
            return PermitService._deputy_side(permit, day)
        if permit.stage in ("secretary", "external"):
            secretaries = PermitService._available(day, "secretary", applicant)
            if secretaries:
                return secretaries, "secretary"
            if permit.is_principals_own:
                return day.holders(PRINCIPAL_DELEGATE) - {applicant}, "secretary"
            return PermitService._principal_side(day, applicant), "secretary"
        if permit.stage == "principal":
            return PermitService._principal_side(day, applicant), PRINCIPAL
        return set(), ""

    @staticmethod
    def _deputy_side(permit: PermitRequest, day: _StageDay) -> tuple[set[Any], str]:
        role = permit.deputy_role
        if role == PRINCIPAL:
            return PermitService._principal_side(day, permit.staff_id), PRINCIPAL
        deputies = PermitService._available(day, role, permit.staff_id)
        if deputies:
            return deputies, role
        return PermitService._principal_side(day, permit.staff_id), role

    @staticmethod
    def eligible_actors(permit: PermitRequest) -> list[CustomUser]:
        """من يعمل في مرحلة الطلب الآن — أشخاصاً."""
        ids, _role = PermitService._eligible(permit, _StageDay(permit.school, _now().date()))
        return list(CustomUser.objects.filter(pk__in=ids).order_by("full_name"))

    @staticmethod
    def _natural(permit: PermitRequest, actor: CustomUser, stage_role: str) -> bool:
        """أيعمل بصفته هو؟ — وإلّا فبالنيابة، ويُكتب ذلك في التدقيق."""
        if stage_role == "line_manager":
            return actor.pk == permit.line_manager_id
        return _role_of(actor) == stage_role

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
        """مربّعٌ واحدٌ من نموذج 02 — تحت قفل صفّ الموظّف فلا تتسابق مرحلتان.

        * المسؤولُ المباشر ثمّ النائبُ المسؤول: موافق/غير موافق، كلٌّ في عموده.
        * السكرتارية: تسجّل رصيدَ الساعات (المتبقّي قبل الطلب) واسمَها ووقتَها
          (07b:13)، ولا قرارَ لها في المصدر — فإن جاوز الطلبُ السقفَ (4.2) سُجّل
          رفضاً باسم البند لا بتقديرها.
        * «استخدام الإدارة» — مديرُ المدرسة: الاعتمادُ النهائيّ، ويُعاد فحصُ 4.3 و4.2
          و5.1 على المعتمَد، وبه وحدَه يُخصم الرصيد (4.1). وينوب عنه من أنابه.
        * إذنُ المدير نفسِه: اعتمادُه من رئيسه خارج المدرسة، والمصدرُ لا يسمّيه؛
          فالسكرتاريةُ التي تحفظ سجلَّ الاستئذانات تُثبت قرارَه بمرجعه (``external``).

        وبعد الاعتماد يُعاد تصنيفُ سجلّ حضور اليوم إن رُصد قبله.
        """
        CustomUser.objects.select_for_update().filter(pk=permit.staff_id).first()
        permit.refresh_from_db()
        if permit.status != "pending":
            raise PolicyError(f"الطلبُ «{permit.get_status_display()}» — لا يُراجَع ثانيةً.")
        if actor.pk == permit.staff_id:
            raise PolicyError("لا يعمل أحدٌ في طلبه هو (البند 4.1: الاعتمادُ من غيره).")
        now = _now()
        eligible, stage_role = PermitService._eligible(permit, _StageDay(permit.school, now.date()))
        if actor.pk not in eligible:
            raise PolicyError(f"الطلبُ بانتظار «{permit.get_stage_display()}» لا دورك.")
        on_behalf = "" if PermitService._natural(permit, actor, stage_role) else stage_role
        stage = permit.stage
        if stage == "external" and not reason.strip():
            raise PolicyError(
                "قرارُ رئيس المدير يُثبَت بمرجعه (بريدٌ أو كتابٌ وتاريخُه) — "
                "فالسكرتاريةُ تُوثّق ولا تقرّر (03:102)."
            )
        if stage == "secretary":
            approve, reason = PermitService._record_balance(permit, actor, now)
        if not approve:
            permit.status, permit.rejected_stage, permit.stage = "rejected", stage, "closed"
            permit.rejection_reason = reason.strip()[:300]
        elif stage == "supervisor":
            permit.supervisor_by, permit.supervisor_at, permit.stage = actor, now, "deputy"
        elif stage == "deputy":
            permit.deputy_by, permit.deputy_at, permit.stage = actor, now, "secretary"
        elif stage in ("principal", "external"):
            _check_open_month(permit.date, now)
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
        permit.stage = "external" if permit.is_principals_own else "principal"
        return True, ""

    @staticmethod
    def own_permits(school: School, staff: CustomUser) -> QuerySet[PermitRequest]:
        return PermitRequest.objects.filter(school=school, staff=staff).order_by(
            "-date", "-created_at"
        )[:50]

    @staticmethod
    def awaiting(school: School, user: CustomUser) -> list[PermitRequest]:
        """الطلباتُ المعلّقةُ في مرحلةٍ يعمل فيها هذا المستخدم الآن — لا طلبُه هو.

        يُحكم على كلّ طلبٍ بـ``_eligible`` نفسِها التي تحكم القرار، فلا يعرض الطابورُ ما
        يردّه الاعتماد، ولا يُخفي ما يقبله. والمعلَّقُ في مدرسةٍ عشراتٌ لا آلاف.
        """
        day = _StageDay(school, _now().date())
        pending = (
            PermitRequest.objects.filter(school=school, status="pending")
            .exclude(staff=user)
            .select_related("staff", "line_manager")
            .order_by("date", "created_at")
        )
        return [p for p in pending if user.pk in PermitService._eligible(p, day)[0]]

    @staticmethod
    def pending_one(school: School, pk: Any) -> PermitRequest:
        return PermitRequest.objects.select_related("staff", "school").get(school=school, pk=pk)


# ══════════════════════════════════════════════════════════════════════
#  الإنابةُ عن المدير — بقراره
# ══════════════════════════════════════════════════════════════════════


class DelegationService:
    """«الإنابة عن المدير في مهامه في حال غيابه» (03_job_descriptions_rbac.md:401).

    يُنيب المديرُ نائبَ الشؤون الإدارية ليومٍ بنفسه — فلا تنتقل صلاحيةُ الاعتماد النهائيّ
    برصدٍ يكتبه غيرُه، ولا ينفرد بها اثنان دونه. وأصلُ نموذج 02: «لا يعتبر الطلب
    معتمداً الا باعتماد مدير المدرسة وتوقيعه عليه» — فالتوقيعُ عنه بإذنه.
    """

    @staticmethod
    def is_principal(school: School, user: CustomUser) -> bool:
        return user.pk in _active_role_holders(school, PRINCIPAL)

    @staticmethod
    def today_for(school: School) -> PrincipalDelegation | None:
        return (
            PrincipalDelegation.objects.filter(school=school, date=_now().date())
            .select_related("delegate")
            .first()
        )

    @staticmethod
    def candidates(school: School) -> QuerySet[CustomUser]:
        return staff_members(school).filter(pk__in=_active_role_holders(school, PRINCIPAL_DELEGATE))

    @staticmethod
    @transaction.atomic
    def grant(
        *,
        school: School,
        principal: CustomUser,
        delegate: CustomUser,
        day: date | None = None,
        request: HttpRequest | None = None,
    ) -> PrincipalDelegation:
        day = day or _now().date()
        if principal.pk not in _active_role_holders(school, PRINCIPAL):
            raise PolicyError("لا يُنيب عن المدير إلّا المديرُ نفسُه (03:401).")
        if delegate.pk not in _active_role_holders(school, PRINCIPAL_DELEGATE):
            raise PolicyError("الإنابةُ لنائب المدير للشؤون الإدارية (03:401).")
        if day < _now().date():
            raise PolicyError("لا إنابةَ ليومٍ مضى.")
        delegation, created = PrincipalDelegation.objects.update_or_create(
            school=school,
            date=day,
            defaults={"delegate": delegate, "updated_by": principal},
            create_defaults={
                "delegate": delegate,
                "created_by": principal,
                "updated_by": principal,
            },
        )
        _audit(
            principal,
            "create" if created else "update",
            delegation,
            {"delegate": "vice_admin"},
            request,
        )
        return delegation

    @staticmethod
    @transaction.atomic
    def revoke(
        *, school: School, principal: CustomUser, request: HttpRequest | None = None
    ) -> None:
        if principal.pk not in _active_role_holders(school, PRINCIPAL):
            raise PolicyError("لا يرفع الإنابةَ إلّا المديرُ نفسُه.")
        delegation = DelegationService.today_for(school)
        if delegation is None:
            return
        _audit(principal, "delete", delegation, {"delegate": "vice_admin"}, request)
        delegation.delete()


# ══════════════════════════════════════════════════════════════════════
#  استثناءُ التأخير الصباحيّ أو الخروج المبكر — نموذج 03
# ══════════════════════════════════════════════════════════════════════


class ExceptionService:
    """نموذج 03 «نموذج طلب» الموجَّه إلى مدير المدرسة (07_forms_catalog.md:14، أصلُه ص1).

    استثناءٌ لأيّامٍ متتالية: تأخيرٌ صباحيٌّ إلى ساعةٍ، أو خروجٌ مبكرٌ من ساعة. يُرفق به
    «ما يثبت حاجة الموظف لذلك»، ويدوّن المديرُ «التغذية الراجعة» وتاريخَها. وليس إذناً
    من نموذج 02: فلا يدخل سقفَ السبع ساعات (4.2) ولا حدَّ المرّة (4.4) ولا «مرّةً في اليوم»
    (4.3) — تلك قيودُ الأذونات، وهذا قرارُ المدير نفسه باستثناءٍ موثَّق.
    """

    @staticmethod
    @transaction.atomic
    def submit(
        *,
        school: School,
        staff: CustomUser,
        exception_type: str,
        start_date: date,
        end_date: date,
        boundary: time,
        content: str,
        evidence: str,
        request: HttpRequest | None = None,
    ) -> AttendanceException:
        role = _role_of(staff)
        if role == PRINCIPAL:
            raise PolicyError("نموذج 03 موجَّهٌ إلى مدير المدرسة نفسِه — فلا يقدّمه.")
        if role in NON_STAFF_ROLES:
            raise PolicyError("نموذج 03 للموظّفين.")
        if exception_type not in {key for key, _label in EXCEPTION_TYPES}:
            raise PolicyError("الاستثناءُ للتأخير الصباحيّ أو الخروج المبكر (نموذج 03).")
        if not WORK_START < boundary < WORK_END:
            raise PolicyError("ساعةُ الاستثناء داخلَ الدوام الرسميّ 7:00–14:00 (البند 1.1).")
        if end_date < start_date:
            raise PolicyError("«إلى تاريخ» يجب ألّا تسبق «من تاريخ».")
        _check_open_month(start_date, _now())
        if not content.strip():
            raise PolicyError("محتوى الطلب مطلوب (نموذج 03).")
        if not evidence.strip():
            raise PolicyError(
                "«يجب ارفاق مع طلب استثناء الخروج المبكر أو التأخير الصباحي ما يثبت حاجة "
                "الموظف لذلك» (نموذج 03)."
            )
        exception = AttendanceException.objects.create(
            school=school,
            staff=staff,
            exception_type=exception_type,
            start_date=start_date,
            end_date=end_date,
            boundary_time=boundary,
            content=content.strip()[:1000],
            evidence=evidence.strip()[:300],
            created_by=staff,
            updated_by=staff,
        )
        _audit(staff, "create", exception, {"type": exception_type}, request)
        return exception

    @staticmethod
    @transaction.atomic
    def decide(
        exception: AttendanceException,
        *,
        actor: CustomUser,
        approve: bool,
        feedback: str = "",
        request: HttpRequest | None = None,
    ) -> AttendanceException:
        """«استخدام مدير المدرسة» — المديرُ وحدَه، والتغذيةُ الراجعة لازمةٌ للرفض."""
        exception.refresh_from_db()
        if exception.status != "pending":
            raise PolicyError(f"الطلبُ «{exception.get_status_display()}» — لا يُراجَع ثانيةً.")
        if actor.pk == exception.staff_id:
            raise PolicyError("لا يعمل أحدٌ في طلبه هو.")
        if actor.pk not in _active_role_holders(exception.school, PRINCIPAL):
            raise PolicyError("نموذج 03 يقرّره مديرُ المدرسة («استخدام مدير المدرسة»).")
        if not approve and not feedback.strip():
            raise PolicyError("التغذيةُ الراجعة مطلوبةٌ مع الرفض (نموذج 03).")
        now = _now()
        exception.status = "approved" if approve else "rejected"
        exception.feedback = feedback.strip()[:500]
        exception.reviewed_by, exception.reviewed_at, exception.updated_by = actor, now, actor
        exception.save()
        _audit(actor, "update", exception, {"status": exception.status}, request)
        if approve:
            first_open = max(exception.start_date, now.date().replace(day=1))
            last = min(exception.end_date, now.date())
            days = StaffAttendance.objects.filter(
                school=exception.school, staff_id=exception.staff_id, date__range=(first_open, last)
            ).values_list("date", flat=True)
            for day in days:
                StaffAttendanceService.reconcile(
                    exception.school,
                    exception.staff,
                    day,
                    actor=actor,
                    request=request,
                    cause="exception_approved",
                )
        return exception

    @staticmethod
    def own(school: School, staff: CustomUser) -> QuerySet[AttendanceException]:
        return AttendanceException.objects.filter(school=school, staff=staff).order_by(
            "-start_date", "-created_at"
        )[:20]

    @staticmethod
    def awaiting(school: School, user: CustomUser) -> QuerySet[AttendanceException]:
        if user.pk not in _active_role_holders(school, PRINCIPAL):
            return AttendanceException.objects.none()
        return (
            AttendanceException.objects.filter(school=school, status="pending")
            .exclude(staff=user)
            .select_related("staff")
            .order_by("start_date", "created_at")
        )

    @staticmethod
    def pending_one(school: School, pk: Any) -> AttendanceException:
        return AttendanceException.objects.select_related("staff", "school").get(
            school=school, pk=pk
        )

    @staticmethod
    def approved_on(school: School, staff: CustomUser, day: date) -> list[AttendanceException]:
        return list(
            AttendanceException.objects.filter(
                school=school,
                staff=staff,
                status="approved",
                start_date__lte=day,
                end_date__gte=day,
            )
        )


# ══════════════════════════════════════════════════════════════════════
#  الحضور (1.1)
# ══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class _DayCover:
    """ما يغطّي يومَ موظّفٍ معتمَداً: أذوناتُ نموذج 02 واستثناءاتُ نموذج 03."""

    permits: list[PermitRequest]
    exceptions: list[AttendanceException]

    def late_until(self) -> time | None:
        ends = [p.end_time for p in self.permits if p.permit_type == "late_arrival"]
        ends += [e.boundary_time for e in self.exceptions if e.exception_type == "late_arrival"]
        return max(ends) if ends else None

    def leave_windows(self) -> list[tuple[time, time]]:
        windows = [
            (p.start_time, p.end_time) for p in self.permits if p.permit_type != "late_arrival"
        ]
        windows += [
            (e.boundary_time, WORK_END)
            for e in self.exceptions
            if e.exception_type == "early_departure"
        ]
        return windows


class StaffAttendanceService:
    @staticmethod
    def _cover(school: School, staff: CustomUser, day: date) -> _DayCover:
        permits = list(
            PermitRequest.objects.filter(school=school, staff=staff, date=day, status="approved")
        )
        return _DayCover(permits, ExceptionService.approved_on(school, staff, day))

    @staticmethod
    def _derive(
        cover: _DayCover,
        check_in: time | None,
        check_out: time | None,
        excused: bool,
    ) -> dict[str, Any]:
        """ما يُحسب من الأوقات وما يغطّي اليوم: التصنيفُ والدقائق.

        ويومُ الغياب لا دقائقَ انصرافٍ مبكرٍ فيه: اليومُ كلُّه يُعدّ غياباً في التقرير
        (البند 5.1)، فلا يُعدّ نقصُ آخره مرّةً ثانية.
        """
        until = cover.late_until()
        derived: dict[str, Any] = {
            "status": None,
            "late_minutes": 0,
            "permit_minutes": sum(p.duration_minutes for p in cover.permits),
            "early_leave_minutes": 0,
            "excuse_used": False,
        }
        if check_in is not None:
            derived["status"], derived["late_minutes"] = classify_arrival(check_in, until, excused)
            derived["excuse_used"] = excused and classify_arrival(check_in, until)[0] == "absent"
        if check_out is not None and derived["status"] != "absent":
            derived["early_leave_minutes"] = early_leave_minutes(check_out, cover.leave_windows())
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
        cause: str = "permit_approved",
    ) -> StaffAttendance | None:
        """يُعيد حسابَ سجلّ اليوم من أوقاته المرصودة وما يغطّيه معتمَداً الآن.

        يُستدعى باعتماد إذنٍ أو استثناء: فمن رُصد متأخّراً 8:15 ثمّ اعتُمد له تأخيرٌ إلى
        8:30 صار مستأذناً بلا دقائق تأخّر — لا متأخّراً ومستأذناً معاً. ومن لم يُكتب له
        وقتُ حضور (غائبٌ لم يحضر) تبقى حالتُه، وتتبدّل دقائقُ إذنه وحدَها.
        """
        record = (
            StaffAttendance.objects.select_for_update()
            .filter(school=school, staff=staff, date=day)
            .first()
        )
        if record is None:
            return None
        cover = StaffAttendanceService._cover(school, staff, day)
        derived = StaffAttendanceService._derive(
            cover, record.check_in, record.check_out, bool(record.accepted_excuse)
        )
        status = derived["status"] or record.status
        values = {
            "status": status,
            "late_minutes": derived["late_minutes"],
            "permit_minutes": derived["permit_minutes"],
            "early_leave_minutes": derived["early_leave_minutes"] if status != "absent" else 0,
            "absence_type": record.absence_type if status == "absent" else "",
            "accepted_excuse": record.accepted_excuse if derived["excuse_used"] else "",
        }
        before = {key: getattr(record, key) for key in values}
        changes = StaffAttendanceService._changes(before, values)
        if not changes:
            return record
        for key, value in values.items():
            setattr(record, key, value)
        record.updated_by = actor
        record.save()
        _audit(actor, "update", record, {**changes, "cause": cause}, request)
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
        * ``check_out`` وقتُ الانصراف، وما بينه وبين 14:00 بلا إذنٍ يُعدّ (1.1) — إلّا في
          يوم الغياب.

        وتكرارُ الرصد نفسِه لا يغيّر شيئاً ولا يترك أثراً ثانياً، والتعديلُ يُدقَّق بكلّ
        ما تغيّر وقيمتِه قبل.
        """
        if status not in STATUSES:
            raise PolicyError("حالةٌ غيرُ معروفة.")
        if day > _now().date():
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
            StaffAttendanceService._cover(school, staff, day), check_in, check_out, bool(excuse)
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
                # يومُ الغياب يُعدّ غياباً وحدَه (``_derive``) — والشرطُ هنا حارسٌ ثانٍ.
                early_total=Sum("early_leave_minutes", filter=~Q(status="absent")),
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

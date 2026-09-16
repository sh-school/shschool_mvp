"""حضورُ الموظّفين والأذوناتُ القصيرة — القواعدُ والخدمة.

المرجعُ الحاكمُ لكلّ قاعدةٍ هنا: ``docs/compliance/staff_attendance_spec.md`` (م-1 … م-36)،
وأرقامُ «م» في التعليقات أرقامُ بنوده، وأسماءُ الرموز فيه لا أرقامُ الأسطر (ز-8).
ووراءه الأصولُ نفسُها:

* «السياسة»: ``data/2026-2027/05-السياسات الداخلية/01-2027 سياسة وضوابط الحضور
  والانصراف.pdf`` (ت/د 01/2027 بتاريخ 2026-08-23، صفحتان) — بنودُها 1.1 و2.1 و2.4
  و3.4–3.7 و4.1–4.6 و5.1–5.3.
* «ن02»: ``data/2026-2027/07-نماذج المدرسة/02) نموذج طلب تأخير - استئذان - خروج
  مبكر.pdf`` ص1 — مربّعاتُه بترتيب الورقة: بيانات الموظّف، ثمّ «استخدام السكرتارية»
  (رصيد الساعات، الاسم، توقيت تقديم)، ثمّ «استخدام المسؤول المباشر والنائب المسؤول»
  عمودين، ثمّ «استخدام الإدارة»، ثمّ «مدير المدرسة». وحاشيتُه بنصّها في ``_check_timing``.
* «ن03»: ``07-نماذج المدرسة/03) نموذج طلب.pdf`` ص1 — خطابٌ حرٌّ إلى مدير المدرسة،
  «يجب ارفاق مع طلب استثناء الخروج المبكر أو التأخير الصباحي ما يثبت حاجة الموظف
  لذلك»، و«استخدام مدير المدرسة: التغذية الراجعة … تاريخ التغذية الراجعة».
* «البطاقات»: ``02- شؤون الموظفين/05- الوصف الوظيفي/*.pdf`` — «المسؤول المباشر» في
  ترويسة كلّ بطاقة، ومنه جدولُ م-21 (``LINE_MANAGER``). وبطاقةُ نائب الشؤون الإدارية
  وحدَها فيها «الإنابة عن المدير في مهامه في حال غيابه» (م-24).
* ``AAdocs/ministry_data/2026_2027/rbac_roles.json`` — «reports_to» لكلّ مسمّى، ويوافق
  جدولَ البطاقات.

الفلسفة: **يحسب ولا ينفّذ آليّاً** — تُصنَّف الحالةُ وتُعدّ الدقائق، ولا خصمَ ولا
جزاءَ يُطلقه النظام؛ الخصمُ (البند 5) قرارٌ إداريٌّ على التقرير الشهريّ.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import UUID

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

#: م-1 (السياسة 1.1) — بدايةُ الدوام، وما بعدها تأخّر (م-3).
WORK_START = time(7, 0)
#: م-1 (السياسة 1.1) — «وينتهي في تمام الثانية ظهراً».
WORK_END = time(14, 0)
#: م-4 (السياسة 2.4) — ما بعدها غيابٌ بلا تغطيةٍ سارية ولا عذرٍ مقبول.
ABSENT_AFTER = time(9, 0)
#: م-15 (السياسة 3.4 و4.2) — سبعُ ساعاتٍ في الشهر.
MONTHLY_PERMIT_CAP = 7 * 60
#: م-13 (السياسة 3.6 و4.4) — ساعتان للمرّة، و120 مقبولة.
PERMIT_MAX_MINUTES = 2 * 60
#: م-35 (السياسة 5.3) — «تغطية أيام غيابه قبل يوم (15) من الشهر»: المهلةُ تنتهي بنهاية
#: اليوم الرابع عشر من الشهر التالي، وما بعدها يُسجَّل ويُوسم لا يُمنع.
COVERAGE_DEADLINE_DAY = 14

#: أيّامُ الدوام الأسبوعيّ: الأحد–الخميس، كما في الجدول المدرسيّ نفسِه (خمسةُ أيّامٍ
#: بأسمائها في مولّد الجدول) — ومنها تُعدّ أيّامُ الاستثناء في التقرير (م-33).
SCHOOL_WEEKDAYS = frozenset({6, 0, 1, 2, 3})  # ``date.weekday()``: الأحد 6 … الخميس 3

STATUSES = ("present", "late", "absent", "permitted")
STATUS_LABELS = {"present": "حاضر", "late": "متأخّر", "absent": "غائب", "permitted": "مستأذن"}
#: حالاتُ من حضر — لا تُرصد إلّا بوقت حضوره، فبه تُحسب دقائقُ التأخّر (م-3 وم-6).
ARRIVAL_STATUSES = ("present", "late", "permitted")
ABSENCE_TYPE_KEYS = tuple(key for key, _label in ABSENCE_TYPES)
NON_STAFF_ROLES = ("student", "parent")
#: م-18ب — نوعان يُقدَّمان قبل وقت بدئهما، وما لم يُعتمد قبله يصير «منتهياً».
LEAVING_PERMIT_TYPES = ("during_day", "early_departure")

#: rbac_roles.json، «مدير المدرسة»: «reports_to» فارغ — لا مسؤولَ له داخل المدرسة (م-23).
PRINCIPAL = "principal"
#: م-24 — بطاقةُ نائب المدير للشؤون الإدارية وشؤون الطلاب (1034) وحدَها فيها «الإنابة عن
#: المدير في مهامه في حال غيابه»؛ وبطاقةُ النائب الأكاديميّ (1033) بلا بندِ إنابة.
PRINCIPAL_DELEGATE = "vice_admin"
#: من يقرأ تقريرَ الحضور للمدرسة كلّها (خارج المواصفة — قرارُ صلاحيّات).
REPORT_WHOLE_SCHOOL = frozenset({PRINCIPAL, "secretary"})


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


def _minute(moment: time) -> time:
    """م-2: المقارنةُ بالدقيقة الكاملة — تُهمل الثواني، فـ07:00:59 سابعةٌ تماماً."""
    return moment.replace(second=0, microsecond=0)


def classify_arrival(
    check_in: time, covered_until: time | None = None, excused: bool = False
) -> tuple[str, int]:
    """(الحالة، دقائقُ التأخّر) لوقت حضورٍ — م-3 وم-4 وم-5 وم-6.

    ``covered_until`` نهايةُ ما يغطّي الصباح معتمَداً: إذنُ تأخيرٍ من نموذج 02 (نافذتُه
    من 7:00، م-13) أو استثناءُ نموذج 03. والتغطيةُ تغطّي نافذتَها وحدَها لا اليومَ كلَّه
    (م-5): من حضر فيها «مستأذن»، ومن جاوزها حتّى التاسعة «متأخّر» بدقائقه من نهايتها
    (م-6)، ومن جاوزها وجاوز التاسعة «غائب» إلّا أن يُقبل عذرُه (``excused``، م-7).
    """
    check_in = _minute(check_in)
    if check_in <= WORK_START:
        return "present", 0
    if covered_until is not None and check_in <= _minute(covered_until):
        return "permitted", 0
    counted_from = max(WORK_START, covered_until or WORK_START)
    if check_in <= ABSENT_AFTER or excused:
        return "late", minutes_between(counted_from, check_in)
    return "absent", 0


def early_leave_minutes(check_out: time, windows: Iterable[tuple[time, time]] = ()) -> int:
    """م-8: دقائقُ الخروج المبكر — من الانصراف إلى أقرب اللحظتين: 14:00 أو بدءِ التغطية.

    ``windows`` نوافذُ اليوم المعتمدة (خروجٌ مبكر أو استئذانٌ من نموذج 02، أو استثناءُ
    خروجٍ من نموذج 03). وبالتناظر مع م-6: لا تُحسب إلّا نافذةٌ لم تنقضِ قبل الانصراف،
    ومن انصرف داخل نافذته فلا دقائقَ عليه. والحسابُ اختيارٌ هندسيٌّ مؤقّت (المصدر صامت).
    """
    check_out = _minute(check_out)
    ahead = [_minute(start) for start, end in windows if _minute(end) > check_out]
    bound = min([WORK_END, *ahead])
    return minutes_between(check_out, bound)


def month_bounds(day: date) -> tuple[date, date]:
    last = calendar.monthrange(day.year, day.month)[1]
    return day.replace(day=1), day.replace(day=last)


def coverage_deadline(day: date) -> date:
    """م-35: آخرُ يومٍ تُقبل فيه تغطيةُ غياب ``day`` بلا وسم — الرابعَ عشرَ من الشهر التالي."""
    first, last = month_bounds(day)
    return (last + timedelta(days=1)).replace(day=COVERAGE_DEADLINE_DAY)


def _check_submission_window(day: date, now: datetime) -> None:
    """م-18أ: تاريخُ إذن التأخير الصباحيّ — الشهرُ الجاري، أو السابقُ ما لم يتجاوز اليومُ 14.

    فالبند 5.1 يُشعر بتقرير الشهر السابق «بداية كل شهر»، و5.3 يمهل التغطية «قبل يوم
    (15) من الشهر» — فما قبل ذلك كلَّه باب التسوية، وما بعده أُغلق تقريرُه.
    """
    first_of_month = now.date().replace(day=1)
    if day >= first_of_month:
        return
    if now.day <= COVERAGE_DEADLINE_DAY and day >= (first_of_month - timedelta(days=1)).replace(
        day=1
    ):
        return
    raise PolicyError(
        f"شهرُ {day:%Y-%m} أُغلق: التقريرُ يُشعَر به بداية الشهر التالي (البند 5.1) "
        f"والتغطيةُ قبل يوم 15 منه (البند 5.3) — فلا إذنَ يُقدَّم له الآن."
    )


def _plain(value: Any) -> Any:
    """قيمةٌ تُكتب في سجلّ التدقيق (JSON): الوقتُ «HH:MM» والتاريخُ «YYYY-MM-DD»."""
    if isinstance(value, time):
        return f"{value:%H:%M}"
    if isinstance(value, datetime):  # قبل ``date``: فـdatetime صنفٌ منه
        return f"{value:%Y-%m-%d %H:%M}"
    if isinstance(value, date):
        return f"{value:%Y-%m-%d}"
    if isinstance(value, UUID):
        return str(value)
    return value


#: حقولٌ لا يُكتب نصُّها في سجلّ التدقيق الثابت: العذرُ المقبول قد يحمل بيانةً صحّيّةً
#: (فئةٌ خاصّة — PDPPL م.16)، وسجلُّ التدقيق «يُحفظ كلُّه» ولا يُحذف (م.19). فيُسجَّل أنّ
#: عذراً قُبل ومن قبِله، ونصُّه في سجلّ اليوم وحدَه حيث يُمحى بمحوه.
_REDACTED_FIELDS = ("accepted_excuse",)


def _audited(key: str, value: Any) -> Any:
    return bool(value) if key in _REDACTED_FIELDS else _plain(value)


def _audit(
    actor: CustomUser | None,
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
    """من يحضر مراحلَ الاعتماد في مدرسةٍ في لحظةٍ — يُقرأ مرّةً لكلّ طابور أو قرار.

    أسئلتُه ثلاثة: من يحمل الدورَ نشطاً، ومن رُصد غائباً اليوم (غائباً أو في إجازة —
    م-25 وم-28)، ومن أنابه المديرُ بقرارٍ صريح. ونافذةُ إذنٍ أو استثناءٍ ليست غياباً
    مرصوداً، فلا تُقيم إنابةً (م-25).
    """

    def __init__(self, school: School, now: datetime) -> None:
        self.school, self.now = school, now
        self.today = now.date()
        self._holders: dict[str, set[Any]] = {}
        self._absent: set[Any] | None = None
        self._delegates: set[Any] | None = None

    def holders(self, role: str) -> set[Any]:
        if role not in self._holders:
            self._holders[role] = _active_role_holders(self.school, role)
        return self._holders[role]

    def absent(self) -> set[Any]:
        """المرصودون غائبين اليوم — وفيهم من في إجازة (يومُ غيابٍ بنوعه من سجلّ الغياب).

        منه تقوم الإنابةُ عن المدير (م-25) ويُرفع مربّعٌ غاب صاحبُه (م-28).
        """
        if self._absent is None:
            self._absent = set(
                StaffAttendance.objects.filter(
                    school=self.school, date=self.today, status="absent"
                ).values_list("staff_id", flat=True)
            )
        return self._absent

    def delegates(self) -> set[Any]:
        """من أنابه المديرُ بقرارٍ صريحٍ لهذا اليوم — ويبقى مقبولاً مع الإنابة التلقائيّة (م-25)."""
        if self._delegates is None:
            named = set(
                PrincipalDelegation.objects.filter(school=self.school, date=self.today).values_list(
                    "delegate_id", flat=True
                )
            )
            self._delegates = named & self.holders(PRINCIPAL_DELEGATE)
        return self._delegates


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


#: م-21 — «المسؤول المباشر» في ترويسة كلّ بطاقةِ وصفٍ وظيفيّ، ويوافقه «reports_to» في
#: rbac_roles.json (ورقمُ السطر سطرُ «title» هناك). والمسؤولُ المباشرُ هو النائبُ
#: المسؤولُ نفسُه في كلّ الفئات، فيوقّع المربّعين بتوقيعٍ واحد (م-19). وما لا بطاقةَ
#: لمسمّاه يرفع إلى المدير (م-22، ``deputy_role_for``).
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


def _check_window(permit_type: str, start: time, end: time) -> None:
    """م-1 وم-12 وم-13: نافذةُ الإذن داخلَ الدوام وعلى قدر نوعه.

    التأخيرُ الصباحيّ يبدأ من 7:00 لأنّ التأخّرَ يُعدّ من بعدها (م-3)، والخروجُ المبكر
    ينتهي بنهاية الدوام 14:00، والاستئذانُ أثناء الدوام بينهما.
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
    """م-18أ وم-18ب وم-11: متى يُقدَّم الطلب.

    حاشيةُ ن02 بنصّها (أصل PDF ص1، وdocx النموذج): «في حال تقديم الطلب فإنه يتعين على
    الموظف عدم الخروج إلا بعد اعتماده وإخطاره من قبل السكرتارية بالموافقة على طلب
    الاجازة.» و«لا يعتبر الطلب معتمداً الا باعتماد مدير المدرسة وتوقيعه عليه.» —
    فالخروجُ والاستئذانُ يُطلبان قبل وقت بدئهما.

    والتأخيرُ الصباحيّ يُطلب قبل وقوعه أو بعده (م-18أ): يُبلَّغ المسؤولُ لحظتَها بالبريد
    (البند 2.2) ثمّ يُرفع الإذن (4.5) — وتُقبل المنصّةُ طلبَ الغد في أيّ ساعة (م-11).
    """
    if permit_type == "late_arrival":
        _check_submission_window(day, now)
        return
    if (day, _minute(start)) <= (now.date(), _minute(now.time())):
        raise PolicyError(
            "الخروجُ والاستئذانُ يُطلبان قبل وقت بدئهما — «يتعين على الموظف عدم الخروج "
            "إلا بعد اعتماده وإخطاره من قبل السكرتارية بالموافقة» (حاشية نموذج 02)."
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
    def _overdue(permit: PermitRequest, now: datetime) -> bool:
        return permit.permit_type in LEAVING_PERMIT_TYPES and (permit.date, permit.start_time) <= (
            now.date(),
            now.time(),
        )

    @staticmethod
    def _expire(permit: PermitRequest, request: HttpRequest | None = None) -> PermitRequest:
        """م-18ب: طلبُ خروجٍ أو استئذانٍ مضى وقتُ بدئه ولم يُعتمد — «منتهٍ» بلا أثرٍ في الرصيد."""
        stage = permit.stage
        permit.status, permit.stage = "expired", "closed"
        permit.save(update_fields=["status", "stage", "updated_at"])
        _audit(
            None,
            "update",
            permit,
            {"stage": stage, "status": "expired", "cause": "not_approved_before_start"},
            request,
        )
        return permit

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
        now = now or _now()
        qs = PermitRequest.objects.filter(
            school=school, status="pending", permit_type__in=LEAVING_PERMIT_TYPES
        ).filter(Q(date__lt=now.date()) | Q(date=now.date(), start_time__lte=now.time()))
        if staff is not None:
            qs = qs.filter(staff=staff)
        expired = 0
        for permit in qs.select_related("school"):
            PermitService._expire(permit, request)
            expired += 1
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
        now = _now()
        _check_window(permit_type, start_time, end_time)
        _check_timing(permit_type, day, start_time, now)
        CustomUser.objects.select_for_update().filter(pk=staff.pk).first()
        PermitService.expire_due(school, now, staff, request)
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
            stage="secretary",
            deputy_role=deputy_role_for(role),
            created_by=staff,
            updated_by=staff,
        )
        _audit(staff, "create", permit, {"type": permit_type, "minutes": duration}, request)
        return permit

    # ── من يعمل في مرحلة الطلب ─────────────────────────────────────────

    @staticmethod
    def _principal_side(day: _StageDay, applicant: Any) -> set[Any]:
        """م-24 وم-25 وم-26 وم-27: من يعمل بصفة المدير الآن.

        المديرُ نفسُه أوّلاً، ومعه نائبُ الشؤون الإدارية (1034) وحدَه إذا قامت الإنابة:
        شغرَ المنصبُ (م-26)، أو رُصد المديرُ اليومَ غائباً أو في إجازة (م-25). ونافذةُ
        إذنه ليست غياباً مرصوداً. والإنابةُ الصريحةُ (``DelegationService``) مقبولةٌ ولو
        كان حاضراً. والنائبُ المرصودُ غائباً لا ينوب — فإن غابا معاً بقي الطلبُ معلّقاً،
        ولا يرتفع إلى النائب الأكاديميّ (م-27).
        """
        principals = day.holders(PRINCIPAL)
        deputies = day.holders(PRINCIPAL_DELEGATE) - day.absent()
        if not (principals - day.absent()):
            side = principals | deputies
        else:
            side = principals | (day.delegates() - day.absent())
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
        ids, _role = PermitService._eligible(permit, _StageDay(permit.school, _now()))
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
        CustomUser.objects.select_for_update().filter(pk=permit.staff_id).first()
        permit.refresh_from_db()
        if permit.status != "pending":
            raise PolicyError(f"الطلبُ «{permit.get_status_display()}» — لا يُراجَع ثانيةً.")
        now = _now()
        if PermitService._overdue(permit, now):
            return PermitService._expire(permit, request)
        if actor.pk == permit.staff_id:
            raise PolicyError("لا يعمل أحدٌ في طلبه هو (البند 4.1: الاعتمادُ من غيره).")
        eligible, stage_role = PermitService._eligible(permit, _StageDay(permit.school, now))
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
        elif stage == "supervisor":
            PermitService._sign(permit, stage, actor, now)
            permit.stage = "principal"
        elif stage in ("principal", "external"):
            PermitService._check_rules(
                permit.school,
                permit.staff,
                permit.date,
                permit.duration_minutes,
                open_statuses=("approved",),
                exclude_pk=permit.pk,
            )
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
        # النائبُ الإداريّ يوقّع مربّعَ مسؤوله ثمّ يعتمد بالإنابة (م-21 وم-24): المواصفةُ
        # لا تمنعه، فيُقبل ويُكتب في التدقيق أنّ التوقيعين من يدٍ واحدة.
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

    @staticmethod
    @transaction.atomic
    def cancel(
        permit: PermitRequest, *, actor: CustomUser, request: HttpRequest | None = None
    ) -> PermitRequest:
        """م-20: يلغي صاحبُ الطلب طلبَه المعلَّق، أو إذنَه المعتمدَ قبل بدء نافذته.

        فيُفرج عن يومه (م-14) ويُستردّ رصيدُه (م-10)، ويبقى الصفُّ بحالة «ملغى» وقيدُه في
        التدقيق — لا يُحذف طلبٌ ولا قرار.
        """
        CustomUser.objects.select_for_update().filter(pk=permit.staff_id).first()
        permit.refresh_from_db()
        if actor.pk != permit.staff_id:
            raise PolicyError("لا يلغي الطلبَ إلّا صاحبُه.")
        now = _now()
        was = permit.status
        if was == "approved":
            if (permit.date, permit.start_time) <= (now.date(), _minute(now.time())):
                raise PolicyError(
                    "الإذنُ المعتمد يُلغى قبل بدء نافذته وحدَه — وما بدأ يبقى محسوباً (م-20)."
                )
        elif was != "pending":
            raise PolicyError(f"الطلبُ «{permit.get_status_display()}» — لا يُلغى.")
        elif PermitService._overdue(permit, now):
            return PermitService._expire(permit, request)
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
            permit.stage = "supervisor"

    @staticmethod
    def own_permits(school: School, staff: CustomUser) -> list[PermitRequest]:
        """طلباتُ الموظّف — بعد كنس ما انتهى وقتُه (م-18ب)، وكلٌّ معلَّمٌ بما يُلغى (م-20)."""
        now = _now()
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
        now = _now()
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


# ══════════════════════════════════════════════════════════════════════
#  الإنابةُ الصريحة عن المدير — م-25
# ══════════════════════════════════════════════════════════════════════


class DelegationService:
    """إنابةٌ صريحةٌ يكتبها المديرُ ليومٍ — وتبقى مقبولةً مع الإنابة التلقائيّة (م-25).

    البطاقةُ (1034) تجعل الإنابةَ بحكم الوظيفة «في حال غيابه» ولا تشترط قراراً، فغيابُه
    المرصودُ في رصد اليوم يكفي (``_principal_side``). والسجلُّ الصريحُ أثرٌ للتدقيق لا
    شرطٌ لقيام الإنابة؛ وهذه الشاشةُ لمن أراد أن يُنيب وهو حاضر، أو أن يُعلنها قبل غيابه.
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
            raise PolicyError(
                "السجلُّ الصريحُ للإنابة يكتبه مديرُ المدرسة (م-25)؛ والإنابةُ في غيابه قائمةٌ "
                "بنصّ بطاقة نائب الشؤون الإدارية: «الإنابة عن المدير في مهامه في حال غيابه»."
            )
        if delegate.pk not in _active_role_holders(school, PRINCIPAL_DELEGATE):
            raise PolicyError("الإنابةُ لنائب المدير للشؤون الإدارية وحدَه (م-24).")
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
#  استثناءُ التأخير الصباحيّ أو الخروج المبكر — نموذج 03 (م-29 وم-31)
# ══════════════════════════════════════════════════════════════════════


class ExceptionService:
    """نموذج 03 «نموذج طلب» (م-29): خطابٌ حرٌّ موجَّهٌ إلى مدير المدرسة، يقرّره هو أو من
    ينوب عنه (م-30 وم-24) في مرحلةٍ واحدة.

    ونطاقُ هذه الموجة (م-31) طلبُ «استثناء التأخير الصباحيّ أو الخروج المبكر» وحدَه:
    النوع، ومن تاريخ إلى تاريخ، وساعةُ الحدّ، والمرفقُ الإلزاميّ — «يجب ارفاق مع طلب
    استثناء الخروج المبكر أو التأخير الصباحي ما يثبت حاجة الموظف لذلك». ولا يُشترط
    التكرار. والطلباتُ الحرّةُ الأخرى في النموذج فجوةٌ معروفة. وليس إذناً من نموذج 02:
    فلا يدخل سقفَ السبع ساعات (م-33) ولا حدَّ الساعتين ولا «مرّةً في اليوم».
    """

    #: المرفقُ صورةٌ أو PDF — وقد يكون تقريراً طبيّاً، فلا يُقبل ما يُنفَّذ في المتصفّح.
    EVIDENCE_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg")
    EVIDENCE_MAX_BYTES = 5 * 1024 * 1024

    @staticmethod
    def _check_evidence(evidence_file: Any) -> None:
        if not evidence_file:
            raise PolicyError(
                "«يجب ارفاق مع طلب استثناء الخروج المبكر أو التأخير الصباحي ما يثبت حاجة "
                "الموظف لذلك» (نموذج 03، م-31) — أرفق الملفّ."
            )
        name = str(getattr(evidence_file, "name", "")).lower()
        if not name.endswith(ExceptionService.EVIDENCE_EXTENSIONS):
            raise PolicyError("المرفقُ ملفُّ PDF أو صورة (PNG/JPG).")
        if (getattr(evidence_file, "size", 0) or 0) > ExceptionService.EVIDENCE_MAX_BYTES:
            raise PolicyError("المرفقُ أكبرُ من 5 ميغابايت.")

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
        evidence_file: Any,
        evidence: str = "",
        request: HttpRequest | None = None,
    ) -> AttendanceException:
        role = _role_of(staff)
        if role == PRINCIPAL:
            raise PolicyError("نموذج 03 موجَّهٌ إلى مدير المدرسة نفسِه — فلا يقدّمه (م-34).")
        if role in NON_STAFF_ROLES:
            raise PolicyError("نموذج 03 للموظّفين.")
        if exception_type not in {key for key, _label in EXCEPTION_TYPES}:
            raise PolicyError("الاستثناءُ للتأخير الصباحيّ أو الخروج المبكر (نموذج 03، م-31).")
        if not WORK_START < boundary < WORK_END:
            raise PolicyError("ساعةُ الاستثناء داخلَ الدوام الرسميّ 7:00–14:00 (البند 1.1).")
        if end_date < start_date:
            raise PolicyError("«إلى تاريخ» يجب ألّا تسبق «من تاريخ».")
        if not content.strip():
            raise PolicyError("محتوى الطلب مطلوب («استخدام الموظف»، نموذج 03).")
        ExceptionService._check_evidence(evidence_file)
        exception = AttendanceException.objects.create(
            school=school,
            staff=staff,
            exception_type=exception_type,
            start_date=start_date,
            end_date=end_date,
            boundary_time=boundary,
            content=content.strip()[:1000],
            evidence=evidence.strip()[:300],
            evidence_file=evidence_file,
            created_by=staff,
            updated_by=staff,
        )
        _audit(staff, "create", exception, {"type": exception_type, "evidence": True}, request)
        return exception

    @staticmethod
    def _deciders(school: School, applicant: Any) -> set[Any]:
        """م-30 وم-24 وم-25: المديرُ، ونائبُ الشؤون الإدارية حين تقوم الإنابة."""
        return PermitService._principal_side(_StageDay(school, _now()), applicant)

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
        """«استخدام مدير المدرسة» (م-30): المديرُ أو من ينوب عنه، والتغذيةُ الراجعة لازمة.

        وحالةُ «معتمد / مرفوض» المرافقةُ للتغذية اختيارٌ هندسيٌّ مؤقّت. والقرارُ بالإنابة
        يُوسم (``decided_on_behalf``) مع اسم النائب في ``reviewed_by`` (م-25).
        """
        exception.refresh_from_db()
        if exception.status != "pending":
            raise PolicyError(f"الطلبُ «{exception.get_status_display()}» — لا يُراجَع ثانيةً.")
        if actor.pk == exception.staff_id:
            raise PolicyError("لا يعمل أحدٌ في طلبه هو.")
        if actor.pk not in ExceptionService._deciders(exception.school, exception.staff_id):
            raise PolicyError(
                "نموذج 03 يقرّره مديرُ المدرسة («استخدام مدير المدرسة»)، أو نائبُ الشؤون "
                "الإدارية في غيابه (م-30 وم-24)."
            )
        if not feedback.strip():
            raise PolicyError("التغذيةُ الراجعة مطلوبةٌ مع القرار (نموذج 03، م-30).")
        now = _now()
        on_behalf = _role_of(actor) != PRINCIPAL
        exception.status = "approved" if approve else "rejected"
        exception.feedback = feedback.strip()[:500]
        exception.reviewed_by, exception.reviewed_at, exception.updated_by = actor, now, actor
        exception.decided_on_behalf = on_behalf
        exception.save()
        changes: dict[str, Any] = {"status": exception.status}
        if on_behalf:
            changes["on_behalf_of"] = PRINCIPAL
        _audit(actor, "update", exception, changes, request)
        if approve:
            # م-32: عند الاعتماد تُعاد مطابقةُ أيّامه. وم-35: التغطيةُ بعد المهلة لا تُمنع —
            # تُعاد أيّامُ المدّة كلُّها وتُوسم في التقرير.
            last = min(exception.end_date, now.date())
            days = StaffAttendance.objects.filter(
                school=exception.school,
                staff_id=exception.staff_id,
                date__range=(exception.start_date, last),
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
    def awaiting(school: School, user: CustomUser) -> list[AttendanceException]:
        """طلباتُ نموذج 03 المعلّقة لمن يقرّرها الآن — المديرُ أو نائبُه في غيابه (م-30)."""
        deciders = _StageDay(school, _now())
        pending = (
            AttendanceException.objects.filter(school=school, status="pending")
            .exclude(staff=user)
            .select_related("staff")
            .order_by("start_date", "created_at")
        )
        return [
            e for e in pending if user.pk in PermitService._principal_side(deciders, e.staff_id)
        ]

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
#  الحضور — م-1 … م-7
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

        ويومُ الغياب لا دقائقَ انصرافٍ مبكرٍ فيه (م-9): اليومُ كلُّه يُعدّ غياباً في
        التقرير، فلا يُعدّ نقصُ آخره مرّةً ثانية.
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
    def _covered_at(
        record: StaffAttendance,
        values: dict[str, Any],
        check_in: time | None,
        now: datetime,
    ) -> datetime | None:
        """م-35: متى غُطّي غيابُ هذا اليوم — ووقتُه هو ما يُقاس على المهلة في التقرير.

        «غيابٌ مغطّى» يومٌ كان الحضورُ فيه غياباً بذاته (لم يحضر، أو حضر بعد التاسعة بلا
        تغطية): غُطّي بنوعٍ من سجلّ الغياب (إجازةٌ أو مهمّة)، أو بعذرٍ مقبول أو استثناءٍ
        رفع التصنيف. والوقتُ الأوّلُ يبقى — فلا يُمحى قيدٌ بقيدٍ لاحق.
        """
        bare = classify_arrival(check_in)[0] if check_in is not None else "absent"
        if bare != "absent":
            return None
        covered = values["status"] != "absent" or bool(values["absence_type"])
        if not covered:
            return None
        return record.covered_at or now

    @staticmethod
    def _locked_record(school: School, staff: CustomUser, day: date) -> StaffAttendance | None:
        """سجلُّ اليوم مقفولاً للكتابة — مدخلٌ واحدٌ للقراءة قبل الكتابة في الخدمة كلِّها."""
        return (
            StaffAttendance.objects.select_for_update()
            .filter(school=school, staff=staff, date=day)
            .first()
        )

    @staticmethod
    def _changes(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        return {
            key: [_audited(key, before[key]), _audited(key, value)]
            for key, value in after.items()
            if before[key] != value
        }

    @staticmethod
    def _excuse_values(
        record: StaffAttendance | None,
        excuse: str,
        actor: CustomUser | None,
        now: datetime | None,
    ) -> dict[str, Any]:
        """م-7: العذرُ ومن قبله ووقتُ القبول — قبولٌ جديدٌ بيد ``actor``، أو يبقى ما كان.

        ``actor`` فارغٌ حين لا قبولَ جديدَ (إعادةُ الحساب): يبقى القابلُ الأوّل ما بقي
        العذرُ نفسُه، ويُمحى القيدُ معه متى سقط العذر.
        """
        if not excuse:
            return {
                "accepted_excuse": "",
                "excuse_accepted_by_id": None,
                "excuse_accepted_at": None,
                "excuse_on_behalf": False,
            }
        if actor is None or (record is not None and record.accepted_excuse == excuse):
            if record is None:
                raise PolicyError("عذرٌ بلا من يقبله (م-7).")
            return {
                "accepted_excuse": excuse,
                "excuse_accepted_by_id": record.excuse_accepted_by_id,
                "excuse_accepted_at": record.excuse_accepted_at,
                "excuse_on_behalf": record.excuse_on_behalf,
            }
        return {
            "accepted_excuse": excuse,
            "excuse_accepted_by_id": actor.pk,
            "excuse_accepted_at": now,
            "excuse_on_behalf": _role_of(actor) != PRINCIPAL,
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
        record = StaffAttendanceService._locked_record(school, staff, day)
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
            **StaffAttendanceService._excuse_values(
                record, record.accepted_excuse if derived["excuse_used"] else "", None, None
            ),
        }
        values["covered_at"] = StaffAttendanceService._covered_at(
            record, values, record.check_in, _now()
        )
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
        * الحاضرُ والمتأخّرُ والمستأذنُ بوقت حضورهم، فبه تُحسب دقائقُ التأخّر (م-3 وم-6)،
          ونقرةٌ تخالف تصنيفَه تُرفض باسم البند. والغائبُ بلا وقتٍ جائز.
        * ``accepted_excuse`` (م-7) لا يقبله إلّا المديرُ أو من ينوب عنه، ويُكتب لمن حضر
          بعد 9:00 بلا تغطيةٍ سارية، فيُعدّ متأخّراً بدقائقه لا غائباً.
        * ``absence_type`` نوعُ يوم الغياب من سجلّ الغياب المدرسيّ (إجازةٌ أو مهمّة)،
          والفارغُ غيابٌ لم يُغطَّ بعد (م-35).
        * ``check_out`` وقتُ الانصراف، وما بينه وبين 14:00 بلا إذنٍ يُعدّ (م-1) — إلّا في
          يوم الغياب (م-9).

        والكتابةُ تحت قفل صفّ الموظّف — القفلِ نفسِه الذي يأخذه ``PermitService.act`` —
        فلا يكتب رصدٌ فوق ما أعادت ``reconcile`` حسابَه، ولا يتسابق راصدان.
        """
        now = _now()
        if status not in STATUSES:
            raise PolicyError("حالةٌ غيرُ معروفة.")
        if day > now.date():
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
        CustomUser.objects.select_for_update().filter(pk=staff.pk).first()
        record = StaffAttendanceService._locked_record(school, staff, day)
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
        accepting = bool(excuse) and (record is None or record.accepted_excuse != excuse)
        if accepting and actor.pk not in PermitService._principal_side(
            _StageDay(school, now), staff.pk
        ):
            raise PolicyError(
                "العذرُ المقبول (البند 2.4) يقبله مديرُ المدرسة أو من ينوب عنه (م-7 وم-24) — "
                "ومن رصد الحضورَ يكتب الوقتَ لا العذر."
            )
        values: dict[str, Any] = {
            "status": status,
            "check_in": check_in,
            "check_out": check_out,
            "late_minutes": derived["late_minutes"],
            "permit_minutes": derived["permit_minutes"],
            "early_leave_minutes": derived["early_leave_minutes"],
            "absence_type": absence_type,
            **StaffAttendanceService._excuse_values(
                record, excuse, actor if accepting else None, now
            ),
        }
        if record is None:
            values["covered_at"] = StaffAttendanceService._covered_at(
                StaffAttendance(), values, check_in, now
            )
            try:
                with transaction.atomic():
                    record = StaffAttendance.objects.create(
                        school=school,
                        staff=staff,
                        date=day,
                        created_by=actor,
                        updated_by=actor,
                        **values,
                    )
            except IntegrityError as exc:  # راصدٌ آخرُ سبقنا في اللحظة نفسِها
                raise PolicyError("رُصد هذا اليومُ للتوّ من جهةٍ أخرى — أعد تحميل اللوحة.") from exc
            created = {key: _audited(key, value) for key, value in values.items() if value}
            _audit(actor, "create", record, {"status": status, **created}, request)
            return record
        values["covered_at"] = StaffAttendanceService._covered_at(record, values, check_in, now)
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

        والنائبان يريان من يتبعهما وحدَهم — والتبعيّةُ من جدول م-21 (``LINE_MANAGER``).
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
        """م-36: تقريرُ الشهر لكلّ موظّفٍ في نطاق ``viewer`` (بلا ``viewer``: المدرسةُ كلُّها).

        أيّامُ كلّ حالة ودقائقُ التأخّر (م-36) والانصراف المبكر من سجلّ اليوم، وأيّامُ
        الغياب بأنواعها وغيرُ المغطّى منها، وما غُطّي بعد مهلة يوم 14 موسوماً (م-35)،
        والإذنُ المعتمد من الأذونات نفسِها (فإذنٌ في يومٍ لم يُرصد يُحسب، م-10)،
        والمتبقّي من السقف الشهريّ (م-15)، وأيّامُ استثناء نموذج 03 المعتمد في الشهر
        مستقلّةً عن الأذونات ولا تمسّ السقف (م-33).
        """
        first, last = month_bounds(date(year, month, 1))
        deadline = coverage_deadline(first)
        after_deadline = timezone.make_aware(datetime.combine(deadline + timedelta(days=1), time()))
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
                covered_late=Count("id", filter=Q(covered_at__gte=after_deadline)),
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
        exception_days: dict[Any, set[date]] = {}
        for staff_id, start, end in AttendanceException.objects.filter(
            school=school, status="approved", start_date__lte=last, end_date__gte=first
        ).values_list("staff_id", "start_date", "end_date"):
            day, stop = max(start, first), min(end, last)
            while day <= stop:
                if day.weekday() in SCHOOL_WEEKDAYS:
                    exception_days.setdefault(staff_id, set()).add(day)
                day += timedelta(days=1)
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
                    "covered_late": counted.get("covered_late", 0),
                    **{
                        f"absence_{key}": counted.get(f"absence_{key}", 0)
                        for key in ABSENCE_TYPE_KEYS
                    },
                    "late_minutes": counted.get("late_total") or 0,
                    "early_leave_minutes": counted.get("early_total") or 0,
                    "permit_minutes": used,
                    "permit_remaining": max(0, MONTHLY_PERMIT_CAP - used),
                    "exception_days": len(exception_days.get(person.pk, ())),
                }
            )
        keys = (
            *STATUSES,
            "absent_uncovered",
            "covered_late",
            "exception_days",
            "late_minutes",
            "early_leave_minutes",
            "permit_minutes",
        )
        totals = {key: sum(r[key] for r in rows) for key in keys}
        return {
            "first": first,
            "last": last,
            "deadline": deadline,
            "rows": rows,
            "totals": totals,
        }

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
                f"غياب غُطّي بعد المهلة ({report['deadline']:%d/%m})",
                *(f"غياب: {label}" for _key, label in ABSENCE_TYPES),
                "دقائق التأخّر",
                "دقائق الانصراف المبكر بلا إذن",
                "دقائق الإذن المعتمد",
                "المتبقّي من سقف الأذونات",
                "أيام الاستثناء (نموذج 03)",
            ]
        )
        for r in report["rows"]:
            ws.append(
                [
                    r["employee_number"],
                    r["full_name"],
                    *(r[key] for key in STATUSES),
                    r["absent_uncovered"],
                    r["covered_late"],
                    *(r[f"absence_{key}"] for key in ABSENCE_TYPE_KEYS),
                    r["late_minutes"],
                    r["early_leave_minutes"],
                    r["permit_minutes"],
                    r["permit_remaining"],
                    r["exception_days"],
                ]
            )
        return wb

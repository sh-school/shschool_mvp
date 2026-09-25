"""السياقُ المشترك: الساعةُ، وخطأُ السياسة، والتدقيقُ، والأدوار، و``_StageDay``.

من تفكيك ``staff_affairs/attendance.py`` (الحزمةُ تُصدّر الأسماءَ نفسَها في ``__init__``).
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any
from uuid import UUID

from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils import timezone

from core.models.access import Membership
from core.models.audit import AuditLog
from core.models.school import School
from core.models.user import CustomUser
from staff_affairs.models import (
    AttendanceException,
    PermitRequest,
    StaffAssignment,
    StaffAttendance,
    StaffAttendanceExemption,
)

NON_STAFF_ROLES = ("student", "parent")

#: rbac_roles.json، «مدير المدرسة»: «reports_to» فارغ — لا مسؤولَ له داخل المدرسة (م-23).
PRINCIPAL = "principal"
#: م-24 — بطاقةُ نائب المدير للشؤون الإدارية وشؤون الطلاب (1034) وحدَها فيها «الإنابة عن
#: المدير في مهامه في حال غيابه»؛ وبطاقةُ النائب الأكاديميّ (1033) بلا بندِ إنابة.
PRINCIPAL_DELEGATE = "vice_admin"
#: من يقرأ تقريرَ الحضور للمدرسة كلّها (خارج المواصفة — قرارُ صلاحيّات).
REPORT_WHOLE_SCHOOL = frozenset({PRINCIPAL, "secretary"})
#: من يرصد حضورَ الكادر بصفته (03_job_descriptions_rbac.md، السكرتير «متابعة الحضور
#: والانصراف للموظفين»؛ والمدير) — ونائبُ الشؤون الإدارية معهما بالإنابة وحدَها (م-24).
RECORDERS = frozenset({PRINCIPAL, "secretary"})


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
    obj: StaffAttendance
    | PermitRequest
    | AttendanceException
    | StaffAssignment
    | StaffAttendanceExemption,
    changes: dict[str, Any],
    request: HttpRequest | None = None,
) -> None:
    """أثرٌ في سجلّ التدقيق بلا اسمٍ ولا رقمٍ شخصيّ — النوعُ والمعرّفُ والتغيير."""
    day = (
        obj.start_date
        if isinstance(obj, AttendanceException | StaffAssignment | StaffAttendanceExemption)
        else obj.date
    )
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


def _established_absences(school: School, day: date) -> QuerySet[StaffAttendance]:
    """غيابُ اليوم: المرصودون غائبين — فلا يوقّعون ولا يُعدّون في مربّعٍ يومَهم."""
    return StaffAttendance.objects.filter(school=school, date=day, status="absent")


class _StageDay:
    """من يحضر مراحلَ الاعتماد في مدرسةٍ في لحظةٍ — يُقرأ مرّةً لكلّ طابور أو قرار.

    أسئلتُه اثنان: من يحمل الدورَ نشطاً — ومعه من كُلّف بأعباء ذلك الدور اليومَ بقرارٍ
    صريح (``StaffAssignment``، م-43 من النظام الوظيفيّ) — ومن رُصد غائباً اليوم. فلا
    إنابةَ تقوم برصد غياب ولا بأقدميّة: من غاب ولم يُكلَّف عنه أحدٌ بقي مربّعُه معلّقاً
    حتى يكلّف صاحبُ القرار.
    """

    def __init__(self, school: School, now: datetime) -> None:
        self.school, self.now = school, now
        self.today = now.date()
        self._holders: dict[str, set[Any]] = {}
        self._absent: set[Any] | None = None
        self._assigned: dict[str, dict[Any, Any]] | None = None

    def assigned(self, role: str) -> dict[Any, Any]:
        """{المكلَّف: معرّفُ تكليفه} للدور اليوم — والمرفوعُ والمنتهي لا يُعدّان."""
        if self._assigned is None:
            self._assigned = {}
            rows = StaffAssignment.objects.filter(
                school=self.school,
                start_date__lte=self.today,
                end_date__gte=self.today,
                revoked_at__isnull=True,
            ).values_list("acting_role", "assignee_id", "pk")
            for acting_role, assignee, pk in rows:
                self._assigned.setdefault(acting_role, {})[assignee] = pk
        return self._assigned.get(role, {})

    def holders(self, role: str) -> set[Any]:
        """حاملو الدور نشطين، ومعهم المكلَّفون بأعبائه اليوم."""
        if role not in self._holders:
            self._holders[role] = _active_role_holders(self.school, role) | set(self.assigned(role))
        return self._holders[role]

    def absent(self) -> set[Any]:
        """المرصودون غائبين اليوم — وفيهم من في إجازة (يومُ غيابٍ بنوعه من سجلّ الغياب).

        منه يُرفع مربّعٌ غاب صاحبُه (م-28)، ولا يعمل الغائبُ في مربّع.
        """
        if self._absent is None:
            self._absent = set(
                _established_absences(self.school, self.today).values_list("staff_id", flat=True)
            )
        return self._absent

    def assignment_basis(self, actor: CustomUser) -> dict[str, Any]:
        """ما يُكتب في التدقيق حين يعمل ``actor`` بتكليفٍ: معرّفُه ووظيفتُه.

        فيرتبط كلُّ قرارٍ بالتكليف الذي أقامه، ويبقى بعد رفعه (``AssignmentService.revoke``).
        وفارغٌ إن لم يعمل بتكليف (مربّعٌ رُفع بغياب صاحبه أو شغوره، م-28).
        """
        for role in (PRINCIPAL, PRINCIPAL_DELEGATE, "vice_academic"):
            pk = self.assigned(role).get(actor.pk)
            if pk is not None:
                return {"assignment": _plain(pk), "acting_role": role}
        return {}


#: م-21 — «المسؤول المباشر» في ترويسة كلّ بطاقةِ وصفٍ وظيفيّ، ويوافقه «reports_to» في
#: rbac_roles.json (ورقمُ السطر سطرُ «title» هناك). والمسؤولُ المباشرُ هو النائبُ
#: المسؤولُ نفسُه في كلّ الفئات، فيوقّع المربّعين بتوقيعٍ واحد (م-19). وما لا بطاقةَ
#: لمسمّاه يرفع إلى المدير (م-22، ``deputy_role_for``).
LINE_MANAGER: dict[str, str] = {
    "vice_admin": "principal",  # :21 نائب المدير للشؤون الإدارية وشؤون الطالب
    "vice_academic": "principal",  # :28 نائب المدير للشؤون الأكاديمية
    "secretary": "principal",  # :36 سكرتير مدرسة  # pragma: allowlist secret
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

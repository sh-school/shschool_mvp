"""التكليفات — المادّة 43 من النظام الوظيفيّ.

من تفكيك ``staff_affairs/attendance.py`` (الحزمةُ تُصدّر الأسماءَ نفسَها في ``__init__``).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any

from django.db import transaction
from django.db.models import Q, QuerySet
from django.http import Http404, HttpRequest

import staff_affairs.attendance as _pkg
from core.models.access import Membership
from core.models.department import Department
from core.models.permission_audit import PermissionAuditLog
from core.models.school import School
from core.models.user import CustomUser
from staff_affairs.models import (
    LeaveRequest,
    StaffAssignment,
    StaffAttendance,
)

from .context import (
    LINE_MANAGER,
    PRINCIPAL,
    PRINCIPAL_DELEGATE,
    PolicyError,
    _active_role_holders,
    _audit,
    _plain,
    _role_of,
    staff_members,
)

# ══════════════════════════════════════════════════════════════════════
#  التكليفات — المادّة 43 من النظام الوظيفيّ
# ══════════════════════════════════════════════════════════════════════

#: أقصى مدّةٍ لتكليف — «لمدة لا تجاوز عام أكاديمي» (م-43).
ASSIGNMENT_MAX_DAYS = 365
#: المنسّقون (قرار المدرسة 2026-09-19). ما عادوا وحدَهم من يكلّفهم النائبُ الأكاديميّ: صار
#: يكلّف كلَّ من يتبعه في ``LINE_MANAGER`` أيّاً كان دورُه (قرار المالك 2026-10-04).
COORDINATOR_ROLES = frozenset({"coordinator", "e_projects_coordinator"})
#: من يكلّف: المديرُ ونائباه، والمنسّقُ أحدَ معلّمي قسمه في غيابه أو خروجه (قرار المالك 2026-10-04).
_TASKING_ROLES = (PRINCIPAL, PRINCIPAL_DELEGATE, "vice_academic", "coordinator")

_ACTING_CACHE = "_acting_roles"


def acting_roles(user: Any) -> frozenset[str]:
    """الوظائفُ التي يقوم هذا المستخدمُ بأعبائها اليومَ بتكليفٍ ساري — منها يقرأ ``has_capability``.

    استعلامٌ واحدٌ يُحفظ على كائن المستخدم لليوم نفسِه (كمنح القدرة المفوَّضة)؛ والتكليفُ
    والرفعُ يُبطلانه على كائن المكلَّف (``_forget_acting``). وما انقضى يومُه أو رُفع لا يُعدّ.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return frozenset()
    today = _pkg._now().date()
    cached = user.__dict__.get(_ACTING_CACHE)
    if cached is not None and cached[0] == today:
        return cached[1]  # type: ignore[no-any-return]
    roles = frozenset(
        StaffAssignment.objects.filter(
            assignee=user,
            revoked_at__isnull=True,
            start_date__lte=today,
            end_date__gte=today,
        ).values_list("acting_role", flat=True)
    )
    user.__dict__[_ACTING_CACHE] = (today, roles)
    return roles


def _forget_acting(user: Any) -> None:
    user.__dict__.pop(_ACTING_CACHE, None)


def _audit_permission(
    *,
    action: str,
    actor: CustomUser,
    assignment: StaffAssignment,
    request: HttpRequest | None,
) -> None:
    """أثرُ التكليف والرفع في ``PermissionAuditLog`` (ثابتٌ لا يُعدَّل ولا يُحذف).

    معرّفاتٌ وتواريخُ فقط: نصُّ السبب يبقى في سجلّ التكليف (قد يحمل بيانةً شخصيّة، PDPPL)،
    ويُسجَّل أنّ سبباً أُدخل.
    """
    PermissionAuditLog.log(  # type: ignore[no-untyped-call]
        actor=actor,
        target=assignment.assignee,
        action=action,
        school=assignment.school,
        details={
            "assignment": str(assignment.pk),
            "acting_role": assignment.acting_role,
            "start": _plain(assignment.start_date),
            "end": _plain(assignment.end_date),
            "reason_given": bool(assignment.reason),
        },
        request=request,
    )


class AssignmentService:
    """تكليفُ موظّفٍ بأعباء وظيفةٍ مؤقّتاً — بيد صاحب القرار وحدَه.

    قرارُ المدرسة (2026-09-19)، وسندُه م-43 من النظام الوظيفيّ وم-53 من القانون:

    * المديرُ يكلّف النائبَ الإداريّ أو النائبَ الأكاديميّ بأعباء المدير؛ فإن غاب النائبان
      معاً كلّف غيرَهما من الإداريّين أو الأكاديميّين.
    * كلٌّ من النائبين يكلّف أحدَ من تحت مسؤوليته (مسؤولُهم المباشرُ في بطاقاتهم، ``LINE_MANAGER``)
      بأعبائه — أيّاً كان دورُه (قرار المالك 2026-10-04).
    * المنسّقُ يكلّف أحدَ معلّمي قسمه بأعبائه في غيابه أو خروجه (قرارُ مدرسة، لا نصَّ وزاريّ).

    وهو قرارٌ صريحٌ: لا يقوم برصد غيابٍ ولا بالأقدميّة. والمكلَّفُ يعمل في مربّعات وظيفته
    (اعتمادُ الأذونات وقبولُ العذر وقرارُ نموذج 03 وأمثالُها) ويُوسم قرارُه بمعرّف تكليفه.
    """

    @staticmethod
    def acting_role_of(user: CustomUser) -> str:
        """الوظيفةُ التي يكلّف عنها هذا المستخدم — وظيفتُه نفسُها إن كانت من ``_TASKING_ROLES``."""
        role = _role_of(user)
        return role if role in _TASKING_ROLES else ""

    @staticmethod
    def is_principal(school: School, user: CustomUser) -> bool:
        return user.pk in _active_role_holders(school, PRINCIPAL)

    @staticmethod
    def _unavailable(school: School, role: str, start: date) -> bool:
        """أغاب كلُّ حاملي الدور في ``start``: رصدُ غيابٍ أو إجازةٌ معتمدةٌ تغطّيه؟"""
        holders = _active_role_holders(school, role)
        if not holders:
            return True
        away = set(
            StaffAttendance.objects.filter(
                school=school, date=start, status="absent", staff_id__in=holders
            ).values_list("staff_id", flat=True)
        ) | set(
            LeaveRequest.objects.filter(
                school=school,
                status="approved",
                staff_id__in=holders,
                start_date__lte=start,
                end_date__gte=start,
            ).values_list("staff_id", flat=True)
        )
        return holders <= away

    @staticmethod
    def candidates(
        school: School, assigner: CustomUser, start: date | None = None
    ) -> QuerySet[CustomUser]:
        """من يجوز لـ``assigner`` أن يكلّفهم — بحسب وظيفته وقرار المدرسة."""
        role = AssignmentService.acting_role_of(assigner)
        people = staff_members(school).exclude(pk=assigner.pk)
        if role == PRINCIPAL:
            deputies = _active_role_holders(school, PRINCIPAL_DELEGATE) | _active_role_holders(
                school, "vice_academic"
            )
            allowed = set(deputies)
            day = start or _pkg._now().date()
            if all(
                AssignmentService._unavailable(school, r, day)
                for r in (PRINCIPAL_DELEGATE, "vice_academic")
            ):
                # غاب النائبان معاً: يكلّف غيرَهما من الإداريّين والأكاديميّين.
                allowed |= {
                    user_id
                    for user_id, member_role in Membership.objects.current()
                    .filter(school=school, is_active=True)
                    .values_list("user_id", "role__name")
                    if member_role in LINE_MANAGER and member_role not in {"secretary"}
                }
            return people.filter(pk__in=allowed)
        if role in (PRINCIPAL_DELEGATE, "vice_academic"):
            under = {r for r, manager in LINE_MANAGER.items() if manager == role}
            return people.filter(pk__in=_holders_of(school, under))
        if role == "coordinator":
            return people.filter(pk__in=_department_teachers(school, assigner))
        return people.none()

    @staticmethod
    def screen(
        school: School, viewer: CustomUser | None = None
    ) -> dict[str, list[StaffAssignment]]:
        """ما يعرضه ركنُ «التكليفات»: القائمُ اليوم، والمنتظِرُ بدأه، والمنتهي أو المرفوع.

        والمنسّقُ يرى تكليفاتِه هو وحدَها: سجلُّ المدرسة كلِّها (وأسبابُه) للمدير ونائبَيه.
        """
        today = _pkg._now().date()
        query = StaffAssignment.objects.filter(school=school)
        if viewer is not None and AssignmentService.acting_role_of(viewer) == "coordinator":
            query = query.filter(assigned_by=viewer)
        rows = list(
            query.select_related("assignee", "assigned_by").order_by("-start_date", "-created_at")[
                :100
            ]
        )
        current, upcoming, past = [], [], []
        for row in rows:
            if row.revoked_at or row.end_date < today:
                past.append(row)
            elif row.start_date > today:
                upcoming.append(row)
            else:
                current.append(row)
        return {"current": current, "upcoming": upcoming, "past": past}

    @staticmethod
    def one(school: School, pk: Any) -> StaffAssignment:
        """تكليفٌ في هذه المدرسة — وغيرُها لا يُكشف وجودُه (Http404 من العرض)."""
        try:
            return StaffAssignment.objects.select_related("assignee").get(school=school, pk=pk)
        except StaffAssignment.DoesNotExist as exc:
            raise Http404("لا تكليفَ بهذا المعرّف") from exc

    @staticmethod
    @transaction.atomic
    def assign(
        *,
        school: School,
        assigner: CustomUser,
        assignee: CustomUser,
        start: date,
        end: date,
        reason: str,
        reference: str = "",
        request: HttpRequest | None = None,
    ) -> StaffAssignment:
        role = AssignmentService.acting_role_of(assigner)
        if not role or assigner.pk not in _active_role_holders(school, role):
            raise PolicyError(
                "التكليفُ لمدير المدرسة ونائبَيه والمنسّقين — كلٌّ عن وظيفته (م-43 من النظام الوظيفيّ)."
            )
        if assignee.pk == assigner.pk:
            raise PolicyError("لا يكلّف الموظّفُ نفسَه.")
        today = _pkg._now().date()
        if start < today:
            raise PolicyError("لا تكليفَ بأثرٍ رجعيّ.")
        if end < start:
            raise PolicyError("«إلى تاريخ» يجب ألّا يسبق «من تاريخ».")
        if (end - start).days + 1 > ASSIGNMENT_MAX_DAYS:
            raise PolicyError("التكليفُ لمدّةٍ لا تجاوز عاماً أكاديميّاً (م-43).")
        if not reason.strip():
            raise PolicyError("سببُ التكليف مطلوب.")
        if (
            not AssignmentService.candidates(school, assigner, start)
            .filter(pk=assignee.pk)
            .exists()
        ):
            raise PolicyError(
                {
                    PRINCIPAL: "المديرُ يكلّف نائبَيه، ولا يكلّف غيرَهما إلّا إن غاب النائبان معاً.",
                    "vice_academic": "النائبُ الأكاديميّ يكلّف أحدَ من تحت مسؤوليته.",
                    PRINCIPAL_DELEGATE: "النائبُ الإداريّ يكلّف أحدَ من تحت مسؤوليته.",
                    "coordinator": "المنسّقُ يكلّف أحدَ معلّمي قسمه.",
                }[role]
            )
        CustomUser.objects.select_for_update().filter(pk=assignee.pk).first()
        for overlapping in StaffAssignment.objects.filter(
            school=school,
            assignee=assignee,
            acting_role=role,
            revoked_at__isnull=True,
            start_date__lte=end,
            end_date__gte=start,
        ):
            if (overlapping.assigned_by_id, overlapping.start_date, overlapping.end_date) == (
                assigner.pk,
                start,
                end,
            ):
                return overlapping  # التكليفُ نفسُه قائم — لا سجلَّ ثانياً
            raise PolicyError(
                "يتداخل التكليفُ مع تكليفٍ قائمٍ للموظّف نفسِه بالوظيفة نفسِها — ارفع القائمَ أوّلاً."
            )
        assignment = StaffAssignment.objects.create(
            school=school,
            assignee=assignee,
            assigned_by=assigner,
            acting_role=role,
            start_date=start,
            end_date=end,
            reason=reason.strip()[:300],
            reference=reference.strip()[:200],
            created_by=assigner,
            updated_by=assigner,
        )
        _audit(
            assigner,
            "create",
            assignment,
            {
                "assignee": str(assignee.pk),
                "acting_role": role,
                "start": _plain(start),
                "end": _plain(end),
            },
            request,
        )
        _audit_permission(
            action="acting_assigned", actor=assigner, assignment=assignment, request=request
        )
        _forget_acting(assignee)
        return assignment

    @staticmethod
    @transaction.atomic
    def revoke(
        assignment: StaffAssignment, *, actor: CustomUser, request: HttpRequest | None = None
    ) -> StaffAssignment:
        """رفعُ تكليفٍ بلا حذف: يبقى من كُلّف ومن كلّفه ومن رفعه ومتى."""
        assignment = StaffAssignment.objects.select_for_update().get(pk=assignment.pk)
        is_owner = actor.pk == assignment.assigned_by_id
        if not (is_owner or actor.pk in _active_role_holders(assignment.school, PRINCIPAL)):
            raise PolicyError("لا يرفع التكليفَ إلّا من كلّف به أو مديرُ المدرسة.")
        if assignment.revoked_at is not None:
            return assignment
        assignment.revoked_at, assignment.revoked_by = _pkg._now(), actor
        assignment.updated_by = actor
        assignment.save(update_fields=["revoked_at", "revoked_by", "updated_by", "updated_at"])
        _audit(
            actor,
            "update",
            assignment,
            {"assignee": str(assignment.assignee_id), "revoked": True},
            request,
        )
        _audit_permission(
            action="acting_revoked", actor=actor, assignment=assignment, request=request
        )
        _forget_acting(assignment.assignee)
        return assignment


def _department_teachers(school: School, coordinator: CustomUser) -> set[Any]:
    """معلّمو قسم المنسّق: الأقسامُ التي يرأسها أو ينتمي إليها بعضويّته — بلا غيرها."""
    departments = Department.objects.filter(school=school, is_active=True).filter(
        Q(head=coordinator)
        | Q(
            pk__in=Membership.objects.current()
            .filter(school=school, user=coordinator, is_active=True, department_obj__isnull=False)
            .values("department_obj_id")
        )
    )
    teachers: set[Any] = set()
    for department in departments:
        teachers |= department.get_teacher_ids()
    return teachers


def _holders_of(school: School, roles: Iterable[str]) -> set[Any]:
    """حاملو أيٍّ من ``roles`` نشطين في المدرسة."""
    return set(
        Membership.objects.current()
        .filter(school=school, is_active=True, role__name__in=set(roles))
        .values_list("user_id", flat=True)
    )

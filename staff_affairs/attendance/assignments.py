"""التكليفات — المادّة 43 من النظام الوظيفيّ.

من تفكيك ``staff_affairs/attendance.py`` (الحزمةُ تُصدّر الأسماءَ نفسَها في ``__init__``).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any

from django.db import transaction
from django.db.models import QuerySet
from django.http import Http404, HttpRequest

import staff_affairs.attendance as _pkg
from core.models.access import Membership
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
#: من يكلَّفهم النائبُ الأكاديميّ: المنسّقون (قرار المدرسة 2026-09-19).
COORDINATOR_ROLES = frozenset({"coordinator", "e_projects_coordinator"})
_TASKING_ROLES = (PRINCIPAL, PRINCIPAL_DELEGATE, "vice_academic")


class AssignmentService:
    """تكليفُ موظّفٍ بأعباء وظيفةٍ مؤقّتاً — بيد صاحب القرار وحدَه.

    قرارُ المدرسة (2026-09-19)، وسندُه م-43 من النظام الوظيفيّ وم-53 من القانون:

    * المديرُ يكلّف النائبَ الإداريّ أو النائبَ الأكاديميّ بأعباء المدير؛ فإن غاب النائبان
      معاً كلّف غيرَهما من الإداريّين أو الأكاديميّين.
    * النائبُ الأكاديميّ يكلّف أحدَ المنسّقين بأعبائه في غيابه.
    * النائبُ الإداريّ يكلّف أحدَ من تحت مسؤوليته (مسؤولُهم المباشرُ في بطاقاتهم) بأعبائه.

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
        if role == "vice_academic":
            return people.filter(pk__in=_holders_of(school, COORDINATOR_ROLES))
        if role == PRINCIPAL_DELEGATE:
            under = {r for r, manager in LINE_MANAGER.items() if manager == PRINCIPAL_DELEGATE}
            return people.filter(pk__in=_holders_of(school, under))
        return people.none()

    @staticmethod
    def screen(school: School) -> dict[str, list[StaffAssignment]]:
        """ما يعرضه ركنُ «التكليفات»: القائمُ اليوم، والمنتظِرُ بدأه، والمنتهي أو المرفوع."""
        today = _pkg._now().date()
        rows = list(
            StaffAssignment.objects.filter(school=school)
            .select_related("assignee", "assigned_by")
            .order_by("-start_date", "-created_at")[:100]
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
                "التكليفُ لمدير المدرسة ونائبَيه — كلٌّ عن وظيفته (م-43 من النظام الوظيفيّ)."
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
                    "vice_academic": "النائبُ الأكاديميّ يكلّف أحدَ المنسّقين.",
                    PRINCIPAL_DELEGATE: "النائبُ الإداريّ يكلّف أحدَ من تحت مسؤوليته.",
                }[role]
            )
        CustomUser.objects.select_for_update().filter(pk=assignee.pk).first()
        overlapping = StaffAssignment.objects.filter(
            school=school,
            assignee=assignee,
            acting_role=role,
            revoked_at__isnull=True,
            start_date__lte=end,
            end_date__gte=start,
        ).first()
        if overlapping is not None:
            return overlapping  # التكليفُ نفسُه قائم — لا سجلَّ ثانياً
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
        return assignment


def _holders_of(school: School, roles: Iterable[str]) -> set[Any]:
    """حاملو أيٍّ من ``roles`` نشطين في المدرسة."""
    return set(
        Membership.objects.current()
        .filter(school=school, is_active=True, role__name__in=set(roles))
        .values_list("user_id", flat=True)
    )

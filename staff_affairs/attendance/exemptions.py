"""الإعفاءُ من الرصد اليوميّ — موظّفٌ لا يداوم فلا يُرصد غائباً فيُخصم منه.

قرارُ المالك (2026-09-21): نموذجٌ عامّ يسجّل موظّفاً أو أكثر بمدّةٍ أو بلا نهاية، بلا خزنِ
سببٍ (بيانةٌ صحّيّةٌ محتملة) — ``StaffAttendanceExemption``. أثرُه ثلاثةٌ: لا يدخل لوحةَ رصد
اليوم، ولا تقريرَ الشهر (إن أُعفي الشهرَ كلَّه ولا سجلَّ له فيه)، ولا إخطارَ الغياب والخصم.
وحسابُه ودورُه وصلاحيّاتُه كما هي.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any

from django.db import transaction
from django.db.models import Q, QuerySet
from django.http import Http404, HttpRequest
from django.utils import timezone

import staff_affairs.attendance as _pkg
from core.models.school import School
from core.models.user import CustomUser
from staff_affairs.models import StaffAttendanceExemption

from .context import (
    PRINCIPAL,
    PRINCIPAL_DELEGATE,
    PolicyError,
    _active_role_holders,
    _audit,
    staff_members,
)

#: من يعفي ويرفع: المديرُ والنائبُ الإداريّ (شؤونُ الموظفين الإداريّة).
EXEMPTION_ROLES = (PRINCIPAL, PRINCIPAL_DELEGATE)


def covering(school: School, first: date, last: date | None = None) -> QuerySet[Any]:
    """إعفاءاتٌ تغطّي كلَّ يومٍ من ``first`` إلى ``last`` (يومٌ واحدٌ إن لم تُعطَ ``last``).

    ومرفوعٌ يسري حتى يومِ رفعه لا بعده: فلا يُعاد به فتحُ أيّامٍ مضت.
    """
    last = last or first
    return StaffAttendanceExemption.objects.filter(
        Q(revoked_at__isnull=True) | Q(revoked_at__date__gt=last),
        school=school,
        start_date__lte=first,
    ).filter(Q(end_date__isnull=True) | Q(end_date__gte=last))


def exempt_ids(school: School, first: date, last: date | None = None) -> set[Any]:
    return set(covering(school, first, last).values_list("staff_id", flat=True))


def exempt_days(school: School, first: date, last: date) -> dict[Any, list[tuple[date, date]]]:
    """لكلّ موظّفٍ معفًى في ``first``..``last``: مجالاتُ أيّامه المعفاة (الرفعُ يقصّ المجال)."""
    from datetime import timedelta

    out: dict[Any, list[tuple[date, date]]] = {}
    rows = StaffAttendanceExemption.objects.filter(school=school, start_date__lte=last).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=first)
    )
    for row in rows:
        stop = row.end_date or last
        if row.revoked_at is not None:
            stop = min(stop, timezone.localtime(row.revoked_at).date() - timedelta(days=1))
        if stop >= row.start_date:
            out.setdefault(row.staff_id, []).append((row.start_date, stop))
    return out


def recording_staff(school: School, day: date) -> QuerySet[CustomUser]:
    """كادرُ المدرسة الذي يُرصد حضورُه في ``day`` — بلا المعفَيْن."""
    return staff_members(school).exclude(pk__in=exempt_ids(school, day))


class ExemptionService:
    """تسجيلُ الإعفاء ورفعُه — بيد المدير ونائبه الإداريّ."""

    @staticmethod
    def can_manage(school: School, user: CustomUser) -> bool:
        return any(user.pk in _active_role_holders(school, role) for role in EXEMPTION_ROLES)

    @staticmethod
    def candidates(school: School, actor: CustomUser) -> QuerySet[CustomUser]:
        """من يجوز إعفاؤُهم: الكادرُ النشط عدا المعفيَّ اليومَ ومعدا صاحبِ القرار نفسِه."""
        today = _pkg._now().date()
        return staff_members(school).exclude(pk=actor.pk).exclude(pk__in=exempt_ids(school, today))

    @staticmethod
    def screen(school: School) -> dict[str, list[StaffAttendanceExemption]]:
        """القائمُ اليوم (مفتوحٌ أو ضمنَ مدّته)، والمنتهي أو المرفوع أو القادم."""
        today = _pkg._now().date()
        rows = list(
            StaffAttendanceExemption.objects.filter(school=school)
            .select_related("staff")
            .order_by("-start_date", "-created_at")[:100]
        )
        live_ids = set(covering(school, today).values_list("pk", flat=True))
        current = [r for r in rows if r.pk in live_ids]
        return {"current": current, "past": [r for r in rows if r.pk not in live_ids]}

    @staticmethod
    def one(school: School, pk: Any) -> StaffAttendanceExemption:
        try:
            return StaffAttendanceExemption.objects.select_related("staff").get(
                school=school, pk=pk
            )
        except StaffAttendanceExemption.DoesNotExist as exc:
            raise Http404("لا إعفاءَ بهذا المعرّف") from exc

    @staticmethod
    @transaction.atomic
    def grant(
        *,
        school: School,
        actor: CustomUser,
        staff_ids: Iterable[Any],
        start: date,
        end: date | None,
        reference: str = "",
        request: HttpRequest | None = None,
    ) -> list[StaffAttendanceExemption]:
        """يعفي موظّفاً أو أكثر بقرارٍ واحد. الصفُّ القائمُ نفسُه لا يتكرّر (idempotent)."""
        if not ExemptionService.can_manage(school, actor):
            raise PolicyError("الإعفاءُ من الرصد لمدير المدرسة ونائبه الإداريّ.")
        if end is not None and end < start:
            raise PolicyError("«إلى تاريخ» يجب ألّا يسبق «من تاريخ».")
        wanted = {str(pk) for pk in staff_ids}
        if not wanted:
            raise PolicyError("اختر موظّفاً واحداً على الأقلّ.")
        people = list(
            ExemptionService.candidates(school, actor)
            .filter(pk__in=wanted)
            .select_for_update(of=("self",))
        )
        if {str(p.pk) for p in people} != wanted:
            raise PolicyError("موظّفٌ غيرُ صالحٍ للإعفاء (ليس من الكادر، أو معفًى أصلاً، أو أنت).")
        made = []
        for person in people:
            row = StaffAttendanceExemption.objects.create(
                school=school,
                staff=person,
                start_date=start,
                end_date=end,
                reference=reference.strip()[:200],
                created_by=actor,
                updated_by=actor,
            )
            _audit(
                actor,
                "create",
                row,
                {
                    "staff": str(person.pk),
                    "start": start.isoformat(),
                    "end": end and end.isoformat(),
                },
                request,
            )
            made.append(row)
        return made

    @staticmethod
    @transaction.atomic
    def revoke(
        exemption: StaffAttendanceExemption,
        *,
        actor: CustomUser,
        request: HttpRequest | None = None,
    ) -> StaffAttendanceExemption:
        """رفعٌ بلا حذف: يبقى من أُعفي ومن أعفاه ومن رفعه ومتى."""
        exemption = StaffAttendanceExemption.objects.select_for_update().get(pk=exemption.pk)
        if not ExemptionService.can_manage(exemption.school, actor):
            raise PolicyError("رفعُ الإعفاء لمدير المدرسة ونائبه الإداريّ.")
        if exemption.revoked_at is not None:
            return exemption
        exemption.revoked_at, exemption.revoked_by = _pkg._now(), actor
        exemption.updated_by = actor
        exemption.save(update_fields=["revoked_at", "revoked_by", "updated_by", "updated_at"])
        _audit(
            actor, "update", exemption, {"staff": str(exemption.staff_id), "revoked": True}, request
        )
        return exemption

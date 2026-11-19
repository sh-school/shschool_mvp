"""تعيينُ مشرف الجناح وميدانيِّه بسجلٍّ زمنيّ — الكتابةُ هنا والقراءةُ في `assignment_selectors`.

التعيينُ الجديد يغلق السابقَ بتاريخٍ ولا يحذفه، ويُكتب في `AuditLog` بلا اسمٍ ولا رقمٍ شخصيّ:
معرّفاتٌ ودورٌ وجناحٌ فقط.
"""

from __future__ import annotations

import datetime as dt

from django.core.exceptions import ValidationError
from django.db import transaction

from core.models import AuditLog, CustomUser, Wing, WingAssignment


@transaction.atomic
def assign_wing_role(
    *,
    wing: Wing,
    role: str,
    user: CustomUser,
    by: CustomUser,
    start_date: dt.date,
) -> WingAssignment:
    """يعيّن `user` في `role` على `wing` من `start_date`، فيُغلَق تعيينُ سابقِه قبل هذا اليوم بيوم.

    يرفض: دوراً مجهولاً، ومن يحمل الدورَ أصلاً، وبدايةً لا تتأخّر عن بداية السابق، ومعيَّناً غيرَ مؤهَّل
    أو يحمل دورين في الجناح نفسه أو الدورَ نفسَه في جناحين (`WingAssignment.clean`).
    """
    if role not in dict(WingAssignment.ROLES):
        raise ValidationError({"role": "دورٌ غيرُ معروف."})
    # قفلُ الجناح يسلسل تعيينين متزامنين عليه فلا يمرّان معاً على الفحص.
    wing = Wing.objects.select_for_update().get(pk=wing.pk)
    rows = wing.assignments.filter(role=role)
    if rows.filter(start_date__gte=start_date).exists():
        raise ValidationError({"start_date": "يوجد تعيينٌ يبدأ في هذا اليوم أو بعده لهذا الدور."})
    previous = rows.filter(end_date__isnull=True).first() or (
        rows.filter(end_date__gte=start_date).order_by("-start_date").first()
    )
    if previous is not None and previous.user_id == user.pk:
        raise ValidationError({"user": "هو المعيَّنُ لهذا الدور أصلاً."})
    if previous is not None:
        previous.end_date = start_date - dt.timedelta(days=1)
        previous.ended_by = by
        previous.save(update_fields=["end_date", "ended_by"])
    assignment = WingAssignment(
        wing=wing, role=role, user=user, start_date=start_date, assigned_by=by
    )
    assignment.full_clean()
    assignment.save()
    AuditLog.objects.create(
        user=by,
        school=wing.school,
        action="create",
        model_name="other",
        object_id=str(assignment.pk),
        object_repr=f"تعيين {assignment.get_role_display()} — {wing.name}"[:300],
        changes={
            "wing": str(wing.pk),
            "role": role,
            "user": str(user.pk),
            "start_date": start_date.isoformat(),
            "closed": str(previous.pk) if previous is not None else None,
        },
    )
    return assignment

"""قراءةُ قوائم الإجراءات المقترحة — W-20261108-023. الكتابةُ في `action_services.py`."""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet

from wings.scope import student_scope

from .action_services import PREPARABLE, may_decide
from .models import BehaviorInfraction

_LIMIT = 200


def _base(school: Any) -> QuerySet[BehaviorInfraction]:
    return BehaviorInfraction.objects.filter(school=school).select_related(
        "student", "violation_category", "reported_by", "prepared_by"
    )


def pending_for_approver(user: Any, school: Any) -> list[BehaviorInfraction]:
    """المخالفاتُ بانتظار اعتماد `user`: من لم يسجّلها هو، وبدورِ المعتمِد المقرَّر لها."""
    rows = _base(school).filter(approval_status="pending").order_by("date", "id")[:_LIMIT]
    return [row for row in rows if may_decide(user, row)]


def approved_for_followup(user: Any, school: Any) -> list[BehaviorInfraction]:
    """المعتمَدةُ التي لم تُتابَع بعدُ، ممّا يتابعه `user`."""
    rows = (
        _base(school)
        .filter(approval_status="approved", followup_status="")
        .order_by("-approved_at")
    )
    return [row for row in rows[:_LIMIT] if may_decide(user, row)]


def pending_for_supervisor(user: Any, school: Any) -> list[BehaviorInfraction]:
    """ما يجهّزه مشرفُ الجناح: تعهّدٌ أو إحالةٌ مقترحة، لطلبة جناحه وحدَهم، بلا ما جُهّز."""
    qs = (
        _base(school)
        .filter(
            approval_status="pending",
            prepared_kind="",
            proposed_action_type__in=list(PREPARABLE),
        )
        .order_by("date", "id")
    )
    return list(student_scope(user, school).narrow(qs)[:_LIMIT])


def specialist_referrals(school: Any) -> list[BehaviorInfraction]:
    """إحالاتُ الاختصاصيّين: المعتمَدةُ التي بلغت عتبةً تنصّ عليها السياسة (سندُها محفوظٌ بالسطر)."""
    return list(
        _base(school)
        .filter(approval_status="approved", proposed_specialist=True)
        .order_by("-approved_at")[:_LIMIT]
    )

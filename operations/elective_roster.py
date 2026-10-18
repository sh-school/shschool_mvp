"""قائمةُ طلاب الجلسة الاختيارية من العضويّة لا من الشعبة كلِّها (W-20261002-021).

القاعدة: جلسةٌ بوسم مجموعةٍ ولها أعضاءٌ مسجَّلون في شعبتها ← أعضاؤها وحدَهم.
وجلسةٌ بلا وسمٍ، أو وسمُها بلا أعضاءَ مسجَّلين بعدُ ← الشعبةُ كلُّها كما كان (رجوعٌ آمنٌ لا يُسقط أحداً قبل الملء).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models import ElectiveGroupMembership, StudentEnrollment

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from .models import Session


def has_members(session: Session) -> bool:
    """هل لوسم هذه الجلسة الاختيارية أعضاءٌ مسجَّلون في شعبتها؟"""
    return bool(
        session.elective_group
        and ElectiveGroupMembership.objects.filter(
            group_label=session.elective_group, enrollment__class_group_id=session.class_group_id
        ).exists()
    )


def session_enrollments(session: Session) -> QuerySet[StudentEnrollment]:
    """قيودُ من تشملهم الجلسةُ في يومها: أعضاءُ المجموعة إن وُجدوا، وإلا شعبتُها كلُّها."""
    qs: QuerySet[StudentEnrollment] = StudentEnrollment.objects.filter(
        class_group_id=session.class_group_id
    ).on_roll(session.date)
    if has_members(session):
        qs = qs.filter(elective_memberships__group_label=session.elective_group)
    return qs

"""كتاباتُ متابعة المشرف الإداريّ والتحقّقُ منها (لا نماذجَ إدخال، كالزيارة الصفّية).

الحفظُ متساوي الأثر: معرّفُ المتابعة ومعرّفاتُ توصياتها تأتي من النموذج، فإعادةُ الإرسال تُحدّث ولا تكرّر.
وسجلُّ التدقيق بلا اسمٍ ولا نصٍّ حرّ.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from django.db import IntegrityError, transaction
from django.http import Http404, HttpRequest
from django.utils import timezone

from core.audit_repr import masked_repr
from core.models import AuditLog, CustomUser, School

from . import supervisor_followup_selectors as selectors
from .supervisor_followup_indicators import INDICATORS, RATINGS
from .supervisor_followup_models import (
    SupervisorFollowUp,
    SupervisorFollowUpRecommendation,
    SupervisorFollowUpScore,
)


class FollowUpError(ValueError):
    """خطأُ إدخالٍ تُعرض رسالتُه للمستخدم."""


@dataclass
class FormData:
    """ما أدخله المتابِع — يُملأ من POST أو من متابعةٍ محفوظة."""

    follow_date: str = ""
    strengths: str = ""
    improvements: str = ""
    scores: dict[int, tuple[str, str]] = field(default_factory=dict)
    recommendations: list[tuple[str, str]] = field(default_factory=list)
    reviews: dict[str, tuple[str, str]] = field(default_factory=dict)


def _uuid_or_none(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def parse_post(post: Any) -> FormData:
    ratings = dict(RATINGS)
    scores = {}
    for number, _text in INDICATORS:
        rating = post.get(f"rating_{number}", "")
        scores[number] = (
            rating if rating in ratings else "",
            post.get(f"note_{number}", "").strip(),
        )
    ids = post.getlist("rec_id")
    texts = post.getlist("rec_text")
    reviews = {}
    for key in post.getlist("review_id"):
        status = post.get(f"review_status_{key}", "pending")
        reviews[key] = (
            status if status in ("done", "not_done") else "pending",
            post.get(f"review_note_{key}", "").strip(),
        )
    return FormData(
        follow_date=post.get("follow_date", ""),
        strengths=post.get("strengths", "").strip(),
        improvements=post.get("improvements", "").strip(),
        scores=scores,
        recommendations=[(i, t.strip()) for i, t in zip(ids, texts, strict=False)],
        reviews=reviews,
    )


def _clean_date(value: str) -> dt.date:
    try:
        day = dt.date.fromisoformat(value)
    except ValueError:
        raise FollowUpError("اختر تاريخ المتابعة.") from None
    if day > timezone.localdate():
        raise FollowUpError("تاريخ المتابعة لا يكون في المستقبل.")
    return day


def _save_scores(
    followup: SupervisorFollowUp, scores: Mapping[int, tuple[str, str]], user: CustomUser
) -> None:
    existing = {s.indicator_no: s for s in followup.scores.all()}
    for number, (rating, note) in scores.items():
        row = existing.get(number) or SupervisorFollowUpScore(
            school_id=followup.school_id,
            followup=followup,
            indicator_no=number,
            created_by=user,
        )
        row.rating, row.note, row.updated_by = rating, note, user
        row.save()


def _save_recommendations(
    followup: SupervisorFollowUp, rows: list[tuple[str, str]], user: CustomUser
) -> None:
    """يطابق بالمعرّف؛ ما غاب عن النموذج يُحذف حذفاً ناعماً."""
    existing = {r.pk: r for r in followup.recommendations.filter(is_deleted=False)}
    kept: set[uuid.UUID] = set()
    order = 0
    for raw_id, text in rows:
        if not text:
            continue
        order += 1
        key = _uuid_or_none(raw_id) or uuid.uuid4()
        row = existing.get(key)
        if row is None:
            # معرّفٌ يخصّ سجلاً آخر لا يُكتب فوقه.
            if SupervisorFollowUpRecommendation.all_objects.filter(pk=key).exists():
                key = uuid.uuid4()
            row = SupervisorFollowUpRecommendation(
                pk=key, school_id=followup.school_id, followup=followup, created_by=user
            )
        row.text, row.order, row.updated_by = text, order, user
        row.save()
        kept.add(row.pk)
    for key, row in existing.items():
        if key not in kept:
            row.updated_by = user
            row.delete()


def _save_reviews(
    followup: SupervisorFollowUp,
    previous: SupervisorFollowUp | None,
    reviews: Mapping[str, tuple[str, str]],
    user: CustomUser,
) -> None:
    for item in selectors.review_items(followup.school, followup, previous):
        if str(item.pk) not in reviews:
            continue
        status, note = reviews[str(item.pk)]
        touched = status != "pending" or bool(note)
        if not touched and item.reviewed_in_id != followup.pk:
            continue
        item.status, item.note = status, note
        item.reviewed_in = followup if touched else None
        item.updated_by = user
        item.save(update_fields=["status", "note", "reviewed_in", "updated_by", "updated_at"])


def save_follow_up(
    school: School,
    pk: uuid.UUID,
    *,
    supervisor_id: str,
    data: FormData,
    final: bool,
    request: HttpRequest,
) -> SupervisorFollowUp:
    """ينشئ المتابعةَ ذاتَ المعرّف `pk` أو يحدّثها، ويحفظ لقطةَ الحضور للفترة."""
    user: Any = request.user
    day = _clean_date(data.follow_date)
    try:
        with transaction.atomic():
            followup = (
                SupervisorFollowUp.all_objects.select_for_update()
                .filter(pk=pk, school=school)
                .first()
            )
            created = followup is None
            if followup is None:
                wanted = _uuid_or_none(supervisor_id)
                supervisor = selectors.supervisors(school).filter(pk=wanted).first()
                if supervisor is None:
                    raise FollowUpError("المشرف الإداري غير موجود في هذه المدرسة.")
                if selectors.open_draft(school, supervisor) is not None:
                    raise FollowUpError("لهذا المشرف مسودة مفتوحة — أكملها أو احذفها أولاً.")
                followup = SupervisorFollowUp(
                    pk=pk,
                    school=school,
                    supervisor=supervisor,
                    follower=user,
                    created_by=user,
                )
            elif followup.is_deleted:
                raise Http404
            previous = selectors.previous_saved(
                school, followup.supervisor, day, None if created else followup
            )
            summary = selectors.attendance_summary(school, followup.supervisor, day, previous)
            for name, value in summary.as_fields().items():
                setattr(followup, name, value)
            followup.follow_date = day
            followup.strengths = data.strengths
            followup.improvements = data.improvements
            # المحفوظةُ لا تعود مسودة.
            if final:
                followup.status = "saved"
            followup.updated_by = user
            followup.save()
            _save_scores(followup, data.scores, user)
            _save_recommendations(followup, data.recommendations, user)
            _save_reviews(followup, previous, data.reviews, user)
            _audit(followup, "create" if created else "update", request)
    except IntegrityError:
        raise FollowUpError("تعذّر الحفظ لتعارض مع سجل آخر — أعد فتح المتابعة.") from None
    return followup


def delete_follow_up(followup: SupervisorFollowUp, request: HttpRequest) -> None:
    user: Any = request.user
    with transaction.atomic():
        followup.updated_by = user
        followup.delete()
        _audit(followup, "delete", request)


def _audit(followup: SupervisorFollowUp, action: str, request: HttpRequest) -> None:
    AuditLog.log(
        user=request.user,
        action=action,
        model_name="other",
        object_id=followup.pk,
        object_repr=masked_repr(followup),
        changes={"status": followup.status},
        request=request,
    )

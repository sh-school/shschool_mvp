"""اقتراحُ متابعةٍ لتأخّر عودة الطالب (إدارةُ الأجنحة 4/4، قراراتُ المالك 2026-11-19).

حين يتجاوز مجموعُ دقائق تأخّر عودة الطالب في الأسبوع الدراسيّ حدَّاً قابلاً للضبط (افتراضُه 30) يُقترح على مشرف
جناحه متابعتُه. القرارُ للمشرف قبولاً أو رفضاً — **لا مخالفةَ آليّة** ولا أثرَ على وليّ الأمر. والموسومُ بخروجٍ
مبرَّرٍ دائم لا يُقترح له (`operations.exit_wing.week_totals` تُسقطه). والتوليدُ ثابتُ التكرار: اقتراحٌ واحدٌ
لكلّ طالبٍ في الأسبوع (قيدٌ فريد)، وما قُرّر لا يُمسّ.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from django.conf import settings
from django.utils import timezone

from core.audit_repr import masked_repr
from core.models import AuditLog, CustomUser, School
from operations.exit_wing import week_start_of, week_totals

from .models import ReturnLateSuggestion

logger = logging.getLogger(__name__)

#: الحدُّ الافتراضيّ لمجموع دقائق تأخّر العودة في الأسبوع؛ يُضبط بـ`WING_RETURN_LATE_THRESHOLD_MINUTES`.
DEFAULT_THRESHOLD_MINUTES = 30

_OPEN_STATES = ("proposed", "withdrawn")


class SuggestionError(ValueError):
    """رفضٌ بسببٍ يُعرض للمشرف كما هو."""


def threshold_minutes() -> int:
    """الحدُّ المضبوط (دقائق)؛ قيمةٌ فاسدةٌ أو غيرُ موجبةٍ تعود إلى الافتراض."""
    raw = getattr(settings, "WING_RETURN_LATE_THRESHOLD_MINUTES", DEFAULT_THRESHOLD_MINUTES)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_THRESHOLD_MINUTES
    return value if value > 0 else DEFAULT_THRESHOLD_MINUTES


def generate_for_week(
    school: School, today: dt.date | None = None, threshold: int | None = None
) -> dict[str, int]:
    """يجعل اقتراحات أسبوع `today` غيرَ المقرَّرة مطابقةً للعدّاد الآن — ثابتُ التكرار.

    يُنشئ لمن **تجاوز** الحدَّ (أكبرُ منه لا يساويه)، ويحدّث دقائقَ المقترَح، ويسحب من نزل عن الحدّ بعد
    تصحيحٍ أو وسمِ خروجٍ مبرَّر. وما اعتُمد أو رُدَّ يبقى قرارُه فلا يُنشأ له بديل.
    """
    day = today or timezone.localdate()
    limit = threshold if threshold is not None else threshold_minutes()
    week = week_start_of(day)
    over = {
        sid: row for sid, row in week_totals(school, None, week).items() if row.late_minutes > limit
    }
    existing = {
        s.student_id: s for s in ReturnLateSuggestion.objects.filter(school=school, week_start=week)
    }
    stats = {"created": 0, "updated": 0, "withdrawn": 0}
    for sid, row in over.items():
        current = existing.get(sid)
        if current is None:
            ReturnLateSuggestion.objects.create(
                school=school,
                student_id=sid,
                week_start=week,
                late_minutes=row.late_minutes,
                exit_count=row.count,
            )
            stats["created"] += 1
        elif current.status in _OPEN_STATES and (
            current.late_minutes != row.late_minutes
            or current.exit_count != row.count
            or current.status == "withdrawn"
        ):
            # مشروطٌ بحالةٍ غيرِ مقرَّرة فلا يطغى على قرار مشرفٍ جرى بين القراءة والكتابة.
            stats["updated"] += ReturnLateSuggestion.objects.filter(
                pk=current.pk, status__in=_OPEN_STATES
            ).update(late_minutes=row.late_minutes, exit_count=row.count, status="proposed")
    for sid, suggestion in existing.items():
        if sid not in over and suggestion.status == "proposed":
            stats["withdrawn"] += ReturnLateSuggestion.objects.filter(
                pk=suggestion.pk, status="proposed"
            ).update(status="withdrawn")
    return stats


def queue_for(school: School, scope: Any) -> list[ReturnLateSuggestion]:
    """اقتراحاتُ متابعة طلبة جناح المشرف التي تنتظر قرارَه، الأعلى تأخّراً أولاً."""
    qs = scope.narrow(
        ReturnLateSuggestion.objects.filter(school=school, status="proposed").select_related(
            "student"
        ),
        "student_id",
    ).order_by("-late_minutes", "student__full_name")
    return list(qs)


def accept(suggestion_id: Any, by: CustomUser, scope: Any) -> ReturnLateSuggestion:
    return _decide(suggestion_id, by, scope, "accepted")


def dismiss(suggestion_id: Any, by: CustomUser, scope: Any) -> ReturnLateSuggestion:
    return _decide(suggestion_id, by, scope, "dismissed")


def _decide(suggestion_id: Any, by: CustomUser, scope: Any, outcome: str) -> ReturnLateSuggestion:
    """قرارُ المشرف: تحديثٌ مشروطٌ بحالة «مقترح» فالقرارُ الثاني لا يطغى على الأول."""
    suggestion = ReturnLateSuggestion.objects.filter(
        pk=suggestion_id, school=by.get_school()
    ).first()
    if suggestion is None or not scope.covers_student(suggestion.student_id):
        raise SuggestionError("الاقتراحُ غيرُ موجودٍ في جناحك.")
    if suggestion.status == outcome:
        return suggestion
    if suggestion.status != "proposed":
        raise SuggestionError("لم يعد هذا الاقتراحُ بانتظار قرار.")
    done = ReturnLateSuggestion.objects.filter(pk=suggestion.pk, status="proposed").update(
        status=outcome, decided_by=by, decided_at=timezone.now()
    )
    if not done:
        raise SuggestionError("قُرّر هذا الاقتراحُ للتوّ.")
    suggestion.refresh_from_db()
    AuditLog.log(
        user=by,
        action="update",
        model_name="other",
        object_id=suggestion.pk,
        object_repr=masked_repr(suggestion),
        changes={"return_late_suggestion": outcome},
        school=suggestion.school,
    )
    return suggestion

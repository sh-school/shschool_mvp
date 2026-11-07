"""تجهيزُ الإجراء ومتابعتُه واعتمادُه على المخالفة — طبقةُ الخدمة (W-20261108-005).

التسلسل: يُسجَّل المخالفةَ المعلّمُ بلا إلزامٍ باختيار إجراء ← يُحسب الاقتراحُ من السلّم (`action_proposal`)
← يجهّز مشرفُ الجناح تعهّداً خطّيّاً أو إحالةً لطلاب جناحه فقط ← يتابع منسّقُ شؤون الطلبة ويعتمد.
فصلُ المهام: من سجّل المخالفةَ لا يعتمدها؛ فإن كان المسجِّلُ المنسّقَ نفسَه اعتمدها النائبُ الإداريّ.
لا إشعارَ آليّاً لوليّ الأمر هنا، ولا يُكتب `action_taken` (ما يصل الأسرة) إلّا عند الاعتماد.
مسارُ لجنة الضبط (الدرجة الرابعة والإيقاف والتصعيد) في `services.py` بلا تغيير.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from core.capabilities import has_capability
from core.models import AuditLog
from wings.scope import student_scope

from .action_proposal import propose
from .models import BehaviorInfraction

PREPARE = "behavior.prepare_action"
APPROVE = "behavior.approve_action"
SPECIALIST_LIST = "behavior.specialist_list"

COORDINATOR_ROLE = "student_affairs_coordinator"
DEPUTY_ROLE = "vice_admin"

_FIELDS = (
    "suggested_action",
    "suggested_source",
    "suggested_step",
    "specialist_listed",
    "prepared_kind",
    "followup_status",
    "approved_action",
    "action_taken",
)


def _snapshot(infraction: BehaviorInfraction) -> dict[str, Any]:
    return {name: getattr(infraction, name) for name in _FIELDS}


def _audit(user: Any, infraction: BehaviorInfraction, event: str, before: dict[str, Any]) -> None:
    """سطرُ تدقيقٍ لكلّ اقتراحٍ وتجهيزٍ ومتابعةٍ واعتماد: من ومتى (الطابعُ الزمنيّ للسجلّ) وما قبل وبعد."""
    after = _snapshot(infraction)
    changed = {
        k: {"before": before[k], "after": after[k]} for k in _FIELDS if before[k] != after[k]
    }
    AuditLog.objects.create(
        user=user,
        school=infraction.school,
        action="update",
        model_name="BehaviorInfraction",
        object_id=str(infraction.pk),
        object_repr=f"مخالفة سلوكية — {event}"[:300],
        changes={"event": event, "fields": changed},
    )


def _save(infraction: BehaviorInfraction, fields: list[str]) -> None:
    infraction.save(update_fields=fields)


def suggest_for(infraction: BehaviorInfraction, actor: Any) -> None:
    """يحسب الاقتراحَ من السلّم ويحفظه ويدوّنه؛ الدرجتان 3 و4 بلا اقتراح (لا نصَّ مستخرجاً لهما)."""
    category = infraction.violation_category
    proposal = propose(category.code, infraction.escalation_step) if category else None
    if proposal is None:
        return
    before = _snapshot(infraction)
    infraction.suggested_action = proposal.text[:1000]
    infraction.suggested_source = proposal.source[:200]
    infraction.suggested_step = proposal.step
    infraction.specialist_listed = proposal.specialist
    _save(
        infraction,
        ["suggested_action", "suggested_source", "suggested_step", "specialist_listed"],
    )
    _audit(actor, infraction, "اقتراح الإجراء من السلّم", before)


@transaction.atomic
def prepare_action(infraction: BehaviorInfraction, user: Any, kind: str) -> BehaviorInfraction:
    """مشرفُ الجناح يجهّز تعهّداً خطّيّاً أو إحالةً — لطلاب جناحه وحدَهم، بلا استدعاءٍ ولا إدارة."""
    if not has_capability(user, PREPARE):
        raise PermissionDenied("لا تملك تجهيز الإجراء.")
    if not student_scope(user, infraction.school).covers_student(infraction.student_id):
        raise PermissionDenied("الطالب خارج جناحك.")
    if kind not in dict(BehaviorInfraction.PREPARED_KINDS):
        raise ValueError("لا يُجهَّز إلّا تعهّدٌ خطّيّ أو إحالة.")
    before = _snapshot(infraction)
    infraction.prepared_kind = kind
    infraction.prepared_by = user
    infraction.prepared_at = timezone.now()
    _save(infraction, ["prepared_kind", "prepared_by", "prepared_at"])
    _audit(user, infraction, "تجهيز الإجراء", before)
    return infraction


def _require_approver(infraction: BehaviorInfraction, user: Any) -> None:
    """حارسُ الاعتماد والمتابعة: القدرةُ، وفصلُ المهام (من سجّل لا يعتمد، والنائبُ بديلُ المنسّق المسجِّل فقط)."""
    if not has_capability(user, APPROVE):
        raise PermissionDenied("لا تملك متابعة الإجراء واعتماده.")
    if infraction.reported_by_id == user.pk:
        raise PermissionDenied("من سجّل المخالفة لا يعتمد إجراءها.")
    reporter_role = infraction.reported_by.get_role() if infraction.reported_by else ""
    wanted = DEPUTY_ROLE if reporter_role == COORDINATOR_ROLE else COORDINATOR_ROLE
    if user.get_role() != wanted:
        raise PermissionDenied(
            "اعتمادُ مخالفةٍ سجّلها المنسّقُ للنائب الإداريّ."
            if wanted == DEPUTY_ROLE
            else "الاعتمادُ لمنسّق شؤون الطلبة."
        )


@transaction.atomic
def record_followup(infraction: BehaviorInfraction, user: Any, status: str) -> BehaviorInfraction:
    """متابعةُ الإجراء: تمّ، لم يتمّ، جزئيّاً — كمتابعة الغياب."""
    _require_approver(infraction, user)
    if status not in dict(BehaviorInfraction.FOLLOWUP_STATUSES):
        raise ValueError("حالةُ المتابعة غير معروفة.")
    before = _snapshot(infraction)
    infraction.followup_status = status
    infraction.followed_by = user
    infraction.followed_at = timezone.now()
    _save(infraction, ["followup_status", "followed_by", "followed_at"])
    _audit(user, infraction, "متابعة الإجراء", before)
    return infraction


@transaction.atomic
def approve_action(
    infraction: BehaviorInfraction, user: Any, action_text: str = ""
) -> BehaviorInfraction:
    """اعتمادُ الإجراء — المقترحُ إن لم يُكتب غيرُه. وبه وحدَه يُكتب `action_taken` الذي تراه الأسرة."""
    _require_approver(infraction, user)
    if infraction.approved_at is not None:
        raise ValueError("اعتُمد إجراءُ هذه المخالفة من قبل.")
    text = (action_text or infraction.suggested_action).strip()
    if not text:
        raise ValueError("اكتب الإجراء المعتمد: لا اقتراحَ للدرجتين 3 و4.")
    before = _snapshot(infraction)
    infraction.approved_action = text[:1000]
    infraction.approved_by = user
    infraction.approved_at = timezone.now()
    infraction.action_taken = infraction.approved_action
    _save(
        infraction,
        ["approved_action", "approved_by", "approved_at", "action_taken"],
    )
    _audit(user, infraction, "اعتماد الإجراء", before)
    return infraction


def approval_queue(user: Any, school: Any) -> QuerySet[BehaviorInfraction]:
    """المخالفاتُ التي يحقّ لهذا المستخدم متابعتُها أو اعتمادُها — بلا ما سجّله هو، وبقاعدة النائب."""
    if not has_capability(user, APPROVE):
        return BehaviorInfraction.objects.none()
    reporter_is_coordinator = {"reported_by__memberships__role__name": COORDINATOR_ROLE}
    qs = BehaviorInfraction.objects.filter(school=school).exclude(reported_by=user)
    if user.get_role() == DEPUTY_ROLE:
        qs = qs.filter(**reporter_is_coordinator, reported_by__memberships__is_active=True)
    else:
        qs = qs.exclude(
            reported_by__memberships__role__name=COORDINATOR_ROLE,
            reported_by__memberships__is_active=True,
        )
    return qs.select_related("student", "violation_category").distinct().order_by("-created_at")


def prepare_queue(user: Any, school: Any) -> QuerySet[BehaviorInfraction]:
    """مخالفاتُ طلاب جناح المشرف وحدَهم عبر wings/scope.py — ما لم يجهَّز له إجراءٌ بعدُ أولاً."""
    if not has_capability(user, PREPARE):
        return BehaviorInfraction.objects.none()
    qs = student_scope(user, school).narrow(BehaviorInfraction.objects.filter(school=school))
    return qs.select_related("student", "violation_category").order_by("prepared_at", "-created_at")


def specialist_queue(user: Any, school: Any) -> QuerySet[BehaviorInfraction]:
    """قائمةُ الاختصاصيَّين: الإحالاتُ عند خطوات السلّم التي تنصّ عليهما — يدرسان الحالة ولا يعتمدان."""
    if not has_capability(user, SPECIALIST_LIST):
        return BehaviorInfraction.objects.none()
    return (
        BehaviorInfraction.objects.filter(school=school, specialist_listed=True)
        .select_related("student", "violation_category")
        .order_by("-created_at")
    )

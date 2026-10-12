"""قرارُ الانتقال الداخلي بين الشعب: من يقرّر، وأيُّ انتقالِ حالةٍ يجوز، والنقلُ المباشر (W-20261001-017، D-343م).

المنسّق يقدّم الطلب، والمدير أو النائب الإداري يعتمده ثم يُتمّه، ولهما النقل المباشر بلا انتظار اعتماد أحد.
وحدةٌ مستقلّة عن `services.py` و`views.py` حفاظاً على سقف حجم الملف؛ والتنفيذ الفعليُّ للنقل في
`internal_transfer.complete_internal` (يغلق التسجيل القديم وينشئ الجديد بلا حذف، والغيابُ وما يتبعه يبقى مع الطالب).
مستوياتُ الاعتماد 3..7 في نموذج 03 معلّقةٌ بسؤال المالك فلا حالاتٍ لها هنا؛ ويُضاف جدولُ موافقاتٍ متعدّد المراحل لاحقاً إن طلبها.
"""

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from core.capabilities import has_capability

APPROVE_CAPABILITY = "student_affairs.transfer_approve"

#: الحالةُ الحاليّة ← الحالاتُ المسموح الانتقالُ إليها. «مكتمل» لا يُبلغ إلا من «موافق عليه».
INTERNAL_TRANSITIONS = {
    "pending": {"approved", "rejected", "cancelled"},
    "approved": {"completed", "cancelled"},
}


def may_decide(user) -> bool:
    """أيملك المستخدمُ اعتمادَ الانتقال الداخلي وإتمامَه ونقلَه المباشر؟ (المنسّق لا)."""
    return has_capability(user, APPROVE_CAPABILITY)


def _append_note(transfer, actor, notes: str) -> None:
    if notes:
        separator = "\n---\n" if transfer.notes else ""
        transfer.notes += f"{separator}[{actor.full_name}]: {notes}"


@transaction.atomic
def decide_internal(transfer, action: str, notes: str, actor) -> None:
    """يطبّق قراراً على انتقالٍ داخليّ، أو يرفع ValueError/PermissionDenied قبل أيّ كتابة.

    الاعتماد والرفض والإتمام لمن يملك القدرة وحدَه؛ ولمقدّم الطلب وحدَه إلغاءُ طلبه ما دام «قيد الانتظار».
    والرفضُ بلا سببٍ يُردّ. والاعتمادُ والإتمام يتحقّقان من الهدف (شعبةٌ أخرى بنفس الصفّ والعام)،
    فلا يُعتمد طلبٌ لن يُنفَّذ، ولا يُحفظ «مكتمل» بلا نقل.
    """
    from .internal_transfer import complete_internal, internal_target_error

    if transfer.direction != "internal":
        raise ValueError("هذا المسار للانتقال الداخلي بين الشعب وحده.")
    own_pending_cancel = (
        action == "cancelled"
        and transfer.status == "pending"
        and transfer.created_by_id == getattr(actor, "pk", None)
    )
    if not own_pending_cancel and not may_decide(actor):
        raise PermissionDenied("اعتماد الانتقال الداخلي للمدير أو النائب الإداري.")
    if action not in INTERNAL_TRANSITIONS.get(transfer.status, set()):
        raise ValueError(
            f"لا يجوز الإجراء «{action}» على طلبٍ بحالة «{transfer.get_status_display()}»."
        )
    if action == "rejected" and not (notes or "").strip():
        raise ValueError("يجب ذكر سبب الرفض.")
    if action in ("approved", "completed"):
        error = internal_target_error(transfer)
        if error:
            raise ValueError(error)
    if action == "completed":
        complete_internal(transfer, actor)

    transfer.status = action
    transfer.decided_by = actor
    transfer.decided_at = timezone.now()
    transfer.updated_by = actor
    _append_note(transfer, actor, notes)
    transfer.save(
        update_fields=["status", "notes", "decided_by", "decided_at", "updated_by", "updated_at"]
    )


def decide_and_audit(transfer, action: str, notes: str, actor, school) -> str:
    """`decide_internal` ثم سجلُّ التدقيق؛ يعيد وسمَ الحالة الجديدة للرسالة."""
    from .services import StudentService

    decide_internal(transfer, action, notes, actor)
    StudentService.audit_student_event(school, actor, transfer.student, f"transfer_{action}")
    return transfer.get_status_display()


def detail_flags(transfer, user) -> dict:
    """ما تعرضه صفحةُ التفاصيل: أيقرّر المستخدمُ، أم يلغي طلبَه المعلَّق وحدَه (مقدّمُ الطلب، D-343م)."""
    internal = transfer.direction == "internal"
    can_decide = not internal or may_decide(user)
    own_pending = transfer.status == "pending" and transfer.created_by_id == user.pk
    return {"can_decide": can_decide, "can_cancel_own": internal and not can_decide and own_pending}


@transaction.atomic
def move_directly(transfer, actor, school):
    """نقلٌ مباشرٌ بلا طلبٍ معلَّق: يُنفَّذ ويُحفظ الطلبُ «مكتملاً» بمن نفّذه ومتى، في معاملةٍ واحدة.

    `transfer` طلبٌ غيرُ محفوظٍ من `internal_transfer.build_request`. يُرفض قبل أيّ كتابةٍ لمن لا قدرة له،
    ولهدفٍ غيرِ صالحٍ أو تاريخٍ مستقبليّ (يرفعهما `complete_internal`).
    """
    from .internal_transfer import complete_internal
    from .services import StudentService

    if not may_decide(actor):
        raise PermissionDenied("النقل المباشر للمدير أو النائب الإداري.")
    complete_internal(transfer, actor)
    transfer.status = "completed"
    transfer.decided_by = actor
    transfer.decided_at = timezone.now()
    _append_note(transfer, actor, "نقل مباشر بلا طلب معلَّق (D-343م).")
    transfer.save()
    StudentService.audit_student_event(school, actor, transfer.student, "transfer_completed")
    return transfer

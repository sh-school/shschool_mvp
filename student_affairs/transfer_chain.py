"""سلسلةُ اعتماد طلب الانتقال الوارد والصادر (نموذج 07): تدقيقٌ ← اعتمادٌ ← تشعيبٌ ← إدخال (W-20261001-018).

الانتقالُ الداخلي خارج هذه الوحدة (`transfer_decision.py`). وحدةٌ مستقلّة عن `views.py` حفاظاً على سقف حجم الملف.
المراحلُ الأربع تُسجَّل بمنفّذها ووقتها على `StudentTransfer`، و«مكتمل» لا يُبلغ إلا بعد المراحل الأربع كلّها.
"""

from django.db import transaction
from django.utils import timezone

#: مستنداتُ التسجيل الأحد عشر بنصّ النموذج (تعميم 1 لسنة 2024)، والمفتاحُ ترتيبُها 1..11.
REQUIRED_DOCUMENTS = [
    ("1", "البطاقة الشخصية"),
    ("2", "جواز السفر"),
    ("3", "شهادة الميلاد"),
    ("4", "الرقم الشخصي القطري"),
    ("5", "إقامة سارية المفعول"),
    ("6", "بطاقة تصريح الإقامة المؤقتة"),
    ("7", "صورة شخصية (عدد 2)"),
    ("8", "شهادة أو فاتورة كهرماء"),
    ("9", "شهادة التقييم الصحي"),
    ("10", "شهادة عمل ولي الأمر"),
    ("11", "شهادة نجاح نهاية العام الدراسي"),
]

CHAIN_DIRECTIONS = {"in", "out"}
#: الإجراءُ ← (الحالات المسموحة، المرحلة التي يُسجَّل فيها المنفّذ)
CHAIN_ACTIONS = ("review", "approved", "rejected", "place", "enter", "completed", "cancelled")
STAGES = (
    ("reviewed", "التدقيق"),
    ("approved", "اعتماد الطلب"),
    ("placed", "التشعيب"),
    ("entered", "الإدخال"),
)


def is_chain(transfer) -> bool:
    return transfer.direction in CHAIN_DIRECTIONS


def stage_rows(transfer) -> list[dict]:
    """المراحلُ الأربع بمنفّذها وتاريخها لعرض الصفحة."""
    return [
        {
            "label": label,
            "by": getattr(transfer, f"{key}_by"),
            "at": getattr(transfer, f"{key}_at"),
        }
        for key, label in STAGES
    ]


def document_rows(transfer) -> list[dict]:
    checked = set(transfer.documents_checked or [])
    return [
        {"key": k, "label": t, "checked": k in checked, "id": f"f-doc-{k}"}
        for k, t in REQUIRED_DOCUMENTS
    ]


def available_actions(transfer) -> list[tuple[str, str]]:
    """الإجراءاتُ المتاحة الآن لحالة الطلب ومراحله (للقائمة في الصفحة)."""
    st = transfer.status
    out = []
    if st == "pending":
        if not transfer.reviewed_at:
            out.append(("review", "تدقيق المستندات"))
        else:
            out += [("approved", "اعتماد الطلب (مقبول)"), ("rejected", "رفض")]
    elif st == "approved":
        if not transfer.placed_at:
            out.append(("place", "تشعيب"))
        elif not transfer.entered_at:
            out.append(("enter", "إدخال في النظام الداخلي"))
        else:
            out.append(("completed", "إتمام الانتقال"))
    if st in ("pending", "approved"):
        out.append(("cancelled", "إلغاء"))
    return out


def _stamp(transfer, key: str, actor, now) -> None:
    setattr(transfer, f"{key}_by", actor)
    setattr(transfer, f"{key}_at", now)


def _deactivate_outgoing(transfer) -> None:
    from core.models.academic import StudentEnrollment
    from core.models.access import Membership

    school = transfer.school
    Membership.objects.filter(
        user=transfer.student, school=school, role__name="student", is_active=True
    ).update(is_active=False)
    StudentEnrollment.objects.filter(
        student=transfer.student, class_group__school=school, is_active=True
    ).update(is_active=False)


def _check_rules(
    transfer, action: str, notes: str, documents: list[str], missing_reason: str
) -> None:
    st = transfer.status
    if action in ("cancelled",) and st not in ("pending", "approved"):
        raise ValueError("لا يُلغى إلا طلبٌ قيد الانتظار أو موافقٌ عليه.")
    if action == "review":
        if st != "pending" or transfer.reviewed_at:
            raise ValueError("التدقيق لمرّةٍ واحدة على طلبٍ قيد الانتظار.")
        valid = {k for k, _ in REQUIRED_DOCUMENTS}
        if not set(documents) <= valid:
            raise ValueError("مستندٌ غير معروف في قائمة التدقيق.")
        if len(set(documents)) < len(REQUIRED_DOCUMENTS) and not missing_reason.strip():
            raise ValueError("المستندات ناقصة: أكمل الـ11 أو اذكر سبب النقص.")
    elif action in ("approved", "rejected"):
        if st != "pending":
            raise ValueError("الاعتماد والرفض لطلبٍ قيد الانتظار.")
        if not transfer.reviewed_at:
            raise ValueError("لا اعتمادَ ولا رفضَ قبل التدقيق.")
        if action == "rejected" and not (notes or "").strip():
            raise ValueError("يجب ذكر سبب الرفض.")
    elif action == "place":
        if st != "approved" or transfer.placed_at:
            raise ValueError("التشعيب لطلبٍ موافقٍ عليه ولمرّةٍ واحدة.")
    elif action == "enter":
        if st != "approved" or not transfer.placed_at or transfer.entered_at:
            raise ValueError("الإدخال بعد التشعيب ولمرّةٍ واحدة.")
    elif action == "completed":
        if st != "approved" or not (
            transfer.reviewed_at and transfer.placed_at and transfer.entered_at
        ):
            raise ValueError("لا إتمامَ قبل التدقيق والاعتماد والتشعيب والإدخال.")
    elif action != "cancelled":
        raise ValueError("إجراءٌ غير معروف.")


@transaction.atomic
def apply_chain_action(
    transfer, action: str, notes: str, actor, documents=None, missing_reason: str = ""
) -> str:
    """يطبّق إجراءً من السلسلة على انتقالٍ وارد/صادر أو يرفع ValueError قبل أيّ كتابة؛ يعيد وسمَ الإجراء للتدقيق."""
    from .models import StudentTransfer

    if not is_chain(transfer):
        raise ValueError("هذا المسار للانتقال الوارد والصادر وحدَه.")
    # قفلٌ على الصفّ وإعادةُ قراءته: لا يتجاوز إجراءان متزامنان الترتيب
    locked = StudentTransfer.objects.select_for_update().get(pk=transfer.pk)
    for field in (
        "status",
        "reviewed_by_id",
        "reviewed_at",
        "approved_by_id",
        "approved_at",
        "placed_by_id",
        "placed_at",
        "entered_by_id",
        "entered_at",
        "documents_checked",
    ):
        setattr(transfer, field, getattr(locked, field))
    documents = list(documents or [])
    _check_rules(transfer, action, notes, documents, missing_reason)

    now = timezone.now()
    fields = ["status", "notes", "updated_by", "updated_at"]
    if action == "review":
        transfer.documents_checked = sorted(set(documents), key=int)
        transfer.documents_missing_reason = (missing_reason or "").strip()[:500]
        _stamp(transfer, "reviewed", actor, now)
        fields += ["documents_checked", "documents_missing_reason", "reviewed_by", "reviewed_at"]
    elif action == "approved":
        _stamp(transfer, "approved", actor, now)
        transfer.status = "approved"
        fields += ["approved_by", "approved_at"]
    elif action == "place":
        _stamp(transfer, "placed", actor, now)
        fields += ["placed_by", "placed_at"]
    elif action == "enter":
        _stamp(transfer, "entered", actor, now)
        fields += ["entered_by", "entered_at"]
    else:  # rejected / completed / cancelled
        transfer.status = action
        if action == "completed" and transfer.direction == "out":
            _deactivate_outgoing(transfer)
    if notes:
        separator = "\n---\n" if transfer.notes else ""
        transfer.notes += f"{separator}[{actor.full_name}]: {notes}"
    transfer.updated_by = actor
    transfer.save(update_fields=fields)
    return f"transfer_{action}"

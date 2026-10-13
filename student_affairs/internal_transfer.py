"""الانتقال الداخلي بين شعب المدرسة — التحقّق من الهدف والإتمام الذرّي (W-20261005-008، D-201م).

وحدةٌ مستقلّة عن `services.py` حفاظاً على سقف حجم الملف؛ تستدعيها `TransferService.review_transfer` والعرض.
"""

from django.db import transaction
from django.utils import timezone

from core.audit_repr import masked_repr
from core.models.academic import StudentEnrollment
from core.models.audit import AuditLog


def internal_target_error(transfer, today=None) -> str:
    """سببُ رفض الهدف في الانتقال الداخلي، أو «» إن صحّ — المصدرُ الواحد للنموذج والإتمام (D-201م).

    الهدفُ شعبةٌ أخرى بنفس الصفّ والمدرسة والعام (صفّ الطالب الحالي لا الصفّ المكتوب في الطلب).
    """
    target = transfer.to_class_group
    if target is None:
        return "الشعبة المنقول إليها مطلوبة في الانتقال الداخلي."
    current = StudentEnrollment.objects.current_of(transfer.student, transfer.school)
    if current is None:
        return "الطالب بلا تسجيل نشط في شعبة — لا انتقال داخليّ له."
    source = current.class_group
    if target.school_id != transfer.school_id or not target.is_active:
        return "الشعبة المنقول إليها ليست شعبةً نشطة في هذه المدرسة."
    if target.pk == source.pk:
        return "الشعبة المنقول إليها هي شعبة الطالب الحالية."
    if target.grade != source.grade or target.academic_year != source.academic_year:
        return "الانتقال الداخلي يكون إلى شعبةٍ من الصفّ نفسه والعام نفسه."
    return ""


@transaction.atomic
def complete_internal(transfer, actor):
    """إتمامُ انتقالٍ داخليّ ذرّيّاً: يُغلق التسجيلَ القديم وينشئ الجديد بتاريخ الانتقال، بلا حذف (W-20261005-008).

    الغيابُ والإدخالاتُ والقراراتُ والأعذارُ والتنبيهاتُ مفتاحُها الطالبُ لا الشعبة، فتبقى كلُّها مع الطالب (D-201م).
    ويُرفض قبل أيّ كتابةٍ: هدفٌ غيرُ صالح، أو تاريخٌ في المستقبل (لا يغيب الطالبُ عن الشعبتين).
    """
    error = internal_target_error(transfer)
    if error:
        raise ValueError(error)
    if transfer.transfer_date > timezone.localdate():
        raise ValueError("تاريخ الانتقال في المستقبل — يُتمّ الانتقال الداخلي يوم نفاذه أو بعده.")
    current = StudentEnrollment.objects.current_of(transfer.student, transfer.school)
    source = current.class_group
    current.is_active = False
    current.save(update_fields=["is_active"])
    enrollment = StudentEnrollment.objects.create(
        student=transfer.student,
        class_group=transfer.to_class_group,
        enrolled_at=transfer.transfer_date,
    )
    AuditLog.log(
        user=actor,
        action="update",
        model_name="other",
        object_id=enrollment.pk,
        object_repr=f"انتقال داخليّ: {source.short_label} ← {transfer.to_class_group.short_label}",
        changes={
            "student": masked_repr(transfer.student),
            "from": source.short_label,
            "to": transfer.to_class_group.short_label,
            "date": transfer.transfer_date.isoformat(),
        },
        school=transfer.school,
    )
    return enrollment


def build_request(school, student, data, year, actor):
    """يبني طلب الانتقال من بيانات النموذج ولا يحفظه، ويُرجع `(الطلب، سببُ الرفض أو "")` — الداخليُّ يُتحقَّق هدفُه قبل الحفظ."""
    from .models import StudentTransfer
    from .selectors import active_class

    internal = data["direction"] == "internal"
    transfer = StudentTransfer(
        school=school,
        student=student,
        direction=data["direction"],
        other_school_name=school.name if internal else data["other_school_name"],
        from_grade=data.get("from_grade", ""),
        to_grade=data.get("to_grade", ""),
        to_class_group=active_class(school, data["to_class_group_id"]) if internal else None,
        transfer_date=data["transfer_date"],
        reason=data.get("reason", ""),
        academic_year=year,
        created_by=actor,
        updated_by=actor,
    )
    return transfer, (internal_target_error(transfer) if internal else "")

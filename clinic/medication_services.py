"""
clinic/medication_services.py — قواعدُ صرف الدواء في العيادة (W-20261020-036)
══════════════════════════════════════════════════════════════════════════════
الصرفُ لا يقع إلا من كتالوجٍ اعتمدته جهةٌ طبّيّة وبموافقةِ وليّ أمرٍ سارية. ولا مسارَ لصرفٍ من نصٍّ حرّ:
الواجهةُ الوحيدةُ `MedicationService.dispense` تأخذ بندَ كتالوجٍ لا نصّاً، وترفض بخطأٍ يسمّي السبب.

حالةُ الموافقة ثلاثٌ: `approved` (سارية)، `expired` (انتهت مدّتُها)، `absent` (لا موافقة، أو سُحبت كلُّها).
والتدقيقُ لكلّ صرفٍ بمعرّفاتٍ فقط — لا اسمَ دواءٍ ولا طالبٍ ولا نصّاً صحّيّاً.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

if TYPE_CHECKING:
    from clinic.models import ClinicVisit, MedicationCatalogItem, VisitMedication

CONSENT_APPROVED = "approved"
CONSENT_EXPIRED = "expired"
CONSENT_ABSENT = "absent"

_CONSENT_MESSAGES = {
    CONSENT_EXPIRED: "انتهت موافقة وليّ الأمر على هذا الدواء.",
    CONSENT_ABSENT: "لا موافقة من وليّ الأمر على هذا الدواء.",
}


class MedicationNotAllowed(Exception):  # noqa: N818 — حالةُ منعٍ يقرؤها المستدعي لا عطلٌ
    """منعُ صرف — `code` رمزٌ ثابتٌ للاختبار والواجهة، والرسالةُ للممرّض."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class MedicationService:
    @staticmethod
    def consent_status(student, item: MedicationCatalogItem, now=None):
        """`(الحالة، الموافقة السارية أو None)` لطالبٍ وبند — الموافقةُ المسحوبةُ لا تُحسب."""
        from clinic.models import GuardianMedicationConsent

        now = now or timezone.now()
        live = GuardianMedicationConsent.objects.filter(
            student=student, catalog_item=item, revoked_at__isnull=True
        ).order_by("-expires_at")
        valid = live.filter(expires_at__gt=now, granted_at__lte=now).first()
        if valid is not None:
            return CONSENT_APPROVED, valid
        if live.exists():
            return CONSENT_EXPIRED, None
        return CONSENT_ABSENT, None

    @staticmethod
    @transaction.atomic
    def dispense(
        visit: ClinicVisit, item: MedicationCatalogItem, nurse, now=None
    ) -> VisitMedication:
        """يصرف بنداً من الكتالوج في زيارة، أو يرفع `MedicationNotAllowed` بسبب المنع."""
        from clinic.models import VisitMedication
        from core.models import AuditLog

        now = now or timezone.now()
        if item.school_id != visit.school_id:
            raise MedicationNotAllowed("foreign_item", "الدواء ليس في كتالوج هذه المدرسة.")
        if not item.is_dispensable:
            raise MedicationNotAllowed("not_approved", "الدواء غير معتمَدٍ سريرياً أو غير مفعَّل.")

        status, consent = MedicationService.consent_status(visit.student, item, now)
        if consent is None:
            raise MedicationNotAllowed(f"consent_{status}", _CONSENT_MESSAGES[status])

        dispensing = VisitMedication.objects.create(
            school=visit.school,
            visit=visit,
            catalog_item=item,
            dose=item.standard_dose,
            consent=consent,
            dispensed_by=nurse,
            dispensed_at=now,
        )
        AuditLog.log(
            user=nurse,
            action="create",
            model_name="VisitMedication",
            object_id=dispensing.pk,
            object_repr="صرف دواء من الكتالوج المعتمَد",
            changes={
                "visit_id": str(visit.pk),
                "catalog_item_id": str(item.pk),
                "consent_id": str(consent.pk),
            },
            school=visit.school,
        )
        return dispensing

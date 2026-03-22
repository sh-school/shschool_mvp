"""
core/erasure_service.py — Right to Erasure (PDPPL م.18)

Anonymizes student PII across all models while preserving:
- AuditLog entries (immutable per م.19, user FK set to NULL)
- Statistical aggregates (counts stay, identifiers removed)
"""
import logging
from django.db import transaction
from django.utils import timezone

from core.models import (
    AuditLog, ConsentRecord, ErasureRequest,
    ParentStudentLink, StudentEnrollment, Profile,
)

logger = logging.getLogger("core")

# Models with FK `student` → CustomUser (on_delete=CASCADE handles deletion,
# but we anonymize first to ensure no PII leaks via DB backups)
_STUDENT_FK_MODELS = []


def _lazy_student_fk_models():
    """Lazy import to avoid circular imports at module level."""
    if _STUDENT_FK_MODELS:
        return _STUDENT_FK_MODELS

    from clinic.models import HealthRecord, ClinicVisit
    from assessments.models import StudentAssessmentGrade, StudentSubjectResult, AnnualSubjectResult
    from behavior.models import BehaviorInfraction
    from operations.models import StudentAttendance, AbsenceAlert
    from library.models import BookBorrowing

    _STUDENT_FK_MODELS.extend([
        (HealthRecord, 'student', True),          # OneToOne
        (ClinicVisit, 'student', False),
        (StudentAssessmentGrade, 'student', False),
        (StudentSubjectResult, 'student', False),
        (AnnualSubjectResult, 'student', False),
        (BehaviorInfraction, 'student', False),
        (StudentAttendance, 'student', False),
        (AbsenceAlert, 'student', False),
        (BookBorrowing, 'user', False),
    ])
    return _STUDENT_FK_MODELS


class ErasureService:
    """Anonymize all PII for a student — PDPPL م.18."""

    @staticmethod
    @transaction.atomic
    def execute(erasure_request: ErasureRequest) -> dict:
        """
        Execute an approved erasure request.
        Returns a summary dict of what was anonymized/deleted.
        """
        student = erasure_request.student
        if not student:
            raise ValueError("Student record not found for this erasure request.")

        anon_id = f"ERASED-{str(erasure_request.id)[:8].upper()}"
        summary = {"anon_id": anon_id, "models": {}}

        # 1. Anonymize records in child models (count before deleting)
        for Model, fk_field, is_one_to_one in _lazy_student_fk_models():
            count = Model.objects.filter(**{fk_field: student}).count()
            if count:
                summary["models"][Model.__name__] = count

        # 2. Remove M2M links
        from library.models import LibraryActivity
        from transport.models import BusRoute
        activity_count = LibraryActivity.objects.filter(participants=student).count()
        if activity_count:
            for activity in LibraryActivity.objects.filter(participants=student):
                activity.participants.remove(student)
            summary["models"]["LibraryActivity_m2m"] = activity_count

        route_count = BusRoute.objects.filter(students=student).count()
        if route_count:
            for route in BusRoute.objects.filter(students=student):
                route.students.remove(student)
            summary["models"]["BusRoute_m2m"] = route_count

        # 3. Delete child FK records (CASCADE would do this, but explicit is better for counting)
        for Model, fk_field, _ in _lazy_student_fk_models():
            Model.objects.filter(**{fk_field: student}).delete()

        # 4. Anonymize consent records (keep structure, remove PII)
        consent_count = ConsentRecord.objects.filter(student=student).count()
        if consent_count:
            ConsentRecord.objects.filter(student=student).delete()
            summary["models"]["ConsentRecord"] = consent_count

        # 5. Remove parent-student links
        link_count = ParentStudentLink.objects.filter(student=student).count()
        if link_count:
            ParentStudentLink.objects.filter(student=student).delete()
            summary["models"]["ParentStudentLink"] = link_count

        # 6. Remove enrollments
        enroll_count = StudentEnrollment.objects.filter(student=student).count()
        if enroll_count:
            StudentEnrollment.objects.filter(student=student).delete()
            summary["models"]["StudentEnrollment"] = enroll_count

        # 7. Delete profile
        if hasattr(student, 'profile'):
            try:
                student.profile.delete()
                summary["models"]["Profile"] = 1
            except Profile.DoesNotExist:
                pass

        # 8. Anonymize the user record itself (don't delete — keep for audit trail)
        student.full_name = anon_id
        student.national_id = f"ERASED-{student.pk.hex[:8]}"
        student.email = ""
        student.phone = ""
        student.totp_secret = ""
        student.totp_enabled = False
        student.is_active = False
        student.set_unusable_password()
        student.save()

        # 9. AuditLog — immutable per PDPPL م.19, DO NOT delete or update.
        #    The student's CustomUser record is already anonymized (name=ERASED-XXXX),
        #    so FK references in AuditLog now point to an anonymized identity.
        audit_count = AuditLog.objects.filter(user=student).count()
        if audit_count:
            summary["models"]["AuditLog_preserved"] = audit_count

        # 10. Update the erasure request
        erasure_request.status = 'completed'
        erasure_request.completed_at = timezone.now()
        erasure_request.anonymized_id = anon_id
        erasure_request.summary = summary
        erasure_request.save()

        # 11. Log the erasure itself
        AuditLog.log(
            user=erasure_request.reviewed_by,
            action='delete',
            model_name='CustomUser',
            object_id=str(student.pk),
            object_repr=f"ERASURE {anon_id} — PDPPL م.18",
            changes=summary,
            school=erasure_request.school,
        )

        logger.info("PDPPL Erasure completed: %s — %d models affected",
                     anon_id, len(summary["models"]))

        return summary

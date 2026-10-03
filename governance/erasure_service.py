"""
governance/erasure_service.py — Right to Erasure (PDPPL م.18)

Anonymizes student PII across all models while preserving:
- AuditLog entries (immutable per م.19, user FK set to NULL)
- Statistical aggregates (counts stay, identifiers removed)
"""

import logging
from typing import Any

from django.db import transaction
from django.utils import timezone

from core.models import (
    AuditLog,
    ConsentRecord,
    ErasureRequest,
    Membership,
    ParentStudentLink,
    Profile,
    StudentEnrollment,
)

logger = logging.getLogger("core")

# Models with FK `student` → CustomUser (on_delete=CASCADE handles deletion,
# but we anonymize first to ensure no PII leaks via DB backups)
_STUDENT_FK_MODELS: list[tuple[Any, str, bool]] = []


def _lazy_student_fk_models() -> list[tuple[Any, str, bool]]:
    """Lazy import to avoid circular imports at module level."""
    if _STUDENT_FK_MODELS:
        return _STUDENT_FK_MODELS

    from assessments.models import (
        AnnualSubjectResult,
        ExamDeprivation,
        ExamMisconduct,
        StudentAssessmentGrade,
        StudentSubjectResult,
    )
    from behavior.models import AutoInfractionNotice, BehaviorInfraction
    from clinic.models import ClinicVisit, HealthRecord
    from developer_feedback.models import DeveloperMessage
    from exam_control.models import ExamIncident
    from library.models import BookBorrowing
    from notifications.models import (
        InAppNotification,
        NotificationLog,
        PushSubscription,
        UserNotificationPreference,
    )
    from operations.models import (
        AbsenceAlert,
        AbsenceExcuse,
        ClassExit,
        GuardianContact,
        StudentAttendance,
    )
    from student_affairs.models import StudentActivity, StudentTransfer
    from student_info.models import StudentNote

    _STUDENT_FK_MODELS.extend(
        [
            (HealthRecord, "student", True),  # OneToOne
            (ClinicVisit, "student", False),
            (StudentAssessmentGrade, "student", False),
            (StudentSubjectResult, "student", False),
            (AnnualSubjectResult, "student", False),
            (ExamDeprivation, "student", False),  # قرارُ حرمانٍ من اختبار
            (ExamMisconduct, "student", False),  # واقعةُ غشٍّ أو إلغاءٍ في لجان الاختبار
            (BehaviorInfraction, "student", False),
            (AutoInfractionNotice, "student", False),  # علامةُ إبلاغ الأسرة بمخالفة رصد
            (StudentAttendance, "student", False),
            (AbsenceAlert, "student", False),
            (AbsenceExcuse, "student", False),  # عذرُ غياب (يحوي مستنداً)
            (BookBorrowing, "user", False),
            (StudentActivity, "student", False),  # نشاط طلابي (يحوي مرفق PII)
            # [W-20261001-014] كانت مغفَلةً فتبقى بعد المحو (SET_NULL أو CASCADE لا يعمل
            # لأنّ المستخدم يُجهَّل ولا يُحذف). tests/test_erasure_coverage.py يحرس القائمة.
            (StudentNote, "student", False),  # ملاحظاتٌ نفسيّةٌ وصحّيّةٌ عن قاصر (م.16)
            (StudentTransfer, "student", False),  # سجلُّ الانتقال بين المدارس
            (GuardianContact, "student", False),  # اتّصالات وليّ الأمر بالهاتف
            (ClassExit, "student", False),  # خروجُ الطالب من الحصّة
            (ExamIncident, "student", False),  # محضرُ حادثةٍ في اللجنة
            (NotificationLog, "student", False),  # سجلُّ إشعارٍ يحمل المستلمَ ونصَّه
            # [W-20261002-042] مخازنُ محتوى الطالب بحقل `user` لا `student`.
            (InAppNotification, "user", False),  # إشعاراتُه داخل المنصّة
            (PushSubscription, "user", False),  # اشتراكُ دفعٍ بجهازه (نقطةُ اتّصال)
            (UserNotificationPreference, "user", True),  # تفضيلاتُه
            (DeveloperMessage, "user", False),  # موضوعٌ ونصٌّ حرٌّ منه إلى المطوّر
        ]
    )
    return _STUDENT_FK_MODELS


# نماذج بحقول ملفات مرتبطة بالطالب — تُطهَّر blobs الملفات قبل الحذف
_FILE_FIELD_MODELS: list[tuple[Any, str, str]] = []


def _lazy_file_field_models() -> list[tuple[Any, str, str]]:
    """(Model, fk_field, file_field) للنماذج التي ترفع ملفات مرتبطة بالطالب."""
    if _FILE_FIELD_MODELS:
        return _FILE_FIELD_MODELS

    from operations.models import AbsenceExcuse, StudentAttendance
    from student_affairs.models import StudentActivity

    _FILE_FIELD_MODELS.extend(
        [
            (StudentAttendance, "student", "excuse_file"),
            (AbsenceExcuse, "student", "document"),
            (StudentActivity, "student", "attachment"),
        ]
    )
    return _FILE_FIELD_MODELS


def _purge_files(files: list[tuple[str, Any]], school: Any, actor: Any) -> None:
    """يحذف ملفّاتِ التخزين بعد نجاح معاملة المحو كلِّها (on_commit) — فشلُ ملفٍّ لا يوقف الباقي.

    وبعد التثبيت مُحيت الصفوفُ المشيرةُ إلى الملفّ فلا إعادةَ محاولةٍ ممكنة: فيُكتب في AuditLog **مفتاحُ الملفّ** (لا محتواه ولا
    اسمُ الطالب) تحت «ملفٌّ يتيمٌ بعد محو» ليُزال يدويّاً أو بمهمّة (حكمُ 0105 P3-أ).
    """
    for file_field, f in files:
        try:
            f.delete(save=False)  # يفوّض storage backend (DatabaseStorage/S3)
        except Exception:
            logger.warning("تعذّر حذف ملف %s أثناء المحو", file_field, exc_info=True)
            try:
                AuditLog.log(
                    user=actor,
                    action="delete",
                    model_name="other",
                    object_repr="محوُ طالبٍ — ملفٌّ يتيمٌ بعد محو (يُزال يدويّاً)",
                    changes={"file_field": file_field, "key": getattr(f, "name", "")},
                    school=school,
                )
            except Exception:
                logger.exception("تعذّر تدوين ملفٍّ يتيمٍ بعد محو")


class ErasureFailedError(Exception):
    """تعثّر المحو برسالةٍ مفهومةٍ للمدير — الطلبُ عاد «approved» وتجوز إعادةُ التنفيذ."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


class ErasureStateError(Exception):
    """الطلبُ ليس في حالةٍ تقبل الموافقة/التنفيذ (غيرُ pending ولا approved)."""

    def __init__(self, status_display: str):
        super().__init__(f"لا يمكن الموافقة — الحالة الحالية: {status_display}")


class ErasureService:
    """Anonymize all PII for a student — PDPPL م.18."""

    @staticmethod
    def approve_and_execute(
        request_id: Any, reviewer: Any, note: str = ""
    ) -> tuple[ErasureRequest, dict[str, Any]]:
        """يوافق ويُنفّذ — بقفلِ صفّ الطلب كي لا يُنفّذ مديران متزامنان معاً (حكمُ 0105 N3).

        القفلُ والانتقالُ إلى «processing» في معاملةٍ قصيرةٍ تُثبَّت قبل التنفيذ: الثاني يجد الحالةَ «processing» فيُردّ.
        وإن كان الطلبُ «approved» فهو تنفيذٌ سابقٌ تعثّر فيُعاد، ويُكتب المراجعُ الأصليُّ في AuditLog لأنّ `reviewed_by`
        يتبدّل بالإعادة.
        """
        with transaction.atomic():
            obj = (
                ErasureRequest.objects.select_for_update()
                .select_related("school")
                .get(pk=request_id)
            )
            if obj.status not in ("pending", "approved"):
                raise ErasureStateError(obj.get_status_display())
            if obj.status == "approved":
                AuditLog.log(
                    user=reviewer,
                    action="update",
                    model_name="other",
                    object_id=obj.pk,
                    object_repr="محوُ طالبٍ — إعادةُ تنفيذٍ بعد تعثّر",
                    changes={
                        "request": str(obj.pk),
                        "previous_reviewer": str(obj.reviewed_by_id)
                        if obj.reviewed_by_id
                        else None,
                    },
                    school=obj.school,
                )
            obj.status = "processing"
            obj.reviewed_by = reviewer
            obj.reviewed_at = timezone.now()
            obj.review_note = note
            obj.save()
        return obj, ErasureService.execute_safely(obj, reviewer)

    @staticmethod
    def execute_safely(erasure_request: ErasureRequest, actor: Any) -> dict[str, Any]:
        """ينفّذ المحوَ دون أن يترك الطلبَ عالقاً «processing» أيّاً كان الفشلُ (حكمُ 0105 M5 وN2).

        معاملةُ `execute` تتراجع كلُّها عند الخطأ (الطالبُ لم يُمسّ، وملفّاتُ التخزين لا تُحذف إلّا بعد النجاح)، لكنّ الطلبَ
        كان محفوظاً «processing» قبلها فيبقى بلا مخرجٍ. فهنا: يعود «approved»، ويُكتب AuditLog بالفشل ورمزِه
        (رمزُ خطأ سجلّ الرصد، أو `erasure_error` لأيّ استثناءٍ آخر ويُسجَّل في logger للمراقبة)، ويُرفع
        `ErasureFailedError` برسالةٍ مفهومةٍ — فيُعيد المديرُ التنفيذَ بعد معالجة السبب.
        """
        from operations.attendance_entries import EntryError

        try:
            return ErasureService.execute(erasure_request)
        except EntryError as exc:
            code = exc.code
            detail = f"تعذّر محو سجلّ رصد المعلّم لهذا الطالب ({exc})"
            cause: Exception = exc
        except Exception as exc:  # أيُّ فشلٍ آخر (قيدٌ، تخزينٌ…): لا يُترك الطلبُ عالقاً
            logger.exception("فشل محوٌ غيرُ متوقَّع لطلب %s", erasure_request.pk)
            code = "erasure_error"
            detail = "تعذّر تنفيذ المحو لخطأٍ غيرِ متوقَّع سُجّل للمراجعة"
            cause = exc
        erasure_request.status = "approved"
        erasure_request.save(update_fields=["status"])
        AuditLog.log(
            user=actor,
            action="update",
            model_name="other",
            object_id=erasure_request.pk,
            object_repr="محوُ طالبٍ — تعثّر محوٍ",
            changes={"code": code, "request": str(erasure_request.pk)},
            school=erasure_request.school,
        )
        raise ErasureFailedError(
            f"{detail} — لم يُمسّ شيء. الطلبُ باقٍ «تمّت الموافقة» ويمكن إعادة التنفيذ بعد معالجة السبب.",
            code,
        ) from cause

    @staticmethod
    def student_in_school(student: Any, school: Any) -> bool:
        """هل للطالب عضويّةٌ في المدرسة؟ (نشطةً أو لا: حقُّ المحو لا يسقط بتخرّجه)."""
        return bool(student.memberships.filter(school=school).exists())

    @staticmethod
    @transaction.atomic
    def execute(erasure_request: ErasureRequest) -> dict[str, Any]:
        """
        Execute an approved erasure request.
        Returns a summary dict of what was anonymized/deleted.
        """
        student = erasure_request.student
        if not student:
            raise ValueError("Student record not found for this erasure request.")

        # دفاعٌ في العمق (W-20261002-040): لا محوَ لطالبٍ ليس من مدرسة الطلب مهما كان
        # الطريق إلى هنا — فالفعلُ لا رجعةَ فيه.
        if not ErasureService.student_in_school(student, erasure_request.school):
            raise ValueError("الطالب ليس من مدرسة طلب المحو.")

        anon_id = f"ERASED-{str(erasure_request.id)[:8].upper()}"
        summary: dict[str, Any] = {"anon_id": anon_id, "models": {}}

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

        # 2.5 سجلُّ رصد المعلّم (إدخالاتٌ وقراراتٌ مضافةٌ فقط، W-20261002-020): يُمحى بمساره المسمّى وحدَه — لا
        #     بالحلقة العامّة أدناه (حارسُ ORM وحارسُ القاعدة يرفضان الحذفَ العامّ). يكتب AuditLog بالأعداد.
        from operations.attendance_entries import erase_attendance_ledger

        ledger = erase_attendance_ledger(
            student, actor=erasure_request.reviewed_by, school=erasure_request.school
        )
        if ledger["entries"]:
            summary["models"]["AttendanceEntry"] = ledger["entries"]
        if ledger["decisions"]:
            summary["models"]["AttendanceDecision"] = ledger["decisions"]
        # حدٌّ معلَن (0105): دورُ هذه المدرسة لا يرى صفوفَ مدرسةٍ سابقةٍ سُجّل فيها الطالب — فلا يُقال «اكتمل» بلا تنبيه.
        if Membership.objects.filter(user=student).exclude(school=erasure_request.school).exists():
            summary["attendance_ledger_note"] = (
                "سجلُّ رصد المعلّم مُحيَ لمدرسة الطلب الحاليّة فقط؛ وللطالب عضويّاتٌ في مدارسَ أخرى قد تبقى فيها "
                "إدخالاتٌ وقراراتٌ — يلزم محوُها بدور تلك المدارس."
            )

        # 2.9 محوُ ملفّات التخزين (blobs) — **بعد** ما قد يفشل، وعند **نجاح المعاملة كلِّها فقط** (حكمُ 0105 N1):
        #     حذفُ الملفّ في S3 لا يتراجع مع معاملة القاعدة، فلو حُذف قبل فشلٍ لاحقٍ بقيت صفوفٌ تشير إلى ملفّاتٍ
        #     مفقودة. والحذفُ العامّ للصفوف لا يستدعي storage backend فتبقى الملفّاتُ يتيمةً (فجوة محو م.18) — لذلك
        #     تُجمع المراجعُ الآن وتُحذف في on_commit.
        files_to_purge = []
        for Model, fk_field, file_field in _lazy_file_field_models():
            for obj in Model.objects.filter(**{fk_field: student}):
                f = getattr(obj, file_field, None)
                if f:
                    files_to_purge.append((file_field, f))
        if files_to_purge:
            # «مجدوَل» لا «محذوف»: الحذفُ الفعليُّ بعد التثبيت وقد يفشل ملفٌّ (يُدوَّن يتيماً). و`files_purged` باقٍ لتوافق الواجهة.
            summary["files_purged"] = summary["files_scheduled_for_purge"] = len(files_to_purge)
            school, actor = erasure_request.school, erasure_request.reviewed_by
            transaction.on_commit(lambda: _purge_files(files_to_purge, school, actor))

        # 3. Delete child FK records (CASCADE would do this, but explicit is better for counting)
        for Model, fk_field, _ in _lazy_student_fk_models():
            Model.objects.filter(**{fk_field: student}).delete()

        # 3.5 [W-20261002-042] نيّةُ الإرسال PROTECT ودليلٌ على المحاولة: يبقى الصفُّ
        #     ويُمسح محتواه (title وbody) ويُضبط وقتُ المسح.
        from notifications.models import NotificationEnqueueIntent

        cleared = NotificationEnqueueIntent.objects.filter(recipient=student).update(
            title=None, body=None, content_cleared_at=timezone.now()
        )
        if cleared:
            summary["models"]["NotificationEnqueueIntent_cleared"] = cleared

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
        if hasattr(student, "profile"):
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
        # PDPPL م.18 [PII-07]: صفّر الأعمدة المشفّرة والـ HMAC صراحةً — وإلا يبقى
        # الهاتف الأصلي قابلاً للفك (save() لا يعيد حسابها لأن phone أصبح فارغاً).
        student.national_id_encrypted = ""
        student.national_id_hmac = ""
        student.phone_encrypted = ""
        student.phone_hmac = ""
        student.totp_secret = ""
        student.totp_enabled = False
        student.is_active = False
        student.set_unusable_password()
        student.save()

        # 9. AuditLog — immutable per PDPPL م.19, DO NOT delete or update.
        #    The student's CustomUser record is already anonymized (name=ERASED-XXXX),
        #    so FK references in AuditLog now point to an anonymized identity.
        # [W-20261003-013] قرارُ DPO: يبقى السجلُّ وتُفرَّغ شبكةُ الطالب (IP والمتصفّح)،
        # بما فيها محاولاتُ الدخول الفاشلة على حسابه. يُسجَّل العدّ في الملخّص.
        redacted = AuditLog.objects.redact_network_identity(student)
        if redacted:
            summary["models"]["AuditLog_network_redacted"] = redacted

        audit_count = AuditLog.objects.filter(user=student).count()
        if audit_count:
            summary["models"]["AuditLog_preserved"] = audit_count

        # 10. Update the erasure request
        erasure_request.status = "completed"
        erasure_request.completed_at = timezone.now()
        erasure_request.anonymized_id = anon_id
        erasure_request.summary = summary
        erasure_request.save()

        # 11. Log the erasure itself
        AuditLog.log(
            user=erasure_request.reviewed_by,
            action="delete",
            model_name="CustomUser",
            object_id=str(student.pk),
            object_repr=f"ERASURE {anon_id} — PDPPL م.18",
            changes=summary,
            school=erasure_request.school,
        )

        logger.info(
            "PDPPL Erasure completed: %s — %d models affected", anon_id, len(summary["models"])
        )

        return summary

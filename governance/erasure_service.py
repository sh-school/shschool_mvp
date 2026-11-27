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
    School,
    StudentEnrollment,
)
from core.models.access import ALL_STAFF_ROLES
from core.unrestricted_role import PLATFORM_DEVELOPER, has_unrestricted_role
from governance.erasure_notify import send_signature_request

logger = logging.getLogger("core")

# Models with FK `student` → CustomUser (on_delete=CASCADE handles deletion,
# but we anonymize first to ensure no PII leaks via DB backups)
_STUDENT_FK_MODELS: list[tuple[Any, str, bool]] = []


def _lazy_student_fk_models() -> list[tuple[Any, str, bool]]:
    """Lazy import to avoid circular imports at module level."""
    if _STUDENT_FK_MODELS:
        return _STUDENT_FK_MODELS

    from behavior.models import AutoInfractionNotice, BehaviorInfraction
    from clinic.models import ClinicVisit, GuardianMedicationConsent, HealthRecord
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
        DailyExitTally,
        ExcusedExit,
        ExitPermit,
        GuardianContact,
        StudentAttendance,
    )
    from student_affairs.models import GuardianRequest, StudentActivity, StudentTransfer
    from student_info.models import StudentNote
    from wings.models import ConductProposal, ReturnLateSuggestion

    _STUDENT_FK_MODELS.extend(
        [
            (HealthRecord, "student", True),  # OneToOne
            (ClinicVisit, "student", False),
            (GuardianMedicationConsent, "student", False),  # موافقةُ وليّ الأمر على دواءٍ للطالب
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
            (GuardianRequest, "student", False),  # طلباتُ وليّ الأمر وشكاواه (جوّالات مشفّرة)
            (GuardianContact, "student", False),  # اتّصالات وليّ الأمر بالهاتف
            (ClassExit, "student", False),  # خروجُ الطالب من الحصّة
            (ExitPermit, "student", False),  # إذنُ خروج الطالب من المدرسة (W-20261005-010)
            (DailyExitTally, "student", False),  # ملخّصُ خروجه اليوميّ (مشتقٌّ من ClassExit)
            (ExcusedExit, "student", False),  # وسمُ الخروج المبرَّر الدائم وسببُه الصحّيّ
            (ExamIncident, "student", False),  # محضرُ حادثةٍ في اللجنة
            (
                ConductProposal,
                "student",
                False,
            ),  # اقتراحُ مخالفةٍ لغيابٍ أو تأخّرٍ بين الحصص (W-20261013-034)
            (ReturnLateSuggestion, "student", False),  # اقتراحُ متابعة تأخّر العودة (W-20261119-004)
            (NotificationLog, "student", False),  # سجلُّ إشعارٍ يحمل المستلمَ ونصَّه
            # [W-20261002-042] مخازنُ محتوى الطالب بحقل `user` لا `student`.
            (InAppNotification, "user", False),  # إشعاراتُه داخل المنصّة
            (PushSubscription, "user", False),  # اشتراكُ دفعٍ بجهازه (نقطةُ اتّصال)
            (UserNotificationPreference, "user", True),  # تفضيلاتُه
            (DeveloperMessage, "user", False),  # موضوعٌ ونصٌّ حرٌّ منه إلى المطوّر
        ]
    )
    return _STUDENT_FK_MODELS


# [U-11] السجلُّ الأكاديميّ: المحوُ تجهيلٌ لا حذف (قرارُ المالك، هجرة roadmap 0028، وأكّده 2026-11-27).
_RETAINED_ACADEMIC_MODELS: list[tuple[Any, str, dict[str, str]]] = []


def _lazy_retained_academic_models() -> list[tuple[Any, str, dict[str, str]]]:
    """(Model, fk_field, الحقولُ الممسوحة) — الصفوفُ تبقى مربوطةً بالحساب المجهَّل.

    يُمسح كلُّ حقلٍ صحّيٍّ أو نصٍّ حرّ، وتبقى الدرجاتُ والحالاتُ والتواريخ. قاموسٌ فارغ = لا حقلَ من هذا الصنف.
    """
    if _RETAINED_ACADEMIC_MODELS:
        return _RETAINED_ACADEMIC_MODELS

    from assessments.models import (
        AnnualSubjectResult,
        ExamDeprivation,
        ExamMisconduct,
        StudentAssessmentGrade,
        StudentSubjectResult,
    )

    _RETAINED_ACADEMIC_MODELS.extend(
        [
            # excuse_type منه «المرض» فهو سببٌ صحّيّ؛ و is_excused يبقى حالةً.
            (
                StudentAssessmentGrade,
                "student",
                {"excuse_reference": "", "excuse_type": "", "notes": ""},
            ),
            (StudentSubjectResult, "student", {}),  # درجاتٌ فقط
            (AnnualSubjectResult, "student", {"review": ""}),  # تنبيهُ المراجعة سردٌ
            (ExamDeprivation, "student", {"note": ""}),
            (ExamMisconduct, "student", {"note": "", "report_ref": ""}),  # رقمُ المحضر نصٌّ حرّ
        ]
    )
    return _RETAINED_ACADEMIC_MODELS


def _scrub_retained_academic(student: Any, summary: dict[str, Any]) -> None:
    """يمسح الحقولَ الحسّاسة من السجلّ الأكاديميّ ويُبقي صفوفَه، ويدوّن أعدادَها في `retained_anonymized`.

    `update()` لا `save()`: لا إشاراتِ ولا إعادةَ حسابٍ لأيّ نتيجة.
    """
    retained: dict[str, int] = {}
    for Model, fk_field, blanks in _lazy_retained_academic_models():
        rows = Model.objects.filter(**{fk_field: student})
        count = rows.update(**blanks) if blanks else rows.count()
        if count:
            retained[Model.__name__] = count
    if retained:
        summary["retained_anonymized"] = retained


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


def _anonymize_audit_name(student: Any, name: str, summary: dict[str, Any]) -> None:
    """[W-20261004-002، W-20261010-053] قرارُ DPO D-186م ب وD-342م: يُجهَّل اسمُ المحوّ في السجلّ كلِّه.

    `object_repr` يُستبدل فيه الاسمُ بمعرّفه المقنَّع، و`changes` يُمسح منه الاسمُ على القيمة المفكوكة؛
    والتجهيلان في معاملةٍ واحدةٍ فلا يبقى سجلٌّ نصفُه مجهَّل. ما تُخطّي (اسمٌ مشتركٌ أو قصير أو وصفٌ يطول
    أو قيمةٌ شديدة التداخل) لا يُكتب ويُبلَّغ يدوياً في ملاحظةٍ بأعدادٍ لا بأسماء.
    """
    with transaction.atomic():
        named = AuditLog.objects.anonymize_name_in_repr(student, name)
        scrubbed = AuditLog.objects.anonymize_name_in_changes(student, name)
    if named["anonymized"]:
        summary["models"]["AuditLog_name_anonymized"] = named["anonymized"]
    skipped = {k: v for k, v in named.items() if k.startswith("skipped_") and v}
    if skipped:
        summary["auditlog_name_manual_report"] = skipped
        summary["auditlog_name_note"] = (
            "صفوفٌ في سجلّ التدقيق بقي فيها اسمُ المحوّ لأنّه مشتركٌ أو قصيرٌ أو يطول وصفُها بعد الاستبدال — "
            "يلزم إبلاغٌ يدويّ بها (الأعدادُ في auditlog_name_manual_report)."
        )
    if scrubbed["changes_anonymized"]:
        summary["models"]["AuditLog_changes_anonymized"] = scrubbed["changes_anonymized"]
    skipped_changes = {k: v for k, v in scrubbed.items() if k.startswith("skipped_") and v}
    if skipped_changes:
        summary["auditlog_changes_manual_report"] = skipped_changes
        summary["auditlog_changes_note"] = (
            "صفوفٌ في سجلّ التدقيق بقي اسمُ المحوّ في عمود التغييرات لأنّه مشتركٌ أو قصيرٌ أو شديدُ التداخل — "
            "يلزم إبلاغٌ يدويّ بها (الأعدادُ في auditlog_changes_manual_report)."
        )


class ErasureFailedError(Exception):
    """تعثّر المحو برسالةٍ مفهومةٍ للموقّع — الطلبُ عاد «approved» وتجوز إعادةُ التنفيذ بتوقيعين."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


class ErasureStateError(Exception):
    """الطلبُ ليس في حالةٍ تقبل الموافقة/التنفيذ (غيرُ pending ولا approved)."""

    def __init__(self, status_display: str):
        super().__init__(f"لا يمكن الموافقة — الحالة الحالية: {status_display}")


class ErasureSelfApprovalError(Exception):
    """مقدِّمُ الطلب لا يوقّعه ولا يرفضه: المحوُ لا رجعة فيه (فصلُ المهام)."""


class ErasureNoOfficerError(Exception):
    """لا مسؤولَ حمايةِ بياناتٍ معيَّناً للمدرسة: لا يُنفَّذ محوٌ بلا توقيعه."""


class ErasureNotSignerError(Exception):
    """المستخدمُ ليس من موقّعَي هذا الطلب (أو ليس مديراً عند التعيين)."""


class ErasureAlreadySignedError(Exception):
    """وقّع هذا الشخصُ من قبل، أو سبقه غيرُه إلى خانته."""


class ErasureNoteRequiredError(Exception):
    """الرفضُ بلا سبب."""


class ErasureOfficerError(Exception):
    """المرشَّحُ مسؤولاً لحماية البيانات ليس من كادر المدرسة."""


def _has_school_role(user: Any, school_id: Any, role: str) -> bool:
    return bool(
        user.memberships.filter(school_id=school_id, is_active=True, role__name=role).exists()
    )


def _admin_signer_role(obj: ErasureRequest) -> str:
    """دورُ موقّع الإدارة: المدير، وإن كان هو مقدِّمَ الطلب فالنائبُ الإداريّ."""
    filer = obj.requested_by
    if filer is not None and _has_school_role(filer, obj.school_id, "principal"):
        return "vice_admin"
    return "principal"


def _is_admin_signer(user: Any, obj: ErasureRequest) -> bool:
    if not user.is_active or user.pk == obj.requested_by_id or has_unrestricted_role(user):
        return False
    return _has_school_role(user, obj.school_id, _admin_signer_role(obj))


def _signature_slot(user: Any, obj: ErasureRequest) -> str | None:
    """خانةُ المستخدم: "dpo" أو "admin" أو None. المسؤولُ المعيَّنُ خانتُه "dpo" دائماً (لا بديلَ له فيها)."""
    if user.pk == obj.school.data_protection_officer_id:
        return "dpo"
    return "admin" if _is_admin_signer(user, obj) else None


def _valid_signatures(obj: ErasureRequest) -> set[str]:
    """الخاناتُ الموقَّعةُ توقيعاً ما زال سارياً — توقيعُ من فقد صفتَه (مسؤولٌ استُبدل…) لا يُحتسب."""
    valid: set[str] = set()
    dpo = obj.dpo_signed_by_id
    if (
        dpo is not None
        and dpo == obj.school.data_protection_officer_id
        and dpo != obj.requested_by_id
    ):
        valid.add("dpo")
    admin = obj.admin_signed_by
    if admin is not None and admin.pk != dpo and _is_admin_signer(admin, obj):
        valid.add("admin")
    return valid


def _locked_request(request_id: Any) -> ErasureRequest:
    """صفُّ الطلب ومدرستِه بقفلٍ — يسلسل التوقيعَ والرفضَ وتعيينَ المسؤول المتزامنة."""
    obj: ErasureRequest = (
        ErasureRequest.objects.select_for_update().select_related("school").get(pk=request_id)
    )
    return obj


def _audit_request(obj: ErasureRequest, actor: Any, label: str, changes: dict[str, Any]) -> None:
    """سطرُ تدقيقٍ على طلب المحو — معرّفاتٌ فقط."""
    AuditLog.log(
        user=actor,
        action="update",
        model_name="other",
        object_id=obj.pk,
        object_repr=f"محوُ طالبٍ — {label}",
        changes={"request": str(obj.pk), **changes},
        school=obj.school,
    )


class ErasureService:
    """Anonymize all PII for a student — PDPPL م.18."""

    @staticmethod
    def approve_and_execute(
        request_id: Any, reviewer: Any, note: str = ""
    ) -> tuple[ErasureRequest, dict[str, Any] | None]:
        """يسجّل توقيعَ `reviewer` ويُنفّذ عند اكتمال التوقيعين. `summary = None` إن بقي توقيع.

        بقفلِ صفّ الطلب: التوقيعُ والانتقالُ إلى «processing» في معاملةٍ قصيرةٍ تُثبَّت قبل التنفيذ، فالمتزامنُ يجد
        الحالةَ «processing» فيُردّ. و«approved» تنفيذٌ سابقٌ تعثّر: يلزمه توقيعان من جديد.
        """
        with transaction.atomic():
            obj = _locked_request(request_id)
            if obj.status not in ("pending", "approved"):
                raise ErasureStateError(obj.get_status_display())
            # بعد فحص الحالة: طلبٌ منتهٍ يُردّ بحالته أيّاً كان الموقّع.
            if obj.requested_by_id == reviewer.pk:
                raise ErasureSelfApprovalError()
            if obj.school.data_protection_officer_id is None:
                raise ErasureNoOfficerError()
            slot = _signature_slot(reviewer, obj)
            if slot is None:
                raise ErasureNotSignerError()
            signed = _valid_signatures(obj)
            held = {getattr(obj, f"{name}_signed_by_id") for name in signed}
            if slot in signed or reviewer.pk in held:
                raise ErasureAlreadySignedError()
            now = timezone.now()
            setattr(obj, f"{slot}_signed_by", reviewer)
            setattr(obj, f"{slot}_signed_at", now)
            _audit_request(obj, reviewer, "توقيع", {"signer": str(reviewer.pk), "slot": slot})
            complete = _valid_signatures(obj) == {"admin", "dpo"}
            if complete:
                if obj.status == "approved":
                    previous = str(obj.reviewed_by_id) if obj.reviewed_by_id else None
                    _audit_request(
                        obj, reviewer, "إعادةُ تنفيذٍ بعد تعثّر", {"previous_reviewer": previous}
                    )
                obj.status = "processing"
                obj.reviewed_by = reviewer
                obj.reviewed_at = now
            if note:
                obj.review_note = note
            obj.save()
        if not complete:
            ErasureService.notify_pending_signers(obj, reviewer)
            return obj, None
        return obj, ErasureService.execute_safely(obj, reviewer)

    @staticmethod
    def signed_slots(obj: ErasureRequest) -> set[str]:
        """الخاناتُ الموقَّعةُ توقيعاً سارياً."""
        return _valid_signatures(obj)

    @staticmethod
    def pending_signers(obj: ErasureRequest) -> list[tuple[str, list[Any]]]:
        """الخاناتُ الباقيةُ ومن يحقّ له ملءُ كلٍّ منها — بقواعد التوقيع نفسِها."""
        officer = obj.school.data_protection_officer
        signed = _valid_signatures(obj)
        pending: list[tuple[str, list[Any]]] = []
        if "admin" not in signed:
            members = Membership.objects.filter(
                school_id=obj.school_id, is_active=True, role__name=_admin_signer_role(obj)
            ).select_related("user")
            admins = {m.user.pk: m.user for m in members if _signature_slot(m.user, obj) == "admin"}
            pending.append(("admin", list(admins.values())))
        if "dpo" not in signed:
            eligible = officer is not None and officer.pk != obj.requested_by_id
            pending.append(("dpo", [officer] if eligible else []))
        return pending

    @staticmethod
    def signing_options(user: Any, obj: ErasureRequest) -> tuple[bool, bool]:
        """(أيوقّع؟، أيرفض؟) لعرض الأزرار — والحسمُ يبقى لـ`approve_and_execute` و`reject`."""
        if obj.status not in ("pending", "approved") or obj.requested_by_id == user.pk:
            return False, False
        slot = _signature_slot(user, obj)
        if slot is None:
            return False, False
        signed = _valid_signatures(obj)
        held = {getattr(obj, f"{name}_signed_by_id") for name in signed}
        can_sign = (
            obj.school.data_protection_officer_id is not None
            and slot not in signed
            and user.pk not in held
        )
        return can_sign, obj.status == "pending"

    @staticmethod
    def notify_pending_signers(obj: ErasureRequest, actor: Any) -> None:
        """إشعارُ من بقي توقيعُه (عدا الفاعل) عند طلبٍ جديدٍ أو توقيعٍ أوّل."""
        recipients = {
            user.pk: user
            for _, users in ErasureService.pending_signers(obj)
            for user in users
            if user.pk != actor.pk
        }
        send_signature_request(obj, recipients.values())

    @staticmethod
    @transaction.atomic
    def reject(request_id: Any, reviewer: Any, note: str) -> ErasureRequest:
        """رفضُ أحد الموقّعَين مع السبب يكفي."""
        obj = _locked_request(request_id)
        if obj.status != "pending":
            raise ErasureStateError(obj.get_status_display())
        if obj.requested_by_id == reviewer.pk:
            raise ErasureSelfApprovalError()
        if _signature_slot(reviewer, obj) is None:
            raise ErasureNotSignerError()
        if not note:
            raise ErasureNoteRequiredError()
        obj.status = "rejected"
        obj.reviewed_by = reviewer
        obj.reviewed_at = timezone.now()
        obj.review_note = note
        obj.save()
        _audit_request(obj, reviewer, "رفض", {"signer": str(reviewer.pk)})
        return obj

    @staticmethod
    @transaction.atomic
    def assign_officer(actor: Any, officer_id: Any) -> None:
        """تعيينُ مسؤول حماية البيانات لمدرسة المدير — للمدير وحدَه."""
        school = actor.get_school()
        if (
            school is None
            or has_unrestricted_role(actor)
            or not _has_school_role(actor, school.pk, "principal")
        ):
            raise ErasureNotSignerError()
        locked = School.objects.select_for_update().get(pk=school.pk)
        is_staff = Membership.objects.filter(
            school=locked,
            user_id=officer_id,
            user__is_active=True,
            is_active=True,
            role__name__in=ALL_STAFF_ROLES | {PLATFORM_DEVELOPER},
        ).exists()
        if not is_staff:
            raise ErasureOfficerError()
        previous = locked.data_protection_officer_id
        locked.data_protection_officer_id = officer_id
        locked.save(update_fields=["data_protection_officer"])
        AuditLog.log(
            user=actor,
            action="update",
            model_name="other",
            object_id=locked.pk,
            object_repr="تعيينُ مسؤول حماية البيانات",
            changes={
                "officer": str(officer_id),
                "previous_officer": str(previous) if previous else None,
            },
            school=locked,
        )

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
        # الإعادةُ تلزمها التوقيعان من جديد؛ ومن وقّع سابقاً محفوظٌ في AuditLog.
        erasure_request.admin_signed_by = erasure_request.dpo_signed_by = None
        erasure_request.admin_signed_at = erasure_request.dpo_signed_at = None
        # حقولٌ محدّدة: المعاملةُ المتراجعةُ قد تترك في الكائن قيمَ «اكتمل» فلا تُحفظ.
        erasure_request.save(
            update_fields=[
                "status",
                "admin_signed_by",
                "admin_signed_at",
                "dpo_signed_by",
                "dpo_signed_at",
            ]
        )
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
            f"{detail} — لم يُمسّ شيء. الطلبُ باقٍ «تمّت الموافقة» ويمكن إعادة التنفيذ بتوقيعين جديدين بعد معالجة السبب.",
            code,
        ) from cause

    @staticmethod
    def student_in_school(student: Any, school: Any) -> bool:
        """هل الهدفُ طالبٌ في المدرسة؟ (عضويّتُه نشطةً أو لا: حقُّ المحو لا يسقط بتخرّجه).

        بدور «طالب» لا بأيّ عضويّة: كان يكفي أيُّ دورٍ في المدرسة، فيطلب مديرٌ محوَ نائبٍ أو
        موظّفٍ ويعتمده — والمحوُ يعطّل الحسابَ ويجهّله بلا رجعة. ومن له عضويّةُ كادرٍ في أيّ
        مدرسةٍ أو صفةُ المشرف العامّ لا يُمحى من هذا الطريق ولو حمل دورَ طالبٍ معها: الحسابُ
        واحدٌ عبر المدارس، فمحوُه يُسقط عملَه فيها كلِّها.
        """
        if student.is_superuser:
            return False
        if student.memberships.filter(role__name__in=ALL_STAFF_ROLES).exists():
            return False
        return bool(student.memberships.filter(school=school, role__name="student").exists())

    @staticmethod
    @transaction.atomic
    def execute(erasure_request: ErasureRequest) -> dict[str, Any]:
        """
        Execute an approved erasure request.
        Returns a summary dict of what was anonymized/deleted: `models` للمحذوف وما عولج بخطوةٍ مخصَّصة،
        و`retained_anonymized` للسجلّ الأكاديميّ المحفوظ المجهَّل (أعدادٌ فقط).
        """
        student = erasure_request.student
        if not student:
            raise ValueError("Student record not found for this erasure request.")

        # دفاعٌ في العمق (W-20261002-040): لا محوَ لمن ليس طالباً في مدرسة الطلب مهما كان
        # الطريق إلى هنا — فالفعلُ لا رجعةَ فيه.
        if not ErasureService.student_in_school(student, erasure_request.school):
            raise ValueError("هدفُ المحو ليس طالباً في مدرسة طلب المحو.")

        anon_id = f"ERASED-{str(erasure_request.id)[:8].upper()}"
        # الاسمُ قبل الخطوة 8 تمحوه: يلزم لتجهيله في وصف سجلّ التدقيق (W-20261004-002).
        original_name = student.full_name
        summary: dict[str, Any] = {"anon_id": anon_id, "models": {}}

        # 1. Anonymize records in child models (count before deleting)
        for Model, fk_field, is_one_to_one in _lazy_student_fk_models():
            count = Model.objects.filter(**{fk_field: student}).count()
            if count:
                summary["models"][Model.__name__] = count

        # 1.5 [U-11] السجلُّ الأكاديميّ يبقى ويُمسح صحّيُّه ونصُّه الحرّ.
        _scrub_retained_academic(student, summary)

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
        # 2.6 سجلّا متابعة الغياب (اتّصالٌ بالوليّ وتغذيتُه المشفَّرة، وإجراءٌ إداريّ — W-20261013-011): مضافان فقط
        #     كسجلّ الرصد، فالحلقةُ العامّةُ أدناه تُسقطهما (`PermissionDenied`) — يُجهَّلان بمسارهما المسمّى وحدَه (أثرٌ مجهَّلٌ لا حذف، قرارُ المالك).
        from operations.services.absence_followup import erase_followup_logs

        followup = erase_followup_logs(
            student, actor=erasure_request.reviewed_by, school=erasure_request.school
        )
        if followup["contacts"]:
            summary["models"]["AbsenceContactLog"] = followup["contacts"]
        if followup["actions"]:
            summary["models"]["AbsenceActionLog"] = followup["actions"]
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

        _anonymize_audit_name(student, original_name, summary)

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

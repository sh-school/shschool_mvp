"""
assessments/excuse_service.py
قرارُ عذر الغياب عن الاختبار (D-402م) — مفصولٌ عن services.py لحدّ حجم الملفّ؛ يرثه GradeService فيبقى النداءُ GradeService.decide_excuse.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from django.db import transaction

from core.audit_repr import masked_repr

from .models import Assessment, StudentAssessmentGrade
from .verdict_engine import ensure_open_year

if TYPE_CHECKING:
    from core.models import CustomUser

#: مهلةُ تقديم عذر الغياب عن الاختبار: اليومُ الثالث التقويميّ بعد انتهاء جدول الاختبار (04b السطر 1949، D-403م).
EXCUSE_GRACE_DAYS = 3


class ExcuseServiceMixin:
    @staticmethod
    def excuse_deadline(
        assessment: Assessment, cache: dict[Any, Any] | None = None
    ) -> tuple[date, date] | None:
        """(آخرُ موعدٍ لتقديم العذر، نهايةُ جدول الاختبار) أو None إن لم يُعرف الجدول.

        الجدولُ يُقرأ من `exam_control.ExamSession` بلا نسخةٍ محلّيّة: دورةُ المدرسة والعام التي يقع
        تاريخُ التقييم داخل مدّتها. والمهلةُ اليومُ الثالث التقويميّ بعد انتهاء الجدول لا تُستثنى
        فيه عطلةٌ (04b السطر 1949، D-403م). ولا تاريخَ للتقييم أو لا دورةَ مسجَّلة: لا مهلةَ تُحسب.

        `cache` قاموسٌ اختياريّ يُمرَّر عند الحساب لقائمةٍ فيُستعلم عن كلّ (مدرسة، عام، تاريخ) مرّةً واحدة."""
        from exam_control.models import ExamSession

        if assessment.date is None:
            return None
        key = (assessment.school_id, assessment.package.setup.academic_year, assessment.date)
        if cache is not None and key in cache:
            return cache[key]
        session = (
            ExamSession.objects.filter(
                school=assessment.school,
                academic_year=assessment.package.setup.academic_year,
                start_date__lte=assessment.date,
                end_date__gte=assessment.date,
            )
            .order_by("-start_date")
            .first()
        )
        found = (
            None
            if session is None
            else (session.end_date + timedelta(days=EXCUSE_GRACE_DAYS), session.end_date)
        )
        if cache is not None:
            cache[key] = found
        return found

    @staticmethod
    def decide_excuse(
        assessment: Assessment,
        student: CustomUser,
        excuse_type: str,
        reference: str,
        decided_by: CustomUser,
        submitted_on: date | None = None,
    ) -> StudentAssessmentGrade:
        """يثبّت عذرَ غيابٍ رصده المعلّمُ: بنوعٍ من القائمة المغلقة ومرجعٍ ومن قرّر ومتى.

        القدرةُ `assessments.decide_excuse` شرطٌ هنا لا في العرض وحدَه، فلا يمرّ مسارٌ ثانٍ بلا حارس.
        لا يُنشئ غياباً ولا يغيّر درجةً: الصفُّ يجب أن يكون «غائباً» من رصد المعلّم أصلاً.

        `submitted_on` تاريخُ تقديم الطالب أو وليّه إثباتَ العذر (الدوحة؛ الافتراضيّ اليوم)، فمن قُدِّم
        في موعده وقُيِّد متأخّراً يُقبل. ما قُدِّم بعد المهلة يُرفض بسببه ويُدقَّق محاولةً، والغيابُ باقٍ بلا عذر."""
        from django.core.exceptions import PermissionDenied, ValidationError
        from django.utils import timezone

        from core.capabilities import has_capability

        from .models import EXCUSE_TYPES

        if not has_capability(decided_by, "assessments.decide_excuse"):
            raise PermissionDenied("قرارُ العذر لأصحاب القدرة وحدَهم")
        if not any(m.school_id == assessment.school_id for m in decided_by.active_memberships):
            raise PermissionDenied("القرارُ لعضوٍ في مدرسة هذا التقييم وحدَه")
        if excuse_type not in dict(EXCUSE_TYPES):
            raise ValidationError("نوعُ العذر خارج القائمة المغلقة")
        reference = (reference or "").strip()
        if not reference:
            raise ValidationError("مرجعُ العذر (الشهادة أو جهتها) مطلوب")
        today = timezone.localdate()
        submitted_on = submitted_on or today
        if submitted_on > today:
            raise ValidationError("تاريخُ تقديم العذر لا يكون في المستقبل")

        ensure_open_year(assessment.package.setup)
        deadline = ExcuseServiceMixin.excuse_deadline(assessment)
        if deadline is not None and submitted_on > deadline[0]:
            ExcuseServiceMixin._audit_late_excuse(
                assessment, student, decided_by, submitted_on, deadline
            )
            raise ValidationError(
                f"انقضت مهلةُ تقديم العذر: آخرُ موعدٍ {deadline[0]:%Y/%m/%d} "
                f"(اليومُ الثالث بعد انتهاء جدول الاختبار في {deadline[1]:%Y/%m/%d})"
                " — يبقى الغيابُ بلا عذر"
            )
        return ExcuseServiceMixin._store_excuse(
            assessment, student, excuse_type, reference, decided_by, submitted_on
        )

    @staticmethod
    def _audit_late_excuse(
        assessment: Assessment,
        student: CustomUser,
        decided_by: CustomUser,
        submitted_on: date,
        deadline: tuple[date, date],
    ) -> None:
        """محاولةٌ مرفوضةٌ بسببها في سجلّ المراجعة (خارج أيّ معاملةٍ تُلغى بالرفض) — تاريخُها لا يضيع."""
        from core.models import AuditLog

        # الأثرُ يُنسب إلى صفّ الطالب الغائب نفسِه إن وُجد (يربط المحاولةَ بصاحبها)، وإلّا إلى التقييم.
        row = StudentAssessmentGrade.objects.filter(
            assessment=assessment, student=student, school=assessment.school
        ).first()
        target = row if row is not None else assessment
        AuditLog.log(
            user=decided_by,
            action="update",
            model_name="StudentAssessmentGrade" if row is not None else "Assessment",
            object_id=target.pk,
            object_repr=masked_repr(target),
            changes={
                "excuse_attempt": "rejected_after_deadline",
                "submitted_on": submitted_on.isoformat(),
                "deadline": deadline[0].isoformat(),
                "exam_schedule_end": deadline[1].isoformat(),
            },
            school=assessment.school,
        )

    @staticmethod
    @transaction.atomic
    def _store_excuse(
        assessment: Assessment,
        student: CustomUser,
        excuse_type: str,
        reference: str,
        decided_by: CustomUser,
        submitted_on: date,
    ) -> StudentAssessmentGrade:
        from django.core.exceptions import ValidationError
        from django.utils import timezone

        row = (
            StudentAssessmentGrade.objects.select_for_update()
            .filter(assessment=assessment, student=student, school=assessment.school)
            .first()
        )
        if row is None or not row.is_absent:
            raise ValidationError("لا عذرَ إلّا لغيابٍ رصده المعلّم")
        if row.is_excused:
            raise ValidationError("العذرُ مقرَّرٌ سابقاً")

        row.is_excused = True
        row.excuse_type = excuse_type
        row.excuse_reference = reference[:200]
        row.excuse_submitted_on = submitted_on
        row.excuse_decided_by = decided_by
        row.excuse_decided_at = timezone.now()
        row.save(
            update_fields=[
                "is_excused",
                "excuse_type",
                "excuse_reference",
                "excuse_submitted_on",
                "excuse_decided_by",
                "excuse_decided_at",
            ]
        )
        from .services import GradeService

        GradeService._recalculate_student(assessment, student, decided_by, "decide_excuse")
        # أثرُ تدقيقٍ لا يُعدَّل من الإدارة: الحدثُ وحدَه بلا نوعٍ ولا مرجعٍ (صحّةُ الطالب لا تدخل السجلّ)
        from core.models import AuditLog

        AuditLog.log(
            user=decided_by,
            action="update",
            model_name="StudentAssessmentGrade",
            object_id=row.pk,
            object_repr=masked_repr(row),
            changes={"excuse": "decided"},
            school=assessment.school,
        )
        return row

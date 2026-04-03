"""
exam_control/services.py — Business Logic لوحدة الكنترول
══════════════════════════════════════════════════════════
Service Layer — فصل الـ business logic عن الـ views.

القواعد:
  - transaction.atomic() للعمليات التي تُعدّل أكثر من جدول
  - كل method يُعيد Model أو dict
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction

from .models import (
    ExamGradeSheet,
    ExamIncident,
    ExamRoom,
    ExamSchedule,
    ExamSession,
    ExamSupervisor,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.models import CustomUser, School


class ExamControlService:
    """خدمات نظام الكنترول — الجلسات والجداول والحوادث."""

    @staticmethod
    def get_dashboard_sessions(school: "School"):
        """
        جلسات الكنترول مع إحصائيات مُدمجة — annotate واحد.

        ✅ v5.4: ينقل annotate query من dashboard view إلى service layer.

        Args:
            school: كائن المدرسة

        Returns:
            QuerySet من ExamSession مع annotate
        """
        from django.db.models import Count, Q

        return (
            ExamSession.objects.filter(school=school)
            .annotate(
                incident_count=Count("incidents"),
                pending_sheets=Count(
                    "schedules__grade_sheets",
                    filter=Q(schedules__grade_sheets__status="pending"),
                ),
            )
            .order_by("-start_date")
        )

    @staticmethod
    @transaction.atomic
    def create_session(
        school: "School",
        name: str,
        session_type: str,
        academic_year: str,
        start_date,
        end_date,
        created_by: "CustomUser",
    ) -> ExamSession:
        """
        إنشاء دورة اختبار جديدة.

        Args:
            school: كائن المدرسة
            name: اسم الدورة
            session_type: نوع الدورة (final/midterm/...)
            academic_year: العام الدراسي
            start_date: تاريخ البدء
            end_date: تاريخ الانتهاء
            created_by: المستخدم المنشئ

        Returns:
            ExamSession: الدورة المنشأة
        """
        session = ExamSession.objects.create(
            school=school,
            name=name,
            session_type=session_type,
            academic_year=academic_year,
            start_date=start_date,
            end_date=end_date,
            created_by=created_by,
        )
        logger.info("دورة اختبار جديدة: %s — مدرسة=%s", name, school.code)
        return session

    @staticmethod
    @transaction.atomic
    def create_exam_schedule(
        session: ExamSession,
        room: ExamRoom,
        subject: str,
        grade_level: str,
        exam_date,
        start_time,
        end_time,
        students_count: int = 0,
    ) -> tuple[ExamSchedule, ExamGradeSheet]:
        """
        إنشاء جدول اختبار + ورقة رصد تلقائياً.

        ✅ v5.4: يُحوّل ExamSchedule.create + ExamGradeSheet.create من view إلى service.
        يضمن atomicity — إما كلاهما أو لا.

        Returns:
            tuple (ExamSchedule, ExamGradeSheet): الجدول وورقة الرصد
        """
        sched = ExamSchedule.objects.create(
            session=session,
            room=room,
            subject=subject,
            grade_level=grade_level,
            exam_date=exam_date,
            start_time=start_time,
            end_time=end_time,
            students_count=students_count,
        )
        # إنشاء ورقة رصد تلقائياً
        grade_sheet = ExamGradeSheet.objects.create(
            schedule=sched, papers_count=sched.students_count
        )
        return sched, grade_sheet

    @staticmethod
    @transaction.atomic
    def add_incident(
        session: ExamSession,
        school: "School",
        reported_by: "CustomUser",
        incident_type: str,
        severity,
        description: str,
        student: "CustomUser | None" = None,
        room: ExamRoom | None = None,
        injuries: str = "",
        action_taken: str = "",
        attachments: str = "",
        recommendations: str = "",
    ) -> ExamIncident:
        """
        تسجيل حادثة اختبار + ربط تلقائي بسلوك الطالب إذا كانت غشاً.

        ✅ v5.4: ينقل cross-domain logic (ExamIncident + BehaviorInfraction)
        من incident_add view إلى service layer.
        يُنفَّذ كـ transaction.atomic() لضمان الاتساق.

        Args:
            session: جلسة الاختبار
            school: كائن المدرسة
            reported_by: المستخدم المُبلِّغ
            incident_type: نوع الحادثة (cheating/disruption/other/...)
            severity: درجة الخطورة
            description: وصف الحادثة
            student: الطالب المُتورِّط (اختياري)
            room: قاعة الاختبار (اختياري)
            injuries: الإصابات (اختياري)
            action_taken: الإجراء المتخذ (اختياري)
            attachments: المرفقات (اختياري)
            recommendations: التوصيات (اختياري)

        Returns:
            ExamIncident: سجل الحادثة المنشأ
        """
        incident = ExamIncident.objects.create(
            session=session,
            room=room,
            student=student,
            reported_by=reported_by,
            incident_type=incident_type,
            severity=severity,
            description=description,
            injuries=injuries,
            action_taken=action_taken,
            attachments=attachments,
            recommendations=recommendations,
        )

        # إذا كانت الحادثة غشاً → ربط بسلوك الطالب تلقائياً
        if incident_type == "cheating" and student:
            try:
                from behavior.models import BehaviorInfraction, ViolationCategory

                cat = ViolationCategory.objects.filter(code="D4").first()
                infraction = BehaviorInfraction.objects.create(
                    school=school,
                    student=student,
                    reported_by=reported_by,
                    violation_category=cat,
                    level=4,
                    description=f"غش في اختبار: {description[:200]}",
                    action_taken=action_taken,
                )
                incident.behavior_link = infraction
                incident.save(update_fields=["behavior_link"])
                logger.info(
                    "حادثة غش مرتبطة بمخالفة سلوكية: incident=%s infraction=%s",
                    incident.pk, infraction.pk,
                )
            except Exception as exc:
                logger.exception(
                    "فشل ربط حادثة الغش بسلوك الطالب [incident=%s]: %s",
                    incident.pk, exc,
                )

        logger.info(
            "حادثة اختبار جديدة: نوع=%s جلسة=%s طالب=%s",
            incident_type, session.pk, student.full_name if student else "—",
        )
        return incident

    @staticmethod
    @transaction.atomic
    def update_grade_sheet_status(sheet: ExamGradeSheet, new_status: str) -> ExamGradeSheet:
        """
        تحديث حالة ورقة الرصد — مع timestamp لـ submitted.

        Args:
            sheet: ورقة الرصد
            new_status: الحالة الجديدة

        Returns:
            ExamGradeSheet: الورقة بعد التحديث
        """
        from django.utils import timezone

        sheet.status = new_status
        if new_status == "submitted":
            sheet.submitted_at = timezone.now()
        sheet.save(update_fields=["status", "submitted_at"])
        return sheet

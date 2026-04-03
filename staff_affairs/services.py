"""
staff_affairs/services.py — Business Logic لشؤون الموظفين
═══════════════════════════════════════════════════════════
Service Layer للإجازات — فصل الـ business logic عن الـ views.

القواعد:
  - transaction.atomic() للعمليات التي تُعدّل قاعدة البيانات
  - select_for_update() على LeaveBalance لمنع race condition
  - كل method يُعيد Model أو dict — ليس HttpResponse
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from staff_affairs.models import LeaveBalance, LeaveRequest

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.models import CustomUser, School


class StaffService:
    """خدمات بيانات الموظفين — ملف شامل + إحصائيات."""

    @staticmethod
    def get_staff_profile_data(user, school, year: str) -> dict:
        """
        بيانات ملف الموظف الشامل من 7 نماذج — مع select_related.

        Args:
            user: كائن الموظف (CustomUser)
            school: كائن المدرسة
            year: العام الدراسي

        Returns:
            dict يحتوي: membership, profile, absences, swaps, compensatory,
                        evaluations, leaves, leave_balances, weekly_slots
        """
        from django.db.models import Q

        from core.models.access import Membership
        from operations.models import (
            CompensatorySession,
            ScheduleSlot,
            TeacherAbsence,
            TeacherSwap,
        )
        from staff_affairs.models import LeaveBalance, LeaveRequest

        membership = (
            Membership.objects
            .filter(user=user, school=school, is_active=True)
            .select_related("role", "department_obj")
            .first()
        )

        absences_qs = (
            TeacherAbsence.objects
            .filter(teacher=user, school=school)
            .order_by("-date")
        )
        absence_count = absences_qs.count()
        absences_recent = list(absences_qs[:10])

        swaps_count = TeacherSwap.objects.filter(
            Q(teacher_a=user) | Q(teacher_b=user), school=school,
        ).count()

        compensatory_count = CompensatorySession.objects.filter(
            teacher=user, school=school,
        ).count()

        evaluations = list(
            school.staff_evaluations.filter(staff=user)
            .order_by("-academic_year")[:5]
        ) if hasattr(school, "staff_evaluations") else []

        leaves = list(
            LeaveRequest.objects
            .filter(staff=user, school=school)
            .order_by("-created_at")[:10]
        )

        leave_balances = list(
            LeaveBalance.objects.filter(staff=user, school=school, academic_year=year)
        )

        weekly_slots = ScheduleSlot.objects.filter(
            teacher=user, school=school, is_active=True,
        ).count()

        return {
            "membership": membership,
            "profile": getattr(user, "profile", None),
            "absence_count": absence_count,
            "absences_recent": absences_recent,
            "swaps_count": swaps_count,
            "compensatory_count": compensatory_count,
            "evaluations": evaluations,
            "leaves": leaves,
            "leave_balances": leave_balances,
            "weekly_slots": weekly_slots,
        }


class LeaveService:
    """خدمات الإجازات — إنشاء + مراجعة + إحصائيات."""

    DEFAULT_ANNUAL_DAYS = 30  # وفق قانون 15/2016

    @staticmethod
    @transaction.atomic
    def create_leave_request(
        school: "School",
        staff: "CustomUser",
        leave_type: str,
        start_date,
        end_date,
        days_count: int,
        reason: str,
        attachment=None,
        created_by: "CustomUser | None" = None,
    ) -> LeaveRequest:
        """
        إنشاء طلب إجازة جديد.

        Args:
            school: كائن المدرسة
            staff: كائن الموظف
            leave_type: نوع الإجازة (annual/sick/...)
            start_date: تاريخ البداية
            end_date: تاريخ النهاية
            days_count: عدد الأيام
            reason: السبب
            attachment: ملف مرفق (اختياري)
            created_by: المستخدم الذي أنشأ الطلب

        Returns:
            LeaveRequest: الطلب المنشأ
        """
        creator = created_by or staff
        leave = LeaveRequest.objects.create(
            school=school,
            staff=staff,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            days_count=days_count,
            reason=reason,
            attachment=attachment,
            academic_year=settings.CURRENT_ACADEMIC_YEAR,
            created_by=creator,
            updated_by=creator,
        )
        logger.info(
            "طلب إجازة جديد: %s لـ %s (%d يوم) في %s",
            leave.pk, staff.full_name, days_count, school.code,
        )
        return leave

    @staticmethod
    @transaction.atomic
    def review_leave(
        leave: LeaveRequest,
        action: str,
        reviewer: "CustomUser",
        rejection_reason: str = "",
    ) -> LeaveRequest:
        """
        مراجعة طلب إجازة — موافقة أو رفض.

        عند الموافقة: يُحدَّث رصيد الإجازات بـ select_for_update()
        لمنع race condition إذا راجع مديران في نفس الوقت.

        Args:
            leave: كائن طلب الإجازة
            action: "approved" أو "rejected"
            reviewer: المستخدم المراجع
            rejection_reason: سبب الرفض (فقط عند action="rejected")

        Returns:
            LeaveRequest: الطلب بعد التحديث

        Raises:
            ValueError: إذا كان action غير صالح أو الطلب ليس قيد الانتظار
        """
        valid_actions = {"approved", "rejected"}
        if action not in valid_actions:
            raise ValueError(f"إجراء غير صالح: '{action}'. المتاح: {valid_actions}")

        if leave.status != "pending":
            raise ValueError(
                f"لا يمكن مراجعة طلب بحالة '{leave.get_status_display()}' — "
                "الطلب يجب أن يكون قيد الانتظار."
            )

        leave.status = action
        leave.reviewed_by = reviewer
        leave.reviewed_at = timezone.now()
        leave.updated_by = reviewer

        if action == "rejected":
            leave.rejection_reason = rejection_reason

        leave.save(update_fields=[
            "status", "reviewed_by", "reviewed_at",
            "rejection_reason", "updated_by", "updated_at",
        ])

        # ── تحديث رصيد الإجازات عند الموافقة ──────────────────
        if action == "approved":
            # select_for_update: يمنع race condition على balance.used_days
            balance, _ = LeaveBalance.objects.select_for_update().get_or_create(
                school=leave.school,
                staff=leave.staff,
                academic_year=leave.academic_year,
                leave_type=leave.leave_type,
                defaults={"total_days": LeaveService.DEFAULT_ANNUAL_DAYS},
            )
            balance.used_days += leave.days_count
            balance.save(update_fields=["used_days"])
            logger.info(
                "رصيد إجازات %s: استُخدم %d يوم (إجمالي مُستخدم: %d)",
                leave.staff.full_name, leave.days_count, balance.used_days,
            )

        logger.info(
            "طلب إجازة #%s: %s بواسطة %s",
            leave.pk, action, reviewer.full_name,
        )
        return leave

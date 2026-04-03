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

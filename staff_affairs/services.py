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
    """خدمات بيانات الموظفين — لوحة التحكم + ملف شامل."""

    @staticmethod
    def get_dashboard_stats(school, year: str, today=None) -> dict:
        """
        إحصائيات لوحة شؤون الموظفين — 7 KPIs في استعلامات منفصلة.

        Args:
            school: كائن المدرسة
            year: العام الدراسي
            today: تاريخ اليوم (افتراضي: اليوم الفعلي)

        Returns:
            dict يحتوي: total_staff, absences_today, pending_swaps,
                        pending_leaves, pending_evals, expiring_licenses,
                        role_distribution, recent_absences, recent_leaves
        """
        from datetime import timedelta

        from django.db.models import Count
        from django.utils import timezone

        from core.models.access import Membership
        from core.models.user import CustomUser
        from operations.models import StaffEvaluation, TeacherAbsence, TeacherSwap
        from staff_affairs.models import LeaveRequest

        today = today or timezone.localdate()

        total_staff = (
            Membership.objects.filter(school=school, is_active=True)
            .exclude(role__name__in=("student", "parent"))
            .count()
        )

        absences_today = TeacherAbsence.objects.filter(
            school=school,
            date=today,
        ).count()

        pending_swaps = TeacherSwap.objects.filter(
            school=school,
            status__in=["pending_b", "pending_coordinator", "pending_vp"],
        ).count()

        pending_leaves = LeaveRequest.objects.filter(
            school=school,
            status="pending",
        ).count()

        pending_evals = StaffEvaluation.objects.filter(
            school=school,
            status="draft",
            academic_year=year,
        ).count()

        expiring_licenses = CustomUser.objects.filter(
            memberships__school=school,
            memberships__is_active=True,
            professional_license_expiry__isnull=False,
            professional_license_expiry__lte=today + timedelta(days=90),
            professional_license_expiry__gt=today,
        ).count()

        role_distribution_raw = (
            Membership.objects.filter(school=school, is_active=True)
            .exclude(role__name__in=("student", "parent"))
            .values("role__name")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        recent_absences = list(
            TeacherAbsence.objects.filter(school=school)
            .select_related("teacher")
            .order_by("-date")[:5]
        )

        recent_leaves = list(
            LeaveRequest.objects.filter(school=school)
            .select_related("staff")
            .order_by("-created_at")[:5]
        )

        return {
            "total_staff": total_staff,
            "absences_today": absences_today,
            "pending_swaps": pending_swaps,
            "pending_leaves": pending_leaves,
            "pending_evals": pending_evals,
            "expiring_licenses": expiring_licenses,
            "role_distribution_raw": list(role_distribution_raw),
            "recent_absences": recent_absences,
            "recent_leaves": recent_leaves,
        }

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
            Membership.objects.filter(user=user, school=school, is_active=True)
            .select_related("role", "department_obj")
            .first()
        )

        absences_qs = TeacherAbsence.objects.filter(teacher=user, school=school).order_by("-date")
        absence_count = absences_qs.count()
        absences_recent = list(absences_qs[:10])

        swaps_count = TeacherSwap.objects.filter(
            Q(teacher_a=user) | Q(teacher_b=user),
            school=school,
        ).count()

        compensatory_count = CompensatorySession.objects.filter(
            teacher=user,
            school=school,
        ).count()

        evaluations = (
            list(school.staff_evaluations.filter(staff=user).order_by("-academic_year")[:5])
            if hasattr(school, "staff_evaluations")
            else []
        )

        leaves = list(
            LeaveRequest.objects.filter(staff=user, school=school).order_by("-created_at")[:10]
        )

        leave_balances = list(
            LeaveBalance.objects.filter(staff=user, school=school, academic_year=year)
        )

        weekly_slots = ScheduleSlot.objects.filter(
            teacher=user,
            school=school,
            is_active=True,
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

    @staticmethod
    def get_license_overview(school, today=None) -> dict:
        """
        نظرة شاملة على الرخص المهنية — باستخدام DB filters بدل Python comprehensions.

        ✅ v5.4: بدل جلب جميع الموظفين إلى Python وتصنيفهم،
        نستخدم استعلامات منفصلة تُعيد QuerySets مباشرة (أسرع + أقل استهلاكاً للذاكرة).

        Args:
            school: كائن المدرسة
            today: تاريخ اليوم (افتراضي: اليوم الفعلي)

        Returns:
            dict يحتوي: expired, expiring_soon, valid, no_license
        """
        from datetime import timedelta

        from django.db.models import Q
        from django.utils import timezone

        from core.models.access import Membership
        from core.models.user import CustomUser

        today = today or timezone.localdate()
        ninety_days = today + timedelta(days=90)

        base_qs = CustomUser.objects.filter(
            memberships__school=school,
            memberships__is_active=True,
            professional_license_number__isnull=False,
        ).exclude(professional_license_number="")

        expired = base_qs.filter(
            professional_license_expiry__isnull=False,
            professional_license_expiry__lt=today,
        ).order_by("professional_license_expiry")

        expiring_soon = base_qs.filter(
            professional_license_expiry__isnull=False,
            professional_license_expiry__gte=today,
            professional_license_expiry__lte=ninety_days,
        ).order_by("professional_license_expiry")

        valid = base_qs.filter(
            professional_license_expiry__isnull=False,
            professional_license_expiry__gt=ninety_days,
        ).order_by("professional_license_expiry")

        no_license = (
            Membership.objects.filter(
                school=school,
                is_active=True,
                role__name__in=("teacher", "coordinator", "ese_teacher"),
            )
            .filter(
                Q(user__professional_license_number__isnull=True)
                | Q(user__professional_license_number="")
            )
            .select_related("user")
        )

        return {
            "expired": expired,
            "expiring_soon": expiring_soon,
            "valid": valid,
            "no_license": no_license,
        }


class LeaveService:
    """خدمات الإجازات — إنشاء + مراجعة + إحصائيات."""

    DEFAULT_ANNUAL_DAYS = 30  # وفق قانون 15/2016

    @staticmethod
    @transaction.atomic
    def create_leave_request(
        school: School,
        staff: CustomUser,
        leave_type: str,
        start_date,
        end_date,
        days_count: int,
        reason: str,
        attachment=None,
        created_by: CustomUser | None = None,
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
            leave.pk,
            staff.full_name,
            days_count,
            school.code,
        )
        return leave

    @staticmethod
    @transaction.atomic
    def review_leave(
        leave: LeaveRequest,
        action: str,
        reviewer: CustomUser,
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

        leave.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
                "rejection_reason",
                "updated_by",
                "updated_at",
            ]
        )

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
                leave.staff.full_name,
                leave.days_count,
                balance.used_days,
            )

        logger.info(
            "طلب إجازة #%s: %s بواسطة %s",
            leave.pk,
            action,
            reviewer.full_name,
        )
        return leave

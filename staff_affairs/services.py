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

from django.db import transaction
from django.utils import timezone

from core.academic_calendar import academic_year_for_school
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

        # أشخاصٌ لا عضويّات: من كان معلّماً ومنسّقاً رجلٌ واحد.
        total_staff = (
            Membership.objects.filter(school=school, is_active=True)
            .exclude(role__name__in=("student", "parent"))
            .values("user")
            .distinct()
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

        # الكادرُ أوّلاً: موظّفٌ ابنُه في المدرسة له عضويّتان، ولو قُرئت عضويّةُ
        # وليّ الأمر لظهر ملفُّه بلا دورٍ ولا قسمٍ ولا سجلِّ التحاق.
        from core.models.user import role_rank
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
            .order_by(role_rank(), "joined_at")
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

        weekly_slots = ScheduleSlot.objects.live(school, year=year).filter(teacher=user).count()

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
            academic_year=academic_year_for_school(school),
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


class StaffAttendanceService:
    """خدماتُ حضورِ الموظّفين — وسياسةُ الشحانية.

    الحقائقُ:
      - بدايةُ الدوام: 7:00 صباحاً
      - حدُّ التأخّر: 9:00 (بعدها غياب)
      - سقفُ الاستئذان: 7 ساعات/شهر، حدٌّ أقصى ساعتان/مرّة

    مرجعُ السياسة: وثيقة ت/د 2027/01 من مدرسة الشحانية.
    """

    WORK_START_TIME = "07:00"  # نص البند 1.1
    LATE_THRESHOLD = "09:00"  # نص البند 2.4
    MONTHLY_PERMIT_LIMIT = 7 * 60  # 7 ساعات = 420 دقيقة — البند 4.2
    PERMIT_MAX_DURATION = 2 * 60  # 2 ساعات = 120 دقيقة — البند 4.4

    @staticmethod
    def calculate_status(check_in_time) -> str:
        """
        حسابُ حالةِ الحضورِ حسبَ وقتِ الدخول.

        قاعدةُ السياسة (البند 1.1، 2.1، 2.4):
          - ≤7:00 → حاضر
          - 7:01 - 8:59 → متأخّر
          - ≥9:00 → غائب

        Args:
            check_in_time: datetime.time أو str (HH:MM)

        Returns:
            str: 'present' / 'late' / 'absent'
        """
        from datetime import time

        if isinstance(check_in_time, str):
            h, m = map(int, check_in_time.split(":"))
            check_in_time = time(h, m)

        work_start = time(7, 0)
        late_threshold = time(9, 0)

        if check_in_time <= work_start:
            return "present"
        elif work_start < check_in_time < late_threshold:
            return "late"
        else:
            return "absent"

    @staticmethod
    @transaction.atomic
    def record_attendance(
        school: School,
        staff: CustomUser,
        date,
        check_in_time=None,
        check_out_time=None,
        permit_minutes: int = 0,
        notes: str = "",
    ):
        """
        تسجيلُ حضورِ موظّفٍ في يومٍ معيّنٍ.

        تُحسَبُ الحالةُ تلقائياً بناءً على وقتِ الدخول.

        Args:
            school: كائنُ المدرسة
            staff: كائنُ الموظّف
            date: تاريخُ اليوم
            check_in_time: وقتُ الدخول (datetime.time)
            check_out_time: وقتُ الخروج (datetime.time)
            permit_minutes: دقائقُ الاستئذانِ المقبولة
            notes: ملاحظاتٌ إضافية

        Returns:
            StaffAttendance: السجلُّ المُنشأ أو المُحدَّث
        """
        from staff_affairs.models import StaffAttendance

        # حسابُ الحالة بناءً على وقتِ الدخول
        status = "present"
        if check_in_time:
            status = StaffAttendanceService.calculate_status(check_in_time)

        attendance, created = StaffAttendance.objects.update_or_create(
            school=school,
            staff=staff,
            date=date,
            defaults={
                "check_in_time": check_in_time,
                "check_out_time": check_out_time,
                "permit_minutes": permit_minutes,
                "status": status,
                "notes": notes,
            },
        )

        logger.info(
            "حضورٌ مسجَّل: %s — %s (%s)",
            staff.full_name,
            date,
            attendance.get_status_display(),
        )
        return attendance

    @staticmethod
    def get_monthly_report(school: School, staff: CustomUser, year: str, month: int) -> dict:
        """
        تقريرٌ شهريّ لحضورِ موظّفٍ.

        يحسبُ:
          - عددَ أيّامِ الحضورِ والتأخّرِ والغيابِ
          - إجمالياً
          - رصيدَ الاستئذانِ المتبقي

        Args:
            school: كائنُ المدرسة
            staff: كائنُ الموظّف
            year: السنةُ (YYYY)
            month: الشهرُ (1-12)

        Returns:
            dict: {
                'days': [{'date': date, 'status': str, ...}],
                'summary': {'present': int, 'late': int, 'absent': int},
                'permit_used': int,  # دقائق مستخدمة في الشهر
                'permit_remaining': int  # دقائق متبقية
            }
        """
        from calendar import monthrange
        from datetime import date as date_type

        from staff_affairs.models import PermitRequest, StaffAttendance

        # استخراجُ أيّامِ الشهر
        start_date = date_type(year, month, 1)
        last_day = monthrange(year, month)[1]
        end_date = date_type(year, month, last_day)

        attendance_records = StaffAttendance.objects.filter(
            school=school,
            staff=staff,
            date__gte=start_date,
            date__lte=end_date,
        ).order_by("date")

        # حسابُ الملخّص
        summary = {"present": 0, "late": 0, "absent": 0}
        days_list = []

        for record in attendance_records:
            summary[record.status] += 1
            days_list.append(
                {
                    "date": record.date,
                    "status": record.get_status_display(),
                    "check_in_time": record.check_in_time,
                    "check_out_time": record.check_out_time,
                    "permit_minutes": record.permit_minutes,
                }
            )

        # حسابُ رصيدِ الاستئذان
        approved_permits = PermitRequest.objects.filter(
            school=school,
            staff=staff,
            date__gte=start_date,
            date__lte=end_date,
            status="approved",
        )
        permit_used = sum(p.duration_minutes for p in approved_permits)
        permit_remaining = max(0, StaffAttendanceService.MONTHLY_PERMIT_LIMIT - permit_used)

        return {
            "days": days_list,
            "summary": summary,
            "permit_used": permit_used,
            "permit_remaining": permit_remaining,
        }

    @staticmethod
    @transaction.atomic
    def approve_permit(
        permit_request,
        reviewer: CustomUser,
    ):
        """
        اعتمادُ طلبِ إذنٍ — مع فحصِ السقفِ الشهريّ والحدّ الأقصى يومياً.

        القيودُ (البند 4.2، 4.3، 4.4):
          - سقفٌ شهريّ: 7 ساعات
          - حدٌّ يوميّ: إذنٌ واحدٌ فقط
          - حدٌّ فرديّ: ساعتان أقصى

        Args:
            permit_request: كائنُ PermitRequest
            reviewer: المستخدمُ المراجع

        Returns:
            PermitRequest: الطلبُ بعد الاعتماد

        Raises:
            ValueError: إذا تُجاوزت القيودُ
        """
        from staff_affairs.models import PermitRequest

        # فحصُ السقفِ اليوميّ: لا إذنٌ آخر مقبول في نفسِ اليوم
        existing_approved = PermitRequest.objects.filter(
            school=permit_request.school,
            staff=permit_request.staff,
            date=permit_request.date,
            status="approved",
        ).exclude(pk=permit_request.pk)

        if existing_approved.exists():
            raise ValueError(
                f"يوجدُ إذنٌ آخرُ مقبولٌ في نفسِ اليوم (البند 4.3)"
            )

        # فحصُ السقفِ الشهريّ
        from calendar import monthrange
        from datetime import date as date_type

        start_date = date_type(permit_request.date.year, permit_request.date.month, 1)
        last_day = monthrange(permit_request.date.year, permit_request.date.month)[1]
        end_date = date_type(permit_request.date.year, permit_request.date.month, last_day)

        approved_permits = PermitRequest.objects.filter(
            school=permit_request.school,
            staff=permit_request.staff,
            date__gte=start_date,
            date__lte=end_date,
            status="approved",
        ).exclude(pk=permit_request.pk)

        total_permit_minutes = sum(p.duration_minutes for p in approved_permits)
        total_permit_minutes += permit_request.duration_minutes

        if total_permit_minutes > StaffAttendanceService.MONTHLY_PERMIT_LIMIT:
            remaining = StaffAttendanceService.MONTHLY_PERMIT_LIMIT - (
                total_permit_minutes - permit_request.duration_minutes
            )
            raise ValueError(
                f"سقفُ الاستئذانِ الشهريّ (7 ساعات) تُجاوز. "
                f"متبقٍ: {remaining} دقيقة فقط (البند 4.2)"
            )

        # اعتمادٌ ناجح
        permit_request.status = "approved"
        permit_request.reviewed_by = reviewer
        permit_request.reviewed_at = timezone.now()
        permit_request.save(
            update_fields=["status", "reviewed_by", "reviewed_at"]
        )

        logger.info(
            "إذنٌ معتمَد: %s لـ %s (%d دقيقة)",
            permit_request.pk,
            permit_request.staff.full_name,
            permit_request.duration_minutes,
        )
        return permit_request

    @staticmethod
    def reject_permit(
        permit_request,
        reviewer: CustomUser,
        rejection_reason: str = "",
    ):
        """
        رفضُ طلبِ إذنٍ.

        Args:
            permit_request: كائنُ PermitRequest
            reviewer: المستخدمُ المراجع
            rejection_reason: سببُ الرفض

        Returns:
            PermitRequest: الطلبُ بعد الرفض
        """
        permit_request.status = "rejected"
        permit_request.reviewed_by = reviewer
        permit_request.reviewed_at = timezone.now()
        permit_request.rejection_reason = rejection_reason
        permit_request.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
                "rejection_reason",
            ]
        )

        logger.info(
            "إذنٌ مرفوضٌ: %s — %s",
            permit_request.pk,
            rejection_reason or "بلا سبب",
        )
        return permit_request

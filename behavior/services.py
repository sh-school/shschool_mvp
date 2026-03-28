"""
behavior/services.py
━━━━━━━━━━━━━━━━━━━━
Business logic لوحدة السلوك — مستخلص من views.py

يشمل:
  - حساب النقاط والتقييم السلوكي
  - إحصائيات لوحة التحكم
  - الملف السلوكي للطالب
  - إحصائيات اللجنة
  - إشعار أولياء الأمور
  - بيانات التقرير الدوري
"""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

from django.conf import settings
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

logger = logging.getLogger(__name__)

from core.models import (
    BehaviorInfraction,
    BehaviorPointRecovery,
    ParentStudentLink,
    StudentEnrollment,
)

if TYPE_CHECKING:
    from core.models import CustomUser, School

# ── ثوابت موحدة من constants.py ────────────────────────────
from .constants import (  # noqa: E402,F401
    ESCALATION_STEPS,
    LEVEL_AUTHORITY,
    LEVEL_DESC,
    LEVEL_DISPLAY,
    POINTS_BY_LEVEL,
)

PERIOD_CHOICES = [
    ("full", "العام كاملاً"),
    ("S1", "الفصل الأول"),
    ("S2", "الفصل الثاني"),
]


class BehaviorPermissions:
    """صلاحيات وحدة السلوك"""

    REPORTER_ROLES = {
        "principal",
        "vice_admin",
        "vice_academic",
        "coordinator",
        "teacher",
        "ese_teacher",
        "social_worker",
        "specialist",
        "admin_supervisor",
        "admin",
    }
    COMMITTEE_ROLES = {"principal", "vice_admin", "vice_academic", "social_worker", "specialist"}
    SUMMON_ROLES = {"principal", "vice_admin", "vice_academic", "social_worker", "psychologist"}

    @staticmethod
    def can_report(user: CustomUser) -> bool:
        return user.get_role() in BehaviorPermissions.REPORTER_ROLES

    @staticmethod
    def is_committee(user: CustomUser) -> bool:
        return user.get_role() in BehaviorPermissions.COMMITTEE_ROLES or user.is_superuser

    @staticmethod
    def can_summon(user: CustomUser) -> bool:
        return user.get_role() in BehaviorPermissions.SUMMON_ROLES or user.is_superuser


class BehaviorService:
    # ── حساب النقاط السلوكية للطالب ─────────────────────────
    @staticmethod
    def get_student_score(
        student: CustomUser,
        school: School | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict:
        """
        يحسب النقاط السلوكية للطالب (من 100).
        Returns: dict with total_deducted, total_restored, net_score, rating, rating_color
        """
        qs = BehaviorInfraction.objects.filter(student=student)
        if school:
            qs = qs.filter(school=school)
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)

        total_deducted = qs.aggregate(Sum("points_deducted"))["points_deducted__sum"] or 0

        recovery_qs = BehaviorPointRecovery.objects.filter(infraction__student=student)
        if school:
            recovery_qs = recovery_qs.filter(infraction__school=school)
        if date_from:
            recovery_qs = recovery_qs.filter(infraction__date__gte=date_from)
        if date_to:
            recovery_qs = recovery_qs.filter(infraction__date__lte=date_to)

        total_restored = recovery_qs.aggregate(Sum("points_restored"))["points_restored__sum"] or 0

        net_score = max(0, min(100, 100 - total_deducted + total_restored))

        if net_score >= 90:
            rating, rating_color = "ممتاز", "green"
        elif net_score >= 75:
            rating, rating_color = "جيد جداً", "blue"
        elif net_score >= 60:
            rating, rating_color = "جيد", "amber"
        else:
            rating, rating_color = "يحتاج تطوير", "red"

        return {
            "total_deducted": total_deducted,
            "total_restored": total_restored,
            "net_score": net_score,
            "rating": rating,
            "rating_color": rating_color,
        }

    # ── إحصائيات لوحة التحكم ────────────────────────────────
    @staticmethod
    def get_dashboard_stats(school: School, student_ids=None) -> dict:
        """
        إحصائيات لوحة التحكم الرئيسية.

        student_ids: قائمة IDs الطلاب المرئيّين (للمعلم/المنسق).
                     None = كل طلاب المدرسة (القيادة/المدير).
        """
        base = BehaviorInfraction.objects.filter(school=school)
        if student_ids is not None:
            base = base.filter(student_id__in=student_ids)

        stats = base.values("level").annotate(count=Count("id"))

        total_deducted = base.aggregate(Sum("points_deducted"))["points_deducted__sum"] or 0

        recovery_qs = BehaviorPointRecovery.objects.filter(infraction__school=school)
        if student_ids is not None:
            recovery_qs = recovery_qs.filter(infraction__student_id__in=student_ids)
        total_restored = (
            recovery_qs.aggregate(Sum("points_restored"))["points_restored__sum"] or 0
        )

        recent = (
            base.select_related("student", "reported_by", "violation_category")
            .order_by("-date")[:15]
        )

        critical_unresolved = (
            base.filter(level__in=[3, 4], is_resolved=False)
            .select_related("student", "violation_category")
            .prefetch_related("recovery")
        )

        return {
            "stats": stats,
            "total_deducted": total_deducted,
            "total_restored": total_restored,
            "net_deducted": total_deducted - total_restored,
            "recent_infractions": recent,
            "critical_unresolved": critical_unresolved,
        }

    # ── الملف السلوكي للطالب ────────────────────────────────
    @staticmethod
    def get_student_profile(student: CustomUser) -> dict:
        """بيانات الملف السلوكي الكامل"""
        infractions = (
            BehaviorInfraction.objects.filter(student=student)
            .select_related(
                "reported_by", "recovery", "recovery__approved_by", "violation_category"
            )
            .order_by("-date")
        )

        score = BehaviorService.get_student_score(student)
        status_color = (
            "green"
            if score["net_score"] >= 80
            else ("yellow" if score["net_score"] >= 60 else "red")
        )

        by_level: dict = {1: 0, 2: 0, 3: 0, 4: 0}
        for inf in infractions:
            by_level[inf.level] = by_level.get(inf.level, 0) + 1

        return {
            "infractions": infractions,
            "by_level": by_level,
            "status_color": status_color,
            **score,
        }

    # ── إحصائيات اللجنة ────────────────────────────────────
    @staticmethod
    def get_committee_data(school: School) -> dict:
        """بيانات لوحة لجنة الضبط السلوكي"""
        open_cases = (
            BehaviorInfraction.objects.filter(school=school, level__in=[3, 4], is_resolved=False)
            .select_related("student", "reported_by", "violation_category")
            .order_by("-date")
        )

        resolved_cases = (
            BehaviorInfraction.objects.filter(school=school, level__in=[3, 4], is_resolved=True)
            .select_related("student", "reported_by", "recovery", "recovery__approved_by")
            .order_by("-date")[:20]
        )

        stats = {
            "open_count": open_cases.count(),
            "resolved_count": BehaviorInfraction.objects.filter(
                school=school, level__in=[3, 4], is_resolved=True
            ).count(),
            "level3": open_cases.filter(level=3).count(),
            "level4": open_cases.filter(level=4).count(),
        }

        return {
            "open_cases": open_cases,
            "resolved_cases": resolved_cases,
            "stats": stats,
        }

    # ── تنفيذ قرار اللجنة ──────────────────────────────────
    @staticmethod
    def apply_committee_decision(
        infraction: BehaviorInfraction,
        decision: str,
        action: str = "",
        restore_pts: int = 0,
        reason: str = "",
        approved_by: CustomUser | None = None,
        **kwargs,
    ) -> tuple:
        """
        تطبيق قرار اللجنة على المخالفة.
        Returns: (success_message, message_level)
        """
        if action:
            infraction.action_taken = (infraction.action_taken + "\n" + action).strip()

        if decision == "resolve":
            infraction.is_resolved = True
            if restore_pts > 0 and not hasattr(infraction, "recovery"):
                BehaviorPointRecovery.objects.create(
                    infraction=infraction,
                    reason=reason or "قرار لجنة الضبط السلوكي",
                    points_restored=restore_pts,
                    approved_by=approved_by,
                )
            infraction.save()
            return f"✅ تم حل المخالفة للطالب {infraction.student.full_name}", "success"

        elif decision == "escalate":
            if infraction.level < 4:
                infraction.level = 4
                infraction.save()
            BehaviorService._auto_summon_parent(infraction, approved_by, "تصعيد مخالفة إلى الدرجة الرابعة")
            return "⬆️ تم تصعيد المخالفة إلى الدرجة الرابعة + استدعاء ولي الأمر", "warning"

        elif decision == "suspend":
            infraction.action_taken = (
                infraction.action_taken + "\n[قرار اللجنة: إيقاف مؤقت]"
            ).strip()
            infraction.suspension_type = kwargs.get("suspension_type", "internal")
            infraction.suspension_days = kwargs.get("suspension_days", 1)
            infraction.save()
            BehaviorService._auto_summon_parent(infraction, approved_by, "إيقاف مؤقت بقرار لجنة الضبط")
            return "📋 تم تسجيل قرار الإيقاف المؤقت + استدعاء ولي الأمر", "info"

        return "لم يتم تحديد قرار", "error"

    # ── استدعاء تلقائي لولي الأمر (قرار لجنة الضبط) ────────
    @staticmethod
    def _auto_summon_parent(
        infraction: BehaviorInfraction,
        approved_by: CustomUser | None,
        reason: str,
    ) -> None:
        """يرسل استدعاء ولي أمر تلقائياً عند قرار لجنة الضبط (درجة 3-4)."""
        try:
            from notifications.hub import NotificationHub

            school = infraction.school
            student = infraction.student
            sender_name = approved_by.full_name if approved_by else "لجنة الضبط السلوكي"

            title = f"استدعاء ولي أمر — {student.full_name}"
            violation_name = (
                infraction.violation_category.name_ar
                if infraction.violation_category
                else infraction.get_level_display()
            )
            body = (
                f"بناءً على قرار لجنة الضبط السلوكي:\n"
                f"السبب: {reason}\n"
                f"المخالفة: {violation_name} (درجة {infraction.level})\n"
                f"من: {sender_name}"
            )

            NotificationHub.dispatch_to_parents(
                event_type="parent_summon",
                school=school,
                student=student,
                title=title,
                body=body,
                related_url=f"/behavior/student/{student.pk}/",
                sent_by=approved_by,
            )
            logger.info("Auto-summon sent for student %s (infraction %s)", student.pk, infraction.pk)
        except Exception:
            logger.exception("Failed to auto-summon parent for infraction %s", infraction.pk)

    # ── إحصائيات مقيّدة (للمعلم/المنسق) ───────────────────
    @staticmethod
    def get_statistics_scoped(
        school: School,
        student_ids,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict:
        """
        إحصائيات سلوكية مقيّدة بمجموعة طلاب محددة (للمعلم/المنسق).
        student_ids: مجموعة IDs أو قائمة — لا يجوز None هنا.
        """
        if not date_from or not date_to:
            today = timezone.now().date()
            start_year = today.year if today.month >= 9 else today.year - 1
            if not date_from:
                date_from = date(start_year, 9, 1)
            if not date_to:
                date_to = date(start_year + 1, 6, 30)

        all_inf = BehaviorInfraction.objects.filter(
            school=school,
            date__gte=date_from,
            date__lte=date_to,
            student_id__in=student_ids,
        )
        total = all_inf.count()

        by_level = {lvl: all_inf.filter(level=lvl).count() for lvl in [1, 2, 3, 4]}

        top_students = (
            all_inf.values("student__full_name", "student__id")
            .annotate(count=Count("id"), pts=Sum("points_deducted"))
            .order_by("-count")[:10]
        )

        monthly = (
            all_inf.annotate(month=TruncMonth("date"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )

        top_classes = (
            all_inf.values(
                "student__enrollments__class_group__grade",
                "student__enrollments__class_group__section",
            )
            .annotate(count=Count("id"))
            .order_by("-count")[:5]
        )

        resolved_pct = round(all_inf.filter(is_resolved=True).count() / total * 100) if total else 0

        return {
            "by_level": by_level,
            "total": total,
            "top_students": top_students,
            "monthly": monthly,
            "top_classes": top_classes,
            "resolved_pct": resolved_pct,
        }

    # ── إحصائيات شاملة (تقرير المدير) ──────────────────────
    @staticmethod
    def get_statistics(
        school: School,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict:
        """إحصائيات شاملة لوحدة السلوك — تقرير المدير"""
        if not date_from or not date_to:
            today = timezone.now().date()
            # العام الدراسي يبدأ في سبتمبر
            start_year = today.year if today.month >= 9 else today.year - 1
            if not date_from:
                date_from = date(start_year, 9, 1)
            if not date_to:
                date_to = date(start_year + 1, 6, 30)

        all_inf = BehaviorInfraction.objects.filter(
            school=school, date__gte=date_from, date__lte=date_to
        )
        total = all_inf.count()

        by_level = {lvl: all_inf.filter(level=lvl).count() for lvl in [1, 2, 3, 4]}

        top_students = (
            all_inf.values("student__full_name", "student__id")
            .annotate(count=Count("id"), pts=Sum("points_deducted"))
            .order_by("-count")[:10]
        )

        monthly = (
            all_inf.annotate(month=TruncMonth("date"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )

        top_classes = (
            all_inf.values(
                "student__enrollments__class_group__grade",
                "student__enrollments__class_group__section",
            )
            .annotate(count=Count("id"))
            .order_by("-count")[:5]
        )

        resolved_pct = round(all_inf.filter(is_resolved=True).count() / total * 100) if total else 0

        return {
            "by_level": by_level,
            "total": total,
            "top_students": top_students,
            "monthly": monthly,
            "top_classes": top_classes,
            "resolved_pct": resolved_pct,
        }

    # ── بيانات التقرير الدوري ───────────────────────────────
    @staticmethod
    def get_report_period(period: str, year: str = settings.CURRENT_ACADEMIC_YEAR) -> tuple:
        """يحسب نطاق التاريخ والعنوان حسب الفترة والعام الدراسي"""
        try:
            start_year, end_year = (int(y) for y in str(year).split("-"))
        except (ValueError, AttributeError):
            today = timezone.now().date()
            start_year = today.year if today.month >= 9 else today.year - 1
            end_year = start_year + 1

        if period == "S1":
            return date(start_year, 9, 1), date(end_year, 1, 31), "الفصل الأول"
        elif period == "S2":
            return date(end_year, 2, 1), date(end_year, 6, 30), "الفصل الثاني"
        else:
            return date(start_year, 9, 1), date(end_year, 6, 30), "العام الدراسي كاملاً"

    @staticmethod
    def get_student_report_data(
        student: CustomUser,
        school: School,
        period: str = "full",
        year: str = settings.CURRENT_ACADEMIC_YEAR,
    ) -> dict:
        """بيانات التقرير السلوكي الدوري الكامل"""
        date_from, date_to, period_label = BehaviorService.get_report_period(period, year)

        infractions = (
            BehaviorInfraction.objects.filter(
                student=student,
                school=school,
                date__gte=date_from,
                date__lte=date_to,
            )
            .select_related(
                "reported_by", "recovery", "recovery__approved_by", "violation_category"
            )
            .order_by("date")
        )

        score = BehaviorService.get_student_score(student, school, date_from, date_to)

        by_level: dict = {1: [], 2: [], 3: [], 4: []}
        for inf in infractions:
            by_level[inf.level].append(inf)

        parent_links = ParentStudentLink.objects.filter(
            student=student, school=school
        ).select_related("parent")

        return {
            "infractions": infractions,
            "by_level": by_level,
            "period_label": period_label,
            "date_from": date_from,
            "date_to": date_to,
            "parent_links": parent_links,
            **score,
        }

    # ── بيانات PDF المخالفة ─────────────────────────────────
    @staticmethod
    def get_infraction_context(infraction: BehaviorInfraction) -> dict:
        """بيانات مشتركة لنماذج PDF/Word"""
        school = infraction.school
        student = infraction.student

        enrollment = (
            StudentEnrollment.objects.filter(
                student=student, class_group__school=school, is_active=True
            )
            .select_related("class_group")
            .first()
        )
        cg = enrollment.class_group if enrollment else None
        class_name = str(cg) if cg else None

        try:
            link = (
                ParentStudentLink.objects.filter(student=student).select_related("parent").first()
            )
            parent = link.parent if link else None
        except (ValueError, TypeError, AttributeError) as e:
            logger.warning("get_infraction_context: parent query failed: %s", e)
            parent = None

        infraction_count = BehaviorInfraction.objects.filter(student=student, school=school).count()

        return {
            "infraction": infraction,
            "school": school,
            "class_name": class_name,
            "student_grade": cg.get_grade_display() if cg else None,
            "student_section": cg.section if cg else None,
            "infraction_count": infraction_count,
            "academic_year": settings.CURRENT_ACADEMIC_YEAR,
            "generated_at": timezone.now(),
            "parent_name": parent.full_name if parent else None,
            "parent_id": parent.national_id if parent else None,
            "parent_phone": getattr(parent, "phone", None) if parent else None,
            "parent_email": parent.email if parent else None,
        }

    # ── إشعار أولياء الأمور عبر NotificationHub ────────────
    @staticmethod
    def notify_parents(
        infraction: BehaviorInfraction,
        school: School,
        reporter: CustomUser,
    ) -> None:
        """
        إشعار أولياء الأمور عبر NotificationHub المركزي.
        يُوزّع تلقائياً على: in_app + push + whatsapp + email + sms
        حسب درجة المخالفة وتفضيلات كل ولي أمر.
        """
        try:
            from notifications.hub import NotificationHub

            event_type = f"behavior_l{infraction.level}"  # behavior_l1 … behavior_l4
            title = (
                f"⚠️ مخالفة سلوكية — {infraction.student.full_name} "
                f"({LEVEL_DISPLAY.get(infraction.level, '')})"
            )
            body = (
                f"{LEVEL_DESC.get(infraction.level, '')}\n"
                f"التاريخ: {infraction.date.strftime('%Y/%m/%d') if infraction.date else ''} | "
                f"النقاط المخصومة: {infraction.points_deducted}"
            )

            NotificationHub.dispatch_to_parents(
                event_type=event_type,
                school=school,
                student=infraction.student,
                title=title,
                body=body,
                context={
                    "infraction": infraction,
                    "reporter": reporter,
                    "level": infraction.level,
                },
                related_object_id=infraction.pk,
                related_url=f"/behavior/student/{infraction.student.pk}/",
                sent_by=reporter,
            )
        except Exception as e:
            logger.error(
                "notify_parents: Hub dispatch failed [infraction=%s]: %s",
                infraction.pk,
                e,
                exc_info=True,
            )

    # ── تصعيد الإجراء التصاعدي ───────────────────────────────
    @staticmethod
    def escalate_infraction(
        infraction: BehaviorInfraction,
        escalated_by: CustomUser | None = None,
        notes: str = "",
    ) -> tuple:
        """
        ينقل المخالفة إلى الخطوة التصاعدية التالية.
        Returns: (success: bool, message: str)
        """
        current_step = infraction.escalation_step or 0
        steps = ESCALATION_STEPS.get(infraction.level, [])
        max_step = len(steps)

        if current_step >= max_step:
            return False, f"المخالفة وصلت الحد الأقصى (الخطوة {max_step})"

        new_step = current_step + 1
        infraction.escalation_step = new_step

        step_text = next((txt for s, txt in steps if s == new_step), "")
        action_line = f"[تصعيد → الخطوة {new_step}: {step_text}]"
        if notes:
            action_line += f" — {notes}"
        infraction.action_taken = (
            (infraction.action_taken or "") + "\n" + action_line
        ).strip()

        # تحديث الحقول المرتبطة تلقائياً
        if infraction.level >= 2 and new_step >= 2:
            infraction.parent_summoned = True
            if not infraction.parent_summon_date:
                infraction.parent_summon_date = timezone.now().date()

        infraction.save()

        # إشعار ولي الأمر عند التصعيد
        if infraction.level >= 2:
            BehaviorService._auto_summon_parent(
                infraction, escalated_by,
                f"تصعيد إجراء — الخطوة {new_step}: {step_text}",
            )

        return True, f"تم التصعيد إلى الخطوة {new_step}: {step_text}"

    # ── تسجيل إحالة أمنية (الدرجة الرابعة) ───────────────────
    @staticmethod
    def record_security_referral(
        infraction: BehaviorInfraction,
        agency: str,
        reference_number: str = "",
        notes: str = "",
        referred_by: CustomUser | None = None,
    ) -> tuple:
        """
        تسجيل إحالة أمنية لمخالفة من الدرجة الرابعة.
        Returns: (success: bool, message: str)
        """
        if infraction.level < 4:
            return False, "الإحالة الأمنية متاحة فقط لمخالفات الدرجة الرابعة"

        from .constants import SECURITY_AGENCIES
        valid_agencies = [code for code, _ in SECURITY_AGENCIES]
        if agency not in valid_agencies:
            return False, f"جهة أمنية غير معروفة: {agency}"

        infraction.security_referral_date = timezone.now().date()
        infraction.security_agency = agency
        if reference_number:
            infraction.security_reference_number = reference_number
        if notes:
            infraction.security_notes = (
                (infraction.security_notes or "") + "\n" + notes
            ).strip()

        agency_name = dict(SECURITY_AGENCIES).get(agency, agency)
        action_line = f"[إحالة أمنية → {agency_name}]"
        if reference_number:
            action_line += f" رقم المرجع: {reference_number}"
        infraction.action_taken = (
            (infraction.action_taken or "") + "\n" + action_line
        ).strip()

        infraction.save()

        # إشعار ولي الأمر
        BehaviorService._auto_summon_parent(
            infraction, referred_by,
            f"إحالة أمنية إلى {agency_name}",
        )

        return True, f"تم تسجيل الإحالة الأمنية إلى {agency_name}"

    # ── عدد المخالفات السابقة (لحساب خطوة التصعيد) ──────────
    @staticmethod
    def get_prior_infraction_count(
        student: CustomUser,
        school: School,
        level: int,
        violation_category=None,
    ) -> int:
        """عدد المخالفات السابقة من نفس الدرجة (أو نفس الفئة)."""
        qs = BehaviorInfraction.objects.filter(
            student=student, school=school, level=level,
        )
        if violation_category:
            qs = qs.filter(violation_category=violation_category)
        return qs.count()

    # ── اقتراح الخطوة التصاعدية للمخالفة الجديدة ────────────
    @staticmethod
    def suggest_escalation_step(
        student: CustomUser,
        school: School,
        level: int,
        violation_category=None,
    ) -> int:
        """يقترح خطوة التصعيد المناسبة بناءً على تكرار المخالفات."""
        prior = BehaviorService.get_prior_infraction_count(
            student, school, level, violation_category,
        )
        steps = ESCALATION_STEPS.get(level, [])
        max_step = len(steps)
        # المخالفة الأولى = الخطوة 1, الثانية = 2, ...
        return min(prior + 1, max_step)

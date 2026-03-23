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

import logging
from datetime import date

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

# ── نقاط مقترحة لكل درجة مخالفة ────────────────────────────
POINTS_BY_LEVEL = {1: 5, 2: 15, 3: 25, 4: 40}

LEVEL_DISPLAY = {
    1: "الدرجة الأولى (بسيطة)",
    2: "الدرجة الثانية (متوسطة)",
    3: "الدرجة الثالثة (جسيمة)",
    4: "الدرجة الرابعة (شديدة الخطورة)",
}

LEVEL_DESC = {
    1: "مخالفة بسيطة تستوجب التنبيه والتوجيه",
    2: "مخالفة متوسطة تستوجب التدخل والمتابعة",
    3: "مخالفة جسيمة أُحيلت للجنة الضبط السلوكي",
    4: "مخالفة شديدة الخطورة تستوجب التدخل الفوري",
}

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
        "specialist",
        "admin",
    }
    COMMITTEE_ROLES = {"principal", "vice_admin", "vice_academic", "specialist"}

    @staticmethod
    def can_report(user):
        return user.get_role() in BehaviorPermissions.REPORTER_ROLES

    @staticmethod
    def is_committee(user):
        return user.get_role() in BehaviorPermissions.COMMITTEE_ROLES or user.is_superuser


class BehaviorService:
    # ── حساب النقاط السلوكية للطالب ─────────────────────────
    @staticmethod
    def get_student_score(student, school=None, date_from=None, date_to=None):
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
    def get_dashboard_stats(school):
        """إحصائيات لوحة التحكم الرئيسية"""
        base = BehaviorInfraction.objects.filter(school=school)

        stats = base.values("level").annotate(count=Count("id"))

        total_deducted = base.aggregate(Sum("points_deducted"))["points_deducted__sum"] or 0

        total_restored = (
            BehaviorPointRecovery.objects.filter(infraction__school=school).aggregate(
                Sum("points_restored")
            )["points_restored__sum"]
            or 0
        )

        recent = base.select_related("student", "reported_by").order_by("-date")[:15]

        critical_unresolved = base.filter(level__in=[3, 4], is_resolved=False).select_related(
            "student"
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
    def get_student_profile(student):
        """بيانات الملف السلوكي الكامل"""
        infractions = (
            BehaviorInfraction.objects.filter(student=student)
            .select_related("reported_by", "recovery")
            .order_by("-date")
        )

        score = BehaviorService.get_student_score(student)
        status_color = (
            "green"
            if score["net_score"] >= 80
            else ("yellow" if score["net_score"] >= 60 else "red")
        )

        by_level = {1: 0, 2: 0, 3: 0, 4: 0}
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
    def get_committee_data(school):
        """بيانات لوحة لجنة الضبط السلوكي"""
        open_cases = (
            BehaviorInfraction.objects.filter(school=school, level__in=[3, 4], is_resolved=False)
            .select_related("student", "reported_by")
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
        infraction, decision, action="", restore_pts=0, reason="", approved_by=None
    ):
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
            return "⬆️ تم تصعيد المخالفة إلى الدرجة الرابعة", "warning"

        elif decision == "suspend":
            infraction.action_taken = (
                infraction.action_taken + "\n[قرار اللجنة: إيقاف مؤقت]"
            ).strip()
            infraction.save()
            return "📋 تم تسجيل قرار الإيقاف المؤقت", "info"

        return "لم يتم تحديد قرار", "error"

    # ── إحصائيات شاملة (تقرير المدير) ──────────────────────
    @staticmethod
    def get_statistics(school, date_from=None, date_to=None):
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
    def get_report_period(period, year=settings.CURRENT_ACADEMIC_YEAR):
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
    def get_student_report_data(student, school, period="full", year=settings.CURRENT_ACADEMIC_YEAR):
        """بيانات التقرير السلوكي الدوري الكامل"""
        date_from, date_to, period_label = BehaviorService.get_report_period(period, year)

        infractions = (
            BehaviorInfraction.objects.filter(
                student=student,
                school=school,
                date__gte=date_from,
                date__lte=date_to,
            )
            .select_related("reported_by", "recovery")
            .order_by("date")
        )

        score = BehaviorService.get_student_score(student, school, date_from, date_to)

        by_level = {1: [], 2: [], 3: [], 4: []}
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
    def get_infraction_context(infraction):
        """بيانات مشتركة لنماذج PDF/Word"""
        school = infraction.school
        student = infraction.student

        try:
            enrollment = (
                StudentEnrollment.objects.filter(
                    student=student, class_group__school=school, is_active=True
                )
                .select_related("class_group")
                .first()
            )
            class_name = enrollment.class_group.name if enrollment else None
        except Exception as e:
            logger.warning("get_infraction_context: enrollment query failed: %s", e)
            class_name = None

        try:
            link = (
                ParentStudentLink.objects.filter(student=student).select_related("parent").first()
            )
            parent = link.parent if link else None
        except Exception as e:
            logger.warning("get_infraction_context: parent query failed: %s", e)
            parent = None

        infraction_count = BehaviorInfraction.objects.filter(student=student, school=school).count()

        return {
            "infraction": infraction,
            "school": school,
            "class_name": class_name,
            "infraction_count": infraction_count,
            "academic_year": settings.CURRENT_ACADEMIC_YEAR,
            "generated_at": timezone.now(),
            "parent_name": parent.full_name if parent else None,
            "parent_id": parent.username if parent else None,
            "parent_phone": getattr(parent, "phone", None) if parent else None,
            "parent_email": parent.email if parent else None,
        }

    # ── إشعار أولياء الأمور عبر NotificationHub ────────────
    @staticmethod
    def notify_parents(infraction, school, reporter):
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

"""
quality/services.py
━━━━━━━━━━━━━━━━━━━
Business logic لوحدة الجودة والخطة التشغيلية

يشمل:
  - حساب نسب الإنجاز
  - إحصائيات لوحة التحكم
  - إدارة المنفذين والمجالات
  - بيانات تقرير التقدم
"""

from django.conf import settings

from django.db.models import Count, Prefetch

from .models import (
    ExecutorMapping,
    OperationalDomain,
    OperationalIndicator,
    OperationalProcedure,
    OperationalTarget,
    QualityCommitteeMember,
)


class QualityService:
    # ── مساعد داخلي ─────────────────────────────────────────
    @staticmethod
    def _calc_stats(qs):
        """حساب إحصائيات الإنجاز من queryset الإجراءات — Clean Code: DRY"""
        total = qs.count()
        completed = qs.filter(status="Completed").count()
        in_prog = qs.filter(status="In Progress").count()
        pending = qs.filter(status="Pending Review").count()
        pct = round(completed / total * 100) if total else 0
        return {
            "total": total,
            "completed": completed,
            "in_progress": in_prog,
            "pending": pending,
            "pct": pct,
        }

    # ── إحصائيات لوحة التحكم ────────────────────────────────
    @staticmethod
    def get_plan_stats(school, year=settings.CURRENT_ACADEMIC_YEAR):
        """إحصائيات الخطة التشغيلية"""
        base = OperationalProcedure.objects.filter(school=school, academic_year=year)
        stats = QualityService._calc_stats(base)
        # alias للتوافق مع القوالب القديمة
        stats["pending_review"] = stats.pop("pending")
        return stats

    # ── عدد المنفذين غير المربوطين ──────────────────────────
    @staticmethod
    def get_unmapped_count(school, year=settings.CURRENT_ACADEMIC_YEAR):
        """عدد المنفذين الذين ليس لهم مستخدم مربوط"""
        all_executors = set(
            OperationalProcedure.objects.filter(school=school, academic_year=year)
            .values_list("executor_norm", flat=True)
            .distinct()
        )
        mapped = set(
            ExecutorMapping.objects.filter(
                school=school, academic_year=year, user__isnull=False
            ).values_list("executor_norm", flat=True)
        )
        return len(all_executors - mapped)

    # ── إجراءاتي (للموظف غير الإداري) ──────────────────────
    @staticmethod
    def get_my_procedures(user, school, year=settings.CURRENT_ACADEMIC_YEAR):
        """الإجراءات المسندة للمستخدم الحالي"""
        return (
            OperationalProcedure.objects.filter(
                school=school, executor_user=user, academic_year=year
            )
            .select_related("indicator__target__domain")
            .order_by("status", "date_range")
        )

    # ── بيانات المجال التفصيلية مع فلترة ───────────────────
    @staticmethod
    def get_domain_procedures(school, domain, status_filter="", executor_filter=""):
        """إجراءات المجال مع إمكانية الفلترة"""
        proc_filters = {}
        if status_filter:
            proc_filters["status"] = status_filter
        if executor_filter:
            proc_filters["executor_norm__icontains"] = executor_filter

        indicators = OperationalIndicator.objects.prefetch_related(
            Prefetch(
                "procedures",
                queryset=OperationalProcedure.objects.filter(
                    school=school, **proc_filters
                ).select_related("executor_user"),
                to_attr="_filtered_procedures",
            )
        )

        targets = (
            OperationalTarget.objects.filter(domain=domain)
            .prefetch_related(Prefetch("indicators", queryset=indicators))
            .order_by("number")
        )

        domain_procs = OperationalProcedure.objects.filter(
            school=school, indicator__target__domain=domain
        )
        stats = QualityService._calc_stats(domain_procs)

        executors = (
            domain_procs.values("executor_norm")
            .annotate(count=Count("id"))
            .order_by("executor_norm")
        )

        return {
            "targets": targets,
            "executors": executors,
            **stats,
        }

    # ── تقرير التقدم ────────────────────────────────────────
    @staticmethod
    def get_progress_report_data(school, year=settings.CURRENT_ACADEMIC_YEAR):
        """بيانات تقرير التقدم الشامل"""
        domains = OperationalDomain.objects.filter(school=school, academic_year=year).order_by(
            "order"
        )

        domain_stats = []
        for domain in domains:
            procs = OperationalProcedure.objects.filter(
                school=school,
                academic_year=year,
                indicator__target__domain=domain,
            )
            stats = QualityService._calc_stats(procs)
            domain_stats.append({"domain": domain, **stats})

        return {
            "domain_stats": domain_stats,
            "overall": QualityService.get_plan_stats(school, year),
            "year": year,
        }

    # ── بيانات لجنة المنفذين ────────────────────────────────
    @staticmethod
    def get_executor_committee_data(school, year=settings.CURRENT_ACADEMIC_YEAR):
        """بيانات لجنة المنفذين مع إحصائيات كل عضو"""
        members = QualityCommitteeMember.objects.executor_committee(school, year)

        mapped_norms = set(
            ExecutorMapping.objects.filter(
                school=school, academic_year=year, user__isnull=False
            ).values_list("executor_norm", flat=True)
        )

        member_stats = []
        for member in members:
            if member.user:
                procs = OperationalProcedure.objects.filter(
                    school=school, executor_user=member.user, academic_year=year
                )
                stats = QualityService._calc_stats(procs)
                member_stats.append({"member": member, **stats})
            else:
                member_stats.append({
                    "member": member,
                    "total": 0,
                    "completed": 0,
                    "pending": 0,
                    "in_progress": 0,
                    "pct": 0,
                    "unmapped": True,
                })

        all_procs = OperationalProcedure.objects.filter(school=school, academic_year=year)
        all_norms = set(all_procs.values_list("executor_norm", flat=True).distinct())

        return {
            "member_stats": member_stats,
            "unmapped_norms": all_norms - mapped_norms,
            "overall": QualityService.get_plan_stats(school, year),
        }

    # ── تفاصيل إنجاز منفذ واحد ─────────────────────────────
    @staticmethod
    def get_executor_detail(member, school, year=settings.CURRENT_ACADEMIC_YEAR):
        """بيانات الإنجاز التفصيلية لمنفذ واحد"""
        procs = (
            OperationalProcedure.objects.filter(
                school=school, executor_user=member.user, academic_year=year
            )
            .select_related("indicator__target__domain")
            .order_by("status", "indicator__target__domain__order")
        )

        stats = QualityService._calc_stats(procs)

        by_domain = {}
        for proc in procs:
            domain_name = proc.indicator.target.domain.name
            if domain_name not in by_domain:
                by_domain[domain_name] = {"procs": [], "completed": 0, "total": 0}
            by_domain[domain_name]["procs"].append(proc)
            by_domain[domain_name]["total"] += 1
            if proc.status == "Completed":
                by_domain[domain_name]["completed"] += 1

        return {
            "procedures": procs,
            "by_domain": by_domain,
            **stats,
        }

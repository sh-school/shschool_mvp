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
from django.db.models import Count, Q, Prefetch

from .models import (
    OperationalDomain, OperationalTarget, OperationalIndicator,
    OperationalProcedure, ProcedureEvidence,
    QualityCommitteeMember, ExecutorMapping,
)


class QualityService:

    # ── إحصائيات لوحة التحكم ────────────────────────────────
    @staticmethod
    def get_plan_stats(school, year="2025-2026"):
        """إحصائيات الخطة التشغيلية"""
        base = OperationalProcedure.objects.filter(school=school, academic_year=year)
        total     = base.count()
        completed = base.filter(status="Completed").count()
        in_prog   = base.filter(status="In Progress").count()
        pending   = base.filter(status="Pending Review").count()
        pct       = round(completed / total * 100) if total else 0

        return {
            "total":          total,
            "completed":      completed,
            "in_progress":    in_prog,
            "pending_review": pending,
            "pct":            pct,
        }

    # ── عدد المنفذين غير المربوطين ──────────────────────────
    @staticmethod
    def get_unmapped_count(school, year="2025-2026"):
        """عدد المنفذين الذين ليس لهم مستخدم مربوط"""
        all_executors = set(
            OperationalProcedure.objects.filter(school=school, academic_year=year)
            .values_list("executor_norm", flat=True).distinct()
        )
        mapped = set(
            ExecutorMapping.objects.filter(
                school=school, academic_year=year, user__isnull=False
            ).values_list("executor_norm", flat=True)
        )
        return len(all_executors - mapped)

    # ── إجراءاتي (للموظف غير الإداري) ──────────────────────
    @staticmethod
    def get_my_procedures(user, school, year="2025-2026"):
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

        # إحصائيات المجال
        domain_procs = OperationalProcedure.objects.filter(
            school=school, indicator__target__domain=domain
        )
        total = domain_procs.count()
        completed = domain_procs.filter(status="Completed").count()
        pct = round(completed / total * 100) if total else 0

        # المنفذون الفريدون
        executors = (
            domain_procs.values("executor_norm")
            .annotate(count=Count("id"))
            .order_by("executor_norm")
        )

        return {
            "targets":   targets,
            "total":     total,
            "completed": completed,
            "pct":       pct,
            "executors": executors,
        }

    # ── تقرير التقدم ────────────────────────────────────────
    @staticmethod
    def get_progress_report_data(school, year="2025-2026"):
        """بيانات تقرير التقدم الشامل"""
        domains = OperationalDomain.objects.filter(
            school=school, academic_year=year
        ).order_by("order")

        domain_stats = []
        for domain in domains:
            procs = OperationalProcedure.objects.filter(
                school=school, academic_year=year,
                indicator__target__domain=domain,
            )
            total = procs.count()
            completed = procs.filter(status="Completed").count()
            in_prog = procs.filter(status="In Progress").count()
            pct = round(completed / total * 100) if total else 0

            domain_stats.append({
                "domain":    domain,
                "total":     total,
                "completed": completed,
                "in_prog":   in_prog,
                "pct":       pct,
            })

        overall = QualityService.get_plan_stats(school, year)

        return {
            "domain_stats": domain_stats,
            "overall":      overall,
            "year":         year,
        }

    # ── بيانات لجنة المنفذين ────────────────────────────────
    @staticmethod
    def get_executor_committee_data(school, year="2025-2026"):
        """بيانات لجنة المنفذين مع إحصائيات كل عضو"""
        members = QualityCommitteeMember.objects.executor_committee(school, year)

        mapped_norms = set(
            ExecutorMapping.objects.filter(school=school, academic_year=year, user__isnull=False)
            .values_list("executor_norm", flat=True)
        )

        member_stats = []
        for member in members:
            if member.user:
                procs = OperationalProcedure.objects.filter(
                    school=school, executor_user=member.user, academic_year=year
                )
                total     = procs.count()
                completed = procs.filter(status="Completed").count()
                pending   = procs.filter(status="Pending Review").count()
                in_prog   = procs.filter(status="In Progress").count()
                pct       = round(completed / total * 100) if total else 0
                member_stats.append({
                    "member": member, "total": total, "completed": completed,
                    "pending": pending, "in_prog": in_prog, "pct": pct,
                })
            else:
                member_stats.append({
                    "member": member, "total": 0, "completed": 0,
                    "pending": 0, "in_prog": 0, "pct": 0, "unmapped": True,
                })

        all_procs = OperationalProcedure.objects.filter(school=school, academic_year=year)
        all_norms = set(all_procs.values_list("executor_norm", flat=True).distinct())

        return {
            "member_stats":   member_stats,
            "unmapped_norms": all_norms - mapped_norms,
            "overall":        QualityService.get_plan_stats(school, year),
        }

    # ── تفاصيل إنجاز منفذ واحد ─────────────────────────────
    @staticmethod
    def get_executor_detail(member, school, year="2025-2026"):
        """بيانات الإنجاز التفصيلية لمنفذ واحد"""
        procs = (
            OperationalProcedure.objects.filter(
                school=school, executor_user=member.user, academic_year=year
            )
            .select_related("indicator__target__domain")
            .order_by("status", "indicator__target__domain__order")
        )

        total = procs.count()
        completed = procs.filter(status="Completed").count()
        in_prog = procs.filter(status="In Progress").count()
        pct = round(completed / total * 100) if total else 0

        # تجميع حسب المجال
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
            "total":      total,
            "completed":  completed,
            "in_progress": in_prog,
            "pct":        pct,
            "by_domain":  by_domain,
        }

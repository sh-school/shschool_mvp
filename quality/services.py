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

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.db.models import Count, Prefetch, QuerySet

if TYPE_CHECKING:
    from core.models import CustomUser, School

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
    def _calc_stats(qs: QuerySet) -> dict:
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
    def get_plan_stats(school: School, year: str = settings.CURRENT_ACADEMIC_YEAR) -> dict:
        """إحصائيات الخطة التشغيلية"""
        base = OperationalProcedure.objects.filter(school=school, academic_year=year)
        stats = QualityService._calc_stats(base)
        # alias للتوافق مع القوالب القديمة
        stats["pending_review"] = stats.pop("pending")
        return stats

    # ── عدد المنفذين غير المربوطين ──────────────────────────
    @staticmethod
    def get_unmapped_count(school: School, year: str = settings.CURRENT_ACADEMIC_YEAR) -> int:
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
    def get_my_procedures(
        user: CustomUser,
        school: School,
        year: str = settings.CURRENT_ACADEMIC_YEAR,
    ) -> QuerySet:
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
    def get_domain_procedures(
        school: School,
        domain: OperationalDomain,
        status_filter: str = "",
        executor_filter: str = "",
    ) -> dict:
        """إجراءات المجال مع إمكانية الفلترة"""
        proc_filters: dict = {}
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
    def get_progress_report_data(
        school: School, year: str = settings.CURRENT_ACADEMIC_YEAR
    ) -> dict:
        """بيانات تقرير التقدم الشامل"""
        domains = OperationalDomain.objects.filter(school=school, academic_year=year).order_by(
            "order"
        )

        # Bulk: count procedure statuses per domain in a single query
        from django.db.models import Q as _Q

        domain_proc_counts = (
            OperationalProcedure.objects.filter(school=school, academic_year=year)
            .values("indicator__target__domain_id")
            .annotate(
                total=Count("id"),
                completed=Count("id", filter=_Q(status="Completed")),
                in_progress=Count("id", filter=_Q(status="In Progress")),
                pending=Count("id", filter=_Q(status="Pending Review")),
            )
        )
        proc_map = {row["indicator__target__domain_id"]: row for row in domain_proc_counts}

        domain_stats: list = []
        for domain in domains:
            row = proc_map.get(domain.pk, {})
            total = row.get("total", 0)
            completed = row.get("completed", 0)
            pct = round(completed / total * 100) if total else 0
            domain_stats.append(
                {
                    "domain": domain,
                    "total": total,
                    "completed": completed,
                    "in_progress": row.get("in_progress", 0),
                    "pending": row.get("pending", 0),
                    "pct": pct,
                }
            )

        return {
            "domain_stats": domain_stats,
            "overall": QualityService.get_plan_stats(school, year),
            "year": year,
        }

    # ── بيانات لجنة المنفذين ────────────────────────────────
    @staticmethod
    def get_executor_committee_data(
        school: School, year: str = settings.CURRENT_ACADEMIC_YEAR
    ) -> dict:
        """بيانات لجنة المنفذين مع إحصائيات كل عضو"""
        members = QualityCommitteeMember.objects.executor_committee(school, year)

        mapped_norms = set(
            ExecutorMapping.objects.filter(
                school=school, academic_year=year, user__isnull=False
            ).values_list("executor_norm", flat=True)
        )

        # Bulk: count procedure statuses per executor_user in a single query
        from django.db.models import Q as _Q

        user_ids = [m.user_id for m in members if m.user_id]
        user_proc_counts = (
            OperationalProcedure.objects.filter(
                school=school, executor_user_id__in=user_ids, academic_year=year
            )
            .values("executor_user_id")
            .annotate(
                total=Count("id"),
                completed=Count("id", filter=_Q(status="Completed")),
                in_progress=Count("id", filter=_Q(status="In Progress")),
                pending=Count("id", filter=_Q(status="Pending Review")),
            )
        )
        user_proc_map = {row["executor_user_id"]: row for row in user_proc_counts}

        member_stats: list = []
        for member in members:
            if member.user:
                row = user_proc_map.get(member.user_id, {})
                total = row.get("total", 0)
                completed = row.get("completed", 0)
                pct = round(completed / total * 100) if total else 0
                member_stats.append(
                    {
                        "member": member,
                        "total": total,
                        "completed": completed,
                        "in_progress": row.get("in_progress", 0),
                        "pending": row.get("pending", 0),
                        "pct": pct,
                    }
                )
            else:
                member_stats.append(
                    {
                        "member": member,
                        "total": 0,
                        "completed": 0,
                        "pending": 0,
                        "in_progress": 0,
                        "pct": 0,
                        "unmapped": True,
                    }
                )

        all_procs = OperationalProcedure.objects.filter(school=school, academic_year=year)
        all_norms = set(all_procs.values_list("executor_norm", flat=True).distinct())

        return {
            "member_stats": member_stats,
            "unmapped_norms": all_norms - mapped_norms,
            "overall": QualityService.get_plan_stats(school, year),
        }

    # ── تفاصيل إنجاز منفذ واحد ─────────────────────────────
    @staticmethod
    def get_executor_detail(
        member: QualityCommitteeMember,
        school: School,
        year: str = settings.CURRENT_ACADEMIC_YEAR,
    ) -> dict:
        """بيانات الإنجاز التفصيلية لمنفذ واحد"""
        procs = (
            OperationalProcedure.objects.filter(
                school=school, executor_user=member.user, academic_year=year
            )
            .select_related("indicator__target__domain")
            .order_by("status", "indicator__target__domain__order")
        )

        stats = QualityService._calc_stats(procs)

        by_domain: dict = {}
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

    # ── رفع الدليل ──────────────────────────────────────────
    @staticmethod
    def upload_evidence(
        procedure: "OperationalProcedure",
        title: str,
        description: str = "",
        file=None,
        uploaded_by: "CustomUser | None" = None,
    ) -> "ProcedureEvidence":
        """
        إنشاء دليل جديد للإجراء.
        يجب التحقق من نوع الملف في الـ view قبل استدعاء هذه الدالة.
        """
        from .models import ProcedureEvidence

        return ProcedureEvidence.objects.create(
            procedure=procedure,
            title=title,
            description=description,
            file=file,
            uploaded_by=uploaded_by,
        )

    # ── تحديث حالة الإجراء + تسجيل التغيير ─────────────────
    @staticmethod
    def update_procedure_status(
        procedure: "OperationalProcedure",
        *,
        status: str,
        evidence_type: str = "",
        evidence_source_file=None,
        comments: str = "",
        follow_up: str = "",
        changed_by: "CustomUser",
        file=None,
        file_title: str = "",
    ) -> None:
        """
        تحديث الإجراء + تسجيل log التغيير + رفع دليل اختياري.
        يُستدعى من view task_update_modal.
        """
        from .models import ProcedureEvidence, ProcedureStatusLog

        old_status = procedure.status
        if status and status in dict(OperationalProcedure.STATUS):
            procedure.status = status
        if evidence_type in dict(OperationalProcedure.EVIDENCE_TYPE):
            procedure.evidence_type = evidence_type
        if evidence_source_file:
            procedure.evidence_source_file = evidence_source_file
        procedure.comments = comments
        if follow_up in dict(OperationalProcedure.FOLLOW_UP_CHOICES):
            procedure.follow_up = follow_up

        procedure.save(update_fields=[
            "status", "evidence_type", "evidence_source_file",
            "comments", "follow_up", "updated_at",
        ])

        if file:
            ProcedureEvidence.objects.create(
                procedure=procedure,
                title=file_title or file.name,
                file=file,
                uploaded_by=changed_by,
            )

        if old_status != procedure.status:
            ProcedureStatusLog.objects.create(
                procedure=procedure,
                old_status=old_status,
                new_status=procedure.status,
                changed_by=changed_by,
                note=comments,
            )

    # ── تقييم المراجعة + تسجيل التغيير ─────────────────────
    @staticmethod
    def review_evaluate(
        procedure: "OperationalProcedure",
        *,
        evidence_request_status: str = "",
        evidence_request_note: str = "",
        quality_rating: str = "",
        new_status: str = "",
        review_note: str = "",
        reviewed_by: "CustomUser",
    ) -> None:
        """
        حفظ تقييم المراجعة + تسجيل log التغيير.
        يُستدعى من view review_evaluate_modal.
        """
        from django.utils import timezone as _tz

        from .models import ProcedureStatusLog

        old_status = procedure.status

        if evidence_request_status in dict(OperationalProcedure.EVIDENCE_REQUEST_STATUS):
            procedure.evidence_request_status = evidence_request_status
        procedure.evidence_request_note = evidence_request_note

        if quality_rating in dict(OperationalProcedure.QUALITY_RATING) or quality_rating == "":
            procedure.quality_rating = quality_rating

        if new_status and new_status in dict(OperationalProcedure.STATUS):
            procedure.status = new_status

        procedure.review_note = review_note
        procedure.reviewed_by = reviewed_by
        procedure.reviewed_at = _tz.now()

        procedure.save(update_fields=[
            "evidence_request_status", "evidence_request_note", "quality_rating",
            "status", "review_note", "reviewed_by", "reviewed_at", "updated_at",
        ])

        if old_status != procedure.status:
            ProcedureStatusLog.objects.create(
                procedure=procedure,
                old_status=old_status,
                new_status=procedure.status,
                changed_by=reviewed_by,
                note=review_note,
            )

from django.contrib import admin
from .models import (
    OperationalDomain, OperationalTarget, OperationalIndicator,
    OperationalProcedure, ProcedureEvidence, QualityCommitteeMember,
    ExecutorMapping,
)


class TargetInline(admin.TabularInline):
    model  = OperationalTarget
    extra  = 0
    fields = ("number", "text")


@admin.register(OperationalDomain)
class DomainAdmin(admin.ModelAdmin):
    list_display  = ("name", "school", "academic_year", "total_procedures", "completion_pct")
    list_filter   = ("school", "academic_year")
    search_fields = ("name",)
    inlines       = [TargetInline]


class IndicatorInline(admin.TabularInline):
    model  = OperationalIndicator
    extra  = 0
    fields = ("number", "text")


@admin.register(OperationalTarget)
class TargetAdmin(admin.ModelAdmin):
    list_display  = ("number", "text", "domain")
    list_filter   = ("domain__school", "domain")
    search_fields = ("number", "text")
    inlines       = [IndicatorInline]


class ProcedureInline(admin.TabularInline):
    model  = OperationalProcedure
    extra  = 0
    fields = ("number", "executor_norm", "status", "date_range")


@admin.register(OperationalIndicator)
class IndicatorAdmin(admin.ModelAdmin):
    list_display  = ("number", "text", "target")
    list_filter   = ("target__domain__school",)
    search_fields = ("number", "text")
    inlines       = [ProcedureInline]


class EvidenceInline(admin.TabularInline):
    model  = ProcedureEvidence
    extra  = 0
    fields = ("title", "description", "file", "uploaded_by")


@admin.register(OperationalProcedure)
class ProcedureAdmin(admin.ModelAdmin):
    list_display  = ("number", "executor_norm", "status", "date_range", "evidence_type")
    list_filter   = ("school", "status", "evidence_type", "academic_year")
    search_fields = ("number", "text", "executor_norm")
    raw_id_fields = ("executor_user",)
    inlines       = [EvidenceInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("indicator__target__domain")


@admin.register(QualityCommitteeMember)
class QualityCommitteeMemberAdmin(admin.ModelAdmin):
    list_display  = ("job_title", "user", "responsibility", "committee_type", "domain", "academic_year", "is_active")
    list_filter   = ("school", "responsibility", "committee_type", "academic_year", "is_active")
    search_fields = ("job_title", "user__full_name")
    raw_id_fields = ("user",)


@admin.register(ExecutorMapping)
class ExecutorMappingAdmin(admin.ModelAdmin):
    list_display  = ("executor_norm", "user", "school", "academic_year")
    list_filter   = ("school", "academic_year")
    search_fields = ("executor_norm", "user__full_name")
    raw_id_fields = ("user",)
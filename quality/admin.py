import logging

from django.conf import settings
from django.contrib import admin

logger = logging.getLogger(__name__)

from .models import (
    ExecutorMapping,
    OperationalDomain,
    OperationalIndicator,
    OperationalProcedure,
    OperationalTarget,
    ProcedureEvidence,
    QualityCommitteeMember,
)


class TargetInline(admin.TabularInline):
    model = OperationalTarget
    extra = 0
    fields = ("number", "text")


@admin.register(OperationalDomain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "academic_year", "total_procedures", "completion_pct")
    list_filter = ("school", "academic_year")
    search_fields = ("name",)
    inlines = [TargetInline]


class IndicatorInline(admin.TabularInline):
    model = OperationalIndicator
    extra = 0
    fields = ("number", "text")


@admin.register(OperationalTarget)
class TargetAdmin(admin.ModelAdmin):
    list_display = ("number", "text", "domain")
    list_filter = ("domain__school", "domain")
    search_fields = ("number", "text")
    autocomplete_fields = ("domain",)
    inlines = [IndicatorInline]


class ProcedureInline(admin.TabularInline):
    model = OperationalProcedure
    extra = 0
    fields = ("number", "executor_norm", "status", "date_range")


@admin.register(OperationalIndicator)
class IndicatorAdmin(admin.ModelAdmin):
    list_display = ("number", "text", "target")
    list_filter = ("target__domain__school",)
    search_fields = ("number", "text")
    autocomplete_fields = ("target",)
    inlines = [ProcedureInline]


class EvidenceInline(admin.TabularInline):
    model = ProcedureEvidence
    extra = 0
    fields = ("title", "description", "file", "uploaded_by")


@admin.register(OperationalProcedure)
class ProcedureAdmin(admin.ModelAdmin):
    list_display = ("number", "executor_norm", "status", "date_range", "evidence_type")
    list_filter = ("school", "status", "evidence_type", "academic_year")
    search_fields = ("number", "text", "executor_norm")
    autocomplete_fields = ("executor_user", "indicator", "reviewed_by")
    inlines = [EvidenceInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("indicator__target__domain")


@admin.register(QualityCommitteeMember)
class QualityCommitteeMemberAdmin(admin.ModelAdmin):
    list_display = (
        "job_title",
        "user",
        "responsibility",
        "committee_type",
        "domain",
        "academic_year",
        "is_active",
    )
    list_filter = ("school", "responsibility", "committee_type", "academic_year", "is_active")
    search_fields = ("job_title", "user__full_name")
    autocomplete_fields = ["user", "domain"]


from django import forms as _forms
from django.http import JsonResponse as _JsonResponse
from django.urls import path as _path


class ExecutorMappingAdminForm(_forms.ModelForm):
    """
    نموذج مخصص لـ ExecutorMapping:
    - executor_norm: قائمة منسدلة تُحمَّل من OperationalProcedure الفعلية
    - user: يُعالَج عبر autocomplete_fields
    """

    class Meta:
        model = ExecutorMapping
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        school = None
        year = settings.CURRENT_ACADEMIC_YEAR

        if self.instance and self.instance.pk:
            try:
                school = self.instance.school
                year = self.instance.academic_year
            except (AttributeError, ValueError) as e:
                logger.warning(
                    "فشل قراءة المدرسة والسنة الدراسية من النموذج في لوحة الإدارة: %s", e
                )
                school = None
        if not school and self.data.get("school"):
            from core.models import School as _S

            try:
                school = _S.objects.get(pk=self.data["school"])
            except _S.DoesNotExist:
                pass
            year = self.data.get("academic_year", year)

        if school:
            norms = (
                OperationalProcedure.objects.filter(school=school, academic_year=year)
                .values_list("executor_norm", flat=True)
                .distinct()
                .order_by("executor_norm")
            )
            choices = [("", "— اختر المسمى الوظيفي —")] + [(n, n) for n in norms if n]
        else:
            choices = [("", "— اختر المدرسة أولاً ثم ستظهر الخيارات —")]

        self.fields["executor_norm"] = _forms.ChoiceField(
            choices=choices,
            label="المسمى الوظيفي (من الخطة التشغيلية)",
        )


@admin.register(ExecutorMapping)
class ExecutorMappingAdmin(admin.ModelAdmin):
    form = ExecutorMappingAdminForm
    autocomplete_fields = ["user"]
    change_form_template = "admin/quality/executormapping/change_form.html"

    list_display = ("executor_norm", "mapped_user", "procedures_count", "school", "academic_year")
    list_filter = ("school", "academic_year")
    search_fields = ("executor_norm", "user__full_name", "user__national_id")
    ordering = ("school", "academic_year", "executor_norm")

    @admin.display(description="عدد الإجراءات")
    def procedures_count(self, obj):
        return OperationalProcedure.objects.filter(
            school=obj.school,
            academic_year=obj.academic_year,
            executor_norm=obj.executor_norm,
        ).count()

    @admin.display(description="الموظف المرتبط")
    def mapped_user(self, obj):
        if obj.user:
            return f"✅ {obj.user.full_name}"
        return "⚠️ غير مربوط"

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            _path(
                "norms/", self.admin_site.admin_view(self.norms_ajax), name="executormapping_norms"
            ),
        ]
        return custom + urls

    def norms_ajax(self, request):
        """AJAX: إرجاع قائمة executor_norm لمدرسة وسنة محددتين"""
        school_id = request.GET.get("school")
        year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)
        norms = []
        if school_id:
            norms = list(
                OperationalProcedure.objects.filter(school_id=school_id, academic_year=year)
                .values_list("executor_norm", flat=True)
                .distinct()
                .order_by("executor_norm")
            )
        return _JsonResponse({"norms": [n for n in norms if n]})

    class Media:
        css = {"all": ("https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/css/select2.min.css",)}
        js = (
            "https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js",
            "https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/i18n/ar.js",
        )

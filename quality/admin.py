import logging

from django.contrib import admin

from core.academic_calendar import academic_year_for, default_academic_year
from core.models import AuditLog

logger = logging.getLogger(__name__)

from .models import (
    EmployeeEvaluation,
    EvaluationAxis,
    EvaluationCycle,
    EvaluationLevelBackup,
    EvaluationScore,
    ExecutorMapping,
    OperationalDomain,
    OperationalIndicator,
    OperationalProcedure,
    OperationalTarget,
    ProcedureEvidence,
    QualityCommitteeMember,
    RoleEvaluationTemplate,
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
        # نموذج إدارةٍ بلا `request` — وأمان الصفوف يقيّد الاشتقاق بمدرسة الجلسة.
        year = default_academic_year()

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
        year = request.GET.get("year") or academic_year_for(request)
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


# ── Phase 6: تقييم الموظفين (New Models) ──────────────────────────


def _template_has_evaluations(template) -> bool:
    """قالبٌ عليه تقييماتٌ مقفل — كما يقفله `appraisal_seed.apply_plan`."""
    return template is not None and template.pk is not None and template.evaluations.exists()


class EvaluationAxisInline(admin.TabularInline):
    """
    للقراءة: المحاورُ منسوخةٌ من الاستمارة الوزاريّة بأمر البذر وحده (`appraisal_seed`)، وهو
    الذي يصحّح ما انحرف ويُقفل قالباً عليه تقييمات. وكانت اللوحةُ تغيّر وزناً أو مفتاحاً في
    قالبٍ بلا تقييمات، فتُعتمد تقاريرُ على غير أوزان الاستمارة (المادة 15،
    02_staff_affairs.md:199: «وفقاً للنماذج المعتمدة من الوزير»).
    """

    model = EvaluationAxis
    extra = 0
    fields = ("key", "label", "weight", "order")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RoleEvaluationTemplate)
class RoleEvaluationTemplateAdmin(admin.ModelAdmin):
    """
    للقراءة: القالبُ استمارةُ دورٍ منسوخةٌ بأمر البذر (`seed_quality_templates --apply`). كانت
    اللوحةُ تضيف قالباً لدورٍ لا استمارةَ له (ADR-0002 §6.6 بند 12)، وتنقل قالباً عليه تقييماتٌ
    إلى دورٍ أو عامٍ آخر. ويبقى حذفُ قالبٍ لا تقييماتَ عليه.
    """

    list_display = ("role_name", "school", "academic_year", "is_active", "total_weight")
    list_filter = ("school", "academic_year", "is_active")
    search_fields = ("role_name",)
    inlines = [EvaluationAxisInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # حذفُه كان يُفرغ `EmployeeEvaluation.template` فيُحسب المجموعُ من المحاور الافتراضيّة
        # الصفريّة. والنموذجُ يمنعه أيضاً (`on_delete=RESTRICT`).
        if obj is None:
            # قائمةُ التغيير بلا كائن: إجراءُ «حذف المحدَّد» كان يظهر ثمّ يسقط بـRestrictedError.
            return False
        return not _template_has_evaluations(obj) and super().has_delete_permission(request, obj)


class EvaluationScoreInline(admin.TabularInline):
    """للقراءة: درجاتُ المقيِّمين تُكتب من شاشة التقييم وحدها (`save_evaluation`)."""

    model = EvaluationScore
    extra = 0
    can_delete = False
    fields = (
        "evaluator",
        "weight",
        "axis_professional",
        "axis_commitment",
        "axis_teamwork",
        "axis_development",
        "custom_axes",
        "total_score",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(EmployeeEvaluation)
class EmployeeEvaluationAdmin(admin.ModelAdmin):
    """
    للقراءة في الدرجات والمستوى والحالة. كانت اللوحةُ تكتب التقييمَ دون `save_evaluation`:
    تتجاوز قيودَ المواد 17–19، وكان `save()` يعيد حسابَ مجموع تقييمات القالب الوزاريّ من
    المحاور الافتراضيّة الصفريّة فيصفّرها — وهي كانت السبيلَ الوحيد إلى «مُعتمد». فالكتابةُ
    من شاشة التقييم، والاعتمادُ للمدير من زرّه هناك (`approve_evaluation`)؛ ويبقى هنا
    تصحيحُ النصوص وحدها.
    """

    list_display = (
        "employee",
        "evaluator",
        "period",
        "total_score",
        "rating",
        "status",
        "academic_year",
    )
    list_filter = ("school", "academic_year", "period", "status", "rating")
    search_fields = ("employee__full_name", "evaluator__full_name")
    readonly_fields = (
        "school",
        "employee",
        "evaluator",
        "template",
        "academic_year",
        "period",
        "status",
        "axis_professional",
        "axis_commitment",
        "axis_teamwork",
        "axis_development",
        "total_score",
        "rating",
        "acknowledged_at",
        # يُكتبان من الشاشة بسجلّ تدقيق: الاعتمادُ (`approve_evaluation`) وتاريخُ الاستلام
        # عند رفض التوقيع (`record_receipt_on_refusal`).
        "approved_at",
        "received_on",
    )
    inlines = [EvaluationScoreInline]

    #: نصوصُ الواضع: تُصحَّح هنا ما دام التقريرُ لم يُعتمد.
    _EVALUATOR_TEXTS = ("strengths", "improvements", "goals_next")

    def has_add_permission(self, request):
        return False

    def get_readonly_fields(self, request, obj=None):
        """
        تعليقُ الموظّف كلامُه — يكتبه مسارُ الإقرار وحده (`EmployeeEvaluation.acknowledge`). ونصوصُ الواضع تُقفل
        باعتماد المدير: النسخةُ المعتمَدةُ (المادة 16، 02_staff_affairs.md:200) هي التي أُعلن بها
        الموظّفُ وعليها يتظلّم خلال خمسة عشر يوماً (المادة 20، صفحة الملفّ 12)، ومسارُ الشاشة
        يرفض أيَّ تعديلٍ بعدها (`save_evaluation`). وتواريخُ التظلّم تبقى للّوحة.
        """
        fields = [*self.readonly_fields, "employee_comment"]
        if obj is not None and obj.status in ("approved", "acknowledged"):
            fields.extend(self._EVALUATOR_TEXTS)
        return fields

    def save_model(self, request, obj, form, change):
        # الحقولُ القابلةُ للتحرير نصوصٌ وتواريخُ وحدها، فتُكتب وحدها: لا يُعاد حسابُ المجموع.
        # والقفلُ من الحالة المحفوظة لا من نسخة النموذج، وكلُّ تغييرٍ بسطرٍ في سجلّ التدقيق كما
        # في مسارات الشاشة.
        stored = type(obj).objects.get(pk=obj.pk)
        readonly = set(self.get_readonly_fields(request, stored))
        changed = [f for f in form.changed_data if f not in readonly]
        if not changed:
            return
        obj.save(update_fields=[*changed, "updated_at"])
        AuditLog.log(
            user=request.user,
            action="update",
            model_name="other",
            object_id=obj.pk,
            object_repr=str(obj),
            school=obj.school,
            request=request,
            changes={
                f: [_audit_value(getattr(stored, f)), _audit_value(getattr(obj, f))]
                for f in changed
            },
        )


def _audit_value(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


@admin.register(EvaluationLevelBackup)
class EvaluationLevelBackupAdmin(admin.ModelAdmin):
    """سجلُّ ما غيّرته الهجرة 0018 — للقراءة: لا إضافةَ ولا تعديلَ ولا حذف."""

    list_display = (
        "evaluation",
        "old_total_score",
        "old_rating",
        "new_total_score",
        "new_rating",
        "created_at",
    )
    list_select_related = ("evaluation__employee",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EvaluationCycle)
class EvaluationCycleAdmin(admin.ModelAdmin):
    list_display = ("school", "period", "academic_year", "deadline", "is_closed")
    list_filter = ("school", "academic_year", "period", "is_closed")


# ══ الإشراف على أداء المعلّم — الملاحظة الصفّية ══════════════════════
# الوحدة كاملةٌ ومنشورةٌ على الإنتاج، وكانت غائبةً عن لوحة الإدارة وحدَها:
# فلا سبيلَ لقيادة المدرسة أن تفتّش زيارةً، أو تُصلح معياراً مزروعاً خطأً،
# أو ترى المؤرشَف. وثلاثةُ قيودٍ تحكم هذا التسجيل:
#
#   ١ المؤرشَف يُرى: المديرُ الافتراضيّ يستبعد المحذوفَ ناعماً، فالقائمة
#     تُبنى من `all_objects` وإلّا بقي الأرشيف محجوباً هنا أيضاً.
#   ٢ لا حذفَ من هنا: زرُّ الحذف مُغلق، ومكانَه إجراءا «أرشفة/استرجاع»
#     يمرّان بـ`ObservationService` فيُختمان بـ`updated_by`. وحذفُ Django
#     الجماعيّ يستدعي `queryset.delete()` بلا ختمٍ ولا سبب.
#   ٣ النسبة مشتقّة: أيُّ تعديلِ تقييمٍ من هنا يُعيد حسابها فوراً، وإلّا
#     صارت الترويسة تقول رقماً لا يطابق تقييماتِها.

from .models import ClassroomObservation, ObservationCriterion, ObservationScore  # noqa: E402
from .observation_services import ObservationService  # noqa: E402


@admin.register(ObservationCriterion)
class ObservationCriterionAdmin(admin.ModelAdmin):
    """المعايير الـ23 المزروعة لكلّ مدرسة — تُصحَّح من هنا حين يُزرع أحدُها خطأً."""

    list_display = ("order", "domain", "text", "is_active", "school")
    list_filter = ("school", "domain", "is_active")
    list_editable = ("is_active",)
    search_fields = ("text",)
    ordering = ("school", "order")
    list_select_related = ("school",)


class ObservationScoreInline(admin.TabularInline):
    model = ObservationScore
    extra = 0
    fields = ("criterion", "rating", "recommendation")
    autocomplete_fields = ("criterion",)
    ordering = ("criterion__order",)


@admin.register(ClassroomObservation)
class ClassroomObservationAdmin(admin.ModelAdmin):
    list_display = (
        "observation_date",
        "teacher",
        "observer",
        "kind",
        "status",
        "score_percent",
        "is_deleted",
        "school",
    )
    list_filter = ("school", "kind", "status", "is_deleted", "observation_date")
    search_fields = ("teacher__full_name", "observer__full_name", "topic")
    date_hierarchy = "observation_date"
    autocomplete_fields = ("teacher", "observer", "subject", "class_group")
    list_select_related = ("teacher", "observer", "school")
    inlines = [ObservationScoreInline]
    actions = ("archive_selected", "restore_selected")
    ordering = ("-observation_date", "-created_at")

    # مشتقٌّ أو مملوكٌ لسير الحالة — يُقرأ هنا ولا يُكتب.
    readonly_fields = (
        "id",
        "score_percent",
        "submitted_at",
        "teacher_acknowledged_at",
        "submission_count",
        "is_deleted",
        "deleted_at",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    )

    def get_queryset(self, request):
        """`all_objects` — وإلّا اختفى المؤرشَف من لوحة الإدارة كما اختفى من الواجهة."""
        return ClassroomObservation.all_objects.get_queryset().select_related(
            "teacher", "observer", "school", "subject", "class_group"
        )

    def has_delete_permission(self, request, obj=None):
        """لا حذفَ من لوحة الإدارة — الأرشفةُ إجراءٌ صريحٌ يمرّ بالخدمة."""
        return False

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        ObservationService.recompute_score_percent(form.instance)

    @admin.action(description="أرشفة المحدَّد (حذفٌ ناعمٌ قابلٌ للاسترجاع)")
    def archive_selected(self, request, queryset):
        count = 0
        for observation in queryset.filter(is_deleted=False):
            ObservationService.archive(observation, request.user)
            count += 1
        self.message_user(request, f"أُرشفت {count} زيارة — والتقييماتُ محفوظة.")

    @admin.action(description="استرجاع المؤرشَف")
    def restore_selected(self, request, queryset):
        count = 0
        for observation in queryset.filter(is_deleted=True):
            ObservationService.restore(observation, request.user)
            count += 1
        self.message_user(request, f"استُرجعت {count} زيارة.")


@admin.register(ObservationScore)
class ObservationScoreAdmin(admin.ModelAdmin):
    list_display = ("observation", "criterion", "rating", "recommendation")
    list_filter = ("rating", "criterion__domain", "observation__school")
    search_fields = ("criterion__text", "recommendation", "observation__teacher__full_name")
    autocomplete_fields = ("observation", "criterion")
    ordering = ("observation", "criterion__order")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("observation__teacher", "observation__school", "criterion")
        )

    # ── كلُّ مسٍّ للتقييم يُعيد اشتقاقَ نسبة الترويسة ──
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        ObservationService.recompute_score_percent(obj.observation)

    def delete_model(self, request, obj):
        observation = obj.observation
        super().delete_model(request, obj)
        ObservationService.recompute_score_percent(observation)

    def delete_queryset(self, request, queryset):
        observations = list(
            ClassroomObservation.all_objects.filter(
                id__in=queryset.values_list("observation_id", flat=True)
            )
        )
        super().delete_queryset(request, queryset)
        for observation in observations:
            ObservationService.recompute_score_percent(observation)

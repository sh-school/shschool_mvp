from django.contrib import admin, messages

from .models import (
    AbsenceAlert,
    ScheduleBaseline,
    ScheduleConstraintOverride,
    ScheduleGeneration,
    ScheduleSlot,
    SchedulingResource,
    Session,
    StudentAttendance,
    Subject,
    SubjectClassAssignment,
    SubstituteAssignment,
    TeacherAbsence,
    TeacherPreference,
    TimeSlotConfig,
)

# ── Phase 1 ──────────────────────────────────


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name_ar", "code", "pedagogy", "school")
    list_editable = ("pedagogy",)
    list_filter = ("pedagogy", "school")
    search_fields = ("name_ar", "code")


class AttendanceInline(admin.TabularInline):
    model = StudentAttendance
    extra = 0
    fields = ("student", "status", "excuse_type", "marked_by", "marked_at")
    readonly_fields = ("marked_at",)
    autocomplete_fields = ("student", "marked_by")


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("class_group", "subject", "teacher", "date", "start_time", "status")
    list_filter = ("school", "status", "date")
    search_fields = ("teacher__full_name", "class_group__section")
    autocomplete_fields = ("teacher", "class_group", "subject")
    date_hierarchy = "date"
    inlines = [AttendanceInline]


@admin.register(StudentAttendance)
class StudentAttendanceAdmin(admin.ModelAdmin):
    list_display = ("student", "session", "status", "marked_by", "marked_at")
    list_filter = ("status", "school")
    search_fields = ("student__full_name", "student__national_id")
    autocomplete_fields = ("student", "marked_by", "session")
    date_hierarchy = "marked_at"


@admin.register(AbsenceAlert)
class AbsenceAlertAdmin(admin.ModelAdmin):
    list_display = ("student", "absence_count", "status", "created_at")
    list_filter = ("status", "school")
    autocomplete_fields = ("student", "resolved_by")


# ── Phase 2 ──────────────────────────────────


@admin.register(ScheduleSlot)
class ScheduleSlotAdmin(admin.ModelAdmin):
    list_display = (
        "day_of_week",
        "period_number",
        "teacher",
        "class_group",
        "subject",
        "start_time",
        "end_time",
        "is_active",
    )
    list_filter = ("school", "day_of_week", "is_active", "academic_year")
    search_fields = ("teacher__full_name", "class_group__section", "subject__name_ar")
    autocomplete_fields = ("teacher", "class_group", "subject")
    ordering = ("day_of_week", "period_number")


@admin.register(TeacherAbsence)
class TeacherAbsenceAdmin(admin.ModelAdmin):
    list_display = ("teacher", "date", "reason", "status", "reported_by", "created_at")
    list_filter = ("school", "status", "reason", "date")
    search_fields = ("teacher__full_name",)
    autocomplete_fields = ("teacher", "reported_by")
    ordering = ("-date",)


@admin.register(SubstituteAssignment)
class SubstituteAssignmentAdmin(admin.ModelAdmin):
    list_display = ("absence", "slot", "substitute", "status", "assigned_by", "created_at")
    list_filter = ("school", "status")
    search_fields = ("substitute__full_name", "absence__teacher__full_name")
    autocomplete_fields = ("substitute", "assigned_by", "absence", "slot")
    ordering = ("-created_at",)


# ── Phase 3 — الجدولة الذكية ──────────────


@admin.register(TimeSlotConfig)
class TimeSlotConfigAdmin(admin.ModelAdmin):
    list_display = (
        "band",
        "day_type",
        "period_number",
        "start_time",
        "end_time",
        "is_break",
        "break_label",
    )
    list_filter = ("school", "band", "day_type", "is_break")
    list_select_related = ("band",)
    ordering = ("band__order", "day_type", "period_number")


@admin.register(SubjectClassAssignment)
class SubjectClassAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "subject",
        "class_group",
        "teacher",
        "weekly_periods",
        "requires_lab",
        "double_period",
        "is_active",
    )
    list_filter = (
        "school",
        "academic_year",
        "subject",
        "requires_lab",
        "double_period",
        "is_active",
    )
    search_fields = ("teacher__full_name", "subject__name_ar", "class_group__section")
    autocomplete_fields = ("teacher", "class_group", "subject")
    list_editable = ("weekly_periods", "requires_lab", "double_period", "is_active")
    list_per_page = 50


@admin.register(SchedulingResource)
class SchedulingResourceAdmin(admin.ModelAdmin):
    """المكانُ المحدود: معملان وملعبان — والسعةُ كم حصّةً تقع فيه معاً.

    ويُدار من هنا لا من سطر أوامر: عددُ المعامل شأنُ المدرسة، يتبدّل ببناءٍ
    جديدٍ أو معملٍ يُغلق، فلا يُحبس في ترحيلٍ يحتاج مبرمجاً.
    """

    list_display = ("name", "capacity", "same_level_only", "subject_names", "is_active")
    list_filter = ("school", "is_active", "same_level_only")
    search_fields = ("name", "note")
    filter_horizontal = ("subjects",)
    list_editable = ("capacity", "same_level_only", "is_active")

    @admin.display(description="المواد التي تستعمله")
    def subject_names(self, obj):
        return "، ".join(subject.name_ar for subject in obj.subjects.all()) or "—"

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("subjects")


@admin.register(ScheduleConstraintOverride)
class ScheduleConstraintOverrideAdmin(admin.ModelAdmin):
    """استثناءاتُ قيود الجدول — والصفوفُ هنا انحرافٌ عن الشيفرة لا سجلٌّ لها.

    فجدولٌ فارغٌ يعني «افتراضُ الكود بالضبط»، ولا يُنشأ صفٌّ إلّا حين تقرّر
    الإدارةُ خلافَه. ورمزُ القيد يُختار من السجلّ لا يُكتب: رمزٌ لا تعرفه
    الشيفرةُ صفٌّ ميّتٌ يوهم صاحبَه أنّه غيّر شيئاً.
    """

    list_display = ("code", "constraint_title", "break_at", "weight", "academic_year", "updated_by")
    list_filter = ("school", "academic_year", "break_at")
    search_fields = ("code", "reason")
    readonly_fields = ("updated_at",)

    @admin.display(description="القيد")
    def constraint_title(self, obj):
        from .constraint_registry import spec

        found = spec(obj.code)
        return found.title if found else "— رمزٌ لا يعرفه السجلّ —"

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        from .constraint_registry import BREAK_CHOICES

        if db_field.name == "break_at":
            kwargs["choices"] = [("", "افتراضُ الكود"), *BREAK_CHOICES]
        return super().formfield_for_choice_field(db_field, request, **kwargs)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """رمزُ القيد قائمةٌ من السجلّ — وما ليس فيه لا يُكتب."""
        from django import forms

        from .constraint_registry import REGISTRY, TUNABLE_CODES

        if db_field.name == "code":
            choices = [(code, f"{code} · {REGISTRY[code].title}") for code in sorted(TUNABLE_CODES)]
            return forms.ChoiceField(choices=choices, label=db_field.verbose_name)
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(TeacherPreference)
class TeacherPreferenceAdmin(admin.ModelAdmin):
    list_display = (
        "teacher",
        "max_daily_periods",
        "max_consecutive",
        "max_gap",
        "free_day",
        "academic_year",
    )
    list_filter = ("school", "academic_year", "free_day")
    search_fields = ("teacher__full_name",)
    autocomplete_fields = ("teacher",)


@admin.register(ScheduleGeneration)
class ScheduleGenerationAdmin(admin.ModelAdmin):
    list_display = (
        "academic_year",
        "status",
        "quality_score",
        "total_slots_created",
        "generated_by",
        "generated_at",
    )
    list_filter = ("school", "status", "academic_year")
    readonly_fields = (
        "generated_at",
        "quality_score",
        "hard_violations",
        "soft_violations",
        "generation_time_ms",
    )
    autocomplete_fields = ("generated_by",)

    # ── الحمايةُ في النموذج، وهذه واجهتُها: زرٌّ يختفي بدل خطأٍ يُفاجئ ──
    #
    # حذفُ توليدٍ معتمَد كان يمرّ من هنا بلا اعتراض فيفقد الجدولُ الحيّ نسبَه.
    # النموذجُ يرفض الآن (`ProtectedError`)، لكنّ لوحةَ الإدارة لا تلتقط ما يُرفع
    # من `delete()` نفسِها — فتُخفي الزرَّ عن المحميّ، وتستثنيه من حذف الدفعة.

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_protected:
            return False
        return super().has_delete_permission(request, obj)

    def delete_queryset(self, request, queryset):
        protected = [g for g in queryset if g.is_protected]
        if protected:
            self.message_user(
                request,
                f"استُثني {len(protected)} توليداً محميّاً (معتمَدٌ أو له حصصٌ حيّة) — "
                "اعتمد مسودّةً أخرى بدله.",
                level=messages.WARNING,
            )
            queryset = queryset.exclude(pk__in=[g.pk for g in protected])
        super().delete_queryset(request, queryset)


@admin.register(ScheduleBaseline)
class ScheduleBaselineAdmin(admin.ModelAdmin):
    list_display = ("label", "academic_year", "school", "created_at")
    list_filter = ("school", "academic_year")
    readonly_fields = ("metrics", "created_at")

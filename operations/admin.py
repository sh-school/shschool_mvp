from django.contrib import admin

from .models import (
    AbsenceAlert,
    ScheduleGeneration,
    ScheduleSlot,
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
    list_display = ("name_ar", "code", "school")
    list_filter = ("school",)
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
    autocomplete_fields = ("student", "marked_by")
    date_hierarchy = "marked_at"


@admin.register(AbsenceAlert)
class AbsenceAlertAdmin(admin.ModelAdmin):
    list_display = ("student", "absence_count", "status", "created_at")
    list_filter = ("status", "school")
    autocomplete_fields = ("student",)


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
    autocomplete_fields = ("substitute", "assigned_by")
    ordering = ("-created_at",)


# ── Phase 3 — الجدولة الذكية ──────────────


@admin.register(TimeSlotConfig)
class TimeSlotConfigAdmin(admin.ModelAdmin):
    list_display = ("period_number", "start_time", "end_time", "day_type", "is_break", "break_label")
    list_filter = ("school", "day_type", "is_break")
    ordering = ("day_type", "period_number")


@admin.register(SubjectClassAssignment)
class SubjectClassAssignmentAdmin(admin.ModelAdmin):
    list_display = ("subject", "class_group", "teacher", "weekly_periods", "requires_lab", "is_active")
    list_filter = ("school", "academic_year", "subject", "requires_lab", "is_active")
    search_fields = ("teacher__full_name", "subject__name_ar", "class_group__section")
    autocomplete_fields = ("teacher", "class_group", "subject")
    list_editable = ("weekly_periods", "requires_lab", "is_active")
    list_per_page = 50


@admin.register(TeacherPreference)
class TeacherPreferenceAdmin(admin.ModelAdmin):
    list_display = ("teacher", "max_daily_periods", "max_consecutive", "free_day", "academic_year")
    list_filter = ("school", "academic_year", "free_day")
    search_fields = ("teacher__full_name",)
    autocomplete_fields = ("teacher",)


@admin.register(ScheduleGeneration)
class ScheduleGenerationAdmin(admin.ModelAdmin):
    list_display = ("academic_year", "status", "quality_score", "total_slots_created", "generated_by", "generated_at")
    list_filter = ("school", "status", "academic_year")
    readonly_fields = ("generated_at", "quality_score", "hard_violations", "soft_violations", "generation_time_ms")
    autocomplete_fields = ("generated_by",)

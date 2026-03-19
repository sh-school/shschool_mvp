from django.contrib import admin
from .models import (
    Subject, Session, StudentAttendance, AbsenceAlert,
    ScheduleSlot, TeacherAbsence, SubstituteAssignment,
)


# ── Phase 1 ──────────────────────────────────

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display  = ("name_ar", "code", "school")
    list_filter   = ("school",)
    search_fields = ("name_ar", "code")


class AttendanceInline(admin.TabularInline):
    model          = StudentAttendance
    extra          = 0
    fields         = ("student", "status", "excuse_type", "marked_by", "marked_at")
    readonly_fields= ("marked_at",)
    raw_id_fields  = ("student",)


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display   = ("class_group", "subject", "teacher", "date", "start_time", "status")
    list_filter    = ("school", "status", "date")
    search_fields  = ("teacher__full_name", "class_group__section")
    date_hierarchy = "date"
    inlines        = [AttendanceInline]


@admin.register(StudentAttendance)
class StudentAttendanceAdmin(admin.ModelAdmin):
    list_display   = ("student", "session", "status", "marked_by", "marked_at")
    list_filter    = ("status", "school")
    search_fields  = ("student__full_name", "student__national_id")
    date_hierarchy = "marked_at"
    raw_id_fields  = ("student",)


@admin.register(AbsenceAlert)
class AbsenceAlertAdmin(admin.ModelAdmin):
    list_display = ("student", "absence_count", "status", "created_at")
    list_filter  = ("status", "school")


# ── Phase 2 ──────────────────────────────────

@admin.register(ScheduleSlot)
class ScheduleSlotAdmin(admin.ModelAdmin):
    list_display  = ("day_of_week", "period_number", "teacher", "class_group", "subject", "start_time", "end_time", "is_active")
    list_filter   = ("school", "day_of_week", "is_active", "academic_year")
    search_fields = ("teacher__full_name", "class_group__section", "subject__name_ar")
    ordering      = ("day_of_week", "period_number")


@admin.register(TeacherAbsence)
class TeacherAbsenceAdmin(admin.ModelAdmin):
    list_display  = ("teacher", "date", "reason", "status", "reported_by", "created_at")
    list_filter   = ("school", "status", "reason", "date")
    search_fields = ("teacher__full_name",)
    ordering      = ("-date",)


@admin.register(SubstituteAssignment)
class SubstituteAssignmentAdmin(admin.ModelAdmin):
    list_display  = ("absence", "slot", "substitute", "status", "assigned_by", "created_at")
    list_filter   = ("school", "status")
    search_fields = ("substitute__full_name", "absence__teacher__full_name")
    ordering      = ("-created_at",)

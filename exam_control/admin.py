from django.contrib import admin

from .models import (
    ExamGradeSheet,
    ExamIncident,
    ExamRoom,
    ExamSchedule,
    ExamSession,
    ExamSupervisor,
)


class ExamRoomInline(admin.TabularInline):
    model = ExamRoom
    extra = 2
    fields = ["name", "capacity", "floor", "notes"]


class ExamSupervisorInline(admin.TabularInline):
    model = ExamSupervisor
    extra = 3
    fields = ["staff", "role", "room"]
    autocomplete_fields = ["staff"]


@admin.register(ExamRoom)
class ExamRoomAdmin(admin.ModelAdmin):
    list_display = ["name", "capacity", "floor", "session"]
    list_filter = ["session"]
    search_fields = ["name"]


@admin.register(ExamSchedule)
class ExamScheduleAdmin(admin.ModelAdmin):
    list_display = ["subject", "grade_level", "exam_date", "session"]
    list_filter = ["session", "exam_date"]
    search_fields = ["subject", "grade_level"]


@admin.register(ExamSession)
class ExamSessionAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "school",
        "session_type",
        "academic_year",
        "start_date",
        "end_date",
        "status",
    ]
    list_filter = ["status", "session_type", "academic_year"]
    search_fields = ["name"]
    autocomplete_fields = ["created_by"]
    inlines = [ExamRoomInline, ExamSupervisorInline]
    date_hierarchy = "start_date"


@admin.register(ExamIncident)
class ExamIncidentAdmin(admin.ModelAdmin):
    list_display = ["session", "incident_type", "severity", "student", "status", "incident_time"]
    list_filter = ["incident_type", "severity", "status"]
    search_fields = ["description", "student__full_name"]
    autocomplete_fields = ["student", "reported_by", "session", "behavior_link"]
    date_hierarchy = "incident_time"


@admin.register(ExamGradeSheet)
class ExamGradeSheetAdmin(admin.ModelAdmin):
    list_display = ["schedule", "papers_count", "status", "submitted_at"]
    list_filter = ["status"]
    autocomplete_fields = ["schedule", "grader"]

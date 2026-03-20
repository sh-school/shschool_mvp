from django.contrib import admin
from .models import ExamSession, ExamRoom, ExamSupervisor, ExamSchedule, ExamIncident, ExamGradeSheet, ExamEnvelope


class ExamRoomInline(admin.TabularInline):
    model   = ExamRoom
    extra   = 2
    fields  = ['name', 'capacity', 'floor', 'notes']


class ExamSupervisorInline(admin.TabularInline):
    model       = ExamSupervisor
    extra       = 3
    fields      = ['staff', 'role', 'room']
    raw_id_fields = ['staff']


@admin.register(ExamSession)
class ExamSessionAdmin(admin.ModelAdmin):
    list_display  = ['name', 'school', 'session_type', 'academic_year', 'start_date', 'end_date', 'status']
    list_filter   = ['status', 'session_type', 'academic_year']
    search_fields = ['name']
    inlines       = [ExamRoomInline, ExamSupervisorInline]
    date_hierarchy = 'start_date'


@admin.register(ExamIncident)
class ExamIncidentAdmin(admin.ModelAdmin):
    list_display   = ['session', 'incident_type', 'severity', 'student', 'status', 'incident_time']
    list_filter    = ['incident_type', 'severity', 'status']
    search_fields  = ['description', 'student__full_name']
    raw_id_fields  = ['student', 'reported_by']
    date_hierarchy = 'incident_time'


@admin.register(ExamGradeSheet)
class ExamGradeSheetAdmin(admin.ModelAdmin):
    list_display = ['schedule', 'papers_count', 'status', 'submitted_at']
    list_filter  = ['status']

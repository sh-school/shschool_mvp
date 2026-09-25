from django.contrib import admin

from core.admin import SchoolScopedAdmin

from .models import ImportLog


@admin.register(ImportLog)
class ImportLogAdmin(SchoolScopedAdmin):
    list_display = ("file_name", "school", "status", "total_rows", "imported_rows", "started_at")
    list_filter = ("status",)
    autocomplete_fields = ("uploaded_by",)
    readonly_fields = ("error_log",)

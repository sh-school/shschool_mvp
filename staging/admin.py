from django.contrib import admin

from .models import ImportLog


@admin.register(ImportLog)
class ImportLogAdmin(admin.ModelAdmin):
    list_display = ("file_name", "school", "status", "total_rows", "imported_rows", "started_at")
    list_filter = ("status",)
    readonly_fields = ("error_log",)

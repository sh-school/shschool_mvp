from django.contrib import admin

from .models import LeaveBalance, LeaveRequest


@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
    list_display = (
        "staff",
        "leave_type",
        "total_days",
        "used_days",
        "remaining_days",
        "academic_year",
    )
    list_filter = ("leave_type", "academic_year")
    search_fields = ("staff__full_name", "staff__national_id")


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = (
        "staff",
        "leave_type",
        "start_date",
        "end_date",
        "days_count",
        "status",
        "academic_year",
    )
    list_filter = ("status", "leave_type", "academic_year")
    search_fields = ("staff__full_name", "staff__national_id")
    date_hierarchy = "start_date"
    readonly_fields = ("created_at", "updated_at", "created_by", "updated_by")

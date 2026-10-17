from django.contrib import admin

from .models import StudentActivity, StudentTransfer


@admin.register(StudentTransfer)
class StudentTransferAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "direction",
        "other_school_name",
        "to_class_group",
        "status",
        "transfer_date",
        "academic_year",
        "decided_by",
        "decided_at",
    )
    list_filter = ("direction", "status", "academic_year")
    search_fields = ("student__full_name", "student__national_id", "other_school_name")
    date_hierarchy = "transfer_date"
    list_select_related = ("student", "to_class_group", "decided_by")
    readonly_fields = (
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
        "decided_by",
        "decided_at",
        "reviewed_by",
        "reviewed_at",
        "approved_by",
        "approved_at",
        "placed_by",
        "placed_at",
        "entered_by",
        "entered_at",
    )


@admin.register(StudentActivity)
class StudentActivityAdmin(admin.ModelAdmin):
    list_display = ("student", "title", "activity_type", "scope", "date", "academic_year")
    list_filter = ("activity_type", "scope", "academic_year")
    search_fields = ("student__full_name", "title")
    date_hierarchy = "date"
    readonly_fields = ("created_at", "updated_at")

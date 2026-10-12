from django.contrib import admin

from .models import (
    GuardianRequest,
    GuardianRequestEvent,
    StudentActivity,
    StudentTransfer,
)


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
    )


@admin.register(StudentActivity)
class StudentActivityAdmin(admin.ModelAdmin):
    list_display = ("student", "title", "activity_type", "scope", "date", "academic_year")
    list_filter = ("activity_type", "scope", "academic_year")
    search_fields = ("student__full_name", "title")
    date_hierarchy = "date"
    readonly_fields = ("created_at", "updated_at")


class GuardianRequestEventInline(admin.TabularInline):
    model = GuardianRequestEvent
    extra = 0
    can_delete = False
    readonly_fields = ("stage", "actor", "at", "note")


@admin.register(GuardianRequest)
class GuardianRequestAdmin(admin.ModelAdmin):
    """طلباتُ الأولياء: للاطّلاع — الجوّالاتُ المشفَّرةُ لا تُعرض، والتغييرُ يمرّ من مسار الشاشات لا من هنا."""

    list_display = ("kind", "stage", "student", "request_date", "academic_year", "school")
    list_filter = ("kind", "stage", "academic_year")
    date_hierarchy = "request_date"
    list_select_related = ("student", "school")
    inlines = (GuardianRequestEventInline,)
    exclude = ("contact_phone_encrypted", "current_phone_encrypted", "new_phone_encrypted")
    readonly_fields = (
        "kind",
        "stage",
        "school",
        "student",
        "academic_year",
        "request_date",
        "referred_to",
        "feedback_by",
        "verified_by",
        "verified_at",
        "applied_at",
        "closed_at",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    )

    def has_add_permission(self, request):
        return False

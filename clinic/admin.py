from django.contrib import admin

from clinic.models import ClinicVisit, HealthRecord


@admin.register(HealthRecord)
class HealthRecordAdmin(admin.ModelAdmin):
    list_display = ("student", "blood_type", "updated_at")
    search_fields = ("student__full_name", "student__national_id")
    readonly_fields = ("updated_at",)
    fieldsets = (
        ("بيانات الطالب", {"fields": ("student",)}),
        (
            "المعلومات الصحية",
            {"fields": ("blood_type", "allergies", "chronic_diseases", "medications")},
        ),
        ("جهات الاتصال الطارئة", {"fields": ("emergency_contact_name", "emergency_contact_phone")}),
        ("آخر تحديث", {"fields": ("updated_at",)}),
    )


@admin.register(ClinicVisit)
class ClinicVisitAdmin(admin.ModelAdmin):
    list_display = ("student", "visit_date", "nurse", "is_sent_home", "parent_notified")
    list_filter = ("visit_date", "is_sent_home", "parent_notified")
    search_fields = ("student__full_name", "student__national_id")
    readonly_fields = ("visit_date",)
    fieldsets = (
        ("بيانات الزيارة", {"fields": ("school", "student", "nurse", "visit_date")}),
        ("الأعراض والعلاج", {"fields": ("reason", "symptoms", "temperature", "treatment")}),
        ("الإجراءات", {"fields": ("is_sent_home", "parent_notified")}),
    )

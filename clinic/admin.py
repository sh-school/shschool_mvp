from django.contrib import admin

from clinic.models import ClinicVisit, HealthRecord


@admin.register(HealthRecord)
class HealthRecordAdmin(admin.ModelAdmin):
    list_display = ("student", "blood_type_encrypted", "needs_care", "updated_at")
    list_filter = ("needs_care",)
    search_fields = ("student__full_name", "student__national_id")
    readonly_fields = ("updated_at",)
    fieldsets = (
        ("بيانات الطالب", {"fields": ("student",)}),
        (
            "المعلومات الصحية",
            {"fields": ("blood_type_encrypted", "allergies", "chronic_diseases", "medications")},
        ),
        ("علامة المراعاة", {"fields": ("needs_care",)}),
        ("جهات الاتصال الطارئة", {"fields": ("emergency_contact_name", "emergency_contact_phone")}),
        ("آخر تحديث", {"fields": ("updated_at",)}),
    )


@admin.register(ClinicVisit)
class ClinicVisitAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "visit_date",
        "nurse",
        "outcome",
        "is_sent_home",
        "parent_notified",
    )
    # مجموعةُ الخدمة لا تُعرض في القوائم (قرار المالك: وسمٌ محايد، وأسماؤها قد توحي بحالةٍ مزمنة)
    list_filter = ("visit_date", "outcome", "is_sent_home", "parent_notified")
    search_fields = ("student__full_name", "student__national_id")
    autocomplete_fields = ("student", "nurse")
    readonly_fields = ("visit_date", "period_number")
    fieldsets = (
        ("بيانات الزيارة", {"fields": ("school", "student", "nurse", "visit_date")}),
        (
            "الترميز",
            {
                "fields": (
                    "service_code",
                    "service_group",
                    "complaint_code",
                    "outcome",
                    "closed_at",
                    "period_number",
                )
            },
        ),
        ("الأعراض والعلاج", {"fields": ("reason", "symptoms", "temperature", "treatment")}),
        ("الإجراءات", {"fields": ("is_sent_home", "parent_notified")}),
    )

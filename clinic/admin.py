from django.contrib import admin

from clinic.models import (
    ClinicVisit,
    GuardianMedicationConsent,
    HealthRecord,
    MedicationCatalogItem,
    VisitMedication,
)


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
    readonly_fields = (
        "visit_date",
        "period_number",
        "external_report_by",
        "external_report_at",
        "teacher_alerted_at",
    )
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
        (
            "الحالة المعدية وتنبيه المعلّم",
            {
                "fields": (
                    "infectious_status",
                    "external_report_decision",
                    "external_report_by",
                    "external_report_at",
                    "teacher_alerted_at",
                )
            },
        ),
    )


@admin.register(MedicationCatalogItem)
class MedicationCatalogItemAdmin(admin.ModelAdmin):
    """الكتالوج المعتمَد سريرياً: لا يُصرف بندٌ بلا «وقت الاعتماد السريري»."""

    list_display = ("name", "standard_dose", "school", "is_active", "approved_at")
    list_filter = ("school", "is_active")
    search_fields = ("name",)


@admin.register(GuardianMedicationConsent)
class GuardianMedicationConsentAdmin(admin.ModelAdmin):
    list_display = ("student", "catalog_item", "granted_at", "expires_at", "revoked_at")
    list_filter = ("school", "catalog_item")
    autocomplete_fields = ("student",)
    readonly_fields = ("recorded_by",)


@admin.register(VisitMedication)
class VisitMedicationAdmin(admin.ModelAdmin):
    """سجلُّ صرفٍ للقراءة فقط: لا يُنشأ ولا يُعدَّل إلا عبر `MedicationService.dispense`."""

    list_display = ("visit", "catalog_item", "dose", "dispensed_by", "dispensed_at")
    list_filter = ("school", "catalog_item")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

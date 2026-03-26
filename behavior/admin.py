from django.contrib import admin

from .models import BehaviorInfraction, BehaviorPointRecovery, ViolationCategory


@admin.register(ViolationCategory)
class ViolationCategoryAdmin(admin.ModelAdmin):
    list_display = [
        "code", "degree", "name_ar", "points", "tags",
        "requires_security_referral", "requires_parent_summon", "is_active",
    ]
    list_filter = ["degree", "is_active", "requires_security_referral"]
    search_fields = ["code", "name_ar"]
    ordering = ["degree", "code"]
    actions = ["seed_2025_action", "seed_abcd_action"]

    def seed_2025_action(self, request, queryset):
        created = ViolationCategory.seed_2025()
        self.message_user(request, f"✅ تم إضافة {created} مخالفة — لائحة قطر 2025-2026")

    seed_2025_action.short_description = "🔄 حقن لائحة 2025 الرسمية (46 مخالفة)"

    def seed_abcd_action(self, request, queryset):
        created = ViolationCategory.seed_abcd()
        self.message_user(request, f"تم إضافة {created} مخالفة من لائحة ABCD القديمة")

    seed_abcd_action.short_description = "🔄 تغذية لائحة ABCD القديمة"


@admin.register(BehaviorInfraction)
class BehaviorInfractionAdmin(admin.ModelAdmin):
    list_display = [
        "student", "violation_category", "level", "escalation_step",
        "date", "is_resolved", "parent_summoned", "school",
    ]
    list_filter = [
        "level", "is_resolved", "escalation_step",
        "parent_summoned", "security_agency",
        "social_media_platform",
    ]
    search_fields = ["student__full_name", "description"]
    autocomplete_fields = ["student", "reported_by", "violation_category"]
    date_hierarchy = "date"

    fieldsets = (
        ("المعلومات الأساسية", {
            "fields": (
                "school", "student", "reported_by", "violation_category",
                "level", "description",
            ),
        }),
        ("الإجراء المتخذ", {
            "fields": (
                "action_taken", "escalation_step", "points_deducted", "is_resolved",
            ),
        }),
        ("استدعاء ولي الأمر", {
            "fields": (
                "parent_summoned", "parent_summon_date", "parent_undertaking_signed",
            ),
            "classes": ("collapse",),
        }),
        ("الإيقاف", {
            "fields": ("suspension_type", "suspension_days"),
            "classes": ("collapse",),
        }),
        ("التشهير الرقمي", {
            "fields": ("social_media_platform", "digital_evidence_notes"),
            "classes": ("collapse",),
        }),
        ("الإحالة الأمنية (الدرجة 4)", {
            "fields": (
                "security_referral_date", "security_agency",
                "security_reference_number", "security_notes",
            ),
            "classes": ("collapse",),
        }),
    )


@admin.register(BehaviorPointRecovery)
class BehaviorPointRecoveryAdmin(admin.ModelAdmin):
    list_display = ["infraction", "points_restored", "date", "approved_by"]
    autocomplete_fields = ["approved_by"]

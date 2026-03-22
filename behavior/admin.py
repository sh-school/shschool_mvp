from django.contrib import admin

from .models import BehaviorInfraction, BehaviorPointRecovery, ViolationCategory


@admin.register(ViolationCategory)
class ViolationCategoryAdmin(admin.ModelAdmin):
    list_display = ["code", "category", "name_ar", "points", "default_action", "is_active"]
    list_filter = ["category", "is_active"]
    search_fields = ["code", "name_ar"]
    ordering = ["category", "code"]
    actions = ["seed_abcd_action"]

    def seed_abcd_action(self, request, queryset):
        created = ViolationCategory.seed_abcd()
        self.message_user(request, f"تم إضافة {created} مخالفة جديدة من لائحة ABCD")

    seed_abcd_action.short_description = "🔄 تغذية لائحة ABCD الكاملة"


@admin.register(BehaviorInfraction)
class BehaviorInfractionAdmin(admin.ModelAdmin):
    list_display = ["student", "violation_category", "level", "date", "is_resolved", "school"]
    list_filter = ["level", "is_resolved", "violation_category__category"]
    search_fields = ["student__full_name", "description"]
    raw_id_fields = ["student", "reported_by", "violation_category"]
    date_hierarchy = "date"


@admin.register(BehaviorPointRecovery)
class BehaviorPointRecoveryAdmin(admin.ModelAdmin):
    list_display = ["infraction", "points_restored", "date", "approved_by"]

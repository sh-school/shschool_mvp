"""خارطةُ تجويد المنصّة في لوحة الإدارة التقنيّة — لمطوّر المنصّة (superuser أو من مُنح الصلاحيّة).

الصفحةُ `/roadmap/` هي واجهةُ العمل اليوميّة؛ وهذا التسجيلُ للاطّلاع والبحث والتصحيح المباشر
على الجداول الستّة. الطوابعُ (`أُنشئ`/`عُدِّل`/`عدّله`) للقراءة فقط.

أقسامُ كلِّ نموذجٍ قابلةٌ للطيّ ومطويّةٌ افتراضاً (`classes: collapse`): تُفتح بالنقر على «إظهار».
"""

from django.contrib import admin

from roadmap.models import (
    RoadmapChecklistItem,
    RoadmapDecision,
    RoadmapItem,
    RoadmapKpi,
    RoadmapMeta,
    RoadmapRisk,
)

# القائمةُ الأفقيّة في الترويسة (admin_menu) تغني عن الشريط الجانبيّ فلا تكرار.
admin.site.enable_nav_sidebar = False

_STAMPS = ("created_at", "updated_at", "updated_by")
_COLLAPSE = ("collapse",)


def _section(title: str, *fields: str) -> tuple[str, dict[str, object]]:
    return (title, {"fields": fields, "classes": _COLLAPSE})


_STAMPS_SECTION = _section("الطوابع", *_STAMPS)


class _RoadmapAdmin(admin.ModelAdmin):
    readonly_fields = _STAMPS
    list_per_page = 50
    show_full_result_count = False


@admin.register(RoadmapItem)
class RoadmapItemAdmin(_RoadmapAdmin):
    list_display = ("code", "title", "lane", "status", "progress", "start_date", "end_date", "src")
    list_filter = ("lane", "status", "src", "gate")
    search_fields = ("code", "title", "criterion", "note", "pr")
    ordering = ("sort_order", "code")
    fieldsets = (
        _section("الأساسيّ", "code", "title", "lane", "status", "progress"),
        _section("الجدولة", "start_date", "end_date", "date_basis", "effort", "deps"),
        _section("المعيار والملاحظات", "criterion", "note", "gate", "ref", "pr"),
        _section("المصدر والترتيب", "src", "sort_order"),
        _STAMPS_SECTION,
    )


@admin.register(RoadmapKpi)
class RoadmapKpiAdmin(_RoadmapAdmin):
    list_display = ("code", "name", "lane", "baseline", "current", "target", "unit", "measured_at")
    list_filter = ("lane", "direction", "text_mode")
    search_fields = ("code", "name", "source", "why")
    ordering = ("sort_order", "code")
    fieldsets = (
        _section("الأساسيّ", "code", "name", "lane"),
        _section("القيم", "baseline", "current", "target", "direction", "unit"),
        _section("القيم نصّاً", "baseline_text", "target_text", "text_mode"),
        _section("المصدر والقياس", "source", "why", "measured_at"),
        _section("السجلّ وما زاد", "history", "extra"),
        _section("الترتيب", "sort_order"),
        _STAMPS_SECTION,
    )


@admin.register(RoadmapDecision)
class RoadmapDecisionAdmin(_RoadmapAdmin):
    list_display = ("code", "title", "status", "decider", "decision_date", "src")
    list_filter = ("status", "src")
    search_fields = ("code", "title", "blocks", "recommendation")
    ordering = ("sort_order", "code")
    fieldsets = (
        _section("الأساسيّ", "code", "title", "status", "src"),
        _section("الحسم", "decider", "due", "decision_date"),
        _section("التفاصيل", "blocks", "options", "recommendation"),
        _section("الترتيب", "sort_order"),
        _STAMPS_SECTION,
    )


@admin.register(RoadmapRisk)
class RoadmapRiskAdmin(_RoadmapAdmin):
    list_display = ("code", "risk", "prob", "impact", "src")
    list_filter = ("impact", "prob")
    search_fields = ("code", "risk", "mitigation")
    ordering = ("sort_order", "code")
    fieldsets = (
        _section("الأساسيّ", "code", "risk", "src"),
        _section("التقدير", "prob", "impact"),
        _section("التخفيف", "mitigation"),
        _section("الترتيب", "sort_order"),
        _STAMPS_SECTION,
    )


@admin.register(RoadmapChecklistItem)
class RoadmapChecklistItemAdmin(_RoadmapAdmin):
    list_display = ("code", "text", "done", "src")
    list_filter = ("done", "src")
    search_fields = ("code", "text")
    ordering = ("sort_order", "code")
    fieldsets = (
        _section("الأساسيّ", "code", "text", "done"),
        _section("المصدر والترتيب", "src", "sort_order"),
        _STAMPS_SECTION,
    )


@admin.register(RoadmapMeta)
class RoadmapMetaAdmin(_RoadmapAdmin):
    list_display = ("key", "updated_at")
    readonly_fields = (*_STAMPS, "key")
    fieldsets = (
        _section("الوثيقة", "key", "data"),
        _STAMPS_SECTION,
    )

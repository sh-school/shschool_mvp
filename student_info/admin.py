from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from clinic.health_access import HealthAuditAdminMixin

from .models import StudentNote


@admin.register(StudentNote)
class StudentNoteAdmin(HealthAuditAdminMixin, admin.ModelAdmin):
    """النصُّ مشفَّرٌ في القاعدة، ولوحةُ جانغو تفكّه عند العرض — فهي مقصورةٌ
    على حسابين اثنين في هذه المنصّة، ولا يُبحث فيها بنصّ الملاحظة."""

    list_display = ("student", "category", "title", "occurred_on", "created_by")
    list_filter = ("category", "academic_year")
    search_fields = ("student__full_name", "title")
    date_hierarchy = "occurred_on"
    readonly_fields = ("created_at", "updated_at", "created_by", "updated_by")

    def shows_health(self, request: HttpRequest, obj: Any, page: str) -> bool:
        return obj.category == "nurse"

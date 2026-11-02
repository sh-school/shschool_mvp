from django.contrib import admin

from core.admin import SchoolScopedAdmin
from operations.admin import ReadOnlyAdminMixin

from .models import ConductProposal


@admin.register(ConductProposal)
class ConductProposalAdmin(ReadOnlyAdminMixin, SchoolScopedAdmin):
    """اقتراحُ المخالفة يولّده النظامُ ويقرّره المشرفُ بخدمةٍ مدقَّقة — فالإدارةُ قراءةٌ فقط (D-272م)."""

    list_display = ("student", "date", "kind", "status", "decided_by", "decided_at")
    list_select_related = ("student", "decided_by")
    list_filter = ("status", "kind", "school")
    search_fields = ("student__full_name", "student__national_id")
    date_hierarchy = "date"

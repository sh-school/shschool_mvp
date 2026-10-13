"""لوحةُ الإدارة لسجلّي «متابعة الغياب» — قراءةٌ كاملةٌ بمرشّحات، ولا كتابةَ (W-20261013-011).

السجلّان مضافان فقط وتُكتبان بخدمتهما (`services/absence_followup.py`) فلا إضافةَ ولا تعديلَ ولا حذفَ من
هنا. والتغذية الراجعة من وليّ الأمر نصٌّ مشفَّرٌ (PII) لا يراه إلّا المشرفُ الأعلى، وفتحُ سجلٍّ فيه نصٌّ سطرُ تدقيقٍ بلا نصّه.
ولا اسمَ وليٍّ ولا أمٍّ هنا ولا في النموذجين أصلاً (D-431م).
"""

from typing import Any

from django.contrib import admin
from django.http import HttpRequest, HttpResponse

from core.admin import SchoolScopedAdmin
from core.models import AuditLog

from .admin import ReadOnlyAdminMixin, SensitiveFieldsMixin
from .models import AbsenceActionLog, AbsenceContactLog


@admin.register(AbsenceContactLog)
class AbsenceContactLogAdmin(SensitiveFieldsMixin, ReadOnlyAdminMixin, SchoolScopedAdmin):
    list_display = (
        "student",
        "absence_date",
        "outcome",
        "contacted_by",
        "contacted_at",
        "corrects",
    )
    list_select_related = ("student", "contacted_by")
    list_filter = ("outcome", "absence_date", "school")
    search_fields = ("student__full_name", "student__national_id")
    date_hierarchy = "absence_date"
    sensitive_fields = ("feedback",)

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        obj = self.get_object(request, object_id)
        if obj is not None and obj.feedback and request.user.is_superuser:
            AuditLog.log(
                user=request.user,
                action="view",
                model_name="other",
                object_id=obj.pk,
                object_repr="التغذية الراجعة من وليّ الأمر — لوحة الإدارة",
                changes={"feedback_opened": 1},
                school=obj.school,
                request=request,
            )
        return super().change_view(request, object_id, form_url, extra_context)


@admin.register(AbsenceActionLog)
class AbsenceActionLogAdmin(ReadOnlyAdminMixin, SchoolScopedAdmin):
    list_display = (
        "student",
        "absence_date",
        "status",
        "action_kind",
        "acted_by",
        "acted_at",
        "excuse",
        "corrects",
    )
    list_select_related = ("student", "acted_by", "excuse")
    list_filter = ("status", "absence_date", "school")
    search_fields = ("student__full_name", "student__national_id")
    date_hierarchy = "absence_date"

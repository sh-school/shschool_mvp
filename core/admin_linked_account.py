"""لوحةُ الحسابات المرتبطة بالمطوّر في `/admin/` — بقدرة `developer.linked_accounts` وحدَها (شروطُ 0104، W-20261009-032).

- **الإنشاء** بإجراء مطوّر المنصّة الفعليّ نفسِه: حسابُ المطوّر يُفرض = الطالب، والهدفُ يُختار من كادر مدرسته المؤهَّل
  وحدَه (لا قائمةَ بكلّ مستخدمي المنصّة). والربطُ لا يُستعمل قبل تأكيد هويّة المطوّر عند أوّل تبديل (`confirmed_at`).
- **التعديل** إيقافٌ وتفعيلٌ لا غير، و**الحذف** للمطوّر والمشرف الأعلى؛ وكلُّ إنشاءٍ وتعديلٍ وحذفٍ سطرٌ في السجلّ بالطرفين.
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin

from .capabilities import has_capability
from .models import AuditLog, CustomUser, LinkedAccount

CAPABILITY = "developer.linked_accounts"


def _eligible_targets(developer: Any) -> Any:
    from core.view_as.linked import TARGET_ROLES

    school = developer.get_school()
    if school is None:
        return CustomUser.objects.none()
    return (
        CustomUser.objects.filter(
            is_active=True,
            is_superuser=False,
            is_staff=False,
            memberships__school=school,
            memberships__is_active=True,
            memberships__role__name__in=TARGET_ROLES,
        )
        .exclude(pk=developer.pk)
        .distinct()
        .order_by("full_name")
    )


def _log(request: Any, action: str, link: LinkedAccount) -> None:
    AuditLog.log(
        user=request.user,
        action=action,
        model_name="LinkedAccount",
        object_id=str(link.pk),
        object_repr="ربطُ حسابٍ بمطوّر المنصّة",
        changes={
            "developer": str(link.developer_id),
            "target": str(link.target_id),
            "is_active": link.is_active,
        },
        request=request,
    )


@admin.register(LinkedAccount)
class LinkedAccountAdmin(admin.ModelAdmin):
    list_display = ("developer", "target", "is_active", "confirmed_at", "created_at")
    list_select_related = ("developer", "target")
    list_filter = ("is_active",)
    ordering = ("-created_at",)

    def get_fields(self, request: Any, obj: Any = None) -> tuple[str, ...]:
        if obj is None:
            return ("target", "is_active")
        return (
            "developer",
            "target",
            "is_active",
            "confirmed_at",
            "created_by",
            "created_at",
            "updated_at",
        )

    def get_readonly_fields(self, request: Any, obj: Any = None) -> tuple[str, ...]:
        if obj is None:
            return ()
        return ("developer", "target", "confirmed_at", "created_by", "created_at", "updated_at")

    # ── الصلاحيّات: القدرةُ وحدَها لا صلاحيّاتُ Django ───────────────

    def has_module_permission(self, request: Any) -> bool:
        return has_capability(request.user, CAPABILITY)

    def has_view_permission(self, request: Any, obj: Any = None) -> bool:
        return has_capability(request.user, CAPABILITY)

    def has_add_permission(self, request: Any) -> bool:
        from core.view_as.preview import can_start

        # الربطُ لا يُنشأ إلّا بإجراء المطوّر نفسِه — لا المشرفُ الأعلى عنه.
        return has_capability(request.user, CAPABILITY) and can_start(request.user)

    def has_change_permission(self, request: Any, obj: Any = None) -> bool:
        return has_capability(request.user, CAPABILITY)

    def has_delete_permission(self, request: Any, obj: Any = None) -> bool:
        return has_capability(request.user, CAPABILITY)

    def get_queryset(self, request: Any) -> Any:
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        return queryset.filter(developer_id=request.user.pk)

    # ── الإنشاء: المطوّرُ هو الطالب، والهدفُ من كادر مدرسته ─────────

    def formfield_for_foreignkey(self, db_field: Any, request: Any, **kwargs: Any) -> Any:
        if db_field.name == "target":
            kwargs["queryset"] = _eligible_targets(request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_form(self, request: Any, obj: Any = None, change: bool = False, **kwargs: Any) -> Any:
        form = super().get_form(request, obj, change=change, **kwargs)
        if obj is not None:
            return form
        developer = CustomUser.objects.get(pk=request.user.pk)

        class DeveloperForm(form):  # type: ignore[misc, valid-type]
            """يضع المطوّرَ على الصفّ قبل التحقّق — فتُفحص شروطُ الربط (`LinkedAccount.clean`) بطرفيه."""

            def __init__(self, *args: Any, **form_kwargs: Any) -> None:
                super().__init__(*args, **form_kwargs)
                self.instance.developer = developer

        return DeveloperForm

    def save_model(self, request: Any, obj: LinkedAccount, form: Any, change: bool) -> None:
        if not change:
            obj.developer_id = request.user.pk
            obj.created_by_id = request.user.pk
        super().save_model(request, obj, form, change)
        _log(request, "update" if change else "create", obj)

    def delete_model(self, request: Any, obj: LinkedAccount) -> None:
        _log(request, "delete", obj)
        super().delete_model(request, obj)

    def delete_queryset(self, request: Any, queryset: Any) -> None:
        for link in queryset:
            self.delete_model(request, link)

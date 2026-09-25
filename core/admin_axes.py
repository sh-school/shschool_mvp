"""سجلّاتُ الدخول (axes) في لوحة الإدارة — بمن هو صاحبُ المحاولة لا بما كتبه وحده.

axes يحفظ ما كُتب في خانة الدخول (`username`: الرقمُ الشخصيّ أو الوظيفيّ) بلا ربطٍ بالحساب، فكان
المطّلعُ يرى أرقاماً لا أسماء. فتُضاف عمودان — الاسمُ والرقمُ الوظيفيّ — من الحساب الذي يطابق
المكتوبَ رقماً شخصيّاً أو وظيفيّاً، **باستعلامٍ فرعيٍّ في استعلام القائمة نفسه** (لا سؤالٌ لكلّ صفّ).
والمكتوبُ الذي لا يطابق حساباً (خطأٌ إملائيّ، أو محاولةُ تخمين) يبقى بلا اسم — وهذا بعينه ما يُراد رصدُه.

تُستبدل لوحةُ axes لا تُعدَّل الحزمة: تُلغى وتُسجَّل بصنفٍ يرث صنفَها. ويجري ذلك في
`CoreConfig.ready()` لأنّ axes آخرُ التطبيقات، والتسجيلُ التلقائيُّ للوحات يجري في `ready()` تطبيق
الإدارة (قبل `core`) — فلوحتُه مسجَّلةٌ حين يبلغ `core` دورَه.
"""

from __future__ import annotations

from typing import Any, cast

from django.contrib import admin
from django.db.models import OuterRef, Q, QuerySet, Subquery


def _owner(field: str) -> Subquery:
    from core.models import CustomUser

    # الرقمُ الوظيفيّ الفارغ مشتركٌ بين كثيرين (الطلبةُ وأولياءُ الأمور) — فلا يُطابَق به مكتوبٌ فارغ.
    by_employee_number = Q(employee_number=OuterRef("username")) & ~Q(employee_number="")
    matches = CustomUser.objects.filter(Q(national_id=OuterRef("username")) | by_employee_number)
    return Subquery(matches.values(field)[:1])


#: الرقمُ الشخصيّ القطريّ 11 رقماً (`core.models.user._national_id_validator`)؛ والرقمُ الوظيفيّ أقصر.
_NATIONAL_ID_LENGTH = 11


def mask_national_id(typed: str) -> str:
    """الرقمُ الشخصيّ في القائمة آخرُ أربعة أرقامٍ فقط (PDPPL م.8 — كقائمة المستخدمين).

    والرقمُ الوظيفيّ يبقى كما هو: عمودُه ظاهرٌ أصلاً. والبحثُ ما زال بالرقم الكامل (`search_fields`)،
    والصفحةُ التفصيليّة للمحاولة تعرضه كاملاً لمن فتحها — كنموذج تعديل المستخدم.
    """
    if typed.isdigit() and len(typed) == _NATIONAL_ID_LENGTH:
        return f"****{typed[-4:]}"
    return typed or "—"


#: أعمدةُ axes التي تحمل نصّاً إنجليزيّاً لا ترجمةَ له في كتالوجها العربيّ ← بدائلُها العربيّة.
#: (والترجمةُ بملفّ `.po` لا تصل الإنتاج: `compilemessages` في preDeploy وقرصُه غيرُ قرص الخدمة.)
_ARABIC_COLUMNS = {"status": "lock_status", "expiration": "expires_at"}

#: عناوينُ أقسام صفحة المحاولة في axes، بلا ترجمةٍ عربيّة في الحزمة.
_ARABIC_FIELDSETS = {"Form Data": "بيانات النموذج", "Meta Data": "بيانات الطلب"}


def _identified_columns(columns: Any) -> tuple[str, ...]:
    """أعمدةُ axes نفسُها، و«اسمُ المستخدم» مستبدَلٌ بالمخفيّ وبعده الاسمُ والرقمُ الوظيفيّ."""
    out: list[str] = []
    for column in columns:
        if column == "username":
            out += ["typed_username", "owner_name", "owner_employee_number"]
        else:
            out.append(_ARABIC_COLUMNS.get(column, column))
    return tuple(out)


class LockedOutFilter(admin.SimpleListFilter):
    """مرشِّحُ «Locked Out» في axes بعنوانٍ عربيّ، والشرطُ شرطُه: الإخفاقاتُ بلغت الحدّ أم لا."""

    title = "حالة القفل"
    parameter_name = "locked_out"

    def lookups(self, request: Any, model_admin: Any) -> tuple[tuple[str, str], ...]:
        return (("yes", "مقفل"), ("no", "غير مقفل"))

    def queryset(self, request: Any, queryset: QuerySet[Any]) -> QuerySet[Any]:
        from axes.conf import settings as axes_settings

        limit = axes_settings.AXES_FAILURE_LIMIT
        if self.value() == "yes":
            return queryset.filter(failures_since_start__gte=limit)
        if self.value() == "no":
            return queryset.filter(failures_since_start__lt=limit)
        return queryset


class IdentifiedAxesAdminMixin:
    """يُخلط قبل صنف لوحة axes: الاسمُ والرقمُ الوظيفيّ، والرقمُ الشخصيّ مخفيٌّ في القائمة."""

    def get_list_display(self, request: Any) -> tuple[str, ...]:
        return _identified_columns(super().get_list_display(request))  # type: ignore[misc]

    def get_list_filter(self, request: Any) -> list[Any]:
        from axes.admin import IsLockedOutFilter

        filters = super().get_list_filter(request)  # type: ignore[misc]
        return [LockedOutFilter if f is IsLockedOutFilter else f for f in filters]

    def get_fieldsets(self, request: Any, obj: Any = None) -> list[Any]:
        fieldsets = super().get_fieldsets(request, obj)  # type: ignore[misc]
        return [(_ARABIC_FIELDSETS.get(str(title), title), opts) for title, opts in fieldsets]

    def get_queryset(self, request: Any) -> QuerySet[Any]:
        rows: QuerySet[Any] = super().get_queryset(request)  # type: ignore[misc]
        annotated = rows.annotate(
            owner_name=_owner("full_name"),
            owner_employee_number=_owner("employee_number"),
        )
        return cast("QuerySet[Any]", annotated)

    def action_checkbox(self, obj: Any) -> str:
        # وصفُ خانة الاختيار لقارئ الشاشة من `str(obj)` في جانغو — ونصوصُ axes تحمل المكتوبَ كاملاً
        # ("Access Log for <الرقم الشخصيّ> @ …") فتُسرّب ما أخفاه العمود. فيُبنى الوصفُ من الرقم المخفيّ.
        from django import forms
        from django.contrib.admin import helpers
        from django.utils.html import format_html

        label = format_html(
            "اختر هذه المحاولة لإجراء — {} @ {}",
            mask_national_id(str(obj.username or "")),
            obj.attempt_time,
        )
        checkbox = forms.CheckboxInput(
            {"class": "action-select", "aria-label": label}, lambda value: False
        )
        return str(checkbox.render(helpers.ACTION_CHECKBOX_NAME, str(obj.pk)))

    @admin.display(description="المكتوب في خانة الدخول", ordering="username")
    def typed_username(self, obj: Any) -> str:
        return mask_national_id(str(obj.username or ""))

    @admin.display(description="الحالة")
    def lock_status(self, obj: Any) -> str:
        from axes.conf import settings as axes_settings

        remaining = axes_settings.AXES_FAILURE_LIMIT - obj.failures_since_start
        return f"باقٍ {remaining} من المحاولات" if remaining > 0 else "مقفل"

    @admin.display(description="ينتهي في")
    def expires_at(self, obj: Any) -> Any:
        return obj.expiration.expires_at if hasattr(obj, "expiration") else "—"

    @admin.action(description="حذف المحاولات المنتهية")  # type: ignore[type-var]  # خلطةٌ لا ModelAdmin
    def cleanup_expired_attempts(self, request: Any, queryset: QuerySet[Any]) -> None:
        # إجراءُ axes نفسُه (يحذف ما انتهت مدّتُه كلَّه لا المحدَّدَ وحده) برسالةٍ عربيّة
        count = self.handler.clean_expired_user_attempts(request=request)  # type: ignore[attr-defined]
        self.message_user(request, f"حُذفت {count} من المحاولات المنتهية.")  # type: ignore[attr-defined]

    @admin.display(description="الاسم", ordering="owner_name")
    def owner_name(self, obj: Any) -> str:
        return str(getattr(obj, "owner_name", None) or "—")

    @admin.display(description="الرقم الوظيفي", ordering="owner_employee_number")
    def owner_employee_number(self, obj: Any) -> str:
        return str(getattr(obj, "owner_employee_number", None) or "—")


def install() -> None:
    """يستبدل لوحاتِ axes الثلاث (سجلّ الدخول، والمحاولات، والإخفاقات) بأصنافٍ ترثها مع الخلطة."""
    from axes.admin import AccessAttemptAdmin, AccessFailureLogAdmin, AccessLogAdmin
    from axes.models import AccessAttempt, AccessFailureLog, AccessLog

    for model, base in (
        (AccessLog, AccessLogAdmin),
        (AccessAttempt, AccessAttemptAdmin),
        (AccessFailureLog, AccessFailureLogAdmin),
    ):
        identified = type(f"Identified{base.__name__}", (IdentifiedAxesAdminMixin, base), {})
        if admin.site.is_registered(model):
            admin.site.unregister(model)
        admin.site.register(model, identified)

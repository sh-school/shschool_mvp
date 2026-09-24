"""سجلُّ الدخول (axes) في لوحة الإدارة — بمن هو صاحبُ المحاولة لا بما كتبه وحده.

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


def install() -> None:
    from axes.admin import AccessLogAdmin
    from axes.models import AccessLog

    class IdentifiedAccessLogAdmin(AccessLogAdmin):
        list_display = (
            "attempt_time",
            "logout_time",
            "ip_address",
            "typed_username",
            "owner_name",
            "owner_employee_number",
            "user_agent",
            "path_info",
        )

        def get_queryset(self, request: Any) -> QuerySet[Any]:
            rows: QuerySet[Any] = super().get_queryset(request)
            annotated = rows.annotate(
                owner_name=_owner("full_name"),
                owner_employee_number=_owner("employee_number"),
            )
            return cast("QuerySet[Any]", annotated)

        def action_checkbox(self, obj: Any) -> str:
            # وصفُ خانة الاختيار لقارئ الشاشة من `str(obj)` في جانغو — ونصُّ السجلّ في axes يحمل
            # المكتوبَ كاملاً ("Access Log for <الرقم الشخصيّ> @ …") فيُسرّب ما أخفاه العمود. فيُبنى
            # الوصفُ من الرقم المخفيّ نفسه، والسلوكُ كما هو (الاسمُ والقيمةُ والصنف).
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

        @admin.display(description="الاسم", ordering="owner_name")
        def owner_name(self, obj: Any) -> str:
            return str(getattr(obj, "owner_name", None) or "—")

        @admin.display(description="الرقم الوظيفي", ordering="owner_employee_number")
        def owner_employee_number(self, obj: Any) -> str:
            return str(getattr(obj, "owner_employee_number", None) or "—")

    if admin.site.is_registered(AccessLog):
        admin.site.unregister(AccessLog)
    admin.site.register(AccessLog, IdentifiedAccessLogAdmin)

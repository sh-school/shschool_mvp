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


def install() -> None:
    from axes.admin import AccessLogAdmin
    from axes.models import AccessLog

    class IdentifiedAccessLogAdmin(AccessLogAdmin):
        list_display = (
            "attempt_time",
            "logout_time",
            "ip_address",
            "username",
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

        @admin.display(description="الاسم", ordering="owner_name")
        def owner_name(self, obj: Any) -> str:
            return str(getattr(obj, "owner_name", None) or "—")

        @admin.display(description="الرقم الوظيفي", ordering="owner_employee_number")
        def owner_employee_number(self, obj: Any) -> str:
            return str(getattr(obj, "owner_employee_number", None) or "—")

    if admin.site.is_registered(AccessLog):
        admin.site.unregister(AccessLog)
    admin.site.register(AccessLog, IdentifiedAccessLogAdmin)

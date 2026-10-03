"""عرضا «مركز قيادة الجودة»: الصفحةُ ولقطتُها — كلاهما قراءةُ cache فقط (عقدُ `contract.py`).

صفحةٌ في المنصّة لمطوّرها وحدَه (`developer_only`: مجهولٌ يُحوَّل إلى الدخول وغيرُ المطوّر 403) بجانب خارطة التجويد —
لا في `/admin/` (QCC-01b). وكلُّ مسارٍ جديدٍ هنا يضاف بـ`@developer_only` وتحرسه اختباراتُ `tests/test_command_center.py`.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from command_center import contract, layout, services, status_page, webstats
from core.developer_access import developer_only


@developer_only
@require_GET
@never_cache
def index(request: HttpRequest) -> HttpResponse:
    """الصفحةُ: لوحاتٌ مرسومةٌ من اللقطة الحاليّة، ويُحدّثها `command_center.js` بالاستطلاع."""
    services.ensure_fresh()
    webstats.sample_safe()
    snapshot = contract.snapshot()
    grouped = layout.groups(snapshot["panels"])
    return render(
        request,
        "command_center/index.html",
        {
            "snapshot": snapshot,
            "groups": grouped,
            "cards": layout.cards(grouped),
            "strip": layout.strip(snapshot["panels"]),
            "schema": contract.SCHEMA_VERSION,
        },
    )


@developer_only
@require_GET
@never_cache
def status(request: HttpRequest) -> HttpResponse:
    """حالةُ اليوم للمالك (W-20261002-022): الطابورُ والأحمرُ والتعارضاتُ والنشر من اللقطة — قراءةُ cache فقط."""
    services.ensure_fresh()
    return render(request, "command_center/status.html", {"ctx": status_page.build()})


@developer_only
@require_GET
@never_cache
def snapshot(request: HttpRequest) -> JsonResponse:
    """اللقطةُ JSON — يستطلعها السكربتُ كلَّ 15–60 ثانية؛ لا شيءَ يُحسب هنا (القديمةُ يُطلَق جمعُها في الخلفيّة)."""
    services.ensure_fresh()
    webstats.sample_safe()
    return JsonResponse(contract.snapshot())

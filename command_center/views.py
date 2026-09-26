"""عرضا «مركز قيادة الجودة»: الصفحةُ ولقطتُها — كلاهما قراءةُ cache فقط (عقدُ `contract.py`).

صفحةٌ في المنصّة لمطوّرها وحدَه (`developer_only`: مجهولٌ يُحوَّل إلى الدخول وغيرُ المطوّر 403) بجانب خارطة التجويد —
لا في `/admin/` (QCC-01b). وكلُّ مسارٍ جديدٍ هنا يضاف بـ`@developer_only` وتحرسه اختباراتُ `tests/test_command_center.py`.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from command_center import contract
from core.developer_access import developer_only


@developer_only
@require_GET
@never_cache
def index(request: HttpRequest) -> HttpResponse:
    """الصفحةُ: لوحاتٌ مرسومةٌ من اللقطة الحاليّة، ويُحدّثها `command_center.js` بالاستطلاع."""
    return render(
        request,
        "command_center/index.html",
        {"snapshot": contract.snapshot(), "schema": contract.SCHEMA_VERSION},
    )


@developer_only
@require_GET
@never_cache
def snapshot(request: HttpRequest) -> JsonResponse:
    """اللقطةُ JSON — يستطلعها السكربتُ كلَّ 15–60 ثانية؛ لا شيءَ يُحسب هنا."""
    return JsonResponse(contract.snapshot())

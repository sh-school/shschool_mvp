"""عرضا «مركز قيادة الجودة»: الصفحةُ ولقطتُها — كلاهما قراءةُ cache فقط (عقدُ `contract.py`).

صفحةٌ في المنصّة لمطوّرها وحدَه (`developer_only`: مجهولٌ يُحوَّل إلى الدخول وغيرُ المطوّر 403) بجانب خارطة التجويد —
لا في `/admin/` (QCC-01b). وكلُّ مسارٍ جديدٍ هنا يضاف بـ`@developer_only` وتحرسه اختباراتُ `tests/test_command_center.py`.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from command_center import contract, refresh
from core.developer_access import developer_only

#: تفضيلُ العرض: لوحاتٌ يخفيها المطوّرُ (مفاتيحُ مفصولةٌ بفواصل). كوكيٌّ لا قاعدةٌ: تفضيلُ متصفّحٍ لا بيانٌ، فلا هجرةَ ولا وميضَ عند التحميل
#: (الخادمُ يرسم المخفيَّ مخفيّاً من الطلب الأوّل). والإخفاءُ للعرض وحدَه — التنبيهُ عند الأحمر لا يتأثّر (`alerts.py`).
HIDDEN_COOKIE = "qcc_hidden"


def hidden_keys(request: HttpRequest) -> set[str]:
    """اللوحاتُ المخفيّةُ من الكوكي — يُقبل منها المعروفُ فقط، فلا يُسقط كوكيٌّ عبثيٌّ الصفحة ولا يُطبع نصُّه."""
    known = {panel.key for panel in contract.PANELS}
    return {key for key in request.COOKIES.get(HIDDEN_COOKIE, "").split(",") if key in known}


@developer_only
@require_GET
@never_cache
def index(request: HttpRequest) -> HttpResponse:
    """الصفحةُ: لوحاتٌ مرسومةٌ من اللقطة الحاليّة، ويُحدّثها `command_center.js` بالاستطلاع."""
    refresh.ensure_fresh()
    snapshot = contract.snapshot()
    hidden = hidden_keys(request)
    for panel in snapshot["panels"]:
        panel["hidden"] = panel["key"] in hidden
    return render(
        request,
        "command_center/index.html",
        {
            "snapshot": snapshot,
            "schema": contract.SCHEMA_VERSION,
            "shown": len(snapshot["panels"]) - len(hidden),
            "total": len(snapshot["panels"]),
        },
    )


@developer_only
@require_GET
@never_cache
def snapshot(request: HttpRequest) -> JsonResponse:
    """اللقطةُ JSON — يستطلعها السكربتُ كلَّ 15–60 ثانية؛ لا شيءَ يُحسب هنا (القديمةُ يُطلَق جمعُها في الخلفيّة)."""
    refresh.ensure_fresh()
    return JsonResponse(contract.snapshot())

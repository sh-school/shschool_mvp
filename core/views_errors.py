"""صفحاتُ الأخطاء التي تحتاج منطقًا: فشلُ CSRF بصفحةٍ عربيّة بالهويّة بدل النصّ الخام (W-20261015-018)."""

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.http import url_has_allowed_host_and_scheme

DEFAULT_RELOAD_URL = "/dashboard/"


def _reload_target(request: HttpRequest) -> str:
    """صفحةٌ تُطلب بـGET فتحمل رمزًا جديدًا: المرجعُ من المنصّة نفسِها إن وُجد، وإلا الرئيسيّة.

    الطلبُ الفاشل غالبًا POST بصفحةٍ قديمةٍ استُعيدت بزرّ الرجوع؛ فلا يُعاد إلى مساره نفسِه (قد لا يقبل GET).
    """
    referer: str = str(request.META.get("HTTP_REFERER", ""))
    if referer and url_has_allowed_host_and_scheme(
        referer, allowed_hosts={request.get_host()}, require_https=False
    ):
        return referer
    return DEFAULT_RELOAD_URL


def csrf_failure(request: HttpRequest, reason: str = "") -> HttpResponse:
    """`CSRF_FAILURE_VIEW`: انتهت صلاحيةُ الصفحة (غالبًا بزرّ الرجوع) — بلا تفاصيلَ تقنيّةٍ للمستخدم."""
    return render(
        request, "errors/csrf_failed.html", {"reload_url": _reload_target(request)}, status=403
    )

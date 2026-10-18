"""صفحاتُ الأخطاء التي تحتاج منطقًا: فشلُ CSRF بصفحةٍ عربيّة بالهويّة بدل النصّ الخام (W-20261015-018)."""

from urllib.parse import urlsplit

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

DEFAULT_RELOAD_URL = "/dashboard/"
#: صفحاتُ ما قبل الدخول: لا يُعاد المسجَّلُ إليها (الدخولُ يدوِّر رمزَ CSRF فتبقى نماذجُها القديمةُ بالرجوع بلا صلاحية).
_PRE_LOGIN_PREFIXES = ("/auth/",)


def _same_site_referer(request: HttpRequest) -> str:
    referer: str = str(request.META.get("HTTP_REFERER", ""))
    if referer and url_has_allowed_host_and_scheme(
        referer, allowed_hosts={request.get_host()}, require_https=False
    ):
        return referer
    return ""


def _reload_target(request: HttpRequest) -> str:
    """صفحةٌ تُطلب بـGET فتحمل رمزًا جديدًا: المرجعُ من المنصّة نفسِها إن وُجد، وإلا الرئيسيّة.

    الطلبُ الفاشل غالبًا POST بصفحةٍ قديمةٍ استُعيدت بزرّ الرجوع؛ فلا يُعاد إلى مساره نفسِه (قد لا يقبل GET).
    """
    return _same_site_referer(request) or DEFAULT_RELOAD_URL


def _signed_in_target(request: HttpRequest) -> str:
    """وجهةُ المسجَّل: المرجعُ إن كان صفحةً داخليّةً، وإلا الرئيسيّة (لا عودةَ إلى نماذج الدخول)."""
    referer = _same_site_referer(request)
    if not referer or urlsplit(referer).path.startswith(_PRE_LOGIN_PREFIXES):
        return DEFAULT_RELOAD_URL
    return referer


def _is_page_navigation(request: HttpRequest) -> bool:
    """نموذجُ صفحةٍ يرسله المتصفّح (Accept: text/html) لا استدعاءَ fetch/XHR/HTMX الذي ينتظر رمزَ الحالة."""
    if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.headers.get(
        "hx-request"
    ):
        return False
    return "text/html" in request.headers.get("accept", "")


def csrf_failure(request: HttpRequest, reason: str = "") -> HttpResponse:
    """`CSRF_FAILURE_VIEW`: انتهت صلاحيةُ الصفحة (غالبًا بزرّ الرجوع) — بلا تفاصيلَ تقنيّةٍ للمستخدم.

    المسجَّلُ الذي أرسل نموذجَ صفحةٍ يُعاد إلى صفحته مع تنبيهٍ بأنّ طلبَه لم يُنفَّذ بدل 403 (الدخولُ يدوِّر الرمزَ
    فيُرسل الرجوعُ نموذجًا قديمًا)؛ وطلباتُ fetch/XHR/HTMX وكلُّ ما لا يطلب HTML يبقى 403 فلا يتبع الراجعُ تحويلاً صامتًا؛
    وغيرُ المسجَّل يرى صفحةَ الخطأ بزرّ إعادة التحميل.
    """
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and _is_page_navigation(request):
        messages.warning(request, "انتهت صلاحيةُ الصفحة فلم يُنفَّذ طلبُك. أعِد المحاولة من هذه الصفحة.")
        return redirect(_signed_in_target(request))
    return render(
        request, "errors/csrf_failed.html", {"reload_url": _reload_target(request)}, status=403
    )

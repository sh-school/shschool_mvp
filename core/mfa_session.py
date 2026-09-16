"""core/mfa_session.py — الجلسةُ تحمل دليلَ الرمز، لا يكفي أنّ صاحبها فعّله (P1-4).

كان ``TwoFactorEnforcementMiddleware`` يسأل «هل فعّل الثنائيّة؟» لا «هل أدخل
رمزَها في هذه الجلسة؟». فكلُّ بابٍ يفتح جلسةً بكلمة المرور وحدَها كان يتخطّاها:
``/admin/login/`` أوّلُها — نموذجُ Django يُدخل المديرَ بلا رمز.

فالقاعدة هنا: من عليه الثنائيّة (مفعِّلٌ من الكادر، والرايةُ مشتعلة) لا تُقبل جلستُه
إلّا وفيها ``mfa_verified``، وهذه لا تُكتب إلّا بعد رمزٍ صحيح — في صفحة التحقّق
عند الدخول، أو في صفحة الإعداد لحظةَ التفعيل. وجلسةٌ بلا الدليل تُغلق ويُعاد
صاحبُها إلى باب الدخول الواحد، فيمرّ بالرمز.

والرايةُ المطفأة (التجميد، قرار 2026-09-14) لا تُغلق شيئاً: لا يُسأل أحدٌ عن رمز.
وعند إشعالها تُغلق مرّةً واحدةً جلساتُ المفعِّلين المفتوحةُ قبلها — وهو المقصود.
"""

from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import logout
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

MFA_SESSION_KEY = "mfa_verified"

EXEMPT_PREFIXES = (
    "/auth/",
    "/static/",
    "/media/",
    "/health/",
    "/ready/",
    "/status/",
    "/sw.js",
    "/manifest.json",
    "/offline/",
)


def mark_verified(request) -> None:
    """تُستدعى بعد رمزٍ صحيحٍ وحدَه، وبعد ``login()`` (الذي قد يبدّل الجلسة)."""
    request.session[MFA_SESSION_KEY] = True


def needs_second_factor(user) -> bool:
    if not getattr(settings, "TWO_FACTOR_REQUIRED_FOR_STAFF", True):
        return False
    if not (getattr(user, "is_authenticated", False) and getattr(user, "totp_enabled", False)):
        return False
    from core.views_auth import requires_two_factor

    return requires_two_factor(user)


class MfaSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user is not None
            and not request.path.startswith(EXEMPT_PREFIXES)
            and needs_second_factor(user)
            and not request.session.get(MFA_SESSION_KEY)
        ):
            return self._reject(request)
        return self.get_response(request)

    @staticmethod
    def _reject(request):
        logout(request)
        if request.path.startswith("/api/") or (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
        ):
            return JsonResponse(
                {"error": "يلزم رمز المصادقة الثنائية", "code": "mfa_required"}, status=401
            )
        target = f"{reverse('login')}?{urlencode({'next': request.get_full_path()})}"
        if request.headers.get("HX-Request"):
            response = HttpResponse(status=204)
            response["HX-Redirect"] = target
            return response
        return redirect(target)


def admin_login_redirect(request):
    """دخولُ لوحة الإدارة من الباب الواحد — نموذجُ Django لا يعرف الرمز ولا القفل."""
    next_url = request.GET.get("next") or reverse("admin:index")
    return redirect(f"{reverse('login')}?{urlencode({'next': next_url})}")

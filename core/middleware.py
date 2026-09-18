"""
core/middleware.py
حماية كاملة لكل المسارات — بما فيها /api/
يستخدم Module Registry للمسارات المحمية (v6).
"""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.http.response import HttpResponseBase
from django.shortcuts import redirect
from django.urls import reverse

if TYPE_CHECKING:
    from core.models import School

logger = logging.getLogger(__name__)

EXEMPT = [
    "/auth/",
    "/admin/",
    "/static/",
    "/media/",
    "/health/",
    "/ready/",  # ✅ v5.4: Readiness Probe — عام بدون مصادقة
    # ✅ PWA — يجب أن تكون عامة بدون تسجيل دخول
    "/manifest.json",
    "/sw.js",
    "/offline/",
    # ✅ Prometheus metrics
    "/metrics",
]


def _build_protected_paths() -> dict[str, list[str]]:
    """
    يبني قاموس المسارات المحمية من Module Registry.
    يُستدعى مرة واحدة فقط (lazy singleton).
    """
    from core.module_registry import get_protected_paths

    paths = get_protected_paths()
    if paths:
        logger.debug("Middleware: loaded %d protected paths from registry", len(paths))
    return paths


class SchoolPermissionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self._protected_paths = None  # lazy load

    @property
    def protected_paths(self):
        if self._protected_paths is None:
            self._protected_paths = _build_protected_paths()
        return self._protected_paths

    def __call__(self, request):
        path = request.path

        if any(path.startswith(p) for p in EXEMPT):
            return self.get_response(request)

        if not request.user.is_authenticated:
            if path.startswith("/api/"):
                return JsonResponse(
                    {"error": "مطلوب تسجيل الدخول", "code": "not_authenticated"}, status=401
                )
            return redirect(reverse("login"))

        # ── حساب معطّل — تسجيل خروج فوري ──
        if not request.user.is_active:
            from django.contrib.auth import logout

            logout(request)
            if path.startswith("/api/"):
                return JsonResponse(
                    {"error": "الحساب معطّل", "code": "account_disabled"}, status=403
                )
            return redirect(reverse("login"))

        if request.user.is_superuser:
            return self.get_response(request)

        if not request.user.active_membership:
            if path.startswith("/api/"):
                return JsonResponse(
                    {"error": "لا توجد عضوية نشطة", "code": "no_membership"}, status=403
                )
            return HttpResponseForbidden(
                "<h2 dir='rtl'>ليس لديك عضوية نشطة في أي مدرسة. تواصل مع مدير النظام.</h2>"
            )

        from core.module_registry import gate_admits

        user_role = request.user.get_role()
        for protected_path, allowed_roles in self.protected_paths.items():
            if path.startswith(protected_path):
                # بالدور الحاكم، أو بمنح الوحدة لصفةٍ أخرى (المعلّمُ الذي هو وليُّ أمر).
                if not gate_admits(request.user, protected_path, allowed_roles):
                    from core.permissions import log_denial

                    log_denial(request, role=user_role, required=allowed_roles, source="middleware")
                    if path.startswith("/api/"):
                        return JsonResponse(
                            {"error": "ليس لديك صلاحية للوصول", "code": "forbidden"}, status=403
                        )
                    return HttpResponseForbidden(
                        "<h2 dir='rtl'>ليس لديك صلاحية الوصول لهذه الصفحة</h2>"
                    )
                break

        return self.get_response(request)


# ── مدرسةُ الطلب — تُحسب مرّةً وتُقرأ `request.school` ─────────────────
class SchoolRequest(HttpRequest):
    """طلبٌ يحمل مدرسةَ صاحبه — للأنواع فقط؛ لا يُنشأ."""

    school: "School | None"


class SchoolContextMiddleware:
    """يضع `request.school` = مدرسةَ المستخدم الحاكمة، مرّةً لكلّ طلب.

    كان كلُّ عرضٍ يبدأ بـ`request.user.get_school()` — 248 موضعاً — وكلُّها
    تقرأ العضويّةَ الحاكمة نفسَها. فالقيمةُ تُحسب هنا بعد حارس المسارات
    (الذي حمّل العضويّةَ سلفاً فلا استعلامَ يُضاف) وتُقرأ اسماً واحداً.
    وغيرُ المسجَّل، ومن لا عضويّةَ له، مدرستُه `None` — كما كانت `get_school()`.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponseBase]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        user = getattr(request, "user", None)
        school = user.get_school() if user is not None and user.is_authenticated else None
        cast(SchoolRequest, request).school = school
        return self.get_response(request)


# ── Middleware لحفظ المستخدم الحالي للـ AuditLog ──────────
from contextvars import ContextVar

_current_user: ContextVar = ContextVar("current_user", default=None)
_current_request: ContextVar = ContextVar("current_request", default=None)


def get_current_user():
    return _current_user.get(None)


def get_current_request():
    return _current_request.get(None)


class CurrentUserMiddleware:
    """يُخزّن المستخدم الحالي في Context Variable للـ AuditLog"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token_user = _current_user.set(request.user if request.user.is_authenticated else None)
        token_request = _current_request.set(request)
        try:
            return self.get_response(request)
        finally:
            _current_user.reset(token_user)
            _current_request.reset(token_request)


# ── Sentry Scope — إضافة school_id + role لكل حدث ───────
class SentryScopeMiddleware:
    """
    ✅ v5.5: يُضيف context مخصص لـ Sentry على كل request.
    يجب أن يكون بعد AuthenticationMiddleware في MIDDLEWARE.

    Tags المضافة:
    - user.role: دور المستخدم (admin, teacher, parent, student)
    - school.id: معرف المدرسة
    - school.name: اسم المدرسة (بالإنجليزية)
    - user.authenticated: هل مسجّل الدخول
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            import sentry_sdk

            from core.sentry_config import configure_sentry_scope

            # `configure_scope()` مُهمَلة في sentry-sdk 2 وتُنذر مع كلّ طلب في
            # الاختبارات؛ نطاقُ الطلب الجاري يُؤخذ مباشرةً.
            configure_sentry_scope(sentry_sdk.get_current_scope(), request)
        except ImportError:
            pass  # Sentry not installed — skip silently
        except Exception:
            pass  # Never block requests due to Sentry errors

        return self.get_response(request)


# ── Middleware إلزام تغيير كلمة المرور ─────────────────────
class ForcePasswordChangeMiddleware:
    """من عليه تغييرُ كلمة مروره لا يبلغ صفحةً غيرَ صفحة التغيير.

    كان الإلزامُ عند الدخول وحدَه: `login_view` يحوّل إلى صفحة التغيير، ثمّ
    لا شيءَ يمنع من كتابة `/dashboard/` في الشريط — فتبقى الكلمةُ المؤقّتةُ
    كما هي، ويبقى الإلزامُ رايةً لا تُلزم أحداً.

    وخطرُه أثقلُ حين تكون المؤقّتةُ على نمطٍ معروف (قرارُ 2026-09-13: الرقمُ
    الشخصيُّ بين علامتين). فمن عرف النمطَ ورقمَ زميلٍ دخل باسمه — والإلزامُ
    عند أوّل دخولٍ لا يحمي إلّا إن كان إلزاماً فعلاً: أوّلُ من يدخل يُبدّلها،
    صاحبُها أو غيرُه، ولا يمضي أحدٌ بالمؤقّتة.

    والمستثنى ما لا يقوم التغييرُ إلّا به: الدخولُ والخروجُ وصفحةُ التغيير،
    والملفّاتُ الثابتة، وفحوصُ الصحّة، وعاملُ الخدمة.
    """

    EXEMPT_PREFIXES = (
        "/auth/login/",
        "/auth/logout/",
        "/auth/force_change_password/",
        "/static/",
        "/media/",
        "/health/",
        "/ready/",
        "/status/",
        "/sw.js",
        "/manifest.json",
        "/offline/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and getattr(user, "must_change_password", False)
            and not request.path.startswith(self.EXEMPT_PREFIXES)
        ):
            target = reverse("force_change_password")
            if (
                request.path.startswith("/api/")
                or request.headers.get("X-Requested-With") == "XMLHttpRequest"
            ):
                # طلبٌ في الخلفيّة (عدّادُ الإشعارات كلَّ ثلاثين ثانية) لا تحويلَ له:
                # كان يتبع التحويلَ فيقرأ صفحةَ HTML على أنّها JSON.
                return JsonResponse(
                    {"error": "يجب تغيير كلمة المرور أولاً", "code": "password_change_required"},
                    status=403,
                )
            if request.headers.get("HX-Request"):
                # طلبُ HTMX يُبدّل جزءاً من الصفحة — فالتحويلُ يُطلب من المتصفّح كلِّه.
                response = HttpResponse(status=204)
                response["HX-Redirect"] = target
                return response
            return redirect(target)

        return self.get_response(request)


class TwoFactorEnforcementMiddleware:
    """المنتسبُ الذي لم يفعّل المصادقةَ الثنائيّة لا يبلغ صفحةً غيرَ صفحة إعدادها.

    قرارُ 2026-09-14: الثنائيّةُ لكلّ الكادر لا للقيادة وحدَها. وكانت اختياريّةً
    فعلاً: من لم يفعّلها دخل بكلمة مرورٍ فقط — ومن فعّلها سقط عند التحقّق 500
    (أُصلح في #253). فالإلزامُ هنا على نمط إلزام تغيير كلمة المرور: وسيطٌ لا
    رايةٌ عند الدخول. والطلبةُ وأولياءُ الأمور خارجَه، والمستثنى ما لا يقوم
    الإعدادُ إلّا به. و`TWO_FACTOR_REQUIRED_FOR_STAFF=false` بابُ طوارئ.
    """

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

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _must_set_up(user) -> bool:
        from django.conf import settings

        if not getattr(settings, "TWO_FACTOR_REQUIRED_FOR_STAFF", True):
            return False
        return (
            getattr(user, "is_authenticated", False)
            and not getattr(user, "totp_enabled", False)
            and not getattr(user, "must_change_password", False)
            and user.is_staff_member()
        )

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user is not None
            and not request.path.startswith(self.EXEMPT_PREFIXES)
            and self._must_set_up(user)
        ):
            target = reverse("setup_2fa")
            if (
                request.path.startswith("/api/")
                or request.headers.get("X-Requested-With") == "XMLHttpRequest"
            ):
                return JsonResponse(
                    {"error": "يجب تفعيل المصادقة الثنائية أولاً", "code": "two_factor_required"},
                    status=403,
                )
            if request.headers.get("HX-Request"):
                response = HttpResponse(status=204)
                response["HX-Redirect"] = target
                return response
            return redirect(target)

        return self.get_response(request)


# ── Middleware إجبار ولي الأمر على الموافقة ───────────────
class ParentConsentMiddleware:
    """يُجبر وليَّ الأمر على الموافقة قبل الوصول لأي صفحة (بما فيها API).

    والكادرُ الذي هو وليُّ أمرٍ أيضاً لا يُحجب عن عمله: تظهر له صفحةُ الموافقة عند
    شاشات وليّ الأمر وحدَها. والسياسةُ كلُّها في ``core/parent_consent.py`` — يقرؤها
    هذا الوسيطُ وصلاحيّةُ الـAPI معاً، فلا تفترقان. و``/api/`` ليس مستثنى.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from core.parent_consent import consent_blocks

        if consent_blocks(request.user, request.path):
            if request.path.startswith("/api/"):
                return JsonResponse(
                    {"error": "يجب الموافقة على سياسة البيانات أولاً", "code": "consent_required"},
                    status=403,
                )
            return redirect(reverse("parent_consent"))

        return self.get_response(request)


class PrivateHtmlNoStoreMiddleware:
    """صفحةُ مستخدمٍ مسجَّلٍ لا تُخزَّن في المتصفّح — `Cache-Control: no-store`.

    كانت كلُّ صفحات المنصّة تخرج بلا `Cache-Control` البتّة. وحين لا يجد
    المتصفّحُ توجيهاً ولا مُصادِقاً فله أن يُخزّن ويُعيد من تلقائه. وقد وقع
    فعلاً: نُشر تغييرٌ وبقيت النوافذُ على حالها القديم، حتّى حُدّثت بتجاوز
    الذاكرة (2026-09-12) فظهر الجديد — والخادمُ كان يخدم الأحدثَ طَوالها.

    والأثرُ الثاني أثقل: هذه صفحاتٌ شخصيّة — جدولُ معلّمٍ، سجلُّ طالب، ملفٌّ
    طبّيّ — تبقى على قرص جهازٍ قد يكون مشتركاً بعد الخروج، ويبلغها زرُّ
    الرجوع. و`Vary: Cookie` يمنع الخلطَ بين مستخدمَين ولا يمنع البقاء.

    والنطاقُ ضيّقٌ عمداً: HTML للمسجَّلين وحدَه. فالثابتُ يخدمه WhiteNoise
    ببصمةٍ في اسمه ويجب أن يبقى مخزَّناً، وصفحاتُ الزائر (الدخول، الأخطاء)
    ليست شخصيّةً، ومن ضبط ترويستَه بنفسه (`/health/`) أدرى بصفحته.

    وثمنُه معلوم: `no-store` يُبطل bfcache، فزرُّ الرجوع يُعيد الطلب. وهو
    الثمنُ المتعارَف عليه في تطبيقٍ خلفَ تسجيل دخول.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.has_header("Cache-Control"):
            return response
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return response
        if response.get("Content-Type", "").partition(";")[0].strip() != "text/html":
            return response
        response["Cache-Control"] = "no-store"
        return response

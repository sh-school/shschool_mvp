"""
core/middleware.py
حماية كاملة لكل المسارات — بما فيها /api/
يستخدم Module Registry للمسارات المحمية (v6).
"""

import logging

from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

logger = logging.getLogger(__name__)

EXEMPT = [
    "/auth/",
    "/admin/",
    "/static/",
    "/media/",
    "/health/",
    "/ready/",   # ✅ v5.4: Readiness Probe — عام بدون مصادقة
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

        user_role = request.user.get_role()
        for protected_path, allowed_roles in self.protected_paths.items():
            if path.startswith(protected_path):
                if user_role not in allowed_roles:
                    if path.startswith("/api/"):
                        return JsonResponse(
                            {"error": "ليس لديك صلاحية للوصول", "code": "forbidden"}, status=403
                        )
                    return HttpResponseForbidden(
                        "<h2 dir='rtl'>ليس لديك صلاحية الوصول لهذه الصفحة</h2>"
                    )
                break

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


# ── Middleware إجبار ولي الأمر على الموافقة ───────────────
class ParentConsentMiddleware:
    """يُجبر ولي الأمر على الموافقة قبل الوصول لأي صفحة (بما فيها API)"""

    EXEMPT_PATHS = [
        "/auth/",
        "/parents/consent/",
        "/static/",
        "/media/",
        "/admin/",
        # /api/ لم يعد مستثنى — يجب أن يوافق ولي الأمر حتى عبر API
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and request.user.has_role("parent")
            and request.user.consent_given_at is None
            and not any(request.path.startswith(p) for p in self.EXEMPT_PATHS)
        ):
            if request.path.startswith("/api/"):
                return JsonResponse(
                    {"error": "يجب الموافقة على سياسة البيانات أولاً", "code": "consent_required"},
                    status=403,
                )
            return redirect(reverse("parent_consent"))

        return self.get_response(request)

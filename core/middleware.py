"""
core/middleware.py
حماية كاملة لكل المسارات — بما فيها /api/
"""

from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect

EXEMPT = [
    "/auth/",
    "/admin/",
    "/static/",
    "/media/",
    "/health/",
    # ✅ PWA — يجب أن تكون عامة بدون تسجيل دخول
    "/manifest.json",
    "/sw.js",
    "/offline/",
    # ✅ Prometheus metrics
    "/metrics",
]

PROTECTED_PATHS = {
    "/assessments/": [
        "principal",
        "vice_academic",
        "vice_admin",
        "teacher",
        "coordinator",
        "admin",
    ],
    "/quality/": [
        "principal",
        "vice_admin",
        "vice_academic",
        "coordinator",
        "teacher",
        "specialist",
    ],
    "/analytics/": ["principal", "vice_academic", "vice_admin", "admin"],
    "/clinic/": ["principal", "vice_admin", "nurse"],
    "/transport/": ["principal", "vice_admin", "bus_supervisor"],
    "/library/": [
        "principal",
        "vice_admin",
        "librarian",
        "teacher",
        "coordinator",
        "specialist",
        "student",
    ],
    "/behavior/": [
        "principal",
        "vice_admin",
        "vice_academic",
        "teacher",
        "coordinator",
        "specialist",
    ],
    "/staging/": ["principal", "vice_academic", "vice_admin", "admin"],
    "/quality/evaluations/": [
        "principal",
        "vice_admin",
        "vice_academic",
        "teacher",
        "coordinator",
        "specialist",
        "nurse",
        "librarian",
        "bus_supervisor",
        "admin",
    ],
    "/reports/": ["principal", "vice_academic", "vice_admin", "teacher", "coordinator"],
}


class SchoolPermissionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        if any(path.startswith(p) for p in EXEMPT):
            return self.get_response(request)

        if not request.user.is_authenticated:
            if path.startswith("/api/"):
                return JsonResponse(
                    {"error": "مطلوب تسجيل الدخول", "code": "not_authenticated"}, status=401
                )
            return redirect("/auth/login/")

        if request.user.is_superuser:
            return self.get_response(request)

        if not request.user.memberships.filter(is_active=True).exists():
            if path.startswith("/api/"):
                return JsonResponse(
                    {"error": "لا توجد عضوية نشطة", "code": "no_membership"}, status=403
                )
            return HttpResponseForbidden(
                "<h2 dir='rtl'>ليس لديك عضوية نشطة في أي مدرسة. تواصل مع مدير النظام.</h2>"
            )

        user_role = request.user.get_role()
        for protected_path, allowed_roles in PROTECTED_PATHS.items():
            if path.startswith(protected_path):
                if user_role not in allowed_roles:
                    if path.startswith("/api/"):
                        return JsonResponse(
                            {"error": "ليس لديك صلاحية للوصول", "code": "forbidden"}, status=403
                        )
                    return HttpResponseForbidden(
                        f"<h2 dir='rtl'>ليس لديك صلاحية الوصول. دورك الحالي: {user_role or 'غير محدد'}</h2>"
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
    """يُجبر ولي الأمر على الموافقة قبل الوصول لأي صفحة"""

    EXEMPT_PATHS = [
        "/auth/",
        "/parents/consent/",
        "/static/",
        "/media/",
        "/admin/",
        "/api/",
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
            return redirect("/parents/consent/")

        return self.get_response(request)

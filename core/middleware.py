"""
core/middleware.py
حماية كاملة لكل المسارات — بما فيها /api/
"""
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect

# المسارات المعفاة تماماً (بدون تسجيل دخول)
EXEMPT = ["/auth/", "/admin/", "/static/", "/media/"]

# المسارات المحمية بأدوار محددة
PROTECTED_PATHS = {
    "/assessments/":  ["principal", "vice_academic", "vice_admin", "teacher", "coordinator", "admin"],
    "/quality/":      ["principal", "vice_admin", "vice_academic", "coordinator", "teacher", "specialist"],
    "/analytics/":    ["principal", "vice_academic", "vice_admin", "admin"],
    "/clinic/":       ["principal", "vice_admin", "nurse"],
    "/transport/":    ["principal", "vice_admin", "bus_supervisor"],
    "/library/":      ["principal", "vice_admin", "librarian", "teacher", "coordinator", "specialist", "student"],
    "/behavior/":     ["principal", "vice_admin", "vice_academic", "teacher", "coordinator", "specialist"],
    "/staging/":      ["principal", "vice_academic", "vice_admin", "admin"],
    "/reports/":      ["principal", "vice_academic", "vice_admin", "teacher", "coordinator"],
}


class SchoolPermissionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        # 1. المسارات المعفاة
        if any(path.startswith(p) for p in EXEMPT):
            return self.get_response(request)

        # 2. التحقق من تسجيل الدخول — /api/ يرد JSON لا redirect
        if not request.user.is_authenticated:
            if path.startswith("/api/"):
                return JsonResponse(
                    {"error": "مطلوب تسجيل الدخول", "code": "not_authenticated"},
                    status=401
                )
            return redirect("/auth/login/")

        # 3. المستخدم الخارق يمر مباشرة
        if request.user.is_superuser:
            return self.get_response(request)

        # 4. التحقق من عضوية نشطة
        if not request.user.memberships.filter(is_active=True).exists():
            if path.startswith("/api/"):
                return JsonResponse(
                    {"error": "لا توجد عضوية نشطة", "code": "no_membership"},
                    status=403
                )
            return HttpResponseForbidden(
                "<h2 dir='rtl'>ليس لديك عضوية نشطة في أي مدرسة. تواصل مع مدير النظام.</h2>"
            )

        # 5. التحقق من الصلاحيات لكل مسار محمي
        user_role = request.user.get_role()
        for protected_path, allowed_roles in PROTECTED_PATHS.items():
            if path.startswith(protected_path):
                if user_role not in allowed_roles:
                    if path.startswith("/api/"):
                        return JsonResponse(
                            {"error": "ليس لديك صلاحية للوصول", "code": "forbidden"},
                            status=403
                        )
                    return HttpResponseForbidden(
                        f"<h2 dir='rtl'>ليس لديك صلاحية الوصول. دورك الحالي: {user_role or 'غير محدد'}</h2>"
                    )
                break

        return self.get_response(request)
        
        # ── Middleware لحفظ المستخدم الحالي للـ AuditLog ──────────
from contextvars import ContextVar

_current_user: ContextVar = ContextVar('current_user', default=None)
_current_request: ContextVar = ContextVar('current_request', default=None)


def get_current_user():
    return _current_user.get(None)


def get_current_request():
    return _current_request.get(None)


class CurrentUserMiddleware:
    """يُخزّن المستخدم الحالي في Context Variable للـ AuditLog"""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token_user    = _current_user.set(
            request.user if request.user.is_authenticated else None
        )
        token_request = _current_request.set(request)
        try:
            return self.get_response(request)
        finally:
            _current_user.reset(token_user)
            _current_request.reset(token_request)

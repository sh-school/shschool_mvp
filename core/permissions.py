from functools import wraps

from django.http import HttpResponseForbidden
from django.shortcuts import redirect


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("login")
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            user_role = request.user.get_role()
            if user_role not in roles:
                return HttpResponseForbidden(
                    f"<h2 dir='rtl'>هذه الصفحة تتطلب أحد الأدوار: {', '.join(roles)}</h2>"
                )
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def nurse_required(view_func):
    return role_required("nurse", "principal", "vice_admin")(view_func)


def librarian_required(view_func):
    return role_required("librarian", "principal", "vice_admin")(view_func)


def bus_supervisor_required(view_func):
    return role_required("bus_supervisor", "principal", "vice_admin")(view_func)


def staff_required(view_func):
    return role_required(
        "principal",
        "vice_admin",
        "vice_academic",
        "coordinator",
        "teacher",
        "specialist",
        "nurse",
        "librarian",
        "admin",
    )(view_func)


def internal_only(view_func):
    """يسمح فقط بالوصول من عناوين IP الداخلية — لحماية /metrics و endpoints حساسة."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        from django.conf import settings as _s

        xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
        ip = xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")
        allowed = list(getattr(_s, "METRICS_ALLOWED_IPS", [])) + ["127.0.0.1", "::1"]
        if ip not in allowed:
            return HttpResponseForbidden("Access denied — internal only.")
        return view_func(request, *args, **kwargs)

    return wrapper

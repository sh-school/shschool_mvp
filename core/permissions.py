from functools import wraps
from django.shortcuts import redirect
from django.http import HttpResponseForbidden


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
    return role_required("principal", "vice_admin", "vice_academic", "coordinator", "teacher", "specialist", "nurse", "librarian", "admin")(view_func)

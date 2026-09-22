"""إعادةُ تعيين كلمات مرور المستخدمين — لفنّي تقنية المعلومات وحده.

قرارُ المالك (2026-09-22): لهذا الدور نافذةٌ داخل المنصّة لا `/admin/` — البطاقةُ
الوظيفيّةُ الوزاريّة (`AAdocs/ministry_data/2026_2027/rbac_permissions_matrix.md`)
تنسب حسابات المنصّات التعليميّة لـ«منسّق المشاريع الإلكترونية» لا فنّي تقنية
المعلومات (نطاقُه شبكة/أجهزة)، لكنّ المالك اختار أن يحمل فنّي تقنية المعلومات
هذه المهمّةَ فعلاً — قرارُ مدرسةٍ لا خطأً.

الكتابةُ والقراءةُ في core/services.py (`reset_user_password`، `school_users`) —
هذا الملفُّ إحضارُ سياقٍ وردٌّ لا أكثر.
"""

from __future__ import annotations

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from core.capabilities import capability_required
from core.models.access import Role
from core.services import reset_user_password, school_users

PAGE_SIZE = 25


def _role_label(name: str) -> str:
    """اسمُ الدور بالعربيّة من قائمة الأدوار الرسميّة `Role.ROLES` — لا قاموسٍ محلّيّ ناقص."""
    return dict(Role.ROLES).get(name, name) if name else "—"


@capability_required("it_admin.reset_passwords")
def password_reset_list(request):
    q = request.GET.get("q", "").strip()
    people = school_users(request.school, q)

    paginator = Paginator(people, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))

    rows = [
        {
            "id": user.id,
            "full_name": user.full_name,
            "national_id": user.national_id,
            "role_display": _role_label(user.get_role()),
            "is_active": user.is_active,
        }
        for user in page_obj
    ]

    return render(
        request,
        "core/it_admin/password_reset.html",
        {
            "rows": rows,
            "page_obj": page_obj,
            "total": paginator.count,
            "q": q,
        },
    )


@capability_required("it_admin.reset_passwords")
@require_http_methods(["POST"])
def password_reset_action(request, user_id):
    target, new_password = reset_user_password(
        school=request.school, target_id=user_id, actor=request.user
    )

    messages.success(
        request,
        f"كلمةُ مرورٍ جديدةٌ لـ{target.full_name}: {new_password} — "
        "لن تظهر مرّةً أخرى، انسخها الآن وسلّمها للمستخدم.",
    )
    url = reverse("it_admin_password_reset_list")
    if request.GET.get("q"):
        url += f"?q={request.GET['q']}"
    return redirect(url)

"""إعادةُ تعيين كلمات مرور المستخدمين — لفنّي تقنية المعلومات وحده.

قرارُ المالك (2026-09-22): لهذا الدور نافذةٌ داخل المنصّة لا `/admin/` — البطاقةُ
الوظيفيّةُ الوزاريّة (`AAdocs/ministry_data/2026_2027/rbac_permissions_matrix.md`)
تنسب حسابات المنصّات التعليميّة لـ«منسّق المشاريع الإلكترونية» لا فنّي تقنية
المعلومات (نطاقُه شبكة/أجهزة)، لكنّ المالك اختار أن يحمل فنّي تقنية المعلومات
هذه المهمّةَ فعلاً — قرارُ مدرسةٍ لا خطأً.

كلمةُ المرور الجديدة عشوائيّةٌ (`core.initial_passwords`) لا نصّاً يُدخله
الفنّي: لا حقلَ حرٍّ يفتح باباً لكلمةٍ ضعيفة، والكلمةُ تُعرض **مرّةً واحدةً**
في نفس الاستجابة ولا تُخزَّن نصّاً في أيّ مكان — كما في تدفّق الإصدار الأوّليّ.
"""

from __future__ import annotations

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from core.initial_passwords import make_initial_password
from core.models import AuditLog, CustomUser
from core.models.access import Role
from core.permissions import role_required
from core.privacy import mask_national_id

PAGE_SIZE = 25


def _role_label(name: str) -> str:
    """اسمُ الدور بالعربيّة من قائمة الأدوار الرسميّة `Role.ROLES` — لا قاموسٍ محلّيّ ناقص."""
    return dict(Role.ROLES).get(name, name) if name else "—"


@role_required("it_technician")
def password_reset_list(request):
    school = request.user.get_school()
    people = CustomUser.objects.filter(memberships__school=school).distinct().order_by("full_name")

    q = request.GET.get("q", "").strip()
    if q:
        people = people.search_simple(q)

    paginator = Paginator(people, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))

    rows = [
        {
            "id": user.id,
            "full_name": user.full_name,
            "national_id": mask_national_id(user.national_id),
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


@role_required("it_technician")
@require_http_methods(["POST"])
def password_reset_action(request, user_id):
    school = request.user.get_school()
    target = get_object_or_404(
        CustomUser.objects.filter(memberships__school=school).distinct(), id=user_id
    )

    new_password = make_initial_password()
    with transaction.atomic():
        target.set_password(new_password)
        target.must_change_password = True
        target.save(update_fields=["password", "must_change_password"])
        AuditLog.objects.create(
            school=school,
            user=request.user,
            action="update",
            model_name="CustomUser",
            object_id=str(target.id),
            object_repr=f"إعادة تعيين كلمة مرور: {target.full_name}"[:300],
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

from django.conf import settings
"""
quality/views_executor.py — ربط المنفذين بالإجراءات
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.models import CustomUser, Membership

from .models import ExecutorMapping, OperationalProcedure

_DEFAULT_YEAR = settings.CURRENT_ACADEMIC_YEAR


@login_required
def executor_mapping(request):
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    year = request.GET.get("year", _DEFAULT_YEAR)

    all_executors = (
        OperationalProcedure.objects.filter(school=school, academic_year=year)
        .values("executor_norm")
        .annotate(proc_count=Count("id"))
        .order_by("executor_norm")
    )

    existing_mappings = {
        m.executor_norm: m
        for m in ExecutorMapping.objects.filter(school=school, academic_year=year).select_related(
            "user"
        )
    }

    staff_ids = Membership.objects.filter(school=school, is_active=True).values_list(
        "user_id", flat=True
    )
    all_users = CustomUser.objects.filter(id__in=staff_ids).order_by("full_name")

    executor_rows = []
    for row in all_executors:
        norm = row["executor_norm"]
        mapping = existing_mappings.get(norm)
        mapped_user = mapping.user if mapping else None

        suggested_user = None
        if not mapped_user and norm and norm.split():
            suggested_user = all_users.filter(full_name__icontains=norm.split()[0]).first()

        executor_rows.append(
            {
                "executor_norm": norm,
                "proc_count": row["proc_count"],
                "mapping": mapping,
                "mapped_user": mapped_user,
                "user": mapped_user,
                "is_mapped": mapped_user is not None,
                "suggested_user": suggested_user,
            }
        )

    mapped_count = sum(1 for e in executor_rows if e["is_mapped"])

    return render(
        request,
        "quality/executor_mapping.html",
        {
            "executor_rows": executor_rows,
            "staff": all_users,
            "all_users": all_users,
            "total": len(executor_rows),
            "mapped_count": mapped_count,
            "unmapped_count": len(executor_rows) - mapped_count,
            "year": year,
        },
    )


@login_required
@require_POST
def save_executor_mapping(request):
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    year = request.POST.get("year", _DEFAULT_YEAR)
    executor_norm = request.POST.get("executor_norm", "").strip()
    user_id = request.POST.get("user_id", "").strip()

    if not executor_norm:
        messages.error(request, "المسمى الوظيفي مطلوب")
        return redirect("executor_mapping")

    user = CustomUser.objects.filter(id=user_id).first() if user_id else None
    mapping, _ = ExecutorMapping.objects.update_or_create(
        school=school,
        executor_norm=executor_norm,
        academic_year=year,
        defaults={"user": user},
    )
    mapping.apply_mapping()

    if user:
        proc_count = OperationalProcedure.objects.filter(
            school=school, academic_year=year, executor_norm=executor_norm
        ).count()
        messages.success(
            request, f"✅ تم ربط [{executor_norm}] بـ {user.full_name} — {proc_count} إجراء مُحدَّث"
        )
    else:
        messages.warning(request, f"تم إلغاء ربط [{executor_norm}]")

    return redirect(f"{reverse('executor_mapping')}?year={year}")


@login_required
@require_POST
def apply_all_mappings(request):
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    year = request.POST.get("year", _DEFAULT_YEAR)
    mappings = ExecutorMapping.objects.filter(school=school, academic_year=year, user__isnull=False)
    total = 0
    for m in mappings:
        total += OperationalProcedure.objects.filter(
            school=school, academic_year=year, executor_norm=m.executor_norm
        ).count()
        m.apply_mapping()

    messages.success(request, f"✅ تم تطبيق {mappings.count()} ربط على {total} إجراء")
    return redirect(f"{reverse('executor_mapping')}?year={year}")

"""
staff_affairs/views.py — شؤون الموظفين
8 views — يتبع أنماط المشروع.
"""

from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models.access import Membership
from core.models.user import CustomUser
from core.permissions import role_required
from operations.models import StaffEvaluation, TeacherAbsence, TeacherSwap, CompensatorySession

from .models import LeaveBalance, LeaveRequest

STAFF_AFFAIRS_MANAGE = {"principal", "vice_admin", "vice_academic", "platform_developer"}


# ═══════════════════════════════════════════════════════════════════
# الخطوة 3: لوحة شؤون الموظفين
# ═══════════════════════════════════════════════════════════════════

@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def staff_dashboard(request):
    """لوحة شؤون الموظفين — KPIs + روابط سريعة."""
    school = request.user.get_school()
    today = timezone.localdate()
    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)

    # ── KPIs ──
    total_staff = Membership.objects.filter(
        school=school, is_active=True,
    ).exclude(role__name__in=("student", "parent")).count()

    absences_today = TeacherAbsence.objects.filter(school=school, date=today).count()

    pending_swaps = TeacherSwap.objects.filter(
        school=school, status__in=["pending_b", "pending_coordinator", "pending_vp"],
    ).count()

    pending_leaves = LeaveRequest.objects.filter(school=school, status="pending").count()

    pending_evals = StaffEvaluation.objects.filter(
        school=school, status="draft", academic_year=year,
    ).count()

    # رخص تنتهي خلال 90 يوم
    expiring_licenses = CustomUser.objects.filter(
        memberships__school=school, memberships__is_active=True,
        professional_license_expiry__isnull=False,
        professional_license_expiry__lte=today + timedelta(days=90),
        professional_license_expiry__gt=today,
    ).count()

    # ── توزيع الموظفين حسب الدور ──
    role_distribution = (
        Membership.objects.filter(school=school, is_active=True)
        .exclude(role__name__in=("student", "parent"))
        .values("role__name")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    # ── آخر الغيابات ──
    recent_absences = (
        TeacherAbsence.objects.filter(school=school)
        .select_related("teacher")
        .order_by("-date")[:5]
    )

    # ── آخر طلبات الإجازات ──
    recent_leaves = (
        LeaveRequest.objects.filter(school=school)
        .select_related("staff")
        .order_by("-created_at")[:5]
    )

    # ── ترجمة أسماء الأدوار ──
    ROLE_LABELS = {
        "principal": "مدير", "vice_admin": "نائب إداري", "vice_academic": "نائب أكاديمي",
        "coordinator": "منسق", "admin_supervisor": "مشرف إداري",
        "teacher": "معلم", "ese_teacher": "تربية خاصة", "social_worker": "أخصائي اجتماعي",
        "psychologist": "أخصائي نفسي", "academic_advisor": "مرشد أكاديمي",
        "nurse": "ممرض", "librarian": "أمين مكتبة", "it_technician": "فني تقنية",
        "bus_supervisor": "مشرف نقل", "admin": "إداري", "secretary": "سكرتير",
    }

    return render(request, "staff_affairs/dashboard.html", {
        "today": today,
        "year": year,
        "total_staff": total_staff,
        "absences_today": absences_today,
        "pending_swaps": pending_swaps,
        "pending_leaves": pending_leaves,
        "pending_evals": pending_evals,
        "expiring_licenses": expiring_licenses,
        "role_distribution": role_distribution,
        "role_labels": ROLE_LABELS,
        "recent_absences": recent_absences,
        "recent_leaves": recent_leaves,
    })


# ═══ الخطوة 4: سجل الموظفين ═══

@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def staff_list(request):
    return HttpResponse("<h1 dir='rtl'>سجل الموظفين — قيد البناء</h1>")


# ═══ الخطوة 5: ملف الموظف ═══

@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def staff_profile(request, user_id):
    return HttpResponse("<h1 dir='rtl'>ملف الموظف — قيد البناء</h1>")


# ═══ الخطوة 6: الإجازات ═══

@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def leave_list(request):
    return HttpResponse("<h1 dir='rtl'>طلبات الإجازات — قيد البناء</h1>")


@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def leave_request_create(request):
    return HttpResponse("<h1 dir='rtl'>طلب إجازة — قيد البناء</h1>")


@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def leave_detail(request, pk):
    return HttpResponse("<h1 dir='rtl'>تفاصيل الإجازة — قيد البناء</h1>")


@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def leave_review(request, pk):
    return HttpResponse("<h1 dir='rtl'>مراجعة الإجازة — قيد البناء</h1>")


# ═══ الرخص المهنية ═══

@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def licensing_overview(request):
    return HttpResponse("<h1 dir='rtl'>الرخص المهنية — قيد البناء</h1>")

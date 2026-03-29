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

# ترجمة الأدوار
ROLE_LABELS = {
    "principal": "مدير", "vice_admin": "نائب إداري", "vice_academic": "نائب أكاديمي",
    "coordinator": "منسق", "admin_supervisor": "مشرف إداري",
    "teacher": "معلم", "ese_teacher": "تربية خاصة", "social_worker": "أخصائي اجتماعي",
    "psychologist": "أخصائي نفسي", "academic_advisor": "مرشد أكاديمي",
    "nurse": "ممرض", "librarian": "أمين مكتبة", "it_technician": "فني تقنية",
    "bus_supervisor": "مشرف نقل", "admin": "إداري", "secretary": "سكرتير",
    "specialist": "أخصائي", "platform_developer": "مطور",
}


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
    role_distribution_raw = (
        Membership.objects.filter(school=school, is_active=True)
        .exclude(role__name__in=("student", "parent"))
        .values("role__name")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    role_distribution = [
        {"role_name": r["role__name"], "role_display": ROLE_LABELS.get(r["role__name"], r["role__name"]), "count": r["count"]}
        for r in role_distribution_raw
    ]

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
        "recent_absences": recent_absences,
        "recent_leaves": recent_leaves,
    })


# ═══ الخطوة 4: سجل الموظفين ═══

@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def staff_list(request):
    """سجل الموظفين مع بحث وفلتر حسب الدور والقسم."""
    school = request.user.get_school()

    staff = (
        Membership.objects.filter(school=school, is_active=True)
        .exclude(role__name__in=("student", "parent"))
        .select_related("user", "user__profile", "role", "department_obj")
        .order_by("role__name", "user__full_name")
    )

    # ── فلاتر ──
    q = request.GET.get("q", "").strip()
    role_filter = request.GET.get("role", "")
    dept_filter = request.GET.get("dept", "")

    if q:
        staff = staff.filter(
            Q(user__full_name__icontains=q) | Q(user__national_id__icontains=q)
        )
    if role_filter:
        staff = staff.filter(role__name=role_filter)
    if dept_filter:
        staff = staff.filter(department_obj_id=dept_filter)

    # ── بناء القائمة ──
    staff_rows = []
    for m in staff[:200]:
        staff_rows.append({
            "id": m.user_id,
            "full_name": m.user.full_name,
            "national_id": m.user.national_id,
            "role": m.role.name if m.role else "—",
            "role_display": ROLE_LABELS.get(m.role.name, m.role.name) if m.role else "—",
            "department": m.department_obj.name if m.department_obj else m.department or "—",
            "phone": m.user.phone,
            "email": m.user.email,
            "joined": m.joined_at,
            "license_expiry": m.user.professional_license_expiry,
        })

    # ── خيارات الفلتر ──
    from core.models.access import Role
    available_roles = (
        Role.objects.filter(school=school)
        .exclude(name__in=("student", "parent"))
        .values_list("name", flat=True).distinct().order_by("name")
    )
    from core.models.department import Department
    available_depts = Department.objects.filter(school=school, is_active=True).order_by("name")

    ctx = {
        "staff": staff_rows,
        "total": len(staff_rows),
        "q": q,
        "role_filter": role_filter,
        "dept_filter": dept_filter,
        "roles": [(r, ROLE_LABELS.get(r, r)) for r in available_roles],
        "departments": available_depts,
    }

    if request.headers.get("HX-Request"):
        return render(request, "staff_affairs/_staff_table.html", ctx)

    return render(request, "staff_affairs/staff_list.html", ctx)



# ═══ الخطوة 5: ملف الموظف ═══

@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def staff_profile(request, user_id):
    """ملف الموظف الشامل — بيانات + غياب + تقييم + إجازات + رخصة."""
    school = request.user.get_school()
    user = get_object_or_404(
        CustomUser, id=user_id,
        memberships__school=school, memberships__is_active=True,
    )
    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)

    membership = Membership.objects.filter(
        user=user, school=school, is_active=True,
    ).select_related("role", "department_obj").first()

    profile = getattr(user, "profile", None)

    # ── الغياب ──
    absences = (
        TeacherAbsence.objects.filter(teacher=user, school=school)
        .order_by("-date")
    )
    absence_count = absences.count()
    absences_recent = absences[:10]

    # ── التبديلات ──
    swaps = TeacherSwap.objects.filter(
        Q(teacher_a=user) | Q(teacher_b=user), school=school,
    ).count()

    # ── التعويضات ──
    compensatory = CompensatorySession.objects.filter(
        teacher=user, school=school,
    ).count()

    # ── التقييم ──
    evaluations = (
        StaffEvaluation.objects.filter(staff=user, school=school)
        .order_by("-academic_year")[:5]
    )

    # ── الإجازات ──
    leaves = (
        LeaveRequest.objects.filter(staff=user, school=school)
        .order_by("-created_at")[:10]
    )
    leave_balances = LeaveBalance.objects.filter(
        staff=user, school=school, academic_year=year,
    )

    # ── الحصص (أعباء) ──
    from operations.models import ScheduleSlot
    weekly_slots = ScheduleSlot.objects.filter(
        teacher=user, school=school, is_active=True,
    ).count()

    role_display = ROLE_LABELS.get(membership.role.name, membership.role.name) if membership and membership.role else "—"

    return render(request, "staff_affairs/staff_profile.html", {
        "staff_user": user,
        "membership": membership,
        "profile": profile,
        "year": year,
        "role_display": role_display,
        "absence_count": absence_count,
        "absences_recent": absences_recent,
        "swaps_count": swaps,
        "compensatory_count": compensatory,
        "evaluations": evaluations,
        "leaves": leaves,
        "leave_balances": leave_balances,
        "weekly_slots": weekly_slots,
        "today": timezone.localdate(),
    })


# ═══ الخطوة 6: الإجازات ═══

@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def leave_list(request):
    """قائمة طلبات الإجازات مع فلتر."""
    school = request.user.get_school()
    leaves = LeaveRequest.objects.filter(school=school).select_related("staff").order_by("-created_at")

    status_filter = request.GET.get("status", "")
    type_filter = request.GET.get("type", "")
    if status_filter:
        leaves = leaves.filter(status=status_filter)
    if type_filter:
        leaves = leaves.filter(leave_type=type_filter)

    from .models import LEAVE_TYPES, LEAVE_STATUS
    return render(request, "staff_affairs/leave_list.html", {
        "leaves": leaves[:100],
        "status_filter": status_filter,
        "type_filter": type_filter,
        "status_choices": LEAVE_STATUS,
        "type_choices": LEAVE_TYPES,
    })


@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def leave_request_create(request):
    """تقديم طلب إجازة جديد."""
    school = request.user.get_school()
    from .forms import LeaveRequestForm

    if request.method == "POST":
        form = LeaveRequestForm(request.POST, request.FILES)
        if form.is_valid():
            cd = form.cleaned_data
            staff = get_object_or_404(
                CustomUser, id=cd["staff_id"],
                memberships__school=school, memberships__is_active=True,
            )
            LeaveRequest.objects.create(
                school=school,
                staff=staff,
                leave_type=cd["leave_type"],
                start_date=cd["start_date"],
                end_date=cd["end_date"],
                days_count=cd["days_count"],
                reason=cd["reason"],
                attachment=cd.get("attachment"),
                academic_year=settings.CURRENT_ACADEMIC_YEAR,
                created_by=request.user,
                updated_by=request.user,
            )
            messages.success(request, f"تم تقديم طلب إجازة {staff.full_name} ({cd['days_count']} يوم).")
            return redirect("staff_affairs:leave_list")
    else:
        form = LeaveRequestForm()

    staff_members = (
        Membership.objects.filter(school=school, is_active=True)
        .exclude(role__name__in=("student", "parent"))
        .select_related("user").order_by("user__full_name")
    )
    return render(request, "staff_affairs/leave_form.html", {
        "form": form, "staff_members": staff_members,
    })


@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def leave_detail(request, pk):
    """تفاصيل طلب إجازة."""
    school = request.user.get_school()
    leave = get_object_or_404(LeaveRequest, pk=pk, school=school)
    return render(request, "staff_affairs/leave_detail.html", {"leave": leave})


@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
@require_POST
def leave_review(request, pk):
    """مراجعة طلب إجازة — موافقة أو رفض."""
    school = request.user.get_school()
    leave = get_object_or_404(LeaveRequest, pk=pk, school=school)

    from .forms import LeaveReviewForm
    form = LeaveReviewForm(request.POST)
    if form.is_valid():
        action = form.cleaned_data["action"]
        leave.status = action
        leave.reviewed_by = request.user
        leave.reviewed_at = timezone.now()
        if action == "rejected":
            leave.rejection_reason = form.cleaned_data.get("rejection_reason", "")
        leave.updated_by = request.user
        leave.save()

        # تحديث الرصيد عند الموافقة
        if action == "approved":
            balance, created = LeaveBalance.objects.get_or_create(
                school=school, staff=leave.staff,
                academic_year=leave.academic_year, leave_type=leave.leave_type,
                defaults={"total_days": 30},
            )
            balance.used_days += leave.days_count
            balance.save()

        status_label = "موافق عليها" if action == "approved" else "مرفوضة"
        messages.success(request, f"تم تحديث طلب الإجازة إلى: {status_label}")

    return redirect("staff_affairs:leave_detail", pk=pk)


# ═══════════════════════════════════════════════════════════════════
# الرخص المهنية
# ═══════════════════════════════════════════════════════════════════

@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def licensing_overview(request):
    """نظرة شاملة على الرخص المهنية — منتهية / تنتهي قريباً / سارية."""
    school = request.user.get_school()
    today = timezone.localdate()

    staff_with_license = (
        CustomUser.objects.filter(
            memberships__school=school, memberships__is_active=True,
            professional_license_number__isnull=False,
        ).exclude(professional_license_number="")
        .order_by("professional_license_expiry")
    )

    expired = [u for u in staff_with_license if u.professional_license_expiry and u.professional_license_expiry < today]
    expiring_soon = [u for u in staff_with_license if u.professional_license_expiry and today <= u.professional_license_expiry <= today + timedelta(days=90)]
    valid = [u for u in staff_with_license if u.professional_license_expiry and u.professional_license_expiry > today + timedelta(days=90)]

    no_license = (
        Membership.objects.filter(school=school, is_active=True, role__name__in=("teacher", "coordinator", "ese_teacher"))
        .select_related("user")
        .filter(Q(user__professional_license_number__isnull=True) | Q(user__professional_license_number=""))
    )

    return render(request, "staff_affairs/licensing.html", {
        "expired": expired,
        "expiring_soon": expiring_soon,
        "valid": valid,
        "no_license": no_license,
        "today": today,
    })

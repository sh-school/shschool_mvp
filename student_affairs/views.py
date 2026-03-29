"""
student_affairs/views.py — شؤون الطلاب
16 view — يتبع أنماط المشروع الموجودة بالضبط.
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from behavior.models import BehaviorInfraction
from clinic.models import ClinicVisit
from core.models.access import Membership, Role
from core.models.academic import ClassGroup, ParentStudentLink, StudentEnrollment
from core.models.user import CustomUser, Profile
from core.permissions import role_required
from operations.models import StudentAttendance

from .models import StudentActivity, StudentTransfer

# الأدوار المسموح لها بالوصول لشؤون الطلاب
STUDENT_AFFAIRS_MANAGE = {"principal", "vice_admin", "vice_academic", "platform_developer"}
STUDENT_DEACTIVATE = {"principal", "vice_admin", "platform_developer"}


# ═════════════════════════════════════════════════════════════════════
# لوحة شؤون الطلاب — الخطوة 3
# ═════════════════════════════════════════════════════════════════════


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def student_dashboard(request):
    """لوحة شؤون الطلاب — KPIs + روابط سريعة + ملخصات."""
    school = request.user.get_school()
    today = timezone.localdate()
    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)

    # ── KPIs الأساسية ──
    total_students = Membership.objects.filter(
        school=school, role__name="student", is_active=True,
    ).count()

    # حضور اليوم
    today_sessions = StudentAttendance.objects.filter(
        school=school, session__date=today,
    )
    absent_today = today_sessions.filter(status="absent").count()
    late_today = today_sessions.filter(status="late").count()
    present_today = today_sessions.filter(status="present").count()

    # سلوك الشهر
    behavior_month = BehaviorInfraction.objects.filter(
        school=school,
        date__year=today.year,
        date__month=today.month,
    ).count()

    # عيادة اليوم
    clinic_today = ClinicVisit.objects.filter(
        school=school, visit_date__date=today,
    ).count()

    # انتقالات معلقة
    pending_transfers = StudentTransfer.objects.filter(
        school=school, status="pending",
    ).count()

    # ── KPIs ثانوية ──
    # توزيع الطلاب حسب الصف
    grade_distribution = (
        StudentEnrollment.objects.filter(
            class_group__school=school,
            class_group__academic_year=year,
            is_active=True,
        )
        .values("class_group__grade")
        .annotate(count=Count("id"))
        .order_by("class_group__grade")
    )

    # أولياء أمور مرتبطون
    linked_parents = ParentStudentLink.objects.filter(school=school).count()

    # أنشطة هذا العام
    activities_year = StudentActivity.objects.filter(
        school=school, academic_year=year,
    ).count()

    # ── آخر المخالفات (5) ──
    recent_infractions = (
        BehaviorInfraction.objects.filter(school=school)
        .select_related("student", "violation_category")
        .order_by("-date")[:5]
    )

    # ── آخر الانتقالات (5) ──
    recent_transfers = (
        StudentTransfer.objects.filter(school=school)
        .select_related("student")
        .order_by("-created_at")[:5]
    )

    return render(request, "student_affairs/dashboard.html", {
        "today": today,
        "year": year,
        "total_students": total_students,
        "absent_today": absent_today,
        "late_today": late_today,
        "present_today": present_today,
        "behavior_month": behavior_month,
        "clinic_today": clinic_today,
        "pending_transfers": pending_transfers,
        "grade_distribution": grade_distribution,
        "linked_parents": linked_parents,
        "activities_year": activities_year,
        "recent_infractions": recent_infractions,
        "recent_transfers": recent_transfers,
    })


# ═════════════════════════════════════════════════════════════════════
# سجل الطلاب — الخطوة 4
# ═════════════════════════════════════════════════════════════════════


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def student_list(request):
    """قائمة الطلاب مع بحث وفلتر."""
    return HttpResponse("<h1 dir='rtl'>سجل الطلاب — قيد البناء</h1>", status=200)


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def student_table_partial(request):
    """HTMX partial — جدول الطلاب للبحث المباشر."""
    return HttpResponse("", status=200)


# ═════════════════════════════════════════════════════════════════════
# إضافة / تعديل / تعطيل — الخطوات 5 + 7
# ═════════════════════════════════════════════════════════════════════


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def student_add(request):
    """إضافة طالب جديد — ينشئ 4 سجلات ذرّياً."""
    return HttpResponse("<h1 dir='rtl'>إضافة طالب — قيد البناء</h1>", status=200)


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def student_edit(request, student_id):
    """تعديل بيانات طالب."""
    return HttpResponse("<h1 dir='rtl'>تعديل طالب — قيد البناء</h1>", status=200)


@login_required
@role_required(STUDENT_DEACTIVATE)
def student_deactivate(request, student_id):
    """تعطيل طالب — is_active=False فقط، لا حذف."""
    return HttpResponse("<h1 dir='rtl'>تعطيل طالب — قيد البناء</h1>", status=200)


# ═════════════════════════════════════════════════════════════════════
# ملف الطالب الشامل — الخطوة 6
# ═════════════════════════════════════════════════════════════════════


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def student_profile(request, student_id):
    """ملف الطالب الشامل — يجمع بيانات من 7 تطبيقات."""
    return HttpResponse("<h1 dir='rtl'>ملف الطالب — قيد البناء</h1>", status=200)


# ═════════════════════════════════════════════════════════════════════
# الانتقالات — الخطوة 8
# ═════════════════════════════════════════════════════════════════════


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def transfer_list(request):
    """قائمة الانتقالات."""
    return HttpResponse("<h1 dir='rtl'>الانتقالات — قيد البناء</h1>", status=200)


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def transfer_create(request):
    """تسجيل طلب انتقال جديد."""
    return HttpResponse("<h1 dir='rtl'>طلب انتقال — قيد البناء</h1>", status=200)


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def transfer_detail(request, pk):
    """تفاصيل طلب انتقال."""
    return HttpResponse("<h1 dir='rtl'>تفاصيل الانتقال — قيد البناء</h1>", status=200)


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def transfer_review(request, pk):
    """مراجعة طلب انتقال — موافقة أو رفض."""
    return HttpResponse("<h1 dir='rtl'>مراجعة الانتقال — قيد البناء</h1>", status=200)


# ═════════════════════════════════════════════════════════════════════
# الحضور والسلوك (ملخصات)
# ═════════════════════════════════════════════════════════════════════


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def attendance_overview(request):
    """ملخص الحضور والغياب — يقرأ من operations."""
    return HttpResponse("<h1 dir='rtl'>ملخص الحضور — قيد البناء</h1>", status=200)


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def behavior_overview(request):
    """ملخص السلوك — يقرأ من behavior."""
    return HttpResponse("<h1 dir='rtl'>ملخص السلوك — قيد البناء</h1>", status=200)


# ═════════════════════════════════════════════════════════════════════
# الأنشطة والإنجازات — الخطوة 9
# ═════════════════════════════════════════════════════════════════════


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def activity_list(request):
    """قائمة الأنشطة والإنجازات."""
    return HttpResponse("<h1 dir='rtl'>الأنشطة — قيد البناء</h1>", status=200)


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def activity_add(request):
    """تسجيل نشاط أو إنجاز جديد."""
    return HttpResponse("<h1 dir='rtl'>إضافة نشاط — قيد البناء</h1>", status=200)


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def activity_edit(request, pk):
    """تعديل نشاط."""
    return HttpResponse("<h1 dir='rtl'>تعديل نشاط — قيد البناء</h1>", status=200)


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def activity_delete(request, pk):
    """حذف نشاط."""
    return HttpResponse("<h1 dir='rtl'>حذف نشاط — قيد البناء</h1>", status=200)

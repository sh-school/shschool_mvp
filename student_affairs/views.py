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
    """قائمة الطلاب مع بحث وفلتر حسب الصف والشعبة."""
    school = request.user.get_school()
    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)

    # ── الاستعلام الأساسي: طلاب فعّالون في المدرسة ──
    students = (
        Membership.objects.filter(
            school=school, role__name="student", is_active=True,
        )
        .select_related("user", "user__profile")
        .order_by("user__full_name")
    )

    # ── إرفاق بيانات التسجيل (الصف + الشعبة) ──
    # نبني dict سريع: user_id → enrollment
    student_ids = list(students.values_list("user_id", flat=True))
    enrollments = {
        e["student_id"]: e
        for e in StudentEnrollment.objects.filter(
            student_id__in=student_ids,
            class_group__academic_year=year,
            is_active=True,
        )
        .select_related("class_group")
        .values(
            "student_id",
            "class_group__grade",
            "class_group__section",
            "class_group_id",
        )
    }

    # ── الفلاتر ──
    q = request.GET.get("q", "").strip()
    grade_filter = request.GET.get("grade", "")
    section_filter = request.GET.get("section", "")

    if q:
        students = students.filter(
            Q(user__full_name__icontains=q) | Q(user__national_id__icontains=q)
        )

    if grade_filter:
        enrolled_ids = StudentEnrollment.objects.filter(
            class_group__school=school,
            class_group__academic_year=year,
            class_group__grade=grade_filter,
            is_active=True,
        ).values_list("student_id", flat=True)
        students = students.filter(user_id__in=enrolled_ids)

    if section_filter:
        enrolled_ids = StudentEnrollment.objects.filter(
            class_group__school=school,
            class_group__academic_year=year,
            class_group__section=section_filter,
            is_active=True,
        ).values_list("student_id", flat=True)
        students = students.filter(user_id__in=enrolled_ids)

    # ── بناء القائمة مع بيانات التسجيل ──
    student_rows = []
    for m in students[:200]:
        enr = enrollments.get(m.user_id, {})
        student_rows.append({
            "id": m.user_id,
            "full_name": m.user.full_name,
            "national_id": m.user.national_id,
            "phone": m.user.phone,
            "email": m.user.email,
            "gender": getattr(m.user, "profile", None) and m.user.profile.gender or "",
            "grade": enr.get("class_group__grade", "—"),
            "section": enr.get("class_group__section", "—"),
        })

    # ── خيارات الفلتر ──
    available_grades = (
        ClassGroup.objects.filter(school=school, academic_year=year, is_active=True)
        .values_list("grade", flat=True)
        .distinct()
        .order_by("grade")
    )
    available_sections = (
        ClassGroup.objects.filter(school=school, academic_year=year, is_active=True)
        .values_list("section", flat=True)
        .distinct()
        .order_by("section")
    )

    ctx = {
        "students": student_rows,
        "total": len(student_rows),
        "q": q,
        "grade_filter": grade_filter,
        "section_filter": section_filter,
        "grades": available_grades,
        "sections": available_sections,
        "year": year,
    }

    # HTMX: إرجاع الجدول فقط
    if request.headers.get("HX-Request"):
        return render(request, "student_affairs/_student_table.html", ctx)

    return render(request, "student_affairs/student_list.html", ctx)


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def student_table_partial(request):
    """HTMX partial — يُعيد التوجيه لـ student_list مع نفس المعاملات."""
    return student_list(request)


# ═════════════════════════════════════════════════════════════════════
# إضافة / تعديل / تعطيل — الخطوات 5 + 7
# ═════════════════════════════════════════════════════════════════════


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def student_add(request):
    """إضافة طالب جديد — ينشئ 4 سجلات ذرّياً (User + Profile + Membership + Enrollment)."""
    school = request.user.get_school()
    year = settings.CURRENT_ACADEMIC_YEAR

    from .forms import StudentAddForm

    if request.method == "POST":
        form = StudentAddForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            # ── التحقق من عدم وجود طالب بنفس الرقم الوطني ──
            if CustomUser.objects.filter(national_id=cd["national_id"]).exists():
                messages.error(request, f"يوجد مستخدم بالرقم الوطني {cd['national_id']} مسبقاً.")
                return render(request, "student_affairs/student_form.html", {
                    "form": form, "mode": "add", "year": year,
                    "grades": ClassGroup.GRADES, "school": school,
                })

            # ── التحقق من وجود الشعبة ──
            class_group = ClassGroup.objects.filter(
                school=school, grade=cd["grade"], section=cd["section"],
                academic_year=year, is_active=True,
            ).first()
            if not class_group:
                messages.error(
                    request,
                    f"لا توجد شعبة {cd['section']} في الصف {cd['grade']} للعام {year}.",
                )
                return render(request, "student_affairs/student_form.html", {
                    "form": form, "mode": "add", "year": year,
                    "grades": ClassGroup.GRADES, "school": school,
                })

            # ── إنشاء 4 سجلات ذرّياً ──
            from django.db import transaction

            try:
                with transaction.atomic():
                    # 1. CustomUser
                    user = CustomUser.objects.create_user(
                        national_id=cd["national_id"],
                        password=cd["national_id"],  # كلمة المرور = الرقم الوطني
                        full_name=cd["full_name"],
                        phone=cd.get("phone", ""),
                        email=cd.get("email", ""),
                        must_change_password=True,
                    )
                    # 2. Profile
                    Profile.objects.update_or_create(
                        user=user,
                        defaults={
                            "gender": cd.get("gender", ""),
                            "birth_date": cd.get("birth_date"),
                        },
                    )
                    # 3. Membership
                    student_role, _ = Role.objects.get_or_create(
                        school=school, name="student",
                    )
                    Membership.objects.create(
                        user=user, school=school, role=student_role, is_active=True,
                    )
                    # 4. StudentEnrollment
                    StudentEnrollment.objects.create(
                        student=user, class_group=class_group, is_active=True,
                    )

                messages.success(
                    request,
                    f"تم إضافة الطالب {user.full_name} في {class_group.grade}/{class_group.section} بنجاح.",
                )
                return redirect("student_affairs:student_profile", student_id=user.id)

            except Exception as e:
                messages.error(request, f"خطأ أثناء إضافة الطالب: {e}")
    else:
        form = StudentAddForm()

    return render(request, "student_affairs/student_form.html", {
        "form": form,
        "mode": "add",
        "year": year,
        "grades": ClassGroup.GRADES,
        "school": school,
    })


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
    school = request.user.get_school()
    student = get_object_or_404(
        CustomUser, id=student_id,
        memberships__school=school, memberships__is_active=True,
    )
    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)

    # ── 1. البيانات الشخصية (core) ──
    profile = getattr(student, "profile", None)
    enrollment = (
        StudentEnrollment.objects.filter(
            student=student, class_group__academic_year=year, is_active=True,
        )
        .select_related("class_group")
        .first()
    )
    parent_links = ParentStudentLink.objects.filter(
        student=student, school=school,
    ).select_related("parent")

    # ── 2. الحضور (operations) ──
    attendance_qs = StudentAttendance.objects.filter(
        student=student, school=school, session__date__year=timezone.localdate().year,
    )
    attendance_summary = {
        "present": attendance_qs.filter(status="present").count(),
        "absent": attendance_qs.filter(status="absent").count(),
        "late": attendance_qs.filter(status="late").count(),
        "excused": attendance_qs.filter(status="excused").count(),
        "total": attendance_qs.count(),
    }
    if attendance_summary["total"] > 0:
        attendance_summary["pct"] = round(
            attendance_summary["present"] / attendance_summary["total"] * 100, 1
        )
    else:
        attendance_summary["pct"] = 0

    # ── 3. السلوك (behavior) ──
    infractions = (
        BehaviorInfraction.objects.filter(student=student, school=school)
        .select_related("violation_category")
        .order_by("-date")
    )
    behavior_summary = {
        "total": infractions.count(),
        "by_level": {
            lvl: infractions.filter(level=lvl).count() for lvl in range(1, 5)
        },
        "recent": infractions[:5],
    }
    # نقاط السلوك
    from django.db.models import Sum
    from behavior.models import BehaviorPointRecovery

    total_deducted = infractions.aggregate(s=Sum("points_deducted"))["s"] or 0
    total_restored = (
        BehaviorPointRecovery.objects.filter(
            infraction__student=student, infraction__school=school,
        ).aggregate(s=Sum("points_restored"))["s"] or 0
    )
    behavior_summary["net_score"] = max(0, 100 - total_deducted + total_restored)
    behavior_summary["total_deducted"] = total_deducted
    behavior_summary["total_restored"] = total_restored

    # ── 4. العيادة (clinic) ──
    from clinic.models import HealthRecord

    clinic_visits = (
        ClinicVisit.objects.filter(student=student, school=school)
        .order_by("-visit_date")[:5]
    )
    health_record = HealthRecord.objects.filter(student=student).first()

    # ── 5. الدرجات (assessments) ──
    from assessments.models import AnnualSubjectResult

    grades = (
        AnnualSubjectResult.objects.filter(
            student=student, school=school, academic_year=year,
        )
        .select_related("subject", "class_group")
        .order_by("subject__name_ar")
    )
    grades_summary = grades.aggregate(
        total_subjects=Count("id"),
        passed=Count("id", filter=Q(status="pass")),
        failed=Count("id", filter=Q(status="fail")),
    )

    # ── 6. المكتبة (library) ──
    from library.models import BookBorrowing

    borrowings = (
        BookBorrowing.objects.filter(user=student)
        .select_related("book")
        .order_by("-borrow_date")[:5]
    )

    # ── 7. الأنشطة (student_affairs) ──
    activities = (
        StudentActivity.objects.filter(student=student, school=school)
        .order_by("-date")[:10]
    )

    # ── الانتقالات ──
    transfers = (
        StudentTransfer.objects.filter(student=student, school=school)
        .order_by("-created_at")[:5]
    )

    return render(request, "student_affairs/student_profile.html", {
        "student": student,
        "profile": profile,
        "enrollment": enrollment,
        "parent_links": parent_links,
        "attendance": attendance_summary,
        "behavior": behavior_summary,
        "clinic_visits": clinic_visits,
        "health_record": health_record,
        "grades": grades,
        "grades_summary": grades_summary,
        "borrowings": borrowings,
        "activities": activities,
        "transfers": transfers,
        "year": year,
    })


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

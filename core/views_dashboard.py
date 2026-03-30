import datetime

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import cache_page

from assessments.models import AnnualSubjectResult, SubjectClassSetup
from behavior.models import BehaviorInfraction
from clinic.models import ClinicVisit
from core.permissions import role_required
from core.models.access import ALL_STAFF_ROLES
from library.models import BookBorrowing
from operations.models import (
    AbsenceAlert,
    CompensatorySession,
    ScheduleSlot,
    Session,
    StudentAttendance,
    TeacherAbsence,
    TeacherSwap,
)
from operations.services import ScheduleService


@login_required
@role_required(ALL_STAFF_ROLES | {"student", "parent"})
def dashboard(request):
    """لوحة التحكم الرئيسية — تعرض إحصائيات مختلفة حسب دور المستخدم."""
    user = request.user
    school = user.get_school()
    role = user.get_role()

    if not school:
        return HttpResponseForbidden("<h2 dir='rtl'>لم يتم تعيينك في أي مدرسة</h2>")

    today = timezone.now().date()
    ctx = {"today": today, "school": school}

    # ── التوليد التلقائي: Middleware يضمن حصص الأسبوع ──
    # (لا حاجة لاستدعاء يدوي — الـ middleware يغطي هذا تلقائياً)

    # ولي الأمر → بوابته مباشرة
    if role == "parent":
        return redirect("parent_dashboard")

    # الطالب → لوحته المختصرة
    if role == "student":
        year = settings.CURRENT_ACADEMIC_YEAR
        # حضور الطالب
        student_att_stats = StudentAttendance.objects.filter(
            school=school, student=user
        ).aggregate(
            present=Count("id", filter=Q(status="present")),
            absent=Count("id", filter=Q(status="absent")),
            late=Count("id", filter=Q(status="late")),
        )
        student_present = student_att_stats["present"]
        student_absent = student_att_stats["absent"]
        student_late = student_att_stats["late"]
        student_total = student_present + student_absent + student_late
        student_att_pct = round(student_present / student_total * 100) if student_total else 100
        # حصص اليوم
        from core.models import StudentEnrollment
        enrollment = StudentEnrollment.objects.filter(student=user, is_active=True).select_related("class_group").first()
        student_sessions = []
        if enrollment and enrollment.class_group:
            student_sessions = (
                Session.objects.filter(school=school, class_group=enrollment.class_group, date=today)
                .select_related("subject", "teacher")
                .order_by("start_time")
            )
        # نتائج الطالب السنوية
        student_results = AnnualSubjectResult.objects.filter(
            student=user, school=school, academic_year=year
        )
        student_subjects_total = student_results.count()
        student_passed = student_results.filter(status='pass').count()
        student_failed = student_results.filter(status='fail').count()

        ctx.update({
            "view_type": "student",
            "student_att_pct": student_att_pct,
            "student_present": student_present,
            "student_absent": student_absent,
            "student_late": student_late,
            "student_sessions": student_sessions,
            "class_group": enrollment.class_group if enrollment else None,
            "student_subjects_total": student_subjects_total,
            "student_passed": student_passed,
            "student_failed": student_failed,
        })
        return render(request, "dashboard/main.html", ctx)

    if user.is_superuser or role in ("principal", "vice_admin", "vice_academic", "admin"):
        year = settings.CURRENT_ACADEMIC_YEAR

        sessions_today = Session.objects.filter(school=school, date=today).select_related("teacher")
        # دمج 3 queries في واحدة
        session_stats = sessions_today.aggregate(
            total=Count("id"),
            completed=Count("id", filter=Q(status="completed")),
            in_progress=Count("id", filter=Q(status="in_progress")),
        )
        total_sessions = session_stats["total"]
        completed = session_stats["completed"]
        in_progress = session_stats["in_progress"]

        att_stats = StudentAttendance.objects.filter(
            school=school, session__date=today
        ).aggregate(
            present=Count("id", filter=Q(status="present")),
            absent=Count("id", filter=Q(status="absent")),
            late=Count("id", filter=Q(status="late")),
        )
        present = att_stats["present"]
        absent = att_stats["absent"]
        late = att_stats["late"]
        total_att = present + absent + late
        att_pct = round(present / total_att * 100) if total_att else 0

        # بيانات الأمس للمقارنة (delta) — query واحدة بدل 3
        yesterday = today - datetime.timedelta(days=1)
        att_y_stats = StudentAttendance.objects.filter(
            school=school, session__date=yesterday
        ).aggregate(
            present_y=Count("id", filter=Q(status="present")),
            absent_y=Count("id", filter=Q(status="absent")),
            late_y=Count("id", filter=Q(status="late")),
        )
        present_y = att_y_stats["present_y"]
        absent_y = att_y_stats["absent_y"]
        total_y = present_y + absent_y + att_y_stats["late_y"]
        att_pct_y = round(present_y / total_y * 100) if total_y else None
        att_delta = att_pct - att_pct_y if att_pct_y is not None else None
        absent_delta = absent - absent_y if total_y else None

        alerts = (
            AbsenceAlert.objects.filter(school=school, status="pending")
            .select_related("student")
            .order_by("-created_at")[:5]
        )

        # إحصائيات التقييمات — aggregate واحد بدل 4 queries
        annual_stats = AnnualSubjectResult.objects.filter(
            school=school, academic_year=year
        ).aggregate(
            total=Count("id"),
            passed=Count("id", filter=Q(status="pass")),
            failed=Count("id", filter=Q(status="fail")),
        )
        total_annual = annual_stats["total"]
        passed_annual = annual_stats["passed"]
        failed_annual = annual_stats["failed"]
        pass_pct = round(passed_annual / total_annual * 100) if total_annual else 0
        failing_count = (
            AnnualSubjectResult.objects.filter(school=school, academic_year=year, status="fail")
            .values("student")
            .distinct()
            .count()
        )

        # مواد غير مكتملة (بدون حزم تقييم)
        incomplete_setups = SubjectClassSetup.objects.filter(
            school=school, academic_year=year, is_active=True
        ).exclude(
            packages__isnull=False
        ).count()

        # مؤشرات السلوك — query واحدة بدل 2
        behavior_stats = BehaviorInfraction.objects.filter(school=school).aggregate(
            monthly=Count("id", filter=Q(date__month=today.month, date__year=today.year)),
            critical=Count("id", filter=Q(level__gte=3)),
        )
        behavior_monthly = behavior_stats["monthly"]
        behavior_critical = behavior_stats["critical"]

        # مؤشرات العيادة — query واحدة بدل 2
        clinic_stats = ClinicVisit.objects.filter(
            school=school, visit_date__date=today
        ).aggregate(
            total=Count("id"),
            sent_home=Count("id", filter=Q(is_sent_home=True)),
        )
        clinic_today = clinic_stats["total"]
        clinic_sent_home = clinic_stats["sent_home"]

        # مؤشرات المكتبة
        library_overdue = BookBorrowing.objects.filter(
            book__school=school, status='OVERDUE'
        ).count()

        # طلبات التبديل والتعويض المعلقة
        pending_swaps = TeacherSwap.objects.filter(
            school=school,
            status__in=["accepted_b", "pending_coordinator", "pending_vp"],
        ).count()
        pending_comp = CompensatorySession.objects.filter(
            school=school, status="pending"
        ).count()
        absent_teachers_today = TeacherAbsence.objects.filter(
            school=school, date=today
        ).count()

        ctx.update(
            {
                "view_type": "director",
                "sessions_today": total_sessions,
                "completed": completed,
                "in_progress": in_progress,
                "present": present,
                "absent": absent,
                "late": late,
                "attendance_pct": att_pct,
                "att_delta": att_delta,
                "absent_delta": absent_delta,
                "total_students": total_att,
                "alerts": alerts,
                "total_annual": total_annual,
                "passed_annual": passed_annual,
                "failed_annual": failed_annual,
                "pass_pct": pass_pct,
                "failing_count": failing_count,
                "year": year,
                "pending_swaps": pending_swaps,
                "pending_comp": pending_comp,
                "absent_teachers_today": absent_teachers_today,
                "incomplete_setups": incomplete_setups,
                "behavior_monthly": behavior_monthly,
                "behavior_critical": behavior_critical,
                "clinic_today": clinic_today,
                "clinic_sent_home": clinic_sent_home,
                "library_overdue": library_overdue,
            }
        )

    elif role in ("teacher", "coordinator", "ese_teacher", "specialist", "social_worker"):
        year = settings.CURRENT_ACADEMIC_YEAR
        sessions = (
            Session.objects.filter(school=school, teacher=user, date=today)
            .select_related("class_group", "subject")
            .order_by("start_time")
        )

        now = timezone.now().time()
        next_session = next(
            (s for s in sessions if s.start_time >= now and s.status == "scheduled"), None
        )

        my_setups = (
            SubjectClassSetup.objects.filter(
                school=school, teacher=user, academic_year=year, is_active=True
            )
            .select_related("subject", "class_group")
            .order_by("class_group__grade", "subject__name_ar")
        )

        # طلبات تبديل تنتظر رد المعلم
        my_pending_swaps = TeacherSwap.objects.filter(
            school=school, teacher_b=user, status="pending_b"
        ).count()

        teacher_ctx = {
            "view_type": "teacher",
            "sessions": sessions,
            "next_session": next_session,
            "my_setups": my_setups,
            "my_pending_swaps": my_pending_swaps,
        }

        # بيانات إضافية للمنسق
        if role == "coordinator":
            teacher_ctx["view_type"] = "coordinator"
            # طلبات تبديل تنتظر اعتماد المنسق
            teacher_ctx["coord_pending_swaps"] = TeacherSwap.objects.filter(
                school=school,
                status__in=["accepted_b", "pending_coordinator"],
            ).count()
            # تعويضات معلقة
            teacher_ctx["coord_pending_comp"] = CompensatorySession.objects.filter(
                school=school, status="pending"
            ).count()
            # غياب معلمين اليوم
            teacher_ctx["coord_absent_today"] = TeacherAbsence.objects.filter(
                school=school, date=today
            ).count()

        ctx.update(teacher_ctx)

    else:
        # nurse / bus_supervisor / librarian → fallback عام
        ctx["view_type"] = "other"

    return render(request, "dashboard/main.html", ctx)

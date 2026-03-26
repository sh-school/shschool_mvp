import datetime

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils import timezone

from assessments.models import AnnualSubjectResult, SubjectClassSetup
from operations.models import (
    AbsenceAlert,
    CompensatorySession,
    ScheduleSlot,
    Session,
    StudentAttendance,
    TeacherAbsence,
    TeacherSwap,
)


@login_required
def dashboard(request):
    """لوحة التحكم الرئيسية — تعرض إحصائيات مختلفة حسب دور المستخدم."""
    user = request.user
    school = user.get_school()
    role = user.get_role()

    if not school:
        return HttpResponseForbidden("<h2 dir='rtl'>لم يتم تعيينك في أي مدرسة</h2>")

    today = timezone.now().date()
    ctx = {"today": today, "school": school}

    # ولي الأمر → بوابته مباشرة
    if role == "parent":
        return redirect("parent_dashboard")

    # الطالب → لوحته المختصرة
    if role == "student":
        year = settings.CURRENT_ACADEMIC_YEAR
        # حضور الطالب
        att_qs = StudentAttendance.objects.filter(school=school, student=user)
        student_present = att_qs.filter(status="present").count()
        student_absent = att_qs.filter(status="absent").count()
        student_late = att_qs.filter(status="late").count()
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
        ctx.update({
            "view_type": "student",
            "student_att_pct": student_att_pct,
            "student_present": student_present,
            "student_absent": student_absent,
            "student_late": student_late,
            "student_sessions": student_sessions,
            "class_group": enrollment.class_group if enrollment else None,
        })
        return render(request, "dashboard/main.html", ctx)

    if user.is_superuser or role in ("principal", "vice_admin", "vice_academic", "admin"):
        year = settings.CURRENT_ACADEMIC_YEAR

        sessions_today = Session.objects.filter(school=school, date=today).select_related("teacher")
        total_sessions = sessions_today.count()
        completed = sessions_today.filter(status="completed").count()
        in_progress = sessions_today.filter(status="in_progress").count()

        att = StudentAttendance.objects.filter(school=school, session__date=today)
        present = att.filter(status="present").count()
        absent = att.filter(status="absent").count()
        late = att.filter(status="late").count()
        total_att = present + absent + late
        att_pct = round(present / total_att * 100) if total_att else 0

        # بيانات الأمس للمقارنة (delta)
        yesterday = today - datetime.timedelta(days=1)
        att_y = StudentAttendance.objects.filter(school=school, session__date=yesterday)
        present_y = att_y.filter(status="present").count()
        absent_y = att_y.filter(status="absent").count()
        total_y = present_y + absent_y + att_y.filter(status="late").count()
        att_pct_y = round(present_y / total_y * 100) if total_y else None
        att_delta = att_pct - att_pct_y if att_pct_y is not None else None
        absent_delta = absent - absent_y if total_y else None

        alerts = (
            AbsenceAlert.objects.filter(school=school, status="pending")
            .select_related("student")
            .order_by("-created_at")[:5]
        )

        # إحصائيات التقييمات
        total_annual = AnnualSubjectResult.objects.filter(school=school, academic_year=year).count()
        passed_annual = AnnualSubjectResult.objects.filter(
            school=school, academic_year=year, status="pass"
        ).count()
        failed_annual = AnnualSubjectResult.objects.filter(
            school=school, academic_year=year, status="fail"
        ).count()
        pass_pct = round(passed_annual / total_annual * 100) if total_annual else 0
        failing_count = (
            AnnualSubjectResult.objects.filter(school=school, academic_year=year, status="fail")
            .values("student")
            .distinct()
            .count()
        )

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

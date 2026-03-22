from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Count, Q


@login_required
def dashboard(request):
    user   = request.user
    school = user.get_school()
    role   = user.get_role()

    if not school:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("<h2 dir='rtl'>لم يتم تعيينك في أي مدرسة</h2>")

    today = timezone.now().date()
    ctx   = {"today": today, "school": school}

    # ولي الأمر → بوابته مباشرة
    if role == "parent":
        return redirect("parent_dashboard")

    # الطالب → لوحته المختصرة
    if role == "student":
        ctx["view_type"] = "student"
        return render(request, "dashboard/main.html", ctx)

    if user.is_superuser or role in ("principal", "vice_admin", "vice_academic", "admin"):
        from operations.models import Session, StudentAttendance, AbsenceAlert
        from assessments.models import AnnualSubjectResult, SubjectClassSetup

        year = "2025-2026"

        sessions_today = Session.objects.filter(school=school, date=today)
        total_sessions = sessions_today.count()
        completed      = sessions_today.filter(status="completed").count()
        in_progress    = sessions_today.filter(status="in_progress").count()

        att         = StudentAttendance.objects.filter(school=school, session__date=today)
        present     = att.filter(status="present").count()
        absent      = att.filter(status="absent").count()
        late        = att.filter(status="late").count()
        total_att   = present + absent + late
        att_pct     = round(present / total_att * 100) if total_att else 0

        alerts = AbsenceAlert.objects.filter(
            school=school, status="pending"
        ).select_related("student").order_by("-created_at")[:5]

        # إحصائيات التقييمات
        total_annual  = AnnualSubjectResult.objects.filter(school=school, academic_year=year).count()
        passed_annual = AnnualSubjectResult.objects.filter(school=school, academic_year=year, status="pass").count()
        failed_annual = AnnualSubjectResult.objects.filter(school=school, academic_year=year, status="fail").count()
        pass_pct      = round(passed_annual / total_annual * 100) if total_annual else 0
        failing_count = AnnualSubjectResult.objects.filter(
            school=school, academic_year=year, status="fail"
        ).values("student").distinct().count()

        ctx.update({
            "view_type":      "director",
            "sessions_today": total_sessions,
            "completed":      completed,
            "in_progress":    in_progress,
            "present":        present,
            "absent":         absent,
            "late":           late,
            "attendance_pct": att_pct,
            "total_students": total_att,
            "alerts":         alerts,
            "total_annual":   total_annual,
            "passed_annual":  passed_annual,
            "failed_annual":  failed_annual,
            "pass_pct":       pass_pct,
            "failing_count":  failing_count,
            "year":           year,
        })

    elif role in ("teacher", "coordinator", "specialist"):
        from operations.models import Session
        from assessments.models import SubjectClassSetup

        year     = "2025-2026"
        sessions = Session.objects.filter(
            school=school, teacher=user, date=today
        ).select_related("class_group", "subject").order_by("start_time")

        now          = timezone.now().time()
        next_session = next(
            (s for s in sessions if s.start_time >= now and s.status == "scheduled"),
            None
        )

        my_setups = SubjectClassSetup.objects.filter(
            school=school, teacher=user, academic_year=year, is_active=True
        ).select_related("subject", "class_group").order_by(
            "class_group__grade", "subject__name_ar"
        )

        ctx.update({
            "view_type":    "teacher",
            "sessions":     sessions,
            "next_session": next_session,
            "my_setups":    my_setups,
        })

    else:
        # nurse / bus_supervisor / librarian → fallback عام
        ctx["view_type"] = "other"

    return render(request, "dashboard/main.html", ctx)

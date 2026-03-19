"""
reports/views.py
نظام تقارير PDF — كشف النتائج + الشهادة الفردية + تقرير الفصل
يستخدم WeasyPrint (مثبتة في requirements.txt)
"""
from io import BytesIO
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, Http404
from django.template.loader import render_to_string
from django.utils import timezone

from assessments.models import (
    AnnualSubjectResult, StudentSubjectResult,
    SubjectClassSetup, AssessmentPackage,
)
from core.models import CustomUser, StudentEnrollment, ClassGroup, School
from operations.models import StudentAttendance


def _render_pdf(html_string):
    """تحويل HTML → PDF باستخدام WeasyPrint"""
    try:
        from weasyprint import HTML, CSS
        from weasyprint.text.fonts import FontConfiguration
        font_config = FontConfiguration()
        pdf = HTML(string=html_string).write_pdf(font_config=font_config)
        return pdf
    except Exception as e:
        raise RuntimeError(f"WeasyPrint error: {e}")


def _get_student_report_data(student, school, year):
    """بيانات تقرير الطالب السنوي الكاملة"""
    annual = AnnualSubjectResult.objects.filter(
        student=student, school=school, academic_year=year
    ).select_related("setup__subject").order_by("setup__subject__name_ar")

    s1_map = {
        r.setup_id: r for r in StudentSubjectResult.objects.filter(
            student=student, school=school, semester="S1"
        )
    }
    s2_map = {
        r.setup_id: r for r in StudentSubjectResult.objects.filter(
            student=student, school=school, semester="S2"
        )
    }

    rows = []
    for ann in annual:
        rows.append({
            "subject":  ann.setup.subject.name_ar,
            "s1":       s1_map.get(ann.setup_id),
            "s2":       s2_map.get(ann.setup_id),
            "annual":   ann,
        })

    total   = annual.count()
    passed  = annual.filter(status="pass").count()
    failed  = annual.filter(status="fail").count()
    grades  = [float(r.annual_total) for r in annual if r.annual_total]
    avg     = round(sum(grades) / len(grades), 2) if grades else None
    rank    = None  # يمكن إضافته لاحقاً

    enrollment = StudentEnrollment.objects.filter(
        student=student, is_active=True
    ).select_related("class_group").first()

    # الغياب
    att = StudentAttendance.objects.filter(student=student, session__school=school)
    absent_total = att.filter(status="absent").count()
    late_total   = att.filter(status="late").count()

    return {
        "student":       student,
        "school":        school,
        "year":          year,
        "enrollment":    enrollment,
        "rows":          rows,
        "total":         total,
        "passed":        passed,
        "failed":        failed,
        "avg":           avg,
        "absent_total":  absent_total,
        "late_total":    late_total,
        "print_date":    timezone.now().date(),
    }


# ── صفحة اختيار التقرير ────────────────────────────────────

@login_required
def reports_index(request):
    school = request.user.get_school()
    year   = request.GET.get("year", "2025-2026")

    # الفصول الدراسية للمدير
    if request.user.is_admin():
        classes = ClassGroup.objects.filter(
            school=school, academic_year=year, is_active=True
        ).order_by("grade", "section")
    else:
        # المعلم: فصوله فقط
        setup_class_ids = SubjectClassSetup.objects.filter(
            school=school, teacher=request.user, academic_year=year
        ).values_list("class_group_id", flat=True)
        classes = ClassGroup.objects.filter(id__in=setup_class_ids)

    return render(request, "reports/index.html", {
        "classes": classes,
        "year":    year,
        "school":  school,
    })


# ── كشف نتائج الفصل الدراسي ────────────────────────────────

@login_required
def class_results_pdf(request, class_id):
    """PDF: كشف نتائج كامل لجميع طلاب فصل"""
    school     = request.user.get_school()
    class_grp  = get_object_or_404(ClassGroup, id=class_id, school=school)
    year       = request.GET.get("year", "2025-2026")
    preview    = request.GET.get("preview", "0") == "1"

    enrollments = StudentEnrollment.objects.filter(
        class_group=class_grp, is_active=True
    ).select_related("student").order_by("student__full_name")

    # بيانات كل طالب
    students_data = []
    for enr in enrollments:
        st      = enr.student
        annual  = AnnualSubjectResult.objects.filter(
            student=st, school=school, academic_year=year
        ).select_related("setup__subject").order_by("setup__subject__name_ar")

        grades  = [float(r.annual_total) for r in annual if r.annual_total]
        avg     = round(sum(grades) / len(grades), 2) if grades else None
        passed  = annual.filter(status="pass").count()
        failed  = annual.filter(status="fail").count()

        students_data.append({
            "student": st,
            "annual":  annual,
            "avg":     avg,
            "passed":  passed,
            "failed":  failed,
            "status":  "ناجح" if failed == 0 and passed > 0 else ("راسب" if failed > 0 else "—"),
        })

    # ترتيب حسب المتوسط
    students_data.sort(key=lambda x: x["avg"] or 0, reverse=True)
    for i, sd in enumerate(students_data, start=1):
        sd["rank"] = i

    # المواد (من أول طالب)
    subjects = []
    if enrollments.exists():
        subjects = list(AnnualSubjectResult.objects.filter(
            student=enrollments.first().student,
            school=school, academic_year=year
        ).select_related("setup__subject").order_by(
            "setup__subject__name_ar"
        ).values_list("setup__subject__name_ar", flat=True))

    ctx = {
        "class_group":    class_grp,
        "school":         school,
        "year":           year,
        "students_data":  students_data,
        "subjects":       subjects,
        "print_date":     timezone.now().date(),
        "total_students": len(students_data),
        "total_passed":   sum(1 for s in students_data if s["failed"] == 0 and s["passed"] > 0),
        "total_failed":   sum(1 for s in students_data if s["failed"] > 0),
    }

    if preview:
        return render(request, "reports/class_results.html", ctx)

    html = render_to_string("reports/class_results.html", ctx, request=request)
    pdf  = _render_pdf(html)
    filename = f"نتائج_{class_grp.get_grade_display()}_{class_grp.section}_{year}.pdf"
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{filename}"'
    return resp


# ── تقرير الطالب الفردي ─────────────────────────────────────

@login_required
def student_result_pdf(request, student_id):
    """PDF: تقرير نتيجة طالب واحد مفصّل"""
    school   = request.user.get_school()
    student  = get_object_or_404(CustomUser, id=student_id)
    year     = request.GET.get("year", "2025-2026")
    preview  = request.GET.get("preview", "0") == "1"

    # صلاحية
    if (not request.user.is_admin()
            and not request.user.is_teacher()
            and request.user != student):
        # ولي الأمر
        from core.models import ParentStudentLink
        is_parent = ParentStudentLink.objects.filter(
            parent=request.user, student=student, school=school
        ).exists()
        if not is_parent:
            return HttpResponse("غير مسموح", status=403)

    ctx = _get_student_report_data(student, school, year)

    if preview:
        return render(request, "reports/student_result.html", ctx)

    html = render_to_string("reports/student_result.html", ctx, request=request)
    pdf  = _render_pdf(html)
    filename = f"نتيجة_{student.full_name}_{year}.pdf"
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{filename}"'
    return resp


# ── شهادة التقدير (Certificate) ─────────────────────────────

@login_required
def student_certificate_pdf(request, student_id):
    """PDF: شهادة نتيجة سنوية رسمية"""
    school   = request.user.get_school()
    student  = get_object_or_404(CustomUser, id=student_id)
    year     = request.GET.get("year", "2025-2026")
    preview  = request.GET.get("preview", "0") == "1"

    if not request.user.is_admin() and not request.user.is_teacher():
        from core.models import ParentStudentLink
        is_parent = ParentStudentLink.objects.filter(
            parent=request.user, student=student, school=school
        ).exists()
        if not is_parent:
            return HttpResponse("غير مسموح", status=403)

    ctx = _get_student_report_data(student, school, year)

    # تحديد الحالة النهائية
    if ctx["failed"] == 0 and ctx["passed"] > 0:
        ctx["final_status"] = "ناجح"
        ctx["status_color"] = "#15803d"
    elif ctx["failed"] > 0:
        ctx["final_status"] = "راسب"
        ctx["status_color"] = "#dc2626"
    else:
        ctx["final_status"] = "غير مكتمل"
        ctx["status_color"] = "#d97706"

    if preview:
        return render(request, "reports/certificate.html", ctx)

    html = render_to_string("reports/certificate.html", ctx, request=request)
    pdf  = _render_pdf(html)
    filename = f"شهادة_{student.full_name}_{year}.pdf"
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{filename}"'
    return resp


# ── طباعة شهادات الفصل بالجملة ─────────────────────────────

@login_required
def class_certificates_pdf(request, class_id):
    """PDF: شهادات جميع طلاب فصل في ملف واحد"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school    = request.user.get_school()
    class_grp = get_object_or_404(ClassGroup, id=class_id, school=school)
    year      = request.GET.get("year", "2025-2026")
    preview   = request.GET.get("preview", "0") == "1"

    enrollments = StudentEnrollment.objects.filter(
        class_group=class_grp, is_active=True
    ).select_related("student").order_by("student__full_name")

    students_ctx = []
    for enr in enrollments:
        ctx = _get_student_report_data(enr.student, school, year)
        if ctx["failed"] == 0 and ctx["passed"] > 0:
            ctx["final_status"] = "ناجح"
            ctx["status_color"] = "#15803d"
        elif ctx["failed"] > 0:
            ctx["final_status"] = "راسب"
            ctx["status_color"] = "#dc2626"
        else:
            ctx["final_status"] = "غير مكتمل"
            ctx["status_color"] = "#d97706"
        students_ctx.append(ctx)

    ctx = {
        "students_ctx": students_ctx,
        "class_group":  class_grp,
        "school":       school,
        "year":         year,
        "print_date":   timezone.now().date(),
    }

    if preview:
        return render(request, "reports/class_certificates.html", ctx)

    html = render_to_string("reports/class_certificates.html", ctx, request=request)
    pdf  = _render_pdf(html)
    filename = f"شهادات_{class_grp.get_grade_display()}_{class_grp.section}_{year}.pdf"
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{filename}"'
    return resp


# ── تقرير الغياب ────────────────────────────────────────────

@login_required
def attendance_report_pdf(request, class_id):
    """PDF: تقرير حضور وغياب الفصل"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school    = request.user.get_school()
    class_grp = get_object_or_404(ClassGroup, id=class_id, school=school)
    year      = request.GET.get("year", "2025-2026")
    preview   = request.GET.get("preview", "0") == "1"

    enrollments = StudentEnrollment.objects.filter(
        class_group=class_grp, is_active=True
    ).select_related("student").order_by("student__full_name")

    rows = []
    for enr in enrollments:
        att = StudentAttendance.objects.filter(
            student=enr.student, session__school=school
        )
        total   = att.count()
        present = att.filter(status="present").count()
        absent  = att.filter(status="absent").count()
        late    = att.filter(status="late").count()
        pct     = round(present / total * 100) if total else 0
        rows.append({
            "student": enr.student,
            "total":   total,
            "present": present,
            "absent":  absent,
            "late":    late,
            "pct":     pct,
        })

    ctx = {
        "class_group": class_grp,
        "school":      school,
        "year":        year,
        "rows":        rows,
        "print_date":  timezone.now().date(),
    }

    if preview:
        return render(request, "reports/attendance_report.html", ctx)

    html = render_to_string("reports/attendance_report.html", ctx, request=request)
    pdf  = _render_pdf(html)
    filename = f"غياب_{class_grp.get_grade_display()}_{class_grp.section}_{year}.pdf"
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{filename}"'
    return resp

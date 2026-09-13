import logging
from decimal import Decimal

import django.db
from django.contrib import messages

logger = logging.getLogger(__name__)
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core import brand
from core.academic_calendar import academic_year_for, academic_year_for_school
from core.capabilities import capability_required
from core.export_utils import excel_table_styles, xl_font
from core.models import ClassGroup, CustomUser, StudentEnrollment
from core.models.academic import grade_order
from core.permissions import teacher_can_access_student
from core.privacy import mask_national_id
from operations.models import Subject

from .forms import CreateAssessmentForm
from .models import (
    AnnualSubjectResult,
    Assessment,
    AssessmentPackage,
    StudentAssessmentGrade,
    StudentSubjectResult,
    SubjectClassSetup,
)
from .services import GradeService

# ── ألوانُ العرض — الحكمُ هنا مرّةً لا شرطاً في القالب ─────────


def _grade_tone(total, out_of=100) -> str:
    """لونُ درجةٍ بنسبتها من قصواها — العتباتُ التي كانت في القالب: 80 · 65 · 50.

    كان مجموعُ الفصل (من 40 أو 60) يُلوَّن بعتبات المئة نفسها، فيظهر أحمرَ
    ولو كان كاملاً. فالنسبةُ أوّلاً ثمّ العتبة.
    """
    if total is None or not out_of:
        return "muted"
    pct = float(total) / float(out_of) * 100
    if pct >= 80:
        return "success"
    if pct >= 65:
        return "info"
    if pct >= 50:
        return "warning"
    return "danger"


def _half_tone(score, out_of) -> str:
    """نصفُ القصوى فأكثر أخضر، ودونه أحمر — عتبةُ الباقة والفصل في القالب القديم."""
    if score is None:
        return "muted"
    return "success" if float(score) >= float(out_of) * 0.5 else "danger"


#: شارةُ حالة التقييم — ما كان سلسلةَ `{% if %}` في القالب. وما لم يُذكر «مسودّة» تحذيراً.
ASSESSMENT_STATUS_BADGE = {
    "graded": "status-success",
    "published": "status-info",
    "closed": "status-gray",
}

#: شارةُ النتيجة السنويّة — والدورُ الثاني عنّابيّ، وما سواها تحذير.
ANNUAL_STATUS_BADGE = {
    "pass": "status-success",
    "fail": "status-danger",
    "second_round": "status-maroon",
}


# ── لوحة تحكم التقييمات ────────────────────────────────────


@login_required
@capability_required("assessments.view_results")
def assessments_dashboard(request):
    """لوحة تحكم التقييمات — نتائج الفصول والمواد حسب دور المستخدم."""
    school = request.user.get_school()
    semester = request.GET.get("semester", "S1")
    year = request.GET.get("year") or academic_year_for(request)

    if request.user.is_admin():
        # المدير: كل الفصول
        setups = (
            SubjectClassSetup.objects.filter(school=school, academic_year=year, is_active=True)
            .select_related("subject", "class_group", "teacher")
            .order_by(grade_order("class_group__grade"), "class_group__section", "subject__name_ar")
        )

        # إحصائيات عامة — استعلام واحد بدل 3
        total_results = StudentSubjectResult.objects.filter(
            school=school, semester=semester
        ).count()
        annual_stats = AnnualSubjectResult.objects.filter(
            school=school, academic_year=year
        ).aggregate(
            passed=Count("id", filter=Q(status="pass")),
            failed=Count("id", filter=Q(status="fail")),
        )
        passed = annual_stats["passed"]
        failed = annual_stats["failed"]
        failing_list = GradeService.get_failing_students(school, year)[:10]

    else:
        # المعلم: فصوله فقط
        setups = (
            SubjectClassSetup.objects.filter(
                school=school, teacher=request.user, academic_year=year, is_active=True
            )
            .select_related("subject", "class_group", "teacher")
            .order_by(grade_order("class_group__grade"), "class_group__section")
        )
        total_results = passed = failed = 0
        failing_list = []

    # القالبُ كان يقرأ `pass_pct` ولا يمرّره أحد، فتظهر النسبةُ «0%» دائماً.
    # وتُحسب من النتيجتين المعروضتين بجوارها — لا استعلامَ جديد.
    decided = passed + failed
    pass_pct = round(passed / decided * 100) if decided else None

    return render(
        request,
        "assessments/dashboard.html",
        {
            "setups": setups,
            "semester": semester,
            "year": year,
            "total_results": total_results,
            "passed": passed,
            "failed": failed,
            "failing_list": failing_list,
            "SEMESTERS": AssessmentPackage.SEMESTER,
            "subtitle": f"الباقات الأربع · {year}",
            "pass_pct_label": "—" if pass_pct is None else f"{pass_pct}%",
            # اللونُ يحمل التنبيه — كان شريطُ «N طالب راسب» يكرّر الرقم.
            "failed_tone": "red" if failed else "green",
        },
    )


@login_required
@capability_required("assessments.view_results")
def api_assessment_charts(request):
    """بيانات الرسوم البيانية للتقييمات"""
    school = request.user.get_school()
    year = academic_year_for(request)

    # ✅ v5.4: GradeService.get_chart_data — business logic في service layer
    data = GradeService.get_chart_data(school, year)
    return JsonResponse(data)


# ── إدارة الباقات والتقييمات ───────────────────────────────


@login_required
@capability_required("assessments.enter_grades")
def setup_detail(request, setup_id):
    """تفاصيل إعداد مادة — الباقات الأربع"""
    school = request.user.get_school()
    setup = get_object_or_404(SubjectClassSetup, id=setup_id, school=school)

    # التحقق من الصلاحية
    if not request.user.is_admin() and setup.teacher != request.user:
        return HttpResponse("غير مسموح", status=403)

    semester = request.GET.get("semester", "S1")

    # الباقات الأربع لهذا الفصل الدراسي
    packages = (
        AssessmentPackage.objects.filter(setup=setup, semester=semester)
        .prefetch_related("assessments__grades")
        .order_by("package_type")
    )

    # إنشاء الباقات إن لم تكن موجودة
    if not packages.exists():
        semester_max = AssessmentPackage.SEMESTER_MAX.get(semester, Decimal("40"))
        weights = (
            AssessmentPackage.DEFAULT_WEIGHTS_S1
            if semester == "S1"
            else AssessmentPackage.DEFAULT_WEIGHTS_S2
        )
        for ptype, weight in weights.items():
            if weight == Decimal("0"):
                continue  # تخطي الباقات ذات الوزن صفر
            AssessmentPackage.objects.get_or_create(
                setup=setup,
                package_type=ptype,
                semester=semester,
                defaults={
                    "school": school,
                    "weight": weight,
                    "semester_max_grade": semester_max,
                    "is_active": True,
                },
            )
        packages = (
            AssessmentPackage.objects.filter(setup=setup, semester=semester)
            .prefetch_related("assessments")
            .order_by("package_type")
        )

    # نتائج الفصل لهذه المادة
    summary = GradeService.get_class_results_summary(setup)

    # عدد الطلاب
    student_count = StudentEnrollment.objects.filter(
        class_group=setup.class_group, is_active=True
    ).count()

    return render(
        request,
        "assessments/setup_detail.html",
        {
            "setup": setup,
            "packages": packages,
            "semester": semester,
            "summary": summary,
            "student_count": student_count,
            "SEMESTERS": AssessmentPackage.SEMESTER,
            "subtitle": f"{setup.class_group} · {setup.teacher.full_name if setup.teacher else '—'}",
            "status_tones": ASSESSMENT_STATUS_BADGE,
            "failed_tone": "red" if summary.get("failed") else "green",
        },
    )


@login_required
@capability_required("assessments.enter_grades")
@require_POST
def create_assessment(request, package_id):
    """إنشاء تقييم جديد في باقة"""
    school = request.user.get_school()
    package = get_object_or_404(AssessmentPackage, id=package_id, school=school)

    if not request.user.is_admin() and package.setup.teacher != request.user:
        return HttpResponse("غير مسموح", status=403)

    form = CreateAssessmentForm(request.POST)
    if not form.is_valid():
        for field, errs in form.errors.items():
            for e in errs:
                messages.error(request, e)
        return redirect("setup_detail", setup_id=package.setup.id)

    try:
        assessment = GradeService.create_assessment(
            package=package,
            title=form.cleaned_data["title"],
            assessment_type=form.cleaned_data["assessment_type"],
            date=form.cleaned_data["date"],
            max_grade=form.cleaned_data["max_grade"],
            weight_in_package=form.cleaned_data["weight_in_package"],
            description=form.cleaned_data["description"],
            created_by=request.user,
        )
        messages.success(request, f"تم إنشاء التقييم: {assessment.title}")
    except (ValueError, TypeError, django.db.IntegrityError) as e:
        logger.exception("فشل إنشاء التقييم: %s", e)
        messages.error(request, f"خطأ: {e}")

    return redirect("setup_detail", setup_id=package.setup.id)


# ── إدخال الدرجات ──────────────────────────────────────────


@login_required
@capability_required("assessments.enter_grades")
def grade_entry(request, assessment_id):
    """صفحة إدخال درجات — تعرض كل طلاب الفصل"""
    school = request.user.get_school()
    assessment = get_object_or_404(Assessment, id=assessment_id, school=school)

    if not request.user.is_admin() and assessment.package.setup.teacher != request.user:
        return HttpResponse("غير مسموح", status=403)

    # طلاب الفصل
    enrollments = (
        StudentEnrollment.objects.filter(class_group=assessment.class_group, is_active=True)
        .select_related("student")
        .order_by("student__full_name")
    )

    # درجات موجودة
    existing = {
        g.student_id: g
        for g in StudentAssessmentGrade.objects.filter(assessment=assessment).select_related(
            "student"
        )
    }

    students_data = [
        {
            "student": e.student,
            "grade_obj": existing.get(e.student.id),
        }
        for e in enrollments
    ]

    stats = GradeService.get_assessment_stats(assessment)
    package = assessment.package

    return render(
        request,
        "assessments/grade_entry.html",
        {
            "assessment": assessment,
            "students_data": students_data,
            "stats": stats,
            "subtitle": (
                f"{assessment.subject.name_ar} · {assessment.class_group} · "
                f"{package.get_package_type_display()} · "
                f"الدرجة القصوى {assessment.max_grade.normalize():f}"
            ),
            "entered_sub": f"من {len(students_data)} طالباً",
            "absent_tone": "red" if stats.get("absent") else "green",
        },
    )


@login_required
@capability_required("assessments.enter_grades")
@require_POST
def save_single_grade(request, assessment_id):
    """HTMX: حفظ درجة طالب واحد"""
    school = request.user.get_school()
    assessment = get_object_or_404(Assessment, id=assessment_id, school=school)

    if not request.user.is_admin() and assessment.package.setup.teacher != request.user:
        return HttpResponse("غير مسموح", status=403)

    student_id = request.POST.get("student_id")
    student = get_object_or_404(CustomUser, id=student_id)
    is_absent = request.POST.get("is_absent") == "1"
    is_excused = request.POST.get("is_excused") == "1"
    notes = request.POST.get("notes", "")

    grade = None
    if not is_absent and not is_excused:
        raw = request.POST.get("grade", "").strip()
        if raw:
            try:
                grade = Decimal(raw)
            except (ValueError, TypeError, ArithmeticError) as e:
                logger.warning("فشل تحويل الدرجة إلى Decimal: %r — %s", raw, e)
                return HttpResponse("درجة غير صالحة", status=400)

    grade_obj, _ = GradeService.save_grade(
        assessment=assessment,
        student=student,
        grade=grade,
        is_absent=is_absent,
        is_excused=is_excused,
        notes=notes,
        entered_by=request.user,
    )

    stats = GradeService.get_assessment_stats(assessment)

    return render(
        request,
        "assessments/partials/grade_row.html",
        {
            "student": student,
            "grade_obj": grade_obj,
            "assessment": assessment,
            "stats": stats,
        },
    )


@login_required
@capability_required("assessments.enter_grades")
@require_POST
def save_all_grades(request, assessment_id):
    """حفظ كل الدرجات دفعة واحدة من form"""
    school = request.user.get_school()
    assessment = get_object_or_404(Assessment, id=assessment_id, school=school)

    if not request.user.is_admin() and assessment.package.setup.teacher != request.user:
        return HttpResponse("غير مسموح", status=403)

    enrollments = StudentEnrollment.objects.filter(
        class_group=assessment.class_group, is_active=True
    ).select_related("student")

    saved = 0
    for enr in enrollments:
        sid = str(enr.student.id)
        is_absent = request.POST.get(f"absent_{sid}") == "1"
        is_excused = request.POST.get(f"excused_{sid}") == "1"
        notes = request.POST.get(f"notes_{sid}", "")
        grade = None

        if not is_absent and not is_excused:
            raw = request.POST.get(f"grade_{sid}", "").strip()
            if raw:
                try:
                    grade = Decimal(raw)
                except (ValueError, TypeError, ArithmeticError) as e:
                    logger.warning("فشل تحويل درجة الطالب %s إلى Decimal: %r — %s", sid, raw, e)
                    continue

        GradeService.save_grade(
            assessment=assessment,
            student=enr.student,
            grade=grade,
            is_absent=is_absent,
            is_excused=is_excused,
            notes=notes,
            entered_by=request.user,
            recalc=False,  # [PERF-02] يُعاد الحساب دفعةً واحدة بعد الحلقة
        )
        saved += 1

    # [PERF-02] إعادة حساب الفصل كاملاً مرة واحدة (batch) بدل مرة لكل طالب
    GradeService.recalculate_full_class(assessment.package.setup)

    # تحديث حالة التقييم
    assessment.status = "graded"
    assessment.save(update_fields=["status"])

    messages.success(request, f"تم حفظ {saved} درجة بنجاح")
    return redirect("grade_entry", assessment_id=assessment_id)


# ── كشوف الدرجات ───────────────────────────────────────────


@login_required
@capability_required("assessments.view_results")
def class_gradebook(request, setup_id):
    """كشف الدرجات الكامل للفصل في مادة — يدعم عرض فصل أو السنوي"""
    school = request.user.get_school()
    setup = get_object_or_404(SubjectClassSetup, id=setup_id, school=school)

    if not request.user.is_admin() and setup.teacher != request.user:
        return HttpResponse("غير مسموح", status=403)

    semester = request.GET.get("semester", "S1")

    enrollments = (
        StudentEnrollment.objects.filter(class_group=setup.class_group, is_active=True)
        .select_related("student")
        .order_by("student__full_name")
    )

    # للعرض السنوي أو الفصلي
    show_annual = semester == "annual"
    packages = (
        AssessmentPackage.objects.filter(
            setup=setup, semester=semester if not show_annual else "S1", is_active=True
        )
        .prefetch_related("assessments")
        .order_by("package_type")
    )

    # ── Pre-fetch semester & annual results to avoid N+1 queries ──
    student_ids = [enr.student_id for enr in enrollments]
    sem_results_map = {
        r.student_id: r
        for r in StudentSubjectResult.objects.filter(
            student_id__in=student_ids,
            setup=setup,
            semester=semester if not show_annual else "S1",
        )
    }
    annual_results_map = {
        r.student_id: r
        for r in AnnualSubjectResult.objects.filter(
            student_id__in=student_ids,
            setup=setup,
            academic_year=setup.academic_year,
        )
    }

    # ── Batch-fetch package scores to avoid N+1 queries ──
    pkg_list = list(packages)
    if not show_annual and pkg_list:
        batch_scores = GradeService.calc_package_scores_batch(student_ids, pkg_list)
    else:
        batch_scores = {}

    # الباقاتُ ذاتُ الوزن وحدَها أعمدة — كان القالبُ يرشّحها في حلقتين.
    weighted_packages = [pkg for pkg in pkg_list if pkg.weight > 0]
    semester_max = AssessmentPackage.SEMESTER_MAX.get(semester, Decimal("40"))

    rows = []
    for enr in enrollments:
        student = enr.student
        pkg_scores = {}
        cells = []

        if not show_annual:
            for pkg in pkg_list:
                pkg_scores[pkg.package_type] = batch_scores.get((student.id, pkg.package_type))
            for pkg in weighted_packages:
                score = pkg_scores.get(pkg.package_type)
                # نصفُ درجة الباقة فأكثر أخضر — العتبةُ التي كانت في القالب.
                cells.append({"score": score, "tone": _half_tone(score, pkg.effective_max_grade)})

        semester_result = sem_results_map.get(student.id)
        annual_result = annual_results_map.get(student.id)
        sem_total = semester_result.total if semester_result else None
        sem_out_of = semester_result.semester_max if semester_result else semester_max
        rows.append(
            {
                "student": student,
                "pkg_scores": pkg_scores,
                "cells": cells,
                "semester_result": semester_result,
                "annual_result": annual_result,
                "sem_tone": _grade_tone(sem_total, sem_out_of),
                # الحالةُ في عرض الفصل بقاعدة التصدير نفسِها: النصفُ فأكثر ناجح.
                "sem_passed": (
                    None if sem_total is None else float(sem_total) >= float(sem_out_of) * 0.5
                ),
                "annual_tone": _grade_tone(annual_result.annual_total if annual_result else None),
            }
        )

    summary = GradeService.get_class_results_summary(setup)

    return render(
        request,
        "assessments/class_gradebook.html",
        {
            "setup": setup,
            "packages": packages,
            "rows": rows,
            "summary": summary,
            "semester": semester,
            "show_annual": show_annual,
            "SEMESTERS": AssessmentPackage.SEMESTER,
            "weighted_packages": weighted_packages,
            "semester_max": semester_max,
            "subtitle": f"{setup.subject.name_ar} · {setup.class_group} · {setup.academic_year}",
            "failed_tone": "red" if summary.get("failed") else "green",
            "status_tones": ANNUAL_STATUS_BADGE,
        },
    )


@login_required
@capability_required("assessments.view_results")
def export_gradebook(request, setup_id):
    """تصدير كشف الدرجات إلى Excel"""
    import io

    from openpyxl import Workbook
    from openpyxl.styles import Alignment
    from openpyxl.utils import get_column_letter

    school = request.user.get_school()
    setup = get_object_or_404(SubjectClassSetup, id=setup_id, school=school)

    if not request.user.is_admin() and setup.teacher != request.user:
        return HttpResponse("غير مسموح", status=403)

    semester = request.GET.get("semester", "S1")

    enrollments = (
        StudentEnrollment.objects.filter(class_group=setup.class_group, is_active=True)
        .select_related("student")
        .order_by("student__full_name")
    )

    packages = (
        AssessmentPackage.objects.filter(setup=setup, semester=semester, is_active=True)
        .prefetch_related("assessments")
        .order_by("package_type")
    )

    # ── بناء الـ Workbook ──────────────────────────────────
    wb = Workbook()
    ws = wb.active
    ws.title = "كشف الدرجات"
    ws.sheet_view.rightToLeft = True

    # ألوان
    table = excel_table_styles()
    HEADER_FILL = table.header_fill
    HEADER_FONT = table.header_font
    ALT_FILL = table.alt_fill
    THIN_BORDER = table.border
    CENTER = table.data_align
    RIGHT_ALIGN = Alignment(horizontal="right", vertical="center")

    pkg_labels = {
        "P1": "الباقة 1",
        "P2": "الباقة 2",
        "P3": "الباقة 3",
        "P4": "الباقة 4",
    }
    sem_labels = {"S1": "الفصل الأول (40)", "S2": "الفصل الثاني (60)"}

    # ── السطر 1: عنوان ─────────────────────────────────────
    title = (
        f"كشف درجات | {setup.subject.name_ar} | "
        f"{setup.class_group} | {sem_labels.get(semester, semester)} | "
        f"{setup.academic_year}"
    )
    ws.merge_cells("A1:H1")
    ws["A1"] = title
    ws["A1"].font = xl_font(brand.MAROON, size=13, bold=True)
    ws["A1"].alignment = CENTER
    ws.row_dimensions[1].height = 28

    # ── السطر 2: رؤوس الأعمدة ──────────────────────────────
    pkg_list = list(packages)
    headers = (
        ["م", "اسم الطالب", "الرقم الشخصي"]
        + [pkg_labels.get(p.package_type, p.package_type) for p in pkg_list]
        + ["مجموع الفصل", "الحالة"]
    )

    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=2, column=col_idx, value=header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER
        cell.border = THIN_BORDER

    ws.row_dimensions[2].height = 22

    # ── Pre-fetch semester results + package scores to avoid N+1 queries ──
    student_ids = [enr.student_id for enr in enrollments]
    sem_results_map = {
        r.student_id: r
        for r in StudentSubjectResult.objects.filter(
            student_id__in=student_ids, setup=setup, semester=semester
        )
    }
    batch_scores = GradeService.calc_package_scores_batch(student_ids, pkg_list)

    # ── البيانات ────────────────────────────────────────────
    for row_idx, enr in enumerate(enrollments, start=1):
        student = enr.student
        excel_row = row_idx + 2
        fill = ALT_FILL if row_idx % 2 == 0 else None

        pkg_scores = {
            p.package_type: batch_scores.get((student.id, p.package_type)) for p in pkg_list
        }

        sem_result = sem_results_map.get(student.id)
        if sem_result:
            total = float(sem_result.total) if sem_result.total is not None else ""
            status = (
                "ناجح ✓"
                if (sem_result.total or 0) >= (sem_result.semester_max * Decimal("0.5"))
                else "راسب ✗"
            )
        else:
            total, status = "", "—"

        row_data = (
            [row_idx, student.full_name, student.national_id]
            + [float(pkg_scores.get(p.package_type) or 0) for p in pkg_list]
            + [total, status]
        )

        for col_idx, value in enumerate(row_data, start=1):
            cell = ws.cell(row=excel_row, column=col_idx, value=value)
            cell.border = THIN_BORDER
            cell.font = table.cell_font
            cell.alignment = CENTER if col_idx != 2 else RIGHT_ALIGN
            if fill:
                cell.fill = fill

    # ── عرض الأعمدة ────────────────────────────────────────
    col_widths = [5, 30, 18] + [12] * len(pkg_list) + [14, 10]
    for i, width in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width

    # ── تجميد الصفوف الأولى ────────────────────────────────
    ws.freeze_panes = "A3"

    # ── إرسال الملف ────────────────────────────────────────
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"gradebook_{setup.subject.name_ar}_{setup.class_group}_{semester}.xlsx".replace(
        " ", "_"
    ).replace("/", "-")
    resp = HttpResponse(
        buf.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@login_required
@capability_required("assessments.enter_grades")
@require_POST
def recalculate_class(request, setup_id):
    """إعادة حساب درجات كل طلاب الفصل — Admin أو المعلم المسؤول فقط"""
    school = request.user.get_school()
    setup = get_object_or_404(SubjectClassSetup, id=setup_id, school=school)

    if not request.user.is_admin() and setup.teacher != request.user:
        return HttpResponse("غير مسموح", status=403)

    GradeService.recalculate_full_class(setup)
    messages.success(
        request, f"تم إعادة حساب درجات {setup.class_group} في {setup.subject.name_ar} بنجاح."
    )
    return redirect("class_gradebook", setup_id=setup_id)


@login_required
@capability_required("assessments.view_results")
def student_report(request, student_id):
    """كشف درجات سنوي للطالب في كل مواده"""
    school = request.user.get_school()
    student = get_object_or_404(
        CustomUser,
        id=student_id,
        memberships__school=school,
        memberships__is_active=True,
    )
    year = request.GET.get("year") or academic_year_for(request)

    # ── تقييد الوصول: المعلم/المنسق يرى طلابه فقط ──
    if not teacher_can_access_student(request.user, student.id) and request.user != student:
        return HttpResponse("غير مسموح — هذا الطالب ليس من طلابك", status=403)

    results = GradeService.get_student_annual_report(student, school, year)
    stats = results.aggregate(
        total_subjects=Count("id"),
        passed=Count("id", filter=Q(status="pass")),
        failed=Count("id", filter=Q(status="fail")),
    )
    total_subjects = stats["total_subjects"]
    passed = stats["passed"]
    failed = stats["failed"]

    # ألوانُ الصفّ — العتباتُ التي كانت في القالب: نصفُ الفصل (20 من 40، 30 من 60)
    # أخضرُ وما دونه تحذير، والمجموعُ السنويّ بعتبات 80 · 65 · 50.
    rows = [
        {
            "result": r,
            "s1_tone": None if r.s1_total is None else "success" if r.s1_total >= 20 else "warning",
            "s2_tone": None if r.s2_total is None else "success" if r.s2_total >= 30 else "warning",
            "tone": _grade_tone(r.annual_total),
        }
        for r in results
    ]

    return render(
        request,
        "assessments/student_report.html",
        {
            "student": student,
            "results": results,
            "rows": rows,
            "year": year,
            "total_subjects": total_subjects,
            "passed": passed,
            "failed": failed,
            "SEMESTERS": AssessmentPackage.SEMESTER,
            "subtitle": f"{student.full_name} · {mask_national_id(student.national_id)} · {year}",
            "failed_tone": "red" if failed else "green",
            "status_tones": ANNUAL_STATUS_BADGE,
        },
    )


@login_required
@capability_required("assessments.oversee")
def failing_students(request):
    """قائمة الطلاب الراسبين — للمدير"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    semester = request.GET.get("semester", "S1")
    year = request.GET.get("year") or academic_year_for(request)

    failing = GradeService.get_failing_students(school, year)

    # تجميع بالطالب
    by_student = {}
    for r in failing:
        sid = r.student.id
        if sid not in by_student:
            by_student[sid] = {
                "student": r.student,
                "subjects": [],
                # صفُّ الطالب من أوّل موادّه — كما كان القالبُ يقرؤه للترشيح.
                "grade": r.setup.class_group.get_grade_display(),
                # الكشفُ يقرأ `year` لا `semester` — فالرابطُ يحمل عامَ القائمة نفسَه.
                "report_url": f"{reverse('student_report', args=[sid])}?year={year}",
            }
        by_student[sid]["subjects"].append(r)

    for item in by_student.values():
        item["count_label"] = f"{len(item['subjects'])} مادة"

    student_list = list(by_student.values())
    paginator = Paginator(student_list, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "assessments/failing_students.html",
        {
            "by_student": page_obj,
            "page_obj": page_obj,
            "semester": semester,
            "year": year,
            "total": len(by_student),
            "SEMESTERS": AssessmentPackage.SEMESTER,
            "subtitle": f"{len(by_student)} طالب في مادة أو أكثر · {year}",
        },
    )


# ── إعداد المواد (للمدير) ──────────────────────────────────


@login_required
@capability_required("assessments.oversee")
def setup_subject(request):
    """ربط مادة بفصل ومعلم"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()

    if request.method == "POST":
        subject_id = request.POST.get("subject")
        class_id = request.POST.get("class_group")
        teacher_id = request.POST.get("teacher")
        year = request.POST.get("academic_year") or academic_year_for(request)

        subject = get_object_or_404(Subject, id=subject_id, school=school)
        class_group = get_object_or_404(ClassGroup, id=class_id, school=school)
        teacher = get_object_or_404(CustomUser, id=teacher_id)

        setup, created = SubjectClassSetup.objects.get_or_create(
            school=school,
            subject=subject,
            class_group=class_group,
            academic_year=year,
            defaults={"teacher": teacher, "is_active": True},
        )
        if not created:
            setup.teacher = teacher
            setup.is_active = True
            setup.save(update_fields=["teacher", "is_active"])

        msg = "تم الإنشاء" if created else "تم التحديث"
        messages.success(request, f"{msg}: {subject.name_ar} | {class_group}")
        return redirect("assessments_dashboard")

    # GET
    subjects = Subject.objects.filter(school=school).order_by("name_ar")
    classes = ClassGroup.objects.filter(
        school=school, academic_year=academic_year_for_school(school), is_active=True
    ).in_school_order()
    from core.models import Membership

    t_ids = Membership.objects.filter(
        school=school, is_active=True, role__name__in=["teacher", "coordinator"]
    ).values_list("user_id", flat=True)
    teachers = CustomUser.objects.filter(id__in=t_ids).order_by("full_name")

    return render(
        request,
        "assessments/setup_subject.html",
        {
            "subjects": subjects,
            "classes": classes,
            "teachers": teachers,
        },
    )

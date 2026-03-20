"""
parents/views.py
بوابة ولي الأمر — درجات + غياب + تقرير شامل
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Q
from datetime import timedelta

from core.models import ParentStudentLink, CustomUser, StudentEnrollment, School, Membership


def _require_parent(request):
    """تحقق أن المستخدم ولي أمر — يُعيد school أو None
    يدعم الموظف الذي هو أيضاً ولي أمر (has_role بدلاً من get_role)
    """
    if request.user.is_superuser:
        return request.user.get_school()
    parent_membership = request.user.get_parent_membership()
    if not parent_membership:
        return None
    return parent_membership.school


# ── لوحة تحكم ولي الأمر ─────────────────────────────────────

@login_required
def parent_dashboard(request):
    school = _require_parent(request)
    if not school and not request.user.is_superuser:
        return HttpResponse("هذه الصفحة لأولياء الأمور فقط", status=403)

    # استخدم مدرسة عضوية ولي الأمر تحديداً (يدعم الموظف الذي هو ولي أمر)
    parent_membership = request.user.get_parent_membership()
    school = parent_membership.school if parent_membership else request.user.get_school()
    year   = request.GET.get("year", "2025-2026")

    # أبناء ولي الأمر
    links = ParentStudentLink.objects.filter(
        parent=request.user, school=school
    ).select_related("student").order_by("student__full_name")

    children = []
    for link in links:
        student = link.student

        # التسجيل الحالي
        enrollment = StudentEnrollment.objects.filter(
            student=student, is_active=True
        ).select_related("class_group").first()

        # ملخص الدرجات السنوية
        from assessments.models import AnnualSubjectResult
        annual = AnnualSubjectResult.objects.filter(
            student=student, school=school, academic_year=year
        )
        total_subj  = annual.count()
        passed      = annual.filter(status="pass").count()
        failed      = annual.filter(status="fail").count()
        incomplete  = annual.filter(status="incomplete").count()

        # ملخص الغياب (آخر 30 يوم)
        from operations.models import StudentAttendance
        since = timezone.now().date() - timedelta(days=30)
        att = StudentAttendance.objects.filter(
            student=student,
            session__school=school,
            session__date__gte=since,
        )
        absent_count = att.filter(status="absent").count()
        late_count   = att.filter(status="late").count()
        total_att    = att.count()

        children.append({
            "link":         link,
            "student":      student,
            "enrollment":   enrollment,
            "total_subj":   total_subj,
            "passed":       passed,
            "failed":       failed,
            "incomplete":   incomplete,
            "absent_30":    absent_count,
            "late_30":      late_count,
            "attendance_sessions": total_att,
        })

    return render(request, "parents/dashboard.html", {
        "children": children,
        "year":     year,
        "school":   school,
    })


# ── درجات الطالب ────────────────────────────────────────────

@login_required
def student_grades(request, student_id):
    school  = request.user.get_school()
    student = get_object_or_404(CustomUser, id=student_id)
    year    = request.GET.get("year", "2025-2026")

    # تحقق الصلاحية
    link = ParentStudentLink.objects.filter(
        parent=request.user, student=student, school=school
    ).first()
    if not link and not request.user.is_superuser:
        return HttpResponse("غير مسموح", status=403)
    if link and not link.can_view_grades:
        return HttpResponse("ليس لديك صلاحية عرض الدرجات", status=403)

    from assessments.models import AnnualSubjectResult, StudentSubjectResult

    # النتائج السنوية
    annual_results = AnnualSubjectResult.objects.filter(
        student=student, school=school, academic_year=year
    ).select_related("setup__subject", "setup__class_group").order_by(
        "setup__subject__name_ar"
    )

    # نتائج الفصلين منفصلة
    s1_map = {
        r.setup_id: r
        for r in StudentSubjectResult.objects.filter(
            student=student, school=school, semester="S1"
        ).select_related("setup__subject")
    }
    s2_map = {
        r.setup_id: r
        for r in StudentSubjectResult.objects.filter(
            student=student, school=school, semester="S2"
        ).select_related("setup__subject")
    }

    rows = []
    for ann in annual_results:
        rows.append({
            "subject":  ann.setup.subject.name_ar,
            "s1":       s1_map.get(ann.setup_id),
            "s2":       s2_map.get(ann.setup_id),
            "annual":   ann,
        })

    # إحصائيات
    total  = annual_results.count()
    passed = annual_results.filter(status="pass").count()
    failed = annual_results.filter(status="fail").count()
    avg    = None
    grades = [float(r.annual_total) for r in annual_results if r.annual_total]
    if grades:
        avg = round(sum(grades) / len(grades), 1)

    enrollment = StudentEnrollment.objects.filter(
        student=student, is_active=True
    ).select_related("class_group").first()

    return render(request, "parents/student_grades.html", {
        "student":    student,
        "link":       link,
        "rows":       rows,
        "total":      total,
        "passed":     passed,
        "failed":     failed,
        "avg":        avg,
        "year":       year,
        "enrollment": enrollment,
    })


# ── غياب الطالب ─────────────────────────────────────────────

@login_required
def student_attendance(request, student_id):
    school  = request.user.get_school()
    student = get_object_or_404(CustomUser, id=student_id)
    year    = request.GET.get("year", "2025-2026")

    link = ParentStudentLink.objects.filter(
        parent=request.user, student=student, school=school
    ).first()
    if not link and not request.user.is_superuser:
        return HttpResponse("غير مسموح", status=403)
    if link and not link.can_view_attendance:
        return HttpResponse("ليس لديك صلاحية عرض الغياب", status=403)

    from operations.models import StudentAttendance

    # فلتر التاريخ
    period = request.GET.get("period", "30")
    try:
        days = int(period)
    except ValueError:
        days = 30
    since = timezone.now().date() - timedelta(days=days)

    attendance = StudentAttendance.objects.filter(
        student=student,
        session__school=school,
        session__date__gte=since,
    ).select_related("session__subject", "session__class_group").order_by(
        "-session__date", "session__start_time"
    )

    # تجميع يومي
    by_date = {}
    for att in attendance:
        d = att.session.date
        if d not in by_date:
            by_date[d] = {"date": d, "records": [], "has_absent": False, "has_late": False}
        by_date[d]["records"].append(att)
        if att.status == "absent":
            by_date[d]["has_absent"] = True
        if att.status == "late":
            by_date[d]["has_late"] = True

    days_list = sorted(by_date.values(), key=lambda x: x["date"], reverse=True)

    # إحصائيات الفترة
    total   = attendance.count()
    absent  = attendance.filter(status="absent").count()
    late    = attendance.filter(status="late").count()
    present = attendance.filter(status="present").count()
    att_pct = round(present / total * 100) if total else 0

    # تنبيهات الغياب المتكرر
    from operations.models import AbsenceAlert
    alerts = AbsenceAlert.objects.filter(
        student=student, school=school
    ).order_by("-created_at")[:5]

    enrollment = StudentEnrollment.objects.filter(
        student=student, is_active=True
    ).select_related("class_group").first()

    return render(request, "parents/student_attendance.html", {
        "student":        student,
        "link":           link,
        "days_list":      days_list,
        "total":          total,
        "present":        present,
        "absent":         absent,
        "late":           late,
        "att_pct":        att_pct,
        "alerts":         alerts,
        "period":         period,
        "since":          since,
        "enrollment":     enrollment,
        "year":           year,
        "period_choices": ["7", "14", "30", "60"],
    })


# ══════════════════════════════════════════════════════════════
# إدارة الربط (للمدير فقط)
# ══════════════════════════════════════════════════════════════

@login_required
def manage_parent_links(request):
    """صفحة المدير: ربط أولياء الأمور بأبنائهم"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    year   = request.GET.get("year", "2025-2026")
    search = request.GET.get("q", "").strip()

    # أولياء الأمور الحاليون
    links = ParentStudentLink.objects.filter(
        school=school
    ).select_related("parent", "student").order_by(
        "student__full_name", "parent__full_name"
    )

    if search:
        links = links.filter(
            Q(parent__full_name__icontains=search) |
            Q(student__full_name__icontains=search) |
            Q(parent__national_id__icontains=search) |
            Q(student__national_id__icontains=search)
        )

    # قائمة الطلاب للـ dropdown
    student_ids = StudentEnrollment.objects.filter(
        class_group__school=school,
        class_group__academic_year=year,
        is_active=True,
    ).values_list("student_id", flat=True)
    students = CustomUser.objects.filter(id__in=student_ids).order_by("full_name")

    # قائمة أولياء الأمور
    parent_ids = Membership.objects.filter(
        school=school, is_active=True, role__name="parent"
    ).values_list("user_id", flat=True)
    parents = CustomUser.objects.filter(id__in=parent_ids).order_by("full_name")

    return render(request, "parents/manage_links.html", {
        "links":    links,
        "students": students,
        "parents":  parents,
        "search":   search,
        "year":     year,
        "RELATIONSHIP": ParentStudentLink.RELATIONSHIP,
    })


@login_required
def add_parent_link(request):
    if request.method != "POST" or not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school     = request.user.get_school()
    parent_id  = request.POST.get("parent_id")
    student_id = request.POST.get("student_id")
    rel        = request.POST.get("relationship", "father")

    parent  = get_object_or_404(CustomUser, id=parent_id)
    student = get_object_or_404(CustomUser, id=student_id)

    link, created = ParentStudentLink.objects.get_or_create(
        school=school, parent=parent, student=student,
        defaults={
            "relationship":      rel,
            "can_view_grades":   True,
            "can_view_attendance": True,
        }
    )
    if created:
        messages.success(request, f"✓ تم ربط {parent.full_name} بـ {student.full_name}")
    else:
        messages.warning(request, f"الربط موجود مسبقاً: {parent.full_name} ← {student.full_name}")

    return redirect("manage_parent_links")


@login_required
def remove_parent_link(request, link_id):
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    link   = get_object_or_404(ParentStudentLink, id=link_id, school=school)
    name   = f"{link.parent.full_name} ← {link.student.full_name}"
    link.delete()
    messages.success(request, f"تم حذف الربط: {name}")
    return redirect("manage_parent_links")


# ── صفحة الموافقة على معالجة البيانات (PDPPL) ────────────────

@login_required
def consent_view(request):
    """ولي الأمر يمنح / يسحب الموافقة على أنواع البيانات"""
    from core.models import ConsentRecord, ParentStudentLink

    if not request.user.has_role('parent') and not request.user.is_superuser:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("هذه الصفحة لأولياء الأمور فقط.")

    school   = request.user.get_school()
    links    = ParentStudentLink.objects.filter(
        parent=request.user, school=school
    ).select_related('student')

    DATA_TYPES = [
        ('health',     'البيانات الصحية'),
        ('behavior',   'بيانات السلوك'),
        ('grades',     'الدرجات والتقييمات'),
        ('attendance', 'الحضور والغياب'),
        ('transport',  'بيانات النقل'),
    ]

    if request.method == 'POST':
        from django.utils import timezone
        for link in links:
            for dt, _ in DATA_TYPES:
                key     = f"consent_{link.student_id}_{dt}"
                is_given = request.POST.get(key) == '1'
                obj, created = ConsentRecord.objects.get_or_create(
                    parent=request.user, student=link.student,
                    school=school, data_type=dt,
                    defaults={'is_given': is_given, 'method': 'digital',
                              'recorded_by': request.user}
                )
                if not created and obj.is_given != is_given:
                    obj.is_given = is_given
                    if not is_given:
                        obj.withdrawn_at = timezone.now()
                    else:
                        obj.withdrawn_at = None
                    obj.save(update_fields=['is_given', 'withdrawn_at'])

        if not request.user.consent_given_at:
            request.user.consent_given_at = timezone.now()
            request.user.save(update_fields=['consent_given_at'])

        messages.success(request, "تم حفظ إعدادات الموافقة بنجاح.")
        return redirect('parent_dashboard')

    # بناء بيانات الموافقة الحالية
    consent_data = {}
    for link in links:
        consent_data[str(link.student_id)] = {}
        for dt, _ in DATA_TYPES:
            rec = ConsentRecord.objects.filter(
                parent=request.user, student=link.student, data_type=dt
            ).first()
            consent_data[str(link.student_id)][dt] = rec.is_given if rec else True

    return render(request, 'parents/consent.html', {
        'links':        links,
        'data_types':   DATA_TYPES,
        'consent_data': consent_data,
        'school':       school,
    })

# behavior/views.py — Thin views using BehaviorService
"""
وحدة السلوك الطلابي — SchoolOS V2
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Views نحيفة — كل Business Logic في behavior/services.py
"""

import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone as _tz

from core.permissions import (
    BEHAVIOR_COMMITTEE,
    BEHAVIOR_MANAGE,
    BEHAVIOR_RECORD,
    BEHAVIOR_VIEW_ALL,
    get_teacher_student_ids,
    role_required,
    teacher_can_access_student,
)

logger = logging.getLogger(__name__)

_VALID_LEVELS = {1, 2, 3, 4}
_MAX_POINTS = 100
_MAX_DESC_LEN = 2000

from behavior.forms import InfractionForm
from behavior.models import ViolationCategory
from core.models import BehaviorInfraction, CustomUser


def _get_scoped_students(user, school):
    """
    يُعيد QuerySet طلاب مرئيّ حسب دور المستخدم:
    - القيادة/الأخصائيون → كل طلاب المدرسة
    - المعلم/المنسق → طلاب فصوله فقط
    """
    student_ids = get_teacher_student_ids(user)
    if student_ids is None:
        # admin/leadership — all students
        return (
            CustomUser.objects.filter(
                memberships__school=school,
                memberships__role__name="student",
                memberships__is_active=True,
            )
            .order_by("full_name")
            .distinct()
        )
    return CustomUser.objects.filter(id__in=student_ids).order_by("full_name")


from .services import (
    PERIOD_CHOICES,
    BehaviorPermissions,
    BehaviorService,
)


# ── لوحة التحكم ──────────────────────────────────────────────
@login_required
@role_required(BEHAVIOR_MANAGE | BEHAVIOR_RECORD | BEHAVIOR_VIEW_ALL)
def behavior_dashboard(request):
    """لوحة تحكم السلوك — إحصائيات المخالفات والحالات الحرجة للمدرسة."""
    role = request.user.get_role()
    if role in ("parent", "student"):
        return HttpResponseForbidden("ليس لديك صلاحية الوصول إلى هذه الصفحة.")

    school = request.user.get_school()
    if not school:
        messages.error(request, "لم يتم العثور على مدرسة مرتبطة بحسابك.")
        return redirect("dashboard")

    # المعلم/المنسق يرى سلوك طلابه فقط
    student_ids = get_teacher_student_ids(request.user)
    context = BehaviorService.get_dashboard_stats(school, student_ids=student_ids)
    context["can_report"] = BehaviorPermissions.can_report(request.user)
    context["is_committee"] = BehaviorPermissions.is_committee(request.user)
    context["can_summon"] = BehaviorPermissions.can_summon(request.user)
    context["can_stats"] = BehaviorPermissions.can_view_stats(request.user)

    # ── Chart data ──
    from datetime import timedelta

    from django.db.models import Count
    from django.db.models.functions import TruncDate, TruncMonth

    today = _tz.localdate()

    # Monthly trend (last 6 months)
    six_months_ago = today - timedelta(days=180)
    base_qs = BehaviorInfraction.objects.filter(school=school)
    if student_ids is not None:
        base_qs = base_qs.filter(student_id__in=student_ids)

    monthly_trend = (
        base_qs.filter(created_at__date__gte=six_months_ago)
        .values(month=TruncMonth("created_at"))
        .annotate(count=Count("id"))
        .order_by("month")
    )

    # Level distribution (current year)
    level_dist = (
        base_qs.filter(created_at__year=today.year)
        .values("level")
        .annotate(count=Count("id"))
        .order_by("level")
    )

    # Weekly trend (last 7 days)
    week_ago = today - timedelta(days=7)
    daily_trend = (
        base_qs.filter(created_at__date__gte=week_ago)
        .values(day=TruncDate("created_at"))
        .annotate(count=Count("id"))
        .order_by("day")
    )

    # Top violation categories (current year)
    top_violations = (
        base_qs.filter(created_at__year=today.year)
        .values("violation_category__name_ar")
        .annotate(count=Count("id"))
        .order_by("-count")[:5]
    )

    context["monthly_trend"] = monthly_trend
    context["level_dist"] = level_dist
    context["daily_trend"] = daily_trend
    context["top_violations"] = top_violations

    return render(request, "behavior/dashboard.html", context)


# ── تسجيل مخالفة جديدة ───────────────────────────────────────
@login_required
@role_required(BEHAVIOR_MANAGE | BEHAVIOR_RECORD)
def report_infraction(request):
    """تسجيل مخالفة سلوكية جديدة مع إشعار ولي الأمر تلقائياً."""
    if not BehaviorPermissions.can_report(request.user):
        messages.error(request, "ليس لديك صلاحية تسجيل المخالفات.")
        return redirect("behavior:dashboard")

    school = request.user.get_school()

    # فئات المخالفات النشطة — 40 مخالفة رسمية حسب لائحة الشحانية
    # الفلتر code__regex يستبعد ABCD القديمة حتى لو بقيت is_active=True
    all_violations = ViolationCategory.objects.filter(
        is_active=True, code__regex=r"^\d+-\d+$"
    ).order_by("code")
    violations_by_degree = {str(d): list(all_violations.filter(degree=d)) for d in range(1, 5)}

    if request.method == "POST":
        form = InfractionForm(request.POST)
        if not form.is_valid():
            for field, errs in form.errors.items():
                for err in errs:
                    messages.error(request, err)
        else:
            student_id = form.cleaned_data["student_id"]
            violation_cat_id = form.cleaned_data.get("violation_category")
            description = form.cleaned_data["description"]
            # REQ-SH-001: structured disciplinary action + conditional textarea
            disciplinary_action_type = form.cleaned_data.get("disciplinary_action_type", "")
            violation_description = form.cleaned_data.get("violation_description", "")
            # Legacy free-text (kept for backward compat). Mirror the selected label
            # from the dropdown so legacy readers still see a human-friendly value.
            _choices_map = dict(form.fields["disciplinary_action_type"].choices)
            action = _choices_map.get(disciplinary_action_type, "") or form.cleaned_data.get(
                "action_taken", ""
            )
            level = form.cleaned_data["level"]

            # جلب فئة المخالفة إن وُجدت
            violation_cat = None
            if violation_cat_id:
                try:
                    violation_cat = ViolationCategory.objects.get(id=violation_cat_id)
                    level = violation_cat.degree
                except ViolationCategory.DoesNotExist:
                    messages.error(request, "فئة المخالفة غير موجودة.")
                    violation_cat = "INVALID"

            if violation_cat != "INVALID":
                student = get_object_or_404(CustomUser, id=student_id)

                try:
                    # ✅ v5.4: BehaviorService.create_infraction — atomic + escalation حسابي
                    # نظام النقاط ملغى — نُمرر 0 لتوافق DB (الحقل NOT NULL)
                    infraction = BehaviorService.create_infraction(
                        school=school,
                        student=student,
                        reporter=request.user,
                        level=level,
                        description=description,
                        action_taken=action,
                        points_deducted=0,
                        violation_category=violation_cat if violation_cat else None,
                        disciplinary_action_type=disciplinary_action_type,
                        violation_description=violation_description,
                    )
                except ValueError as e:
                    messages.error(request, str(e))
                    return redirect("behavior:dashboard")

                messages.success(
                    request, f"تم تسجيل مخالفة من الدرجة {level} للطالب {student.full_name}"
                )
                # إشعار غير متزامن عبر Celery
                try:
                    from notifications.tasks import notify_behavior_task

                    notify_behavior_task.delay(
                        infraction_id=str(infraction.id),
                        reporter_id=str(request.user.id),
                    )
                except (ImportError, OSError, RuntimeError) as e:
                    logger.warning("Celery غير متاح — إشعار مباشر: %s", e)
                    BehaviorService.notify_parents(infraction, school, request.user)

                if level >= 3:
                    messages.warning(
                        request, f"تم إحالة المخالفة للجنة الضبط السلوكي لكونها من الدرجة {level}"
                    )
                    return redirect("behavior:committee")
                return redirect("behavior:student_profile", student_id=student.id)

    students = _get_scoped_students(request.user, school)
    return render(
        request,
        "behavior/report_form.html",
        {
            "students": students,
            "levels": BehaviorInfraction.LEVELS,
            "violations_by_degree": violations_by_degree,
        },
    )


# ── تسجيل مخالفة سريعة (HTMX Modal) ────────────────────────
@login_required
@role_required(BEHAVIOR_RECORD)
def quick_log(request):
    """
    تسجيل مخالفة سريعة عبر HTMX Modal.

    GET  → نموذج HTML (partial) لعرضه داخل modal
    POST → إنشاء المخالفة + HX-Trigger showToast + HX-Redirect للملف السلوكي
    """
    from core.htmx_utils import htmx_redirect, htmx_toast

    if not BehaviorPermissions.can_report(request.user):
        from django.http import HttpResponse

        return HttpResponse("ليس لديك صلاحية", status=403)

    school = request.user.get_school()

    if request.method == "POST":
        student_id = request.POST.get("student_id", "").strip()
        violation_cat_id = request.POST.get("violation_category", "").strip()
        description = request.POST.get("description", "").strip()
        action = request.POST.get("action_taken", "").strip()

        try:
            level = int(request.POST.get("level", 1))
        except (ValueError, TypeError):
            level = 1

        # جلب فئة المخالفة
        violation_cat = None
        if violation_cat_id:
            try:
                violation_cat = ViolationCategory.objects.get(id=violation_cat_id)
                level = violation_cat.degree
            except ViolationCategory.DoesNotExist:
                pass

        # Validation
        errors = []
        if not student_id:
            errors.append("يرجى اختيار الطالب.")
        if not description:
            errors.append("يرجى كتابة وصف المخالفة.")
        elif len(description) > _MAX_DESC_LEN:
            errors.append(f"الوصف لا يتجاوز {_MAX_DESC_LEN} حرف.")
        if level not in _VALID_LEVELS:
            errors.append("درجة المخالفة يجب أن تكون بين 1 و 4.")

        if errors:
            return htmx_toast(
                render(
                    request,
                    "behavior/partials/quick_log_form.html",
                    _quick_log_context(request.user, school, student_id),
                ),
                msg=" | ".join(errors),
                msg_type="danger",
            )

        student = get_object_or_404(CustomUser, id=student_id)

        # ✅ v5.4: BehaviorService.create_infraction — atomic + escalation حسابي
        # نظام النقاط ملغى — points_deducted=0 للحفاظ على توافق DB
        infraction = BehaviorService.create_infraction(
            school=school,
            student=student,
            reporter=request.user,
            level=level,
            description=description,
            action_taken=action,
            points_deducted=0,
            violation_category=violation_cat,
        )

        # إشعار غير متزامن
        try:
            from notifications.tasks import notify_behavior_task

            notify_behavior_task.delay(
                infraction_id=str(infraction.id),
                reporter_id=str(request.user.id),
            )
        except (ImportError, OSError, RuntimeError) as exc:
            logger.warning("Celery unavailable for quick_log notify: %s", exc)
            BehaviorService.notify_parents(infraction, school, request.user)

        redirect_url = f"/behavior/student/{student.id}/"
        msg = f"تم تسجيل مخالفة درجة {level} للطالب {student.full_name}"
        if level >= 3:
            redirect_url = "/behavior/committee/"
            msg += " — تم إحالتها للجنة الضبط"
        return htmx_redirect(redirect_url, msg=msg, msg_type="success")

    # GET — نموذج فارغ
    student_id_hint = request.GET.get("student_id", "")
    return render(
        request,
        "behavior/partials/quick_log_form.html",
        _quick_log_context(request.user, school, student_id_hint),
    )


def _quick_log_context(user, school, preselected_student_id=""):
    """Context مشترك لنموذج التسجيل السريع — يُظهر طلاب المعلم فقط."""
    students = _get_scoped_students(user, school)
    return {
        "students": students,
        "levels": BehaviorInfraction.LEVELS,
        "violation_categories": ViolationCategory.objects.filter(
            is_active=True, code__regex=r"^\d+-\d+$"
        ).order_by("degree", "code"),
        "preselected_student_id": str(preselected_student_id),
    }


# ── الملف السلوكي للطالب ─────────────────────────────────────
@login_required
@role_required(BEHAVIOR_MANAGE | BEHAVIOR_RECORD | BEHAVIOR_VIEW_ALL)
def student_behavior_profile(request, student_id):
    """الملف السلوكي للطالب — جميع مخالفاته ونقاطه المخصومة والمستعادة."""
    school = request.user.get_school()
    student = get_object_or_404(
        CustomUser,
        id=student_id,
        memberships__school=school,
        memberships__is_active=True,
    )

    # ── تقييد الوصول: المعلم/المنسق يرى طلابه فقط ──
    if not teacher_can_access_student(request.user, student.id):
        return HttpResponseForbidden(
            "<h2 dir='rtl' style='font-family:Tajawal,sans-serif;padding:40px;color:#B91C1C'>"
            "هذا الطالب ليس من طلابك — لا يمكنك عرض ملفه السلوكي.</h2>"
        )

    context = BehaviorService.get_student_profile(student)
    context["student"] = student
    context["can_report"] = BehaviorPermissions.can_report(request.user)
    context["is_committee"] = BehaviorPermissions.is_committee(request.user)
    context["can_summon"] = BehaviorPermissions.can_summon(request.user)
    return render(request, "behavior/student_profile.html", context)


# ── لجنة الضبط السلوكي ───────────────────────────────────────
@login_required
@role_required(BEHAVIOR_COMMITTEE)
def committee_dashboard(request):
    """لوحة لجنة الضبط السلوكي — المخالفات الجسيمة من الدرجة 3 و4."""
    if not BehaviorPermissions.is_committee(request.user):
        return HttpResponseForbidden("ليس لديك صلاحية الوصول إلى هذه الصفحة.")
    school = request.user.get_school()
    context = BehaviorService.get_committee_data(school)
    return render(request, "behavior/committee.html", context)


@login_required
@role_required(BEHAVIOR_COMMITTEE)
def committee_decision(request, infraction_id):
    """تسجيل قرار لجنة الضبط السلوكي في مخالفة جسيمة."""
    if not BehaviorPermissions.is_committee(request.user):
        messages.error(request, "غير مسموح.")
        return redirect("behavior:committee")

    school = request.user.get_school()
    infraction = get_object_or_404(
        BehaviorInfraction, id=infraction_id, level__in=[3, 4], school=school
    )
    if request.method == "POST":
        # نظام النقاط ملغى — restore_pts=0 دائماً
        msg, level = BehaviorService.apply_committee_decision(
            infraction=infraction,
            decision=request.POST.get("decision"),
            action=request.POST.get("action_taken", "").strip(),
            restore_pts=0,
            reason="",
            approved_by=request.user,
            suspension_type=request.POST.get("suspension_type", "internal"),
            suspension_days=int(request.POST.get("suspension_days", 1) or 1),
        )
        getattr(messages, level)(request, msg)
        return redirect("behavior:committee")

    from .constants import ESCALATION_STEPS as ESC_STEPS

    return render(
        request,
        "behavior/committee_decision.html",
        {
            "infraction": infraction,
            "escalation_steps": ESC_STEPS.get(infraction.level, []),
        },
    )


# ── تقرير سلوكي دوري ─────────────────────────────────────────
@login_required
@role_required(BEHAVIOR_RECORD | BEHAVIOR_MANAGE)
def behavior_report(request, student_id):
    """التقرير السلوكي الدوري للطالب — مع إمكانية الإرسال لولي الأمر."""
    if not BehaviorPermissions.can_report(request.user) and not request.user.is_superuser:
        return HttpResponseForbidden("ليس لديك صلاحية.")

    school = request.user.get_school()
    student = get_object_or_404(
        CustomUser,
        id=student_id,
        memberships__school=school,
        memberships__is_active=True,
    )

    # ── تقييد الوصول: المعلم/المنسق يرى طلابه فقط ──
    if not teacher_can_access_student(request.user, student.id):
        return HttpResponseForbidden(
            "<h2 dir='rtl' style='font-family:Tajawal,sans-serif;padding:40px;color:#B91C1C'>"
            "هذا الطالب ليس من طلابك.</h2>"
        )
    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)
    period = request.GET.get("period", "full")

    report = BehaviorService.get_student_report_data(student, school, period, year)

    sent_to = []
    if request.method == "POST" and request.POST.get("action") == "send":
        from notifications.services import NotificationService

        for link in report["parent_links"]:
            parent = link.parent
            if parent.email:
                body = (
                    f"ولي أمر الطالب: {parent.full_name}\n\n"
                    f"التقرير السلوكي للطالب: {student.full_name}\n"
                    f"الفترة: {report['period_label']} — {year}\n\n"
                    f"نقاط السلوك: {report['net_score']}/100 ({report['rating']})\n"
                    f"المخالفات: {report['infractions'].count()}\n\n"
                    f"مدرسة الشحانية الإعدادية الثانوية للبنين"
                )
                try:
                    NotificationService.send_email(
                        school=school,
                        recipient_email=parent.email,
                        subject=f"التقرير السلوكي — {student.full_name} — {report['period_label']}",
                        body_text=body,
                        student=student,
                        notif_type="behavior",
                        sent_by=request.user,
                    )
                    sent_to.append(parent.full_name)
                except Exception as e:
                    logger.error("behavior_report: email failed for %s: %s", parent.email, e)
        if sent_to:
            messages.success(request, f"تم إرسال التقرير لـ: {', '.join(sent_to)}")
        else:
            messages.warning(request, "لا يوجد بريد إلكتروني مسجَّل لأولياء الأمور.")
        return redirect(request.path + f"?year={year}&period={period}")

    return render(
        request,
        "behavior/behavior_report.html",
        {
            "student": student,
            "year": year,
            "period": period,
            "sent_to": sent_to,
            "period_choices": PERIOD_CHOICES,
            **report,
        },
    )


# ── تقرير إحصائي ─────────────────────────────────────────────
_STATS_TEACHER_ROLES = {"teacher", "coordinator", "ese_teacher"}
_STATS_ALLOWED_ROLES = BEHAVIOR_COMMITTEE | BEHAVIOR_VIEW_ALL | _STATS_TEACHER_ROLES


@login_required
@role_required(_STATS_ALLOWED_ROLES)
def behavior_statistics(request):
    """التقرير الإحصائي السلوكي — القيادة/اللجنة ترى الكل، المعلم/المنسق يرى طلابه فقط."""
    role = request.user.get_role()
    school = request.user.get_school()
    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)

    # المعلم/المنسق/معلم ESE → إحصائيات مقيّدة بطلابهم فقط
    if role in _STATS_TEACHER_ROLES:
        student_ids = get_teacher_student_ids(request.user)
        stats = BehaviorService.get_statistics_scoped(school, student_ids=student_ids)
        stats["is_scoped"] = True
    else:
        # القيادة ولجنة الضبط والأخصائيون → كل طلاب المدرسة
        _full_access = BEHAVIOR_MANAGE | BEHAVIOR_VIEW_ALL | BEHAVIOR_COMMITTEE
        if role not in _full_access and not request.user.is_superuser:
            return HttpResponseForbidden("للمدير ونائبيه واللجنة فقط.")
        stats = BehaviorService.get_statistics(school)
        stats["is_scoped"] = False

    stats["year"] = year
    return render(request, "behavior/statistics.html", stats)


# ── تصعيد إجراء ──────────────────────────────────────────────
@login_required
@role_required(BEHAVIOR_COMMITTEE)
def escalate_infraction(request, infraction_id):
    """تصعيد المخالفة إلى الخطوة التالية."""
    if not BehaviorPermissions.is_committee(request.user):
        return HttpResponseForbidden("غير مسموح.")
    school = request.user.get_school()
    infraction = get_object_or_404(BehaviorInfraction, id=infraction_id, school=school)
    if request.method == "POST":
        notes = request.POST.get("notes", "").strip()
        success, msg = BehaviorService.escalate_infraction(
            infraction,
            escalated_by=request.user,
            notes=notes,
        )
        if success:
            messages.success(request, f"⬆️ {msg}")
        else:
            messages.warning(request, msg)
        return redirect("behavior:student_profile", student_id=infraction.student.id)
    return redirect("behavior:committee")


# ── تسجيل إحالة أمنية ────────────────────────────────────────
@login_required
@role_required(BEHAVIOR_COMMITTEE)
def security_referral(request, infraction_id):
    """تسجيل إحالة أمنية لمخالفة من الدرجة الرابعة."""
    if not BehaviorPermissions.is_committee(request.user):
        return HttpResponseForbidden("غير مسموح.")
    school = request.user.get_school()
    infraction = get_object_or_404(BehaviorInfraction, id=infraction_id, level=4, school=school)

    if request.method == "POST":
        agency = request.POST.get("security_agency", "")
        ref_num = request.POST.get("reference_number", "").strip()
        notes = request.POST.get("security_notes", "").strip()
        success, msg = BehaviorService.record_security_referral(
            infraction,
            agency=agency,
            reference_number=ref_num,
            notes=notes,
            referred_by=request.user,
        )
        if success:
            messages.success(request, f"🔒 {msg}")
        else:
            messages.error(request, msg)
        return redirect("behavior:student_profile", student_id=infraction.student.id)

    from .constants import SECURITY_AGENCIES

    return render(
        request,
        "behavior/security_referral.html",
        {
            "infraction": infraction,
            "agencies": SECURITY_AGENCIES,
        },
    )


# ════════════════════════════════════════════════════════════════
# PDF النماذج
# ════════════════════════════════════════════════════════════════


def _render_behavior_pdf(template_name, context, filename):
    from django.template.loader import render_to_string

    from core.pdf_utils import render_pdf

    return render_pdf(render_to_string(template_name, context), filename)


@login_required
@role_required(BEHAVIOR_MANAGE)
def infraction_warning_pdf(request, infraction_id):
    """PDF: نموذج تحذير للطالب بسبب مخالفة سلوكية."""
    inf = get_object_or_404(BehaviorInfraction, id=infraction_id, school=request.user.get_school())
    ctx = BehaviorService.get_infraction_context(inf)
    ctx["received_by"] = request.user.full_name
    return _render_behavior_pdf(
        "behavior/pdf/student_warning.html",
        ctx,
        f"warning_{inf.student.national_id}_{inf.date}.pdf",
    )


@login_required
@role_required(BEHAVIOR_MANAGE)
def infraction_parent_pdf(request, infraction_id):
    """PDF: تعهد ولي الأمر المتعلق بمخالفة سلوكية."""
    inf = get_object_or_404(BehaviorInfraction, id=infraction_id, school=request.user.get_school())
    ctx = BehaviorService.get_infraction_context(inf)
    ctx["received_by"] = request.user.full_name
    return _render_behavior_pdf(
        "behavior/pdf/parent_undertaking.html",
        ctx,
        f"parent_undertaking_{inf.student.national_id}.pdf",
    )


@login_required
@role_required(BEHAVIOR_MANAGE)
def infraction_student_pdf(request, infraction_id):
    """PDF: تعهد الطالب المتعلق بمخالفة سلوكية."""
    inf = get_object_or_404(BehaviorInfraction, id=infraction_id, school=request.user.get_school())
    ctx = BehaviorService.get_infraction_context(inf)
    ctx["received_by"] = request.user.full_name
    return _render_behavior_pdf(
        "behavior/pdf/student_undertaking.html",
        ctx,
        f"student_undertaking_{inf.student.national_id}.pdf",
    )


@login_required
@role_required(BEHAVIOR_MANAGE | {"psychologist"})
def summon_parent(request, student_id=None):
    """استدعاء ولي أمر طالب — إرسال إشعار رسمي (إداري فقط)."""
    school = request.user.get_school()
    if not school:
        return HttpResponseForbidden("لم يتم تعيينك في مدرسة")

    from core.models.academic import ParentStudentLink

    SUMMON_CATEGORIES = [
        ("behavior", "سلوكي"),
        ("academic", "أكاديمي"),
        ("attendance", "حضور وغياب"),
        ("general", "عام"),
    ]
    URGENCY_LEVELS = [
        ("normal", "عادي"),
        ("urgent", "مستعجل"),
        ("emergency", "طارئ"),
    ]
    MEETING_PLACES = [
        ("principal_office", "مكتب المدير"),
        ("counseling", "مكتب الإرشاد"),
        ("meeting_room", "غرفة الاجتماعات"),
        ("other", "أخرى"),
    ]

    if request.method == "POST":
        sid = request.POST.get("student_id") or student_id
        reason = request.POST.get("reason", "").strip()
        category = request.POST.get("category", "behavior")
        urgency = request.POST.get("urgency", "normal")
        summon_date = request.POST.get("summon_date", "")
        summon_time = request.POST.get("summon_time", "")
        meeting_place = request.POST.get("meeting_place", "")
        meeting_place_other = request.POST.get("meeting_place_other", "").strip()

        if not sid or not reason:
            messages.error(request, "يجب اختيار الطالب وكتابة السبب")
            return redirect("behavior:summon_parent")

        student = get_object_or_404(CustomUser, pk=sid)

        from notifications.hub import NotificationHub

        # بناء عنوان الإشعار حسب الاستعجال
        urgency_label = dict(URGENCY_LEVELS).get(urgency, "عادي")
        category_label = dict(SUMMON_CATEGORIES).get(category, "عام")
        prefix = "🔴 " if urgency == "emergency" else "🟡 " if urgency == "urgent" else ""
        title = f"{prefix}استدعاء ولي أمر — {student.full_name}"

        # بناء نص الإشعار
        place_label = dict(MEETING_PLACES).get(meeting_place, "")
        if meeting_place == "other" and meeting_place_other:
            place_label = meeting_place_other

        body_parts = [
            f"التصنيف: {category_label}",
            f"درجة الاستعجال: {urgency_label}",
            f"السبب: {reason}",
        ]
        if summon_date:
            date_str = summon_date
            if summon_time:
                date_str += f" الساعة {summon_time}"
            body_parts.append(f"الموعد المطلوب: {date_str}")
        if place_label:
            body_parts.append(f"مكان الاجتماع: {place_label}")
        body_parts.append(f"من: {request.user.full_name}")
        body = "\n".join(body_parts)

        result = NotificationHub.dispatch_to_parents(
            event_type="parent_summon",
            school=school,
            student=student,
            title=title,
            body=body,
            related_url=f"/behavior/student/{student.pk}/",
            sent_by=request.user,
        )

        count = result.get("in_app", 0)
        if count:
            messages.success(request, f"تم إرسال الاستدعاء لـ {count} ولي أمر")
        else:
            messages.warning(request, "لم يُعثر على أولياء أمور مربوطين بهذا الطالب")

        return redirect("behavior:summon_parent")

    # GET — نموذج الاستدعاء (طلاب المعلم/المنسق فقط)
    students = _get_scoped_students(request.user, school)

    selected_student = None
    student_context = {}
    if student_id:
        selected_student = CustomUser.objects.filter(pk=student_id).first()
    if selected_student:
        # معلومات سياقية عن الطالب
        score_data = BehaviorService.get_student_score(selected_student)
        parent_links = ParentStudentLink.objects.filter(
            student=selected_student, school=school
        ).select_related("parent")
        active_infractions = BehaviorInfraction.objects.filter(
            student=selected_student, is_resolved=False
        ).count()
        # بيانات أولياء الأمور مع أرقام الهواتف
        parents_info = []
        for link in parent_links:
            parents_info.append(
                {
                    "name": link.parent.full_name,
                    "phone": link.parent.phone or "",
                    "relationship": link.get_relationship_display(),
                    "is_primary": link.is_primary,
                }
            )
        student_context = {
            "behavior_score": score_data.get("net_score", 100),
            "active_infractions": active_infractions,
            "parents_info": parents_info,
        }

    return render(
        request,
        "behavior/summon_parent.html",
        {
            "students": students,
            "selected_student": selected_student,
            "school": school,
            "categories": SUMMON_CATEGORIES,
            "urgency_levels": URGENCY_LEVELS,
            "meeting_places": MEETING_PLACES,
            "sender": request.user,
            **student_context,
        },
    )


@login_required
@role_required(BEHAVIOR_MANAGE | BEHAVIOR_VIEW_ALL | BEHAVIOR_RECORD)
def student_behavior_pdf(request, student_id):
    """تقرير سلوكي للطالب — A4 للطباعة (WeasyPrint)"""
    school = request.user.get_school()
    student = get_object_or_404(
        CustomUser,
        id=student_id,
        memberships__school=school,
        memberships__is_active=True,
    )

    # تقييد الوصول: المعلم/المنسق يرى طلابه فقط
    if not teacher_can_access_student(request.user, student.id):
        return HttpResponseForbidden(
            "<h2 dir='rtl' style='font-family:Tajawal,sans-serif;padding:40px;color:#B91C1C'>"
            "هذا الطالب ليس من طلابك — لا يمكنك طباعة تقريره السلوكي.</h2>"
        )

    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)
    period = request.GET.get("period", "full")

    report = BehaviorService.get_student_report_data(student, school, period, year)

    # جلب بيانات الفصل الدراسي
    from core.models import StudentEnrollment

    enrollment = (
        StudentEnrollment.objects.filter(
            student=student, class_group__school=school, is_active=True
        )
        .select_related("class_group")
        .first()
    )
    cg = enrollment.class_group if enrollment else None

    ctx = {
        "student": student,
        "school": school,
        "class_name": str(cg) if cg else None,
        "student_grade": cg.get_grade_display() if cg else None,
        "student_section": cg.section if cg else None,
        "academic_year": year,
        "generated_at": _tz.now(),
        **report,
    }
    filename = f"behavior_report_{student.national_id}_{year}.pdf"
    return _render_behavior_pdf("behavior/pdf/student_report.html", ctx, filename)


@login_required
def behavior_policy_pdf(request):
    """يخدم لائحة السلوك كملف PDF ثابت من static/docs/"""
    import os

    pdf_path = os.path.join(settings.BASE_DIR, "static", "docs", "behavior_policy_2025-2026.pdf")
    if not os.path.exists(pdf_path):
        raise Http404("ملف اللائحة غير موجود")
    return FileResponse(
        open(pdf_path, "rb"),
        content_type="application/pdf",
        as_attachment=False,
        filename="behavior_policy_2025-2026.pdf",
    )

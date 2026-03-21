# behavior/views.py — Thin views using BehaviorService
"""
وحدة السلوك الطلابي — SchoolOS V2
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Views نحيفة — كل Business Logic في behavior/services.py
"""
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseForbidden, FileResponse, Http404
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

_VALID_LEVELS = {1, 2, 3, 4}
_MAX_POINTS   = 100
_MAX_DESC_LEN = 2000

from core.models import BehaviorInfraction, BehaviorPointRecovery, CustomUser
from .services import (
    BehaviorService, BehaviorPermissions,
    POINTS_BY_LEVEL, PERIOD_CHOICES,
)


# ── لوحة التحكم ──────────────────────────────────────────────
@login_required
def behavior_dashboard(request):
    role = request.user.get_role()
    if role in ("parent", "student"):
        return HttpResponseForbidden("ليس لديك صلاحية الوصول إلى هذه الصفحة.")

    school = request.user.get_school()
    if not school:
        messages.error(request, "لم يتم العثور على مدرسة مرتبطة بحسابك.")
        return redirect("dashboard")

    context = BehaviorService.get_dashboard_stats(school)
    context["can_report"] = BehaviorPermissions.can_report(request.user)
    context["is_committee"] = BehaviorPermissions.is_committee(request.user)
    return render(request, "behavior/dashboard.html", context)


# ── تسجيل مخالفة جديدة ───────────────────────────────────────
@login_required
def report_infraction(request):
    if not BehaviorPermissions.can_report(request.user):
        messages.error(request, "ليس لديك صلاحية تسجيل المخالفات.")
        return redirect("behavior:dashboard")

    school = request.user.get_school()

    if request.method == "POST":
        student_id  = request.POST.get("student_id", "").strip()
        description = request.POST.get("description", "").strip()
        action      = request.POST.get("action_taken", "").strip()

        try:
            level  = int(request.POST.get("level", 1))
            points = int(request.POST.get("points_deducted", 0))
        except (ValueError, TypeError):
            messages.error(request, "قيم غير صحيحة — يرجى مراجعة الحقول.")
            level, points = 1, 0

        # ── Validation ──────────────────────────────────────────
        errors = []
        if not student_id:
            errors.append("يرجى اختيار الطالب.")
        if not description:
            errors.append("يرجى كتابة وصف المخالفة.")
        elif len(description) > _MAX_DESC_LEN:
            errors.append(f"الوصف لا يتجاوز {_MAX_DESC_LEN} حرف.")
        if level not in _VALID_LEVELS:
            errors.append("درجة المخالفة يجب أن تكون بين 1 و 4.")
        if not (0 <= points <= _MAX_POINTS):
            errors.append(f"نقاط الخصم يجب أن تكون بين 0 و {_MAX_POINTS}.")

        if errors:
            for err in errors:
                messages.error(request, err)
        else:
            student = get_object_or_404(CustomUser, id=student_id)
            with transaction.atomic():
                infraction = BehaviorInfraction.objects.create(
                    school=school, student=student, reported_by=request.user,
                    level=level, description=description,
                    action_taken=action, points_deducted=points,
                )
            messages.success(
                request,
                f"✅ تم تسجيل مخالفة من الدرجة {level} للطالب {student.full_name}"
            )
            # إشعار غير متزامن عبر Celery
            try:
                from notifications.tasks import notify_behavior_task
                notify_behavior_task.delay(
                    infraction_id=str(infraction.id),
                    reporter_id=str(request.user.id),
                )
            except Exception as e:
                logger.warning("Celery غير متاح — إشعار مباشر: %s", e)
                BehaviorService.notify_parents(infraction, school, request.user)

            if level >= 3:
                messages.warning(
                    request,
                    f"⚠️ تم إحالة المخالفة للجنة الضبط السلوكي لكونها من الدرجة {level}"
                )
                return redirect("behavior:committee")
            return redirect("behavior:student_profile", student_id=student.id)

    students = (
        CustomUser.objects.filter(
            memberships__school=school,
            memberships__role__name="student",
            memberships__is_active=True,
        ).order_by("full_name").distinct()
    )
    return render(request, "behavior/report_form.html", {
        "students": students,
        "POINTS_BY_LEVEL": POINTS_BY_LEVEL,
        "levels": BehaviorInfraction.LEVELS,
    })


# ── الملف السلوكي للطالب ─────────────────────────────────────
@login_required
def student_behavior_profile(request, student_id):
    student = get_object_or_404(CustomUser, id=student_id)
    context = BehaviorService.get_student_profile(student)
    context["student"] = student
    context["can_report"] = BehaviorPermissions.can_report(request.user)
    context["is_committee"] = BehaviorPermissions.is_committee(request.user)
    return render(request, "behavior/student_profile.html", context)


# ── استعادة النقاط ────────────────────────────────────────────
@login_required
def point_recovery_request(request, infraction_id):
    if not BehaviorPermissions.is_committee(request.user):
        messages.error(request, "استعادة النقاط مقتصرة على أعضاء لجنة الضبط السلوكي.")
        return redirect("behavior:dashboard")

    infraction = get_object_or_404(BehaviorInfraction, id=infraction_id)
    if hasattr(infraction, "recovery"):
        messages.warning(request, "تم معالجة هذه المخالفة مسبقاً.")
        return redirect("behavior:student_profile", student_id=infraction.student.id)

    if request.method == "POST":
        reason = request.POST.get("reason", "").strip()
        points = int(request.POST.get("points_restored", 0))
        if not reason:
            messages.error(request, "يرجى تحديد سبب استعادة النقاط.")
        elif points <= 0 or points > infraction.points_deducted:
            messages.error(request, f"النقاط يجب أن تكون بين 1 و {infraction.points_deducted}.")
        else:
            with transaction.atomic():
                BehaviorPointRecovery.objects.create(
                    infraction=infraction, reason=reason,
                    points_restored=points, approved_by=request.user,
                )
                infraction.is_resolved = True
                infraction.save()
            messages.success(request, f"✅ تمت استعادة {points} نقطة للطالب {infraction.student.full_name}")
            return redirect("behavior:student_profile", student_id=infraction.student.id)

    return render(request, "behavior/recovery_form.html", {"infraction": infraction})


# ── لجنة الضبط السلوكي ───────────────────────────────────────
@login_required
def committee_dashboard(request):
    if not BehaviorPermissions.is_committee(request.user):
        return HttpResponseForbidden("ليس لديك صلاحية الوصول إلى هذه الصفحة.")
    school = request.user.get_school()
    context = BehaviorService.get_committee_data(school)
    return render(request, "behavior/committee.html", context)


@login_required
def committee_decision(request, infraction_id):
    if not BehaviorPermissions.is_committee(request.user):
        messages.error(request, "غير مسموح.")
        return redirect("behavior:committee")

    infraction = get_object_or_404(BehaviorInfraction, id=infraction_id, level__in=[3, 4])
    if request.method == "POST":
        msg, level = BehaviorService.apply_committee_decision(
            infraction=infraction,
            decision=request.POST.get("decision"),
            action=request.POST.get("action_taken", "").strip(),
            restore_pts=int(request.POST.get("points_restored", 0)),
            reason=request.POST.get("recovery_reason", "").strip(),
            approved_by=request.user,
        )
        getattr(messages, level)(request, msg)
        return redirect("behavior:committee")
    return render(request, "behavior/committee_decision.html", {"infraction": infraction})


# ── تقرير سلوكي دوري ─────────────────────────────────────────
@login_required
def behavior_report(request, student_id):
    if not BehaviorPermissions.can_report(request.user) and not request.user.is_superuser:
        return HttpResponseForbidden("ليس لديك صلاحية.")

    school = request.user.get_school()
    student = get_object_or_404(CustomUser, id=student_id)
    year = request.GET.get("year", "2025-2026")
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
                        school=school, recipient_email=parent.email,
                        subject=f"التقرير السلوكي — {student.full_name} — {report['period_label']}",
                        body_text=body, student=student, notif_type="behavior", sent_by=request.user,
                    )
                    sent_to.append(parent.full_name)
                except Exception as e:
                    logger.error("behavior_report: email failed for %s: %s", parent.email, e)
        if sent_to:
            messages.success(request, f"تم إرسال التقرير لـ: {', '.join(sent_to)}")
        else:
            messages.warning(request, "لا يوجد بريد إلكتروني مسجَّل لأولياء الأمور.")
        return redirect(request.path + f"?year={year}&period={period}")

    return render(request, "behavior/behavior_report.html", {
        "student": student, "year": year, "period": period,
        "sent_to": sent_to, "period_choices": PERIOD_CHOICES, **report,
    })


# ── تقرير إحصائي ─────────────────────────────────────────────
@login_required
def behavior_statistics(request):
    if not BehaviorPermissions.is_committee(request.user):
        return HttpResponseForbidden("للمدير ونائبيه فقط.")
    school = request.user.get_school()
    year = request.GET.get("year", "2025-2026")
    stats = BehaviorService.get_statistics(school)
    stats["year"] = year
    return render(request, "behavior/statistics.html", stats)


# ════════════════════════════════════════════════════════════════
# PDF النماذج
# ════════════════════════════════════════════════════════════════

def _render_behavior_pdf(template_name, context, filename):
    from django.template.loader import render_to_string
    from core.pdf_utils import render_pdf
    return render_pdf(render_to_string(template_name, context), filename)


@login_required
def infraction_warning_pdf(request, infraction_id):
    inf = get_object_or_404(BehaviorInfraction, id=infraction_id, school=request.user.get_school())
    ctx = BehaviorService.get_infraction_context(inf)
    ctx["received_by"] = request.user.full_name
    return _render_behavior_pdf("behavior/pdf/student_warning.html", ctx,
                                f"warning_{inf.student.username}_{inf.date}.pdf")

@login_required
def infraction_parent_pdf(request, infraction_id):
    inf = get_object_or_404(BehaviorInfraction, id=infraction_id, school=request.user.get_school())
    ctx = BehaviorService.get_infraction_context(inf)
    ctx["received_by"] = request.user.full_name
    return _render_behavior_pdf("behavior/pdf/parent_undertaking.html", ctx,
                                f"parent_undertaking_{inf.student.username}.pdf")

@login_required
def infraction_student_pdf(request, infraction_id):
    inf = get_object_or_404(BehaviorInfraction, id=infraction_id, school=request.user.get_school())
    ctx = BehaviorService.get_infraction_context(inf)
    ctx["received_by"] = request.user.full_name
    return _render_behavior_pdf("behavior/pdf/student_undertaking.html", ctx,
                                f"student_undertaking_{inf.student.username}.pdf")

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


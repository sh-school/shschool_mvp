"""
notifications/views.py
لوحة إدارة الإشعارات للمدير
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.views.decorators.http import require_POST

from .models import NotificationLog, NotificationSettings
from .services import NotificationService
from operations.models import AbsenceAlert


@login_required
def notifications_dashboard(request):
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    year   = request.GET.get("year", "2025-2026")

    # آخر الإشعارات
    logs = NotificationLog.objects.filter(school=school).select_related(
        "student", "sent_by"
    ).order_by("-sent_at")[:50]

    # إحصائيات
    total  = NotificationLog.objects.filter(school=school).count()
    sent   = NotificationLog.objects.filter(school=school, status="sent").count()
    failed = NotificationLog.objects.filter(school=school, status="failed").count()

    # تنبيهات الغياب المعلقة
    pending_absence = AbsenceAlert.objects.filter(
        school=school, status="pending"
    ).select_related("student").count()

    # الطلاب الراسبون (لم يُرسل لهم)
    from assessments.models import AnnualSubjectResult
    failing_students = AnnualSubjectResult.objects.filter(
        school=school, academic_year=year, status="fail"
    ).values("student").distinct().count()

    # الإعدادات
    cfg, _ = NotificationSettings.objects.get_or_create(school=school)

    return render(request, "notifications/dashboard.html", {
        "logs":             logs,
        "total":            total,
        "sent":             sent,
        "failed":           failed,
        "pending_absence":  pending_absence,
        "failing_students": failing_students,
        "cfg":              cfg,
        "year":             year,
    })


@login_required
@require_POST
def send_absence_alerts(request):
    """إرسال كل تنبيهات الغياب المعلقة"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    sent, failed = NotificationService.send_pending_absence_alerts(
        school=school, sent_by=request.user
    )
    messages.success(request, f"✓ تم إرسال {sent} إشعار غياب" +
                               (f" — فشل {failed}" if failed else ""))
    return redirect("notifications_dashboard")


@login_required
@require_POST
def send_fail_alerts(request):
    """إرسال إشعارات الرسوب للسنة الدراسية"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    year   = request.POST.get("year", "2025-2026")
    sent, failed = NotificationService.send_fail_alerts_for_year(
        school=school, year=year, sent_by=request.user
    )
    messages.success(request, f"✓ تم إرسال {sent} إشعار رسوب" +
                               (f" — فشل {failed}" if failed else ""))
    return redirect("notifications_dashboard")


@login_required
@require_POST
def resend_notification(request, log_id):
    """إعادة إرسال إشعار فشل"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    log    = get_object_or_404(NotificationLog, id=log_id, school=school)

    if log.channel == "email":
        ok, err = NotificationService.send_email(
            school          = school,
            recipient_email = log.recipient,
            subject         = log.subject,
            body_text       = log.body,
            student         = log.student,
            notif_type      = log.notif_type,
            sent_by         = request.user,
        )
    else:
        ok, err = NotificationService.send_sms(
            school       = school,
            phone_number = log.recipient,
            message      = log.body,
            student      = log.student,
            notif_type   = log.notif_type,
            sent_by      = request.user,
        )

    if ok:
        messages.success(request, f"✓ أُعيد إرسال الإشعار إلى {log.recipient}")
    else:
        messages.error(request, f"فشل: {err}")
    return redirect("notifications_dashboard")


@login_required
def save_settings(request):
    """حفظ إعدادات الإشعارات"""
    if not request.user.is_admin() or request.method != "POST":
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    cfg, _ = NotificationSettings.objects.get_or_create(school=school)

    cfg.email_enabled         = "email_enabled"         in request.POST
    cfg.absence_email_enabled = "absence_email_enabled" in request.POST
    cfg.fail_email_enabled    = "fail_email_enabled"    in request.POST
    cfg.sms_enabled           = "sms_enabled"           in request.POST
    cfg.absence_threshold     = int(request.POST.get("absence_threshold", 3))
    cfg.from_name             = request.POST.get("from_name", school.name)
    cfg.reply_to              = request.POST.get("reply_to", "")
    cfg.sms_from_number       = request.POST.get("sms_from_number", "")
    cfg.twilio_account_sid    = request.POST.get("twilio_account_sid", "")
    cfg.twilio_auth_token     = request.POST.get("twilio_auth_token", "")
    cfg.absence_email_subject = request.POST.get("absence_email_subject", cfg.absence_email_subject)
    cfg.fail_email_subject    = request.POST.get("fail_email_subject", cfg.fail_email_subject)
    cfg.save()

    messages.success(request, "✓ تم حفظ إعدادات الإشعارات")
    return redirect("notifications_dashboard")

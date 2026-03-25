"""
notifications/views.py
لوحة إدارة الإشعارات للمدير
"""

import logging

from django.conf import settings
from django.contrib import messages

logger = logging.getLogger(__name__)
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.permissions import leadership_required
from operations.models import AbsenceAlert

from .models import NotificationLog, NotificationSettings
from .services import NotificationService


@login_required
@leadership_required
def notifications_dashboard(request):
    school = request.user.get_school()
    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)

    # آخر الإشعارات
    logs = (
        NotificationLog.objects.filter(school=school)
        .select_related("student", "sent_by")
        .order_by("-sent_at")[:50]
    )

    # إحصائيات
    total = NotificationLog.objects.filter(school=school).count()
    sent = NotificationLog.objects.filter(school=school, status="sent").count()
    failed = NotificationLog.objects.filter(school=school, status="failed").count()

    # تنبيهات الغياب المعلقة
    pending_absence = (
        AbsenceAlert.objects.filter(school=school, status="pending")
        .select_related("student")
        .count()
    )

    # الطلاب الراسبون (لم يُرسل لهم)
    from assessments.models import AnnualSubjectResult

    failing_students = (
        AnnualSubjectResult.objects.filter(school=school, academic_year=year, status="fail")
        .values("student")
        .distinct()
        .count()
    )

    # الإعدادات
    cfg, _ = NotificationSettings.objects.get_or_create(school=school)

    return render(
        request,
        "notifications/dashboard.html",
        {
            "logs": logs,
            "total": total,
            "sent": sent,
            "failed": failed,
            "pending_absence": pending_absence,
            "failing_students": failing_students,
            "cfg": cfg,
            "year": year,
        },
    )


@login_required
@leadership_required
@require_POST
def send_absence_alerts(request):
    """إرسال كل تنبيهات الغياب المعلقة"""
    school = request.user.get_school()
    sent, failed = NotificationService.send_pending_absence_alerts(
        school=school, sent_by=request.user
    )
    messages.success(
        request, f"✓ تم إرسال {sent} إشعار غياب" + (f" — فشل {failed}" if failed else "")
    )
    return redirect("notifications_dashboard")


@login_required
@leadership_required
@require_POST
def send_fail_alerts(request):
    """إرسال إشعارات الرسوب للسنة الدراسية"""
    school = request.user.get_school()
    year = request.POST.get("year", settings.CURRENT_ACADEMIC_YEAR)
    sent, failed = NotificationService.send_fail_alerts_for_year(
        school=school, year=year, sent_by=request.user
    )
    messages.success(
        request, f"✓ تم إرسال {sent} إشعار رسوب" + (f" — فشل {failed}" if failed else "")
    )
    return redirect("notifications_dashboard")


@login_required
@leadership_required
@require_POST
def resend_notification(request, log_id):
    """إعادة إرسال إشعار فشل"""
    school = request.user.get_school()
    log = get_object_or_404(NotificationLog, id=log_id, school=school)

    if log.channel == "email":
        ok, err = NotificationService.send_email(
            school=school,
            recipient_email=log.recipient,
            subject=log.subject,
            body_text=log.body,
            student=log.student,
            notif_type=log.notif_type,
            sent_by=request.user,
        )
    else:
        ok, err = NotificationService.send_sms(
            school=school,
            phone_number=log.recipient,
            message=log.body,
            student=log.student,
            notif_type=log.notif_type,
            sent_by=request.user,
        )

    if ok:
        messages.success(request, f"✓ أُعيد إرسال الإشعار إلى {log.recipient}")
    else:
        messages.error(request, f"فشل: {err}")
    return redirect("notifications_dashboard")


@login_required
@leadership_required
def save_settings(request):
    """حفظ إعدادات الإشعارات"""
    if request.method != "POST":
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    cfg, _ = NotificationSettings.objects.get_or_create(school=school)

    cfg.email_enabled = "email_enabled" in request.POST
    cfg.absence_email_enabled = "absence_email_enabled" in request.POST
    cfg.fail_email_enabled = "fail_email_enabled" in request.POST
    cfg.sms_enabled = "sms_enabled" in request.POST
    cfg.absence_threshold = int(request.POST.get("absence_threshold", 3))
    cfg.from_name = request.POST.get("from_name", school.name)
    cfg.reply_to = request.POST.get("reply_to", "")
    cfg.sms_from_number = request.POST.get("sms_from_number", "")
    cfg.twilio_account_sid = request.POST.get("twilio_account_sid", "")
    cfg.twilio_auth_token = request.POST.get("twilio_auth_token", "")
    cfg.absence_email_subject = request.POST.get("absence_email_subject", cfg.absence_email_subject)
    cfg.fail_email_subject = request.POST.get("fail_email_subject", cfg.fail_email_subject)
    cfg.save()

    messages.success(request, "✓ تم حفظ إعدادات الإشعارات")
    return redirect("notifications_dashboard")


# ════════════════════════════════════════════════════════════════════
# ✅ v6: إشعارات المنصة — الجرس + الصندوق + التفضيلات
# ════════════════════════════════════════════════════════════════════

from .models import InAppNotification, UserNotificationPreference


@login_required
def api_unread_count(request):
    """API: عدد الإشعارات غير المقروءة (للجرس في Navbar)"""
    count = InAppNotification.objects.unread_count(request.user)
    return JsonResponse({"count": count})


@login_required
def api_recent_notifications(request):
    """API: آخر 5 إشعارات (للقائمة المنسدلة في الجرس)"""
    notifs = InAppNotification.objects.unread_for_user(request.user)[:5]
    data = [
        {
            "id": str(n.id),
            "title": n.title,
            "body": n.body[:100],
            "event_type": n.event_type,
            "priority": n.priority,
            "url": n.related_url,
            "created_at": n.created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for n in notifs
    ]
    count = InAppNotification.objects.unread_count(request.user)
    return JsonResponse({"notifications": data, "unread_count": count})


@login_required
def notification_inbox(request):
    """صفحة صندوق الإشعارات"""
    event_filter = request.GET.get("type", "")
    qs = InAppNotification.objects.filter(user=request.user)
    if event_filter:
        qs = qs.filter(event_type=event_filter)

    notifications = qs.order_by("-created_at")[:100]
    unread_count = InAppNotification.objects.unread_count(request.user)

    # فلترة أنواع الإشعارات حسب الدور
    PARENT_TYPES = {"behavior", "absence", "grade", "fail", "clinic", "sent_home", "meeting", "general"}
    STUDENT_TYPES = {"grade", "fail", "behavior", "absence", "clinic", "general"}
    role = getattr(request.user, "get_role", lambda: "")()
    if role == "parent":
        visible_types = [t for t in InAppNotification.EVENT_TYPES if t[0] in PARENT_TYPES]
    elif role == "student":
        visible_types = [t for t in InAppNotification.EVENT_TYPES if t[0] in STUDENT_TYPES]
    else:
        visible_types = InAppNotification.EVENT_TYPES

    return render(
        request,
        "notifications/inbox.html",
        {
            "notifications": notifications,
            "unread_count": unread_count,
            "event_filter": event_filter,
            "event_types": visible_types,
        },
    )


@login_required
@require_POST
def mark_notification_read(request, notif_id):
    """تحديد إشعار واحد كمقروء"""
    import json

    notif = get_object_or_404(InAppNotification, id=notif_id, user=request.user)
    notif.mark_read()

    if request.headers.get("HX-Request"):
        # HTMX: أعد العنصر المحدَّث (is_read=True) + أطلق حدث تحديث الـ badge
        count = InAppNotification.objects.unread_count(request.user)
        response = render(request, "notifications/partials/notif_item.html", {"notif": notif})
        response["HX-Trigger"] = json.dumps({"updateBadge": {"count": count}})
        return response

    return redirect(notif.related_url or "notification_inbox")


@login_required
@require_POST
def mark_all_read(request):
    """تحديد كل الإشعارات كمقروءة"""
    InAppNotification.objects.mark_all_read(request.user)

    if request.headers.get("HX-Request"):
        return HttpResponse("0")

    messages.success(request, "✓ تم تحديد كل الإشعارات كمقروءة")
    return redirect("notification_inbox")


@login_required
def notification_preferences(request):
    """صفحة تفضيلات الإشعارات للمستخدم"""
    prefs, created = UserNotificationPreference.objects.get_or_create(user=request.user)

    if request.method == "POST":
        prefs.in_app_enabled = "in_app_enabled" in request.POST
        prefs.push_enabled = "push_enabled" in request.POST
        prefs.whatsapp_enabled = "whatsapp_enabled" in request.POST
        prefs.email_enabled = "email_enabled" in request.POST
        prefs.sms_enabled = "sms_enabled" in request.POST

        # ساعات الهدوء
        quiet_start = request.POST.get("quiet_hours_start", "")
        quiet_end = request.POST.get("quiet_hours_end", "")
        if quiet_start:
            from datetime import time as dt_time

            h, m = map(int, quiet_start.split(":"))
            prefs.quiet_hours_start = dt_time(h, m)
        else:
            prefs.quiet_hours_start = None
        if quiet_end:
            from datetime import time as dt_time

            h, m = map(int, quiet_end.split(":"))
            prefs.quiet_hours_end = dt_time(h, m)
        else:
            prefs.quiet_hours_end = None

        prefs.save()
        messages.success(request, "✓ تم حفظ تفضيلات الإشعارات")
        return redirect("notification_preferences")

    return render(
        request,
        "notifications/preferences.html",
        {
            "prefs": prefs,
        },
    )


# ══════════════════════════════════════════════════════════════
# ✅ v5.1: البث الطارئ عبر WebSocket (مدير / مدير مدرسة فقط)
# ══════════════════════════════════════════════════════════════


@login_required
@require_POST
def emergency_broadcast(request):
    """
    يبث رسالة طارئة لجميع مستخدمي المدرسة المتصلين عبر WebSocket.
    مقيَّد للمدير والمدير المساعد فقط.
    """
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    from core.permissions import is_admin_or_principal

    if not is_admin_or_principal(request.user):
        return JsonResponse({"error": "غير مصرح"}, status=403)

    message = request.POST.get("message", "").strip()
    if not message:
        return JsonResponse({"error": "الرسالة فارغة"}, status=400)

    school = request.user.school
    if not school:
        return JsonResponse({"error": "لا مدرسة مرتبطة بالمستخدم"}, status=400)

    layer = get_channel_layer()
    if not layer:
        return JsonResponse({"error": "WebSocket غير مُعدَّل"}, status=503)

    try:
        async_to_sync(layer.group_send)(
            f"school_{school.pk}",
            {
                "type": "emergency.broadcast",
                "message": message,
            },
        )
        return JsonResponse({"status": "ok", "recipients": f"school_{school.pk}"})
    except (OSError, RuntimeError, ValueError) as exc:
        logger.exception("Emergency broadcast failed: %s", exc)
        return JsonResponse({"error": "فشل الإرسال"}, status=500)

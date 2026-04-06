"""
operations/tasks.py
مهام Celery المُجدوَلة لنظام العمليات
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

المهام:
    1. توليد الحصص اليومية (أحد–خميس 6:00 صباحاً) — BACKUP فقط
    2. فحص انتهاء الرخص المهنية (يومياً — تنبيه قبل 60 يوماً)

⚠️ ملاحظة مهمة:
    توليد الحصص لم يعد يعتمد على Celery كمسار أساسي.
    النظام الأساسي هو SessionAutoGenerateMiddleware + ensure_sessions_for_date()
    الذي يولّد الحصص تلقائياً عند أول طلب من أي مستخدم.

    مهمة Celery هنا تبقى كـ backup اختياري:
    - إذا Celery يعمل → يولّد الحصص مسبقاً 6:00 صباحاً (جيد)
    - إذا Celery لا يعمل → الـ middleware يتكفل بالتوليد (المنصة تعمل عادي)

الاستخدام:
    # يدوي (من shell أو view):
    generate_daily_sessions_task.delay()                  # كل المدارس
    generate_daily_sessions_task.delay(school_id="...")    # مدرسة واحدة
    check_license_expiry_task.delay()                     # فحص كل الرخص
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════
# إلغاء الصلاحيات المؤقتة المنتهية — يعمل كل دقيقة عبر Celery Beat
# ═════════════════════════════════════════════════════════════════════


@shared_task(name="operations.revoke_expired_temp_permissions")
def revoke_expired_temp_permissions():
    """
    مهمة مُجدوَلة — تُشغَّل كل دقيقة من Celery Beat.

    تُلغي كل صلاحية مؤقتة (TemporaryPermission) انتهت صلاحيتها
    (valid_until < now) وحالتها "active".

    تُسجّل كل إلغاء في PermissionAuditLog.
    """
    from django.utils import timezone

    from operations.models import PermissionAuditLog, TemporaryPermission

    now = timezone.now()

    expired = TemporaryPermission.objects.filter(
        status="active",
        valid_until__lt=now,
    ).select_related("teacher", "class_group")

    count = 0
    for perm in expired.iterator(chunk_size=100):
        perm.status = "expired"
        perm.revoked_at = now
        perm.save(update_fields=["status", "revoked_at"])

        PermissionAuditLog.objects.create(
            temp_permission=perm,
            action="auto_revoked",
            notes=f"انتهت صلاحية الإذن تلقائياً عند {now.strftime('%H:%M')}",
        )
        count += 1

    if count:
        logger.info(
            "revoke_expired_temp_permissions: %d permissions auto-revoked at %s",
            count,
            now.strftime("%Y-%m-%d %H:%M"),
        )

    return {"revoked": count, "checked_at": str(now)}


@shared_task(
    name="operations.generate_daily_sessions",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
)
def generate_daily_sessions_task(self, school_id=None):
    """
    توليد Session يومية من ScheduleSlot لجميع المدارس النشطة.

    - idempotent: get_or_create يمنع التكرار
    - يعمل عبر Celery Beat (أحد–خميس 6:00 صباحاً)
    - يُستدعى أيضاً يدوياً من شاشة الإدارة
    """
    try:
        from django.utils import timezone

        from core.models import School
        from operations.services import ScheduleService

        today = timezone.localdate()

        if school_id:
            schools = School.objects.filter(id=school_id, is_active=True)
        else:
            schools = School.objects.filter(is_active=True)

        total = 0
        for school in schools:
            count = ScheduleService.generate_daily_sessions(school, today)
            total += count
            if count > 0:
                logger.info(
                    "generate_daily_sessions: %d sessions for %s on %s",
                    count,
                    school.name,
                    today,
                )

        logger.info(
            "generate_daily_sessions_task complete: %d sessions total on %s",
            total,
            today,
        )
        return {"date": str(today), "total_sessions": total}

    except Exception as exc:
        logger.exception("generate_daily_sessions_task error: %s", exc)
        raise self.retry(exc=exc)


# ═════════════════════════════════════════════════════════════════════
# فحص انتهاء الرخص المهنية — نظام الرخص المهنية (قطر)
# تنبيه المدير والموظف قبل 60 يوماً من انتهاء الرخصة
# ═════════════════════════════════════════════════════════════════════


@shared_task(name="operations.check_license_expiry")
def check_license_expiry_task():
    """
    مهمة مُجدوَلة — تُشغَّل يومياً من Celery Beat.

    تتحقق من الرخص المهنية التي ستنتهي خلال 60 يوماً
    وترسل إشعاراً للموظف ومدير المدرسة.
    """
    from datetime import timedelta

    from django.utils import timezone

    from core.models import CustomUser, Membership

    today = timezone.localdate()
    warning_date = today + timedelta(days=60)

    # الموظفون الذين تنتهي رخصهم خلال 60 يوماً (ولم تنتهِ بعد)
    expiring = (
        CustomUser.objects.filter(
            professional_license_expiry__isnull=False,
            professional_license_expiry__lte=warning_date,
            professional_license_expiry__gte=today,
            is_active=True,
        )
        .exclude(professional_license_number="")
        .select_related()
    )

    alerted = 0
    for user in expiring.iterator(chunk_size=200):
        days_left = (user.professional_license_expiry - today).days

        # العثور على المدرسة والمدير
        membership = (
            Membership.objects.filter(user=user, is_active=True).select_related("school").first()
        )
        if not membership:
            continue

        school = membership.school

        # إرسال إشعار عبر Hub (إن وُجد)
        try:
            from notifications.hub import NotificationHub

            # إشعار الموظف
            NotificationHub.send(
                user=user,
                school=school,
                event_type="license_expiry",
                title="تنبيه: رخصتك المهنية تقترب من الانتهاء",
                body=(
                    f"رخصتك المهنية رقم {user.professional_license_number} "
                    f"ستنتهي خلال {days_left} يوماً "
                    f"({user.professional_license_expiry}). "
                    "يرجى التجديد قبل انتهاء الصلاحية."
                ),
                channels=["in_app", "push"],
            )

            # إشعار المدير
            principal_membership = (
                Membership.objects.filter(
                    school=school,
                    role__name="principal",
                    is_active=True,
                )
                .select_related("user")
                .first()
            )
            if principal_membership:
                NotificationHub.send(
                    user=principal_membership.user,
                    school=school,
                    event_type="license_expiry",
                    title=f"تنبيه: رخصة {user.full_name} تقترب من الانتهاء",
                    body=(
                        f"الرخصة المهنية للموظف {user.full_name} "
                        f"(رقم {user.professional_license_number}) "
                        f"ستنتهي خلال {days_left} يوماً."
                    ),
                    channels=["in_app"],
                )

            alerted += 1

        except Exception as e:
            logger.warning(
                "license_expiry alert failed for %s: %s",
                user.full_name,
                e,
            )

    logger.info(
        "check_license_expiry_task: %d staff alerted (expiring within 60 days)",
        alerted,
    )
    return {"alerted": alerted, "checked_date": str(today)}

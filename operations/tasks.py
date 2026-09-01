"""
operations/tasks.py
مهام Celery المُجدوَلة لنظام العمليات
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

المهام:
    1. توليد الحصص اليومية (أحد–خميس 6:00 صباحاً) — BACKUP فقط
    2. فحص انتهاء الرخص المهنية (يومياً — تنبيه قبل 60 يوماً)
    3. توليد الجدول الأسبوعيّ الذكيّ — بطلب المستخدم لا بجدولٍ زمنيّ

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

from core.celery_tasks import school_rls_scope

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════
# إلغاء الصلاحيات المؤقتة المنتهية — يعمل كل دقيقة عبر Celery Beat
# ═════════════════════════════════════════════════════════════════════


@shared_task(name="operations.revoke_expired_temp_permissions")
def revoke_expired_temp_permissions():
    """Expire temporary permissions school-by-school."""
    from django.utils import timezone

    from core.models import School
    from operations.models import (
        PermissionAuditLog,
        TemporaryPermission,
    )

    now = timezone.now()
    total_count = 0

    schools = School.objects.all()

    for school in schools.iterator(chunk_size=100):
        with school_rls_scope(school.id):
            expired = TemporaryPermission.objects.filter(
                school=school,
                status="active",
                valid_until__lt=now,
            ).select_related("teacher", "class_group")

            school_count = 0

            for perm in expired.iterator(chunk_size=100):
                perm.status = "expired"
                perm.revoked_at = now
                perm.save(update_fields=["status", "revoked_at"])

                PermissionAuditLog.objects.create(
                    temp_permission=perm,
                    action="auto_revoked",
                    notes=("انتهت صلاحية الإذن تلقائياً عند " f"{now.strftime('%H:%M')}"),
                )

                school_count += 1
                total_count += 1

            if school_count:
                logger.info(
                    "revoke_expired_temp_permissions: " "%d permissions auto-revoked for %s",
                    school_count,
                    school.name,
                )

    return {
        "revoked": total_count,
        "checked_at": str(now),
    }


@shared_task(
    name="operations.generate_daily_sessions",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
)
def generate_daily_sessions_task(self, school_id=None):
    """Generate daily sessions inside one RLS scope per school."""
    try:
        from django.utils import timezone

        from core.models import School
        from operations.services import ScheduleService

        today = timezone.localdate()

        schools = School.objects.filter(is_active=True)

        if school_id:
            schools = schools.filter(id=school_id)

        total = 0

        for school in schools.iterator(chunk_size=100):
            with school_rls_scope(school.id):
                count = ScheduleService.generate_daily_sessions(
                    school,
                    today,
                )

                total += count

                if count > 0:
                    logger.info(
                        "generate_daily_sessions: " "%d sessions for %s on %s",
                        count,
                        school.name,
                        today,
                    )

        logger.info(
            "generate_daily_sessions_task complete: " "%d sessions total on %s",
            total,
            today,
        )

        return {
            "date": str(today),
            "total_sessions": total,
        }

    except Exception as exc:
        logger.exception(
            "generate_daily_sessions_task error: %s",
            exc,
        )
        raise self.retry(exc=exc)


# ═════════════════════════════════════════════════════════════════════
# فحص انتهاء الرخص المهنية — نظام الرخص المهنية (قطر)
# تنبيه المدير والموظف قبل 60 يوماً من انتهاء الرخصة
# ═════════════════════════════════════════════════════════════════════


@shared_task(name="operations.check_license_expiry")
def check_license_expiry_task():
    """Check expiring professional licences under the legacy school selection contract."""
    from datetime import timedelta

    from django.utils import timezone

    from core.models import CustomUser, Membership

    today = timezone.localdate()
    warning_date = today + timedelta(days=60)

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
        membership = (
            Membership.objects.filter(
                user=user,
                is_active=True,
            )
            .select_related("school")
            .first()
        )

        if not membership:
            continue

        school = membership.school

        with school_rls_scope(school.id):
            days_left = (user.professional_license_expiry - today).days

            try:
                from notifications.hub import NotificationHub

                NotificationHub.send(
                    user=user,
                    school=school,
                    event_type="license_expiry",
                    title="تنبيه: رخصتك المهنية تقترب من الانتهاء",
                    body=(
                        f"رخصتك المهنية رقم "
                        f"{user.professional_license_number} "
                        f"ستنتهي خلال {days_left} يوماً "
                        f"({user.professional_license_expiry}). "
                        "يرجى التجديد قبل انتهاء الصلاحية."
                    ),
                    channels=["in_app", "push"],
                )

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
                        title=(f"تنبيه: رخصة {user.full_name} " "تقترب من الانتهاء"),
                        body=(
                            f"الرخصة المهنية للموظف "
                            f"{user.full_name} "
                            f"(رقم "
                            f"{user.professional_license_number}) "
                            f"ستنتهي خلال {days_left} يوماً."
                        ),
                        channels=["in_app"],
                    )

                alerted += 1

            except Exception as exc:
                logger.warning(
                    "license_expiry alert failed for %s: %s",
                    user.full_name,
                    exc,
                )

    logger.info(
        "check_license_expiry_task: " "%d staff alerted (expiring within 60 days)",
        alerted,
    )

    return {
        "alerted": alerted,
        "checked_date": str(today),
    }


# ═════════════════════════════════════════════════════════════════════
# توليد الجدول الأسبوعيّ الذكيّ — بطلب المستخدم
# ═════════════════════════════════════════════════════════════════════


@shared_task(
    name="operations.generate_smart_schedule",
    bind=True,
    max_retries=0,
    soft_time_limit=900,
    time_limit=960,
)
def generate_smart_schedule_task(self, generation_id):
    """يُشغّل مولّد الجدول خارج دورة الطلب، ويكتب مصيرَه في صفّ التوليد.

    قِيس زمنُ التوليد في هذه المدرسة فكان بين ٤٢ ثانيةً و٢٧٩ — و`gunicorn`
    يقطع عند مئةٍ وعشرين، و`nginx` كذلك. فالزرُّ المتزامنُ كان يَعِد بجدولٍ
    ويُسلّم خطأَ بوّابةٍ بعد دقيقتين، والتوليدُ يمضي في عاملٍ مقطوعِ الصلة.

    ولا إعادةَ محاولةٍ تلقائيّة (`max_retries=0`): التوليدُ يستبدل جدولَ
    المدرسة كلَّه، وإعادتُه بلا طلبٍ صريحٍ فعلٌ لا يُؤذَن به مرّتين بإذنٍ واحد.
    """
    from celery.exceptions import SoftTimeLimitExceeded
    from django.utils import timezone

    from operations.models import ScheduleGeneration

    try:
        generation = ScheduleGeneration.objects.select_related("school", "generated_by").get(
            pk=generation_id
        )
    except ScheduleGeneration.DoesNotExist:
        logger.warning("generate_smart_schedule: صفُّ التوليد %s غير موجود", generation_id)
        return {"ok": False, "reason": "generation_not_found"}

    if generation.status not in ScheduleGeneration.PENDING_STATUSES:
        # التقاطٌ مكرَّرٌ لرسالةٍ واحدة — والتوليدُ لا يُعاد على نتيجةٍ قائمة.
        logger.info("generate_smart_schedule: %s ليس في الانتظار — يُتخطّى", generation_id)
        return {"ok": False, "reason": "not_pending", "status": generation.status}

    school = generation.school
    generation.status = "running"
    generation.save(update_fields=["status"])

    def _fail(message):
        generation.status = "failed"
        generation.error_message = message[:2000]
        generation.finished_at = timezone.now()
        generation.save(update_fields=["status", "error_message", "finished_at"])
        _notify_generation_done(generation, ok=False, summary=message)

    try:
        with school_rls_scope(school.id):
            from operations.scheduler import generate_schedule

            # مسودّةٌ لا نشر: الحصصُ تُربط بصفّ التوليد وتبقى مطفأةً حتّى
            # يعتمدها المدير — وعندها فقط تحلّ محلَّ الجدول الحيّ.
            result = generate_schedule(
                school,
                generation.academic_year,
                user=generation.generated_by,
                generation=generation,
                publish=False,
            )
    except SoftTimeLimitExceeded:
        logger.error("generate_smart_schedule: تجاوز الزمنَ المسموح — %s", generation_id)
        _fail("تجاوز التوليدُ الزمنَ المسموح (خمس عشرة دقيقة) فأُوقف.")
        return {"ok": False, "reason": "soft_time_limit"}
    except Exception as exc:  # noqa: BLE001 — يُسجَّل ويُقال، ولا يُبتلع
        logger.exception("generate_smart_schedule: فشل التوليد — %s", exc)
        _fail(f"خطأ في التوليد: {exc}")
        return {"ok": False, "reason": "exception"}

    quality = result["quality"]
    summary = (
        f"{quality['total_slots']}/{quality['total_required']} حصّة "
        f"({quality['placed_ratio']}%) — جودةُ التوزيع {quality['score']}% "
        f"في {result['elapsed_ms']}ms"
    )

    if result["generation"] is None:
        # لم يُحفَظ شيء — والصفُّ ما زال «قيد التوليد»، فلا يُترك معلّقاً أبداً.
        _fail("؛ ".join(result["errors"]) or "تعذّر حفظ الجدول المولَّد.")
        return {"ok": False, "reason": "not_saved"}

    if result["errors"]:
        generation.error_message = "؛ ".join(result["errors"])[:2000]
        generation.save(update_fields=["error_message"])

    _notify_generation_done(generation, ok=result["success"], summary=summary)
    return {"ok": result["success"], "summary": summary, "failed": len(result["errors"])}


def _notify_generation_done(generation, *, ok, summary):
    """يُخبر من ضغط الزرَّ بالنتيجة — فقد يمضي على التوليد دقائقُ يغادر فيها."""
    if generation.generated_by_id is None:
        return
    try:
        from notifications.models import InAppNotification

        InAppNotification.objects.create(
            user_id=generation.generated_by_id,
            school=generation.school,
            title="انتهى توليد الجدول" if ok else "تعذّر توليد الجدول",
            body=summary,
            event_type="general",
            priority="medium" if ok else "high",
            related_url="/teacher/smart-schedule/",
        )
    except Exception as exc:  # noqa: BLE001 — الإشعارُ خدمةٌ لا شرطٌ للنجاح
        logger.warning("تعذّر إشعارُ صاحب التوليد: %s", exc)

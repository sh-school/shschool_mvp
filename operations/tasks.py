"""
operations/tasks.py
مهام Celery المُجدوَلة لنظام العمليات
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

المهام:
    1. فحص انتهاء الرخص المهنية (يومياً — تنبيه قبل 60 يوماً)
    2. توليد الجدول الأسبوعيّ الذكيّ — بطلب المستخدم لا بجدولٍ زمنيّ
    3. حارسُ العام الدراسيّ — إطفاءُ جداول وإسنادات الأعوام الماضية (يومياً)
    4. نهايةُ الحصص — أثرُ «خرج بإذن» فيما ثبّته المشرف (كلَّ خمس دقائق في الدوام)

ملاحظة:
    توليدُ حصص اليوم ليس مهمّةَ Celery: يتكفّل به SessionAutoGenerateMiddleware
    عبر ensure_sessions_for_date() عند أوّل طلبٍ من أيّ مستخدم، وهو idempotent
    ويحتمل التكرار. وكانت هنا مهمّةُ backup تستدعي مساراً ثانياً يُدرج بمفتاحٍ
    يضمّ المعلّم بينما قيدُ القاعدة بلا معلّم، فتسقط على حصص الاختيار — فأُزيلت.

الاستخدام:
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
                    notes=(f"انتهت صلاحية الإذن تلقائياً عند {now.strftime('%H:%M')}"),
                )

                school_count += 1
                total_count += 1

            if school_count:
                logger.info(
                    "revoke_expired_temp_permissions: %d permissions auto-revoked for %s",
                    school_count,
                    school.name,
                )

    return {
        "revoked": total_count,
        "checked_at": str(now),
    }


# ═════════════════════════════════════════════════════════════════════
# نهايةُ الحصص — من خرج بإذن المعلّم ولم يعد حتى الجرس (قرارُ 2026-09-16)
# ═════════════════════════════════════════════════════════════════════


@shared_task(name="operations.finalize_period_exits")
def finalize_period_exits_task():
    """يُغلق خروجَ الحصص المنتهية اليومَ ويقلب الحاضرَ الذي لم يعد غياباً بإذن.

    كلُّ مدرسةٍ في نطاقها وحدَها، وعطبُ واحدةٍ يُسجَّل ولا يُسقط غيرَها. وثابتةُ التكرار:
    الدورةُ الثانية لا تجد ما تفعله.
    """
    from django.utils import timezone

    from core.models import School
    from operations.exit_reflection import finalize_exits_for_day

    now = timezone.now()
    day = timezone.localdate(now)
    flipped = 0
    failed = 0
    for school in School.objects.filter(is_active=True).iterator(chunk_size=100):
        try:
            with school_rls_scope(school.id):
                flipped += finalize_exits_for_day(school, day, now)
        except Exception:  # noqa: BLE001 — مدرسةٌ معطوبةٌ لا تُسقط غيرَها
            failed += 1
            logger.exception("finalize_period_exits: تعذّر في المدرسة %s", school.pk)
    return {"flipped": flipped, "failed_schools": failed, "checked_at": str(now)}


# ═════════════════════════════════════════════════════════════════════
# الحصّةُ التعويضيّة — إنهاءُ الطلبات التي فات وقتُها
# ═════════════════════════════════════════════════════════════════════


@shared_task(name="operations.expire_overdue_compensatory")
def expire_overdue_compensatory_task():
    """ينهي طلباتِ التعويض المفتوحة التي مضى يومُ تعويضها، في كلّ مدرسة — كلَّ فجر.

    كانت `CompensatoryService.expire_overdue` مكتوبةً لا يستدعيها شيء، فيبقى طلبٌ لزميلٍ لم يردّ
    معلَّقاً إلى الأبد وهو لا يُقبَل. كلُّ مدرسةٍ في نطاقها وحدَها وعطبُ واحدةٍ يُسجَّل ولا يُسقط
    غيرَها؛ وثابتةُ التكرار.
    """
    from core.models import School
    from operations.services import CompensatoryService

    expired = 0
    failed = 0
    for school in School.objects.filter(is_active=True).iterator(chunk_size=100):
        try:
            with school_rls_scope(school.id):
                expired += CompensatoryService.expire_overdue(school)
        except Exception:  # noqa: BLE001 — مدرسةٌ معطوبةٌ لا تُسقط غيرَها
            failed += 1
            logger.exception("expire_overdue_compensatory: تعذّر في المدرسة %s", school.pk)
    return {"expired": expired, "failed_schools": failed}


# ═════════════════════════════════════════════════════════════════════
# حارسُ العام الدراسيّ — إطفاءُ جداول الأعوام الماضية
# طبقةٌ ثالثةٌ فوق وسيطةِ الطلب ومرحلةِ الإصدار، تعمل إن شُغِّل Celery Beat
# ═════════════════════════════════════════════════════════════════════


@shared_task(name="operations.retire_past_year_records")
def retire_past_year_records_task():
    """يُطفئ الجدولَ والإسنادَ الباقيَين نشطَين من أعوامٍ مضت، في كلّ مدرسة.

    ثابتةُ التكرار: نداؤها على قاعدةٍ سليمة لا يكتب شيئاً. وهي ثالثةُ ثلاثٍ
    تحرس القاعدة نفسَها — «لا حصّةَ نشطةٌ خارجَ العام الجاري» — لأنّ اعتمادَ
    الحراسة على موضعٍ واحدٍ يُسقطها متى تعطّل ذلك الموضع، والبيتُ مطفأٌ في
    الإنتاج اليوم.
    """
    from core.models import School
    from operations.services import ScheduleService

    total = {"slots": 0, "assignments": 0}
    for school in School.objects.all().iterator(chunk_size=100):
        with school_rls_scope(school.id):
            for key, count in ScheduleService.retire_past_year_records(school).items():
                total[key] += count

    return total


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
                        title=(f"تنبيه: رخصة {user.full_name} تقترب من الانتهاء"),
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
        "check_license_expiry_task: %d staff alerted (expiring within 60 days)",
        alerted,
    )

    return {
        "alerted": alerted,
        "checked_date": str(today),
    }


# ═════════════════════════════════════════════════════════════════════
# مصالحةُ الأسابيع المولَّدة سلفاً بعد اعتماد جدول (SCH-08)
# ═════════════════════════════════════════════════════════════════════


@shared_task(
    name="operations.resync_generated_sessions",
    max_retries=0,
    soft_time_limit=600,
    time_limit=660,
)
def resync_generated_sessions_task(school_id, academic_year):
    """يُصالح حصصَ الأيّام المولَّدة بعد أسبوع الاعتماد مع الجدول المعتمَد.

    الاعتمادُ يصالح الأسبوعَ الجاريَ في الطلب، وهذه تُكمل ما بعده خارجَه: كلفتُها تكبر
    بعدد الأسابيع المولَّدة (قرابةَ مئةٍ وستٍّ وسبعين حصّةً لكلّ يوم). وثابتةُ التكرار:
    دورةٌ ثانيةٌ على جدولٍ مصالَحٍ لا تجد ما تحذفه ولا ما تُنشئه.
    """
    from core.models import School
    from operations.services import ScheduleService

    school = School.objects.get(pk=school_id)
    with school_rls_scope(school.id):
        return ScheduleService.resync_future_weeks(school, academic_year)


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
    # من «الانتظار» إلى «يجري» شرطاً لا حفظاً: إن أُوقف بين القراءة وهنا فلا يُبعث من جديد.
    rows = ScheduleGeneration.objects.filter(
        pk=generation.pk, status__in=ScheduleGeneration.PENDING_STATUSES
    )
    if not rows.update(status="running"):
        return {"ok": False, "reason": "not_pending"}
    generation.status = "running"

    from operations.services.schedule_drafts import is_stopped

    def _fail(message):
        # شرطاً على «يجري»: صفٌّ أوقفه المستخدمُ أو حذفه لا يُكتب فوقه، ولا يُسقط المهمّة.
        ScheduleGeneration.objects.filter(pk=generation.pk, status="running").update(
            status="failed", error_message=message[:2000], finished_at=timezone.now()
        )
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
                should_stop=lambda: is_stopped(generation.pk),
            )
    except SoftTimeLimitExceeded:
        logger.error("generate_smart_schedule: تجاوز الزمنَ المسموح — %s", generation_id)
        _fail("تجاوز التوليدُ الزمنَ المسموح (خمس عشرة دقيقة) فأُوقف.")
        return {"ok": False, "reason": "soft_time_limit"}
    except Exception as exc:  # noqa: BLE001 — يُسجَّل ويُقال، ولا يُبتلع
        logger.exception("generate_smart_schedule: فشل التوليد — %s", exc)
        # نصُّ الاستثناء يُسجَّل للمشغّل لا للمستخدم: قد يحمل مساراتٍ أو أسماءَ
        # جداول أو جزءاً من تتبّع المكدّس، وهذه الرسالةُ تُعرض في الواجهة وتُبثّ JSON.
        _fail("خطأ غير متوقَّع في التوليد — سُجّلت التفاصيلُ للمشغّل، أعد المحاولةَ أو راجع السجلّ.")
        return {"ok": False, "reason": "exception"}

    if result.get("stopped"):
        logger.info("generate_smart_schedule: أُوقف يدويّاً — %s", generation_id)
        return {"ok": False, "reason": "stopped"}

    # مؤشراتُ المختبر تُحسب هنا مرّةً وتُحفظ في صفّ التوليد — فالصفحةُ تعرض ولا تحسب.
    try:
        from operations.schedule_lab import store_metrics

        store_metrics(generation)
    except Exception:  # noqa: BLE001 — القياسُ لا يُسقط توليداً ناجحاً
        logger.exception("schedule_lab: تعذّر حسابُ المؤشرات للتوليد %s", generation_id)

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
        # بالاستعلام لا بالحفظ: مسودّةٌ حُذفت بين الحفظ وهنا لا تُسقط المهمّة.
        ScheduleGeneration.objects.filter(pk=generation.pk).update(
            error_message="؛ ".join(result["errors"])[:2000]
        )

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


# ═════════════════════════════════════════════════════════════════════
# تصديرُ ورقة الجدول (PDF/Excel) — خارج دورة الطلب (P4-6، البند 5)
# ═════════════════════════════════════════════════════════════════════
#
# كان `schedule_export_pdf`/`schedule_export_excel` يبنيان الملفَّ متزامناً
# داخل الطلب — وWeasyPrint بطيءٌ بما يكفي ليُخالف معيار المشروع (>300ms →
# Background Job). فصار الطلبُ يُنشئ `ExportJob` (حالته `pending`) ويُرجع
# فوراً، وهذه المهمّة تملؤه، وصفحةُ متابعةٍ (`export_job_status`) تُنزّل
# الناتج حين يجهز. لا `request` حقيقيّاً هنا — `query_string` المحفوظة في
# الصفّ تُعاد قراءتها بـ`QueryDict` لبناء نفس السياق الذي كان سيُبنى في الطلب.


@shared_task(
    name="operations.render_schedule_export",
    bind=True,
    max_retries=1,
    default_retry_delay=10,
    soft_time_limit=60,
    time_limit=90,
)
def render_schedule_export_task(self, job_id, fmt):
    """`fmt`: `"pdf"` أو `"xlsx"`."""
    from django.http import QueryDict
    from django.utils import timezone

    from core.models import ExportJob

    try:
        job = ExportJob.objects.select_related("school", "requested_by").get(pk=job_id)
    except ExportJob.DoesNotExist:
        logger.warning("render_schedule_export: صفّ التصدير %s غير موجود", job_id)
        return {"ok": False, "reason": "job_not_found"}

    if job.status != "pending":
        logger.info("render_schedule_export: %s ليس قيدَ الانتظار — يُتخطّى", job_id)
        return {"ok": False, "reason": "not_pending"}

    job.status = "running"
    job.save(update_fields=["status"])

    try:
        with school_rls_scope(job.school_id):
            from operations.views_schedule import _export_filename, _schedule_print_payload_core

            get_params = QueryDict(job.query_string)
            ctx = _schedule_print_payload_core(job.school, job.requested_by, get_params)
            ctx["embed"] = True

            if fmt == "pdf":
                from django.template.loader import render_to_string

                from core.pdf_utils import render_pdf_bytes

                ctx["for_pdf"] = True
                html = render_to_string("schedule/print_schedule.html", ctx)
                content = render_pdf_bytes(
                    html, paper_size="A3" if ctx.get("paper") == "a3" else "A4"
                )
                content_type = "application/pdf"
                filename = _export_filename(ctx, "pdf")
            else:
                from io import BytesIO

                from operations.schedule_export import schedule_workbook

                buffer = BytesIO()
                schedule_workbook(ctx).save(buffer)
                content = buffer.getvalue()
                content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                filename = _export_filename(ctx, "xlsx")
    except Exception as exc:  # noqa: BLE001 — يُسجَّل ويُنقل لصفّ التصدير لا يُبتلع
        logger.exception("render_schedule_export: فشل — %s", exc)
        job.status = "failed"
        job.error_message = str(exc)[:2000]
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error_message", "finished_at"])
        return {"ok": False, "reason": "exception"}

    job.status = "done"
    job.content = content
    job.content_type = content_type
    job.filename = filename
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "content", "content_type", "filename", "finished_at"])
    return {"ok": True, "filename": filename}


@shared_task(name="operations.purge_expired_export_jobs")
def purge_expired_export_jobs_task():
    """صفوفُ التصدير مؤقّتة — لا تتراكم كالملفّات الدائمة في `StoredFile`.

    يوم واحد يكفي: التنزيلُ يقع خلال دقائق من طلبه، ومن تأخّر يعيد التصدير.
    """
    from datetime import timedelta

    from django.utils import timezone

    from core.models import ExportJob

    cutoff = timezone.now() - timedelta(hours=24)
    deleted, _ = ExportJob.objects.filter(created_at__lt=cutoff).delete()
    if deleted:
        logger.info("purge_expired_export_jobs: حُذف %s صفّ تصدير منتهٍ", deleted)

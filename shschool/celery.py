"""
shschool/celery.py
إعداد Celery لـ SchoolOS — معالجة المهام غير المتزامنة
"""

import os
from typing import Any

from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shschool.settings.development")


@setup_logging.connect
def _log_through_django(**kwargs: Any) -> None:
    """السجلُّ إعدادُ Django وحدَه — وCelery لا يمسّه.

    كان العاملُ وBeat على Railway يطبعان اللافتةَ ثمّ يصمتان: لا
    `Task … received` ولا `Scheduler: Sending due task`، رغم أنّ
    `production.py` يوجّه `celery` إلى stdout بمستوى INFO. والسببُ أنّ
    Celery — ما لم يجد مستقبِلاً لهذه الإشارة — «يختطف» السجلَّ عند البدء
    (`worker_hijack_root_logger`): يُفرغ معالِجاتِ الجذر ومعالِجاتِ `celery`
    نفسِه ثمّ يركّب معالِجَه على الجذر. لكنّ `celery` عندنا `propagate: False`،
    فبعد الإفراغ يصير مسجِّلاً بلا معالِجٍ ولا صعود: سطورُ INFO تسقط في
    الفراغ، وWARNING فما فوق يلتقطها معالِجُ بايثون الأخير على stderr — وهذا
    ما كان يُرى.

    ومستقبِلٌ واحدٌ للإشارة يكفي: وجودُه يُلغي الاختطافَ كلَّه، فيبقى
    إعدادُ `LOGGING` كما كتبناه — بما فيه فلترُ `pii_masking` على كلّ
    معالِج، وهو ما لا يحمله معالِجُ Celery لو تُرك يركّبه. و`dictConfig`
    هنا تكرارٌ آمن: Django طبّقه في `django.setup()` قبل هذه الإشارة، وإعادتُه
    تضمن الحالَ لو بدّل Celery ترتيبَه يوماً.

    والتطويرُ والاختبارُ لا يعرّفان `LOGGING` (Django يترك الجذرَ بلا معالِج)،
    فلولا الفرعُ الثاني لصمت عاملُ التطوير بدورِه: يُركَّب على الجذر ما كان
    Celery سيركّبه — مستواه وصيغتُه من وسائط الإشارة نفسِها.
    """
    import logging
    from logging.config import dictConfig

    from django.conf import settings

    if settings.LOGGING:
        dictConfig(settings.LOGGING)
        return
    logging.basicConfig(
        level=kwargs.get("loglevel") or logging.INFO,
        format=kwargs.get("format") or "[%(asctime)s: %(levelname)s/%(processName)s] %(message)s",
    )


app = Celery(
    "shschool",
    task_cls="core.celery_tasks:RLSIsolatedTask",
)

# قراءة الإعدادات من Django settings تحت namespace CELERY
app.config_from_object("django.conf:settings", namespace="CELERY")

# اكتشاف tasks تلقائياً من كل تطبيقات Django
app.autodiscover_tasks()


# ── المهام المُجدوَلة (Celery Beat) ─────────────────────────────────
app.conf.beat_schedule = {
    # إرسال تنبيهات الغياب كل صباح الساعة 7:00
    "send-absence-alerts-daily": {
        "task": "notifications.send_pending_absence_alerts_all_schools",
        "schedule": crontab(hour=7, minute=0),
    },
    # ✅ v5: فحص مواعيد BreachReport كل ساعة (PDPPL 72h)
    "check-breach-deadlines-hourly": {
        "task": "notifications.check_breach_deadlines",
        "schedule": crontab(minute=0),  # كل ساعة عند الدقيقة صفر
    },
    # ✅ v6: تقرير KPIs الشهري — أول يوم من كل شهر الساعة 6:00 صباحاً
    "send-monthly-kpi-report": {
        "task": "analytics.send_monthly_kpi_report",
        "schedule": crontab(hour=6, minute=0, day_of_month=1),
    },
    # سياسةُ الحضور والانصراف 5.1: «الخصم … بعد اشعار الموظف … بداية كل شهر بتقرير أيام الغياب
    # عن الشهر السابق» — أوّلَ كلّ شهرٍ 7:30، فتبقى مهلةُ التغطية (قبل يوم 15) أسبوعَين.
    "staff-monthly-absence-notices": {
        "task": "staff_affairs.send_monthly_absence_notices",
        "schedule": crontab(hour=7, minute=30, day_of_month=1),
    },
    # ✅ v7: إلغاء الصلاحيات المؤقتة المنتهية — كل دقيقة
    "revoke-expired-temp-permissions": {
        "task": "operations.revoke_expired_temp_permissions",
        "schedule": crontab(),  # كل دقيقة
    },
    # ✅ v5.4: فحص أسبوعي للطلاب المعرّضين للخطر السلوكي — كل أحد 6:00 صباحاً
    "weekly-behavior-risk-check": {
        "task": "behavior.weekly_risk_check",
        "schedule": crontab(hour=6, minute=0, day_of_week="0"),  # 0=الأحد (قطر)
    },
    # نهايةُ الحصص: من خرج بإذن المعلّم ولم يعد حتى الجرس يُكتب غائباً بإذن فيما ثبّته
    # المشرف، ويُغلق خروجُه (قرارُ 2026-09-16). كلَّ خمس دقائق، الأحد–الخميس في الدوام.
    "finalize-period-exits": {
        "task": "operations.finalize_period_exits",
        "schedule": crontab(minute="*/5", hour="6-15", day_of_week="0-4"),
    },
    # ملخّصُ مخالفات الرصد لأولياء الأمور — العصرَ من الأحد إلى الخميس (قرارُ 2026-09-16).
    # آخرُ جرسٍ ينتهي 13:30 والتثبيتُ المتأخّرُ بعده (والهروبُ من المدرسة لا يُحسم إلّا به)،
    # فساعةٌ ونصفٌ للمشرفين قبل أن يُقرأ اليوم. وما يُصحَّح بعدها يُرسَل إضافةً غداً.
    "behavior-auto-infraction-digest": {
        "task": "behavior.send_auto_infraction_digest",
        "schedule": crontab(hour=15, minute=0, day_of_week="0-4"),  # 0=الأحد … 4=الخميس
    },
    # الاحتفاظُ بالبيانات (PDPPL م.7 و10) — أسبوعيّاً فجرَ الجمعة، والمدرسةُ نائمة.
    # السياسةُ في docs/privacy/data_retention.md، والصفرُ في الإعداد يعطّلها.
    "enforce-data-retention-weekly": {
        "task": "core.enforce_data_retention",
        "schedule": crontab(hour=3, minute=30, day_of_week="5"),  # 5=الجمعة
    },
    # نبضةُ حياة العامل كلَّ خمس دقائق (P4-9): غيابُها في Sentry Crons هو
    # الإنذار — لا فشلُها. `monitor_beat_tasks=True` يفحصها تلقائيّاً.
    "worker-heartbeat": {
        "task": "core.worker_heartbeat",
        "schedule": crontab(minute="*/5"),
    },
    # حالةُ النسخ الاحتياطيّ اليوميّ (GitHub Actions) إلى الـcache لبطاقة الإدارة (OWN-23) — كلَّ نصف ساعة،
    # فطلبان في الساعة يسعهما الحدُّ غيرُ المصادَق (60). لا مراقبَ Sentry Crons لها: الحصّةُ للنبضة وحدَها.
    "refresh-backup-status": {
        "task": "core.refresh_backup_status",
        "schedule": crontab(minute="*/30"),
    },
    # مركزُ قيادة الجودة (QCC): جمعٌ آليٌّ للّوحات في الـcache بلا تدخّل — المحلّيُّ كلَّ دقيقة (قاعدةٌ وcache وملفّات)،
    # وGitHub كلَّ أربع دقائق بطلباتٍ شرطيّةٍ لا تُحتسب ضمن حدّ الستّين غيرِ المصادَق. الصفحةُ تقرأ الـcache وحدَه.
    "qcc-collect-local": {
        "task": "command_center.collect_local",
        "schedule": crontab(),
    },
    "qcc-collect-remote": {
        "task": "command_center.collect_remote",
        "schedule": crontab(minute="*/4"),
    },
    # صفوفُ تصدير PDF/Excel الخلفيّة (البند 5، P4-6؛ VI-30ب) مؤقّتة — حدٌّ صلبٌ 24 ساعةً من الإنشاء لكلّ الصفوف؛
    # وكلَّ ساعةٍ لا يومياً: اليوميّةُ كانت تترك أسوأَ حالةٍ ≈ 48 ساعةً، والمحتوى ثنائيٌّ في القاعدة (`data_retention.md`).
    "purge-expired-export-jobs": {
        "task": "operations.purge_expired_export_jobs",
        "schedule": crontab(minute=5),  # كلَّ ساعة عند الدقيقة 5
    },
    # طلباتُ التعويض المفتوحة التي مضى يومُها لا يقبلها أحدٌ بعدُ (`_not_past`): تُنهى فجراً
    # فلا تبقى معلَّقةً في قوائم المنسّق ولا تُعدّ انشغالاً لأصحابها ولا تسدّ خانةَ يومها.
    "expire-overdue-compensatory": {
        "task": "operations.expire_overdue_compensatory",
        "schedule": crontab(hour=4, minute=15),  # يومياً 4:15 صباحاً (الدوحة)
    },
}

app.conf.update(timezone="Asia/Qatar")

# ── v5.2: Task reliability — retry + ack-late + reject on worker lost ──────
app.conf.task_acks_late = True  # Ack بعد اكتمال المهمة (لا قبلها)
app.conf.task_reject_on_worker_lost = True  # إعادة المهمة إذا مات العامل
app.conf.task_default_retry_delay = 60  # تأخير بين المحاولات (ثانية)
app.conf.task_max_retries = 3  # أقصى 3 محاولات
app.conf.task_soft_time_limit = 300  # 5 دقائق (تحذير)
app.conf.task_time_limit = 600  # 10 دقائق (حد أقصى)
app.conf.worker_max_tasks_per_child = (
    100  # إعادة تشغيل العامل كل 100 مهمة (Task 6 — منع تسريب الذاكرة)
)
app.conf.worker_max_memory_per_child = 300_000  # 300MB حد أقصى لكل عامل


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")

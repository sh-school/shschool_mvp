"""
shschool/celery.py
إعداد Celery لـ SchoolOS — معالجة المهام غير المتزامنة
"""

import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shschool.settings.development")

app = Celery("shschool")

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
    # ✅ v7: توليد الحصص اليومية — 6:00 صباحاً (أحد–خميس = أسبوع قطر الدراسي)
    "generate-daily-sessions": {
        "task": "operations.generate_daily_sessions",
        "schedule": crontab(hour=6, minute=0, day_of_week="0-4"),  # Sun=0 .. Thu=4
    },
    # ✅ v7: إلغاء الصلاحيات المؤقتة المنتهية — كل دقيقة
    "revoke-expired-temp-permissions": {
        "task": "operations.revoke_expired_temp_permissions",
        "schedule": crontab(),  # كل دقيقة
    },
}

app.conf.timezone = "Asia/Qatar"

# ── v5.2: Task reliability — retry + ack-late + reject on worker lost ──────
app.conf.task_acks_late = True  # Ack بعد اكتمال المهمة (لا قبلها)
app.conf.task_reject_on_worker_lost = True  # إعادة المهمة إذا مات العامل
app.conf.task_default_retry_delay = 60  # تأخير بين المحاولات (ثانية)
app.conf.task_max_retries = 3  # أقصى 3 محاولات
app.conf.task_soft_time_limit = 300  # 5 دقائق (تحذير)
app.conf.task_time_limit = 600  # 10 دقائق (حد أقصى)
app.conf.worker_max_tasks_per_child = 1000  # إعادة تشغيل العامل كل 1000 مهمة (منع تسريب الذاكرة)
app.conf.worker_max_memory_per_child = 300_000  # 300MB حد أقصى لكل عامل


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")

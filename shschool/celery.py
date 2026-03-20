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
        "task":     "notifications.send_pending_absence_alerts_all_schools",
        "schedule": crontab(hour=7, minute=0),
    },
}

app.conf.timezone = "Asia/Qatar"


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")

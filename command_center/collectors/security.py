"""لوحةُ «الأمان والدخول» — محاولاتُ الدخول الفاشلة والحساباتُ المقفولة بأعدادٍ لا أسماء (قرارُ المالك 2026-09-27).

من `AuditLog` (دخولٌ فاشلٌ ورمزُ تحقّقٍ خاطئ، والفشلُ يُدقَّق كالنجاح) و`axes` (الحساباتُ المقفولةُ الآن). كانت بطاقةُ «الأمان» في رئيسيّة الإدارة
وأُخرجت من «صحّة الإنتاج» لأنّ جدولَ التدقيق بسياسة RLS لكلّ مدرسة؛ والمجمِّعُ يعمل في عاملٍ مربوطٍ بمدرسته فيقرؤها.
- **«انتبه»**: عشرُ محاولاتٍ فاشلةٍ فأكثرُ في 24 ساعة (عتبةُ البطاقة القائمة)، أو حسابٌ مقفولٌ الآن.
- **أحمرُ (قفزة)**: 30 فأكثرُ **وستّةُ أضعاف** الأربعِ والعشرين قبلها — هجومٌ محتملٌ لا خطأُ كلمةِ مرورٍ عابر.
ما يُخزَّن أعدادٌ فقط — لا اسمَ مستخدمٍ ولا عنوانَ IP.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from command_center import contract
from command_center.collectors.publish import publish, score, worst

PANEL = "security"
FAILED_WARN = 10
SPIKE_MIN = 30
SPIKE_FACTOR = 6
FAILED_ACTIONS = ("login_failed", "mfa_failed")


def level(failed: int, previous: int, locked: int) -> str:
    if failed >= max(SPIKE_MIN, SPIKE_FACTOR * previous):
        return contract.BAD
    return contract.WARN if (failed >= FAILED_WARN or locked) else contract.OK


def collect(now=None) -> None:
    from axes.models import AccessAttempt

    from core.models import AuditLog

    moment = now or timezone.now()
    day = timedelta(hours=24)
    logs = AuditLog.objects.filter(action__in=FAILED_ACTIONS)
    failed = logs.filter(timestamp__gte=moment - day).count()
    previous = logs.filter(timestamp__gte=moment - 2 * day, timestamp__lt=moment - day).count()
    mfa = AuditLog.objects.filter(action="mfa_failed", timestamp__gte=moment - day).count()
    limit = getattr(settings, "AXES_FAILURE_LIMIT", 5)
    cooloff = getattr(settings, "AXES_COOLOFF_TIME", timedelta(minutes=5))
    locked = AccessAttempt.objects.filter(
        failures_since_start__gte=limit, attempt_time__gte=moment - cooloff
    ).count()
    overall = level(failed, previous, locked)
    if overall == contract.BAD:
        headline = "قفزةٌ في محاولات الدخول الفاشلة"
    elif overall == contract.WARN:
        headline = "محاولاتُ دخولٍ فاشلةٌ بحاجةٍ إلى نظر"
    else:
        headline = "لا نشاطَ دخولٍ مريباً"
    publish(
        PANEL,
        status=worst([overall]),
        headline=headline,
        gauge=score([overall]),
        metrics=(
            ("دخولٌ فاشل / 24س", failed),
            ("الأربعُ والعشرون قبلها", previous),
            ("حساباتٌ مقفولةٌ الآن", locked),
            ("رمزُ تحقّقٍ خاطئ / 24س", mfa),
        ),
    )

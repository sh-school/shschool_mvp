"""
notifications/quiet_hours.py
ساعات الهدوء — المرجعُ الوحيد لحكمها ولموعد رفعها.

القاعدة (قرار 2026-09-21): إشعارُ المنصّة يصل فوراً دائماً، أمّا القنواتُ الخارجيّة
(بريد، SMS، WhatsApp، Push) فلا تخرج في ساعات هدوء المستلم — **وتُؤجَّل إلى
انتهائها لا تُتخطّى**: تنبيهُ غيابٍ أو رسوبٍ يقع ليلاً لا يجوز أن يضيع.

كان الحكمُ مكتوباً في موضعٍ واحدٍ من الـHub يتخطّى ولا يؤجّل، وأزرارُ لوحة الإشعارات
تمرّ على الخدمة مباشرةً فلا تسأل عنه أصلاً. فصار السؤالُ «هل أُرسل الآن؟» يُطرح
من هنا وحدَه: `plan(user)` — والـHub والخدمةُ كلاهما يستدعيانه.

**كيف يُؤجَّل بلا جدول جديد:** مهمّةُ Celery بموعد (`eta`) — `release_after_quiet_hours_task`.
وتقفز على قفزاتٍ لا تتجاوز `MAX_HOLD_HOP` (45 دقيقة) لا قفزةً واحدة إلى نهاية النافذة:
وسيطُ Redis يُعيد تسليم رسالةٍ مؤجَّلة تجاوزت `visibility_timeout` (ساعةٌ افتراضيّاً)
مع `acks_late`، ونافذةُ الهدوء تبلغ ثماني ساعات — فقفزةٌ واحدةٌ كانت ستُخرج الرسالةَ
مكرّرةً كلَّ ساعة. وعند كلّ قفزةٍ يُعاد السؤال، فتعديلُ المستلم لساعاته يُحتسب.

**حدٌّ صادق:** الإرجاءُ يحتاج عاملاً حقيقيّاً. مع `CELERY_TASK_ALWAYS_EAGER` يُنفَّذ
`eta` فوراً، فلا يُؤجَّل شيء — عندها يُتخطّى الإرسالُ الخارجيّ (وهو السلوكُ السابق
نفسُه) بدل أن يخرج في الهدوء؛ والمسارُ المتتبَّع يستردّه المُصالِحُ بعد انتهاء النافذة.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import NamedTuple

from django.conf import settings
from django.utils import timezone

#: أطولُ قفزةٍ للمهمّة المؤجَّلة — أقلُّ من `visibility_timeout` الافتراضيّ (ساعة).
MAX_HOLD_HOP = timedelta(minutes=45)

SEND_NOW = "send_now"
HOLD = "hold"
SKIP = "skip"


class QuietPlan(NamedTuple):
    """قرارُ الإرسال لمستلمٍ واحد: `action` ومعه `eta` عند الإرجاء."""

    action: str
    eta: datetime | None = None


def in_quiet_window(start: time | None, end: time | None, at: time) -> bool:
    """هل `at` داخل [start, end)؟ النافذةُ قد تعبر منتصف الليل (22:00–06:00).

    الطرفُ الأخير خارجُها: عند 06:00 بالضبط تنتهي الساعاتُ فيُرسَل. ونافذةٌ
    بطرفين متساويين أو ناقصة تُعدّ معطَّلة.
    """
    if not start or not end or start == end:
        return False
    if start < end:
        return start <= at < end
    return at >= start or at < end


def _next_occurrence(end: time, local_now: datetime) -> datetime:
    """أوّلُ لحظةٍ بعد `local_now` تبلغ فيها الساعةُ `end` بتوقيت المنصّة."""
    tz = local_now.tzinfo
    candidate = datetime.combine(local_now.date(), end, tzinfo=tz)
    if candidate <= local_now:
        candidate = datetime.combine(local_now.date() + timedelta(days=1), end, tzinfo=tz)
    return candidate


def _prefs(user):
    from .models import UserNotificationPreference

    try:
        return user.notification_preferences
    except UserNotificationPreference.DoesNotExist:
        return None


def quiet_release_at(user, now: datetime | None = None) -> datetime | None:
    """لحظةُ انتهاء ساعات هدوء المستخدم إن كان فيها الآن، وإلّا `None`.

    التوقيتُ محلّيٌّ للمنصّة (`TIME_ZONE = Asia/Qatar`) لا UTC.
    """
    prefs = _prefs(user)
    if prefs is None:
        return None

    local_now = timezone.localtime(now or timezone.now())
    if not in_quiet_window(prefs.quiet_hours_start, prefs.quiet_hours_end, local_now.time()):
        return None
    return _next_occurrence(prefs.quiet_hours_end, local_now)


def can_hold() -> bool:
    """هل يوجد عاملٌ يحفظ المهامَّ المؤجَّلة؟ — لا مع التنفيذ الفوريّ."""
    return not getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False)


def plan(user, now: datetime | None = None) -> QuietPlan:
    """الحكمُ المركزيّ: أُرسل الآن، أم أُؤجَّل (وإلى متى)، أم أُتخطّى."""
    now = now or timezone.now()
    release = quiet_release_at(user, now)

    if release is None:
        return QuietPlan(SEND_NOW)
    if not can_hold():
        return QuietPlan(SKIP)
    return QuietPlan(HOLD, min(release, now + MAX_HOLD_HOP))

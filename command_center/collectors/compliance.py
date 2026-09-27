"""لوحةُ «الامتثال (PDPPL)» — ثلاثةُ فحوصٍ قانونيّةٍ بأعدادٍ لا أسماء (قرارُ المالك 2026-09-27: قراءةُ بيانات المدرسة بعدّاداتٍ رقميّةٍ فقط).

1. **بلاغاتُ الخرق** (`BreachReport`، م.11 / إشعارُ NCSA خلال 72 ساعة): مفتوحٌ = لم يُشعَر به ولم يُحلّ. **أحمرُ** إن فات موعدُ أحدها،
   و«انتبه» إن اقترب موعدُ أقربها (أقلَّ من 24 ساعة)، وإلّا سليم.
2. **طلباتُ المحو** (`ErasureRequest`، م.18): مفتوحٌ = قيد المراجعة أو الموافقة أو التنفيذ. والمدّةُ عتبتان **داخليّتان** (لا نصَّ قانونيَّ برقمها هنا):
   «انتبه» بعد 7 أيّام و**أحمرُ** بعد 30 — وهما ثابتان في هذا الملفّ يُراجعهما المالكُ.
3. **إنفاذُ الاحتفاظ** (`governance/retention.py`، م.7 و10): المدّةُ 0 = **معطَّل** («انتبه»: السياسةُ لا تعمل)؛ وإنفاذٌ أسبوعيٌّ (فجرَ الجمعة) فأكثرُ من 9 أيّامٍ
   بلا تنفيذٍ «انتبه» وأكثرُ من 16 أحمر؛ ولا تنفيذَ مسجَّلاً بعدُ «انتبه» لا سليم.

قراءةُ القرص = 100 ناقصاً عقوبةَ كلّ فحصٍ (`publish.score`). ما يُخزَّن أعدادٌ وأعمارٌ فقط — لا اسمَ طالبٍ ولا نصَّ خرقٍ ولا سببَ محو (المستودعُ والـcache بلا بياناتٍ شخصيّة).
تعمل هذه الاستعلاماتُ في عاملٍ مربوطٍ بمدرسته (سياسةُ RLS تقرأ مدرستَه)، فلا يتجاوز المجمِّعُ عزلَ المدارس.
"""

from __future__ import annotations

from django.utils import timezone

from command_center import contract
from command_center.collectors.publish import publish, score, worst

PANEL = "compliance"
BREACH_SOON_HOURS = 24
ERASURE_WARN_DAYS = 7
ERASURE_BAD_DAYS = 30
RETENTION_WARN_DAYS = 9
RETENTION_BAD_DAYS = 16
CLOSED_BREACH = ("notified", "resolved")
OPEN_ERASURE = ("pending", "approved", "processing")
RETENTION_LOG_PREFIX = "إنفاذُ الاحتفاظ بالبيانات"


def breach_level(open_count: int, overdue: int, nearest_hours: int | None) -> str:
    if overdue:
        return contract.BAD
    if open_count and nearest_hours is not None and nearest_hours < BREACH_SOON_HOURS:
        return contract.WARN
    return contract.OK


def erasure_level(open_count: int, oldest_days: int) -> str:
    if not open_count:
        return contract.OK
    if oldest_days >= ERASURE_BAD_DAYS:
        return contract.BAD
    return contract.WARN if oldest_days >= ERASURE_WARN_DAYS else contract.OK


def retention_level(days_setting: int, last_run_days: int | None) -> str:
    if days_setting <= 0 or last_run_days is None:
        return contract.WARN
    if last_run_days > RETENTION_BAD_DAYS:
        return contract.BAD
    return contract.WARN if last_run_days > RETENTION_WARN_DAYS else contract.OK


def _breaches(now):
    from core.models.audit import BreachReport

    open_qs = BreachReport.objects.exclude(status__in=CLOSED_BREACH)
    open_count = open_qs.count()
    overdue = open_qs.filter(ncsa_deadline__lt=now).count()
    upcoming = (
        open_qs.filter(ncsa_deadline__gte=now)
        .order_by("ncsa_deadline")
        .values_list("ncsa_deadline", flat=True)
        .first()
    )
    hours = None if upcoming is None else max(0, int((upcoming - now).total_seconds() // 3600))
    return open_count, overdue, hours


def _erasures(now):
    from core.models.audit import ErasureRequest

    open_qs = ErasureRequest.objects.filter(status__in=OPEN_ERASURE)
    open_count = open_qs.count()
    oldest = open_qs.order_by("created_at").values_list("created_at", flat=True).first()
    return open_count, 0 if oldest is None else max(0, (now - oldest).days)


def _last_retention_run_days(now):
    from core.models.audit import AuditLog

    stamp = (
        AuditLog.objects.filter(action="delete", object_repr__startswith=RETENTION_LOG_PREFIX)
        .order_by("-timestamp")
        .values_list("timestamp", flat=True)
        .first()
    )
    return None if stamp is None else max(0, (now - stamp).days)


def collect(now=None) -> None:
    from governance.retention import retention_days

    moment = now or timezone.now()
    breach_open, breach_overdue, breach_hours = _breaches(moment)
    erasure_open, erasure_days = _erasures(moment)
    days_setting = retention_days()
    last_run = _last_retention_run_days(moment)
    levels = [
        breach_level(breach_open, breach_overdue, breach_hours),
        erasure_level(erasure_open, erasure_days),
        retention_level(days_setting, last_run),
    ]
    troubled = sum(1 for level in levels if level != contract.OK)
    if breach_overdue:
        headline = f"{breach_overdue} من بلاغات الخرق فات موعدُ إشعارها"
    elif troubled:
        headline = f"{troubled} من 3 فحوصٍ بحاجةٍ إلى نظر"
    else:
        headline = "لا خروقَ مفتوحةً ولا محوَ متأخّراً"
    publish(
        PANEL,
        status=worst(levels),
        headline=headline,
        gauge=score(levels),
        metrics=(
            ("بلاغاتُ خرقٍ مفتوحة", breach_open),
            (
                "طلباتُ محوٍ مفتوحة",
                f"{erasure_open} (الأقدمُ {erasure_days} يوماً)" if erasure_open else 0,
            ),
            ("آخرُ إنفاذٍ للاحتفاظ", "لم يُنفَّذ بعدُ" if last_run is None else f"قبل {last_run} يوماً"),
            ("مدّةُ الاحتفاظ", "معطَّلة" if days_setting <= 0 else f"{days_setting} يوماً"),
        ),
    )

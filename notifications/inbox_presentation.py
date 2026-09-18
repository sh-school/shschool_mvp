"""
notifications/inbox_presentation.py
تقسيمُ صندوق الإشعارات للعرض — مجموعاتٌ بالأيّام، وكلُّ مجموعةٍ أعمدةٌ متجاورة.

كان الصندوقُ عمودَ قراءةٍ بعرض 48rem: مئةُ إشعارٍ بطاقةً تحت بطاقة، والنافذةُ
فارغةٌ عن يمينه ويساره. والإشعارُ سطرٌ أو سطران (عنوانٌ ونصٌّ قصيرٌ ووقت)، فهو
من صنف «المحتوى الضيّق غير المحدود» في معيار التخطيط (CLAUDE.md): يُقسَّم أعمدةً
في العرض لا في القالب — `chunk_for_grid` — ويُرسم داخل `.auto-grid`.
"""

from datetime import date, datetime, timedelta

from django.utils import timezone

from core.dashboard_presentation import chunk_for_grid

# ثلاثةُ أعمدةٍ تملأ نافذةَ المكتب بعرضٍ يتّسع لسطرَي النصّ؛ و`.auto-grid`
# يفكّها عموداً واحداً على الهاتف بلا استعلامات @media.
INBOX_COLUMNS = 3

_BUCKETS = (
    ("today", "اليوم"),
    ("yesterday", "أمس"),
    ("week", "هذا الأسبوع"),
    ("older", "أقدم"),
)


def _bucket_of(created: datetime, today: date) -> str:
    day = timezone.localtime(created).date()
    if day >= today:
        return "today"
    if day == today - timedelta(days=1):
        return "yesterday"
    if day > today - timedelta(days=7):
        return "week"
    return "older"


def group_by_day(notifications: list, today: date | None = None) -> list[dict]:
    """مجموعاتٌ بترتيب الزمن (الأحدثُ أوّلاً)، والفارغةُ منها تُسقط.

    الترتيبُ داخل المجموعة يبقى كما جاء (الأحدثُ أوّلاً)، والتقسيمُ متتابعٌ:
    رأسُ المجموعة أعلى العمود الأوّل — فتنقُّلُ j/k على ترتيب الوثيقة يطابق الزمن.
    """
    today = today or timezone.localdate()
    buckets: dict[str, list] = {key: [] for key, _ in _BUCKETS}
    for notif in notifications:
        buckets[_bucket_of(notif.created_at, today)].append(notif)
    return [
        {
            "key": key,
            "label": label,
            "count": len(buckets[key]),
            "columns": chunk_for_grid(buckets[key], INBOX_COLUMNS),
        }
        for key, label in _BUCKETS
        if buckets[key]
    ]

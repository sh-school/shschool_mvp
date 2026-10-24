from typing import Any

from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None


@register.filter
def periods_phrase(count: Any) -> str:
    """«N حصة» بتمييز العدد العربيّ الصحيح: 1 حصّةٌ واحدة، 2 حصّتان، 3–10 حصص، 11 فأكثر حصّة.

    فالتمييزُ يتبع العددَ: المفردُ للواحد، والمثنّى للاثنين، والجمعُ لثلاثةٍ إلى عشرة، والمفردُ المنصوبُ لما فوقها.
    وما لا يُقرأ عدداً صحيحاً يُعاد فارغاً فلا يُطبع تمييزٌ لرقمٍ مجهول (W-20261012-009).
    """
    try:
        n = int(count)
    except (TypeError, ValueError):
        return ""
    if n == 0:
        return "لا حصص"
    if n == 1:
        return "حصّة واحدة"
    if n == 2:
        return "حصّتان"
    if 3 <= n <= 10:
        return f"{n} حصص"
    return f"{n} حصّة"


@register.filter
def has_capability(user: Any, key: str) -> bool:
    """أيملك المستخدمُ هذه القدرة؟ — للقالب، بالحكم نفسِه الذي يحرس العرض.

    فزرٌّ تحرسه قدرةٌ في العرض يُسأل عنها هنا لا بعلَمٍ في سياق العرض: علَمٌ لكلّ
    زرٍّ يطيل العرضَ سطراً سطراً، والحارسُ يعدّ أسطره.
    """
    from core.capabilities import has_capability as _has

    return _has(user, key)


@register.filter
def duration_ms(value):
    """مدّةٌ بالملّي ثانية تُقرأ: «25.6 ث» تحت الدقيقة، و«6:14 د» فوقها.

    فـ«374379ms» رقمٌ يُحسب لا يُقرأ — ومن يقارن توليدين يريد أن يرى الفرق
    بين ست دقائق ونصف دقيقة بلا قسمة.
    """
    try:
        ms = int(value)
    except (TypeError, ValueError):
        return ""
    seconds = ms / 1000
    if seconds < 60:
        return f"{seconds:.1f} ث"
    minutes, rest = divmod(int(round(seconds)), 60)
    return f"{minutes}:{rest:02d} د"

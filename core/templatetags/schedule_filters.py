from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None


@register.filter
def has_capability(user, key):
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

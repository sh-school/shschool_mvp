"""[U-09، PDPPL] نصُّ القنوات الخارجية لوليّ الأمر (SMS وواتساب وإشعار الجوال وعنوان البريد).

لا اسمَ طالبٍ ولا سببَ ولا مخالفةَ ولا درجةَ ولا مواد: التفاصيلُ تبقى داخل المنصّة خلف الدخول.
"""

PARENT_NEUTRAL_TITLE = "إشعار جديد في بوابة ولي الأمر"
PARENT_NEUTRAL_BODY = "يوجد إشعار جديد بخصوص ابنكم، يُرجى الدخول إلى بوابة ولي الأمر للاطّلاع عليه."


def parent_neutral_body(*extra_lines: str) -> str:
    """النصُّ المحايد، تتبعه أسطرٌ لا تكشف شيئاً عن الطالب (موعدُ الحضور ومكانه، تاريخُ الإخطار)."""
    return "\n".join([PARENT_NEUTRAL_BODY, *extra_lines])


def summon_visit_lines(summon_date: str, summon_time: str, place_label: str) -> list[str]:
    """سطرا موعد الحضور ومكانه في الاستدعاء إن وُجدا."""
    lines = []
    if summon_date:
        when = f"{summon_date} الساعة {summon_time}" if summon_time else summon_date
        lines.append(f"الموعد المطلوب: {when}")
    if place_label:
        lines.append(f"مكان الاجتماع: {place_label}")
    return lines

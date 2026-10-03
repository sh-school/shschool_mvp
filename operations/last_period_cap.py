"""سقفُ السابعة الشخصيّ (HC8) — مداه وقراءتُه الآمنة (W-20261003-035، شرطُ 0105).

`TeacherPreference.max_last_periods` سقفٌ إداريٌّ في حقّ معلّمٍ بعينه. والـvalidators في النموذج لا تمنع
إدخالاً مباشراً بالـORM، فمن كتب 0 أو 99 لا يجوز أن يتحوّل خطؤه إلى إلغاء HC8 أو تضخيمه. لذلك كلُّ قراءةٍ
في المولّد وفحص الجدوى تمرّ من هنا: ما خرج عن المدى يُعامَل كغيابه (أي السقفَ العامّ).
"""

MIN_PERSONAL_LAST = 1
MAX_PERSONAL_LAST = 5


def personal_last_cap(value: int | None) -> int:
    """السقفُ الشخصيّ الصالح، أو صفرٌ يعني «خُذ العامّ»."""
    if isinstance(value, int) and not isinstance(value, bool):
        if MIN_PERSONAL_LAST <= value <= MAX_PERSONAL_LAST:
            return value
    return 0

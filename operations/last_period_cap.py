"""سقفُ السابعة الشخصيّ (HC8) — مداه وقراءتُه الآمنة (W-20261003-035، شرطُ 0105).

`TeacherPreference.max_last_periods` سقفٌ إداريٌّ في حقّ معلّمٍ بعينه. والـvalidators في النموذج لا تمنع
إدخالاً مباشراً بالـORM، فمن كتب 0 أو 99 لا يجوز أن يتحوّل خطؤه إلى إلغاء HC8 أو تضخيمه. لذلك كلُّ قراءةٍ
في المولّد وفحص الجدوى تمرّ من هنا: ما خرج عن المدى يُعامَل كغيابه (أي السقفَ العامّ).

**والصفرُ منعٌ لا غياب (W-20261004-013):** كان `0` يعني «خُذ العامّ» فلا يُمكن منعُ السابعة عن معلّمٍ بعينه
(كمن يعتذر عنها لسبب صحّيّ أو لقرار إداريّ). فصار `None` وحده هو «العامّ» و`0` هو «لا سابعةَ إطلاقاً»،
والقيمُ `1..5` سقفُه الأسبوعيّ. وما خُزّن صفراً قبل هذا القرار يُقرأ منعاً كذلك — لا هجرةَ تُعيد تفسيرَ بيانات
قائمة (شرطُ المالك: عدُّ الأصفار القديمة في الإنتاج قراءةٌ بإذنه المباشر وحدَه).
"""

from typing import Any

#: الصفرُ منعُ السابعة عن المعلّم. وما بين 1 و5 سقفٌ أسبوعيّ.
BAN_PERSONAL_LAST = 0
MIN_PERSONAL_LAST = 1
MAX_PERSONAL_LAST = 5


def personal_last_cap(value: int | None) -> int | None:
    """السقفُ الشخصيّ الصالح: `0` منعٌ و`1..5` سقفٌ، و`None` تعني «خُذ العامّ» (غيابٌ أو خارجَ المدى)."""
    if isinstance(value, int) and not isinstance(value, bool):
        if BAN_PERSONAL_LAST <= value <= MAX_PERSONAL_LAST:
            return value
    return None


def admin_last_caps(school: Any, academic_year: str) -> dict[str, int]:
    """سقوفُ السابعة الشخصيّةُ المقرَّرة إدارياً ({معلّم ← سقف}) — ما خالف العامَّ وفي مداه فقط، ومنه الصفر (منع).

    مصدرٌ واحدٌ يقرؤه المولّدُ V2 (نظيرُ `admin_first_caps`) فلا يختلف حكمُه عن V1 والمُقيِّم (W-20261004-013).
    قيمةٌ خارج المدى تُعامَل كغيابها لا كإلغاءٍ للسقف ولا كتضخيمٍ له.
    """
    from .models import TeacherPreference
    from .scheduling_limits import MAX_LAST_PERIODS

    rows = TeacherPreference.objects.filter(
        school=school, academic_year=academic_year, max_last_periods__isnull=False
    ).values_list("teacher_id", "max_last_periods")
    caps = {str(teacher): personal_last_cap(value) for teacher, value in rows}
    return {t: cap for t, cap in caps.items() if cap is not None and cap != MAX_LAST_PERIODS}


def last_cap_or(value: int | None, general: int) -> int:
    """السقفُ الساري على المعلّم: شخصيُّه إن صدر (ومنه الصفر)، وإلّا `general`.

    موضعٌ واحدٌ لـ«الصفرُ ليس غياباً» فلا يعود `or general` يبتلع المنعَ في موضعٍ دون آخر.
    """
    cap = personal_last_cap(value)
    return general if cap is None else cap

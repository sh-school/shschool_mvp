"""أسماءُ الأشياء كما تكتبها الوزارة — مصدرٌ واحدٌ لا نسختان.

كان لكلّ شاشةٍ منطقُها في كتابة الصفّ: سجلُّ الطلاب يحشو بالصفر فيكتب
«07/2»، وشاشةُ ربط أولياء الأمور تقصّ الحرفَ فتكتب «7/2». ورقمٌ واحدٌ
بشكلين يجعل القارئَ يشكّ أنّهما صفّان.

وسجلُّ القيد الوزاريُّ يكتبه بخانتين: `07/2` و`10/4`. فهذا هو الشكل.
"""


def class_label(grade: str | None, section: str | None) -> str:
    """«G7» و«2» ← «07/2» — وما لا رقمَ فيه يبقى كما هو.

    والشعبةُ قد تكون حرفاً («ESE»)، فلا تُمسّ: الحشوُ للصفّ وحدَه.
    """
    if not grade or not section:
        return "—"
    digits = "".join(character for character in grade if character.isdigit())
    return f"{digits.zfill(2)}/{section}" if digits else f"{grade}/{section}"

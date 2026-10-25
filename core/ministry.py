"""عبارةُ الانتماء للوزارة — مصدرٌ واحدٌ ومفتاحٌ واحد (W-20261012-008، قرار المالك D-399م ثمّ D-400م).

كانت العبارةُ «وزارة التربية والتعليم والتعليم العالي — دولة قطر» مكتوبةً حرفيّاً في ترويسات القوالب وتذييلاتها وملفّات PDF وExcel.
وقرّر المالكُ **تجميدَها لا حذفَها**: تبقى في الشيفرة ولا تظهر، ويُفعَّل ظهورُها لاحقاً بمفتاحٍ واحدٍ بلا تعديل كود:

    MINISTRY_AFFILIATION_VISIBLE=true      # متغيّرُ بيئةٍ؛ مطفأٌ افتراضاً، بلا هجرةٍ ولا جدول

وكلُّ موضعٍ يقرأ النصَّ من هنا فقط: بايثون بـ`ministry_name()` و`ministry_line()`، والقوالبُ بالوسم `{% ministry_name %}`
(`core/templatetags/ministry.py`). ولا نصَّ حرفيّاً للعبارة خارج هذه الوحدة (`tests/test_ministry_affiliation.py`).

خارجَ هذا المفتاح — وتبقى ظاهرةً — إشاراتُ الوزارة جهةً مرجعيّةً (لجنةُ الوزارة، معاييرُ استمارات التقييم، مرجعُ التقرير)
ورؤيةُ المدرسة `school.vision` (`core/ministry_vision.py`).
"""

from __future__ import annotations

from django.conf import settings

#: العبارةُ الكاملةُ في الترويسات والتذييلات.
MINISTRY_NAME = "وزارة التربية والتعليم والتعليم العالي — دولة قطر"
#: الصيغةُ المختصرةُ حيث تلي اسمَ المدرسة في سطرٍ واحد (عناوين Excel وتذييلُ الأخطاء).
MINISTRY_SHORT = "وزارة التربية والتعليم والتعليم العالي"


def ministry_visible() -> bool:
    """أمفتاحُ إظهار عبارة الوزارة مشغَّل؟ — يُقرأ عند كلّ استدعاءٍ فيُغيَّر بـ`override_settings` في الاختبار."""
    return bool(getattr(settings, "MINISTRY_AFFILIATION_VISIBLE", False))


def ministry_name(short: bool = False) -> str:
    """عبارةُ الوزارة، أو نصٌّ فارغٌ حين يكون المفتاحُ مطفأً — فيُسقطها المستدعي مع فاصلها."""
    if not ministry_visible():
        return ""
    return MINISTRY_SHORT if short else MINISTRY_NAME


def ministry_line(*parts: str, sep: str = " — ") -> str:
    """يضمّ الأجزاءَ غيرَ الفارغة بفاصلٍ واحد — فجزءُ الوزارة الفارغُ (مطفأً) لا يترك فاصلاً يتيماً.

    ministry_line(school_name, ministry_name(short=True), sep="  —  ")  ←  «المدرسة — وزارة…» مضاءً و«المدرسة» مطفأً.
    """
    return sep.join(part for part in parts if part)

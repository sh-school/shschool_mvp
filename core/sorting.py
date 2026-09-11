"""فرزُ القوائم المقسَّمة صفحاتٍ — من الخادم لا من المتصفّح.

الجدولُ المقسَّمُ صفحاتٍ لا يُفرَز في المتصفّح: الصفحةُ الظاهرةُ أربعون صفّاً من
ألفٍ، وفرزُها يُوهم القارئَ أنّه رأى الأعلى وهو أعلى صفحةٍ واحدة. فالترتيبُ
يقع على الاستعلام كلِّه قبل التقسيم، ثمّ تُقسَّم النتيجةُ المرتَّبة.

والحقولُ المسموحُ الفرزُ بها تُصرَّح في كلّ شاشةٍ صراحةً: `?sort=` نصٌّ يأتي من
المستخدم، فلو مُرِّر إلى `order_by` كما هو لفُتحت العلاقاتُ كلُّها أمامه.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db.models import CharField, F, Func, Value
from django.db.models.functions import NullIf, Trim

#: تسويةُ رسمِ الحرف قبل الفرز. القاعدةُ ترتّب بالنقاط البرمجيّة، فـ«أكرم»
#: (همزةٌ على ألف، U+0623) تسبق «ابراهيم» (ألفٌ مجرّدة، U+0627) وهما عند
#: القارئ ألفٌ واحدة. فتُردُّ صورُ الألف إلى ألف، والهمزةُ على واوٍ إلى واو،
#: وعلى ياءٍ إلى ياء، والمقصورةُ إلى ياء، والتاءُ المربوطةُ إلى هاء —
#: ويُحذف التطويلُ والهمزةُ المفردةُ والتشكيلُ كلُّه.
_SHAPES_FROM = "أإآٱؤئىة" + "ـء" + "ًٌٍَُِّْ"
_SHAPES_TO = "ااااوييه"

#: القاموسُ نفسُه لبايثون — مصدرُ الحرفين واحدٌ فلا يفترق الطرفان يوماً.
_FOLD = {
    ord(src): (_SHAPES_TO[i] if i < len(_SHAPES_TO) else None) for i, src in enumerate(_SHAPES_FROM)
}


def arabic_key(expression):
    """مفتاحُ فرزٍ عربيٌّ من عبارة: يسوّي رسمَ الحرف، ويجعل الفارغَ عَدَماً.

    والعَدَمُ مقصود: `apply_sort` يدفع العَدَمَ إلى الذيل في الاتّجاهين، فلا
    يتصدّر الفارغُ قائمةً فُرزت بعمودٍ نصفُ خاناته لم يُملأ بعد.
    """
    return NullIf(
        Trim(
            Func(
                expression,
                Value(_SHAPES_FROM),
                Value(_SHAPES_TO),
                function="TRANSLATE",
                output_field=CharField(),
            )
        ),
        Value(""),
    )


def normalise_arabic(text: str) -> str:
    """تسويةُ نصّ البحث بالتسوية نفسِها التي في `arabic_key`.

    المفتاحُ في القاعدة مُسوّى، فلو بُحث فيه بنصٍّ خامٍ لم يُطابَق: من كتب
    «أحمد» بالهمزة لا يجد «احمد» المسوّاة. فيُسوّى الطرفان بقاموسٍ واحد.
    """
    return text.translate(_FOLD).strip()


def blank_as_null(field_name: str):
    """نصٌّ فارغٌ ليس قيمةً صغرى — يُساوى بالعَدَم ليقع في الذيل."""
    return NullIf(F(field_name), Value(""))


@dataclass(frozen=True)
class SortState:
    """حالةُ الفرز الجارية — يقرؤها القالبُ ليرسم الترويسة."""

    key: str
    descending: bool
    allowed: dict[str, tuple[str, ...]] = field(default_factory=dict)
    desc_first: frozenset[str] = frozenset()

    def starts_desc(self, key: str) -> bool:
        """أعمدةُ التواريخ والأعداد تبدأ تنازليّاً: الأحدثُ والأكبرُ هو المقصودُ أوّلاً."""
        return key in self.desc_first

    @property
    def direction(self) -> str:
        return "desc" if self.descending else "asc"


def _order(field: str, descending: bool):
    """عبارةُ ترتيبٍ واحدة — والعَدَمُ في الذيل صعوداً ونزولاً.

    الحقلُ المصرَّحُ قد يأتي معكوساً أصلاً («-created_at» فاصلاً يقطع التساوي)،
    فالتنازليُّ يعكسه ولا يُضاعف إشارتَه.

    وترتيبُ القاعدة للعَدَم يتبع الاتّجاه: أخيراً صعوداً وأوّلاً نزولاً. فمن
    نقر عموداً نصفُ خاناته فارغةٌ ليرى أكبرَه رأى الفراغَ كلَّه أوّلاً ولم يرَ
    شيئاً. والقصدُ من النقر رؤيةُ القِيَم — فالعَدَمُ في الذيل في الحالين.
    """
    name, flipped = (field[1:], True) if field.startswith("-") else (field, False)
    descending = descending != flipped
    expression = F(name)
    return expression.desc(nulls_last=True) if descending else expression.asc(nulls_last=True)


def apply_sort(
    queryset,
    request,
    allowed: dict[str, tuple[str, ...]],
    default: str,
    default_desc: bool = False,
    desc_first: tuple[str, ...] = (),
):
    """يُرتّب `queryset` وفق `?sort=` و`?dir=` ضمن `allowed` وحدها.

    `allowed` تُسمّي المفتاحَ الظاهرَ في الرابط وتربطُه بحقول ORM التي يُرتَّب بها
    (أكثرُ من حقلٍ حين يحتاج الترتيبُ فاصلاً يقطع التساوي)، و`default_desc` هو
    اتّجاهُ الشاشة قبل أن ينقر القارئُ شيئاً — أحدثُ التواريخ أوّلاً في السجلّات.

    ويُعاد الاستعلامُ وحالةُ الفرز معاً — والحالةُ هي ما يرسم به القالبُ الأسهم.
    """
    asked = request.GET.get("sort")
    key = asked if asked in allowed else default
    if asked in allowed:
        asked_dir = request.GET.get("dir")
        if asked_dir in ("asc", "desc"):
            descending = asked_dir == "desc"
        else:
            # رابطٌ بلا اتّجاه (قائمةٌ منسدلةٌ مثلاً): يأخذ اتّجاهَ العمود الطبيعيّ.
            descending = key in desc_first
    else:
        # لا فرزَ مطلوباً: يبقى ترتيبُ الشاشة الأصليّ كما اعتاده القارئ.
        descending = default_desc

    fields = allowed[key]
    ordering = [_order(f, descending) for f in fields]
    state = SortState(
        key=key,
        descending=descending,
        allowed=allowed,
        desc_first=frozenset(desc_first),
    )
    return queryset.order_by(*ordering), state

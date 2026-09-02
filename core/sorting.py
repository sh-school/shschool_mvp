"""فرزُ القوائم المقسَّمة صفحاتٍ — من الخادم لا من المتصفّح.

الجدولُ المقسَّمُ صفحاتٍ لا يُفرَز في المتصفّح: الصفحةُ الظاهرةُ أربعون صفّاً من
ألفٍ، وفرزُها يُوهم القارئَ أنّه رأى الأعلى وهو أعلى صفحةٍ واحدة. فالترتيبُ
يقع على الاستعلام كلِّه قبل التقسيم، ثمّ تُقسَّم النتيجةُ المرتَّبة.

والحقولُ المسموحُ الفرزُ بها تُصرَّح في كلّ شاشةٍ صراحةً: `?sort=` نصٌّ يأتي من
المستخدم، فلو مُرِّر إلى `order_by` كما هو لفُتحت العلاقاتُ كلُّها أمامه.
"""

from __future__ import annotations

from dataclasses import dataclass, field


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


def _flip(field: str) -> str:
    return field[1:] if field.startswith("-") else f"-{field}"


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

    # الحقلُ المصرَّحُ قد يأتي معكوساً أصلاً («-created_at» فاصلاً يقطع التساوي)،
    # فالتنازليُّ يعكسه لا يُضاعف إشارتَه — وإلّا صار «--created_at» حقلاً لا وجودَ له.
    fields = allowed[key]
    ordering = [_flip(f) if descending else f for f in fields]
    state = SortState(
        key=key,
        descending=descending,
        allowed=allowed,
        desc_first=frozenset(desc_first),
    )
    return queryset.order_by(*ordering), state

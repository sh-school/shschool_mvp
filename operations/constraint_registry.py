"""constraint_registry.py — سجلُّ قيود الجدول: رمزٌ واحدٌ لكلّ قيدٍ واسمٌ يُقرأ.

    الكودُ يعرّف، والقاعدةُ تستثني.

القيودُ سلوكُ خوارزميّةٍ لا صفةَ كيان، فمصدرُ حقيقتها الشيفرةُ لا صفوفُ جدول.
وصفرُ صفوفٍ في `ScheduleConstraintOverride` يعني «افتراضُ الكود بالضبط» — فلا
بذرةَ تُزرع، ولا انحرافَ بين إنتاجٍ ومحلّيّ، ولا أمرَ مزامنةٍ ثالث. وكلُّ صفٍّ
هناك انحرافٌ متعمَّدٌ له صاحبٌ وتاريخ.

**رتبةُ الكسر لا زرُّ الإطفاء.** في تاريخ قيود هذه المنصّة لم يُطفأ قيدٌ قطّ:
عولج التلاصقُ بمعايرة الرقم (٣ ← ٢ ← ١)، والخميسُ بتضييق النطاق على الحادي
عشر والثاني عشر، والتباعدُ بنطاق المرحلة. والإطفاءُ يتساهل ولا يشدّد — وثمنُه
مقيس: السماحُ بالتلاصق من البداية يُنتج ثمانيةً وتسعين زوجاً عند خمسةٍ
وأربعين معلّماً، والرخصةُ في آخر خطوةٍ تُنتج زوجاً لكلّ متعذّرة.

فالرتبةُ تقول **متى يُكسَر القيدُ إن ضاق الجدول**، وهي ثلاثُ درجاتٍ توافق
رخصتَي `_run_attempt` القائمتين:

    never     لا يُكسَر — وإن بقيت حصّةٌ بلا موضع
    relaxed   يُكسَر في الرخصة الأولى (`allow_adjacent`)
    dense     يُكسَر في الرخصة الثانية وحدَها (`allow_dense`)

والنواةُ لا رتبةَ لها تُحرَّر: خرقُها يُنتج جدولاً مستحيلاً في الواقع لا
مزعجاً — معلّمٌ في غرفتين، أو ملعبٌ يسع أربعين فيه ثمانون، أو معلّمٌ ينتقل
طابقاً في صفر ثانية.
"""

from __future__ import annotations

from dataclasses import dataclass

#: رتبُ الكسر — والترتيبُ من الأشدّ إلى الأليَن.
NEVER, RELAXED, DENSE = "never", "relaxed", "dense"

BREAK_CHOICES = [
    (NEVER, "لا يُكسَر"),
    (RELAXED, "يُكسَر في الرخصة الأولى"),
    (DENSE, "يُكسَر في الملاذ الأخير"),
]

HARD, SOFT = "hard", "soft"


@dataclass(frozen=True)
class ConstraintSpec:
    """وصفُ قيدٍ واحد كما تعرّفه الشيفرة."""

    code: str
    title: str
    kind: str
    #: رتبةُ الكسر للصلب — ووزنُ الترجيح للمرن.
    break_at: str = NEVER
    weight: float = 0.0
    #: أتُحرَّر رتبتُه من لوحة الإدارة؟ النواةُ لا، ولا القرارُ في حقّ شخص.
    tunable: bool = True
    #: أتعرف دالّتُه كيف تلين بنفسها حين تُرخى؟
    #:
    #: التلاصقُ يرفع سقفَه من واحدٍ إلى اثنين ولا يُلغى — فلو تُخُطّي كلَّه عند
    #: الرخصة لظهرت ثلاثيّاتٌ ورباعيّات. وأمّا خميسُ الثانويّ فلا سقفَ له
    #: يُرفع: كسرُه تخطّيه في تلك الجولة وحدَها.
    relaxes_in_place: bool = False
    note: str = ""


def _hard(code, title, break_at=NEVER, tunable=True, relaxes_in_place=False, note=""):
    return ConstraintSpec(
        code,
        title,
        HARD,
        break_at=break_at,
        tunable=tunable,
        relaxes_in_place=relaxes_in_place,
        note=note,
    )


def _soft(code, title, weight, note=""):
    return ConstraintSpec(code, title, SOFT, weight=weight, note=note)


#: القيودُ الصلبة — الرتبةُ الافتراضيّةُ هنا هي ما يفعله المولّدُ اليوم بالضبط.
#: من قَبِل رخصةً في `is_slot_valid` فرتبتُه رتبتُها، ومن لم يقبل فـ`never`.
HARD_CONSTRAINTS = (
    _hard("HC1", "المعلّم لا يُدرّس شعبتين معاً", tunable=False, note="نواة"),
    _hard("HC2", "الشعبة لا تأخذ مادّتين معاً", tunable=False, note="نواة"),
    _hard("HC4", "سقفُ حصص اليوم", tunable=False, note="الخميس: إعداديٌّ ستٌّ وثانويٌّ سبع"),
    _hard("HC5", "لا أكثرَ من حصّتين متلاصقتين", break_at=RELAXED, relaxes_in_place=True),
    _hard("HC6", "المادّةُ تُوزَّع على الأيّام بالقسمة", break_at=DENSE, relaxes_in_place=True),
    _hard("HC7", "لا تُكدَّس المادّةُ في حصّةٍ واحدةٍ من اليوم"),
    _hard("HC8", "لا تتكدّس السابعةُ على معلّم"),
    _hard("HC9", "سعةُ المورد في التوقيت", tunable=False, note="نواة"),
    _hard(
        "HC10",
        "فراغُ المعلّم لا يتجاوز سقفَه الشخصيّ",
        tunable=False,
        note="قرارٌ في حقّ الشخص يسبق كلّ رخصة",
    ),
    _hard("HC11", "موردٌ لا يجمع مرحلتين في التوقيت"),
    _hard("HC12", "لا تداخلَ بالساعة بين الجرسين", tunable=False, note="نواة"),
    _hard("HC13", "لا تماسَّ بين طابقين", tunable=False, note="نواة — الانتقالُ يحتاج زمناً"),
    _hard("HC14", "لا يومَ فارغاً لمعلّمٍ تامّ النصاب", break_at=DENSE, relaxes_in_place=True),
    _hard("HC16", "لا يومَ فوق حصّة القسمة"),
    _hard("HC16B", "احتياطُ الحدّ الأدنى لليوم", break_at=DENSE, relaxes_in_place=True),
    _hard("HC17", "لا حصّتان لمادّةٍ يومَ الخميس في 11 و12"),
    _hard("HC18", "حصصُ المادّة في أيّامٍ مختلفة"),
    _hard("HC19", "المزدوجةُ لا تعبر فسحةً ولا صلاة", tunable=False, note="نواة"),
)

#: القيودُ المرنة — أوزانُها هي مفاتيحُ `scheduler_constraints.WEIGHTS`.
SOFT_CONSTRAINTS = (
    _soft("consecutive", "تلاصقُ حصص المعلّم", 10),
    _soft("gap", "فراغاتُ المعلّم", 8),
    _soft("subject_spread", "تفريقُ حصص المادّة", 6),
    _soft("daily_load", "الحملُ اليوميّ", 5),
    _soft("day_balance", "توازنُ الأيّام", 6),
    _soft("thursday_pair", "حصّتا المادّة يومَ الخميس", 15),
    _soft("core_early", "الموادُّ الأساسيّةُ مبكّراً", 3),
    _soft("pe_after_break", "البدنيّةُ بعد الاستراحة", 2),
    _soft("double_bonus", "مكافأةُ الحصّة المزدوجة", -5),
    _soft("high_weekly_adjacent", "تلاصقُ مادّةٍ عاليةِ النصاب", 7),
    _soft("extra_edge_period", "طرفٌ زائدٌ للمعلّم (أولى أو سابعة)", 12),
    _soft("free_day", "يومُ التفريغ الذي طلبه المعلّم", 14),
)

REGISTRY: dict[str, ConstraintSpec] = {
    spec.code: spec for spec in (*HARD_CONSTRAINTS, *SOFT_CONSTRAINTS)
}

#: ما يقبل التحرير من لوحة الإدارة — والنواةُ ليست منه.
TUNABLE_CODES = tuple(code for code, spec in REGISTRY.items() if spec.tunable)


def spec(code: str) -> ConstraintSpec | None:
    return REGISTRY.get(code)


@dataclass(frozen=True)
class ConstraintPolicy:
    """ما يسري فعلاً في هذا العام: افتراضُ الكود وقد طُبّقت عليه الاستثناءات.

    يُبنى مرّةً واحدةً قبل التوليد ويُمرَّر مجمَّداً — ولا استعلامَ في الحلقة
    الساخنة بحال: استعلامُ الجرس فيها كلّف سبعمئةً وخمساً وثلاثين ثانيةً على
    Railway قبل أن يُنقَل خارجَها.
    """

    breaks: dict[str, str]
    weights: dict[str, float]
    #: ما خالف افتراضَ الكود — للعرض والتوثيق لا للحساب.
    overridden: tuple[str, ...] = ()

    def break_at(self, code: str) -> str:
        return self.breaks.get(code, NEVER)

    def weight(self, name: str) -> float:
        return self.weights.get(name, 0.0)

    def licence(self, code: str, allow_adjacent: bool, allow_dense: bool) -> bool:
        """أسارٍ على هذا القيد ترخيصُ هذه الجولة؟

        والرخصةُ الثانيةُ تحمل الأولى: من كُسر عند التلاصق يُكسَر عند الكثافة
        أيضاً — الجولاتُ تتراكم ولا تتبادل.
        """
        at = self.break_at(code)
        if at == RELAXED:
            return allow_adjacent or allow_dense
        if at == DENSE:
            return allow_dense
        return False

    def as_dict(self) -> dict:
        return {"breaks": dict(self.breaks), "overridden": list(self.overridden)}


def default_policy() -> ConstraintPolicy:
    """ما تقوله الشيفرةُ وحدَها — بلا قاعدةِ بيانات."""
    return ConstraintPolicy(
        breaks={s.code: s.break_at for s in HARD_CONSTRAINTS},
        weights={s.code: s.weight for s in SOFT_CONSTRAINTS},
    )


def resolve(school, academic_year: str) -> ConstraintPolicy:
    """افتراضُ الكود وقد طُبّقت عليه استثناءاتُ هذه المدرسة في هذا العام.

    وما لا يُعرف رمزُه في السجلّ يُطرَح: صفٌّ باقٍ لقيدٍ حُذف من الشيفرة لا
    يجوز أن يغيّر سلوكَ قيدٍ آخر ولا أن يُسقط التوليد.
    """
    from .models import ScheduleConstraintOverride

    policy = default_policy()
    breaks = dict(policy.breaks)
    weights = dict(policy.weights)
    changed = []
    rows = ScheduleConstraintOverride.objects.filter(school=school, academic_year=academic_year)
    for row in rows.only("code", "break_at", "weight"):
        found = REGISTRY.get(row.code)
        if found is None or not found.tunable:
            continue
        if found.kind == HARD and row.break_at:
            breaks[row.code] = row.break_at
            changed.append(row.code)
        elif found.kind == SOFT and row.weight is not None:
            weights[row.code] = row.weight
            changed.append(row.code)
    return ConstraintPolicy(breaks=breaks, weights=weights, overridden=tuple(sorted(changed)))

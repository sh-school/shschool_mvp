"""شرائحُ الدرجات من مئة — جدولٌ واحد.

كان توزيعُ الدرجات على الشرائح (90–100، 80–89 …) سلسلةَ `if` في ثلاثة مواضع:
واجهةُ الرسم البيانيّ، وتقريرُ التقييمات، وستّةُ استعلامات `COUNT` في خدمة
التحليلات. والدرجةُ الحرفيّة (A+ … F) سلسلةً رابعةً بعتباتٍ أخرى — فهي
هنا جدولٌ ثانٍ لا يُخلط بالأوّل: العتباتُ تختلف (95 · 85 · 75 · 65) وكذلك
المعنى.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

Score = int | float | Decimal


@dataclass(frozen=True)
class GradeBand:
    """شريحةٌ من الدرجات: من `low` (شاملةً) إلى ما دون الشريحة الأعلى."""

    low: int
    label: str
    #: رتبةُ الشريحة من الأدنى: `<50` صفر، و`90-100` خمسة.
    rank: int


#: الشرائحُ من الأعلى إلى الأدنى — الترتيبُ جزءٌ من التعريف: `band_of` يختار
#: أوّلَ شريحةٍ لا تقلّ الدرجةُ عن حدّها.
GRADE_BANDS: tuple[GradeBand, ...] = (
    GradeBand(90, "90-100", 5),
    GradeBand(80, "80-89", 4),
    GradeBand(70, "70-79", 3),
    GradeBand(60, "60-69", 2),
    GradeBand(50, "50-59", 1),
    GradeBand(0, "أقل من 50", 0),
)


def band_of(score: Score | None) -> GradeBand | None:
    """الشريحةُ التي تقع فيها الدرجة، و`None` لدرجةٍ لم تُرصد.

    >>> band_of(90).label, band_of(89.9).label, band_of(0).label
    ('90-100', '80-89', 'أقل من 50')
    """
    if score is None:
        return None
    value = float(score)
    for band in GRADE_BANDS:
        if value >= band.low:
            return band
    return GRADE_BANDS[-1]


#: الدرجةُ الحرفيّة من الأعلى إلى الأدنى، وما دون 50 راسب (`F`).
LETTER_GRADES: tuple[tuple[int, str], ...] = (
    (95, "A+"),
    (90, "A"),
    (85, "B+"),
    (80, "B"),
    (75, "C+"),
    (70, "C"),
    (65, "D+"),
    (50, "D"),
)

LETTER_FAIL = "F"
LETTER_MISSING = "—"


def letter_of(score: Score | None) -> str:
    """الدرجةُ الحرفيّة للمجموع السنويّ — `—` لما لم يُرصد.

    >>> letter_of(95), letter_of(94.99), letter_of(49.9), letter_of(None)
    ('A+', 'A', 'F', '—')
    """
    if score is None:
        return LETTER_MISSING
    value = float(score)
    for threshold, letter in LETTER_GRADES:
        if value >= threshold:
            return letter
    return LETTER_FAIL


# ─────────────────────────────────────────────────────────────
# بنيةُ الباقات — ما يوجد منها لكلّ صفٍّ وفصل، وبأيّ وزن
# ─────────────────────────────────────────────────────────────
#
# المرجع: قرار وزير التعليم والتعليم العالي رقم (14) لسنة 2018، صادر
# 2018/06/06 (1439/09/21هـ)، نافذ من 2018/2019، المادّة 3 (صفحتا القرار 4–5):
#
#   «ثانياً: الصفوف (الرابع … الحادي عشر)»
#       الفصل الأول:  15 منتصف الفصل · 5 أعمال الفصل · 20 نهاية الفصل  = 40
#       الفصل الثاني: 15 منتصف الفصل · 5 أعمال الفصل · 40 نهاية الفصل  = 60
#
#   «ثالثاً: الصف الثاني عشر — يقيم طلبة الصف الثاني عشر على النحو التالي:
#       الفصل الدراسي الأول: (40 درجة) من الدرجة المخصصة للمادة في الفصل
#       الدراسي الأول لاختبار نهاية الفصل، ويجرى بأسئلة موحدة على مستوى جميع
#       المدارس …  الفصل الدراسي الثاني: (60 درجة) … لاختبار نهاية الفصل …»
#
# والاستخراج: `04b_academic_deep_part1.md:2176-2181` (جدول 5: `:2240`)،
# و`04e_academic_thirdpass.md:24` (المادّة 2: 40/60 لكلّ الصفوف 1–12).
#
# فالثاني عشر لا منتصفَ فصلٍ له ولا أعمالَ فصل — لا P1 ولا P3 ولا AW.
# وغيابُها بنيويّ: ليست في الجدول أصلاً (`None` لا صفر)، فلا تُنشأ باقةٌ
# بوزن صفر تظهر عموداً فارغاً في الرصد والكشف. والنسبةُ 40/60 نفسُها لا
# تتغيّر (خطّة الإصلاح، «تصحيحٌ جوهري» 2026-09-10).
#
# والوزنُ نسبةٌ من درجة الفصل لا من المئة: 15 من 40 = 37.50٪.

SEMESTER_MAX: dict[str, Decimal] = {"S1": Decimal("40"), "S2": Decimal("60")}

PACKAGE_WEIGHTS_STANDARD: dict[str, dict[str, Decimal]] = {
    "S1": {"P1": Decimal("37.50"), "P2": Decimal("50.00"), "AW": Decimal("12.50")},
    "S2": {"P3": Decimal("25.00"), "P4": Decimal("66.67"), "AW": Decimal("8.33")},
}

PACKAGE_WEIGHTS_GRADE12: dict[str, dict[str, Decimal]] = {
    "S1": {"P2": Decimal("100")},  # اختبارُ نهاية الفصل الأول = الأربعون كلُّها
    "S2": {"P4": Decimal("100")},  # اختبارُ نهاية الفصل الثاني = الستّون كلُّها
}

#: الأوزانُ **دقيقةً** — من درجات القرار نفسِها (15 من 40، 40 من 60): الجدولُ العشريُّ
#: أعلاه للتخزين والعرض (66.67)، والحسابُ بكسرٍ صحيح (2/3) فلا أثرَ لتقريبٍ يُقصّ.
SEMESTER_MAX_EXACT: dict[str, Fraction] = {"S1": Fraction(40), "S2": Fraction(60)}
PACKAGE_MARKS_STANDARD: dict[str, dict[str, int]] = {
    "S1": {"P1": 15, "P2": 20, "AW": 5},
    "S2": {"P3": 15, "P4": 40, "AW": 5},
}
PACKAGE_MARKS_GRADE12: dict[str, dict[str, int]] = {"S1": {"P2": 40}, "S2": {"P4": 60}}

#: الصفُّ الذي له بنيةٌ مستقلّة.
FINAL_GRADE = 12


def package_weights(grade: int, semester: str) -> dict[str, Decimal]:
    """الباقاتُ الموجودة لصفٍّ وفصل وأوزانُها — وما ليس فيها غيرُ موجود.

    >>> sorted(package_weights(12, "S1")), sorted(package_weights(10, "S1"))
    (['P2'], ['AW', 'P1', 'P2'])
    """
    table = PACKAGE_WEIGHTS_GRADE12 if grade == FINAL_GRADE else PACKAGE_WEIGHTS_STANDARD
    return dict(table.get(semester, {}))


def package_weight(grade: int, semester: str, package_type: str) -> Decimal | None:
    """وزنُ باقةٍ واحدة، و`None` لباقةٍ لا وجودَ لها في هذا الصفّ والفصل.

    >>> package_weight(12, "S1", "P1") is None, package_weight(12, "S2", "P4")
    (True, Decimal('100'))
    """
    return package_weights(grade, semester).get(package_type)


def exact_package_weight(
    grade: int, semester: str, package_type: str, stored: Decimal | None = None
) -> Fraction | None:
    """وزنُ الباقة نسبةً صحيحة من مئة: 2/3×100 لا 66.67.

    إن كان الوزنُ المخزَّن تقريبَ الجدول إلى 0.01 فالدقيقُ هو الجدول؛ وإن غيّرته
    المدرسةُ فوزنُها كما كُتب — لا يُستبدل به الجدول.

    >>> exact_package_weight(10, "S2", "P4", Decimal("66.67"))
    Fraction(200, 3)
    >>> exact_package_weight(10, "S2", "P4", Decimal("60"))
    Fraction(60, 1)
    """
    table = PACKAGE_MARKS_GRADE12 if grade == FINAL_GRADE else PACKAGE_MARKS_STANDARD
    marks = table.get(semester, {}).get(package_type)
    exact = None if marks is None else Fraction(marks * 100) / SEMESTER_MAX_EXACT[semester]
    if stored is None:
        return exact
    if exact is not None:
        rounded = (Decimal(exact.numerator) / Decimal(exact.denominator)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if rounded == stored:
            return exact
    return Fraction(stored)


# ─────────────────────────────────────────────────────────────
# جبرُ الكسور — المادّة 8
# ─────────────────────────────────────────────────────────────


def _exact(value: Score | Fraction | str) -> Fraction:
    """القيمةُ كسراً دقيقاً — `Decimal` و`int` بلا فقد، و`float` من نصّه."""
    if isinstance(value, Fraction):
        return value
    if isinstance(value, float):
        return Fraction(Decimal(str(value)))
    if isinstance(value, str):
        return Fraction(Decimal(value))
    return Fraction(value)


def _to_decimal(value: Fraction) -> Decimal:
    """كسرٌ مجبورٌ (مضاعفُ نصف) عدداً عشريّاً: 47 أو 47.5."""
    halves = value * 2
    assert halves.denominator == 1, value
    n = int(halves)
    return Decimal(n // 2) if n % 2 == 0 else (Decimal(n) / 2).quantize(Decimal("0.1"))


def _jabr_exact(value: Fraction) -> Fraction:
    return Fraction(math.ceil(value * 2), 2)


def jabr_fraction(value: Score | Fraction | str | None) -> Decimal | None:
    """جبرُ كسور الدرجة إلى أقرب نصفٍ **صعوداً** — لا تقريبٌ إلى أقرب عدد.

    سياسة تقييم الطلبة للصفوف 4–11 (أغسطس 2015)، المادّة 8، صفحة 9 — نصُّها:
        «عند حساب درجات أية مادة من المواد الدراسية في منتصف الفصل أو نهايته
         أو الدور الثاني تطبق الأحكام الآتية لجبر الكسور:
         1- يجبر ما دون النصف إلى النصف.  2- يثبت النصف.
         3- يجبر ما زاد على النصف إلى واحد صحيح.»
    وسياسة الثاني عشر، المادّة 7 (صفحة 5)، بالنصّ نفسه. والاستخراج:
    `04_academic.md:28` و`:172`.

    فالكسرُ لا يُنزَّل أبداً: 47.2 ← 47.5، و47.5 تثبت، و47.6 ← 48. ويُجبر على
    القيمة **الدقيقة** (`Fraction`) — لا قصَّ إلى 0.01 قبله: القصُّ كان يُنزل كسراً
    حقيقيّاً (19.5025 ← 19.5 لا 20)، والنصُّ لا يُنزل كسراً. (تصحيح 2026-09-15.)

    **وموضعُه** — النصُّ يسمّي لحظاتِ حساب درجة **المادّة**: «في منتصف الفصل أو
    نهايته أو الدور الثاني» (4–11، م8 ص9)، و«في نهاية كل فصل دراسي أو الدور
    الثاني» (الثاني عشر، م7 ص5). فيُجبر اختبارُ منتصف الفصل (P1/P3) ثمّ مجموعُ
    الفصل مرّةً واحدة، ودرجةُ الدور الثاني.

    >>> [str(jabr_fraction(v)) for v in ("47", "47.01", "47.5", "47.51", "49.99")]
    ['47', '47.5', '47.5', '48', '50']
    >>> str(jabr_fraction(Fraction(780101, 40000)))
    '20'
    """
    if value is None:
        return None
    return _to_decimal(_jabr_exact(_exact(value)))


#: الباقاتُ التي هي «منتصفُ الفصل» في م8 — تُجبر وحدَها قبل الجمع.
MIDTERM_PACKAGES = frozenset({"P1", "P3"})

_CENT = Decimal("0.01")


def package_score(package_type: str, raw: Score | Fraction | str) -> Decimal:
    """درجةُ باقةٍ **للعرض والتخزين**: منتصفُ الفصل مجبور (م8)، وغيرُه إلى 0.01.

    العرضُ وحدَه يُقرَّب؛ المجموعُ يُحسب من الخام الدقيق.

    >>> [str(package_score(p, v)) for p, v in (("P1", "7.1"), ("P2", "9.104"), ("AW", "2.1"))]
    ['7.5', '9.10', '2.10']
    """
    value = _exact(raw)
    if package_type in MIDTERM_PACKAGES:
        return _to_decimal(_jabr_exact(value))
    return (Decimal(value.numerator) / Decimal(value.denominator)).quantize(
        _CENT, rounding=ROUND_HALF_UP
    )


def semester_total(raw_scores: Mapping[str, Score | Fraction | str | None]) -> Decimal | None:
    """مجموعُ فصلٍ حضر اختباراته، من درجات باقاته **الخام**، مجبوراً مرّةً (م8).

    يُجبر المنتصفُ أوّلاً، ثمّ يُجمع مع البقيّة خاماً دقيقاً ثمّ يُجبر المجموع.
    (أحكامُ الغياب — م17 وما بعدها — في `judge_student`.)

    >>> str(semester_total({"P1": "7.1", "AW": "2.1", "P2": "9.1"}))
    '19'
    >>> semester_total({"P1": None}) is None
    True
    """
    present = {k: _exact(v) for k, v in raw_scores.items() if v is not None}
    if not present:
        return None
    total = sum(
        (_jabr_exact(v) if k in MIDTERM_PACKAGES else v for k, v in present.items()), Fraction(0)
    )
    return jabr_fraction(total)


# ─────────────────────────────────────────────────────────────
# الحكمُ الواحد — نتيجةُ الطالب في كلّ مادّة، والدورُ الثاني، والترفيع
# ─────────────────────────────────────────────────────────────
#
# الأصل: `04- سياسة تقييم الطلاب من الرابع حتى الحادي عشر.pdf` (أغسطس 2015)
# و`04- سياسة تقييم الطلبة للصف الثاني عشر.pdf` في `data/2026-2027/03- الأكاديمي/`،
# بأرقام الصفحات المطبوعة (صفحةُ PDF = المطبوعة + 1):
#
#  4–11
#   م12 ص18  يدخل الدورَ الثاني: أ- الراسبون في ثلاث موادّ أو أقلّ؛ ب- المتغيّبون
#            «عن تأدية اختبارات نهاية الفصل الدراسي الأول أو الثاني بعذر مقبول»؛
#            ج- الجامعون بينهما «يختبرون فيما رسبوا فيه وفيما تغيبوا عنه».
#   م13 ص18  لا يدخله المتغيّبون بلا عذر عن نهاية الفصل الثاني في أكثر من ثلاث.
#   م14 ص18  الدورُ الثاني «بواقع 100% من النهاية العظمى» للمعذور عن الفصلين وللراسب.
#   م15 ص18  «لا يسمح للطالب الذي يتغيب عن اختبار مادة دراسية بكاملها في الدور الثاني
#            بالاستمرار في تأدية اختبارات باقي المواد (مهما كان سبب الغياب)».
#   م16 ص18  درجةُ الناجح في الدور الثاني: الراسبُ والمحرومُ «النهاية الصغرى للمادة
#            فقط»، والمعذورُ «الدرجة التي يحصل عليها في الدور الثاني، كما تحسب له
#            الدرجة الكلية للمادة وفقاً لما تنص عليه هذه السياسة».
#   م17 ص20  المعذورُ عن منتصف الفصل «يختبر في نهاية الفصل بواقع 100% من الدرجة
#            المخصصة للفصل»، وغيرُ المعذور «غائب» ويُختبر بواقع درجة النهاية «وتضاف له
#            نسبة ما حصل عليه من النسبة المخصصة لأعمال الفصل».
#   م18 ص20  المعذورُ عن الفصل الأول بكامله «يجرى له اختبار ملحق … وتحسب له درجة هذا
#            الاختبار بواقع 100% من الدرجة المخصصة للفصل الدراسي الأول».
#   م19 ص20  من حضر المنتصفَ والأعمالَ وعُذر عن النهاية: ملحقٌ «وتجمع درجات هذا الاختبار
#            مع درجات الطالب في اختبار منتصف الفصل الدراسي الأول وأعمال الفصل».
#   م20 ص20  وإن غاب عن الملحق «(سواء أكان الغياب بعذر أم بدون عذر)» فالنهايةُ «غائب»
#            ودرجةُ الفصل الأول منتصفُه وأعمالُه، ويُحكم بمجموع الفصلين.
#   م21 ص20  المعذورُ عن الفصل الأول بكامله **والملحق**: لا يدخل الفصلَ الثاني في المادّة،
#            ويدخل الدورَ الثاني «(منهاج الفصلين الدراسيين) بواقع 100%».
#   م22 ص21  الغائبُ بلا عذر عن الفصل الأول بكامله: لا يدخل الفصلَ الثاني في المادّة
#            «وتحسب ضمن مواد الرسوب». م23: وأكثرُ من ثلاث «راسباً وباقياً للإعادة».
#   م24 ص21  ذواتُ الفرعين: المعذورُ عن جزءٍ من المنتصف يُختبر في النهاية بواقع درجة
#            ذلك الجزء؛ وعن جزءٍ من نهاية الأول «يؤجل إلى اختبار الملحق»؛ والغائبُ عن
#            جزءٍ من نهاية الثاني (بعذر أو بدونه) يُحكم بمجموعه.
#   م25 ص22  المعذورُ عن نهاية الثاني وحدَها: دورٌ ثانٍ في منهاج الفصل الثاني «وتجمع
#            درجات هذا الاختبار مع درجات اختبار منتصف الفصل الثاني وأعمال الفصل الثاني
#            وتضاف إلى درجات الطالب في الفصل الدراسي الأول».
#   م26 ص22  المعذورُ عن الفصل الثاني كلِّه: دورٌ ثانٍ «بواقع 100% من الدرجة المخصصة
#            للفصل الدراسي الثاني، وتضاف إلى درجاته في الفصل الدراسي الأول».
#   م27 ص22  الغائبُ بلا عذر عن نهاية الثاني: «الدرجة النهائية للمادة (مجموع الفصلين)
#            "غائب" أي لا يحتسب له درجات الفصل الأول، وتحسب المادة ضمن مواد الرسوب».
#   م29 ص22–23 الحرمانُ بأيّام الغياب (والعتباتُ النافذةُ من دليل 2026): 1) منتصف الأول،
#            2) نهاية الأول، 3) منتصف الثاني — «(جميع المواد)»؛ 4) الدور الأول: «يسمح
#            له بدخول اختبار الدور الثاني بواقع 100% من النهاية العظمى للمواد».
#   م30 ص23  «الطالب المتغيب بعذر مقبول … يرصد له كلمة "معذور"، أما المتغيب بدون عذر
#            فيرصد له كلمة "غائب". أما الطالب المحروم من دخول الاختبار بسبب الغياب عن
#            أيام التمدرس فيرصد له كلمة "محروم"».
#   م50 ص33  «تحكم مراجعة النتائج وترفيع الطالب الراسب القواعد الآتية»: الأولى — حاجتُه
#            «لا تزيد عن درجتين»؛ الثانية — «في مادتين» أربعُ درجاتٍ في كلٍّ؛ الثالثة —
#            «في مادة وحيدة»: 75% فأكثر في كلّ مادّةٍ باقية و40% فأكثر في مادّة الرسوب،
#            «وتطبق هذه القاعدة في الدور الثاني فقط»، «على أن يرصد في كشوف الدرجات
#            والشهادة الدرجة التي حصل عليها الطالب في اختبار الدور الثاني». م51: قاعدةٌ
#            واحدةٌ فقط. والقيدُ «في الدور الثاني فقط» بعد الثالثة وحدَها — فالأوليان
#            تُراجَع بهما نتيجةُ الدورين.
#
#  الثاني عشر (م8–م12 ص7–8 مقابلُ م12–م16؛ وأحكامُ الغياب ص10–11)
#   م13 ص10  المعذورُ عن نهاية الفصل الأول: «ب- لا يسمح له بدخول اختبار الفصل الدراسي
#            الثاني في المواد التي تغيب عنها بعذر مقبول … ويعتبر معذوراً فيها. ت- يسمح
#            له بدخول اختبار الدور الثاني في مواد التغيب (منهاج الفصلين)».
#   م14/م15  الغائبُ بلا عذر عن الفصل الأول: لا فصلَ ثانياً فيها «وتحسب ضمن مواد الرسوب»؛
#            وأكثرُ من ثلاث «راسباً وباقياً للإعادة».
#   م16 ص10  المعذورُ عن نهاية الثاني: دورٌ ثانٍ «(منهاج الفصلين) … ولا تحسب له درجات
#            الفصل الأول». م17 ص11: الغائبُ بلا عذر عنها «غائب» ومن موادّ الرسوب.
#   م19 ص11  الحرمان: 1) نهاية الفصل الأول — «ولا يسمح له بالتقدم لاختبار نهاية الفصل
#            الثاني، ويسمح له بالتقدم لاختبار الدور الثاني بواقع 100%»؛ 2) نهاية الثاني
#            — «(تلغى درجات الطالب في الفصل الأول) ويسمح له بدخول اختبار الدور الثاني».
#   ولا قواعدَ ترفيعٍ ولا ملحقَ في سياسة الثاني عشر.
#
#  «ملغي» — م45 مكرر (قرار 30/2018): «ولا يحق له دخول اختبارات الدور الثاني».
#
# والحرمانُ **قرارٌ** لفريق إدارة سلوك الطلبة (`08_conduct_policy_2026.md:107-137`)
# لا عدّادُ أيّام: الحكمُ يقرأ القرارَ المسجَّل (`deprived_gates`)، وبلوغُ العتبة بلا
# قرارٍ تنبيهٌ يُعرض ولا يُحكم به.

PASS_MARK = Decimal("50")
MAX_FAILED_FOR_SECOND_ROUND = 3
FULL_MARK = Decimal("100")
PROMOTION_RULE_1_GAP = 2
PROMOTION_RULE_2_GAP = 4
#: القاعدةُ الثالثة (م50): 75% في كلّ مادّةٍ باقية، و40% في مادّة الرسوب.
PROMOTION_RULE_3_OTHERS = Decimal("75")
PROMOTION_RULE_3_FAILED = 40

_PASS = Fraction(50)

# ── علاماتُ الاختبار (م30): كلمةٌ تُرصد مكانَ الدرجة ──
PRESENT = "present"
ABSENT = "absent"
EXCUSED_MARK = "excused"
DEPRIVED_MARK = "deprived"

MARK_CHOICES: tuple[tuple[str, str], ...] = (
    (ABSENT, "غائب"),
    (EXCUSED_MARK, "معذور"),
    (DEPRIVED_MARK, "محروم"),
)
MARK_LABELS = dict(MARK_CHOICES)

# ── حالةُ المادّة المخزَّنة (`AnnualSubjectResult.status`) ──
STATUS_PASS = "pass"
STATUS_PROMOTED = "promoted"
STATUS_FAIL = "fail"
STATUS_SECOND_ROUND = "second_round"
STATUS_EXCUSED = "excused"
STATUS_DEPRIVED = "deprived"
STATUS_MAKEUP = "makeup"
STATUS_INCOMPLETE = "incomplete"

RESULT_STATUS_CHOICES: tuple[tuple[str, str], ...] = (
    (STATUS_PASS, "ناجح"),
    (STATUS_PROMOTED, "مُرفَّع"),
    (STATUS_FAIL, "راسب"),
    (STATUS_SECOND_ROUND, "راسب — دور ثانٍ"),
    (STATUS_EXCUSED, "معذور — دور ثانٍ"),
    (STATUS_DEPRIVED, "محروم — دور ثانٍ"),
    (STATUS_MAKEUP, "بانتظار الملحق"),
    (STATUS_INCOMPLETE, "غير مكتمل"),
)
RESULT_STATUS_LABELS = dict(RESULT_STATUS_CHOICES)

#: **التعريفُ الواحد** لـ«ناجح/راسب/معلَّق» — كلُّ مستهلكٍ يعدّ بهذه لا بنصٍّ حرفيّ.
PASSING_STATUSES: tuple[str, ...] = (STATUS_PASS, STATUS_PROMOTED)
FAILING_STATUSES: tuple[str, ...] = (STATUS_FAIL, STATUS_SECOND_ROUND)
PENDING_STATUSES: tuple[str, ...] = (
    STATUS_EXCUSED,
    STATUS_DEPRIVED,
    STATUS_MAKEUP,
    STATUS_INCOMPLETE,
)
#: موادُّ يُختبر فيها في الدور الثاني.
SITTING_STATUSES: tuple[str, ...] = (STATUS_SECOND_ROUND, STATUS_EXCUSED, STATUS_DEPRIVED)

BUCKET_PASSED, BUCKET_FAILED, BUCKET_PENDING = "passed", "failed", "pending"


def status_bucket(status: str) -> str:
    """«ناجح» أو «راسب» أو «معلَّق» لحالة مادّةٍ مخزَّنة.

    >>> status_bucket("promoted"), status_bucket("second_round"), status_bucket("deprived")
    ('passed', 'failed', 'pending')
    """
    if status in PASSING_STATUSES:
        return BUCKET_PASSED
    if status in FAILING_STATUSES:
        return BUCKET_FAILED
    return BUCKET_PENDING


#: نغمةُ الشارة — أسماءٌ محايدة يترجمها كلُّ عرضٍ إلى صنفه.
STATUS_TONES: dict[str, str] = {
    STATUS_PASS: "success",
    STATUS_PROMOTED: "success",
    STATUS_FAIL: "danger",
    STATUS_SECOND_ROUND: "maroon",
    STATUS_EXCUSED: "info",
    STATUS_DEPRIVED: "warning",
    STATUS_MAKEUP: "warning",
    STATUS_INCOMPLETE: "gray",
}

# ── موقفُ الطالب (`AnnualSubjectResult.standing` — واحدٌ في كلّ موادّه) ──
STANDING_PASSED = "passed"
STANDING_PROMOTED = "promoted"
STANDING_SECOND_ROUND = "second_round"
STANDING_FAILED = "failed"
STANDING_INCOMPLETE = "incomplete"

STANDING_CHOICES: tuple[tuple[str, str], ...] = (
    (STANDING_PASSED, "ناجح"),
    (STANDING_PROMOTED, "ناجح بالترفيع"),
    (STANDING_SECOND_ROUND, "دور ثانٍ"),
    (STANDING_FAILED, "راسب"),
    (STANDING_INCOMPLETE, "غير مكتمل"),
)
STANDING_LABELS = dict(STANDING_CHOICES)
STANDING_TONES: dict[str, str] = {
    STANDING_PASSED: "success",
    STANDING_PROMOTED: "success",
    STANDING_SECOND_ROUND: "maroon",
    STANDING_FAILED: "danger",
    STANDING_INCOMPLETE: "warning",
}
#: الموقفُ الذي يُعدّ به الطالبُ ناجحاً أو راسباً في العدّ.
PASSING_STANDINGS: tuple[str, ...] = (STANDING_PASSED, STANDING_PROMOTED)
FAILING_STANDINGS: tuple[str, ...] = (STANDING_FAILED, STANDING_SECOND_ROUND)

#: عتباتُ الحرمان التي يُسجَّل بها قرارُ الفريق (مفاتيحُ `operations.absence_policy`).
GATE_S1_MIDTERM, GATE_S1_FINAL = "s1_midterm", "s1_final"
GATE_S2_MIDTERM, GATE_S2_FINAL = "s2_midterm", "s2_final"
GATE_CHOICES: tuple[tuple[str, str], ...] = (
    (GATE_S1_MIDTERM, "اختبار منتصف الفصل الأول"),
    (GATE_S1_FINAL, "اختبار نهاية الفصل الأول"),
    (GATE_S2_MIDTERM, "اختبار منتصف الفصل الثاني"),
    (GATE_S2_FINAL, "اختبار نهاية الفصل الثاني (الدور الأول)"),
)


@dataclass(frozen=True)
class ExamFacts:
    """باقةٌ واحدة (اختبارٌ أو أعمال) لطالبٍ في مادّة — وقائعُ لا حكم.

    `score` الدرجةُ الدقيقة من درجة الفصل بعد الوزن (الجزءُ الغائبُ صفر)، و`None` إن لم
    يُرصد شيء. و`out_of` نصيبُ الباقة من الفصل (15، 20، 40 …). والحصّتان نسبةُ ما غاب
    عنه من وزن الباقة بعذرٍ وبغيره.
    """

    score: Fraction | None = None
    out_of: Fraction = Fraction(0)
    excused_share: Fraction = Fraction(0)
    absent_share: Fraction = Fraction(0)

    @property
    def mark(self) -> str:
        """«معذور» أو «غائب» عن الاختبار **كلِّه** (م24: الجزءُ ليس غياباً عن الاختبار).

        وغيابٌ كلُّه بعضُه بعذر «معذور» — حالٌ لا يسمّيها النصّ، والعذرُ يُحيل إلى ملحقٍ
        أو دورٍ يُختبر فيه لا إلى رسوب.
        """
        if self.excused_share + self.absent_share == 1:
            return EXCUSED_MARK if self.excused_share else ABSENT
        return PRESENT

    @property
    def attended_pct(self) -> Fraction | None:
        """نسبةُ ما حصّله فيما لم يُعذر عنه — أساسُ «بواقع 100%» (م17، م24)."""
        base = self.out_of * (1 - self.excused_share)
        if self.score is None or not base:
            return None
        return self.score / base


@dataclass(frozen=True)
class MakeupFacts:
    """اختبارُ الملحق للفصل الأول (4–11، م18–م20): علامتُه ونسبةُ ما حصّل من قصواه."""

    mark: str = PRESENT
    pct: Fraction | None = None


@dataclass(frozen=True)
class SecondRoundFacts:
    """ما رُصد في الدور الثاني: الدرجةُ من قصوى اختباره (`second_round_max`)، أو الغياب."""

    score: Fraction | None = None
    absent: bool = False


@dataclass(frozen=True)
class SubjectFacts:
    key: str
    s1: Mapping[str, ExamFacts] = field(default_factory=dict)
    s2: Mapping[str, ExamFacts] = field(default_factory=dict)
    makeup: MakeupFacts | None = None
    second_round: SecondRoundFacts | None = None


@dataclass(frozen=True)
class SubjectVerdict:
    key: str
    status: str
    s1_total: Decimal | None
    s2_total: Decimal | None
    annual_total: Decimal | None
    #: الكلمةُ مكانَ المجموع (م30): «غائب»/«معذور»/«محروم»، أو "".
    mark: str
    article: str
    #: قصوى اختبار الدور الثاني لهذه المادّة (م14، م25، م26)، و`None` لمن لا يدخله.
    second_round_max: Decimal | None = None

    @property
    def label(self) -> str:
        return RESULT_STATUS_LABELS[self.status]


@dataclass(frozen=True)
class StudentVerdict:
    standing: str
    article: str
    subjects: tuple[SubjectVerdict, ...]

    @property
    def label(self) -> str:
        return STANDING_LABELS[self.standing]

    def by_key(self) -> dict[str, SubjectVerdict]:
        return {v.key: v for v in self.subjects}


#: أرقامُ الموادّ بين السياستين: (4–11، الثاني عشر).
_ARTICLES = {
    "eligible": ("م12", "م8"),
    "barred": ("م13", "م9"),
    "barred_s1": ("م23", "م15"),
    "deprived_first_round": ("م29-4", "م19-2"),
    "cancelled": ("م45 مكرر", "م33 مكرر"),
    "passed": ("م10–11", "م6"),
    "credit": ("م16", "م12"),
    "second_round_absent": ("م15", "م11"),
}

FINAL_GRADE_S1_DEPRIVED_ARTICLE = "م19-1"


def _art(key: str, grade: int, suffix: str = "") -> str:
    return _ARTICLES[key][grade == FINAL_GRADE] + suffix


# ── الجولةُ الأولى لمادّةٍ واحدة ──

_SCORED, _MAKEUP = "scored", "makeup"
_EXCUSED, _ABSENT_S1, _ABSENT_FINAL = "excused", "absent_s1", "absent_final"


@dataclass(frozen=True)
class _Round1:
    state: str
    s1: Fraction | None = None
    s2: Fraction | None = None
    article: str = ""
    #: المعذور: ما يُضاف إلى درجة دوره الثاني (م25، م26)، وقصوى اختباره.
    carried: Fraction = Fraction(0)
    retake_max: Fraction = Fraction(100)

    @property
    def total(self) -> Fraction | None:
        if self.s1 is None and self.s2 is None:
            return None
        return (self.s1 or Fraction(0)) + (self.s2 or Fraction(0))


def _sum(parts: list[Fraction | None]) -> Fraction | None:
    present = [p for p in parts if p is not None]
    return sum(present, Fraction(0)) if present else None


def _jabr_or_none(value: Fraction | None) -> Fraction | None:
    return None if value is None else _jabr_exact(value)


def _mid(exam: ExamFacts | None, deprived: bool) -> Fraction | None:
    """منتصفُ الفصل مجبوراً (م8)، والمحرومُ منه صفر (م29 1–3، م30)."""
    if deprived:
        return Fraction(0)
    if exam is None or exam.score is None:
        return None
    return _jabr_exact(exam.score)


def _score(exam: ExamFacts | None, deprived: bool = False) -> Fraction | None:
    if deprived:
        return Fraction(0)
    return None if exam is None else exam.score


def _mark(exam: ExamFacts | None, deprived: bool = False) -> str:
    if deprived:
        return DEPRIVED_MARK
    return PRESENT if exam is None else exam.mark


def _others(ex: Mapping[str, ExamFacts], known: frozenset[str]) -> list[Fraction | None]:
    """باقاتٌ خارج بنية الجدول (أوزانٌ قرّرتها مدرسة) — تُجمع كما هي بلا حكم غياب."""
    return [e.score for k, e in ex.items() if k not in known]


_S1_KNOWN = frozenset({"P1", "P2", "AW"})
_S2_KNOWN = frozenset({"P3", "P4", "AW"})


def _borrowed(final: ExamFacts | None, part: Fraction) -> Fraction:
    """م24 «أولاً-1»: ما عُذر عنه من المنتصف يُحتسب بنسبة ما حصّله في النهاية."""
    if not part or final is None or final.attended_pct is None:
        return Fraction(0)
    return final.attended_pct * part


def _first_semester_standard(
    ex: Mapping[str, ExamFacts], makeup: MakeupFacts | None, gates: frozenset[str]
) -> _Round1:
    p1, p2, aw = ex.get("P1"), ex.get("P2"), ex.get("AW")
    dep_mid, dep_fin = GATE_S1_MIDTERM in gates, GATE_S1_FINAL in gates
    m1, m2 = _mark(p1, dep_mid), _mark(p2, dep_fin)

    if m1 == ABSENT and m2 == ABSENT:
        # م22 — والمحرومُ ليس «غائباً» (م30)، فلا يُعدّ هنا ولا في م23.
        return _Round1(_ABSENT_S1, article="م22")

    mid, aw_s = _mid(p1, dep_mid), _score(aw)
    p2_excused = Fraction(0) if (dep_fin or p2 is None) else p2.excused_share

    if p2 is not None and p2_excused:
        whole = m1 == EXCUSED_MARK and m2 == EXCUSED_MARK
        if makeup is None:
            # م18 / م19: الملحقُ أوّلاً — لا دورَ ثانياً قبله.
            return _Round1(_MAKEUP, article="م18" if whole else "م19")
        if whole:
            if makeup.mark == PRESENT and makeup.pct is not None:
                s1 = _jabr_exact(makeup.pct * SEMESTER_MAX_EXACT["S1"])
                return _Round1(_SCORED, s1=s1, article="م18")
            if makeup.mark == EXCUSED_MARK:
                return _Round1(_EXCUSED, article="م21", retake_max=Fraction(100))
            # غائبٌ بلا عذر عن الملحق بعد عذرٍ عن الفصل كلِّه — صمتٌ في النصّ؛ والأقربُ
            # م20 («سواء أكان الغياب بعذر أم بدون عذر»): درجةُ الفصل ما حضره.
            return _Round1(_SCORED, s1=_jabr_exact(aw_s or Fraction(0)), article="م20")
        base = [mid, aw_s, p2.score]
        if makeup.mark == PRESENT and makeup.pct is not None:
            total = _sum([*base, makeup.pct * p2_excused * p2.out_of])
            return _Round1(_SCORED, s1=_jabr_or_none(total), article="م19")
        return _Round1(_SCORED, s1=_jabr_or_none(_sum(base)), article="م20")

    if m1 == EXCUSED_MARK:
        # م17: «يختبر في نهاية الفصل بواقع 100% من الدرجة المخصصة للفصل».
        if dep_fin:
            return _Round1(_SCORED, s1=Fraction(0), article="م17")
        pct = None if p2 is None else p2.attended_pct
        from_final = None if pct is None else _jabr_exact(pct * SEMESTER_MAX_EXACT["S1"])
        return _Round1(_SCORED, s1=from_final, article="م17")

    total = _sum([mid, aw_s, _score(p2, dep_fin), *_others(ex, _S1_KNOWN)])
    if total is None:
        return _Round1(_SCORED)
    borrowed = Fraction(0)
    if p1 is not None and not dep_mid and not dep_fin:
        borrowed = _borrowed(p2, p1.excused_share * p1.out_of)
    return _Round1(_SCORED, s1=_jabr_exact(total + borrowed))


def _second_semester_standard(
    ex: Mapping[str, ExamFacts], gates: frozenset[str], s1: Fraction | None
) -> _Round1:
    p3, p4, aw = ex.get("P3"), ex.get("P4"), ex.get("AW")
    dep_mid = GATE_S2_MIDTERM in gates
    m3, m4 = _mark(p3, dep_mid), _mark(p4)
    mid, aw_s = _mid(p3, dep_mid), _score(aw)
    s1_part = s1 or Fraction(0)

    if p4 is not None and m4 == EXCUSED_MARK:
        if m3 == EXCUSED_MARK:
            return _Round1(
                _EXCUSED,
                s1=s1,
                article="م26",
                carried=s1_part,
                retake_max=SEMESTER_MAX_EXACT["S2"],
            )
        carried = s1_part + (mid or Fraction(0)) + (aw_s or Fraction(0))
        return _Round1(_EXCUSED, s1=s1, article="م25", carried=carried, retake_max=p4.out_of)
    if m4 == ABSENT:
        return _Round1(_ABSENT_FINAL, s1=s1, article="م27")
    if m3 == EXCUSED_MARK:
        pct = None if p4 is None else p4.attended_pct
        s2 = None if pct is None else _jabr_exact(pct * SEMESTER_MAX_EXACT["S2"])
        return _Round1(_SCORED, s1=s1, s2=s2, article="م17")
    total = _sum([mid, aw_s, _score(p4), *_others(ex, _S2_KNOWN)])
    borrowed = Fraction(0)
    if p3 is not None and not dep_mid:
        borrowed = _borrowed(p4, p3.excused_share * p3.out_of)
    s2 = None if total is None else _jabr_exact(total + borrowed)
    return _Round1(_SCORED, s1=s1, s2=s2)


def _round1_standard(f: SubjectFacts, gates: frozenset[str]) -> _Round1:
    first = _first_semester_standard(f.s1, f.makeup, gates)
    if first.state != _SCORED:
        # م21 وم22: لا يدخل الفصلَ الثاني في المادّة — فما رُصد له فيه لا يُقرأ.
        return first
    second = _second_semester_standard(f.s2, gates, first.s1)
    if second.state == _SCORED and not second.article:
        return replace(second, article=first.article)
    return second


def _round1_final_grade(f: SubjectFacts) -> _Round1:
    p2, p4 = f.s1.get("P2"), f.s2.get("P4")
    m2 = _mark(p2)
    if m2 == EXCUSED_MARK:
        # م13-ب: لا يدخل الفصلَ الثاني في المادّة «ويعتبر معذوراً فيها» — فعلامتُه فيه لا تُقرأ.
        return _Round1(_EXCUSED, article="م13", retake_max=Fraction(100))
    if m2 == ABSENT:
        return _Round1(_ABSENT_S1, article="م14")
    s1 = _jabr_or_none(_sum([_score(p2), *_others(f.s1, frozenset({"P2"}))]))
    m4 = _mark(p4)
    if m4 == EXCUSED_MARK:
        # م16: «ولا تحسب له درجات الفصل الأول» — دورُه من مئة.
        return _Round1(_EXCUSED, s1=s1, article="م16", retake_max=Fraction(100))
    if m4 == ABSENT:
        return _Round1(_ABSENT_FINAL, s1=s1, article="م17")
    s2 = _jabr_or_none(_sum([_score(p4), *_others(f.s2, frozenset({"P4"}))]))
    return _Round1(_SCORED, s1=s1, s2=s2)


def _dec(value: Fraction | None) -> Decimal | None:
    return None if value is None else _to_decimal(value)


def second_round_credit(
    kind: str, score: Score | Fraction, carried: Score | Fraction = 0, *, grade: int
) -> tuple[bool, Decimal]:
    """(نجح؟، الدرجةُ المحتسبة) لمادّةٍ في الدور الثاني — م16 (12: م12).

    `kind` حالةُ المادّة المخزَّنة: `second_round` (راسب) و`deprived` (محروم) ينالان
    النهايةَ الصغرى وحدَها عند النجاح (م16-1، م16-3)، و`excused` درجتَه مع ما يُحمل له
    (م16-2 «كما تحسب له الدرجة الكلية للمادة وفقاً لما تنص عليه هذه السياسة»: م25/م26).
    والثاني عشر لا يُحمل له شيء (م13-ت، م16). والمجموعُ لا يتجاوز مئة.

    وقواعدُ الترفيع بعد الدور الثاني (م50، ومنها الثالثة) عابرةٌ للموادّ، فهي في
    `judge_student` لا هنا.

    >>> second_round_credit("second_round", 83, grade=10), second_round_credit("excused", 83, grade=12)
    ((True, Decimal('50')), (True, Decimal('83')))
    """
    if kind not in SITTING_STATUSES:
        raise ValueError(f"حالةٌ لا تدخل الدور الثاني: {kind}")
    score_x, carried_x = _exact(score), _exact(carried)
    if score_x < 0 or carried_x < 0:
        raise ValueError("درجةٌ سالبة")
    if kind == STATUS_EXCUSED and grade == FINAL_GRADE and carried_x:
        raise ValueError("الثاني عشر: المعذورُ يُختبر في منهاج الفصلين ولا يُحمل له شيء (م13، م16)")
    raw = score_x + (carried_x if kind == STATUS_EXCUSED else 0)
    if raw > 100 or score_x > 100:
        raise ValueError(f"درجةٌ فوق النهاية العظمى: {float(raw)}")
    value = _jabr_exact(raw)
    if value < _PASS:
        return False, _to_decimal(value)
    return True, (_to_decimal(value) if kind == STATUS_EXCUSED else PASS_MARK)


def _promotion_rule(gaps: list[Fraction]) -> str:
    """القاعدةُ الأولى أو الثانية (م50) لنقصٍ عن النهاية الصغرى — أو "".

    قراءتان تُعلَنان: الأولى لراسبٍ في مادّةٍ واحدة (الثانيةُ تسمّي «مادتين» والثالثةُ
    «مادة وحيدة»، والتدرّجُ 2 ثمّ 4)، و«أربع درجات» حدٌّ أعلى.
    """
    if len(gaps) == 1 and gaps[0] <= PROMOTION_RULE_1_GAP:
        return "م50 القاعدة الأولى"
    if len(gaps) == 2 and all(g <= PROMOTION_RULE_2_GAP for g in gaps):
        return "م50 القاعدة الثانية"
    return ""


def judge_student(
    grade: int,
    subjects: list[SubjectFacts] | tuple[SubjectFacts, ...],
    deprived_gates: frozenset[str] = frozenset(),
    cancelled: bool = False,
) -> StudentVerdict:
    """الحكمُ الواحد: حالةُ كلّ مادّةٍ ومجموعُها وموضعُها، وموقفُ الطالب — دالّةٌ خالصة.

    المدخلاتُ وقائع: درجاتُ الباقات وغيابُها بعذرٍ وبغيره، والملحق، وقراراتُ الحرمان
    المسجَّلة (`deprived_gates`)، وما رُصد في الدور الثاني. والقواعدُ العابرةُ للموادّ
    (م13، م15، م23، م29، م50، م51) تُطبَّق هنا مرّةً — فلا يحكم مستهلكٌ بحكمٍ موازٍ.

    الترتيبُ نصّيّ: «ملغي» (م45 مكرر)؛ ثمّ حرمانُ الثاني عشر من نهاية الأول (م19-1، قبل
    أن يُمتحن الأول فلا يُعدّ غيابُه فيه «غائباً»)؛ ثمّ م23 (12: م15) لأنّ حكمَ الفصل
    الأول يسبق عتبةَ الدور الأول؛ ثمّ الحرمانُ من الدور الأول (م29-4، 12: م19-2)؛ ثمّ م13
    وم12-أ؛ ثمّ ما لم يكتمل؛ ثمّ الترفيعُ بالأوليين (م50) ثمّ الدورُ الثاني.
    """
    g12 = grade == FINAL_GRADE
    gates = frozenset(deprived_gates)
    if not subjects:
        return StudentVerdict(STANDING_INCOMPLETE, "", ())
    facts = {f.key: f for f in subjects}
    r1 = {f.key: (_round1_final_grade(f) if g12 else _round1_standard(f, gates)) for f in subjects}

    absent_s1 = [k for k, r in r1.items() if r.state == _ABSENT_S1]
    absent_final = [k for k, r in r1.items() if r.state == _ABSENT_FINAL]
    complete = {
        k for k, r in r1.items() if r.state == _SCORED and r.s1 is not None and r.s2 is not None
    }
    low = [k for k in r1 if k in complete and (r1[k].total or 0) < _PASS]
    excused = [k for k, r in r1.items() if r.state == _EXCUSED]
    pending = [
        k for k, r in r1.items() if r.state == _MAKEUP or (r.state == _SCORED and k not in complete)
    ]
    failed = absent_s1 + absent_final + low

    def verdict(
        k: str,
        status: str,
        article: str = "",
        mark: str = "",
        numeric: bool = True,
        retake_max: Fraction | None = None,
    ) -> SubjectVerdict:
        r = r1[k]
        sitting = status in SITTING_STATUSES
        return SubjectVerdict(
            key=k,
            status=status,
            s1_total=_dec(r.s1),
            s2_total=_dec(r.s2),
            annual_total=_dec(r.total) if numeric else None,
            mark=mark,
            article=article or r.article,
            second_round_max=_dec(retake_max if retake_max is not None else r.retake_max)
            if sitting
            else None,
        )

    def own(k: str) -> SubjectVerdict:
        """حالةُ المادّة بما وقع فيها وحدَها — لطالبٍ حُسم موقفُه بغيرها."""
        r = r1[k]
        if r.state in (_ABSENT_S1, _ABSENT_FINAL):
            return verdict(k, STATUS_FAIL, mark=ABSENT, numeric=False)
        if r.state == _EXCUSED:
            return replace(
                verdict(k, STATUS_EXCUSED, mark=EXCUSED_MARK, numeric=False), second_round_max=None
            )
        if r.state == _MAKEUP:
            return verdict(k, STATUS_MAKEUP, numeric=False)
        if k not in complete:
            return verdict(k, STATUS_INCOMPLETE)
        return verdict(k, STATUS_FAIL if k in low else STATUS_PASS)

    def all_deprived(article: str) -> StudentVerdict:
        # م16-3 وم29-4 (12: م19): «محروم» في كلّ الموادّ، ويُختبر فيها من مئة.
        subs = tuple(
            verdict(
                k,
                STATUS_DEPRIVED,
                article,
                mark=DEPRIVED_MARK,
                numeric=False,
                retake_max=Fraction(100),
            )
            for k in r1
        )
        return _second_round(grade, StudentVerdict(STANDING_SECOND_ROUND, article, subs), facts, r1)

    if cancelled:
        art = _art("cancelled", grade)
        return StudentVerdict(STANDING_FAILED, art, tuple(replace(own(k), article=art) for k in r1))
    if g12 and GATE_S1_FINAL in gates:
        return all_deprived(FINAL_GRADE_S1_DEPRIVED_ARTICLE)
    if len(absent_s1) > MAX_FAILED_FOR_SECOND_ROUND:
        return StudentVerdict(STANDING_FAILED, _art("barred_s1", grade), tuple(own(k) for k in r1))
    if GATE_S2_FINAL in gates:
        return all_deprived(_art("deprived_first_round", grade))
    if len(absent_final) > MAX_FAILED_FOR_SECOND_ROUND:
        return StudentVerdict(STANDING_FAILED, _art("barred", grade), tuple(own(k) for k in r1))
    if len(failed) > MAX_FAILED_FOR_SECOND_ROUND:
        return StudentVerdict(
            STANDING_FAILED, _art("eligible", grade, "-أ"), tuple(own(k) for k in r1)
        )
    if pending:
        return StudentVerdict(STANDING_INCOMPLETE, "", tuple(own(k) for k in r1))

    if not g12 and not excused and low and len(low) == len(failed):
        rule = _promotion_rule([_PASS - (r1[k].total or 0) for k in low])
        if rule:
            subs = tuple(
                verdict(k, STATUS_PROMOTED, rule) if k in low else verdict(k, STATUS_PASS)
                for k in r1
            )
            return StudentVerdict(STANDING_PROMOTED, rule, subs)

    if not failed and not excused:
        return StudentVerdict(
            STANDING_PASSED, _art("passed", grade), tuple(verdict(k, STATUS_PASS) for k in r1)
        )

    suffix = "-ج" if failed and excused else ("-ب" if excused else "-أ")
    art = _art("eligible", grade, suffix)
    subs_list = []
    for k in r1:
        if k in excused:
            subs_list.append(verdict(k, STATUS_EXCUSED, mark=EXCUSED_MARK, numeric=False))
        elif k in absent_s1 or k in absent_final:
            subs_list.append(verdict(k, STATUS_SECOND_ROUND, mark=ABSENT, numeric=False))
        elif k in low:
            subs_list.append(verdict(k, STATUS_SECOND_ROUND, art))
        else:
            subs_list.append(verdict(k, STATUS_PASS))
    first = StudentVerdict(STANDING_SECOND_ROUND, art, tuple(subs_list))
    return _second_round(grade, first, facts, r1)


def _second_round(
    grade: int,
    first: StudentVerdict,
    facts: Mapping[str, SubjectFacts],
    r1: Mapping[str, _Round1],
) -> StudentVerdict:
    """الدورُ الثاني بما رُصد فيه — م15، م16، ثمّ م50 (والثالثةُ هنا وحدَها) وم51."""
    sitting = [v for v in first.subjects if v.status in SITTING_STATUSES]
    rounds = {v.key: facts[v.key].second_round for v in sitting}
    if not any(sr is not None and (sr.absent or sr.score is not None) for sr in rounds.values()):
        return first
    any_absent = any(sr is not None and sr.absent for sr in rounds.values())
    absent_art = _art("second_round_absent", grade)
    decided: dict[str, SubjectVerdict] = {}
    values: dict[str, Fraction] = {}
    failed: list[str] = []
    undecided = False
    for v in sitting:
        sr = rounds[v.key]
        if sr is None or sr.absent or sr.score is None:
            if (sr is not None and sr.absent) or any_absent:
                # م15: من غاب عن مادّةٍ في الدور الثاني لا يستمرّ في باقيها.
                decided[v.key] = replace(
                    v, status=STATUS_FAIL, annual_total=None, mark=ABSENT, article=absent_art
                )
                failed.append(v.key)
            else:
                undecided = True
            continue
        carried = r1[v.key].carried if v.status == STATUS_EXCUSED else Fraction(0)
        if v.status == STATUS_DEPRIVED:
            carried = Fraction(0)
        passed, value = second_round_credit(v.status, sr.score, carried, grade=grade)
        values[v.key] = _jabr_exact(sr.score + carried)
        decided[v.key] = replace(
            v,
            status=STATUS_PASS if passed else STATUS_FAIL,
            annual_total=value,
            mark="",
            article=_art("credit", grade),
        )
        if not passed:
            failed.append(v.key)

    subs_map = {v.key: decided.get(v.key, v) for v in first.subjects}
    if undecided:
        return StudentVerdict(first.standing, first.article, tuple(subs_map.values()))

    if failed and grade != FINAL_GRADE and all(k in values for k in failed):
        rule = _promotion_rule([_PASS - values[k] for k in failed])
        if not rule and len(failed) == 1:
            k = failed[0]
            others = [subs_map[o].annual_total for o in subs_map if o != k]
            if (
                values[k] >= PROMOTION_RULE_3_FAILED
                and others
                and all(t is not None and t >= PROMOTION_RULE_3_OTHERS for t in others)
            ):
                rule = "م50 القاعدة الثالثة"
        if rule:
            # «يرصد في كشوف الدرجات والشهادة الدرجة التي حصل عليها» — تبقى درجتُه.
            for k in failed:
                subs_map[k] = replace(subs_map[k], status=STATUS_PROMOTED, article=rule)
            return StudentVerdict(STANDING_PROMOTED, rule, tuple(subs_map.values()))
    if failed:
        return StudentVerdict(STANDING_FAILED, first.article, tuple(subs_map.values()))
    return StudentVerdict(STANDING_PASSED, _art("credit", grade), tuple(subs_map.values()))

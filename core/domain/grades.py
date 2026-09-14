"""شرائحُ الدرجات من مئة — جدولٌ واحد.

كان توزيعُ الدرجات على الشرائح (90–100، 80–89 …) سلسلةَ `if` في ثلاثة مواضع:
واجهةُ الرسم البيانيّ، وتقريرُ التقييمات، وستّةُ استعلامات `COUNT` في خدمة
التحليلات. والدرجةُ الحرفيّة (A+ … F) سلسلةً رابعةً بعتباتٍ أخرى — فهي
هنا جدولٌ ثانٍ لا يُخلط بالأوّل: العتباتُ تختلف (95 · 85 · 75 · 65) وكذلك
المعنى.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

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


# ─────────────────────────────────────────────────────────────
# جبرُ الكسور — المادّة 8
# ─────────────────────────────────────────────────────────────


def jabr_fraction(value: Score | None) -> Decimal | None:
    """جبرُ كسور الدرجة إلى أقرب نصفٍ **صعوداً** — لا تقريبٌ إلى أقرب عدد.

    سياسة تقييم الطلبة للصفوف 4–11 (أغسطس 2015)، المادّة 8، صفحة 9 — نصُّها:
        «عند حساب درجات أية مادة من المواد الدراسية في منتصف الفصل أو نهايته
         أو الدور الثاني تطبق الأحكام الآتية لجبر الكسور:
         1- يجبر ما دون النصف إلى النصف.  2- يثبت النصف.
         3- يجبر ما زاد على النصف إلى واحد صحيح.»
    وسياسة الثاني عشر، المادّة 7 (صفحة 5)، بالنصّ نفسه.

    فالكسرُ لا يُنزَّل أبداً: 47.2 ← 47.5، و47.5 تثبت، و47.6 ← 48.
    (كان استخراجُ `04_academic.md` قد لخّصها «أقل من نصف تُجبر لأسفل» — وهو
    خلافُ النصّ المصوَّر؛ صُحِّح في الاستخراج 2026-09-14.)

    >>> [str(jabr_fraction(v)) for v in ("47", "47.01", "47.5", "47.51", "49.99")]
    ['47', '47.5', '47.5', '48', '50']
    """
    if value is None:
        return None
    halves = (Decimal(str(value)) * 2).to_integral_value(rounding=ROUND_CEILING)
    result = halves / 2
    return result.quantize(Decimal("1")) if halves % 2 == 0 else result.quantize(Decimal("0.1"))

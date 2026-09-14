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
    وسياسة الثاني عشر، المادّة 7 (صفحة 5)، بالنصّ نفسه. والاستخراج:
    `04_academic.md:28` و`:172`.

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


# ─────────────────────────────────────────────────────────────
# الدورُ الثاني — من يدخله، وبأيّ صنف، وكيف تُحسب درجتُه
# ─────────────────────────────────────────────────────────────
#
# سياسةُ تقييم الطلبة للصفوف 4–11 (أغسطس 2015)، الفصل الثاني «اختبار الدور
# الثاني»، صفحة 18 — والصفُّ الثاني عشر بالنصّ نفسه في سياسته، صفحتا 7–8:
#
#   م12 (12: م8) «يسمح بدخول اختبار الدور الثاني للفئات الآتية:
#       أ- الطلبة الراسبون في ثلاث مواد دراسية أو أقل.
#       ب- الطلبة المتغيبون في مواد الغياب عن تأدية اختبارات نهاية الفصل
#          الدراسي الأول أو الثاني بعذر مقبول.
#       ج- الطلبة الذين يجمعون بين الرسوب والغياب بعذر مقبول من الفئتين
#          السابقتين (أ، ب) يختبرون فيما رسبوا فيه وفيما تغيبوا عنه.»
#   م13 (12: م9) «لا يسمح بدخول اختبار الدور الثاني للطلبة المتغيبين (بدون
#       عذر) عن اختبارات نهاية الفصل الدراسي الثاني في أكثر من ثلاث مواد.»
#   م16 (12: م12) «تحسب درجة الطالب الناجح في الدور الثاني على النحو التالي:
#       1. الراسب في الدور الأول … النهاية الصغرى للمادة فقط.
#       2. (المعذور) … الدرجة التي يحصل عليها في الدور الثاني.
#       3. (المحروم) من التقدم لاختبار الدور الأول بسبب الغياب عن أيام
#          التمدرس … النهاية الصغرى للمادة فقط.»
#   م29 الجدول، الصفّ الأخير (12: م19): المحرومُ من الدور الأول بالغياب يُسمح
#       له بالدور الثاني «بواقع 100% من النهاية العظمى لكل مادة».
#
#   م22–23 (12: م14–15) «الطالب المتغيب بدون عذر (في الفصل الدراسي الأول
#       بكامله) عن أكثر من ثلاث مواد دراسية لا يسمح له بحضور اختبارات الفصل
#       الدراسي الثاني والدور الثاني، ويكون راسباً وباقياً للإعادة في صفه.»
#       — وما دون ذلك «تحسب ضمن مواد الرسوب». (سياسة 4–11 ص21، والثاني عشر ص10)
#   م25–26: المعذورُ عن نهاية الفصل الثاني وحده يُختبر في منهاج الفصل الثاني
#       «وتجمع درجات هذا الاختبار مع درجات … منتصف الفصل الثاني وأعمال الفصل
#       الثاني وتضاف إلى درجات الطالب في الفصل الدراسي الأول» (ص22).
#   م27: الغائبُ بلا عذر عن نهاية الفصل الثاني «تحسب المادة ضمن مواد الرسوب».
#   «ملغي» — م45 مكرر (قرار 30/2018): «ولا يحق له دخول اختبارات الدور الثاني»
#       (الدليل التعريفي ص29–30، `04b_academic_deep_part1.md:1975`).
#
# ومواضعُها في الاستخراج: `04_academic.md:48-52` (م12–16)، `:65` (م29)،
# `:143-145` (م45 مكرر / 33 مكرر)، `:175-179` (الثاني عشر م8–12)؛
# و`04b_academic_deep_part1.md:1884-1898` و`:1908-1910` و`:1925-1929`
# و`:2028-2042` و`:2052-2053`. والحرمانُ بغير الغياب — العذرُ الطبيّ المزوَّر،
# وثلاثُ مخالفات تنمّرٍ حمراء — «يؤدي اختبارات الدور الثاني فقط»:
# `08_conduct_policy_2026.md:173-174`.
#
# لا شرطَ في النصّ على درجةٍ دنيا (40 مثلاً) لدخول الدور الثاني — الشرطُ عددُ
# الموادّ وحده. وعتباتُ أيّام الحرمان نافذةٌ من دليل 2026 في
# `operations.absence_policy` لا من هنا.

PASS_MARK = Decimal("50")
MAX_FAILED_FOR_SECOND_ROUND = 3

PASSED = "passed"
FAILED_ELIGIBLE = "failed_eligible"
FAILED_INELIGIBLE = "failed_ineligible"
EXCUSED = "excused"
DEPRIVED = "deprived"
INCOMPLETE = "incomplete"

SECOND_ROUND_LABELS: dict[str, str] = {
    PASSED: "ناجح",
    FAILED_ELIGIBLE: "راسبٌ مؤهَّلٌ للدور الثاني",
    FAILED_INELIGIBLE: "راسبٌ غيرُ مؤهَّل",
    EXCUSED: "معذور",
    DEPRIVED: "محروم",
    INCOMPLETE: "لم تكتمل الدرجات",
}


@dataclass(frozen=True)
class SubjectOutcome:
    """نتيجةُ مادّةٍ واحدة في الدور الأول، بما يلزم الحكمَ لا أكثر."""

    subject: str
    #: المجموعُ السنويّ من مئة بعد جبر الكسور، و`None` لما لم يُرصد.
    annual_total: Decimal | None
    #: غاب بعذرٍ مقبول عن اختبار نهاية الفصل الأول أو الثاني — م12-ب.
    excused_final_absence: bool = False
    #: غاب بلا عذر عن اختبار نهاية الفصل الثاني — م13، وم27: «ضمن مواد الرسوب».
    unexcused_final_absence: bool = False
    #: غاب بلا عذر عن اختبارات الفصل الأول بكاملها — م22 (12: م14)، وعدُّها م23 (12: م15).
    unexcused_first_semester_absence: bool = False


@dataclass(frozen=True)
class FirstRoundDecision:
    category: str
    #: الموادُّ التي يختبرها في الدور الثاني (م12-ج: فيما رسب وفيما تغيّب).
    retake: tuple[str, ...]
    failed: tuple[str, ...]
    excused: tuple[str, ...]
    #: الموضعُ الذي قضى بالصنف — «م12-أ» للصفوف 4–11، «م8-أ» للثاني عشر.
    article: str

    @property
    def label(self) -> str:
        return SECOND_ROUND_LABELS[self.category]

    @property
    def sits_second_round(self) -> bool:
        return self.category in (FAILED_ELIGIBLE, EXCUSED, DEPRIVED)

    def kind_of(self, subject: str) -> str:
        """صنفُ المادّة لحساب درجتها (م16): المعذورُ فيها، أو المحروم، أو الراسب."""
        if subject in self.excused:
            return EXCUSED
        return DEPRIVED if self.category == DEPRIVED else FAILED_ELIGIBLE


#: أرقامُ الموادّ بين السياستين: (4–11، الثاني عشر).
_ARTICLES = {
    "eligible": ("م12", "م8"),
    "barred": ("م13", "م9"),
    "barred_s1": ("م23", "م15"),
    "deprived": ("م29", "م19"),
    "cancelled": ("م45 مكرر", "م33 مكرر"),
}


def _art(key: str, grade: int, suffix: str = "") -> str:
    return _ARTICLES[key][grade == FINAL_GRADE] + suffix


def classify_first_round(
    outcomes: list[SubjectOutcome] | tuple[SubjectOutcome, ...],
    grade: int,
    deprived: bool = False,
    cancelled: bool = False,
) -> FirstRoundDecision:
    """صنفُ الطالب بعد الدور الأول — ناجح/راسبٌ مؤهَّل/غيرُ مؤهَّل/معذور/محروم.

    >>> o = [SubjectOutcome("ع", Decimal("49")), SubjectOutcome("ر", Decimal("80"))]
    >>> classify_first_round(o, 10).category, classify_first_round(o, 10).article
    ('failed_eligible', 'م12-أ')
    """
    names = tuple(o.subject for o in outcomes)
    excused = tuple(o.subject for o in outcomes if o.excused_final_absence)
    failed = tuple(
        o.subject
        for o in outcomes
        if not o.excused_final_absence
        and (
            o.unexcused_final_absence
            or o.unexcused_first_semester_absence
            or (o.annual_total is not None and o.annual_total < PASS_MARK)
        )
    )
    missing = [
        o
        for o in outcomes
        if o.annual_total is None
        and not (
            o.excused_final_absence
            or o.unexcused_final_absence
            or o.unexcused_first_semester_absence
        )
    ]
    unexcused = sum(1 for o in outcomes if o.unexcused_final_absence)
    unexcused_s1 = sum(1 for o in outcomes if o.unexcused_first_semester_absence)

    def decide(category: str, retake: tuple[str, ...], article: str) -> FirstRoundDecision:
        return FirstRoundDecision(category, retake, failed, excused, article)

    if cancelled:
        return decide(FAILED_INELIGIBLE, (), _art("cancelled", grade))
    if deprived:
        return decide(DEPRIVED, names, _art("deprived", grade))
    if unexcused_s1 > MAX_FAILED_FOR_SECOND_ROUND:
        return decide(FAILED_INELIGIBLE, (), _art("barred_s1", grade))
    if unexcused > MAX_FAILED_FOR_SECOND_ROUND:
        return decide(FAILED_INELIGIBLE, (), _art("barred", grade))
    if len(failed) > MAX_FAILED_FOR_SECOND_ROUND:
        return decide(FAILED_INELIGIBLE, (), _art("eligible", grade, "-أ"))
    if missing:
        return decide(INCOMPLETE, (), "")
    if excused:
        suffix = "-ج" if failed else "-ب"
        return decide(EXCUSED, failed + excused, _art("eligible", grade, suffix))
    if failed:
        return decide(FAILED_ELIGIBLE, failed, _art("eligible", grade, "-أ"))
    return decide(PASSED, (), "م10–11" if grade != FINAL_GRADE else "م6")


def second_round_credit(kind: str, score: Score, carried: Score = 0) -> tuple[bool, Decimal]:
    """(نجح؟، الدرجةُ المحتسبة) لمادّةٍ في الدور الثاني — م16 (12: م12).

    `kind` صنفُ المادّة لا الطالب (`FirstRoundDecision.kind_of`): فالجامعُ بين
    الرسوب والعذر (م12-ج) ينال الصغرى فيما رسب فيه، ودرجتَه فيما عُذر عنه.

    الراسبُ والمحرومُ يُختبران من مئة (م14 / 12: م10) وينالان النهايةَ الصغرى
    وحدَها عند النجاح. والمعذورُ درجتَه الفعليّة «كما تحسب له الدرجة الكلية للمادة
    وفقاً لما تنص عليه هذه السياسة» (م16-2): فمن عُذر عن نهاية الفصل الثاني وحدَه
    تُجمع درجةُ اختباره مع ما حصّله قبلها (`carried`: الفصلُ الأول ومنتصفُ الثاني
    وأعمالُه — م25، وم26 للفصل الثاني كلِّه)، ومن عُذر عن الفصلين يُختبر من مئة
    و`carried` صفر (م21، والثاني عشر م16: «ولا تحسب له درجات الفصل الأول»).
    ومن لم يبلغ الصغرى تُحتسب له درجتُه كما هي ويبقى راسباً.

    >>> second_round_credit(FAILED_ELIGIBLE, 83), second_round_credit(EXCUSED, 83)
    ((True, Decimal('50')), (True, Decimal('83')))
    """
    if kind not in (FAILED_ELIGIBLE, EXCUSED, DEPRIVED):
        raise ValueError(f"صنفٌ لا يدخل الدور الثاني: {kind}")
    raw = Decimal(str(score)) + (Decimal(str(carried)) if kind == EXCUSED else 0)
    value = jabr_fraction(raw)
    assert value is not None
    if value < PASS_MARK:
        return False, value
    return True, (value if kind == EXCUSED else PASS_MARK)

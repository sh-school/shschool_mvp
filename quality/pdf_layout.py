"""[PROVISIONAL] سعةُ منطقة النصوص الحرّة في PDF استمارة الزيارة الصفّيّة — نموذجٌ أوّليٌّ محلّيّ.

قرّر المالكُ (2026-09-26): لا قصَّ للنصّ الحرّ في المطبوع؛ المتنُ 12pt والنصوصُ الحرّة 11pt تتدرّج بنصف نقطةٍ إلى حدٍّ أدنى، وعدّادٌ حيٌّ
للأحرف المتبقّية يمنع حفظَ ما يزيد عن سعة الصفحة. والمحرّكُ المركزيّ (مواصفةُ «مسار الواجهة والهويّة») سيُعرّف دالّةَ `capacity` النقيّة؛
وهذا الملفُّ **نموذجٌ أوّليٌّ يُقاس عليه** إلى أن تحلّ محلَّه: **لا يُنسخ رقمٌ منه إلى قالبٍ أو JS**، والقالبُ يقرأ حجمَ الخطّ الناتجَ وحدَه.

النموذجُ تقديريٌّ (أحرفٌ ← أسطر) ومحافظ: يُقدّر الأسطرَ بما لا يقلّ عن الحقيقيّ — فما يسعه النموذجُ يسعه التخطيطُ الفعليّ (يحرسه
`tests/test_observation_pdf_a4.py` على PDF حقيقيّ). وثوابتُه مقيسةٌ من تخطيط WeasyPrint بخطّ الإنتاج:

    متنُ الصفحة   = 841.9 (A4) − 86.4 (الترويسة 1.2 بوصة بلا رؤية) − 30.2 (تذييلٌ بسطرٍ واحد: المدرسةُ والوزارةُ والرؤيةُ معاً، 0.42 بوصة) = 725.3pt
    الجسمُ الفارغ = العنوانُ + جدولُ المعلومات + المعايير الـ23 (12pt) + منطقةُ النصوص (ملاحظاتٌ فارغة بأدنى ارتفاع) + التوقيعات
"""

from math import ceil, floor

#: حجمُ خطّ النصوص الحرّة المثاليّ، وحدُّه الأدنى (قرارُ المالك: 9.5 صغيرٌ جدّاً)، وخطوةُ التدرّج (pt)
IDEAL_PT = 11.0
MIN_PT = 10.0
STEP_PT = 0.5

#: ارتفاعُ السطر في المنطقة (مضروباً في الخطّ)
LINE_HEIGHT = 1.2
#: متوسّطُ عرض الحرف العربيّ بالنسبة إلى الخطّ (em) في Noto Naskh — تقديرٌ **محافظ** (أكبرُ من المقيس) فيُقدَّر الأسطرُ بالزيادة
AVG_CHAR_EM = 0.42
#: عرضُ سطر النصّ في المنطقة (pt): 184.6مم − حشوا الصندوق 2×3.5 − حدّاه
TEXT_WIDTH_PT = 514.0

#: متنُ الصفحة (pt) — انظر أعلاه
BODY_PT = 725.3
#: ارتفاعُ الجسم الفارغ (pt): كلُّ شيءٍ (المعايير الـ23 كلُّها مقدَّرةٌ، والختمان) والمنطقةُ فيها عنوانُ الملاحظات وصندوقُها بأدنى ارتفاعٍ 38pt
BLANK_BODY_PT = 580.2
#: ارتفاعُ صندوق المنطقة الفارغ (pt) بحدّيه — أساسُ `zone_min_pt`
ZONE_BLANK_PT = 52.5
#: فسحةُ أمانٍ تحت كلّ شيء (pt): تشكيلُ الخطّ يختلف يسيراً بين البيئات، وموضوعُ الزيارة (حتّى 200 حرف) قد يلفّ سطراً في جدول المعلومات
SAFETY_PT = 24.0

#: عنوانُ «توصيات المعايير» وحشوُ قائمته (pt)
RECS_HEADING_PT = 14.0
RECS_PAD_PT = 4.0
#: أدنى ارتفاعٍ لصندوق الملاحظات (pt) وحشوُه — ما دونه لا يزيد الجسمَ
NOTES_MIN_PT = 38.0
NOTES_PAD_PT = 4.0


def chars_per_line(pt: float) -> int:
    return max(1, floor(TEXT_WIDTH_PT / (AVG_CHAR_EM * pt)))


def lines_for(text: str, pt: float) -> int:
    """أسطرُ فقرةٍ أو أكثر (كلُّ سطرٍ جديدٍ فقرة): لا أقلّ من سطر."""
    cpl = chars_per_line(pt)
    return sum(
        max(1, ceil(len(paragraph) / cpl)) for paragraph in (text or "").splitlines() or [""]
    )


def extra_height(recs, notes: str, pt: float) -> float:
    """ما تزيده النصوصُ الحرّةُ على الجسم الفارغ (pt) عند خطٍّ `pt`."""
    line = pt * LINE_HEIGHT
    extra = 0.0
    if recs:
        rec_lines = sum(lines_for(f"0000 {rec['text']}", pt) for rec in recs)
        extra += RECS_HEADING_PT + RECS_PAD_PT + rec_lines * line
    extra += max(0.0, lines_for(notes, pt) * line + NOTES_PAD_PT - NOTES_MIN_PT)
    return extra


def budget() -> float:
    """ما يتّسع للنصوص الحرّة فوق الجسم الفارغ (pt)."""
    return BODY_PT - BLANK_BODY_PT - SAFETY_PT


def zone_min_pt() -> float:
    """أدنى ارتفاعٍ لصندوق المنطقة (pt): يملأ الصفحةَ إلى فسحة الأمان — الاستمارةُ الفارغةُ والعاديّةُ كلُّها بارتفاعٍ واحد، والنصُّ الزائدُ يمدّه."""
    return ZONE_BLANK_PT + budget()


def font_steps():
    pt = IDEAL_PT
    while pt >= MIN_PT:
        yield pt
        pt -= STEP_PT


def free_font(recs, notes: str) -> float:
    """أكبرُ خطٍّ (من 11pt إلى الحدّ الأدنى بنصف نقطة) تسعه الصفحةُ؛ فإن لم يسعها فالحدُّ الأدنى ويفيض النصُّ إلى صفحةٍ ثانية."""
    for pt in font_steps():
        if extra_height(recs, notes, pt) <= budget():
            return pt
    return MIN_PT


def fits(recs, notes: str) -> bool:
    return extra_height(recs, notes, MIN_PT) <= budget()


def recs_block_height(recs, pt: float) -> float:
    """ارتفاعُ قائمة التوصيات (عنوانُها وحشوُها وأسطرُها) عند خطٍّ `pt` — صفرٌ إن لم تكن توصيات."""
    if not recs:
        return 0.0
    line = pt * LINE_HEIGHT
    rec_lines = sum(lines_for(f"0000 {rec['text']}", pt) for rec in recs)
    return RECS_HEADING_PT + RECS_PAD_PT + rec_lines * line


def remaining_chars(recs, notes: str) -> int:
    """الأحرفُ المتبقّية للملاحظات عند الحدّ الأدنى للخطّ — ما يقرؤه العدّادُ الحيّ (سالبٌ = يزيد عن السعة). بدقّة سطرٍ كاملٍ.

    الأسطرُ المسموحةُ للملاحظات = ما يفضل بعد قائمة التوصيات (فوق صندوقها الأدنى) ÷ ارتفاع السطر؛ فيتّسق الإشارةُ مع `fits`.
    """
    line = MIN_PT * LINE_HEIGHT
    cpl = chars_per_line(MIN_PT)
    room = budget() - recs_block_height(recs, MIN_PT)
    if room < 0:
        return -ceil(-room / line) * cpl
    allowed = floor((room + NOTES_MIN_PT - NOTES_PAD_PT) / line)
    return (allowed - lines_for(notes, MIN_PT)) * cpl


def format_pt(pt: float) -> str:
    """`11` أو `10.5` — نصٌّ لا عددٌ فلا تُحلّ الفاصلةُ العشريّةُ بحسب اللغة في القالب."""
    return f"{pt:g}"

"""الإطارُ المطبوعُ المركزيّ — ثوابتُ الترويسة والتذييل والهوامش لكلّ (ورق، اتّجاه) في موضعٍ واحد.

المواصفة: `docs/design/print_fit_spec.md` §٥ (قراراتُ المالك 2026-09-26): **ترويسةٌ كاملةٌ ≈30 ملم**، وتذييلٌ **صفٌّ واحدٌ ثابتُ الارتفاع**
(8 ملم)، وهوامشُ علويّةٌ وسفليّةٌ 6 ملم حول الإطار. وكان لكلّ قالبٍ ترويستُه وتذييلُه بأرقامه (خمسُ نسخٍ متباينةٍ: `core/pdf_utils.py`
و`reports/base_qatar_report.html` و`schedule/print_pages.html` و`wings/register_pdf.html` ونسخةٌ محلّيّة)، فلا تعرف آليّةُ الملاءمة
ما يتبقّى للمتن. فهنا الثوابتُ التي **تطرحها الملاءمةُ من ارتفاع الصفحة بلا تخمين**، ويقرؤها `PaperGeometry` وقوالبُ PDF.

دوالُّ **نقيّةٌ** بلا request ولا قاعدة ولا ألوان (الألوانُ في `templates/components/print/frame_css.html` من `brand_color`):

    frame("a4", "portrait")  ← Frame: header_h، footer_h، body_height، الهوامش، وتوليدُ CSS الصفحة
    footer_plan(frame, …)    ← أيُّ عناصر التذييل يسعها الصفُّ الواحد بحسب الأولويّات (الفقرة ٥-٢ من المواصفة)

والحارسُ النصّيّ `tests/print_frame_ratchet.py` يمنع `running(` و`@bottom-` وأصنافَ التذييل **خارجَ هذا المكوّن**.
"""

from __future__ import annotations

from dataclasses import dataclass

#: (عرض، ارتفاع) بالملّيمتر لكلّ (ورق، اتّجاه).
SHEETS_MM: dict[tuple[str, str], tuple[float, float]] = {
    ("a4", "portrait"): (210.0, 297.0),
    ("a4", "landscape"): (297.0, 210.0),
    ("a3", "portrait"): (297.0, 420.0),
    ("a3", "landscape"): (420.0, 297.0),
}

PAPERS = ("a4", "a3")
ORIENTATIONS = ("portrait", "landscape")

#: الترويسةُ كاملةٌ ≈30 ملم (شعارٌ 11 ملم + وزارةٌ + مدرسةٌ + عنوانٌ + سطرُ السنة). وعلى العموديّ +5 ملم لسطر الرؤية (القرار D1):
#: التذييلُ العموديُّ بخطّ 10pt لا يسع الرؤيةَ مع الملزِم (56.6em > 53.9em)، فتنتقل إلى سطرٍ في الترويسة.
HEADER_H_MM: dict[tuple[str, str], float] = {
    ("a4", "portrait"): 35.0,
    ("a4", "landscape"): 30.0,
    ("a3", "portrait"): 35.0,
    ("a3", "landscape"): 30.0,
}
#: الرؤيةُ في سطرٍ من الترويسة لا في التذييل (D1) — حيث لا يسعها التذييلُ صفّاً واحداً.
VISION_IN_HEADER = frozenset({("a4", "portrait"), ("a3", "portrait")})

FOOTER_H_MM = 8.0  # صفٌّ واحدٌ ثابتُ الارتفاع
MARGIN_TOP_MM = 6.0
MARGIN_BOTTOM_MM = 6.0
MARGIN_SIDE_MM = 9.0  # ≥ 8: الطابعاتُ تترك حيّزاً غيرَ قابلٍ للطباعة 3–6 ملم (المواصفة ٤-٢)
GAP_MM = 2.0  # فاصلُ ما بين الإطار والمتن

#: حدُّ الخطّ الأدنى للتذييل (المواصفة ٤-١): المثاليّ 10pt والأدنى الصارم 9pt.
FOOTER_PT = 10.0
FOOTER_MIN_PT = 9.0
#: حيّزٌ يُترك على كلّ جانبٍ من صفّ التذييل عند حساب سعته (المواصفة ٥-٢).
FOOTER_INSET_MM = 10.0

_PT_MM = 25.4 / 72  # النقطةُ بالملّيمتر


@dataclass(frozen=True)
class Frame:
    paper: str
    orient: str
    page_w: float
    page_h: float
    margin_top: float
    margin_bottom: float
    margin_side: float
    header_h: float
    footer_h: float
    gap: float
    vision_in_header: bool

    @property
    def top_total(self) -> float:
        """من حافّة الورق إلى أوّل المتن: هامشٌ + ترويسةٌ + فاصل."""
        return self.margin_top + self.header_h + self.gap

    @property
    def bottom_total(self) -> float:
        return self.margin_bottom + self.footer_h + self.gap

    @property
    def body_height(self) -> float:
        """ارتفاعُ المتن المتاحُ لكلّ ما ليس إطاراً — ما تقرؤه الملاءمةُ."""
        return round(self.page_h - self.top_total - self.bottom_total, 1)

    @property
    def body_width(self) -> float:
        return round(self.page_w - 2 * self.margin_side, 1)

    def page_css(self) -> str:
        """`@page` بحجم الورق والهوامش ومربّعَي الإطار (الترويسة والتذييل عنصران جاريان `running`). هندسةٌ بلا ألوان."""
        return (
            f"@page {{ size: {self.paper.upper()} {self.orient}; "
            f"margin: {self.top_total:g}mm {self.margin_side:g}mm {self.bottom_total:g}mm {self.margin_side:g}mm; "
            f"@top-center {{ content: element(print-header); vertical-align: top; width: {self.body_width:g}mm; }} "
            f"@bottom-center {{ content: element(print-footer); vertical-align: bottom; width: {self.body_width:g}mm; }} }}"
        )


def frame(paper: str, orient: str) -> Frame:
    """ثوابتُ الإطار لـ(ورق، اتّجاه) — ورقٌ غيرُ معروفٍ يفشل بصوتٍ عالٍ لا بافتراضٍ صامت."""
    key = (paper, orient)
    if key not in SHEETS_MM:
        raise ValueError(
            f"الإطار المطبوع: الورقة {paper!r} باتّجاه {orient!r} غيرُ معروفة — {sorted(SHEETS_MM)}"
        )
    width, height = SHEETS_MM[key]
    return Frame(
        paper=paper,
        orient=orient,
        page_w=width,
        page_h=height,
        margin_top=MARGIN_TOP_MM,
        margin_bottom=MARGIN_BOTTOM_MM,
        margin_side=MARGIN_SIDE_MM,
        header_h=HEADER_H_MM[key],
        footer_h=FOOTER_H_MM,
        gap=GAP_MM,
        vision_in_header=key in VISION_IN_HEADER,
    )


# ── صفُّ التذييل: العناصرُ والأولويّات وما يسعه (المواصفة ٥-٢) ──────────────────────────────

#: بالأولويّة: الثلاثةُ الأولى ملزِمة، والباقي يُدرَج ما وَسِع الصفُّ (اسمُ الوزارة تكرارٌ لما في الترويسة فهو أوّلُ ما يسقط بعد الرؤية).
FOOTER_ITEMS = ("school", "page", "date", "vision", "ministry", "contact", "samm")
FOOTER_MANDATORY = ("school", "page", "date")

_SEPARATOR_EM = 1.5  # « · » بين عنصرين
_DIGIT_EM = 0.55  # رقمٌ أو فاصلُ تاريخٍ/وقت
_LETTER_EM = 0.42  # حرفٌ عربيٌّ (متوسّطُ Tajawal المقيس)


def text_em(text: str) -> float:
    """عرضُ نصٍّ بالإم بمقاييس Tajawal التقريبيّة (الحرفُ 0.42em والرقمُ وعلاماتُه 0.55em) — تقديرٌ محافظٌ للحدّ لا قياسٌ للرسم."""
    return round(sum(_DIGIT_EM if (c.isdigit() or c in "/:.-") else _LETTER_EM for c in text), 2)


@dataclass(frozen=True)
class FooterPlan:
    items: tuple[str, ...]  # العناصرُ المُدرَجة بترتيب الأولويّة
    dropped: tuple[str, ...]
    width_em: float
    capacity_em: float
    font_pt: float

    @property
    def fits(self) -> bool:
        """هل يسع الصفُّ الملزِمَ على الأقلّ؟ (وإلّا فاسمُ المدرسة أطولُ من الحدّ ويلزم قرارٌ لا قصٌّ صامت.)"""
        return self.width_em <= self.capacity_em


def footer_capacity_em(fr: Frame, font_pt: float = FOOTER_PT) -> float:
    """سعةُ الصفّ بالإم: عرضُ الورق ناقصَ حيّزَين على الجانبين."""
    return round((fr.page_w - 2 * FOOTER_INSET_MM) / (font_pt * _PT_MM), 2)


def footer_plan(
    fr: Frame,
    *,
    school: str,
    vision: str,
    ministry: str,
    contact: str = "",
    samm: str = "SchoolOS-SAMM ©",
    date_text: str = "2026/09/26 22:40",
    page_text: str = "10 / 10",
    font_pt: float = FOOTER_PT,
) -> FooterPlan:
    """أيُّ عناصر التذييل يسعها صفٌّ واحدٌ بخطّ `font_pt`؛ الملزِمُ أوّلاً ثمّ بالأولويّة ما يسعه الباقي.

    عنصرٌ لا يسع لا يمنع ما بعده الأقصر (الأولويّةُ ترتيبُ الإدراج لا قطعٌ عند أوّل إخفاق)، والرؤيةُ خارجَ التذييل حيث
    `vision_in_header` (D1). والنصوصُ حقيقيّةٌ تُقاس بالإم فتقصيرُ اسمٍ أو رؤيةٍ يعيد إدراجَ ما سقط.
    """
    texts = {
        "school": school,
        "page": page_text,
        "date": date_text,
        "vision": "" if fr.vision_in_header else vision,
        "ministry": ministry,
        "contact": contact,
        "samm": samm,
    }
    capacity = footer_capacity_em(fr, font_pt)
    chosen: list[str] = []
    dropped: list[str] = []
    width = 0.0
    for key in FOOTER_ITEMS:
        text = texts[key]
        if not text and key not in FOOTER_MANDATORY:
            continue
        extra = text_em(text) + (_SEPARATOR_EM if chosen else 0.0)
        if key in FOOTER_MANDATORY or width + extra <= capacity:
            chosen.append(key)
            width = round(width + extra, 2)
        else:
            dropped.append(key)
    return FooterPlan(tuple(chosen), tuple(dropped), width, capacity, font_pt)

"""ورقةُ الجدول الأسبوعيّ للمعلّم والشعبة: الأعمدةُ والاستراحاتُ والمقاس.

ثلاثةُ قرارات (2026-09-14، بلاغ المستخدم بلقطة ورقة A4 أفقيّة يشغل الجدولُ
نصفَها، وفي كلّ خانةٍ «الصف الحادي عشر / 2 — تكنولوجي (2026-2027)»):

١. **الفسحةُ والصلاةُ في الورقة بتوقيتهما.** وهما محفوظتان أصلاً في
   `TimeSlotConfig` (`is_break`) لكلّ جرسٍ ولكلّ نوعِ يوم — فلا هجرة. لكنّ
   موضعَهما يتبدّل: الأرضيُّ صلاتُه بعد السادسة ويومَ الخميس بعد الخامسة،
   والتاسعُ فسحتُه بعد الرابعة ويومَ الخميس بعد الثالثة. فالعمودُ لا يُثبَّت
   على جرس الأحد: **أعمدةُ الاستراحة اتّحادُ مواضعها في الأسبوع**، وخانةُ
   اليوم الذي لا استراحةَ عنده فارغةٌ مظلّلة — والترتيبُ الزمنيُّ صادقٌ في
   كلّ سطر.
٢. **المعلّمُ في جرسين يرى الجرسين كاملين** مع اسم الجرس، لا جرسَ طابقه
   الغالب ولا حذفَ ما يقع وقتَ حصّةٍ له.
٣. **الجدولُ يملأ الورقة.** مولّدُ PDF (WeasyPrint 70) لا يمدّ جدولاً عنصراً
   مرناً (`flex: 1; height: 1px`) ولا يوزّع ارتفاعَ الجدول على صفوفه، ويحترم
   ارتفاعَ الصفّ بالملّيمتر. فالورقةُ تُحسب هنا بالملّيمتر: أشرطةٌ ثابتةُ
   الارتفاع (الترويسة، سطر المعلّم، رأس الجدول، الذيل)، وما بقي يُقسم على
   الأيّام الخمسة — بهامش أمانٍ لأنّ كسراً من الملّيمتر زائداً يُخرج صفحةً
   ثانية.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from operations.bells import REGULAR, THURSDAY, Bell, bells_for
from operations.models import ScheduleSlot

#: عددُ الحصص في اليوم وعددُ أيّام الدراسة — شكلُ `days` في `ScheduleService`.
PERIODS = 7
DAYS = 5


@dataclass(frozen=True)
class BreakItem:
    """استراحةٌ في خانة: اسمُها ووقتُها، واسمُ جرسها حين يلتبس."""

    label: str
    start: dt.time
    end: dt.time
    band: str = ""


def day_type_of(day_of_week: int) -> str:
    """نوعُ اليوم من رقمه في `ScheduleSlot` (0 الأحد … 4 الخميس)."""
    return THURSDAY if day_of_week == 4 else REGULAR


def bell_tables(school) -> dict[str, dict[str, Bell]]:
    """أجراسُ المدرسة ليومَي الأسبوع — استعلامان للطلب كلِّه لا لكلّ صفحة."""
    return {REGULAR: bells_for(school, REGULAR), THURSDAY: bells_for(school, THURSDAY)}


def breaks_after(bell: Bell) -> list[tuple[int, BreakItem]]:
    """استراحاتُ الجرس ومواضعُها: بعد آخر حصّةٍ تنتهي قبلها بالساعة.

    والموضعُ بالساعة لا بالرقم: الصلاةُ رقمُها 101 ووقتُها قبل السابعة.
    """
    periods = bell.periods
    placed = []
    for slot in bell.slots:
        if not slot.is_break:
            continue
        after = max((p.number for p in periods if p.end <= slot.start), default=0)
        placed.append(
            (
                after,
                BreakItem(label=slot.label, start=slot.start, end=slot.end, band=bell.band_short),
            )
        )
    return placed


def _day_breaks(bands: list[str], table: dict[str, Bell]) -> list[tuple[int, BreakItem]]:
    """استراحاتُ يومٍ من أجراسه: المتطابقُ اسماً ووقتاً يُكتب مرّة، واسمُ الجرس
    يبقى حيث تتكرّر الاستراحةُ نفسُها بوقتين."""
    seen: dict[tuple, tuple[int, BreakItem]] = {}
    for code in [code for code in table if code in bands]:  # بترتيب الأجراس
        for after, item in breaks_after(table[code]):
            seen.setdefault((item.label, item.start, item.end), (after, item))
    items = sorted(seen.values(), key=lambda pair: (pair[1].start, pair[0]))
    labels = [item.label for _, item in items]
    return [
        (
            after,
            item if labels.count(item.label) > 1 else BreakItem(item.label, item.start, item.end),
        )
        for after, item in items
    ]


def week_layout(
    days: list, bands_by_day: list[list[str]], tables: dict[str, dict[str, Bell]]
) -> dict:
    """أعمدةُ الورقة وسطورُها: حصصٌ سبعٌ وبينها أعمدةُ الاستراحات.

    `days`: خمسةُ أيّامٍ في كلٍّ منها سبعُ خانات (قوائمُ حصص) — شكلُ
    `ScheduleService`. و`bands_by_day`: رموزُ الأجراس التي يُقرأ منها كلُّ يوم.

    يُرجع `columns` لرأس الجدول و`lines` سطراً لكلّ يوم، وكلٌّ منهما عناصرُ
    بالترتيب نفسه: `{"kind": "period", "number"}` أو `{"kind": "break", ...}`.
    """
    per_day = [
        _day_breaks(
            bands_by_day[d] if d < len(bands_by_day) else [], tables.get(day_type_of(d), {})
        )
        for d in range(DAYS)
    ]
    positions = sorted({after for breaks in per_day for after, _ in breaks})

    columns: list[dict] = []
    for number in range(0, PERIODS + 1):
        if number:
            columns.append({"kind": "period", "number": number})
        if number in positions:
            names = {item.label for breaks in per_day for after, item in breaks if after == number}
            columns.append(
                {
                    "kind": "break",
                    "after": number,
                    "label": names.pop() if len(names) == 1 else "استراحة",
                }
            )

    names = [name for _num, name in ScheduleSlot.DAYS]
    lines = []
    for d, cells in enumerate(days[:DAYS]):
        entries = []
        for column in columns:
            if column["kind"] == "period":
                entries.append({"kind": "period", "slots": cells[column["number"] - 1]})
            else:
                entries.append(
                    {
                        "kind": "break",
                        "items": [item for after, item in per_day[d] if after == column["after"]],
                    }
                )
        lines.append({"day": names[d], "entries": entries})
    return {"columns": columns, "lines": lines, "break_count": len(positions)}


def grid_to_days(grid: dict) -> list:
    """`{يوم: {حصّة: [حصص]}}` (`get_weekly_schedule`) → خمسةُ أيّامٍ بسبع خانات."""
    return [
        [list((grid.get(d) or {}).get(p, [])) for p in range(1, PERIODS + 1)] for d in range(DAYS)
    ]


def teacher_bands_by_day(days: list, band_codes: dict) -> list[list[str]]:
    """أجراسُ المعلّم في كلّ يوم: أجراسُ شُعب حصصه فيه — ويومٌ بلا حصصٍ بلا جرس."""
    return [
        sorted(
            {
                band_codes[slot.class_group.time_band_id]
                for cell in cells
                for slot in cell
                if slot.class_group.time_band_id in band_codes
            }
        )
        for cells in days[:DAYS]
    ]


# ── المقاس ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PaperGeometry:
    """أبعادُ الورقة بالملّيمتر — مصدرٌ واحدٌ يكتب منه القالبُ هوامشَه وصفوفَه."""

    page_w: float
    page_h: float
    margin_top: float
    margin_side: float
    margin_bottom: float
    header_h: float
    who_h: float
    thead_h: float
    footer_h: float
    gap: float
    safety: float
    rows: int
    font_scale: float
    break_col_w: float
    day_col_w: float

    @property
    def content_w(self) -> float:
        return self.page_w - 2 * self.margin_side

    @property
    def content_h(self) -> float:
        return self.page_h - self.margin_top - self.margin_bottom

    @property
    def bands_h(self) -> float:
        gaps = self.gap * (3 if self.who_h else 2)
        return self.header_h + self.who_h + self.thead_h + self.footer_h + gaps + self.safety

    @property
    def row_h(self) -> float:
        return round((self.content_h - self.bands_h) / self.rows, 1)

    @property
    def cell_h(self) -> float:
        """ارتفاعُ محتوى الخانة: الصفُّ ناقصَ حشوته وحدوده — لا يطيله محتوىً زائد."""
        return round(self.row_h - 2.5, 1)

    @property
    def css(self) -> dict[str, str]:
        """الأرقامُ نصوصاً بوحدتها للقالب.

        نصوصٌ لا أعداد: القالبُ يُترجم العددَ العشريّ بلغة الواجهة، و«25,8mm»
        قاعدةٌ يُسقطها المحرّكُ صامتاً.
        """

        def mm(value: float) -> str:
            return f"{value:.1f}mm"

        def pt(value: float) -> str:
            return f"{value * self.font_scale:.1f}pt"

        return {
            "margin": f"{mm(self.margin_top)} {mm(self.margin_side)} {mm(self.margin_bottom)}",
            "content_w": mm(self.content_w),
            "header_h": mm(self.header_h),
            "who_h": mm(self.who_h),
            "thead_h": mm(self.thead_h),
            "footer_h": mm(self.footer_h),
            "gap": mm(self.gap),
            "row_h": mm(self.row_h),
            "cell_h": mm(self.cell_h),
            "day_col_w": mm(self.day_col_w),
            "break_col_w": mm(self.break_col_w),
            "head_pt": pt(9),
            "day_pt": pt(10),
            "subject_pt": pt(8.5),
            "meta_pt": pt(7.5),
            "time_pt": pt(7),
            "break_pt": pt(7.5),
        }


_SHEETS = {("a4", "landscape"): (297, 210), ("a4", "portrait"): (210, 297)}
_SHEETS[("a3", "landscape")] = (420, 297)
_SHEETS[("a3", "portrait")] = (297, 420)


def paper_geometry(paper: str, orient: str, *, with_who: bool) -> PaperGeometry:
    """مقاسُ ورقة المعلّم أو الشعبة.

    `with_who`: سطرُ «المعلّم · القسم · المنسّق» في ورقة الصفحات، ولا سطرَ له في
    الجدول المطبوع (العنوانُ يحمل الاسم).

    والخطُّ يكبر على A3 بقدرٍ معتدل: الخانةُ تتّسع ضعفَها تقريباً، وخطُّ A4 فيها
    يتيه في بياضها.
    """
    paper = paper if paper in ("a3", "a4") else "a4"
    orient = orient if orient in ("landscape", "portrait") else "landscape"
    page_w, page_h = _SHEETS[(paper, orient)]
    landscape = orient == "landscape"
    return PaperGeometry(
        page_w=page_w,
        page_h=page_h,
        margin_top=8,
        margin_side=9,
        margin_bottom=10,
        header_h=29 if landscape else 32,
        who_h=8 if with_who else 0,
        thead_h=7,
        footer_h=10,
        gap=2,
        safety=4,
        rows=DAYS,
        font_scale=1.5 if paper == "a3" else 1.0,
        break_col_w=16 if paper == "a3" else 12,
        day_col_w=20 if paper == "a3" else 16,
    )

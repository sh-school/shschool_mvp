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
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from operations.bells import REGULAR, THURSDAY, Bell, bells_for
from operations.models import ScheduleSlot

if TYPE_CHECKING:
    from core.models import CustomUser, School

#: عددُ الحصص في اليوم وعددُ أيّام الدراسة — شكلُ `days` في `ScheduleService`.
PERIODS = 7
DAYS = 5


@dataclass(frozen=True)
class BreakItem:
    """استراحةٌ في خانة: اسمُها ووقتُها واسمُ جرسها."""

    label: str
    start: dt.time
    end: dt.time
    band: str = ""


def day_type_of(day_of_week: int) -> str:
    """نوعُ اليوم من رقمه في `ScheduleSlot` (0 الأحد … 4 الخميس)."""
    return THURSDAY if day_of_week == 4 else REGULAR


def bell_tables(school: School) -> dict[str, dict[str, Bell]]:
    """أجراسُ المدرسة ليومَي الأسبوع — استعلامان للطلب كلِّه لا لكلّ صفحة."""
    return {REGULAR: bells_for(school, REGULAR), THURSDAY: bells_for(school, THURSDAY)}


#: اسمُ الجرس في خانة الاستراحة. «التاسع» وحدها تضلّل: تاسع 1·2 في الأرضيّ
#: (بلاغ المستخدم 2026-09-16)، و«الطابق» أوّلُ كلمةٍ من اسم الأرضيّ لا تميّزه.
#: والرقمان معزولان (U+2066…U+2069): مولّدُ PDF يقلبهما «4-3» بلا عازل.
BAND_LABELS = {
    "ground": "الأرضيّ",
    "ninth": "تاسع \u20663-4\u2069",
    "secondary": "الثانويّ",
}

#: لونُ تمييز عمود الاستراحة بطابقه — على الشاشة وحدها (2026-09-18)، ليعرف
#: معلّمُ الطابقين أيَّ صلاةٍ لأيّ طابقٍ بلمحةٍ لا بفتح الخليّة. مفتاحُه نصُّ
#: `BAND_LABELS` نفسُه، فيبقى صحيحاً لو تغيّر اسمُ طابقٍ يوماً.
BAND_COLOR_CLASS = {label: f"band-{code}" for code, label in BAND_LABELS.items()}


def band_label(bell: Bell) -> str:
    """اسمُ الجرس في خانة الاستراحة: «الأرضيّ» و«تاسع 3-4» و«الثانويّ»."""
    return BAND_LABELS.get(bell.band_code) or bell.band_short


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
                BreakItem(label=slot.label, start=slot.start, end=slot.end, band=band_label(bell)),
            )
        )
    return placed


def _day_breaks(bands: list[str], table: dict[str, Bell]) -> list[tuple[int, BreakItem]]:
    """استراحاتُ يومٍ من أجراسه: المتطابقُ اسماً ووقتاً يُكتب مرّةً بأسماء أجراسه
    كلِّها («تاسع 3-4 · الثانويّ»). واسمُ الجرس مكتوبٌ دائماً: فسحةٌ بلا جرسٍ
    تُقرأ فسحةَ الجميع، ووقتُها لا يصدق إلّا لجرسها."""
    seen: dict[tuple, tuple[int, list[str]]] = {}
    for code in [code for code in table if code in bands]:  # بترتيب الأجراس
        for after, item in breaks_after(table[code]):
            key = (item.label, item.start, item.end)
            if key not in seen:
                seen[key] = (after, [])
            if item.band not in seen[key][1]:
                seen[key][1].append(item.band)
    ordered = sorted(seen.items(), key=lambda pair: (pair[0][1], pair[1][0]))
    return [
        (after, BreakItem(label, start, end, " · ".join(band_names)))
        for (label, start, end), (after, band_names) in ordered
    ]


def cell_kind(slots: Iterable[Any] | None) -> str:
    """نوعُ أوّل حصّةٍ حُوّل معلّمُها في خانة: `swap` أو `cover` أو `comp` — وفارغٌ لغيرها.

    وحصصُ الخطّة بلا `kind` أصلاً، فخانتُها فارغةُ العلامة. تقرؤه الشبكةُ (`week_layout`) والجدولُ
    العامّ (`{{ cell|cell_kind }}`) وExcel — فلا تختلف علامةُ الخانة بين مخرجٍ ومخرج.
    """
    return next((kind for slot in slots or () if (kind := getattr(slot, "kind", ""))), "")


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
            # طابقُ العمود: صحيحٌ فقط حين يتّفق كلُّ يومٍ يستعمل هذا الموضع على
            # الاسم نفسه — فموضعٌ يخدم طابقين مختلفين في يومين مختلفين لا يُنسب
            # لأحدهما كذباً، ويبقى بلا لونٍ في الترويسة.
            bands = {item.band for breaks in per_day for after, item in breaks if after == number}
            band = bands.pop() if len(bands) == 1 else ""
            columns.append(
                {
                    "kind": "break",
                    "after": number,
                    "label": names.pop() if len(names) == 1 else "استراحة",
                    "band": band,
                    "band_class": BAND_COLOR_CLASS.get(band, ""),
                }
            )

    day_names = [name for _num, name in ScheduleSlot.DAYS]
    lines = []
    for d, cells in enumerate(days[:DAYS]):
        entries = []
        for column in columns:
            if column["kind"] == "period":
                slots = cells[column["number"] - 1]
                # الخانةُ المشتركةُ (حصّتان متوازيتان) بخطٍّ أصغر: كانت تُقصّ توقيتَ ثانيتهما.
                entries.append(
                    {
                        "kind": "period",
                        "number": column["number"],
                        "slots": slots,
                        "multi": len(slots) > 1,
                        # حصّةٌ حُوّل معلّمُها (أسبوعٌ فعليّ) تُلوَّن خانتُها — والخطّةُ بلا `kind`.
                        "change": cell_kind(slots),
                    }
                )
            else:
                entries.append(
                    {
                        "kind": "break",
                        "items": [item for after, item in per_day[d] if after == column["after"]],
                        "band_class": column["band_class"],
                    }
                )
        lines.append({"day": day_names[d], "entries": entries})
    return {"columns": columns, "lines": lines, "break_count": len(positions)}


#: قراراتٌ ثلاثةٌ فقط تُلوَّن في الجدول (قرارُ المستخدم 2026-09-18) — «لتوليد
#: الجدول» أداةُ تشكيلٍ لا قرارَ جهةٍ (انظر `TeacherExemption.SOFT_SOURCES`)،
#: و«أخرى» فئةٌ مبهمةٌ لا تستحقّ لوناً مخصَّصاً. والصنفُ والتسميةُ والحرفُ
#: القصيرُ من مصدرٍ واحدٍ هنا. والحرفُ لخانة الجدول العامّ الضيّقة (13px) —
#: لا تسع تسميةً كاملةً كخلايا جدول المعلم الفردي فتُقرأ نصّاً هناك.
EXEMPTION_COLORS: dict[str, tuple[str, str, str]] = {
    "ministry": ("exempt-ministry", "قرارُ الوزارة", "و"),
    "school": ("exempt-school", "قرارُ إدارة المدرسة", "إ"),
    "department": ("exempt-department", "قرارُ القسم الأكاديميّ", "ق"),
}


def _fill_exemption_map(out: dict, day: int, period: int | None, source: str, reason: str) -> None:
    """يومٌ كاملٌ يملأ حصصَه السبع بمصدره وسببه نفسيهما؛ وحصّةٌ بعينها خانتُها وحدها."""
    if period is None:
        for p in range(1, PERIODS + 1):
            out[(day, p)] = (source, reason)
    else:
        out[(day, period)] = (source, reason)


def teacher_exemption_map(
    school: School, teacher: CustomUser, year: str
) -> dict[tuple[int, int], tuple[str, str]]:
    """(يوم، حصّة) ← (مصدرُ تفريغه، سببُه) — لمعلّمٍ واحد، وللقرارات الثلاثة الملوَّنة وحدها.

    والخانةُ المشغولةُ فعلاً (تعارضٌ سابقُ التوليد) لا تُلوَّن — التلوينُ حكمٌ
    على الفراغ لا فوق حصّةٍ قائمة. لجدول العام (معلّمون كثيرون معاً) انظر
    `colored_exemptions_by_teacher` — استعلامٌ واحدٌ لا واحدٌ لكلّ معلّم.
    """
    from operations.models import TeacherExemption

    rows = TeacherExemption.objects.filter(
        school=school,
        teacher=teacher,
        academic_year=year,
        is_active=True,
        source__in=EXEMPTION_COLORS,
    ).values_list("day_of_week", "period_number", "source", "reason")

    out: dict[tuple[int, int], tuple[str, str]] = {}
    for day, period, source, reason in rows:
        _fill_exemption_map(out, day, period, source, reason)
    return out


def colored_exemptions_by_teacher(school: School, year: str) -> dict:
    """معلّمٌ ← {(يوم، حصّة): (مصدر، سبب)} — استعلامٌ واحدٌ للمدرسة كلِّها.

    الجدولُ العامّ سطرٌ لكلّ معلّمٍ من عشرات: استعلامٌ لكلّ سطرٍ سبعون
    استعلاماً إضافيّاً على صفحةٍ واحدة (`N+1`) — وهذه نظيرتُها الجماعيّة.
    """
    from operations.models import TeacherExemption

    rows = TeacherExemption.objects.filter(
        school=school,
        academic_year=year,
        is_active=True,
        source__in=EXEMPTION_COLORS,
    ).values_list("teacher_id", "day_of_week", "period_number", "source", "reason")

    out: dict = {}
    for teacher_id, day, period, source, reason in rows:
        _fill_exemption_map(out.setdefault(teacher_id, {}), day, period, source, reason)
    return out


def annotate_teacher_exemptions(
    week: dict, exemption_map: dict[tuple[int, int], tuple[str, str]]
) -> None:
    """يضع صنفَ التلوين والسببَ على خانات الفراغ التي تطابق `exemption_map`.

    الخليّةُ تكتب سببَ التفريغ («دورةٌ في الوزارة») لا اسمَ جهته («قرارُ
    الوزارة») — ذاك تقوله الألوانُ نفسُها وشريطُ تفسيرها أسفل الجدول
    (قرارُ المستخدم 2026-09-18)، فتكرارُه في كلّ خليّةٍ نثرٌ لا يزيد شيئاً.
    واسمُ الجهة يبقى في `title` الخليّة للتلميح عند الحاجة.

    يُعدَّل `week["lines"]` في مكانه — نداءٌ بعد `week_layout` مباشرةً، لا بديلٌ
    عنها: تلك تبني الأعمدة والصفوف، وهذه تُلوّن ما بُني.
    """
    for day_index, line in enumerate(week["lines"]):
        for entry in line["entries"]:
            if entry["kind"] != "period" or entry["slots"]:
                continue
            found = exemption_map.get((day_index, entry["number"]))
            if not found:
                continue
            source, reason = found
            css_class, label, _letter = EXEMPTION_COLORS[source]
            entry["exemption_class"] = css_class
            entry["exemption_label"] = label
            entry["exemption_reason"] = reason


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
    #: شريطُ المفتاح والملاحظات أسفل الجدول (الأسبوعُ الفعليّ) — صفرٌ للخطّة فلا يتبدّل مقاسُها.
    notes_h: float = 0.0

    @property
    def content_w(self) -> float:
        return self.page_w - 2 * self.margin_side

    @property
    def content_h(self) -> float:
        return self.page_h - self.margin_top - self.margin_bottom

    @property
    def bands_h(self) -> float:
        gaps = self.gap * (3 if self.who_h else 2) + (self.gap if self.notes_h else 0)
        return (
            self.header_h + self.who_h + self.thead_h + self.footer_h + self.notes_h + gaps
        ) + self.safety

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
            "notes_h": mm(self.notes_h),
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
            "multi_subject_pt": pt(7.5),
            "multi_pt": pt(6.5),
        }


_SHEETS = {("a4", "landscape"): (297, 210), ("a4", "portrait"): (210, 297)}
_SHEETS[("a3", "landscape")] = (420, 297)
_SHEETS[("a3", "portrait")] = (297, 420)


#: ارتفاعُ سطرٍ من شريط المفتاح والملاحظات: خطُّ 6.5pt بتباعدٍ يسع سطراً بلا قصّ.
STRIP_LINE_H = 3.4


def paper_geometry(
    paper: str, orient: str, *, with_who: bool, strip_lines: int = 0
) -> PaperGeometry:
    """مقاسُ ورقة المعلّم أو الشعبة.

    `with_who`: سطرُ «المعلّم · القسم · المنسّق» في ورقة الصفحات، ولا سطرَ له في
    الجدول المطبوع (العنوانُ يحمل الاسم).

    `strip_lines`: سطورُ شريط المفتاح والملاحظات أسفل جدول الأسبوع الفعليّ — تُقتطع من ارتفاع
    الصفوف فتبقى الورقةُ صفحةً واحدة.

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
        notes_h=round(STRIP_LINE_H * strip_lines, 1),
    )

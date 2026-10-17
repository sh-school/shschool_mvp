"""كشفُ الحصص مطبوعاً — بياناتُ كشف الشعبة وكشف الجناح لليوم.

مصدرٌ واحدٌ للطباعة والـPDF وExcel: تُبنى الصفوفُ والأعمدةُ والذيولُ هنا مرّةً،
ويرسمها كلُّ مخرَجٍ كما يرسمه — فلا يقول الـPDF رقماً ويقول Excel غيرَه.

قراراتُ 2026-09-13:

- **لا رقمَ شخصيّاً** في الكشف: الاسمُ يكفي لمن يوقّع، وأقلُّ البيانات أسلم.
- **توقيعٌ واحد**: مشرفُ الجناح وحدَه (D-385م، 2026-10-11 — يُلغي قرارَ الثلاثة تواقيع).
- **مصدران للرصد**: التثبيتُ القديم (`PeriodConfirmation`) ورصدُ المعلّم من جدول الشعبة (دفترُ الإدخال)؛ الكشفُ يقرؤهما معاً،
  والرصدُ بالإدخال يطابق لوحةَ المشرف بفرق 0 لأنّه يعدّ بـ`entry_tallies_by_start` نفسِها (W-20261011-011).
- **الكشفُ الجزئيّ مسموح**: يومٌ لم تُثبَّت حصصُه كلُّها يُطبع موسوماً «كشفٌ جزئيٌّ
  حتى HH:MM» — فلا يُحسب ورقُ الصباح كشفَ يومٍ كامل.
- **كشفُ الجناح**: مصفوفةُ شُعبه × حصص اليوم (وقتُ أوّل تثبيتٍ أو «لم تُرصد» أو
  «ثُبّتت متأخّرة» مع عدد الغائبين) — أداةُ محاسبة النائب الإداريّ — ثمّ كشفُ كلّ شعبة.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from django.utils import timezone

from core.ministry import ministry_line, ministry_name
from operations.attendance_precedence import Mark as PrecedenceMark
from operations.attendance_precedence import resolve_attendance
from operations.attendance_selectors import entry_heads_by_start, entry_tallies_by_start
from operations.day_attendance import enrolled_of
from operations.period_register import cells_of, periods_of

#: حرفُ الحال في الخانة — ومفتاحُه يُطبع أسفلَ الكشف.
LETTER = {"present": "ح", "absent": "غ", "late": "م"}
UNRECORDED = "·"

#: «أين الطالب» برمزٍ من حرفٍ واحد — الخانةُ ضيّقةٌ في سبعة أعمدة.
WHERE_CODE = {
    "clinic": "ع",
    "activity": "ن",
    "out_permit": "إ",
    "out_no_permit": "خ",
    "left_early": "س",
    "gate": "ب",
}

STATUS_LABEL = {
    "confirmed": "مثبّتة",
    "confirmed_late": "ثُبّتت متأخّرة",
    "current": "جارية",
    "missed": "لم تُرصد",
    "upcoming": "قادمة",
}


ENTERED_LABEL = "رُصدت"


@dataclass(frozen=True)
class Mark:
    """خانةُ طالبٍ في حصّة."""

    status: str  # present · absent · late · "" (لم تُرصد)
    minutes: int | None = None
    where: str = ""

    @property
    def letter(self) -> str:
        return LETTER.get(self.status, UNRECORDED)

    @property
    def where_code(self) -> str:
        return WHERE_CODE.get(self.where, "")

    @property
    def text(self) -> str:
        """الخانةُ نصّاً واحداً — «م 12»، «غ ع»، «ح»، «·»."""
        parts = [self.letter]
        if self.status == "late" and self.minutes is not None:
            parts.append(str(self.minutes))
        if self.where_code:
            parts.append(self.where_code)
        return " ".join(parts)


@dataclass(frozen=True)
class Column:
    """حصّةٌ من حصص اليوم وذيلُها: من ثبّتها ومتى وبأيّ عدد."""

    number: int
    start: dt.time
    end: dt.time
    subjects: str
    status: str
    first_confirmed_at: dt.datetime | None
    confirmed_by: str
    present: int
    absent: int
    late: int
    #: رصدُ المعلّم من جدول الشعبة (إدخالٌ) لا تثبيتُ مشرف — فوسمُها «رُصدت» لا «مثبّتة».
    from_entries: bool = False

    @property
    def is_confirmed(self) -> bool:
        return self.first_confirmed_at is not None

    @property
    def label(self) -> str:
        if self.from_entries:
            return ENTERED_LABEL
        return STATUS_LABEL.get(self.status, "")


@dataclass(frozen=True)
class Row:
    number: int
    name: str
    marks: list[Mark]

    @property
    def absent_periods(self) -> int:
        return sum(m.status == "absent" for m in self.marks)

    @property
    def late_count(self) -> int:
        return sum(m.status == "late" for m in self.marks)

    @property
    def late_minutes(self) -> int:
        return sum(m.minutes or 0 for m in self.marks if m.status == "late")


@dataclass(frozen=True)
class Signatory:
    title: str
    name: str


@dataclass
class SectionRegister:
    class_group: object
    wing: object
    day: dt.date
    as_of: dt.datetime
    columns: list[Column]
    rows: list[Row]
    signatories: list[Signatory] = field(default_factory=list)

    @property
    def is_partial(self) -> bool:
        """يومٌ لم تُثبَّت حصصُه كلُّها — يُطبع موسوماً لا ممنوعاً."""
        return any(not c.is_confirmed for c in self.columns)

    @property
    def title(self) -> str:
        return f"كشف حضور الحصص — {self.class_group.short_label}"

    @property
    def confirmed_count(self) -> int:
        return sum(c.is_confirmed for c in self.columns)

    @property
    def late_confirmations(self) -> int:
        return sum(c.status == "confirmed_late" for c in self.columns)

    @property
    def missed_count(self) -> int:
        return sum(c.status == "missed" for c in self.columns)


@dataclass
class WingRegister:
    wing: object
    day: dt.date
    as_of: dt.datetime
    sections: list[SectionRegister]
    signatories: list[Signatory] = field(default_factory=list)

    @property
    def is_partial(self) -> bool:
        return any(s.is_partial for s in self.sections)

    @property
    def width(self) -> int:
        """عددُ أعمدة المصفوفة — أطولُ يومٍ بين الشُّعب (الخميسُ ستٌّ لا سبع)."""
        return max((len(s.columns) for s in self.sections), default=0)

    @property
    def numbers(self) -> list[int]:
        return list(range(1, self.width + 1))

    @property
    def matrix(self) -> list[tuple[SectionRegister, list[Column | None]]]:
        width = self.width
        return [(s, s.columns + [None] * (width - len(s.columns))) for s in self.sections]

    @property
    def title(self) -> str:
        return f"كشف حضور الحصص — {self.wing.name}"


def footer_lines(school) -> tuple[str, str]:
    """ذيلُ كلّ صفحةٍ مطبوعة — نصُّ ذيل `base_qatar_report` نفسُه، للطباعة وExcel.

    كان الذيلُ في الـPDF وحدَه: يُكرَّر فيه أسفلَ كلّ صفحةٍ بصندوق هامشٍ لا يفهمه
    المتصفّح، فتُخفيه نسخةُ الطباعة، ولا يُكتب في Excel. والرؤيةُ من مكوّنها الواحد.
    """
    from django.template.loader import render_to_string

    parts = [getattr(school, "name", "") or ""]
    if getattr(school, "phone", ""):
        parts.append(f"هاتف: {school.phone}")
    if getattr(school, "email", ""):
        parts.append(school.email)
    if getattr(school, "city", ""):
        parts.append(f"{school.city}، قطر")
    vision = render_to_string("components/ministry_vision.html", {"school": school}).strip()
    return (
        " · ".join(p for p in parts if p),
        ministry_line(ministry_name(), vision),
    )


def signatories(wing, day: dt.date) -> list[Signatory]:
    """مشرفُ الجناح وحدَه (D-385م) — وإن لم يُعيَّن فخانةُ التوقيع تبقى للكتابة باليد."""
    holder = wing.current_supervisor(day) if wing is not None else None
    return [Signatory("مشرف الجناح", holder.full_name if holder else "")]


def section_register(class_group, day: dt.date, now: dt.datetime | None = None) -> SectionRegister:
    now = now or timezone.now()
    periods = periods_of(class_group, day)
    cells = cells_of(class_group, day)
    entry_heads = entry_heads_by_start(class_group, day)
    tallies = entry_tallies_by_start(class_group, day)
    # أوّلُ إدخالٍ في كلّ خانة — وقتُ «أوّل رصد» حين لا تثبيتَ للمشرف.
    first_entered: dict = {}
    for heads in entry_heads.values():
        for start, head in heads.items():
            if start not in first_entered or head.entered_at < first_entered[start]:
                first_entered[start] = head.entered_at

    columns = []
    for period in periods:
        c = period.confirmation
        if c is None and period.start in tallies:
            tally = tallies[period.start]
            columns.append(
                Column(
                    number=period.number,
                    start=period.start,
                    end=period.end,
                    subjects=period.subjects,
                    status="confirmed",
                    first_confirmed_at=timezone.localtime(first_entered[period.start]),
                    confirmed_by="",
                    present=tally["present"],
                    absent=tally["absent"],
                    late=tally["late"],
                    from_entries=True,
                )
            )
            continue
        columns.append(
            Column(
                number=period.number,
                start=period.start,
                end=period.end,
                subjects=period.subjects,
                status=period.status(day, now),
                first_confirmed_at=timezone.localtime(c.first_confirmed_at) if c else None,
                confirmed_by=(c.confirmed_by.full_name if c and c.confirmed_by_id else ""),
                present=c.present_count if c else 0,
                absent=c.absent_count if c else 0,
                late=c.late_count if c else 0,
            )
        )

    confirmed = {p.start for p in periods if p.confirmation is not None}
    rows = []
    for index, enrollment in enumerate(enrolled_of(class_group), start=1):
        own = cells.get(enrollment.student_id, {})
        own_entries = entry_heads.get(enrollment.student_id, {})
        marks = []
        for period in periods:
            cell = own.get(period.start) if period.start in confirmed else None
            head = own_entries.get(period.start)
            # الأسبقيّةُ من مصدرها الوحيد: إدخالُ المعلّم يغلب تثبيتَ المشرف، والمشرفُ يملأ الفراغ (D-420م).
            won = resolve_attendance(
                teacher_entry=PrecedenceMark(head.status, head.late_minutes) if head else None,
                supervisor=(
                    PrecedenceMark(cell.status, cell.late_minutes, cell.whereabouts)
                    if cell
                    else None
                ),
            )
            marks.append(Mark(won.status, won.late_minutes, won.whereabouts))
        rows.append(Row(index, enrollment.student.full_name, marks))

    wing = class_group.wing if class_group.wing_id else None
    return SectionRegister(
        class_group=class_group,
        wing=wing,
        day=day,
        as_of=timezone.localtime(now),
        columns=columns,
        rows=rows,
        signatories=signatories(wing, day),
    )


def wing_register(wing, day: dt.date, now: dt.datetime | None = None) -> WingRegister:
    now = now or timezone.now()
    sections = [
        section_register(klass, day, now)
        for klass in wing.class_groups.filter(is_active=True).order_by("grade", "section")
    ]
    return WingRegister(
        wing=wing,
        day=day,
        as_of=timezone.localtime(now),
        sections=sections,
        signatories=signatories(wing, day),
    )

"""استيرادُ كشف حضور الموظّفين من جهاز البصمة — غلافٌ حول ``StaffAttendanceService.mark``.

الكشفُ تصديرٌ خامٌّ من الجهاز (CSV بلا ترويسةٍ منتظمة): كلُّ سطرٍ يكرّر نصَّ ترويسة التقرير
الأصليّ ثمّ بياناتَ موظّفٍ واحد. والمنتفَعُ به منه سبعةُ حقول يُحدَّد موضعُها بالمرساة
«Department:» لا برقم العمود وحدَه، فلا يضلّ الفهرسُ إن زاد الجهازُ عموداً قبلها.

لا قاعدةَ عملٍ جديدةً هنا: التصنيفُ (حاضر/متأخّر/مستأذن/غائب) ودقائقُ التأخّر والانصراف
المبكر والتغطيةُ بالأذونات والإعفاءُ والتدقيقُ كلُّها في ``classify_arrival`` و``mark`` — يُحسب
الحالُ بهما ثمّ يُرصد بهما، فيصير الرصدُ المستورَدُ كالرصد اليدويّ تماماً (م-1 … م-9).

وما لا يُستورَد عمداً: بصمةُ دخولٍ ناقصة (كودُ الجهاز 103: وقتُ الحضور فيها 12:00AM افتراضيٌّ)،
لأنّ تخمينَ حضورٍ لم يُسجَّل يُنتج خصماً (البند 5) بلا شاهد؛ فتُعرض للسكرتير ليرصدها يدويّاً.
وأعمدةُ الجهاز Total وAbsent وAttend ليست حضوراً (ثابتةٌ أو ترقيمٌ تسلسليّ) فلا تُقرأ أصلاً.
"""

from __future__ import annotations

import calendar
import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any

from django.http import HttpRequest

import staff_affairs.attendance as _pkg
from core.models.audit import AuditLog
from core.models.school import School
from core.models.user import CustomUser

from .context import PolicyError, _minute, staff_members
from .daily import StaffAttendanceService
from .exemptions import exempt_ids
from .rules import STATUS_LABELS

#: مصدرُ الرصد في أثر التدقيق — يفرّق المستورَدَ عن اليدويّ عند أيّ مراجعة.
SOURCE = "biometric_import"

#: كودُ حالة الجهاز: بصمتا حضورٍ وانصرافٍ سليمتان.
DEVICE_OK = "102"
#: كودُ حالة الجهاز: بصمةُ الدخول ناقصة (وقتُ الحضور افتراضيٌّ 12:00AM).
DEVICE_MISSING_IN = "103"
DEVICE_CODES = (DEVICE_OK, DEVICE_MISSING_IN)

#: بدايةُ سطر بيانات الجهاز، والمرساةُ التي تُقاس منها مواضعُ الحقول.
_LINE_MARK = "Date :"
_ANCHOR = "Department:"
#: إزاحةُ كلّ حقلٍ عن المرساة (مأخوذةٌ من الملفّ الحقيقيّ 2026-09-30، 118 سطراً).
_OFF_EMPLOYEE = 2
_OFF_STATUS = 6
_OFF_IN = 9
_OFF_OUT = 16
_MIN_COLUMNS_AFTER_ANCHOR = _OFF_OUT + 1

#: أقصى حجم ملفٍّ مقبول — كشفُ يومٍ للكادر كلِّه بضعُ عشراتٍ من الكيلوبايت.
MAX_BYTES = 2 * 1024 * 1024
#: أقصى عدد أسطرٍ مقبول — كادرُ المدرسة بضعُ مئاتٍ × أيّامٌ قليلة؛ وكلُّ سطرٍ يُحفظ في الجلسة.
MAX_ROWS = 2000
#: ما يبقى للمعاينة قبل الاعتماد (بالثواني).
PREVIEW_TTL_SECONDS = 30 * 60


def window_start(today: date) -> date:
    """أقدمُ يومٍ يُقبل استيرادُه: قبل شهرٍ من اليوم (قرارُ المالك D-117م، 2026-10-02)."""
    year, month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    return date(year, month, min(today.day, calendar.monthrange(year, month)[1]))


# أفعالُ الصفّ في المعاينة.
NEW = "new"
UPDATE = "update"
SAME = "same"
CONFLICT = "conflict"
MISSING_IN = "missing_in"
UNMATCHED = "unmatched"
EXEMPT = "exempt"
SELF = "self"
INVALID = "invalid"

#: ما يُكتب عند الاعتماد دون قرارٍ إضافيّ من السكرتير.
WRITABLE = (NEW, UPDATE)

ACTION_LABELS = {
    NEW: "سيُرصد",
    UPDATE: "سيُستكمل",
    SAME: "مرصودٌ بالمثل",
    CONFLICT: "يخالف رصداً سابقاً",
    MISSING_IN: "بصمةُ دخولٍ ناقصة",
    UNMATCHED: "غيرُ مطابَق",
    EXEMPT: "معفًى من الرصد",
    SELF: "بصمتُك أنت",
    INVALID: "سطرٌ غيرُ صالح",
}


class BiometricFileError(ValueError):
    """الملفُّ كلُّه مرفوض — رسالتُه تُعرض للسكرتير كما هي."""


@dataclass(frozen=True)
class BiometricRow:
    """سطرُ موظّفٍ في كشف الجهاز: الرقمُ الوظيفيّ واليومُ والوقتان وكودُ الجهاز."""

    line: int
    employee_number: str
    day: date
    check_in: time | None
    check_out: time | None
    device_status: str

    def as_session(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "employee_number": self.employee_number,
            "day": self.day.isoformat(),
            "check_in": self.check_in.strftime("%H:%M") if self.check_in else "",
            "check_out": self.check_out.strftime("%H:%M") if self.check_out else "",
            "device_status": self.device_status,
        }

    @classmethod
    def from_session(cls, data: dict[str, Any]) -> BiometricRow:
        return cls(
            line=int(data["line"]),
            employee_number=str(data["employee_number"]),
            day=date.fromisoformat(data["day"]),
            check_in=_hhmm(data["check_in"]),
            check_out=_hhmm(data["check_out"]),
            device_status=str(data["device_status"]),
        )


@dataclass(frozen=True)
class ParseIssue:
    """سطرٌ لم يُقرأ — يُعرض رقمُ سطره وسببُه، ولا يُحذف صامتاً."""

    line: int
    message: str


@dataclass
class ParsedFile:
    rows: list[BiometricRow] = field(default_factory=list)
    issues: list[ParseIssue] = field(default_factory=list)


@dataclass
class PlanItem:
    """قرارُ المعاينة لصفٍّ واحد."""

    row: BiometricRow
    action: str
    staff: CustomUser | None = None
    status: str = ""
    late_minutes: int = 0
    check_out: time | None = None
    note: str = ""

    @property
    def label(self) -> str:
        return ACTION_LABELS[self.action]

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, "")


@dataclass
class ImportPreview:
    items: list[PlanItem]
    issues: list[ParseIssue]
    #: كادرُ المنصّة المرصودُ يومَه ولا سطرَ له في الكشف — يكشف المنقولين الذين لم تُسجَّل مغادرتُهم،
    #: ومن لم يبصم أصلاً؛ والحكمُ لمن يقرؤه (لا يُرصد غيابٌ منه تلقائيّاً).
    absent_from_file: list[tuple[date, list[CustomUser]]] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        out = dict.fromkeys(ACTION_LABELS, 0)
        for item in self.items:
            out[item.action] += 1
        return out

    @property
    def days(self) -> list[date]:
        return sorted({item.row.day for item in self.items})

    @property
    def writable(self) -> int:
        return sum(1 for item in self.items if item.action in WRITABLE)

    @property
    def conflicts(self) -> int:
        return sum(1 for item in self.items if item.action == CONFLICT)


@dataclass
class ImportResult:
    written: int = 0
    skipped_same: int = 0
    skipped_other: int = 0
    failed: list[tuple[BiometricRow, str]] = field(default_factory=list)


def _hhmm(raw: str) -> time | None:
    return datetime.strptime(raw, "%H:%M").time() if raw else None


def _decode(raw: bytes) -> str:
    """نصُّ الملفّ: UTF-8 (بصمةٌ أو بدونها) ثمّ ويندوز العربيّ — جهازٌ يصدّر بأيٍّ منهما."""
    for encoding in ("utf-8-sig", "cp1256"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise BiometricFileError("تعذّر قراءةُ ترميز الملفّ — صدِّرْه من الجهاز بصيغة CSV من جديد.")


def _parse_time(raw: str) -> time | None:
    """وقتُ البصمة «06:57AM» — والفارغُ أو منتصفُ الليل الافتراضيُّ يعني: لا بصمة."""
    text = raw.strip().upper().replace(" ", "")
    if not text:
        return None
    parsed = datetime.strptime(text, "%I:%M%p").time()
    return None if parsed == time(0, 0) else parsed


def parse(raw: bytes) -> ParsedFile:
    """يقرأ كشفَ الجهاز — يرفض ما ليس كشفاً، ويُبلغ عن كلّ سطرٍ فسد دون أن يُسقط غيرَه."""
    if len(raw) > MAX_BYTES:
        raise BiometricFileError("الملفُّ أكبرُ من الحدّ المقبول — كشفُ بصمةٍ ليومٍ واحدٍ أصغرُ بكثير.")
    parsed = ParsedFile()
    anchored = 0
    reader = csv.reader(io.StringIO(_decode(raw)))
    for line, cells in enumerate(reader, 1):
        if not any(cell.strip() for cell in cells):
            continue
        if not cells or cells[0].strip() != _LINE_MARK or _ANCHOR not in cells:
            parsed.issues.append(ParseIssue(line, "ليس سطرَ بياناتٍ بصيغة كشف الجهاز."))
            continue
        anchored += 1
        base = cells.index(_ANCHOR)
        if len(cells) <= base + _MIN_COLUMNS_AFTER_ANCHOR:
            parsed.issues.append(ParseIssue(line, "سطرٌ ناقصُ الأعمدة."))
            continue
        number = cells[base + _OFF_EMPLOYEE].strip()
        code = cells[base + _OFF_STATUS].strip()
        try:
            day = datetime.strptime(cells[1].strip(), "%d/%m/%Y").date()
            check_in = _parse_time(cells[base + _OFF_IN])
            check_out = _parse_time(cells[base + _OFF_OUT])
        except ValueError:
            parsed.issues.append(ParseIssue(line, "تاريخٌ أو وقتٌ بصيغةٍ غيرِ مقروءة."))
            continue
        if not number:
            parsed.issues.append(ParseIssue(line, "سطرٌ بلا رقمٍ وظيفيّ."))
            continue
        if code not in DEVICE_CODES:
            parsed.issues.append(ParseIssue(line, f"كودُ حالةٍ غيرُ معروف للجهاز ({code or 'فارغ'})."))
            continue
        parsed.rows.append(BiometricRow(line, number, day, check_in, check_out, code))
        if len(parsed.rows) > MAX_ROWS:
            raise BiometricFileError(f"أسطرُ الكشف أكثرُ من الحدّ المقبول ({MAX_ROWS}).")
    if not anchored:
        raise BiometricFileError(
            "الملفُّ ليس كشفَ حضورٍ وانصرافٍ من جهاز البصمة بالصيغة المعروفة — "
            "لم يُعثر على أيّ سطرٍ بصيغته."
        )
    return parsed


def _plan_row(
    school: School,
    actor: CustomUser,
    row: BiometricRow,
    staff: CustomUser | None,
    exempt: dict[date, set[Any]],
    existing: dict[tuple[Any, date], Any],
    seen: set[tuple[str, date]],
    today: date,
) -> PlanItem:
    key = (row.employee_number, row.day)
    if key in seen:
        return PlanItem(row, INVALID, staff, note="مكرَّرٌ في الملفّ لليوم نفسه.")
    seen.add(key)
    if row.day > today:
        return PlanItem(row, INVALID, staff, note="تاريخٌ لم يأتِ بعد.")
    if row.day < window_start(today):
        return PlanItem(
            row,
            INVALID,
            staff,
            note=f"أقدمُ من نافذة الاستيراد (شهر) — أقدمُ يومٍ مقبول {window_start(today):%d/%m/%Y}.",
        )
    if staff is None:
        return PlanItem(row, UNMATCHED, note="لا موظّفَ بهذا الرقم الوظيفيّ في هذه المدرسة.")
    if staff.pk == actor.pk:
        return PlanItem(row, SELF, staff, note="لا يرصد أحدٌ حضورَ نفسه — يرصده المديرُ يدويّاً.")
    if staff.pk in exempt[row.day]:
        return PlanItem(row, EXEMPT, staff, note="معفًى من الرصد اليوميّ في هذا اليوم.")
    if row.check_in is None:
        return PlanItem(
            row,
            MISSING_IN,
            staff,
            note="لا بصمةَ دخول" + (" — بصمةُ الانصراف مسجَّلة." if row.check_out else "."),
        )
    check_out, note = row.check_out, ""
    if check_out is not None and check_out <= row.check_in:
        check_out, note = None, "الانصرافُ قبل الحضور في الجهاز — أُهمل وُرصد الحضورُ وحدَه."
    record = existing.get((staff.pk, row.day))
    derived = StaffAttendanceService._derive(
        StaffAttendanceService._cover(school, staff, row.day),
        row.check_in,
        check_out,
        bool(record and record.accepted_excuse),
    )
    item = PlanItem(row, NEW, staff, derived["status"], derived["late_minutes"], check_out, note)
    if record is None:
        return item
    same_in = record.check_in is not None and _minute(record.check_in) == _minute(row.check_in)
    same_out = (record.check_out is None and check_out is None) or (
        record.check_out is not None
        and check_out is not None
        and _minute(record.check_out) == _minute(check_out)
    )
    if same_in and same_out and record.status == derived["status"]:
        item.action = SAME
    elif same_in and record.check_out is None and check_out is not None:
        item.action = UPDATE
        item.note = item.note or "يُضاف وقتُ الانصراف إلى رصدٍ قائم."
    else:
        item.action = CONFLICT
        item.note = "رصدٌ سابقٌ بأوقاتٍ أخرى — لا يُكتب فوقه إلّا بقرارٍ صريح."
    return item


def preview(
    school: School, actor: CustomUser, rows: list[BiometricRow], issues: list[ParseIssue]
) -> ImportPreview:
    """معاينةٌ بلا كتابة — لكلّ سطر: مطابقةٌ بالرقم الوظيفيّ وتصنيفٌ محسوب وسببُ أيّ تخطٍّ."""
    from staff_affairs.models import StaffAttendance

    numbers = {row.employee_number for row in rows}
    days = {row.day for row in rows}
    by_number = {
        s.employee_number: s
        for s in staff_members(school).filter(employee_number__in=numbers)
        if s.employee_number
    }
    exempt = {day: exempt_ids(school, day) for day in days}
    existing = {
        (r.staff_id, r.date): r
        for r in StaffAttendance.objects.filter(school=school, date__in=days)
    }
    seen: set[tuple[str, date]] = set()
    today = _pkg._now().date()
    items = [
        _plan_row(
            school, actor, row, by_number.get(row.employee_number), exempt, existing, seen, today
        )
        for row in rows
    ]
    return ImportPreview(items, issues)


def commit(
    school: School,
    actor: CustomUser,
    rows: list[BiometricRow],
    *,
    overwrite_conflicts: bool = False,
    request: HttpRequest | None = None,
) -> ImportResult:
    """يرصد ما أقرّته المعاينةُ عبر ``mark`` — والخطأُ في صفٍّ يُعرض ولا يُسقط الباقي.

    تُحسب الخطّةُ من جديد عند الاعتماد لا من المعاينة المحفوظة: قد يكون راصدٌ آخرُ كتب
    في الأثناء. وكلُّ ``mark`` معاملةٌ ذرّيّةٌ قائمةٌ بذاتها تحت قفل صفّ الموظّف؛ وإعادةُ
    الاستيراد آمنةٌ (المرصودُ بالمثل يُتخطّى) فانقطاعٌ في المنتصف يُستأنف بإعادة الرفع.
    """
    plan = preview(school, actor, rows, [])
    result = ImportResult()
    for item in plan.items:
        if item.action == SAME:
            result.skipped_same += 1
        elif item.action in WRITABLE or (item.action == CONFLICT and overwrite_conflicts):
            assert item.staff is not None  # noqa: S101 — الفعلان لا يقعان بلا موظّف
            try:
                StaffAttendanceService.mark(
                    school=school,
                    staff=item.staff,
                    day=item.row.day,
                    status=item.status,
                    actor=actor,
                    check_in=item.row.check_in,
                    check_out=item.check_out,
                    accepted_excuse=None,
                    request=request,
                    source=SOURCE,
                )
                result.written += 1
            except PolicyError as exc:
                result.failed.append((item.row, str(exc)))
        else:
            result.skipped_other += 1
    AuditLog.log(  # type: ignore[no-untyped-call]
        user=actor,
        action="create",
        model_name="other",
        object_id="",
        object_repr=f"BiometricImport {', '.join(d.isoformat() for d in plan.days)}"[:300],
        changes={
            "source": SOURCE,
            "written": result.written,
            "same": result.skipped_same,
            "skipped": result.skipped_other,
            "failed": len(result.failed),
            "overwrite_conflicts": overwrite_conflicts,
        },
        school=school,
        request=request,
    )
    return result

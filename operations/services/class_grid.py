"""جدولُ الشعبة العموديّ لرصد الغياب — صفوفُ الطلاب × أعمدةُ ح1…ح7 (W-20261006-005، قرارا المالك D-239م وD-240م).

**لِمَ**: الرصدُ بالمنتقي المؤقّت كان ينشئ حصّةً عند أوّل ضغطةٍ فيحجز الخانةَ على من يدرّسها فعلاً. هنا **الحصّةُ للعمود لا للمعلّم**:
شاشةٌ واحدةٌ لكلّ شعبةٍ يرصد عليها المخوَّلون جميعاً، وتُنشأ حصّةُ العمود **عند أوّل حفظٍ وحدَه** (لا عند العرض).

القواعدُ (كلُّها في الخدمة لا الواجهة):

- **المفتاحُ**: `PROVISIONAL_GRID_ENABLED` — مطفأً ← `GridNotFoundError` (404) لكلّ المسارات.
- **الصلاحيةُ** من `attendance_policy` (`can_read_grid`/`can_write_grid`/`can_correct_grid`) المشتقّةِ من الإسناد والجناح والدور لا من الطلب؛
  وغيرُ المخوَّل 404. والطلبةُ المكتوبُ لهم يُتحقَّق منهم في الخادم من **كشف الشعبة** لا من حقول الطلب.
- **حصّةُ العمود**: حقيقيّةٌ للخانة إن وُجدت، وإلّا مؤقّتةٌ بإنشاءٍ متساوي الأثر. و`Session.teacher` لها **مُسنَدٌ حتميّ** (الكاتبُ إن كان مُسنَداً وإلّا
  أصغرُ معرّفٍ بين مُسنَدي الشعبة باستبعاد حاملها) — والكاتبُ الفعليُّ في `entered_by` لا في `Session.teacher`.
- **الكتابةُ**: كلُّ خليّةٍ بحالةٍ صريحةٍ و`expected_head`، **كلُّ خليّةٍ بنقطة حفظٍ مستقلّة** (`savepoint`)؛ والمتعارضةُ تُرجَع ولا تُخسر البقيّة.
- **الفارغُ حاضراً (D-240م)**: لعمودٍ بدأت حصّتُه وحُفظ فقط، موسوماً `origin=grid_default`، ويُعدّ في التدقيق (عددٌ لا أسماء).
- **حدُّ معدّلٍ** للحفظات مستقلٌّ عن سقف المؤقّتة؛ وتدقيقٌ بالأعداد والمعرّفات لا الأسماء (PDPPL).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.academic_calendar import academic_year_for_school
from core.models import AuditLog, ClassGroup, CustomUser, StudentEnrollment
from operations.attendance_entries import (
    EntryConflictError,
    EntryError,
    GridConflictError,
    write_grid_cell,
)
from operations.attendance_policy import (
    GRID_HOLDER,
    GRID_LEADERSHIP,
    GRID_READER_ROLES,
    GRID_TEACHER,
    _wing_holder_on,
    can_approve,
    can_correct_grid,
    can_read_grid,
    can_write_grid,
    grid_now,
    grid_roles,
    grid_window,
    is_developer,
)
from operations.attendance_selectors import CellHistoryRow, ColumnCell, cell_history, column_heads
from operations.models import ClassExit, Session, SubjectClassAssignment
from operations.school_days import school_day

from . import provisional_session

if TYPE_CHECKING:
    from core.models import School

#: ح1 … ح7.
PERIOD_NUMBERS = provisional_session.PERIOD_NUMBERS
#: مدّةُ سريان حصّة العمود المؤقّتة (كحصّة المنتقي).
VALIDITY = provisional_session.VALIDITY
#: سقفُ خلايا الطلب الواحد: 7 أعمدةٍ × 60 طالباً.
MAX_CELLS = 7 * 60
#: وسمُ حصّة العمود المؤقّتة.
LABEL = "حصّةُ جدول الشعبة"
#: أسبابُ المنع التي تعني «لا يُعرف أنّ الشعبة موجودة» (404).
NOT_FOUND_REASONS = {"not_found"}


class GridNotFoundError(Exception):
    """ليس لك أن ترى هذا — يُترجم 404 (مفتاحٌ مطفأ، شعبةٌ غيرُ مخوَّلة، يومٌ غيرُ دراسيّ)."""


class GridRefusedError(Exception):
    """طلبٌ صحيحُ الصلاحيّة مرفوضٌ ومعه رمزُ السبب (`before_start`، `after_window`، `reason_required`…)."""

    def __init__(self, reason: str, message: str = ""):
        super().__init__(message or reason)
        self.reason = reason
        #: نصٌّ كتبناه نحن للعرض — لا `str(exc)` (يمنع تسرّبَ تتبّع الاستثناء إلى الاستجابة، CodeQL).
        self.message = message or reason


@dataclass(frozen=True)
class GridColumn:
    """عمودٌ واحد: رقمُ الحصّة وزمنُها وحصّتُه إن أُنشئت، وحالتُه الآن."""

    number: int
    start: dt.time
    end: dt.time
    session_id: Any
    #: past انقضت · current جاريةٌ الآن · future لم تبدأ
    state: str
    #: أيُكتب فيه الآن (بدأت حصّتُه وفي نافذة اليوم وللمستخدم صلاحية)؟
    writable: bool
    #: خلايا العمود المنتظرة قرارَ حاملِ الجناح، وهل لهذا المستخدم أن يعتمدها (زرُّ «اعتماد الحصّة» أسفل العمود).
    pending: int = 0
    approvable: bool = False

    @property
    def started(self) -> bool:
        return self.state != "future"


@dataclass(frozen=True)
class GridRow:
    student: CustomUser
    #: `(العمود، رأسُ خليّته أو None)` بترتيب الأعمدة — للقالب بلا فهرسة.
    pairs: list[tuple[GridColumn, ColumnCell | None]]
    #: خروجٌ مفتوحٌ لهذا الطالب في الحصّة الجارية (`ClassExit` — لم يعد بعد) أو `None`.
    exit: ClassExit | None = None


@dataclass(frozen=True)
class GridPage:
    klass: ClassGroup
    day: dt.date
    columns: list[GridColumn]
    rows: list[GridRow]
    roles: frozenset[str]
    #: بعد 14:00: المعلّمُ مقفلٌ ويصحّح المشرفُ بسبب.
    correction_mode: bool
    #: الحصّةُ الجاريةُ وقتَ العرض (لمفتاحَي المتأخّر والخروج) أو `None` (استراحةٌ/خارج الدوام).
    current: GridColumn | None
    opens: dt.datetime
    closes: dt.datetime
    #: لحظةُ العرض بساعة الشبكة (تتبع `ATTENDANCE_GRID_FAKE_TIME` في التطوير) — يقيس بها عدّادُ الخروج.
    now: dt.datetime
    #: أيكتب هذا المستخدمُ أصلاً (لا قراءةً فقط)؟
    can_write: bool
    #: وجهاتُ الخروج من الفصل (`ClassExit.DESTINATIONS`) لقائمة المفتاح.
    destinations: tuple[tuple[str, str], ...] = tuple(ClassExit.DESTINATIONS)

    @property
    def approvable_columns(self) -> list[GridColumn]:
        return [c for c in self.columns if c.approvable]

    @property
    def writable_columns(self) -> list[GridColumn]:
        """أعمدةٌ يكتب فيها هذا المستخدمُ الآن — لقائمة العمود في شريط «الكلّ ✓ / الكلّ ✗ / حفظ» فوق البطاقة."""
        return [c for c in self.columns if c.writable]


@dataclass
class SaveResult:
    """نتيجةُ حفظ عمود: ما حُفظ، وما تعارض (لكلٍّ رأسُه الحاليّ)، وعددُ الافتراضيّات."""

    session_id: Any
    saved: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    defaults: int = 0


# ══════════════════════════════════════════════════════════════════
# الوصول
# ══════════════════════════════════════════════════════════════════


def _require_enabled() -> None:
    if not provisional_session.grid_enabled():
        raise GridNotFoundError("الميزةُ مطفأة")


def _today(school: School) -> dt.date:
    """اليومُ الدراسيّ الجاري وحدَه — أيُّ يومٍ بلا دراسةٍ ← 404 (لا ماضيَ ولا مستقبل، D-215م)."""
    today: dt.date = grid_now().date()
    if not school_day(school, today).is_open:
        raise GridNotFoundError("لا دراسةَ اليوم")
    return today


def _class_or_404(school: School, class_id: Any) -> ClassGroup:
    try:
        return ClassGroup.objects.select_related("wing", "time_band", "school").get(
            pk=class_id, school=school, is_active=True
        )
    except (ClassGroup.DoesNotExist, ValueError, TypeError):
        raise GridNotFoundError("لا شعبة") from None


def _readable_class(
    user: CustomUser, school: School, class_id: Any
) -> tuple[ClassGroup, dt.date, frozenset[str]]:
    _require_enabled()
    day = _today(school)
    klass = _class_or_404(school, class_id)
    roles = grid_roles(user, klass, day)
    if not can_read_grid(user, klass, day, roles=roles):
        raise GridNotFoundError("ليست من شُعبك")
    return klass, day, roles


def classes_for(user: CustomUser, school: School) -> list[ClassGroup]:
    """شُعبُ هذا المستخدم للجدول: إسنادُه ∪ أجنحتُه، وللقيادة وحاصر الغياب والنائب الأكاديميّ كلُّ الشُّعب (قراءةً أو كتابة)."""
    if not provisional_session.grid_enabled():
        return []
    from wings.services import holds_school_wide, wings_of

    base = ClassGroup.objects.filter(
        school=school, is_active=True, academic_year=academic_year_for_school(school)
    ).select_related("wing")
    if is_developer(user):
        return []
    roles = set(
        user.memberships.filter(is_active=True, school=school).values_list("role__name", flat=True)
    )
    if roles & GRID_READER_ROLES or holds_school_wide(user):
        return list(base.order_by("grade", "section"))
    assigned = SubjectClassAssignment.objects.filter(
        school=school,
        teacher=user,
        is_active=True,
        deleted_at__isnull=True,
        academic_year=academic_year_for_school(school),
    ).values_list("class_group_id", flat=True)
    wing_ids = [wing.pk for wing in wings_of(user, school, academic_year_for_school(school))]
    from django.db.models import Q

    return list(
        base.filter(Q(pk__in=list(assigned)) | Q(wing_id__in=wing_ids)).order_by("grade", "section")
    )


# ══════════════════════════════════════════════════════════════════
# العرض
# ══════════════════════════════════════════════════════════════════


def _column_sessions(
    klass: ClassGroup, day: dt.date, bell: dict[int, tuple[dt.time, dt.time]]
) -> dict[int, Session]:
    """حصّةُ كلّ عمودٍ إن وُجدت باستعلامٍ واحد: حقيقيّةٌ لخانته أوّلاً ثمّ مؤقّتةٌ بالرقم."""
    rows = list(
        Session.objects.filter(class_group=klass, date=day)
        .exclude(status="cancelled")
        .order_by("created_at")
    )
    found: dict[int, Session] = {}
    for number, (start, _end) in bell.items():
        real = next((s for s in rows if not s.provisional and s.start_time == start), None)
        provisional = next(
            (
                s
                for s in rows
                if s.provisional and s.period_number == number and not s.elective_group
            ),
            None,
        )
        chosen = real or provisional
        if chosen is not None:
            found[number] = chosen
    return found


def _with_pending(
    column: GridColumn, user: CustomUser, session: Session | None, cells: dict[Any, ColumnCell]
) -> GridColumn:
    """يضيف عدّادَ المنتظر وأهليّةَ الاعتماد للعمود — الأهليّةُ للسياسة وحدَها، لا لمن كتب الإدخال بنفسه."""
    if session is None:
        return column
    waiting = sum(
        1 for (sid, _s), cell in cells.items() if sid == session.pk and cell.state == "pending"
    )
    if not waiting:
        return column
    return dataclasses.replace(column, pending=waiting, approvable=bool(can_approve(user, session)))


def _state_of(start: dt.time, end: dt.time, now: dt.time) -> str:
    if now < start:
        return "future"
    return "current" if now < end else "past"


def page(
    user: CustomUser, school: School, class_id: Any, *, now: dt.datetime | None = None
) -> GridPage:
    """سياقُ صفحة الشعبة: الطلبةُ (قيدٌ نشطٌ بدأ في تاريخ اليوم أو قبله) × أعمدةُ جرس الشعبة، ورؤوسُ السلاسل باستعلامٍ واحد."""
    klass, day, roles = _readable_class(user, school, class_id)
    moment = grid_now(now)
    bell = provisional_session.bell_periods(school, klass, day)
    sessions = _column_sessions(klass, day, bell)
    opens, closes = grid_window(day)
    inside = opens <= moment <= closes
    columns = []
    for number in PERIOD_NUMBERS:
        times = bell.get(number)
        if times is None:
            continue
        start, end = times
        state = _state_of(start, end, moment.time())
        verdict = can_write_grid(user, klass, day, period_start=start, now=moment, roles=roles)
        session = sessions.get(number)
        columns.append(
            GridColumn(
                number=number,
                start=start,
                end=end,
                session_id=session.pk if session else None,
                state=state,
                writable=bool(verdict) and inside,
            )
        )
    students = [
        enrollment.student
        for enrollment in StudentEnrollment.objects.filter(
            class_group=klass, is_active=True, enrolled_at__lte=day
        )
        .select_related("student")
        .order_by("student__full_name")
    ]
    cells = column_heads([c.session_id for c in columns if c.session_id])
    columns = [_with_pending(c, user, sessions.get(c.number), cells) for c in columns]
    current = next((c for c in columns if c.state == "current"), None)
    open_exits = (
        {
            e.student_id: e
            for e in ClassExit.objects.filter(
                session_id=current.session_id, returned_at__isnull=True
            )
        }
        if current is not None and current.session_id
        else {}
    )
    rows = [
        GridRow(
            student=student,
            pairs=[
                (c, cells.get((c.session_id, student.pk)) if c.session_id else None)
                for c in columns
            ],
            exit=open_exits.get(student.pk),
        )
        for student in students
    ]
    write_roles = roles & {GRID_TEACHER, GRID_HOLDER, GRID_LEADERSHIP}
    return GridPage(
        klass=klass,
        day=day,
        columns=columns,
        rows=rows,
        roles=roles,
        correction_mode=bool(write_roles) and moment > closes,
        current=current,
        opens=opens,
        closes=closes,
        now=moment,
        can_write=bool(write_roles),
    )


def history(
    user: CustomUser, school: School, class_id: Any, student_id: Any, number: Any
) -> tuple[ClassGroup, CustomUser, list[CellHistoryRow]]:
    """سجلُّ خليّةٍ: من كتب ومتى ومن صحّح. الطالبُ من كشف الشعبة وإلّا 404."""
    klass, day, _roles = _readable_class(user, school, class_id)
    student = _roster_student(klass, day, student_id)
    try:
        wanted = int(number)
    except (TypeError, ValueError):
        raise GridNotFoundError("حصّةٌ غيرُ معروفة") from None
    session = _column_sessions(
        klass, day, provisional_session.bell_periods(school, klass, day)
    ).get(wanted)
    if session is None:
        return klass, student, []
    return klass, student, cell_history(session, student)


def _roster_student(klass: ClassGroup, day: dt.date, student_id: Any) -> CustomUser:
    try:
        wanted = UUID(str(student_id))
    except ValueError:
        raise GridNotFoundError("طالبٌ غيرُ معروف") from None
    enrollment = (
        StudentEnrollment.objects.filter(
            class_group=klass, is_active=True, enrolled_at__lte=day, student_id=wanted
        )
        .select_related("student")
        .first()
    )
    if enrollment is None:
        raise GridNotFoundError("طالبٌ ليس في الشعبة")
    return enrollment.student  # type: ignore[no-any-return]


# ══════════════════════════════════════════════════════════════════
# الحفظ
# ══════════════════════════════════════════════════════════════════


def _throttle_saves(user: CustomUser) -> None:
    """حدُّ معدّلٍ **مستقلٌّ** لحفظات الجدول (كتلُ 7×~30) — كلُّ محاولةٍ تُعدّ ولو رُفضت."""
    key = f"classgrid:saves:{user.pk}:{timezone.now():%Y%m%d%H}"
    cache.add(key, 0, timeout=3600)
    try:
        attempts = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=3600)
        attempts = 1
    if attempts > int(getattr(settings, "ATTENDANCE_GRID_SAVES_PER_HOUR", 60)):
        raise GridRefusedError("rate_limited", "حفظاتٌ كثيرةٌ في الساعة الأخيرة — حاول لاحقاً")


def _assignments(klass: ClassGroup) -> list[SubjectClassAssignment]:
    return list(
        SubjectClassAssignment.objects.filter(
            school_id=klass.school_id,
            class_group=klass,
            is_active=True,
            deleted_at__isnull=True,
            academic_year=academic_year_for_school(klass.school),
        )
        .select_related("subject")
        .order_by("teacher_id", "subject_id")
    )


def _column_teacher(user: CustomUser, klass: ClassGroup, day: dt.date) -> tuple[CustomUser, Any]:
    """`Session.teacher` لحصّة العمود وموادُّها: **مُسنَدٌ حتميّ** — الكاتبُ إن كان مُسنَداً وإلّا أصغرُ معرّفٍ بين مُسنَدي الشعبة باستبعاد حاملها.

    فلا يصير المشرفُ أو الإداريُّ `Session.teacher` (فلا `own_session` ولا `holder_gap` بسببه) ولا تُنسب الحصّةُ لمن لا يدرّسها. شعبةٌ بلا إسنادٍ
    يكتب فيها إداريٌّ: يبقى الكاتبُ نفسُه (افتراضٌ معلن، لا مُسنَدَ يُنسب إليه).
    """
    assigned = _assignments(klass)
    mine = [a for a in assigned if a.teacher_id == user.id]
    if mine:
        return user, mine[0].subject
    holder = _wing_holder_on(klass, day)
    pool = [a for a in assigned if holder is None or a.teacher_id != holder.id] or assigned
    if not pool:
        return user, None
    chosen = pool[0]
    return chosen.teacher, chosen.subject


def _ensure_session(
    user: CustomUser,
    school: School,
    klass: ClassGroup,
    day: dt.date,
    number: int,
    times: tuple[dt.time, dt.time],
    request: Any,
) -> Session:
    """حصّةُ العمود بإنشاءٍ **متساوي الأثر**: حقيقيّةٌ لخانته أو مؤقّتةٌ قائمةٌ تُستعمل، وإلّا تُنشأ؛ وعند سباقٍ على القيد تُعاد القراءةُ (لا خطأ للمستخدم)."""
    start, end = times
    found = _column_sessions(klass, day, {number: times}).get(number)
    if found is not None:
        return found
    teacher, subject = _column_teacher(user, klass, day)
    try:
        with transaction.atomic():
            session = Session.objects.create(
                school=school,
                class_group=klass,
                teacher=teacher,
                subject=subject,
                date=day,
                start_time=start,
                end_time=end,
                period_number=number,
                status="scheduled",
                provisional=True,
                provisional_until=timezone.now() + VALIDITY,
                notes=LABEL,
            )
    except IntegrityError:
        again = _column_sessions(klass, day, {number: times}).get(number)
        if again is None:
            raise GridRefusedError("busy", "تعذّر إنشاءُ حصّة العمود — أعِد المحاولة.") from None
        return again
    AuditLog.log(
        user=user,
        action="create",
        model_name="other",
        object_id=session.pk,
        object_repr=f"{LABEL} — إنشاءٌ عند أوّل حفظ",
        changes={"class_group": str(klass.pk), "date": day.isoformat(), "period": number},
        school=school,
        request=request,
    )
    return session


def _parse_cells(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or len(raw) > MAX_CELLS:
        raise GridRefusedError("bad_payload", "حمولةٌ غيرُ صالحةٍ أو أكبرُ من الحدّ")
    cells = []
    for item in raw:
        if not isinstance(item, dict):
            raise GridRefusedError("bad_payload", "خليّةٌ غيرُ صالحة")
        cells.append(item)
    return cells


def _minutes(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if 0 < number <= 600 else None


def _cell_payload(student_id: Any, cell: ColumnCell | None) -> dict[str, Any]:
    return {
        "student": str(student_id),
        "head": cell.head_id if cell else "",
        "status": cell.status if cell else "",
        "minutes": cell.minutes if cell else None,
        "state": cell.state if cell else "",
        "default_present": bool(cell and cell.default_present),
        "by": cell.entered_by_name if cell else "",
        "at": timezone.localtime(cell.entered_at).strftime("%H:%M") if cell else "",
    }


def save_column(
    user: CustomUser,
    school: School,
    class_id: Any,
    number: Any,
    cells: Any,
    *,
    fill_empty: bool = False,
    bulk: str = "",
    reason: str = "",
    request: Any = None,
    now: dt.datetime | None = None,
) -> SaveResult:
    """يحفظ عموداً: حصّتُه مرّةً متساويةَ الأثر، ثمّ **كلُّ خليّةٍ بنقطة حفظٍ مستقلّة**؛ والمتعارضةُ تُرجَع بدل أن تُخسر العمود.

    `fill_empty`: الفارغاتُ حاضرٌ افتراضيّ (D-240م) — لعمودٍ بدأت حصّتُه وحُفظ فقط. وبعد إغلاق النافذة التصحيحُ لحاملِ الجناح والقيادة بسببٍ إلزاميّ.
    """
    _require_enabled()
    day = _today(school)
    klass = _class_or_404(school, class_id)
    moment = grid_now(now)
    try:
        wanted = int(number)
    except (TypeError, ValueError):
        raise GridRefusedError("bad_period", "رقمُ الحصّة غيرُ صالح") from None
    times = provisional_session.bell_periods(school, klass, day).get(wanted)
    if wanted not in PERIOD_NUMBERS or times is None:
        raise GridRefusedError("bad_period", "لا زمنَ مُعرَّفاً لهذه الحصّة في جرس هذه الشعبة")
    posted = _parse_cells(cells)

    verdict = can_write_grid(user, klass, day, period_start=times[0], now=moment)
    correcting = False
    if not verdict:
        if verdict.reason in NOT_FOUND_REASONS:
            raise GridNotFoundError("ليست من شُعبك")
        if verdict.reason == "after_window" and can_correct_grid(user, klass, day, now=moment):
            correcting = True
            if not (reason or "").strip():
                raise GridRefusedError("reason_required", "التصحيحُ بعد إغلاق النافذة يلزمه سبب")
        else:
            raise GridRefusedError(verdict.reason)
    _throttle_saves(user)

    roster = {
        enrollment.student_id: enrollment.student
        for enrollment in StudentEnrollment.objects.filter(
            class_group=klass, is_active=True, enrolled_at__lte=day
        ).select_related("student")
    }
    with transaction.atomic():
        session = _ensure_session(user, school, klass, day, wanted, times, request)
        existing = column_heads([session.pk])
        result = SaveResult(session_id=session.pk)
        seen: set[Any] = set()
        for item in posted:
            student = roster.get(_uuid_or_none(item.get("student")))
            if student is None or student.pk in seen:
                result.errors.append(
                    {"student": str(item.get("student", "")), "code": "not_enrolled"}
                )
                continue
            seen.add(student.pk)
            _write_one(user, session, student, item, result, correcting=correcting, reason=reason)
        if fill_empty:
            for student_id, student in roster.items():
                if student_id in seen or (session.pk, student_id) in existing:
                    continue
                _write_default(user, session, student, result)
        AuditLog.log(
            user=user,
            action="update",
            model_name="other",
            object_id=session.pk,
            object_repr="جدول الشعبة — حفظُ عمود",
            changes={
                "class_group": str(klass.pk),
                "period": wanted,
                "written": len(result.saved) - result.defaults,
                "default_present": result.defaults,
                "conflicts": len(result.conflicts),
                "bulk": bulk if bulk in {"all_present", "all_absent"} else "",
                "correction": correcting,
            },
            school=school,
            request=request,
        )
    return result


def _uuid_or_none(raw: Any) -> UUID | None:
    try:
        return UUID(str(raw))
    except ValueError:
        return None


def _write_one(
    user: CustomUser,
    session: Session,
    student: CustomUser,
    item: dict[str, Any],
    result: SaveResult,
    *,
    correcting: bool,
    reason: str,
) -> None:
    status = str(item.get("status", ""))
    minutes = _minutes(item.get("minutes"))
    if status == "late" and minutes is None:
        minutes = _late_minutes(session)
    try:
        with transaction.atomic():  # نقطةُ حفظٍ لكلّ خليّة
            entry, _created = write_grid_cell(
                user,
                session,
                student,
                status,
                minutes=minutes,
                expected_head=str(item.get("head") or ""),
            )
    except GridConflictError as conflict:
        current = (
            column_heads([session.pk]).get((session.pk, student.pk)) if conflict.current else None
        )
        result.conflicts.append(_cell_payload(student.pk, current))
        return
    except (EntryConflictError, EntryError) as error:
        result.errors.append({"student": str(student.pk), "code": getattr(error, "code", "error")})
        return
    result.saved.append(
        _cell_payload(student.pk, column_heads([session.pk]).get((session.pk, student.pk)))
    )
    if correcting:
        AuditLog.log(
            user=user,
            action="update",
            model_name="other",
            object_id=entry.pk,
            object_repr="جدول الشعبة — تصحيحٌ بعد الإغلاق",
            changes={"reason": (reason or "").strip()[:300], "student": str(student.pk)},
            school=session.school,
        )


def _write_default(
    user: CustomUser, session: Session, student: CustomUser, result: SaveResult
) -> None:
    try:
        with transaction.atomic():
            write_grid_cell(user, session, student, "present", default_present=True)
    except GridConflictError:
        # كتب متزامنٌ الخليّةَ أثناء الحفظ — لا نكتب فوقه ولا نُظهرها تعارضاً (لم يرها العميلُ فارغةً ثمّ غيّرها).
        return
    except (EntryConflictError, EntryError):
        return
    result.defaults += 1
    result.saved.append(
        _cell_payload(student.pk, column_heads([session.pk]).get((session.pk, student.pk)))
    )


def _late_minutes(session: Session) -> int:
    """دقائقُ التأخّر منذ بدء الحصّة حتّى الآن (على الأقلّ دقيقة)."""
    start = timezone.make_aware(dt.datetime.combine(session.date, session.start_time))
    return max(1, int((grid_now() - start).total_seconds() // 60))


def mark_late_now(
    user: CustomUser, school: School, class_id: Any, student_id: Any, *, request: Any = None
) -> SaveResult:
    """«دخول متأخّر» لطالبٍ: ينسب الحدثَ إلى **الحصّة الجارية وقتَ الضغط** (من جرس الشعبة لا من العمود المعروض) — لا حصّةَ جاريةً ← رفض (الزرُّ معطَّل)."""
    _require_enabled()
    day = _today(school)
    klass = _class_or_404(school, class_id)
    if not can_read_grid(user, klass, day):
        raise GridNotFoundError("ليست من شُعبك")
    student = _roster_student(klass, day, student_id)
    now = grid_now()
    bell = provisional_session.bell_periods(school, klass, day)
    current = next(
        (n for n, (s, e) in sorted(bell.items()) if _state_of(s, e, now.time()) == "current"), None
    )
    if current is None:
        raise GridRefusedError("no_current_period", "لا حصّةَ جاريةً الآن")
    session = _column_sessions(klass, day, bell).get(current)
    head = column_heads([session.pk]).get((session.pk, student.pk)) if session else None
    return save_column(
        user,
        school,
        class_id,
        current,
        [{"student": str(student.pk), "status": "late", "head": head.head_id if head else ""}],
        request=request,
    )


def redirect_target(user: CustomUser, session: Session) -> str | None:
    """رابطُ جدول شعبة هذه الحصّة إن كان مفتاحُ الجدول مشغَّلاً ويقرؤه هذا المستخدمُ — وإلّا `None` فيبقى الكشفُ القديمُ بديلاً (بديلٌ لا إسنادَ له مثلاً).

    أمرُ المالك 2026-10-06: «اطفئ الشبكة» — مع المفتاح لا يُفتح كشفُ الحصّة القديمُ لمن يملك الجدول، بل جدولُ شعبته.
    """
    from django.urls import reverse

    if not provisional_session.grid_enabled() or session.date != grid_now().date():
        return None
    if not can_read_grid(user, session.class_group, session.date):
        return None
    return reverse("class_grid", args=[session.class_group_id])


def grid_url_for_class(
    user: CustomUser, klass: ClassGroup, day: dt.date | None = None
) -> str | None:
    """رابطُ جدول هذه الشعبة لليوم الجاري إن كان المفتاحُ مشغَّلاً ويقرؤه المستخدم — لكشف المشرف القديم (`wings.record_section`) فيفتح الجدولَ بدل الشبكة."""
    from django.urls import reverse

    if not provisional_session.grid_enabled():
        return None
    today = grid_now().date()
    if day is not None and day != today:
        return None
    if not can_read_grid(user, klass, today):
        return None
    return reverse("class_grid", args=[klass.pk])


def opens_the_grid(view):
    """مزخرِف عرضٍ يأخذ `class_id`: مع مفتاح الجدول وفي اليوم الجاري يحوّل من قرأ الشعبةَ إلى جدولها بدل الكشف القديم."""
    import functools

    from django.shortcuts import redirect

    @functools.wraps(view)
    def wrapper(request, class_id, *args, **kwargs):
        klass = ClassGroup.objects.filter(pk=class_id, school=request.school).first()
        try:
            day = dt.date.fromisoformat(request.GET["date"]) if request.GET.get("date") else None
        except ValueError:
            return view(request, class_id, *args, **kwargs)  # تاريخٌ فاسدٌ يعالجه الكشفُ نفسُه
        if klass is not None and (target := grid_url_for_class(request.user, klass, day)):
            return redirect(target)
        return view(request, class_id, *args, **kwargs)

    return wrapper


def exit_action(
    user: CustomUser,
    school: School,
    class_id: Any,
    student_id: Any,
    action: str,
    destination: str = "",
    *,
    request: Any = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """«خرج من الفصل» / «عاد» لطالبٍ في **الحصّة الجارية وقتَ الضغط** (قرارُ المالك D-239م) — بمسار `ClassExit` القائم دون تعديل (`class_exit.leave/come_back`).

    الصلاحيةُ نفسُها كتابةِ الجدول (`can_write_grid` لعمود الحصّة الجارية)؛ ولا حصّةَ جاريةً ← رفض (الزرُّ معطَّل). والغائبُ لا يُفتح له خروج
    (غائبٌ وخروجٌ لا يجتمعان). والوجهةُ من قائمة `ClassExit.DESTINATIONS` وما سواها «أخرى».
    """
    from operations.class_exit import come_back, leave

    _require_enabled()
    day = _today(school)
    klass = _class_or_404(school, class_id)
    if not can_read_grid(user, klass, day):
        raise GridNotFoundError("ليست من شُعبك")
    student = _roster_student(klass, day, student_id)
    moment = grid_now(now)
    bell = provisional_session.bell_periods(school, klass, day)
    current = next(
        (n for n, (s, e) in sorted(bell.items()) if _state_of(s, e, moment.time()) == "current"),
        None,
    )
    if current is None:
        raise GridRefusedError("no_current_period", "لا حصّةَ جاريةً الآن")
    verdict = can_write_grid(user, klass, day, period_start=bell[current][0], now=moment)
    if not verdict:
        if verdict.reason in NOT_FOUND_REASONS:
            raise GridNotFoundError("ليست من شُعبك")
        raise GridRefusedError(verdict.reason)
    session = _ensure_session(user, school, klass, day, current, bell[current], request)
    if action == "return":
        closed = come_back(session, student, now=moment, by=user)
        return {"ok": True, "returned": closed is not None, "period": current}
    opened = leave(session, student, destination, by=user, now=moment)
    if opened is None:
        raise GridRefusedError("student_absent", "الطالبُ مرصودٌ غائباً — لا خروجَ لغائب")
    return {"ok": True, "destination": opened.destination, "period": current}


def approve_column(user: CustomUser, school: School, class_id: Any, number: Any) -> dict[str, int]:
    """«اعتماد الحصّة» من أسفل عمودها: يعتمد كلَّ ما ينتظر المستخدمَ في حصّة العمود **بما فيه الحاضرُ الافتراضيّ** (قرارُ المالك 2026-10-07).

    كلُّ إدخالٍ بقراره المسجَّل باسمه عبر المسار القائم (الأهليّةُ والقفلُ والتدقيق)، والرفضُ يبقى بنداً بنداً. غيرُ ذي سلطةٍ ← رفضٌ بسبب.
    """
    from operations.services.attendance_teacher import TeacherAttendanceService

    _require_enabled()
    klass, day, _roles = _readable_class(user, school, class_id)
    try:
        wanted = int(number)
    except (TypeError, ValueError):
        raise GridNotFoundError("حصّةٌ غيرُ معروفة") from None
    bell = provisional_session.bell_periods(school, klass, day)
    session = _column_sessions(klass, day, bell).get(wanted)
    if session is None:
        raise GridNotFoundError("لا حصّةَ لهذا العمود")
    if not can_approve(user, session):
        raise GridRefusedError("not_approver", "ليس لك اعتمادُ هذه الحصّة")
    approved, skipped = TeacherAttendanceService.approve_session(
        user, school, session.pk, with_defaults=True
    )
    return {"approved": approved, "skipped": skipped}

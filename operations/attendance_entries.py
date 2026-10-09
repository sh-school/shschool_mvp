"""رصدُ المعلّم الفعليّ — إدخالٌ مبدئيّ ثمّ قرارُ حاملِ الجناح، والرصدُ المعتمَدُ وحدَه يصل `StudentAttendance`.

التصميمُ وأسبابُه في [`models/attendance_ledger.py`](models/attendance_ledger.py)، والسياسةُ (من يُدخل ومن يعتمد
ومتى) في [`attendance_policy.py`](attendance_policy.py) — وهنا التنفيذُ الذرّيّ:

- `submit_entry` — المعلّمُ الفعليّ يُدخل (أو يصحّح). في شُعب الأجنحة يبقى الإدخالُ **معلَّقاً** ولا يُكتب شيءٌ في
  `StudentAttendance`؛ وفي التربية الخاصّة يُقرَّر فيه ذاتيّاً في المعاملة نفسِها ويُكتب فوراً (موسوماً صراحةً).
- `decide_entry` — حاملُ الجناح (أو القيادةُ حين لا حاملَ) يعتمد أو يرفض. قفلُ صفّ الإدخال، وإعادةُ تقييم الأهليّة
  داخل القفل، وقرارٌ واحدٌ لكلّ إدخال (قيدٌ فريد)، والدليلُ يُحفظ.
- `erase_attendance_ledger` — محوُ طالبٍ (PDPPL م.18): المسارُ الوحيد الذي يحذف من السجلّ.

كلُّ إدخالٍ وقرارٍ وكتابةٍ فوق صفٍّ فعّالٍ يكتب `AuditLog` بالمعرّفات لا بالأسماء (PDPPL).
والفاعلُ (`entered_by`، `decided_by`) من الخادم وحدَه — الدوالُّ لا تقبل فاعلاً ولا حالةَ اعتماد من الطلب.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import TYPE_CHECKING, Any

from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from core.models import AuditLog

from .attendance_policy import (
    can_enter,
    is_special_education,
)
from .models import Session, StudentAttendance
from .models.attendance_ledger import ERASURE_FLAG, AttendanceDecision, AttendanceEntry

if TYPE_CHECKING:
    from core.models import CustomUser, School

logger = logging.getLogger(__name__)

#: مصدرُ ما يُكتب في `StudentAttendance` عند اعتماد إدخالِ معلّم.
SOURCE = "teacher"

#: مصادرُ يجوز لاعتمادِ المعلّم أن يحلّ محلَّها — نقرةُ التأخّر ورصدُ المعلّم نفسُه. وما سواها (مشرف، عيادة،
#: بوّابة، نظام/خروج) رصدٌ بشريٌّ أو مشتقٌّ آخر فلا يُكتب فوقه: يبقى الإدخالُ معلَّقاً ويُحلّ بالرفض بسبب.
OVERWRITABLE_SOURCES = {"teacher", "teacher_late"}

ENTERABLE_STATUSES = {code for code, _ in AttendanceEntry.STATUS}

#: سقفُ نصّ السبب (رفضٍ أو تصحيح): نصٌّ حرٌّ يُكتب في التدقيق وقد يحمل ما لا يُراد حفظُه بلا حدّ (حكمُ 0105 P3).
MAX_REASON_LENGTH = 300


def _checked_reason(reason: str) -> str:
    reason = (reason or "").strip()
    if len(reason) > MAX_REASON_LENGTH:
        raise EntryError("reason_too_long", f"السببُ أطولُ من {MAX_REASON_LENGTH} حرفاً.")
    return reason


class EntryError(Exception):
    """خطأٌ في طلب الإدخال/القرار، برمزٍ مختصرٍ يُعرض ويُختبر."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


class EntryRefusedError(EntryError):
    """السياسةُ منعت: `reason` رمزُ المنع من `attendance_policy`."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class EntryConflictError(EntryError):
    """اعتمادُ الإدخال يصطدم برصدٍ بشريٍّ آخر — لا كتابةَ فوقه."""


# ══════════════════════════════════════════════════════════════════
# القراءة
# ══════════════════════════════════════════════════════════════════


def state_of(entry: AttendanceEntry) -> str:
    """حالةُ الإدخال المشتقّة: `superseded` | `approved` | `rejected` | `pending`."""
    if AttendanceEntry.objects.filter(supersedes_id=entry.pk).exists():
        return "superseded"
    decision = AttendanceDecision.objects.filter(entry_id=entry.pk).values_list(
        "decision", flat=True
    )
    return next(iter(decision), "pending")


def head_of(session: Session, student: CustomUser, *, lock: bool = False) -> AttendanceEntry | None:
    """رأسُ سلسلة الإدخالات لهذا الزوج — الإدخالُ الذي لا خلفَ له."""
    qs = AttendanceEntry.objects.filter(
        session=session, student=student, superseded_by__isnull=True
    )
    if lock:
        qs = qs.select_for_update(of=("self",))
    head: AttendanceEntry | None = qs.first()
    return head


# ══════════════════════════════════════════════════════════════════
# التدقيق
# ══════════════════════════════════════════════════════════════════


def _audit(
    user: CustomUser,
    session: Session,
    action: str,
    obj_id: Any,
    title: str,
    changes: dict[str, Any],
) -> None:
    """سطرُ تدقيقٍ بالمعرّفات — `role` هو الدورُ الحاكم للفاعل وقتَه."""
    AuditLog.log(
        user=user,
        action=action,
        model_name="other",
        object_id=obj_id,
        object_repr=f"رصدُ المعلّم — {title}",
        changes={"role": user.get_role(), "session": str(session.pk), **changes},
        school=session.school,
    )


# ══════════════════════════════════════════════════════════════════
# الإدخال
# ══════════════════════════════════════════════════════════════════


def _supersession(
    head: AttendanceEntry | None,
    user: CustomUser,
    status: str,
    minutes: int | None,
    reason: str,
) -> tuple[AttendanceEntry | None, str, AttendanceEntry | None]:
    """يقرّر ما يفعله إدخالٌ جديدٌ فوق الرأس القائم: `(supersedes, reason, idempotent_entry)`."""
    if head is None:
        return None, "", None
    state = state_of(head)
    reason = _checked_reason(reason)
    if state == "pending":
        if (
            head.status == status
            and head.tardiness_minutes == minutes
            and head.entered_by_id == user.id
        ):
            return None, "", head  # نقرةٌ مكرّرة: لا صفَّ جديد (N6)
        default = (
            "تعديلٌ قبل القرار" if head.entered_by_id == user.id else "نسخةُ المعلّم الفعليّ الحاليّ"
        )
        return head, reason or default, None
    if state == "rejected":
        return head, reason or "إعادةُ إدخالٍ بعد الرفض", None
    # approved: التصحيحُ بسببٍ إلزاميّ، وحالةٌ لا تتغيّر ليست تصحيحاً (A9).
    if head.status == status and head.tardiness_minutes == minutes:
        raise EntryError("unchanged", "الحالةُ المعتمَدةُ كما هي — لا تصحيحَ.")
    if not reason:
        raise EntryError("reason_required", "تصحيحُ رصدٍ معتمَدٍ يلزمه سبب.")
    return head, reason, None


@transaction.atomic
def submit_entry(
    user: CustomUser,
    session: Session,
    student: CustomUser,
    status: str,
    *,
    now: dt.datetime | None = None,
    tardiness_minutes: int | None = None,
    correction_reason: str = "",
) -> AttendanceEntry:
    """المعلّمُ الفعليّ يُدخل (أو يصحّح) رصداً لطالبٍ في حصّته.

    شُعبُ الأجنحة: إدخالٌ معلَّقٌ بلا أثرٍ في `StudentAttendance`. والتربيةُ الخاصّة: قرارٌ ذاتيٌّ موسومٌ وكتابةٌ
    فوريّة. وفي كلّ حال: لا فاعلَ ولا وقتَ ولا حالةَ اعتمادٍ من المستدعي — يُحسبان هنا.
    """
    if status not in ENTERABLE_STATUSES:
        raise EntryError("bad_status", "حالةٌ غيرُ مسموحةٍ للإدخال.")
    verdict = can_enter(user, session, student, now=now)
    if not verdict:
        raise EntryRefusedError(verdict.reason)

    minutes = tardiness_minutes if status == "late" else None
    head = head_of(session, student, lock=True)
    supersedes, reason, same = _supersession(head, user, status, minutes, correction_reason)
    if same is not None:
        return same

    try:
        with transaction.atomic():
            entry = AttendanceEntry.objects.create(
                school_id=session.school_id,
                session=session,
                student=student,
                status=status,
                tardiness_minutes=minutes,
                entered_by=user,
                entered_at=now or timezone.now(),
                supersedes=supersedes,
                correction_reason=reason,
            )
    except IntegrityError as exc:
        raise EntryConflictError(
            "concurrent", "إدخالٌ آخرُ سبقك على هذا الطالب — أعِد المحاولة."
        ) from exc

    _audit(
        user,
        session,
        "create",
        entry.pk,
        "إدخالٌ مبدئيّ",
        {
            "status": status,
            "student": str(student.pk),
            "supersedes": str(supersedes.pk) if supersedes else None,
        },
    )

    # رصدُ المعلّم نهائيٌّ دائماً (أمرُ المالك 2026-10-09، W-20261009-003): لا اعتمادَ في المنصّة.
    _decide_directly(entry, user, session)
    return entry


# ══════════════════════════════════════════════════════════════════
# القرار
# ══════════════════════════════════════════════════════════════════


def _apply_to_effective(entry: AttendanceEntry, actor: CustomUser) -> None:
    """يكتب الرصدَ المعتمَدَ في `StudentAttendance` — بلا كتابةٍ فوق رصدٍ بشريٍّ آخر، وبتدقيقٍ عند الاستبدال."""
    session, student = entry.session, entry.student
    row = (
        StudentAttendance.objects.select_for_update()
        .filter(session=session, student=student)
        .first()
    )
    if row is not None and row.source not in OVERWRITABLE_SOURCES:
        raise EntryConflictError(
            "non_teacher_row",
            "رصدٌ آخرُ (مشرفٌ أو عيادةٌ أو بوّابةٌ) قائمٌ على هذا الطالب — لا كتابةَ فوقه.",
        )
    values = {
        "school_id": session.school_id,
        "status": entry.status,
        "source": SOURCE,
        "marked_by": entry.entered_by,
        "late_minutes": entry.tardiness_minutes if entry.status == "late" else None,
    }
    if row is None:
        try:
            with transaction.atomic():
                StudentAttendance.objects.create(session=session, student=student, **values)
        except IntegrityError as exc:
            # لم نجد صفّاً عند القفل فكتب مشرفٌ صفّاً في اللحظة نفسِها فاصطدم القيدُ الفريد — تعارضٌ لا 500.
            raise EntryConflictError(
                "non_teacher_row", "رصدٌ آخرُ كُتب على هذا الطالب للتوّ — لا كتابةَ فوقه."
            ) from exc
        _audit(
            actor,
            session,
            "create",
            entry.pk,
            "اعتمادٌ يكتب الرصدَ المعتمَد",
            {"student": str(student.pk), "after": {"status": entry.status}},
        )
        return

    before = {"status": row.status, "source": row.source, "late_minutes": row.late_minutes}
    for field, value in values.items():
        setattr(row, field, value)
    if entry.status != "absent":
        row.excuse = None
        row.excuse_type = ""
    row.save()
    _audit(
        actor,
        session,
        "update",
        entry.pk,
        "اعتمادٌ يستبدل الرصدَ المعتمَد",
        {
            "student": str(student.pk),
            "before": before,
            "after": {
                "status": entry.status,
                "source": SOURCE,
                "late_minutes": values["late_minutes"],
            },
        },
    )


def _decide_directly(entry: AttendanceEntry, user: CustomUser, session: Session) -> None:
    """رصدٌ نهائيٌّ بلا اعتماد: التربيةُ الخاصّة (D-126م) أو جناحٌ بقرار المالك 2026-10-07 — بأساسٍ صريحٍ يُميّز كلاً منهما."""
    if is_special_education(session.class_group):
        basis = "special_ed_self"
        evidence: dict[str, Any] = {
            "rule": "special_education",
            "section": session.class_group.section,
        }
    else:
        basis = "direct_entry"
        wing = session.class_group.wing
        evidence = {"rule": "direct_wing", "wing": wing.code if wing else ""}
    _decide(entry, user, approve=True, basis=basis, evidence=evidence, reason="")


def _notify_replaced(head: AttendanceEntry, entry: AttendanceEntry, session: Session) -> None:
    """يُخطَر المعلّمُ حين يبدّل غيرُه رصدَه (مشرفُ الجناح): إشعارٌ داخليٌّ لا يُفشل الكتابة."""
    if head.entered_by_id == entry.entered_by_id or head.entered_by_id != session.teacher_id:
        return
    try:
        from notifications.models import InAppNotification

        InAppNotification.objects.create(
            user_id=head.entered_by_id,
            school_id=session.school_id,
            title="عدّل مشرفُ الجناح رصدَك",
            body=f"{entry.student.full_name}: من «{head.status}» إلى «{entry.status}» — الحصّة {session.start_time:%H:%M}.",
            event_type="attendance",
            priority="normal",
            related_url=f"/teacher/classes/{session.class_group_id}/grid/",
        )
    except Exception as exc:  # الإشعارُ لا يُفشل الرصد
        logger.warning("تعذّر إخطارُ المعلّم بتعديل رصدِه [entry=%s]: %s", entry.pk, exc)


def _decide(
    entry: AttendanceEntry,
    user: CustomUser,
    *,
    approve: bool,
    basis: str,
    evidence: dict[str, Any],
    reason: str,
    now: dt.datetime | None = None,
) -> AttendanceDecision:
    if approve:
        _apply_to_effective(entry, user)
    decision = AttendanceDecision.objects.create(
        school_id=entry.school_id,
        entry=entry,
        decision="approved" if approve else "rejected",
        decided_by=user,
        decided_at=now or timezone.now(),
        basis=basis,
        evidence=evidence,
        reason=reason,
    )
    _audit(
        user,
        entry.session,
        "create",
        decision.pk,
        "قرارٌ في إدخالٍ مبدئيّ",
        {
            "entry": str(entry.pk),
            "decision": decision.decision,
            "basis": basis,
            "reason": reason,
            "evidence": evidence,
        },
    )
    return decision


# ══════════════════════════════════════════════════════════════════
# جدولُ الشعبة العموديّ (W-20261006-005) — كتابةُ خليّةٍ بحالةٍ صريحةٍ و`expected_head`
# ══════════════════════════════════════════════════════════════════

#: مصدرُ الإدخال لخليّةٍ كتبها كاتبٌ في الجدول، ولحاضرٍ افتراضيٍّ كتبه الحفظُ لخليّةٍ فارغة (D-240م).
GRID_ORIGIN = "grid"
GRID_DEFAULT_ORIGIN = "grid_default"
#: أسبابٌ ثابتةٌ مركزيّةٌ تحقّق قيدَ `correction_reason` دون احتكاك (لا يكتب المعلّمُ سبباً لتعديلٍ من الجدول).
GRID_EDIT_REASON = "تعديلٌ من جدول الشعبة"
GRID_DEFAULT_FIX_REASON = "تصحيحُ حاضرٍ افتراضيّ"
BULK_SETTLEMENT_REASON = "تسوية جماعية"


class GridConflictError(EntryConflictError):
    """الرأسُ الحاليُّ للخليّة غيرُ ما رآه العميلُ — لا يُكتب شيءٌ، ويحمل الإدخالَ الحاليَّ ليُعرض من كتبه ومتى."""

    def __init__(self, current: AttendanceEntry | None):
        super().__init__("conflict", "غيّر آخرُ هذه الخليّةَ قبل حفظك.")
        self.current = current


@transaction.atomic
def write_grid_cell(
    user: CustomUser,
    session: Session,
    student: CustomUser,
    status: str,
    *,
    minutes: int | None = None,
    expected_head: str = "",
    default_present: bool = False,
    correction_reason: str = "",
    now: dt.datetime | None = None,
) -> tuple[AttendanceEntry, bool]:
    """يكتب خليّةً من جدول الشعبة: إدخالٌ جديدٌ، أو إدخالٌ يصحّح الرأسَ القائم (`supersedes`) بسببٍ ثابت. `(الإدخال، أُنشئ الآن؟)`.

    **الصلاحيةُ ليست هنا**: يفحصها المستدعي (`can_write_grid`) فلا تُخفَّف `can_enter` العامّة. وهنا الذرّيّةُ والتزامن:
    - `expected_head` معرّفُ الرأس الذي رآه العميلُ أو فارغٌ لـ«لا شيء»؛ يختلف الرأسُ الحاليُّ ← `GridConflictError` ولا كتابة.
    - التكرارُ بالمفتاح نفسِه (الرأسُ الحاليُّ بالقيمة المطلوبة نفسِها وكاتبُه المستدعي) لا يُنتج صفّاً ثانياً.
    - الحاضرُ الافتراضيُّ (`default_present`) يُوسَم `origin=grid_default` ولا يكتب فوق خليّةٍ لها رأس.
    """
    if status not in ENTERABLE_STATUSES:
        raise EntryError("bad_status", "حالةٌ غيرُ مسموحةٍ للإدخال.")
    value_minutes = minutes if status == "late" else None
    head = head_of(session, student, lock=True)
    if (
        head is not None
        and head.status == status
        and head.tardiness_minutes == value_minutes
        and head.entered_by_id == user.id
    ):
        return head, False
    if str(head.pk if head else "") != (expected_head or ""):
        raise GridConflictError(head)
    if default_present and head is not None:
        raise GridConflictError(head)

    reason = ""
    if head is not None:
        reason = GRID_DEFAULT_FIX_REASON if head.origin == GRID_DEFAULT_ORIGIN else GRID_EDIT_REASON
        if (correction_reason or "").strip():  # سببٌ كتبه المصحِّحُ بنفسه (D-201م) يغلب النصَّ الثابت
            reason = correction_reason.strip()[:300]
    try:
        with transaction.atomic():
            entry = AttendanceEntry.objects.create(
                school_id=session.school_id,
                session=session,
                student=student,
                status=status,
                tardiness_minutes=value_minutes,
                entered_by=user,
                entered_at=now or timezone.now(),
                supersedes=head,
                correction_reason=reason,
                origin=GRID_DEFAULT_ORIGIN if default_present else GRID_ORIGIN,
            )
    except IntegrityError as exc:
        raise EntryConflictError(
            "concurrent", "إدخالٌ آخرُ سبقك على هذا الطالب — أعِد المحاولة."
        ) from exc

    _audit(
        user,
        session,
        "create",
        entry.pk,
        "إدخالٌ من جدول الشعبة",
        {
            "status": status,
            "student": str(student.pk),
            "supersedes": str(head.pk) if head else None,
            "default_present": default_present,
        },
    )
    _decide_directly(entry, user, session)
    if head is not None:
        _notify_replaced(head, entry, session)
    return entry, True


# ══════════════════════════════════════════════════════════════════
# المحو (PDPPL م.18) — المسارُ الوحيد الذي يحذف من السجلّ
# ══════════════════════════════════════════════════════════════════


def _role_tenant() -> Any:
    """مدرسةُ دور القاعدة الحاليّ (`app_rls_school()`، هويّةُ المستأجِر من الدور لا من سياقٍ يضبطه التطبيق) أو `None`.

    `None` لمالك الجداول/المتميّز (لا مستأجِرَ له فلا يُقيَّد بـRLS) ولقاعدةٍ بلا الدالّة.
    """
    if connection.vendor != "postgresql":
        return None
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regprocedure('public.app_rls_school()') IS NOT NULL")
        if not cursor.fetchone()[0]:
            return None
        cursor.execute("SELECT public.app_rls_school()")
        row = cursor.fetchone()
    return row[0] if row else None


@transaction.atomic
def erase_attendance_ledger(
    student: CustomUser, *, actor: CustomUser | None = None, school: School | None = None
) -> dict[str, int]:
    """يمحو إدخالاتِ طالبٍ وقراراتِها — حقُّ المحو. يضبط علَمَ المحو المحلّيّ في المعاملة (يسمح بالحذف وحدَه
    لا بالتعديل) ويكتب `AuditLog` بالأعداد. **يُستدعى من `ErasureService` وحدَه.**

    **لا يفشل صامتاً تحت RLS** (حكمُ 0105): هويّةُ المستأجِر من دور القاعدة، فدورُ مدرسةٍ غيرِ مدرسة الطلب يرى صفراً
    ويرجع عدّادٌ 0 و«تمّ المحو» والصفوفُ باقية. فيُرفض ابتداءً (`erasure_wrong_tenant`) إن لم يطابق مستأجرُ الدور
    مدرسةَ الطلب، ويُتحقَّق بعد الحذف ألّا يبقى شيءٌ (`erasure_incomplete`) — وكلاهما يُلغي المعاملةَ كلَّها.
    **حدٌّ معلَن:** صفوفُ مدرسةٍ أخرى سُجّل فيها الطالبُ قبل نقله لا يراها هذا الدور أصلاً، فلا يمحوها ولا يعدّها؛
    محوُها يُنفَّذ بدور تلك المدرسة.
    """
    tenant = _role_tenant()
    if tenant is not None and school is not None and str(tenant) != str(school.pk):
        raise EntryError(
            "erasure_wrong_tenant",
            f"دورُ القاعدة الحاليّ لمدرسةٍ غيرِ مدرسة «{school.name}» التي قُدّم فيها طلبُ المحو — يُنفَّذ بدور مدرستها",
        )
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config(%s, 'on', true)", [ERASURE_FLAG])
    try:
        decisions = AttendanceDecision.objects.filter(entry__student=student)._erase()
        entries = AttendanceEntry.objects.filter(student=student)._erase()
    finally:
        # `set_config(..., true)` محلّيٌّ في المعاملة **الخارجيّة**: إن استُدعيت الدالّةُ داخل معاملةٍ أكبر
        # (طلبٌ أو اختبار) بقي العلَمُ مفتوحاً لما بعدها. فيُغلق صراحةً عند الخروج.
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config(%s, '', true)", [ERASURE_FLAG])
    if (
        AttendanceEntry.objects.filter(student=student).exists()
        or AttendanceDecision.objects.filter(entry__student=student).exists()
    ):
        raise EntryError("erasure_incomplete", "بقيت صفوفٌ بعد المحو — أُلغيت المعاملة.")
    counts = {"decisions": decisions, "entries": entries}
    if decisions or entries:
        AuditLog.log(
            user=actor,
            action="delete",
            model_name="other",
            object_id=student.pk,
            object_repr="رصدُ المعلّم — محوُ سجلّ طالبٍ (PDPPL م.18)",
            changes=counts,
            school=school,
        )
    return counts


def teacher_marked_absent(session: Session, student: CustomUser) -> bool:
    """هل وسمه معلّمُ الحصّة غائباً (إدخالٌ مبدئيّ)؟ — لمنع فتح خروجٍ لغائبٍ (غائبٌ وخروجٌ لا يجتمعان). رصدُ المشرف لا يمنع."""
    return AttendanceEntry.objects.filter(
        session=session, student=student, status="absent", superseded_by__isnull=True
    ).exists()


@transaction.atomic
def settle_pending_as_direct(school: School, *, apply: bool = False) -> int:
    """عند تحويل جناحٍ إلى الرصد النهائيّ: ما بقي معلَّقاً من إدخالاتٍ سابقةٍ يُقرَّر نهائيّاً بقرارٍ مسجَّلٍ باسم كاتبه (أساسُ `direct_entry`، دليلُه تسويةٌ جماعيّة).

    `apply=False` يعدّ ولا يكتب. يعيد عددَ الإدخالات.
    """
    pending = (
        AttendanceEntry.objects.filter(
            school=school, decision__isnull=True, superseded_by__isnull=True
        )
        .select_related("session__class_group__wing", "entered_by", "student")
        .order_by("entered_at")
    )
    settled = 0
    wings: set[str] = set()
    for entry in pending:
        if apply:
            with transaction.atomic():
                _decide(
                    entry,
                    entry.entered_by,
                    approve=True,
                    basis="direct_entry",
                    evidence={"rule": "direct_wing", "bulk_settlement": True},
                    reason=BULK_SETTLEMENT_REASON,
                )
                wings.add(getattr(entry.session.class_group.wing, "code", "") or "")
        settled += 1
    if apply and settled:
        # القرارُ يُسجَّل باسم كاتب الإدخال، فسطرُ التدقيق هذا هو الأثرُ على **من شغّل التسوية**: المدرسةُ والعددُ والأجنحةُ والوقتُ بلا أسماء (ملاحظة 0104)
        AuditLog.log(
            user=None,
            action="update",
            model_name="other",
            object_id=school.pk,
            object_repr="تسويةٌ جماعيّةٌ لإدخالاتٍ معلَّقةٍ — رصدٌ نهائيّ",
            changes={
                "settled": settled,
                "wings": sorted(wings),
                "at": timezone.now().isoformat(timespec="seconds"),
            },
            school=school,
        )
    return settled

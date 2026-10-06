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
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from core.models import AuditLog

from .attendance_policy import (
    approval_evidence,
    approval_holder,
    can_approve,
    can_correct,
    can_enter,
    holder_gap,
    needs_approval,
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


#: أساسُ قرار القيادة بحسب سببِ غياب الحامل الفعليّ (`attendance_policy.holder_gap`).
_LEADERSHIP_BASIS = {
    "no_holder": "leadership_no_holder",
    "holder_is_teacher": "leadership_holder_is_teacher",
    "holder_inactive": "leadership_holder_inactive",
}


def _decision_basis(user: CustomUser, session: Session, gap: str | None) -> str:
    """أساسُ الصلاحيّة المحفوظُ مع القرار: حاصرُ الغياب العامّ ليس حاملَ الجناح ولا القيادة، فيُسمّى باسمه."""
    from wings.services import holds_school_wide

    holder = approval_holder(session)
    if holds_school_wide(user) and not (holder is not None and holder.id == user.id):
        return "school_wide"
    return "wing_holder" if gap is None else _LEADERSHIP_BASIS[gap]


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


@dataclass(frozen=True)
class PendingRow:
    """سطرُ تقرير «غيرُ معتمَد بعد X ساعة»."""

    entry: AttendanceEntry
    age_hours: float
    holder_missing: bool
    #: سببُ غياب الحامل الفعليّ (`no_holder` | `holder_is_teacher` | `holder_inactive`) أو `None`.
    holder_gap: str | None = None


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


def pending_entries(session: Session) -> list[AttendanceEntry]:
    """الإدخالاتُ المعلَّقةُ في حصّة: رؤوسٌ بلا قرار — «بانتظار الاعتماد»."""
    return list(
        AttendanceEntry.objects.filter(
            session=session, superseded_by__isnull=True, decision__isnull=True
        ).select_related("student", "entered_by")
    )


def unapproved_report(
    school: School, *, older_than_hours: float, now: dt.datetime | None = None
) -> list[PendingRow]:
    """تقريرُ النائب: إدخالاتٌ معلَّقةٌ مضى عليها أكثرُ من `older_than_hours` ساعة. قراءةٌ فقط، لمدرسةٍ واحدة.

    و`holder_missing` يرفع الحالةَ التي لا حاملَ فيها للجناح (تعتمدها القيادةُ) — ومنها شعبةٌ عاديّةٌ بجناحٍ
    لم يُسند خطأً — فلا يصل التنبيهُ المعلّمَ وحدَه بل من يتصرّف فيه.
    """
    moment = now or timezone.now()
    cutoff = moment - dt.timedelta(hours=older_than_hours)
    entries = (
        AttendanceEntry.objects.filter(
            school=school,
            superseded_by__isnull=True,
            decision__isnull=True,
            entered_at__lte=cutoff,
        )
        .select_related("session__class_group__wing", "student", "entered_by")
        .order_by("entered_at")
    )
    rows = []
    for entry in entries:
        gap = holder_gap(entry.session)
        rows.append(
            PendingRow(
                entry=entry,
                age_hours=(moment - entry.entered_at).total_seconds() / 3600,
                holder_missing=gap is not None,
                holder_gap=gap,
            )
        )
    return rows


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

    if not needs_approval(session):
        _decide(
            entry,
            user,
            approve=True,
            basis="special_ed_self",
            evidence={"rule": "special_education", "section": session.class_group.section},
            reason="",
        )
    elif session.class_group.wing_id is None:
        logger.warning(
            "إدخالُ رصدٍ مبدئيٍّ لشعبةٍ عاديّةٍ بلا جناح (يعتمده القيادةُ): class_group=%s",
            session.class_group_id,
        )
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


@transaction.atomic
def decide_entry(
    user: CustomUser,
    entry: AttendanceEntry,
    approve: bool,
    *,
    reason: str = "",
    now: dt.datetime | None = None,
) -> tuple[AttendanceDecision, bool]:
    """حاملُ الجناح (أو القيادةُ حين لا حامل) يعتمد الإدخالَ أو يرفضه. يعيد `(القرار، أُنشئ الآن؟)`.

    قفلُ صفّ الإدخال يُسلسل القرارَين المتزامنَين، والثاني يجد القرارَ قائماً فيعيده بلا أثر. والأهليّةُ تُقيَّم داخل
    القفل لا قبله. والاعتمادُ الذي يصطدم برصدٍ بشريٍّ آخر يرفع `EntryConflictError` فتُلغى المعاملةُ كلُّها ويبقى معلَّقاً.
    """
    locked = (
        AttendanceEntry.objects.select_for_update(of=("self",))
        .select_related("session__class_group__wing", "session__school", "entered_by", "student")
        .get(pk=entry.pk)
    )
    existing = AttendanceDecision.objects.filter(entry=locked).first()
    if existing is not None:
        return existing, False
    if AttendanceEntry.objects.filter(supersedes_id=locked.pk).exists():
        raise EntryError("superseded", "حلّت محلَّه نسخةٌ أحدث — القرارُ على الأحدث.")

    session = locked.session
    verdict = can_approve(user, session, entered_by=locked.entered_by)
    if not verdict:
        raise EntryRefusedError(verdict.reason)

    reason = _checked_reason(reason)
    if not approve and not reason:
        raise EntryError("reason_required", "الرفضُ يلزمه سبب.")

    gap = holder_gap(session)
    decision = _decide(
        locked,
        user,
        approve=approve,
        basis=_decision_basis(user, session, gap),
        evidence=approval_evidence(session),
        reason=reason,
        now=now,
    )
    return decision, True


@transaction.atomic
def settle_before_supervisor_write(
    session: Session,
    student: CustomUser,
    supervisor: CustomUser,
    *,
    new_status: str,
    now: dt.datetime | None = None,
) -> None:
    """يُسوّي أثرَ رصدِ المعلّم قبل أن يكتب المشرفُ فوقه (A11، حكمُ 0105): لا استبدالَ صامتاً.

    - إدخالٌ مبدئيٌّ معلَّق: يبقى كما كتبه المعلّمُ (سجلٌّ ملحقٌ فقط) ويُلحَق به قرارٌ مسبَّبٌ بفاعله
      (`basis=supervisor_record`) فلا يبقى معلَّقاً إلى أن يصطدم اعتمادُه بـ`non_teacher_row`.
    - رصدٌ مصدرُه المعلّم (`teacher` المعتمَد أو نقرةُ `teacher_late`): سطرُ تدقيقٍ بقبلٍ وبعد.
    تُستدعى قبل كتابة المشرف في الدالّة نفسِها وضمن معاملتها.
    """
    row = (
        StudentAttendance.objects.select_for_update()
        .filter(session=session, student=student)
        .first()
    )
    if row is not None and row.source in OVERWRITABLE_SOURCES:
        _audit(
            supervisor,
            session,
            "update",
            row.pk,
            "تثبيتُ مشرفٍ يستبدل رصدَ معلّم",
            {
                "student": str(student.pk),
                "before": {
                    "status": row.status,
                    "source": row.source,
                    "late_minutes": row.late_minutes,
                },
                "after": {"status": new_status, "source": "supervisor"},
            },
        )
    head = head_of(session, student, lock=True)
    if head is None or AttendanceDecision.objects.filter(entry=head).exists():
        return
    _decide(
        head,
        supervisor,
        approve=False,
        basis="supervisor_record",
        evidence=approval_evidence(session),
        reason=f"كُتب رصدُ مشرفٍ على هذا الطالب في الحصّة ({new_status}) فسقط الإدخالُ المبدئيّ",
        now=now,
    )


#: أنواعُ الدليل لتصحيحٍ دون معاينة — لا تصحيحَ بلا نوعٍ منها وسبب.
EVIDENCE_TYPES = {
    "parent_contact": "اتّصالُ وليّ الأمر",
    "gate_log": "سجلُّ البوّابة",
    "clinic_record": "سجلُّ العيادة",
    "staff_statement": "إفادةُ موظّفٍ آخر",
    "document": "مستندٌ",
}

#: مصادرُ يصحّحها المشرفُ — وما سواها (عيادةٌ وبوّابةٌ ونظامٌ) رصدٌ آخرُ لا يُكتب فوقه.
CORRECTABLE_SOURCES = OVERWRITABLE_SOURCES | {"supervisor"}


@transaction.atomic
def correct_without_observation(
    user: CustomUser,
    session: Session,
    student: CustomUser,
    status: str,
    *,
    reason: str,
    evidence_type: str,
    now: dt.datetime | None = None,
) -> StudentAttendance:
    """يصحّح المشرفُ (أو القيادةُ حين لا حاملَ) رصداً لم يشاهده — بسببٍ ونوعِ دليلٍ ووسمٍ وتدقيق.

    يُسقط الإدخالَ المبدئيَّ المعلَّقَ بقرارٍ مسبَّب (`settle_before_supervisor_write`) ثمّ يكتب الرصدَ المعتمَدَ مصدرُه المشرفُ
    موسوماً `unobserved_correction` ويدوّن قبلَه. ولا يكتب فوق رصدٍ مصدرُه العيادةُ أو البوّابة.
    """
    if status not in ENTERABLE_STATUSES:
        raise EntryError("bad_status", "حالةٌ غيرُ مسموحة.")
    verdict = can_correct(user, session)
    if not verdict:
        raise EntryRefusedError(verdict.reason)
    reason = _checked_reason(reason)
    if not reason:
        raise EntryError("reason_required", "تصحيحٌ دون معاينةٍ يلزمه سببٌ.")
    if evidence_type not in EVIDENCE_TYPES:
        raise EntryError("bad_evidence", "نوعُ الدليل غيرُ معروف.")

    row = (
        StudentAttendance.objects.select_for_update()
        .filter(session=session, student=student)
        .first()
    )
    if row is not None and row.source not in CORRECTABLE_SOURCES:
        raise EntryConflictError(
            "non_correctable_row",
            "الرصدُ القائمُ مصدرُه العيادةُ أو البوّابةُ أو النظام — لا كتابةَ فوقه.",
        )
    settle_before_supervisor_write(session, student, user, new_status=status, now=now)
    before = {"status": row.status if row else None, "source": row.source if row else None}
    moment = now or timezone.now()
    tag = {
        "type": evidence_type,
        "reason": reason,
        "by": str(user.pk),
        "at": moment.isoformat(),
        "before": before,
    }
    if row is None:
        row = StudentAttendance(session=session, student=student, school_id=session.school_id)
    row.status = status
    row.source = "supervisor"
    row.marked_by = user
    row.late_minutes = row.late_minutes if status == "late" else None
    row.unobserved_correction = tag
    if status != "absent":
        row.excuse = None
        row.excuse_type = ""
    try:
        with transaction.atomic():
            row.save()
    except IntegrityError as exc:
        # صفٌّ لم نجده عند القفل كُتب في اللحظة نفسِها فاصطدم القيدُ الفريد — تعارضٌ لا 500.
        raise EntryConflictError(
            "concurrent", "رصدٌ آخرُ كُتب على هذا الطالب للتوّ — أعِد المحاولة."
        ) from exc
    _audit(
        user,
        session,
        "update",
        row.pk,
        "تصحيحٌ دون معاينة",
        {
            "student": str(student.pk),
            "before": before,
            "after": {"status": status, "source": "supervisor"},
            "evidence_type": evidence_type,
            "reason": reason,
        },
    )
    return row


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
        session=session, student=student, status="absent"
    ).exists()

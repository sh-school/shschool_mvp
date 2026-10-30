"""توليدُ اقتراحات المخالفة 1-01 واعتمادُها وردُّها (W-20261013-034، قراراتُ المالك 1–5 في 2026-10-13).

- **المقترَح**: مداومٌ (أتمّ `MIN_PERIODS_FOR_PRESENCE` حصصٍ مثبَّتةً حضوراً) غاب حصّةً بلا عذرٍ ولا إذن،
  أو دخل متأخّراً أكثر من خمس دقائق بعد أن حضر حصّةً سبقتها. وما يُنشئه الرصدُ آلياً (2-02 و3-10) يُستثنى، ولا يُمسّ
  التأخّرُ الصباحيّ: الحصّةُ الأولى الحاضرة ليست «بين الحصص».
- **اقتراحٌ واحدٌ لكلّ طالبٍ في اليوم** (القيدُ الفريد طالب+يوم+نوع)، تُجمع فيه الحصصُ في ملاحظته.
- **الظهور**: بعد انقضاء مهلة العذر (`GRACE_DAYS` أيامٍ دراسيّة من يوم الواقعة، فلا «عودة» للمداوم) لا فور الرصد.
- **السحب**: يُعاد الحكمُ على غير المعتمَد مع كلّ توليد؛ فعذرٌ قُبل (في المهلة أو بعدها) أو تصحيحٌ للرصد يسحب المقترحَ،
  وما اعتُمد أو رُدَّ لا يُمسّ.
- **الاعتماد**: مخالفةٌ 1-01 عبر `BehaviorService.create_infraction` وحدَها — بلا نقاطٍ ولا قرارٍ ولا إرسالٍ لوليّ الأمر (D-272م).
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from core.audit_repr import masked_repr
from core.models import AuditLog, ClassGroup, CustomUser, School
from operations.absence_policy import MIN_PERIODS_FOR_PRESENCE
from operations.day_attendance import SOURCE, enrolled_of
from operations.excuses import GRACE_DAYS
from operations.models import StudentAttendance
from operations.period_register import ATTENDED, AWAY_WITH_LEAVE, escapes_for, periods_of
from operations.school_days import SchoolDays, is_school_day, student_grade
from operations.tardiness import is_period_tardy

from .models import ConductProposal

logger = logging.getLogger(__name__)

#: كم يوماً تقويميّاً يُنظر إليه إلى الوراء عند التوليد — ما قبله لا يُقترح له (مخالفةٌ متقادمة).
LOOKBACK_DAYS = 21
RULE_CODE = "1-01"


class ProposalError(ValueError):
    """رفضٌ بسببٍ يُعرض للمشرف كما هو."""


@dataclass
class _Day:
    absent: set = field(default_factory=set)
    tardy: set = field(default_factory=set)
    labels: dict = field(default_factory=dict)


def visible_after(school: School, day: dt.date, grade: str | None) -> dt.date:
    """آخرُ يومٍ تُقبل فيه الأعذارُ للمداوم: ثاني يومٍ دراسيٍّ بعد يوم الواقعة. يظهر الاقتراحُ بعده."""
    window = SchoolDays(school, day, day + dt.timedelta(days=60), grade)
    return window.grace_after(day, GRACE_DAYS)


def _rows(klass: ClassGroup, day: dt.date) -> dict:
    """ما رصده المشرفُ: `{student_id: {start: (status, where, late_minutes)}}` — الأفضلُ في خانتَي الزوج."""
    rank = {"present": 3, "late": 2, "excused": 1, "absent": 0}
    rows = StudentAttendance.objects.filter(
        session__class_group=klass, session__date=day, source=SOURCE
    ).values_list(
        "student_id",
        "session__start_time",
        "status",
        "whereabouts",
        "late_minutes",
        "excuse_type",
        "excuse_id",
        "tardiness_excuse__id",
    )
    cells: dict = {}
    for sid, start, status, where, minutes, excuse_type, excuse_id, tardy_excuse in rows:
        if status == "absent" and (excuse_type or excuse_id):
            status = "excused"
        if status == "late" and tardy_excuse is not None:
            status, minutes = "present", None
        own = cells.setdefault(sid, {})
        cur = own.get(start)
        if cur is None or rank.get(status, 0) > rank.get(cur[0], 0):
            own[start] = (status, where, minutes)
    return cells


def _judge(track: list, tardy_minutes: dict) -> tuple[set, set]:
    """(خاناتُ الغياب، خاناتُ التأخّر) المقترحةُ ليومٍ واحد — فارغتان لمن لم يُتمّ حصصَ الحضور."""
    if sum(1 for _, status, _ in track if status in ATTENDED) < MIN_PERIODS_FOR_PRESENCE:
        return set(), set()
    in_class, in_school = escapes_for(track)
    taken = in_class | in_school
    absent = {
        start
        for start, status, where in track
        if status == "absent" and where not in AWAY_WITH_LEAVE and start not in taken
    }
    tardy: set = set()
    seen = False
    for start, status, _ in track:
        if status == "late" and seen and is_period_tardy(tardy_minutes.get(start)):
            tardy.add(start)
        if status in ATTENDED:
            seen = True
    return absent, tardy


def evaluate_day(school: School, day: dt.date) -> dict:
    """`{student_id: _Day}` لمن يستحقّ اقتراحاً في `day`، من الرصد المثبَّت وحدَه."""
    found: dict = {}
    groups = ClassGroup.objects.filter(school=school, is_active=True).order_by("grade", "section")
    for klass in groups:
        periods = periods_of(klass, day)
        confirmed = {p.start for p in periods if p.confirmation is not None}
        if len(confirmed) < MIN_PERIODS_FOR_PRESENCE:
            continue
        cells = _rows(klass, day)
        by_start = {p.start: p for p in periods}
        for enrollment in enrolled_of(klass, day):
            own = cells.get(enrollment.student_id, {})
            track = []
            for p in periods:
                cell = own.get(p.start) if p.start in confirmed else None
                track.append((p.start, cell[0] if cell else "", cell[1] if cell else ""))
            minutes = {start: cell[2] for start, cell in own.items()}
            absent, tardy = _judge(track, minutes)
            if not absent and not tardy:
                continue
            entry = found.setdefault(enrollment.student_id, _Day())
            entry.absent |= absent
            entry.tardy |= tardy
            for start in absent | tardy:
                entry.labels[start] = by_start[start].subjects
    return found


def _note(entry: _Day) -> str:
    parts = []
    if entry.absent:
        parts.append(
            "غياب: " + "، ".join(f"{s:%H:%M} {entry.labels[s]}" for s in sorted(entry.absent))
        )
    if entry.tardy:
        parts.append(
            "تأخّر: " + "، ".join(f"{s:%H:%M} {entry.labels[s]}" for s in sorted(entry.tardy))
        )
    return " — ".join(parts)


def _shape(entry: _Day) -> tuple[str, list[str], str]:
    """النوعُ والخاناتُ والملاحظة؛ اليومُ بغيابٍ ينتمي إلى «غياب» ويحمل تأخّرَه في الملاحظة (مخالفةٌ واحدةٌ لليوم)."""
    kind = "absence" if entry.absent else "tardy"
    starts = sorted(entry.absent | entry.tardy)
    return kind, [f"{s:%H:%M}" for s in starts], _note(entry)


def generate_for_day(school: School, day: dt.date) -> dict[str, int]:
    """يجعل اقتراحات `day` غيرَ المقرَّرة مطابقةً للرصد الآن — يُنشئ الناقصَ ويحدّث ويسحب. ثابتُ التكرار."""
    found = evaluate_day(school, day)
    stats = {"created": 0, "updated": 0, "withdrawn": 0}
    existing = {
        (p.student_id, p.kind): p for p in ConductProposal.objects.filter(school=school, date=day)
    }
    wanted: set = set()
    students = {u.pk: u for u in CustomUser.objects.filter(pk__in=found.keys())}
    for sid, entry in found.items():
        kind, starts, note = _shape(entry)
        wanted.add((sid, kind))
        current = existing.get((sid, kind))
        if current is None:
            ConductProposal.objects.create(
                school=school, student=students[sid], date=day, kind=kind, periods=starts, note=note
            )
            stats["created"] += 1
        elif current.status in ("proposed", "withdrawn") and (
            current.periods != starts or current.note != note or current.status == "withdrawn"
        ):
            current.periods, current.note, current.status = starts, note, "proposed"
            current.save(update_fields=["periods", "note", "status"])
            stats["updated"] += 1
    for key, proposal in existing.items():
        if key not in wanted and proposal.status == "proposed":
            proposal.status = "withdrawn"
            proposal.save(update_fields=["status"])
            stats["withdrawn"] += 1
    return stats


def generate_due(school: School, today: dt.date | None = None) -> dict[str, int]:
    """كلُّ الأيام الدراسيّة الأخيرة التي انقضت مهلتُها ولم يمض عليها `LOOKBACK_DAYS` — يوماً يوماً."""
    today = today or timezone.localdate()
    total = {"created": 0, "updated": 0, "withdrawn": 0, "days": 0}
    for back in range(1, LOOKBACK_DAYS + 1):
        day = today - dt.timedelta(days=back)
        if not is_school_day(school, day):
            continue
        # المهلةُ هنا عامّةٌ على الصفوف؛ ومهلةُ صفٍّ بإجازةٍ خاصّةٍ تُعاد في العرض (`is_visible`) لا هنا.
        if visible_after(school, day, None) >= today:
            continue
        for key, value in generate_for_day(school, day).items():
            total[key] += value
        total["days"] += 1
    return total


def is_visible(proposal: ConductProposal, today: dt.date | None = None) -> bool:
    """هل انقضت مهلةُ العذر بحساب صفّ الطالب؟ قبلها لا يراه المشرفُ ولا يعتمده."""
    today = today or timezone.localdate()
    grade = student_grade(proposal.student, proposal.school)
    return today > visible_after(proposal.school, proposal.date, grade)


def queue_for(school: School, scope, today: dt.date | None = None) -> list[ConductProposal]:
    """اقتراحاتُ طلبة جناح المشرف التي حلّ وقتُها، الأقدمُ أولاً."""
    today = today or timezone.localdate()
    qs = scope.narrow(
        ConductProposal.objects.filter(
            school=school, status="proposed", date__lt=today
        ).select_related("student", "school"),
        "student_id",
    ).order_by("date", "student__full_name")
    return [p for p in qs if is_visible(p, today)]


def _category():
    from behavior.models import ViolationCategory

    return ViolationCategory.objects.filter(code=RULE_CODE, is_active=True).first()


@transaction.atomic
def approve(proposal_id, by: CustomUser, scope, today: dt.date | None = None) -> ConductProposal:
    """اعتمادُ المشرف: مخالفةٌ 1-01 بلا نقاطٍ ولا قرارٍ ولا إرسال؛ والاعتمادُ الثاني يُرجع الأولَ بلا تكرار."""
    from behavior.conduct_2026 import BY_CODE
    from behavior.services import BehaviorService

    proposal = _lock(proposal_id, by, scope, today)
    if proposal.status == "approved":
        return proposal
    if proposal.status == "rejected":
        raise ProposalError("رُدَّ هذا الاقتراحُ من قبل.")
    category = _category()
    if category is None:
        raise ProposalError("بندُ المخالفة 1-01 غيرُ مفعَّلٍ في هذه المدرسة.")
    row = None
    if proposal.periods:
        row = (
            StudentAttendance.objects.filter(
                student=proposal.student,
                session__date=proposal.date,
                session__start_time=dt.time.fromisoformat(proposal.periods[0]),
            )
            .select_related("session")
            .first()
        )
    kind = dict(ConductProposal.KINDS)[proposal.kind]
    infraction = BehaviorService.create_infraction(
        school=proposal.school,
        student=proposal.student,
        reporter=by,
        level=BY_CODE[RULE_CODE].degree,
        description=f"{kind} بتاريخ {proposal.date:%Y-%m-%d} — {proposal.note}",
        violation_category=category,
        session=row.session if row else None,
    )
    proposal.status, proposal.decided_by, proposal.decided_at = "approved", by, timezone.now()
    proposal.infraction = infraction
    proposal.save(update_fields=["status", "decided_by", "decided_at", "infraction"])
    _audit(by, proposal, "approved")
    return proposal


@transaction.atomic
def reject(proposal_id, by: CustomUser, scope, today: dt.date | None = None) -> ConductProposal:
    proposal = _lock(proposal_id, by, scope, today)
    if proposal.status == "rejected":
        return proposal
    if proposal.status == "approved":
        raise ProposalError("اعتُمد هذا الاقتراحُ من قبل.")
    proposal.status, proposal.decided_by, proposal.decided_at = "rejected", by, timezone.now()
    proposal.save(update_fields=["status", "decided_by", "decided_at"])
    _audit(by, proposal, "rejected")
    return proposal


def _lock(proposal_id, by: CustomUser, scope, today: dt.date | None) -> ConductProposal:
    proposal = (
        ConductProposal.objects.select_for_update(of=("self",))
        .select_related("student", "school")
        .filter(pk=proposal_id, school=by.get_school())
        .first()
    )
    if proposal is None or not scope.covers_student(proposal.student_id):
        raise ProposalError("الاقتراحُ غيرُ موجودٍ في جناحك.")
    if proposal.status in ("approved", "rejected"):
        return proposal
    if proposal.status != "proposed":
        raise ProposalError("سُحب هذا الاقتراحُ لزوال سببه.")
    if not is_visible(proposal, today):
        raise ProposalError("لم تنقضِ مهلةُ العذر بعد.")
    return proposal


def _audit(user: CustomUser, proposal: ConductProposal, action: str) -> None:
    AuditLog.log(
        user=user,
        action="update",
        model_name="other",
        object_id=proposal.pk,
        object_repr=masked_repr(proposal),
        changes={"conduct_proposal": action, "kind": proposal.kind},
        school=proposal.school,
    )

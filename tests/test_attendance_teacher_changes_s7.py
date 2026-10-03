"""كلُّ مسارٍ يغيّر معلّمَ الحصّة يكتب `Session.teacher` عند التنفيذ وحدَه، فيرث الجديدُ صلاحيّةَ الرصد (S3/S7 — W-020).

المعلّمُ الفعليّ للحصّة هو `Session.teacher` وحدَه (D-125م). فلو كتب مسارٌ حقلاً آخر أو كتب قبل التنفيذ ضاعت الصلاحيّةُ أو
تسرّبت. والمساراتُ التي تكتبه — وكلُّها عبر `Session.teacher` لا عبر حقلٍ مواز:

1. **الإشغال = التغطية** (شيءٌ واحد): `SubstituteService.assign_substitute` ← `hand_over_session`. الغيابُ وحدَه لا يغيّر شيئاً.
2. **التبديل**: `SwapService.execute_swap` (مباشرةً `force_swap`، أو بموافقة المنسّق)؛ الطلبُ المعلَّق أو المرفوضُ لا أثرَ له.
3. **تبديل الغياب** (`absence_swap.py`): يمرّ إلى التنفيذ نفسِه `execute_swap` — بتنفيذ القيادة الفوريّ أو باعتماد النائب؛ ورفضُه لا يغيّر.
4. **التعويض**: `CompensatoryService.approve_compensatory` ← `_take`؛ والطلبُ قبل الاعتماد لا يغيّر، والإلغاءُ يُعيد الحصّةَ لصاحبها.

وفي كلٍّ: الجديدُ يُدخل (`can_enter`) والأصليُّ يُرفض بـ`not_teacher`، ورصدُ الأصليّ قبل التنفيذ يبقى في السجلّ (S5).
"""

import datetime as dt

import pytest
from django.core.management import call_command

from core.models import TimeBand
from operations.attendance_entries import submit_entry
from operations.attendance_policy import can_enter
from operations.models import (
    CompensatorySession,
    ScheduleSlot,
    Session,
    Subject,
    TeacherAbsence,
    TeacherSwap,
)
from operations.services import CompensatoryService, ScheduleService, SubstituteService
from operations.services.absence_swap import AbsenceSwapService
from operations.services.swap import SwapService
from tests.attendance_fixtures import _staff, at
from tests.conftest import ClassGroupFactory, StudentEnrollmentFactory, UserFactory

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"
SUNDAY = dt.date(2026, 10, 11)
MONDAY = dt.date(2026, 10, 12)
THURSDAY = dt.date(2026, 10, 15)
TODAY = dt.date(2026, 10, 6)


@pytest.fixture
def world(school, seeded_calendar, monkeypatch, principal_user):
    from django.utils import timezone

    # التعويضُ لا يقع في الماضي، وتواريخُ التقويم المبذور ثابتة: يومُ الاختبار مثبَّت.
    monkeypatch.setattr(timezone, "localdate", lambda *a, **k: TODAY)
    call_command("seed_time_bands")
    bands = {b.code: b for b in TimeBand.objects.filter(school=school)}
    klass = ClassGroupFactory(
        school=school,
        grade="G10",
        level_type="sec",
        academic_year=YEAR,
        time_band=bands["secondary"],
    )
    kid = UserFactory(full_name="طالب", national_id="29000004001")
    StudentEnrollmentFactory(student=kid, class_group=klass, enrolled_at=dt.date(2026, 9, 1))
    return {
        "school": school,
        "klass": klass,
        "kid": kid,
        "subject": Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT"),
        "a": _staff(school, "teacher", "المعلّم أ", "29000004010"),
        "b": _staff(school, "teacher", "المعلّم ب", "29000004011"),
        "principal": principal_user,
    }


def _slot(world, teacher, day, period, start, end):
    return ScheduleSlot.objects.create(
        school=world["school"],
        teacher=teacher,
        class_group=world["klass"],
        subject=world["subject"],
        day_of_week=day,
        period_number=period,
        start_time=start,
        end_time=end,
        academic_year=YEAR,
        is_active=True,
    )


def _lesson(world, day, start):
    return Session.objects.get(
        school=world["school"], class_group=world["klass"], date=day, start_time=start
    )


def _inherits(world, lesson, new, old, *, moment):
    """الجديدُ يُدخل والأصليُّ يُرفض، والحقلُ الوحيد هو `Session.teacher`."""
    lesson.refresh_from_db()
    assert lesson.teacher_id == new.id
    assert can_enter(new, lesson, world["kid"], now=moment)
    assert can_enter(old, lesson, world["kid"], now=moment).reason == "not_teacher"


# ══════════════════════════════════════════════════════════════════
# 1) الإشغال = التغطية
# ══════════════════════════════════════════════════════════════════


def test_s7_an_absence_alone_changes_no_teacher_and_the_occupancy_does(world):
    slot = _slot(world, world["a"], 0, 5, dt.time(10, 50), dt.time(11, 35))
    absence = SubstituteService.register_absence(world["school"], world["a"], SUNDAY, "sick")
    assert not Session.objects.filter(date=SUNDAY, teacher=world["b"]).exists()

    SubstituteService.assign_substitute(absence, slot, world["b"], world["principal"])
    lesson = _lesson(world, SUNDAY, dt.time(10, 50))
    assert lesson.original_teacher_id == world["a"].id
    _inherits(world, lesson, world["b"], world["a"], moment=at(11, 0, day=SUNDAY))


def test_s5_the_original_teachers_entry_before_the_occupancy_stays_and_the_substitute_adds_a_version(
    world,
):
    slot = _slot(world, world["a"], 0, 5, dt.time(10, 50), dt.time(11, 35))
    SubstituteService.hand_over_session(world["school"], slot, SUNDAY, world["a"])
    lesson = _lesson(world, SUNDAY, dt.time(10, 50))
    first = submit_entry(world["a"], lesson, world["kid"], "absent", now=at(11, 0, day=SUNDAY))

    absence = SubstituteService.register_absence(world["school"], world["a"], SUNDAY, "sick")
    SubstituteService.assign_substitute(absence, slot, world["b"], world["principal"])
    lesson.refresh_from_db()

    second = submit_entry(
        world["b"],
        lesson,
        world["kid"],
        "present",
        now=at(11, 10, day=SUNDAY),
        correction_reason="",
    )
    assert second.supersedes_id == first.pk
    first.refresh_from_db()
    assert first.status == "absent"


# ══════════════════════════════════════════════════════════════════
# 2) التبديل
# ══════════════════════════════════════════════════════════════════


def _two_slots(world):
    slot_a = _slot(world, world["a"], 0, 5, dt.time(10, 50), dt.time(11, 35))
    slot_b = _slot(world, world["b"], 1, 5, dt.time(10, 50), dt.time(11, 35))
    return slot_a, slot_b


def test_s7_a_pending_swap_changes_no_teacher(world):
    slot_a, slot_b = _two_slots(world)
    TeacherSwap.objects.create(
        school=world["school"],
        teacher_a=world["a"],
        teacher_b=world["b"],
        slot_a=slot_a,
        slot_b=slot_b,
        swap_date_a=SUNDAY,
        swap_date_b=MONDAY,
        swap_type="cross_day",
        status="pending_b",
        requested_by=world["a"],
    )
    SubstituteService.hand_over_session(world["school"], slot_a, SUNDAY, world["a"])
    lesson = _lesson(world, SUNDAY, dt.time(10, 50))
    assert lesson.teacher_id == world["a"].id
    assert can_enter(world["a"], lesson, world["kid"], now=at(11, 0, day=SUNDAY))


def test_s7_a_forced_swap_hands_both_lessons_over_after_execution(world):
    slot_a, slot_b = _two_slots(world)
    swap = SwapService.force_swap(
        world["school"],
        world["a"],
        world["b"],
        slot_a,
        slot_b,
        SUNDAY,
        MONDAY,
        world["principal"],
        reason="س7",
    )
    assert swap.status == "executed"
    _inherits(
        world,
        _lesson(world, SUNDAY, dt.time(10, 50)),
        world["b"],
        world["a"],
        moment=at(11, 0, day=SUNDAY),
    )
    _inherits(
        world,
        _lesson(world, MONDAY, dt.time(10, 50)),
        world["a"],
        world["b"],
        moment=at(11, 0, day=MONDAY),
    )


# ══════════════════════════════════════════════════════════════════
# 3) تبديل الغياب
# ══════════════════════════════════════════════════════════════════


def _pending_vp_swap(world):
    slot_a, slot_b = _two_slots(world)
    absence = TeacherAbsence.objects.create(school=world["school"], teacher=world["a"], date=SUNDAY)
    return TeacherSwap.objects.create(
        school=world["school"],
        teacher_a=world["a"],
        teacher_b=world["b"],
        slot_a=slot_a,
        slot_b=slot_b,
        swap_date_a=SUNDAY,
        swap_date_b=MONDAY,
        swap_type="cross_day",
        status="pending_vp",
        absence=absence,
        requested_by=world["a"],
    )


def test_s7_an_absence_swap_rejected_by_the_vp_changes_no_teacher(world):
    swap = _pending_vp_swap(world)
    AbsenceSwapService.vp_decide(swap, world["principal"], approved=False, rejection_reason="لا")
    SubstituteService.hand_over_session(world["school"], swap.slot_a, SUNDAY, world["a"])
    lesson = _lesson(world, SUNDAY, dt.time(10, 50))
    assert lesson.teacher_id == world["a"].id


def test_s7_an_absence_swap_approved_by_the_vp_hands_both_over_on_execution(world):
    swap = _pending_vp_swap(world)
    assert not Session.objects.filter(date=SUNDAY, teacher=world["b"]).exists()
    AbsenceSwapService.vp_decide(swap, world["principal"], approved=True)
    swap.refresh_from_db()
    assert swap.status == "executed"
    _inherits(
        world,
        _lesson(world, SUNDAY, dt.time(10, 50)),
        world["b"],
        world["a"],
        moment=at(11, 0, day=SUNDAY),
    )


# ══════════════════════════════════════════════════════════════════
# 4) التعويض
# ══════════════════════════════════════════════════════════════════


def _compensatory_over_a_colleagues_lesson(world):
    """أ يطلب تعويضاً في حصّة ب (الخميس السادسة) — فتصير حصّتُها لأ إن اعتُمد."""
    _slot(world, world["b"], 4, 6, dt.time(11, 10), dt.time(11, 50))
    ScheduleService.ensure_sessions_for_date(world["school"], THURSDAY, academic_year=YEAR)
    missed = _slot(world, world["a"], 1, 3, dt.time(8, 40), dt.time(9, 20))
    absence = TeacherAbsence.objects.create(
        school=world["school"], teacher=world["a"], date=SUNDAY - dt.timedelta(days=7)
    )
    return CompensatoryService.request_compensatory(
        school=world["school"],
        teacher=world["a"],
        original_slot=missed,
        absence=absence,
        compensatory_date=THURSDAY,
        compensatory_period=6,
    )


def test_s7_a_compensatory_request_changes_no_teacher_until_approved(world):
    comp = _compensatory_over_a_colleagues_lesson(world)
    assert comp.status == "colleague"
    lesson = _lesson(world, THURSDAY, dt.time(11, 10))
    assert lesson.teacher_id == world["b"].id
    CompensatoryService.colleague_decide(comp, world["b"], accepted=True)
    lesson.refresh_from_db()
    assert lesson.teacher_id == world["b"].id


def test_s7_an_approved_compensatory_hands_the_lesson_to_the_requester(world):
    comp = _compensatory_over_a_colleagues_lesson(world)
    CompensatoryService.colleague_decide(comp, world["b"], accepted=True)
    CompensatoryService.approve_compensatory(comp, approved_by=world["principal"])
    lesson = _lesson(world, THURSDAY, dt.time(11, 10))
    assert lesson.original_teacher_id == world["b"].id
    _inherits(world, lesson, world["a"], world["b"], moment=at(11, 20, day=THURSDAY))


def test_s7_a_rejected_compensatory_leaves_the_lesson_with_its_owner(world):
    comp = _compensatory_over_a_colleagues_lesson(world)
    CompensatoryService.colleague_decide(comp, world["b"], accepted=True)
    CompensatoryService.approve_compensatory(
        comp, approved_by=world["principal"], approved=False, rejection_reason="لا"
    )
    lesson = _lesson(world, THURSDAY, dt.time(11, 10))
    assert lesson.teacher_id == world["b"].id
    assert CompensatorySession.objects.get(pk=comp.pk).status == "cancelled"


# ══════════════════════════════════════════════════════════════════
# حارسٌ: كاتبٌ جديدٌ لـSession.teacher يُراجَع هنا
# ══════════════════════════════════════════════════════════════════

#: المواضعُ التي تكتب `Session.teacher` اليوم — وكلُّ مسارٍ من الأربعة أعلاه يمرّ بأحدها. موضعٌ جديدٌ يسقط الاختبارَ
#: حتى يُضاف إليه اختبارُ مسارٍ يثبت أنّه يكتب عند التنفيذ وحدَه (S7).
SESSION_TEACHER_WRITERS = {
    ("operations/services/compensatory.py", "lesson.teacher_id = comp.colleague_id"),
    ("operations/services/compensatory.py", "lesson.teacher = comp.teacher"),
    ("operations/services/substitute.py", "session.teacher = to_teacher"),
}


def test_s7_no_new_writer_of_session_teacher_goes_unreviewed():
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    pattern = re.compile(r"^\s*(?:session|lesson)\.teacher(?:_id)?\s*=[^=].*$", re.MULTILINE)
    found = set()
    for path in (root / "operations").rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if "/migrations/" in rel:
            continue
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            found.add((rel, match.group(0).strip()))
    assert found == SESSION_TEACHER_WRITERS, sorted(found ^ SESSION_TEACHER_WRITERS)

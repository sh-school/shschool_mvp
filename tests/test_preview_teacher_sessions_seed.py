"""[W-20261003-023، W-20261005-005] بذرُ المعلّم الوهميّ على 8500 (`docs/preview_teacher_sessions_seed.py`): يُسنِد حصصاً **قائمةً** لجناحٍ واحدٍ ولا يُنشئ.

السكربتُ يُنفَّذ بـ`manage.py shell` لا استيراداً، فيُشغَّل هنا بـ`runpy` وبمتغيّر البيئة نفسِه. ورصدُ الجناح يتوقّف على نافذة اليوم الدراسيّ
بساعة التشغيل الحقيقيّة، فلا يُجزَم هنا بوجود إدخالات؛ يُجزَم بالإسناد وصفوف الرصد المعتمَد وبإعادة المعلّمين الأصليّين.

العالمُ الاختباريّ يحاكي 8500: **شعبُ الجناح مشغولةٌ في فتراتها بمعلّميها** (فلا حصّةَ جديدةً تُنشأ بلا اصطدامٍ بـ`no_class_time_overlap`)،
فالحلُّ تبديلُ معلّمِ حصّةٍ قائمة: أربعٌ في الجناح بفتراتٍ مختلفةٍ وحصّتان للتربية الخاصّة، ولا يُمسّ ما مسّه أحد.
"""

import datetime as dt
import runpy
from pathlib import Path
from unittest.mock import patch

import pytest
from django.utils import timezone

from core.preview_accounts import EMPLOYEE_NUMBERS, ID_PREFIX, NAME_PREFIX
from operations.models import Session, StudentAttendance
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import ENROLLED
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

SEED = Path(__file__).resolve().parent.parent / "docs" / "preview_teacher_sessions_seed.py"
MARK = "[معاينة المعلّم]"
PERIODS = [
    (dt.time(7, 10), dt.time(7, 55)),
    (dt.time(8, 0), dt.time(8, 45)),
    (dt.time(8, 50), dt.time(9, 35)),
    (dt.time(9, 40), dt.time(10, 25)),
    (dt.time(10, 45), dt.time(11, 30)),
    (dt.time(11, 35), dt.time(12, 20)),
]


def _run(action, monkeypatch, *, preview=True):
    monkeypatch.setenv("TEACHER_SEED_ACTION", action)
    with patch("core.preview_accounts.in_preview_environment", return_value=preview):
        runpy.run_path(str(SEED))


def _students(school, group, count=2):
    for _ in range(count):
        student = UserFactory()
        StudentEnrollmentFactory(student=student, class_group=group, enrolled_at=ENROLLED)
        MembershipFactory(
            user=student, school=school, role=RoleFactory(school=school, name="student")
        )


def _session(school, group, period, teacher=None):
    """حصّةٌ قائمةٌ لمعلّمٍ حقيقيٍّ لهذه الشعبة في هذه الفترة اليوم."""
    start, end = PERIODS[period]
    return Session.objects.create(
        school=school,
        class_group=group,
        teacher=teacher or UserFactory(),
        date=timezone.localdate(),
        start_time=start,
        end_time=end,
        status="scheduled",
    )


@pytest.fixture
def world(school, year, klass, kid, wing, monkeypatch):
    """معلّمٌ وهميٌّ موسوم، وثلاثُ شعبِ جناحٍ مشغولةٍ في الفترات 1–4 بمعلّميها، وشعبتا تربيةٍ خاصّةٍ بلا جناحٍ مشغولتان في الفترات 1–6."""
    monkeypatch.setenv("TEACHER_SEED_WING", wing.code)
    teacher = UserFactory(
        full_name=f"{NAME_PREFIX}معلّم",
        national_id=f"{ID_PREFIX}teacher",
        employee_number=EMPLOYEE_NUMBERS["teacher"],
    )
    MembershipFactory(user=teacher, school=school, role=RoleFactory(school=school, name="teacher"))
    wing_groups = [klass] + [
        ClassGroupFactory(school=school, grade="G9", section=f"w{n}", academic_year=year, wing=wing)
        for n in range(2)
    ]
    special_groups = [
        ClassGroupFactory(
            school=school, grade="G8", section=f"0{n}/ESE", academic_year=year, wing=None
        )
        for n in range(2)
    ]
    for group in wing_groups + special_groups:
        _students(school, group)
    for group in wing_groups:
        for period in range(4):
            _session(school, group, period)
    for group in special_groups:
        for period in range(6):
            _session(school, group, period)
    return teacher


def _mine(teacher):
    return list(
        Session.objects.filter(teacher=teacher, notes__contains=MARK)
        .select_related("class_group")
        .order_by("start_time")
    )


def test_it_refuses_outside_the_preview_environment(world, monkeypatch):
    with pytest.raises(SystemExit):
        _run("up", monkeypatch, preview=False)
    assert not Session.objects.filter(notes__contains=MARK).exists()


def test_it_refuses_an_untagged_teacher(world, monkeypatch):
    world.full_name = "معلّم حقيقيّ"
    world.save(update_fields=["full_name"])
    with pytest.raises(SystemExit):
        _run("up", monkeypatch)
    assert not Session.objects.filter(notes__contains=MARK).exists()


def test_up_reassigns_four_wing_sessions_and_two_special_education_without_creating(
    world, wing, monkeypatch
):
    before = Session.objects.count()

    _run("up", monkeypatch)

    sessions = _mine(world)
    assert Session.objects.count() == before, "تبديلُ معلّمٍ على حصصٍ قائمةٍ لا إنشاءُ حصص"
    assert len(sessions) == 6
    in_wing = [s for s in sessions if s.class_group.wing_id]
    special = [s for s in sessions if not s.class_group.wing_id]
    # كلُّ حصص الجناح في جناحٍ واحد، والباقي حصّتان للتربية الخاصّة فقط
    assert len(in_wing) == 4 and {s.class_group.wing_id for s in in_wing} == {wing.id}
    assert len(special) == 2 and all(s.class_group.section.upper().endswith("ESE") for s in special)
    # فتراتٌ مختلفة (قيدُ no_teacher_time_overlap)، وكلُّها مبدَّلةٌ يحفظ original_teacher صاحبَها
    assert len({s.start_time for s in sessions}) == 6
    assert all(s.original_teacher_id for s in sessions)
    # رصدُ الجناح: أبكرُ حصّةٍ في الجناح
    entry = [s for s in sessions if "[جناح الرصد]" in s.notes]
    assert len(entry) == 1 and entry[0].class_group.wing_id == wing.id
    assert entry[0].start_time == min(s.start_time for s in in_wing)
    completed = [s for s in sessions if s.status == "completed"]
    assert len(completed) == 2
    assert StudentAttendance.objects.filter(session__in=completed).count() == 4


def test_up_is_idempotent(world, monkeypatch):
    _run("up", monkeypatch)
    state = (Session.objects.count(), StudentAttendance.objects.count(), len(_mine(world)))

    _run("up", monkeypatch)

    assert (
        Session.objects.count(),
        StudentAttendance.objects.count(),
        len(_mine(world)),
    ) == state


def test_the_wing_supervisor_sees_every_wing_session(world, holder, monkeypatch):
    """المشرفُ المغطّي لجناحٍ واحدٍ يرى حصصَ المعلّم الأربعَ فيه كلَّها — لا حصّتَين من ستّ (واقعةُ 2026-10-05)."""
    _run("up", monkeypatch)

    seen = Session.objects.filter(notes__contains=MARK, class_group__wing__supervisor=holder)

    assert seen.count() == 4


def test_a_touched_session_is_never_taken(school, world, wing, monkeypatch):
    """حصّةٌ فيها رصدٌ لا تُبدَّل ولو كانت أبكرَ مرشَّحة — يؤخذ غيرُها في الفترة نفسها."""
    first = (
        Session.objects.filter(class_group__wing=wing, start_time=PERIODS[0][0])
        .order_by("class_group__grade", "class_group__section", "id")
        .first()
    )
    kid = first.class_group.enrollments.first().student
    StudentAttendance.objects.create(
        session=first, student=kid, school=school, status="present", source="teacher"
    )

    _run("up", monkeypatch)

    first.refresh_from_db()
    assert first.teacher_id != world.id and first.original_teacher_id is None
    assert any(s.start_time == PERIODS[0][0] for s in _mine(world)), "أُخذت حصّةٌ أخرى في الفترة"


def test_a_period_where_the_teacher_already_teaches_is_skipped(school, world, wing, monkeypatch):
    other = ClassGroupFactory(
        school=school, grade="G5", section="x", academic_year=wing.academic_year
    )
    _session(school, other, 0, teacher=world)

    _run("up", monkeypatch)

    taken = [s for s in _mine(world) if s.start_time == PERIODS[0][0]]
    assert taken == [], "المعلّمُ يدرّس في الفترة 1 سلفاً فلا تُبدَّل حصّةٌ فيها"


def test_plan_writes_nothing_and_prints_the_codes_not_names(world, monkeypatch, capsys):
    before = (Session.objects.count(), StudentAttendance.objects.count())

    _run("plan", monkeypatch)

    out = capsys.readouterr().out
    assert (Session.objects.count(), StudentAttendance.objects.count()) == before
    assert not Session.objects.filter(notes__contains=MARK).exists()
    assert "الإسنادُ المقترح" in out
    assert world.full_name not in out


def test_it_refuses_when_the_chosen_wing_has_too_few_sessions(world, monkeypatch, capsys):
    monkeypatch.setenv("TEACHER_SEED_WING", "w9")

    _run("plan", monkeypatch)
    assert "لا يكفي" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        _run("up", monkeypatch)

    assert not Session.objects.filter(notes__contains=MARK).exists()


def test_down_gives_every_session_back_to_its_teacher(world, monkeypatch):
    owners = dict(Session.objects.values_list("pk", "teacher_id"))
    _run("up", monkeypatch)

    _run("down", monkeypatch)

    assert Session.objects.count() == len(owners)
    for session in Session.objects.all():
        assert session.teacher_id == owners[session.pk]
        assert session.original_teacher_id is None
        assert session.status == "scheduled" and MARK not in session.notes
    assert not StudentAttendance.objects.filter(
        session__class_group__enrollments__isnull=False
    ).exists()


def _legacy_created(school, world, klass):
    """بقايا إصدارٍ سابق: حصّةٌ **أُنشئت** وسمُها بلا `original_teacher` (كما على 8500)."""
    start, end = PERIODS[0]
    return Session.objects.create(
        school=school,
        class_group=klass,
        teacher=world,
        date=timezone.localdate(),
        start_time=dt.time(6, 0),
        end_time=dt.time(6, 40),
        status="scheduled",
        notes=f"{MARK} حصّةُ معاينةٍ تُمحى بـdown [جناح الرصد]",
    )


def test_up_refuses_leftovers_of_an_older_seed_instead_of_reusing_them_silently(
    school, klass, world, monkeypatch
):
    _legacy_created(school, world, klass)
    before = Session.objects.count()

    with pytest.raises(SystemExit):
        _run("up", monkeypatch)

    assert Session.objects.count() == before, "لم يُسنَد ولم يُنشأ شيء"


def test_plan_shows_the_existing_marked_sessions_first(school, klass, world, monkeypatch, capsys):
    _legacy_created(school, world, klass)

    _run("plan", monkeypatch)

    out = capsys.readouterr().out
    assert "حصصٌ موسومةٌ قائمةٌ اليوم: 1" in out
    assert "أنشأها إصدارٌ سابق" in out and "لا تصلح لإعادة الاستعمال" in out


def test_up_does_not_try_new_entries_on_a_wing_session_that_already_has_entries(
    world, monkeypatch, capsys
):
    from operations.models import AttendanceEntry

    _run("up", monkeypatch)
    entry_session = next(s for s in _mine(world) if "[جناح الرصد]" in s.notes)
    entries_before = AttendanceEntry.objects.filter(session=entry_session).count()

    _run("up", monkeypatch)

    out = capsys.readouterr().out
    assert AttendanceEntry.objects.filter(session=entry_session).count() == entries_before
    if entries_before:
        assert "لها إدخالاتٌ سلفاً" in out

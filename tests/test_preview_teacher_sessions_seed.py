"""[W-20261003-023] بذرُ حصص المعلّم الوهميّ على 8500 (`docs/preview_teacher_sessions_seed.py`): يرفض خارج المعاينة، ومتساوي الأثر، ويمحو ما وسَمه وحدَه.

السكربتُ يُنفَّذ بـ`manage.py shell` لا استيراداً، فيُشغَّل هنا بـ`runpy` وبمتغيّر البيئة نفسِه. ورصدُ الجناح يتوقّف على نافذة اليوم الدراسيّ
بساعة التشغيل الحقيقيّة، فلا يُجزَم هنا بوجود إدخالاتٍ؛ يُجزَم بالحصص وصفوف الرصد المعتمَد وبالمحو.

العالمُ الاختباريّ يحاكي ما ظهر على 8500: ثلاثُ شعبٍ بلا جناح فقط، **وكلُّ شعب الجناح لها حصّةٌ في الفترة الأولى** — فلا يصحّ اختيارٌ
جشعٌ لفترةٍ ثابتة؛ والحلُّ يجد فترةً تخلو فيها شعبةُ جناح.
"""

import datetime as dt
import runpy
from pathlib import Path
from unittest.mock import patch

import pytest
from django.utils import timezone

from core.preview_accounts import EMPLOYEE_NUMBERS, ID_PREFIX, NAME_PREFIX
from operations.models import ScheduleSlot, Session, StudentAttendance
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
    (dt.time(12, 25), dt.time(13, 10)),
]


def _run(action, monkeypatch, *, preview=True):
    monkeypatch.setenv("TEACHER_SEED_ACTION", action)
    with patch("core.preview_accounts.in_preview_environment", return_value=preview):
        runpy.run_path(str(SEED))


def _students(school, group, count=2):
    out = []
    for _ in range(count):
        student = UserFactory()
        StudentEnrollmentFactory(student=student, class_group=group, enrolled_at=ENROLLED)
        MembershipFactory(
            user=student, school=school, role=RoleFactory(school=school, name="student")
        )
        out.append(student)
    return out


def _busy_at(school, group, start, end):
    """حصّةٌ حقيقيّةٌ لمعلّمٍ آخر لهذه الشعبة في هذا الوقت اليوم."""
    Session.objects.create(
        school=school,
        class_group=group,
        teacher=UserFactory(),
        date=timezone.localdate(),
        start_time=start,
        end_time=end,
        status="scheduled",
        notes="حصّةٌ حقيقيّة",
    )


@pytest.fixture
def world(school, year, klass, kid, wing):
    """معلّمٌ وهميٌّ موسوم، وثلاثُ شعب جناحٍ مشغولةٍ كلُّها في الفترة 1، وثلاثُ شعبٍ بلا جناحٍ (كما على 8500)، وجدولٌ بسبع فترات."""
    teacher = UserFactory(
        full_name=f"{NAME_PREFIX}معلّم",
        national_id=f"{ID_PREFIX}teacher",
        employee_number=EMPLOYEE_NUMBERS["teacher"],
    )
    MembershipFactory(user=teacher, school=school, role=RoleFactory(school=school, name="teacher"))
    _students(school, klass, 1)
    wing_groups = [klass] + [
        ClassGroupFactory(school=school, grade="G9", section=f"w{n}", academic_year=year, wing=wing)
        for n in range(2)
    ]
    for group in wing_groups[1:]:
        _students(school, group)
    for number in range(3):
        _students(
            school,
            ClassGroupFactory(school=school, grade="G8", section=f"p{number}", academic_year=year),
        )
    for group in wing_groups:
        _busy_at(school, group, *PERIODS[0])

    # الجدولُ المعتمَد: سبعُ فتراتٍ لمعلّمٍ آخر (اليومُ الأسبوعيّ نفسُه كما يحسبه السكربت)
    day = (timezone.localdate().weekday() + 1) % 7
    day = 0 if day > 4 else day
    owner = UserFactory()
    for number, (start, end) in enumerate(PERIODS, start=1):
        ScheduleSlot.objects.create(
            school=school,
            teacher=owner,
            class_group=ClassGroupFactory(
                school=school, grade="G6", section=f"s{number}", academic_year=year
            ),
            day_of_week=day,
            period_number=number,
            start_time=start,
            end_time=end,
            academic_year=year,
        )
    return teacher


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


def test_up_finds_a_complete_plan_when_every_wing_group_is_busy_in_period_one(world, monkeypatch):
    _run("up", monkeypatch)
    sessions = list(Session.objects.filter(notes__contains=MARK).order_by("start_time"))
    assert len(sessions) == 6
    assert {s.teacher_id for s in sessions} == {world.id}
    assert len({s.class_group_id for s in sessions}) == 6
    # فترةُ رصد الجناح بشعبةِ جناحٍ لا تصطدم بحصّةٍ، وليست الفترةَ 1 المشغولة
    entry = [s for s in sessions if "[جناح الرصد]" in s.notes]
    assert len(entry) == 1 and entry[0].class_group.wing_id
    assert entry[0].start_time != PERIODS[0][0]
    # الشعبُ بلا جناحٍ أوّلاً: الثلاثُ كلُّها مستعملة
    assert sum(1 for s in sessions if not s.class_group.wing_id) == 3
    completed = [s for s in sessions if s.status == "completed"]
    assert len(completed) == 2
    assert StudentAttendance.objects.filter(session__in=completed).count() == 4
    before = (Session.objects.count(), StudentAttendance.objects.count())

    _run("up", monkeypatch)
    assert (Session.objects.count(), StudentAttendance.objects.count()) == before


def test_plan_writes_nothing_and_prints_the_codes_not_names(world, monkeypatch, capsys):
    before = (Session.objects.count(), StudentAttendance.objects.count())
    _run("plan", monkeypatch)
    out = capsys.readouterr().out
    assert (Session.objects.count(), StudentAttendance.objects.count()) == before
    assert "الحلُّ الكامل" in out
    assert "فترة 1" in out
    assert world.full_name not in out


def test_plan_explains_when_there_is_no_complete_plan(world, monkeypatch, capsys):
    # كلُّ فتراتِ الجدول مشغولةٌ لشعب الجناح كلِّها ⇒ لا فترةَ رصدٍ تخلو
    from core.models import ClassGroup

    for group in ClassGroup.objects.filter(wing__isnull=False):
        for start, end in PERIODS[1:]:
            _busy_at(group.school, group, start, end)
    _run("plan", monkeypatch)
    out = capsys.readouterr().out
    assert "لا حلَّ كاملاً" in out
    assert "شعبُ جناحٍ خاليةٌ 0/" in out
    assert not Session.objects.filter(notes__contains=MARK).exists()


def test_a_full_plan_exists_when_wing_groups_are_free_only_in_three_periods(world, monkeypatch):
    """حالةُ 8500 الفعليّة (قياس plan): شعبُ الجناح خاليةٌ في الفترات 3 و4 و7 وحدَها وبلا الجناح ثلاثٌ فقط — اختيارٌ جشعٌ كان يستنفد الثلاثَ مبكّراً."""
    from core.models import ClassGroup

    for group in ClassGroup.objects.filter(wing__isnull=False):
        for index in (1, 4, 5):  # الفترة 1 مشغولةٌ أصلاً في العالم
            _busy_at(group.school, group, *PERIODS[index])
    _run("up", monkeypatch)
    sessions = list(Session.objects.filter(notes__contains=MARK).order_by("start_time"))
    assert len(sessions) == 6
    assert len({s.class_group_id for s in sessions}) == 6
    entry = [s for s in sessions if "[جناح الرصد]" in s.notes][0]
    assert entry.start_time in {PERIODS[2][0], PERIODS[3][0], PERIODS[6][0]}
    # في الفترات التي لا جناحَ خالياً فيها لا تُستعمل إلا الشعبُ بلا جناح
    for session in sessions:
        if session.start_time in {PERIODS[i][0] for i in (0, 1, 4, 5)}:
            assert not session.class_group.wing_id


def test_down_removes_only_what_was_marked(world, school, klass, monkeypatch):
    other = Session.objects.create(
        school=school,
        class_group=klass,
        teacher=world,
        date=dt.date(2026, 1, 5),
        start_time=dt.time(6, 0),
        end_time=dt.time(6, 40),
        status="scheduled",
        notes="حصّةٌ حقيقيّة",
    )
    _run("up", monkeypatch)
    _run("down", monkeypatch)
    assert not Session.objects.filter(notes__contains=MARK).exists()
    assert Session.objects.filter(pk=other.pk).exists()
    assert not StudentAttendance.objects.filter(session__notes__contains=MARK).exists()

"""[SCHEDULE] ساعةُ المحاولة: الميزانيةُ تُحترم داخل الإصلاح لا بين المحاولات وحدَها (W-20261002-033).

كان `generate_schedule` يسأل الميزانيةَ في `_search_exhausted` بين المحاولات، والمحاولةُ نفسُها (`_repair_pass` ←
`_try_eject` بعمق 3 لكلّ متعذّرة، ثلاثَ مرّاتٍ) بلا ساعة، و`MIN_ATTEMPTS = 3` لا يقف قبل ثلاثٍ مهما طالت الأولى — فشعبةٌ
فوق سعتها أنفقت ≈290 ثانيةً على ميزانيةِ 4 ثوانٍ (profiler: 99.8% في `_try_eject`). فصارت `Deadline` تُمرَّر إلى الإصلاح
فيقف عند نفادها ويذكر ذلك (`budget_cut` في اللقطة)، ومحاولةٌ واحدةٌ تكفي حين تنفد الميزانية.
"""

import pytest

from operations import scheduler
from operations.models import ScheduleGeneration, Subject, SubjectClassAssignment, TimeSlotConfig
from operations.scheduler import Deadline, _repair_pass, _search_exhausted, generate_schedule
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

YEAR = "2026-2027"


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


# ── الساعة ───────────────────────────────────────────────────────────


def test_a_deadline_expires_at_its_moment_and_remembers_it():
    clock = FakeClock()
    deadline = Deadline(10, clock=clock)

    assert deadline.expired() is False and deadline.hit is False
    clock.now = 10
    assert deadline.expired() is True and deadline.hit is True
    clock.now = 0  # ما انقضى لا يعود
    assert deadline.expired() is True


# ── الإصلاح يقف عند الساعة ─────────────────────────────────────────────


def test_an_expired_clock_stops_the_repair_before_any_ejection(monkeypatch):
    calls = []
    monkeypatch.setattr(scheduler, "_try_eject", lambda *a, **k: calls.append(1) or True)
    deadline = Deadline(0, clock=lambda: 1)
    leftovers = ["t1", "t2", "t3"]

    still = _repair_pass(object(), leftovers, set(), [], 99, deadline=deadline)

    assert still == leftovers, "كلُّها تبقى متعذّرةً بموضعها"
    assert calls == [] and deadline.hit is True


def test_the_repair_stops_mid_pass_when_the_clock_runs_out(monkeypatch):
    clock = FakeClock()
    deadline = Deadline(5, clock=clock)
    placed = []

    def eject(grid, task, *a, **k):
        placed.append(task)
        clock.now = 6  # الإزاحةُ الأولى استهلكت الميزانية
        return True

    monkeypatch.setattr(scheduler, "_try_eject", eject)

    still = _repair_pass(object(), ["t1", "t2", "t3"], set(), [], 99, deadline=deadline)

    assert placed == ["t1"], "وُضعت واحدةٌ ثمّ قُطع"
    assert still == ["t2", "t3"] and deadline.hit is True


def test_without_a_clock_the_repair_behaves_as_before(monkeypatch):
    monkeypatch.setattr(scheduler, "_try_eject", lambda *a, **k: True)

    assert _repair_pass(object(), ["t1", "t2"], set(), [], 99) == []


# ── محاولةٌ واحدةٌ تكفي عند نفاد الميزانية ──────────────────────────────


def test_one_attempt_is_enough_once_the_budget_is_spent():
    assert _search_exhausted(1, elapsed=5, budget=4, idle=0, complete=True) is True
    assert (
        _search_exhausted(1, elapsed=5, budget=4, idle=0, complete=False) is False
    ), "ناقصٌ: ضعفُ الميزانية"
    assert _search_exhausted(1, elapsed=9, budget=4, idle=0, complete=False) is True


def test_fast_attempts_still_run_the_minimum_for_comparison():
    """لا تتغيّر محاولاتٌ سريعةٌ لم تبلغ الميزانية: الحدُّ الأدنى للمقارنة باقٍ لها."""
    assert _search_exhausted(1, elapsed=0.1, budget=60, idle=0, complete=True) is False
    assert _search_exhausted(2, elapsed=0.2, budget=60, idle=2, complete=True) is False
    assert _search_exhausted(3, elapsed=0.3, budget=60, idle=3, complete=True) is True


# ── توليدٌ حقيقيّ ───────────────────────────────────────────────────────


@pytest.fixture
def over_capacity(school):
    """36 حصّةً على 35 خانة (متعذّرةٌ واحدة) — صغيرةٌ تكفي لإظهار القطع بلا إبطاء الاختبار."""
    from datetime import time

    for period in range(1, 8):
        for day_type in ("regular", "thursday"):
            TimeSlotConfig.objects.create(
                school=school,
                period_number=period,
                start_time=time(6 + period, 0),
                end_time=time(6 + period, 45),
                day_type=day_type,
            )
    role = RoleFactory(school=school, name="teacher")
    group = ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year=YEAR)
    for index in range(3):
        teacher = UserFactory(full_name=f"معلّم {index}")
        MembershipFactory(user=teacher, school=school, role=role)
        subject = Subject.objects.create(school=school, name_ar=f"مادّة {index}", code=f"S{index}")
        SubjectClassAssignment.objects.create(
            school=school,
            academic_year=YEAR,
            teacher=teacher,
            class_group=group,
            subject=subject,
            weekly_periods=12,
            is_active=True,
        )
    return school


@pytest.mark.django_db
def test_a_spent_budget_cuts_the_repair_records_it_and_runs_a_single_attempt(
    over_capacity, settings
):
    settings.SCHEDULE_TIME_BUDGET_SECONDS = 0.0001

    result = generate_schedule(over_capacity, YEAR)

    snapshot = ScheduleGeneration.objects.get(pk=result["generation"].pk).config_snapshot
    assert snapshot["budget_cut"] is True
    assert snapshot["attempts"] == 1, "محاولةٌ واحدةٌ لا ثلاث"
    assert snapshot["unplaced"] >= 1


@pytest.mark.django_db
def test_an_ample_budget_is_never_cut(over_capacity, settings, monkeypatch):
    settings.SCHEDULE_TIME_BUDGET_SECONDS = 3600
    monkeypatch.setattr(scheduler, "_try_eject", lambda *a, **k: False)  # بلا إزاحةٍ فلا إبطاء
    monkeypatch.setattr(scheduler, "MAX_ATTEMPTS", 3)

    result = generate_schedule(over_capacity, YEAR)

    snapshot = ScheduleGeneration.objects.get(pk=result["generation"].pk).config_snapshot
    assert snapshot["budget_cut"] is False

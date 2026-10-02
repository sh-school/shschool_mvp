"""[SCHEDULE] ساعةُ المحاولة: الميزانيةُ تُحترم داخل الإصلاح لا بين المحاولات وحدَها (W-20261002-033).

كان `generate_schedule` يسأل الميزانيةَ في `_search_exhausted` بين المحاولات، والمحاولةُ نفسُها (`_repair_pass` ←
`_try_eject` بعمق 3 لكلّ متعذّرة، ثلاثَ مرّاتٍ) بلا ساعة، و`MIN_ATTEMPTS = 3` لا يقف قبل ثلاثٍ مهما طالت الأولى — فشعبةٌ
فوق سعتها أنفقت ≈290 ثانيةً على ميزانيةِ 4 ثوانٍ (profiler: 99.8% في `_try_eject`). فصارت `Deadline` تُمرَّر إلى الإصلاح
فيقف عند نفادها ويذكر ذلك (`budget_cut` في اللقطة)، ومحاولةٌ واحدةٌ تكفي حين تنفد الميزانية.
"""

import itertools

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


def test_the_deadline_remembers_which_attempt_and_when_it_first_cut():
    clock = FakeClock()
    deadline = Deadline(10, clock=clock)
    deadline.attempt = 2
    clock.now = 12.34

    assert deadline.expired() is True
    deadline.attempt = 5  # قطعٌ لاحقٌ لا يغيّر سجلَّ الأوّل
    clock.now = 99
    assert deadline.expired() is True
    assert deadline.hit_attempt == 2 and deadline.hit_after == 12.3


def test_the_deadline_uses_a_monotonic_clock_by_default():
    """مدّةٌ لا وقتٌ: تعديلُ ساعة النظام (NTP) لا يقطع التوليدَ ولا يمدّه."""
    import time

    assert Deadline(1)._clock is time.monotonic


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
    assert snapshot["budget_cut_attempt"] == 1 and snapshot["budget_cut_after_s"] is not None
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
    assert snapshot["licences_tried"] is True
    assert all(a["cut"] is False for a in snapshot["attempt_log"])


# ── القطعُ يخصّ المحاولةَ المختارة (مراجعةُ 0403) ─────────────────────────


def _fake_deadline(monkeypatch, clock):
    """`generate_schedule` يبني ساعتَه بـ`Deadline(seconds)` — تُستبدل بساعةٍ وهميّةٍ يتحكّم بها الاختبار."""
    real = scheduler.Deadline
    monkeypatch.setattr(scheduler, "Deadline", lambda seconds: real(seconds, clock=clock))


def _count_attempts(monkeypatch, on_attempt):
    """يُنادي `on_attempt(n)` قبل المحاولة رقم n (من 1) ويُمرّر إلى `_run_attempt` الحقيقيّ."""
    real = scheduler._run_attempt
    seen = {"n": 0}

    def wrapped(*args, **kwargs):
        seen["n"] += 1
        on_attempt(seen["n"])
        return real(*args, **kwargs)

    monkeypatch.setattr(scheduler, "_run_attempt", wrapped)


@pytest.mark.django_db
def test_budget_cut_follows_the_chosen_attempt_not_the_global_flag(
    over_capacity, settings, monkeypatch
):
    """المحاولةُ 1 تامّةُ الإصلاح قبل الموعد وهي المختارة، والمحاولةُ 2 تُقطع: `budget_cut` للمختارة ⇒ `False`."""
    settings.SCHEDULE_TIME_BUDGET_SECONDS = 3600
    clock = FakeClock()
    _fake_deadline(monkeypatch, clock)
    monkeypatch.setattr(scheduler, "_try_eject", lambda *a, **k: False)
    monkeypatch.setattr(scheduler, "MAX_ATTEMPTS", 2)
    # درجةُ المختبر ثابتةٌ فلا تتفوّق المحاولةُ 2 بالدرجة — ويبقى الاختيارُ للمحاولة 1 (المتعذّراتُ متساوية).
    monkeypatch.setattr("operations.schedule_lab.grid_lab_score", lambda grid, ctx: (50, {}))
    _count_attempts(monkeypatch, lambda n: setattr(clock, "now", 10**6) if n == 2 else None)

    result = generate_schedule(over_capacity, YEAR)

    snapshot = ScheduleGeneration.objects.get(pk=result["generation"].pk).config_snapshot
    log = snapshot["attempt_log"]
    assert snapshot["chosen_attempt"] == 0, "شرطٌ مسبق: اختيرت المحاولةُ التامّةُ الأولى"
    assert [a["cut"] for a in log] == [False, True]
    assert snapshot["budget_cut"] is False, "اختيرت المحاولةُ 1 فمتعذّراتُها ليست من قطع"
    assert snapshot["licences_tried"] is True
    assert snapshot["search_budget_exhausted"] is True and snapshot["budget_cut_attempt"] == 2


@pytest.mark.django_db
def test_a_cut_chosen_attempt_never_tries_the_licences_and_says_so(
    over_capacity, settings, monkeypatch
):
    settings.SCHEDULE_TIME_BUDGET_SECONDS = 3600
    clock = FakeClock()
    _fake_deadline(monkeypatch, clock)
    monkeypatch.setattr(scheduler, "_try_eject", lambda *a, **k: pytest.fail("لا إزاحةَ بعد القطع"))
    monkeypatch.setattr(scheduler, "MAX_ATTEMPTS", 1)
    # تنقضي الميزانيةُ قبل أن تبدأ المحاولةُ الأولى (بعد إنشاء الساعة): الإصلاحُ لا يُجرى أصلاً.
    _count_attempts(monkeypatch, lambda n: setattr(clock, "now", 10**6))

    result = generate_schedule(over_capacity, YEAR)

    snapshot = ScheduleGeneration.objects.get(pk=result["generation"].pk).config_snapshot
    assert snapshot["budget_cut"] is True and snapshot["licences_tried"] is False
    assert (
        snapshot["relaxed"] == 0 and snapshot["densed"] == 0
    ), "صفرٌ لأنّها لم تُجرَّب لا لأنّها لم تنفع"
    assert snapshot["attempts"] == 1


# ── لا تغيّرَ في النتيجة ما بقيت ميزانية، ولا تجاوزَ فوق إزاحةٍ واحدة ───────


def _scripted_eject(results):
    """`_try_eject` حتميٌّ: يُرجع النتائجَ بالترتيب — للمقارنة بين تمريرٍ بساعةٍ وآخرَ بلا ساعة."""
    cycle = itertools.cycle(results)
    return lambda *a, **k: next(cycle)


def test_an_ample_clock_gives_exactly_the_result_of_no_clock(monkeypatch):
    script = [True, False, True, True, False, False]
    tasks = [f"t{i}" for i in range(6)]

    monkeypatch.setattr(scheduler, "_try_eject", _scripted_eject(script))
    without = _repair_pass(object(), tasks, set(), [], 99)
    monkeypatch.setattr(scheduler, "_try_eject", _scripted_eject(script))
    ample = Deadline(10**9)
    with_clock = _repair_pass(object(), tasks, set(), [], 99, deadline=ample)

    assert with_clock == without and ample.hit is False


def test_the_overshoot_is_at_most_one_ejection(monkeypatch):
    """إزاحةٌ بطيئةٌ مصطنعةٌ (3 وحداتٍ للواحدة) وموعدٌ عند 5: يقف بعد الثانية ولا يتجاوز الموعدَ بأكثر من إزاحةٍ."""
    clock = FakeClock()
    deadline = Deadline(5, clock=clock)

    def slow_eject(*a, **k):
        clock.now += 3
        return True

    monkeypatch.setattr(scheduler, "_try_eject", slow_eject)

    still = _repair_pass(object(), [f"t{i}" for i in range(10)], set(), [], 99, deadline=deadline)

    assert len(still) == 8, "وُضعت إزاحتان فقط ثمّ قُطع"
    assert clock.now <= 5 + 3, "لا تجاوزَ بأكثر من إزاحةٍ واحدة"


# ── الساعةُ داخل سلسلة الإزاحة نفسِها (قياسُ 0403: إزاحةٌ بعمق 4 = 39 ث) ────────


def test_the_clock_is_checked_at_every_candidate_inside_the_eject_chain(monkeypatch):
    clock = FakeClock()
    deadline = Deadline(2, clock=clock)
    seen = []

    def starts(*args, **kwargs):
        for index in range(10):
            seen.append(index)
            clock.now = index
            yield (0, 1)

    monkeypatch.setattr(scheduler, "_candidate_starts", starts)
    monkeypatch.setattr(scheduler, "_blockers", lambda *a, **k: None)

    assert scheduler._try_eject(object(), object(), set(), [], 4, deadline=deadline) is False
    assert seen == [0, 1, 2], "وقف عند أوّل موضعٍ بعد الموعد لا بعد استنفاد العشرة"
    assert deadline.hit is True


class CountingClock:
    """ساعةٌ تتقدّم بوحدةٍ عند كلّ استدعاء — فتنقضي الميزانيةُ بعد عددٍ محدَّدٍ من فحوص `expired()` حيثما وقعت."""

    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.calls


@pytest.mark.django_db
def test_a_cut_in_the_middle_of_an_eject_chain_leaves_a_consistent_schedule(
    over_capacity, settings, monkeypatch
):
    """القطعُ وسط السلسلة يردّ الحركةَ ذرّيّاً: لا شعبةَ في خانتَين ولا معلّمَ في خانتَين، والمتعذّرُ يبقى مذكوراً."""
    from collections import Counter

    from operations.models import ScheduleSlot

    settings.SCHEDULE_TIME_BUDGET_SECONDS = 3600
    real = scheduler.Deadline
    monkeypatch.setattr(scheduler, "Deadline", lambda seconds: real(300, clock=CountingClock()))
    monkeypatch.setattr(scheduler, "MAX_ATTEMPTS", 1)

    result = generate_schedule(over_capacity, YEAR)

    snapshot = ScheduleGeneration.objects.get(pk=result["generation"].pk).config_snapshot
    assert snapshot["budget_cut"] is True and snapshot["unplaced"] >= 1
    rows = list(ScheduleSlot.objects.filter(school=over_capacity, academic_year=YEAR))
    assert rows, "شيءٌ وُضع"
    classes = Counter((r.class_group_id, r.day_of_week, r.period_number) for r in rows)
    teachers = Counter((r.teacher_id, r.day_of_week, r.period_number) for r in rows)
    assert max(classes.values()) == 1 and max(teachers.values()) == 1


# ── ما يراه من يعتمد (ملاحظةُ 0105) ──────────────────────────────────────


def test_the_notice_reads_the_snapshot():
    from operations.schedule_breaches import budget_cut_notice

    assert budget_cut_notice(None) is None and budget_cut_notice({}) is None
    assert budget_cut_notice({"budget_cut": False}) is None
    assert budget_cut_notice(
        {"budget_cut": True, "budget_cut_attempt": 2, "budget_cut_after_s": 8.1}
    ) == {"attempt": 2, "after_seconds": 8.1}
    assert budget_cut_notice({"budget_cut": True}) == {
        "attempt": None,
        "after_seconds": None,
    }, "لقطةٌ أقدم"

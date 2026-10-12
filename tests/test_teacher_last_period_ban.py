"""[SCHEDULE] منعُ السابعة عن معلّمٍ بعينه: الصفرُ غيرُ الغياب (W-20261004-013).

كان `0` في `personal_last_cap` يعني «خُذ العامّ» فلا طريقَ لمنع السابعة عن معلّمٍ (عذرٌ صحّيّ أو قرارٌ إداريّ). صار
`None` وحدَه هو العامّ و`0` منعاً و`1..5` سقفاً أسبوعيّاً؛ ويحكم بها V1 وV2 وفحصُ الجدوى والمُقيِّمُ من مصدرٍ واحد،
بلا هجرةٍ تُعيد تفسيرَ بياناتٍ قائمة ولا مسٍّ بالجدول المعتمد الحيّ (D-381م).
"""

import re

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from ortools.sat.python import cp_model

from core.models import AuditLog
from operations import schedule_feasibility as sf
from operations.last_period_cap import admin_last_caps, last_cap_or, personal_last_cap
from operations.models import TeacherPreference
from operations.models.schedule import validate_admin_last_cap
from operations.schedule_evaluator import evaluate_slots
from operations.scheduler import ScheduleGrid
from operations.scheduler_constraints import LAST_PERIOD, check_last_period_share
from operations.scheduler_v2 import runner
from operations.scheduler_v2.model import ModelOptions, build_model
from tests.conftest import UserFactory
from tests.test_schedule_evaluator import YEAR, run_scene  # noqa: F401  (fixture)
from tests.test_scheduler_audit import lesson
from tests.test_scheduler_v2_hard import feasible, make, solve
from tests.test_teacher_first_periods import _admin_post, _pref, superuser  # noqa: F401

EVENT = "teacher_last_period_cap_changed"


# ── القراءة الآمنة: الصفرُ منعٌ و None عامّ ───────────────────────────


def test_zero_is_a_ban_and_none_is_the_general_cap():
    assert personal_last_cap(0) == 0
    assert personal_last_cap(None) is None
    assert [last_cap_or(v, 2) for v in (None, 0, 3, 99, -1, True)] == [2, 0, 3, 2, 2, 2]


def test_the_model_validator_accepts_zero_or_two_to_five_only():
    for ok in (0, 2, 3, 5):
        validate_admin_last_cap(ok)
    for bad in (1, 6, 9):
        with pytest.raises(ValidationError):
            validate_admin_last_cap(bad)


# ── V1: لا سابعةَ لمن سقفُه صفر ─────────────────────────────────────


def test_v1_refuses_the_first_seventh_for_a_zero_cap_but_not_for_others():
    grid = ScheduleGrid()
    banned = lesson("c-1", "s-1", "t-1", weekly=1)
    banned.members[0].last_cap = 0
    free = lesson("c-2", "s-2", "t-2", weekly=1)

    assert check_last_period_share(grid, LAST_PERIOD, banned) is False
    assert check_last_period_share(grid, LAST_PERIOD, free) is True
    assert check_last_period_share(grid, 3, banned) is True, "غيرُ السابعة لا يُمنع"


def test_v1_default_member_still_takes_the_general_cap():
    grid = ScheduleGrid()
    grid.place(0, LAST_PERIOD, lesson("c-1", "s-1", "t-1", weekly=1))
    grid.place(1, LAST_PERIOD, lesson("c-2", "s-2", "t-1", weekly=1))

    third = lesson("c-3", "s-3", "t-1", weekly=1)
    assert third.members[0].last_cap is None
    assert check_last_period_share(grid, LAST_PERIOD, third) is False


# ── V2: last_cap_override ────────────────────────────────────────────


def _three_classes():
    return [("C1", "S1", "T1", "", 1), ("C2", "S2", "T1", "", 1), ("C3", "S3", "T1", "", 1)]


def test_v2_zero_override_bans_the_seventh_for_that_teacher_only():
    rows = [("C1", "S1", "T1", "", 1), ("C2", "S2", "T2", "", 1)]

    assert feasible(make(rows), [(0, 0, 7)]), "بلا تخصيصٍ يسع سابعة"
    assert not feasible(make(rows), [(0, 0, 7)], last_cap_override=(("T1", 0),))
    assert feasible(make(rows), [(1, 0, 7)], last_cap_override=(("T1", 0),)), "غيرُه يبقى حرّاً"


def test_v2_override_can_also_raise_and_a_non_listed_teacher_keeps_the_general_cap():
    three = [(0, 0, 7), (1, 1, 7), (2, 2, 7)]

    assert not feasible(make(_three_classes()), three)
    assert feasible(make(_three_classes()), three, last_cap_override=(("T1", 3),))
    assert not feasible(make(_three_classes()), three, last_cap_override=(("T9", 3),))


def test_v2_records_the_override_as_an_announced_relaxation_only_when_it_differs():
    opt = ModelOptions(last_cap_override=(("T1", 0), ("T2", 2)))
    rows = [("C1", "S1", "T1", "", 1), ("C2", "S2", "T2", "", 1)]

    built = build_model(make(rows), opt)

    notes = [r for r in built.relaxations if r["code"] == "HC8"]
    assert [(r["teacher"], r["relaxed"]) for r in notes] == [("T1", "last_cap_0")]


def test_v2_zero_cap_proves_infeasible_when_a_seventh_is_forced():
    inp = make([("C1", "S1", "T1", "", 3)])
    built = build_model(inp, ModelOptions(derived_day_cap=False, last_cap_override=(("T1", 0),)))
    built.model.Add(built.x[(0, 0, 7)] == 1)

    status, _ = solve(built)

    assert status == cp_model.INFEASIBLE


def test_options_from_relaxations_accepts_the_override_and_sorts_it():
    options = runner.options_from_relaxations({"last_cap_override": {"b": 0, "a": 3}})

    assert options["last_cap_override"] == (("a", 3), ("b", 0))


# ── المصدر الواحد في الأدمن ─────────────────────────────────────────


@pytest.mark.django_db
def test_admin_last_caps_reads_ban_and_raise_but_not_the_general_or_out_of_range(school):
    ban, raised = UserFactory().pk, UserFactory().pk
    _pref(school, ban)
    _pref(school, raised)
    _pref(school, UserFactory().pk)  # بلا سقف
    TeacherPreference.objects.filter(teacher_id=ban).update(max_last_periods=0)
    TeacherPreference.objects.filter(teacher_id=raised).update(max_last_periods=4)
    for value in (2, 9):  # العامّ لا يُحمل، وخارج المدى كغيابه
        pref = _pref(school, UserFactory().pk)
        TeacherPreference.objects.filter(pk=pref.pk).update(max_last_periods=value)

    assert admin_last_caps(school, YEAR) == {str(ban): 0, str(raised): 4}


@pytest.mark.django_db
def test_a_stored_cap_reaches_the_v2_options_and_wins_over_the_file(school):
    teacher = str(UserFactory().pk)
    pref = _pref(school, teacher)
    TeacherPreference.objects.filter(pk=pref.pk).update(max_last_periods=0)
    config = runner.SolverConfig(relaxations=(("last_cap_override", {teacher: 3, "other": 4}),))

    merged = runner.with_admin_last_caps(config, school, YEAR)

    assert dict(merged.relaxations)["last_cap_override"] == {teacher: 0, "other": 4}
    options = runner.options_from_relaxations(dict(merged.relaxations))
    assert dict(options["last_cap_override"])[teacher] == 0


@pytest.mark.django_db
def test_without_stored_caps_the_config_is_untouched(school):
    config = runner.SolverConfig(relaxations=(("run_cap", 2),))

    assert runner.with_admin_last_caps(config, school, YEAR) is config


# ── الأدمن: حفظ الصفر وتدقيقه ──────────────────────────────────────


@pytest.mark.django_db
def test_admin_saves_zero_and_audits_it_as_a_change_from_the_general_cap(
    client,
    superuser,  # noqa: F811
    school,
):
    pref = _pref(school, UserFactory().pk)
    client.force_login(superuser)

    _admin_post(client, pref, school, max_last_periods=0)

    pref.refresh_from_db()
    assert pref.max_last_periods == 0
    entry = AuditLog.objects.get(changes__event=EVENT)
    assert (entry.changes["before"], entry.changes["after"]) == (None, 0)


@pytest.mark.django_db
def test_admin_zero_to_two_is_a_change_and_is_audited(client, superuser, school):  # noqa: F811
    pref = _pref(school, UserFactory().pk)
    TeacherPreference.objects.filter(pk=pref.pk).update(max_last_periods=0)
    client.force_login(superuser)

    _admin_post(client, pref, school, max_last_periods=2)

    assert AuditLog.objects.filter(changes__event=EVENT).count() == 1, "رفعُ المنع قرارٌ يُسجَّل"


@pytest.mark.django_db
def test_the_changeform_offers_the_ban_as_a_labelled_choice(client, superuser, school):  # noqa: F811
    pref = _pref(school, UserFactory().pk)
    TeacherPreference.objects.filter(pk=pref.pk).update(max_last_periods=0)
    client.force_login(superuser)

    page = client.get(
        reverse("admin:operations_teacherpreference_change", args=[pref.pk])
    ).content.decode()

    block = re.search(r'<select[^>]*name="max_last_periods"[^>]*>(.*?)</select>', page, re.S).group(
        1
    )
    assert re.search(r'<option value="0"[^>]* selected', block) and "لا سابعةَ إطلاقاً" in block


# ── فحص الجدوى: السابعةُ تخرج من السعة ──────────────────────────────


@pytest.mark.django_db
def test_feasibility_capacity_loses_the_seventh_when_it_is_banned(school):
    from tests.test_schedule_feasibility import SEVEN_BACK_TO_BACK, a_bell

    a_bell(school, None, SEVEN_BACK_TO_BACK)
    general, _ = sf.binding_daily_cap(school, frozenset({""}), (), {}, 7, None, first_cap=None)
    banned, source = sf.binding_daily_cap(school, frozenset({""}), (), {}, 7, 0, first_cap=None)

    assert banned < general, "منعُ السابعة ينقص السعة"
    assert "HC8" in source


# ── المُقيِّم: سابعةٌ لمعلّمٍ ممنوع = مخالفةٌ صلبة ───────────────────


@pytest.mark.django_db
def test_the_evaluator_flags_a_seventh_for_a_banned_teacher_and_not_for_a_general_one(
    run_scene,  # noqa: F811
):
    slots = run_scene.slots((0, 0, 7))
    general = evaluate_slots(run_scene.school, YEAR, slots)
    pref = _pref(run_scene.school, run_scene.teacher)
    TeacherPreference.objects.filter(pk=pref.pk).update(max_last_periods=0)

    banned = evaluate_slots(run_scene.school, YEAR, slots)

    assert "HC8" not in general.hard_breaches
    assert banned.hard_breaches.get("HC8") == 1

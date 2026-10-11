"""سياسةُ تخفيف التلاصق المدرسيّة: مصدرٌ واحد للمولّد والمُقيِّم وفحص الجدوى (D-382م، W-20261011-007)."""

from types import SimpleNamespace

import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

from core.models import AuditLog
from operations import schedule_feasibility as sf
from operations.admin import ScheduleRelaxationPolicyAdmin
from operations.models import ScheduleRelaxationPolicy
from operations.schedule_evaluator import evaluate_slots
from operations.schedule_relaxation import (
    STRICT_RUN_CAP,
    relaxed_run_cap,
    rule_sentence,
    school_policy,
)
from operations.scheduler_v2 import runner
from tests.conftest import UserFactory
from tests.test_schedule_evaluator import YEAR, run_scene  # noqa: F401 — التركيبةُ نفسُها للمُقيِّم

pytestmark = pytest.mark.django_db


@pytest.fixture
def open_scene(run_scene):  # noqa: F811
    """المشهدُ نفسُه بلا صفٍّ صارم: المدرسةُ تأخذ الافتراضَ (= قاعدة الجدول الحيّ)."""
    ScheduleRelaxationPolicy.objects.filter(school=run_scene.school).delete()
    return run_scene


def test_the_defaults_are_the_live_schedule_rules_for_everyone(school):
    policy = school_policy(school)

    assert policy.pk is not None and not ScheduleRelaxationPolicy.objects.exists()
    assert policy.as_spec() == {
        "touch_relaxed_all": True,
        "run_cap": 2,
        "no_6_7": True,
        "triples_by_number": True,
    }
    assert relaxed_run_cap(school) == 2


def test_turning_the_relaxation_off_restores_the_strict_rule(school):
    ScheduleRelaxationPolicy.objects.create(school=school, relax_touch_for_all=False)

    assert relaxed_run_cap(school) == STRICT_RUN_CAP
    assert "touch_relaxed_all" not in school_policy(school).as_spec()


def test_the_evaluator_accepts_a_pair_by_default_and_names_it_as_eased(open_scene):
    slots = open_scene.slots((0, 0, 1), (1, 0, 2), (2, 1, 1))

    result = evaluate_slots(open_scene.school, YEAR, slots)

    assert "HC5" not in result.hard_breaches and result.eased == {"HC5": 1}


def test_the_evaluator_still_refuses_three_in_a_row_under_the_default(open_scene):
    result = evaluate_slots(
        open_scene.school, YEAR, open_scene.slots((0, 0, 1), (1, 0, 2), (2, 0, 3))
    )

    assert result.hard_breaches.get("HC5", 0) >= 1


def test_a_strict_school_row_makes_the_evaluator_refuse_the_pair_again(run_scene):  # noqa: F811
    result = evaluate_slots(
        run_scene.school, YEAR, run_scene.slots((0, 0, 1), (1, 0, 2), (2, 1, 1))
    )

    assert result.hard_breaches.get("HC5") == 1 and result.eased == {}


def test_the_model_and_the_policy_agree_on_everyone_without_naming_teachers():
    """علمُ «للجميع» يخفّف كلَّ معلّمٍ ولو لم يُسمَّ، مثلُ القائمة المسمّاة تماماً."""
    from tests.test_scheduler_v2_hard import feasible, make

    inp = make([("C1", "S1", "T1", "", 1), ("C2", "S2", "T1", "", 1), ("C3", "S3", "T1", "", 1)])
    pair = [(0, 0, 1), (1, 0, 2)]
    triple = [(0, 0, 1), (1, 0, 2), (2, 0, 3)]

    assert feasible(inp, pair) is False
    assert feasible(inp, pair, touch_relaxed_all=True, touch_relaxed_run_cap=2) is True
    assert feasible(inp, triple, touch_relaxed_all=True, touch_relaxed_run_cap=2) is False


def test_feasibility_measures_the_day_with_the_same_relaxed_cap(open_scene):
    """سبعُ حصصٍ متلاصقة: تتّسع لأربعٍ صارمةً وخمسٍ بسقف 2 — فلا يرفض الفحصُ ما يقبله النموذج."""
    school = open_scene.school
    assert sf._band_day_cap(school, frozenset(), "regular", memo={}) == 5

    ScheduleRelaxationPolicy.objects.create(school=school, relax_touch_for_all=False)
    assert sf._band_day_cap(school, frozenset(), "regular", memo={}) == 4


def test_the_admin_records_before_and_after_without_any_teacher_name(school):
    request = RequestFactory().post("/")
    request.user = admin_user = UserFactory()
    site = ScheduleRelaxationPolicyAdmin(ScheduleRelaxationPolicy, AdminSite())
    obj = ScheduleRelaxationPolicy(school=school)

    site.save_model(request, obj, form=SimpleNamespace(), change=False)
    obj.no_6_7 = False
    site.save_model(request, obj, form=SimpleNamespace(), change=True)

    events = list(
        AuditLog.objects.filter(school=school, object_id=str(obj.pk)).order_by("timestamp")
    )
    assert [e.changes["event"] for e in events] == ["schedule_relaxation_policy_changed"] * 2
    assert events[1].changes["before"]["no_6_7"] is True
    assert events[1].changes["after"]["no_6_7"] is False
    assert obj.updated_by == admin_user


def test_the_runner_reads_the_school_policy_and_a_run_specific_file_overrides_it(school):
    base = runner.with_school_policy(runner.SolverConfig(), school)
    spec = dict(base.relaxations)

    assert spec == {
        "no_6_7": True,
        "run_cap": 2,
        "touch_relaxed_all": True,
        "triples_by_number": True,
    }
    assert runner.options_from_relaxations(spec)["touch_relaxed_all"] is True

    own = runner.SolverConfig(relaxations=(("no_6_7", False),))
    assert dict(runner.with_school_policy(own, school).relaxations)["no_6_7"] is False


def test_a_strict_school_hands_the_runner_no_touch_relaxation(school):
    ScheduleRelaxationPolicy.objects.create(school=school, relax_touch_for_all=False)

    spec = dict(runner.with_school_policy(runner.SolverConfig(), school).relaxations)

    assert "touch_relaxed_all" not in spec and "run_cap" not in spec


def test_the_failure_note_names_the_rule_in_force_or_says_there_is_none(school):
    on = runner.with_school_policy(runner.SolverConfig(), school)
    assert "إعداد المدرسة" in runner._rule_note(on)
    assert "2" in runner._rule_note(on)

    assert rule_sentence({}) == "القاعدة السارية: بلا تخفيفات"
    off = ScheduleRelaxationPolicy(
        school=school, relax_touch_for_all=False, no_6_7=False, triples_by_number=False
    )
    assert (
        runner._rule_note(runner.SolverConfig(relaxations=tuple(off.as_spec().items())))
        == "القاعدة السارية: بلا تخفيفات"
    )

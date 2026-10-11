"""[SCHEDULE] تشخيصُ INFEASIBLE في V2: الرسالةُ تسمّي القيدَ والمعلّمَ بدل «القيودُ متعارضة» وحدَها (W-20261011-005).

الحالةُ الحيّة (فشلُ 17:01 على الإنتاج بعد 2.89ث): INFEASIBLE بلا اسمٍ. وعلى البيانات المزروعة عُزلت بمعلّمٍ واحدٍ لا يتّسع
جدولُه إلّا في الحصص الأولى والخامسة والسادسة والسابعة: HC5 (لا تلاصق) وHC8 (سقفُ السابعة) معاً. هنا النموذجُ نفسُه
مصغَّراً: معلّمٌ بخمسَ عشرةَ حصّةً في ثلاثِ شعب محجوبٌ عنه 2–4 كلَّ يوم، ومعلّمٌ ثانٍ سليم.
"""

import pytest

from operations.models import ScheduleGeneration
from operations.scheduler_v2 import runner
from tests.test_scheduler_v2_hard import make

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"
CONFIG = runner.SolverConfig(seed=11, workers=2, max_seconds=5)
BLOCKED = "T1"
CORE_CODES = {"HC5", "HC8", "HC22"}


def _inputs():
    rows = [(f"C{i}", "MATH", BLOCKED, "", 5) for i in range(3)] + [("C3", "ENG", "T2", "", 4)]
    inp = make(rows)
    inp.ex_period = frozenset((BLOCKED, day, period) for day in range(5) for period in (2, 3, 4))
    return inp


@pytest.fixture(autouse=True)
def _no_real_objective(monkeypatch):
    monkeypatch.setattr(runner, "default_objective", lambda: None)


def test_the_blocked_teacher_alone_is_named_with_the_conflicting_codes():
    diagnosis = runner.diagnose_infeasibility(_inputs(), CONFIG, budget_seconds=60)

    assert diagnosis.teachers == (BLOCKED,)
    assert diagnosis.loads == {BLOCKED: 15} and diagnosis.teachers_total == 2
    assert 2 <= len(diagnosis.codes) <= 3 and set(diagnosis.codes) <= CORE_CODES
    assert diagnosis.switchable_cures and diagnosis.minimal and diagnosis.complete


def test_the_sentence_gives_arabic_titles_and_the_teacher_id_with_load_but_no_name():
    diagnosis = runner.diagnose_infeasibility(_inputs(), CONFIG, budget_seconds=60)

    text = diagnosis.sentence()

    assert text.startswith("السببُ: المعلّمُ T1 (15 حصّة) لا يمكن جدولةُ إسنادِه وحدَه")
    assert "«معلّمٌ يقف حصّتين متّصلتين بلا استراحة» (HC5)" in text
    assert "معاً ولا يكفي إيقافُ أحدِها وحدَه" in text


def test_run_adds_the_diagnosis_to_the_infeasible_message(school):
    result, _ = runner.run(school, YEAR, CONFIG, inputs=_inputs())

    assert not result.ok and result.reason == "infeasible"
    assert result.message.startswith("مستحيلٌ بالبرهان (INFEASIBLE): القيودُ متعارضة. السببُ:")
    assert "(15 حصّة)" in result.message
    assert result.diagnosis is not None and result.diagnosis.teachers == (BLOCKED,)


def test_a_failed_generation_keeps_the_diagnosis_in_snapshot_and_message(school):
    generation = ScheduleGeneration.objects.create(
        school=school, academic_year=YEAR, status="running"
    )

    runner.run_generation(generation, CONFIG, inputs=_inputs())

    generation.refresh_from_db()
    assert generation.status == "failed" and "السببُ:" in generation.error_message
    snapshot = generation.config_snapshot["diagnosis"]
    assert snapshot["teachers"] == [BLOCKED] and snapshot["complete"] is True
    assert set(snapshot["codes"]) <= CORE_CODES


def test_an_exhausted_budget_returns_an_incomplete_diagnosis_instead_of_hanging():
    diagnosis = runner.diagnose_infeasibility(_inputs(), CONFIG, budget_seconds=0.0)

    assert diagnosis.complete is False and diagnosis.probes == 0
    assert "غيرُ مكتمل" in diagnosis.sentence()


def test_a_diagnosis_crash_never_hides_the_proven_infeasibility(school, monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("عطلٌ في التشخيص")

    monkeypatch.setattr(runner, "diagnose_infeasibility", boom)

    result, _ = runner.run(school, YEAR, CONFIG, inputs=_inputs())

    assert result.reason == "infeasible" and result.diagnosis is None
    assert result.message == "مستحيلٌ بالبرهان (INFEASIBLE): القيودُ متعارضة"


def test_an_injected_solver_skips_the_diagnosis_that_contract_tests_rely_on(school, monkeypatch):
    def never(*_args, **_kwargs):
        raise AssertionError("لا يُشغَّل التشخيصُ على حلّالٍ مُحقَن")

    monkeypatch.setattr(runner, "diagnose_infeasibility", never)
    built = type("Built", (), {"model": None, "inputs": None, "x": {}})()

    result, _ = runner.run(
        school,
        YEAR,
        CONFIG,
        inputs=_inputs(),
        builder=lambda inputs: built,
        solver=lambda built, config: runner.SolveReport("INFEASIBLE", "", 1, 1, 0.0),
        objective=lambda built, inputs: None,
    )

    assert result.reason == "infeasible" and result.diagnosis is None

"""[SCHEDULE-V2] تشخيصُ الاستحالة: الرسالةُ تسمّي القيودَ المتعارضة بدل «القيود متعارضة» (طوارئ D-346م).

على الإنتاج (2026-10-11 17:01) فشل توليدٌ بـ«مستحيلٌ بالبرهان: القيودُ متعارضة» بلا أيّ قيد. فالنواةُ تُستخرج
بفرضيّات CP-SAT (assumptions) على النموذج نفسِه، وتُصغَّر، وتُذكر بأسمائها في رسالة الفشل.
"""

from types import SimpleNamespace

from operations.scheduler_v2 import diagnosis, runner
from operations.scheduler_v2.model import ModelOptions
from tests.test_scheduler_v2_hard import make


def _joint_with_one_teacher():
    """مهمّةٌ مشتركةٌ بمعلّمٍ واحد: مستحيلةٌ بالبرهان (AS-2)."""
    return make([("C1", "S1", "T1", "", 2, "J"), ("C1", "S2", "T1", "", 2, "J")])


def test_the_core_of_a_proven_conflict_is_named_by_code():
    found = diagnosis.diagnose(_joint_with_one_teacher(), ModelOptions(), max_seconds=30, workers=1)

    assert found.status == "INFEASIBLE"
    assert found.core, "النواةُ لا تكون فارغةً حين تكون القيودُ المعدودةُ سببَ الاستحالة"
    assert set(found.core) <= set(found.codes)
    assert found.untagged == 0 or found.core, "كلُّ قيدٍ معدود يخضع لفرضيّته"


def test_a_feasible_model_has_no_core():
    inp = make([("C1", "S1", "T1", "", 2)])

    found = diagnosis.diagnose(inp, ModelOptions(), max_seconds=30, workers=1)

    assert found.status in ("OPTIMAL", "FEASIBLE")
    assert found.core == []


def test_the_message_names_each_constraint_with_its_title(monkeypatch):
    fake = diagnosis.Diagnosis(status="INFEASIBLE", core=["HC5", "HC8"])
    monkeypatch.setattr(diagnosis, "diagnose", lambda *a, **k: fake)

    message = runner.infeasible_message(SimpleNamespace(), runner.SolverConfig())

    assert message.startswith(runner.INFEASIBLE_BASE)
    assert "HC5 (" in message and "HC8 (" in message
    assert "معلّمٌ يقف حصّتين متّصلتين بلا استراحة" in message


def test_a_failed_diagnosis_never_masks_the_verdict(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("تعذّر")

    monkeypatch.setattr(diagnosis, "diagnose", boom)

    message = runner.infeasible_message(_joint_with_one_teacher(), runner.SolverConfig())

    assert message == runner.INFEASIBLE_BASE


def test_an_empty_core_keeps_the_plain_message(monkeypatch):
    monkeypatch.setattr(
        diagnosis, "diagnose", lambda *a, **k: diagnosis.Diagnosis(status="INFEASIBLE", core=[])
    )

    assert (
        runner.infeasible_message(_joint_with_one_teacher(), runner.SolverConfig())
        == runner.INFEASIBLE_BASE
    )

"""بوّابةُ الدمج الآليّ: أحدثُ تشغيلٍ لكلّ فحصٍ بالاسم (W-20261105-002).

GitHub يُبقي كلَّ تشغيلات الفحص للرأس نفسه في statusCheckRollup؛ فحصٌ أُعيد تشغيله يبقى فيه قديمٌ فاشلٌ بجانب الجديد الناجح.
ما يحرسه هذا الملفّ: أنّ الحكمَ يُبنى على الأحدث وحده، وأنّ الفحصَ المعلَّقَ يُرفض، وأنّ جلبَ البيانات مُعطًى حقنيٌّ لا شبكة فيه.
"""

import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "auto_merge_gate", ROOT / "scripts" / "auto_merge_gate.py"
)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

APPROVED_BODY = "اعتُمد من المالك على 8500 — 2026-11-05"


def _pr(checks, body=APPROVED_BODY):
    return {
        "body": body,
        "files": [{"path": "templates/base/base.html"}],
        "statusCheckRollup": checks,
    }


def _run(name, state, started, completed=None):
    return {
        "name": name,
        "state": state,
        "startedAt": started,
        "completedAt": completed,
    }


def test_older_failure_newer_success_same_name_is_accepted():
    # الصورةُ الأصليّة للعلّة: «سطرُ الاعتماد مطابقٌ للرأس» احمرّ أوّلاً ثم اخضرّ بعد كتابة السطر.
    checks = [
        _run("سطرُ الاعتماد مطابقٌ للرأس", "FAILURE", "2026-11-05T07:35:00Z", "2026-11-05T07:36:00Z"),
        _run("سطرُ الاعتماد مطابقٌ للرأس", "SUCCESS", "2026-11-05T08:14:00Z", "2026-11-05T08:15:00Z"),
    ]
    ok, reasons = gate.evaluate_data(_pr(checks))
    assert ok, reasons


def test_older_success_newer_failure_same_name_is_rejected():
    checks = [
        _run("pytest", "SUCCESS", "2026-11-05T07:35:00Z", "2026-11-05T07:36:00Z"),
        _run("pytest", "FAILURE", "2026-11-05T08:14:00Z", "2026-11-05T08:15:00Z"),
    ]
    ok, reasons = gate.evaluate_data(_pr(checks))
    assert not ok
    assert any("فحصٌ فاشل: pytest (FAILURE)" in r for r in reasons)


def test_pending_check_is_rejected():
    checks = [_run("pytest", "PENDING", "2026-11-05T08:14:00Z")]
    ok, reasons = gate.evaluate_data(_pr(checks))
    assert not ok
    assert any("لم يكتمل بعدُ: pytest" in r for r in reasons)


def test_newer_pending_run_beats_older_success():
    # تشغيلٌ جديدٌ معلَّقٌ فوق قديمٍ ناجح: الحكمُ للمعلَّق لا للقديم.
    checks = [
        _run("pytest", "SUCCESS", "2026-11-05T07:35:00Z", "2026-11-05T07:36:00Z"),
        _run("pytest", "IN_PROGRESS", "2026-11-05T08:14:00Z"),
    ]
    ok, reasons = gate.evaluate_data(_pr(checks))
    assert not ok
    assert any("لم يكتمل بعدُ: pytest" in r for r in reasons)


def test_context_name_is_grouped_like_name():
    # صيغةُ StatusContext تستعمل context بدل name.
    checks = [
        {
            "context": "ci/lint",
            "state": "FAILURE",
            "startedAt": "2026-11-05T07:35:00Z",
            "completedAt": "2026-11-05T07:36:00Z",
        },
        {
            "context": "ci/lint",
            "state": "SUCCESS",
            "startedAt": "2026-11-05T08:14:00Z",
            "completedAt": "2026-11-05T08:15:00Z",
        },
    ]
    ok, reasons = gate.evaluate_data(_pr(checks))
    assert ok, reasons


def test_latest_checks_keeps_unnamed_checks_separate():
    # فحصان بلا اسم لا يُدمجان: الناجحُ لا يُخفي الفاشل.
    checks = [{"state": "FAILURE"}, {"state": "SUCCESS"}]
    assert len(gate.latest_checks(checks)) == 2
    ok, _ = gate.evaluate_data(_pr(checks))
    assert not ok


def test_missing_approval_line_still_rejected():
    checks = [_run("pytest", "SUCCESS", "2026-11-05T08:14:00Z", "2026-11-05T08:15:00Z")]
    ok, reasons = gate.evaluate_data(_pr(checks, body="بلا سطر اعتماد"))
    assert not ok
    assert any("سطرُ اعتماد المالك" in r for r in reasons)

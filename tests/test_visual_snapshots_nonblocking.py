"""[IDENTITY] فحصُ لقطات الهويّة (VI-13) غيرُ حاجبٍ للنشر على push — حارسٌ نصّيٌّ لسير العمل (D-277م، W-20261008-016).

أمرُ المالك المباشر (2026-10-08): الفحصُ استشاريٌّ بنصّه ولا يحجب نشراً. وكان فشلُه على push إلى main يُحمّر مجموعةَ الفحوص فيتخطّى Railway
النشرَ («Wait for CI»: أيُّ check-run فاشلٍ يوقفه ولو لم يكن مطلوباً بحماية الفرع). هذا الحارسُ يمنع أن يعود الفشلُ حاجباً بصمت، ويمنع
الأذى المرافق: أساسٌ يُرفع من تشغيلٍ فاشل، أو بحثٌ عن الأساس بـ«أحدث تشغيلٍ ناجح» وقد صار الفاشلُ ناجحاً.
"""

from __future__ import annotations

import pathlib

import yaml

PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / ".github"
    / "workflows"
    / "visual-snapshots.yml"
)
WORKFLOW = yaml.safe_load(PATH.read_text(encoding="utf-8"))
STEPS = WORKFLOW["jobs"]["snapshots"]["steps"]


def _step(name_part: str) -> dict:
    return next(s for s in STEPS if name_part in str(s.get("name", "")))


def test_a_failure_on_push_does_not_fail_the_job_but_a_pull_request_still_can():
    snap = _step("اللقطات (حتميّةٌ")
    assert snap["id"] == "snap"
    assert "github.event_name == 'push'" in str(snap["continue-on-error"])


def test_the_snapshot_job_itself_is_not_marked_continue_on_error():
    # التعطيلُ على الخطوة لا المهمّة: مهمّةٌ بـcontinue-on-error تُعرض فاشلةً في check-run وتبقى تحجب «Wait for CI».
    assert "continue-on-error" not in WORKFLOW["jobs"]["snapshots"]


def test_the_baseline_is_uploaded_only_from_a_real_success_not_from_a_tolerated_failure():
    upload = _step("رفعُ أساس main")
    assert "steps.snap.outcome == 'success'" in upload["if"]
    assert "success()" not in upload["if"]


def test_the_baseline_is_looked_up_by_artifact_not_by_the_latest_successful_run():
    download = _step("أساسُ main")
    assert "actions/artifacts?name=visual-baseline" in download["run"]
    assert "gh run list" not in download["run"]


def test_a_tolerated_failure_leaves_a_visible_warning_and_summary():
    warn = _step("تحذيرٌ")
    assert "steps.snap.outcome == 'failure'" in warn["if"]
    assert "::warning" in warn["run"] and "GITHUB_STEP_SUMMARY" in warn["run"]


def test_the_check_stays_out_of_the_mandatory_gate():
    gate = PATH.parent / "ci.yml"
    if gate.exists():
        assert "visual-snapshots" not in gate.read_text(encoding="utf-8")

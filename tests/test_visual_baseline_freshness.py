"""تقادمُ أساس اللقطات يُعالَج داخل تشغيل الطلب لا بـ`push` إلى main (W-20261024-003).

الأساسُ يُرفع يومياً فقط، فبعد دمجٍ يمسّ الصفحات يرى الطلبُ فرقَ main (#1255: 6 لقطاتٍ زائفة).
قرارُ المالك 2026-10-14: لا check-run إضافياً على main يؤخّر Railway «Wait for CI».
فالحلُّ خطوةٌ تبني الأساسَ من رأس main عند التقادم، وهذا الاختبارُ يثبّت شكلَها وحدودَها.
"""

import pathlib

import yaml

WF = pathlib.Path(__file__).resolve().parent.parent / ".github/workflows/visual-snapshots.yml"


def _wf():
    return yaml.safe_load(WF.read_text(encoding="utf-8"))


def _steps():
    return (
        _wf()["jobs"]["snapshots"]["steps"]
        if "snapshots" in _wf()["jobs"]
        else next(iter(_wf()["jobs"].values()))["steps"]
    )


def _step(fragment):
    return next(s for s in _steps() if fragment in s.get("name", ""))


def test_no_push_trigger_on_main():
    on = _wf().get("on") or _wf().get(True)
    assert "push" not in on, "قرارُ المالك 2026-10-14: لا trigger على push إلى main"


def test_refresh_step_exists_for_pull_requests_only_and_is_non_blocking():
    st = _step("تجديدُ الأساس")
    assert "pull_request" in st["if"]
    assert st.get("continue-on-error") is True


def test_refresh_runs_between_baseline_download_and_snapshots():
    names = [s.get("name", "") for s in _steps()]
    i_dl = next(i for i, n in enumerate(names) if "أساسُ main" in n)
    i_ref = next(i for i, n in enumerate(names) if "تجديدُ الأساس" in n)
    i_snap = next(i for i, n in enumerate(names) if "اللقطات" in n and "حتميّة" in n)
    assert i_dl < i_ref < i_snap


def test_download_exports_baseline_sha_and_refresh_compares_to_main_head():
    assert "VISUAL_BASELINE_SHA=" in _step("أساسُ main")["run"]
    run = _step("تجديدُ الأساس")["run"]
    assert "commits/main" in run and "compare/" in run
    assert "docs/" in run, "دمجُ الوثائق وحدَها لا يُقادم الأساس"
    assert "git worktree add" in run
    assert "VISUAL_BASELINE_DIR=" in run
    assert run.rstrip().endswith(
        "python manage.py migrate --noinput"
    ), "إعادةُ ترحيل القاعدة لمخطّط الطلب"

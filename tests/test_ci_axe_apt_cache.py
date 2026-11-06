"""حارسُ ذاكرة حزم apt لوظيفة axe-a11y — W-20261106-010.

مرآةُ azure.archive.ubuntu.com البطيئة أكلت مهلةَ الوظيفة (20 دقيقة) مرّتين. الحلّ: حزمُ .deb من ذاكرة main.
الطلباتُ تقرأ ذاكرةَ main فقط، وaxe-a11y لا تعمل على push، فيلزم حفظٌ من وظيفةٍ تعمل على push.
يقرأ YAML بلا شبكة.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "quality-gate.yml"
RESTORE = "actions/cache/restore@0057852bfaa89a56745cba8c7296529d2fc39830 # v4"
SAVE = "actions/cache/save@0057852bfaa89a56745cba8c7296529d2fc39830 # v4"
CONF_MARK = "Dir::Cache::archives"


def _jobs() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def _index(steps: list[dict], pred) -> int:
    for i, step in enumerate(steps):
        if pred(step):
            return i
    raise AssertionError("الخطوة المطلوبة غائبة")


def _runs_apt(step: dict) -> bool:
    run = step.get("run") or ""
    return "apt-get" in run or "playwright install" in run


def test_axe_restores_cache_before_first_apt_step():
    steps = _jobs()["axe-a11y"]["steps"]
    conf = _index(steps, lambda s: CONF_MARK in (s.get("run") or ""))
    restore = _index(steps, lambda s: str(s.get("uses", "")).startswith("actions/cache/restore@"))
    first_apt = _index(steps, _runs_apt)
    assert conf < restore < first_apt


def test_restore_is_pinned_and_key_has_os_playwright_and_package_list_hash():
    steps = _jobs()["axe-a11y"]["steps"]
    step = steps[
        _index(steps, lambda s: str(s.get("uses", "")).startswith("actions/cache/restore@"))
    ]
    raw = WORKFLOW.read_text(encoding="utf-8")
    assert RESTORE in raw
    key = step["with"]["key"]
    assert "runner.os" in key
    assert "AXE_PLAYWRIGHT_PIN" in key
    # قائمة الحزم متغيّرٌ في الملف نفسه، فبصمة الملف هي بصمة القائمة
    assert "hashFiles('.github/workflows/quality-gate.yml')" in key
    assert yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["env"]["AXE_APT_PACKAGES"].strip()


def test_missing_cache_does_not_fail_the_job():
    """غياب الذاكرة = تنزيلٌ من المرآة: الاستعادةُ لا تُفشل عند الغياب، ولا تخفيضَ لمهلة الوظيفة."""
    job = _jobs()["axe-a11y"]
    steps = job["steps"]
    step = steps[
        _index(steps, lambda s: str(s.get("uses", "")).startswith("actions/cache/restore@"))
    ]
    assert "fail-on-cache-miss" not in step["with"]
    assert job["timeout-minutes"] == 20


def test_conf_action_sets_user_owned_archives_and_keeps_downloads():
    for job in ("axe-a11y", "axe-apt-cache"):
        steps = _jobs()[job]["steps"]
        text = steps[_index(steps, lambda s: CONF_MARK in (s.get("run") or ""))]["run"]
        assert "/etc/apt/apt.conf.d/" in text
        assert 'APT::Keep-Downloaded-Packages "true"' in text


def test_save_runs_from_a_job_that_runs_on_push_to_main():
    jobs = _jobs()
    saver = [
        (name, job)
        for name, job in jobs.items()
        if any(s.get("uses") == SAVE.split(" #")[0] or s.get("uses") == SAVE for s in job["steps"])
    ]
    assert saver, "لا وظيفة تحفظ الذاكرة"
    raw = WORKFLOW.read_text(encoding="utf-8")
    assert SAVE in raw
    for name, job in saver:
        assert name != "axe-a11y"
        assert "github.event_name == 'push'" in job["if"], name
        steps = job["steps"]
        assert (
            steps[
                _index(steps, lambda s: str(s.get("uses", "")).startswith("actions/cache/restore@"))
            ]["with"].get("lookup-only")
            is True
        )
        assert _index(steps, lambda s: str(s.get("uses", "")).startswith("actions/cache/save@")) > (
            _index(steps, _runs_apt)
        )
    # push يقتصر على main في هذا الملف
    on = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert (on.get("on") or on.get(True))["push"]["branches"] == ["main"]


def test_save_job_uses_same_key_and_paths_as_restore():
    jobs = _jobs()
    axe = jobs["axe-a11y"]["steps"]
    save_job = jobs["axe-apt-cache"]["steps"]
    r = axe[_index(axe, lambda s: str(s.get("uses", "")).startswith("actions/cache/restore@"))]
    s = save_job[
        _index(save_job, lambda s: str(s.get("uses", "")).startswith("actions/cache/save@"))
    ]
    assert r["with"]["key"] == s["with"]["key"]
    assert r["with"]["path"] == s["with"]["path"]

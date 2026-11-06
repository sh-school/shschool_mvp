"""حارسُ ذاكرة حزم apt لوظيفتَي axe-a11y وe2e — W-20261106-015.

مرآةُ azure.archive.ubuntu.com تبطؤ فتأكل مهلةَ الوظيفتين (20 دقيقة) قبل الاختبارات. الحلّ: حزمُ .deb من ذاكرةٍ تُحفظ من push إلى main.
يقرأ YAML بلا شبكة.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "quality-gate.yml"
RESTORE = "actions/cache/restore@0057852bfaa89a56745cba8c7296529d2fc39830"
SAVE = "actions/cache/save@0057852bfaa89a56745cba8c7296529d2fc39830"
CONSUMERS = ("axe-a11y", "e2e")
SAVER = "apt-deb-cache-save"


def _jobs() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def _touches_apt(step: dict) -> bool:
    """خطوةٌ تشغّل apt: apt-get، أو playwright (يشغّله بـ--with-deps)، أو إجراءٌ مركَّبٌ يثبّت حزماً."""
    run = step.get("run") or ""
    uses = step.get("uses") or ""
    return (
        "apt-get" in run
        or "playwright install" in run
        or uses.endswith("apt-resilient")
        or uses.endswith("native-postgres")
    )


def _first_index(steps: list[dict], pred) -> int:
    for i, step in enumerate(steps):
        if pred(step):
            return i
    raise AssertionError("الخطوةُ غائبة")


@pytest.mark.parametrize("job", CONSUMERS)
def test_conf_then_restore_precede_the_first_apt_step(job):
    steps = _jobs()[job]["steps"]
    conf = _first_index(steps, lambda s: "Dir::Cache::archives" in (s.get("run") or ""))
    restore = _first_index(steps, lambda s: s.get("uses", "").startswith(RESTORE))
    first_apt = _first_index(steps, _touches_apt)
    assert conf < restore < first_apt, (job, conf, restore, first_apt)


@pytest.mark.parametrize("job", CONSUMERS)
def test_conf_keeps_downloaded_packages_in_a_user_owned_dir(job):
    steps = _jobs()[job]["steps"]
    run = next(s["run"] for s in steps if "Dir::Cache::archives" in (s.get("run") or ""))
    assert "/etc/apt/apt.conf.d/" in run
    assert 'APT::Keep-Downloaded-Packages "true"' in run
    assert 'mkdir -p "$HOME/apt-archives/partial"' in run


@pytest.mark.parametrize("job", CONSUMERS)
def test_restore_never_fails_the_job_and_key_has_os_playwright_and_fingerprint(job):
    steps = _jobs()[job]["steps"]
    restore = next(s for s in steps if s.get("uses", "").startswith(RESTORE))
    assert not restore.get("fail-on-cache-miss")
    key = restore["with"]["key"]
    assert "runner.os" in key and "pytest-playwright-0.9.0" in key and "hashFiles(" in key


def test_saver_runs_only_on_push_to_main_and_saves_the_same_key():
    jobs = _jobs()
    saver = jobs[SAVER]
    assert saver["if"].strip() == "github.event_name == 'push'"
    triggers = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    on = triggers.get("on", triggers.get(True))
    assert on["push"]["branches"] == ["main"]
    steps = saver["steps"]
    lookup = next(s for s in steps if s.get("uses", "").startswith(RESTORE))
    assert lookup["with"]["lookup-only"] is True
    save = next(s for s in steps if s.get("uses", "").startswith(SAVE))
    assert save["with"]["key"] == lookup["with"]["key"]
    assert "cache-hit != 'true'" in save["if"]
    consumer_key = next(s for s in jobs["e2e"]["steps"] if s.get("uses", "").startswith(RESTORE))[
        "with"
    ]["key"]
    assert consumer_key == lookup["with"]["key"]


def test_saver_installs_the_same_packages_with_timeouts():
    steps = _jobs()[SAVER]["steps"]
    text = "\n".join(s.get("run") or "" for s in steps)
    for pkg in ("libcairo2-dev", "libpango1.0-dev", "pytest-playwright==0.9.0"):
        assert pkg in text
    assert "playwright install --with-deps chromium" in text
    assert "playwright install --with-deps webkit" in text
    for s in steps:
        if "apt-get install" in (s.get("run") or ""):
            assert isinstance(s.get("timeout-minutes"), int)


def test_consumer_timeouts_are_untouched():
    jobs = _jobs()
    assert jobs["axe-a11y"]["timeout-minutes"] == 20
    assert jobs["e2e"]["timeout-minutes"] == 20

"""أداةُ ما قبل الدفع تطابق فحوصَ CI السريعة ولا تنجرف عنها (W-20261002-030).

لو تغيّرت عتبةُ التعقيد أو استثناءاتُه أو إصدارُ ruff المثبَّت في `quality-gate.yml` ولم تتغيّر الأداةُ
المحلّيّة، قال المطوّرُ «نجح عندي» وسقط في CI — وهو بالضبط ما بُنيت الأداةُ لتفاديه.
"""

import importlib.util
import re
from pathlib import Path

_spec = importlib.util.spec_from_file_location("prepush_check", Path("scripts/prepush_check.py"))
prepush_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prepush_check)

WORKFLOW = Path(".github/workflows/quality-gate.yml").read_text(encoding="utf-8")
PRE_COMMIT = Path(".pre-commit-config.yaml").read_text(encoding="utf-8")


def test_the_radon_excludes_match_the_ci_complexity_step():
    assert prepush_check.RADON_EXCLUDE in WORKFLOW, "استثناءات radon محلّيّاً غير استثناءات CI"


def test_the_pre_commit_ruff_pin_matches_the_ci_pin():
    ci = re.search(r"pip install ruff==([\d.]+)", WORKFLOW)
    local = re.search(r"ruff-pre-commit\s+rev:\s*v([\d.]+)", PRE_COMMIT)
    assert ci and local, "لم يوجد تثبيتُ ruff في أحد المصدرين"
    assert ci.group(1) == local.group(1), "ruff المحلّيّ (pre-commit) غير ruff الذي يشغّله CI"


def test_the_mypy_env_matches_the_ci_step():
    for key, value in prepush_check.MYPY_ENV.items():
        assert f"{key}: {value}" in WORKFLOW, f"{key} في الأداة غير ما في CI"


def test_a_missing_tool_is_not_reported_as_a_pass(monkeypatch):
    monkeypatch.setattr(prepush_check.shutil, "which", lambda name: None)
    status, _ = prepush_check.check_secrets()
    assert status == prepush_check.MISSING
    status, _ = prepush_check.check_pre_commit_hook("ruff")()
    assert status == prepush_check.MISSING


def _all_pass(monkeypatch, **overrides):
    ok = lambda *a, **k: (prepush_check.OK, "")  # noqa: E731
    monkeypatch.setattr(prepush_check, "check_pre_commit_hook", lambda hook_id: ok)
    monkeypatch.setattr(prepush_check, "check_personal_data", ok)
    monkeypatch.setattr(prepush_check, "check_secrets", overrides.get("secrets", ok))
    monkeypatch.setattr(prepush_check, "check_complexity", overrides.get("complexity", ok))


def test_all_green_exits_zero(monkeypatch):
    _all_pass(monkeypatch)
    assert prepush_check.main([]) == 0


def test_one_failing_check_exits_one_even_if_another_is_missing(monkeypatch):
    _all_pass(
        monkeypatch,
        secrets=lambda all_files=False: (prepush_check.FAIL, "سرٌّ جديد"),
        complexity=lambda: (prepush_check.MISSING, "radon غائب"),
    )
    assert prepush_check.main([]) == 1


def test_a_missing_tool_exits_three_unless_allowed(monkeypatch):
    _all_pass(monkeypatch, complexity=lambda: (prepush_check.MISSING, "radon غائب"))
    assert prepush_check.main([]) == 3
    assert prepush_check.main(["--allow-missing"]) == 0

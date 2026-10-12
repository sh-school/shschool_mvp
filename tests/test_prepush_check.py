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
    # لا واجهةَ تغيّرت افتراضاً: خطوةُ الهويّة تُتخطّى فلا تُشغَّل الحرّاسُ الحقيقيّة في اختبارات الأداة.
    monkeypatch.setattr(prepush_check, "changed_paths_vs_merge_base", lambda: [])


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


# ── حرّاسُ الهويّة في prepush (W-20261011-002، D-376م) ─────────────────────────────────────


def test_only_templates_and_static_count_as_touching_the_interface():
    assert prepush_check.touches_interface(["templates/dashboard/a.html"])
    assert prepush_check.touches_interface(["core/views.py", "static/css/custom/x.css"])
    assert not prepush_check.touches_interface(["core/views.py", "tests/test_x.py", "docs/a.md"])
    # بادئةٌ لا اسمُ مجلّدٍ يشبهها: `templates_old/` و`staticfiles/` ليسا الواجهة.
    assert not prepush_check.touches_interface(["templates_old/a.html", "staticfiles/a.css"])


def test_the_three_identity_guards_of_d376_are_among_those_prepush_runs():
    added = {
        "tests/test_dead_classes.py",
        "tests/test_design_ratchet.py",
        "tests/test_tailwind_freeze.py",
    }
    assert added <= set(prepush_check.IDENTITY_GUARDS)
    for path in prepush_check.IDENTITY_GUARDS:
        assert Path(path).exists(), f"حارسٌ مذكورٌ في الأداة وغيرُ موجود: {path}"


def _stub_other_checks(monkeypatch):
    _all_pass(monkeypatch)


def test_a_commit_without_interface_files_skips_the_identity_guards(monkeypatch, capsys):
    _stub_other_checks(monkeypatch)
    monkeypatch.setattr(prepush_check, "changed_paths_vs_merge_base", lambda: ["core/views.py"])
    ran = []
    monkeypatch.setattr(
        prepush_check, "_run_identity_guards", lambda: ran.append(1) or (prepush_check.OK, "")
    )
    assert prepush_check.main([]) == 0
    assert not ran, "الحرّاس شُغّلت على إيداعٍ لا يمسّ الواجهة"
    assert "identity_ack" not in capsys.readouterr().out


def test_an_interface_commit_runs_the_guards_and_a_pass_prints_the_receipt_last(
    monkeypatch, capsys
):
    _stub_other_checks(monkeypatch)
    monkeypatch.setattr(prepush_check, "changed_paths_vs_merge_base", lambda: ["templates/a.html"])
    monkeypatch.setattr(prepush_check, "_run_identity_guards", lambda: (prepush_check.OK, ""))
    monkeypatch.setattr(prepush_check, "head8", lambda: "abcd1234")
    assert prepush_check.main([]) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "identity_ack: abcd1234 نجح"


def test_a_failing_identity_guard_blocks_and_the_last_line_says_failed(monkeypatch, capsys):
    _stub_other_checks(monkeypatch)
    monkeypatch.setattr(prepush_check, "changed_paths_vs_merge_base", lambda: ["static/css/x.css"])
    monkeypatch.setattr(
        prepush_check, "_run_identity_guards", lambda: (prepush_check.FAIL, "صنفٌ بلا تعريف")
    )
    monkeypatch.setattr(prepush_check, "head8", lambda: "abcd1234")
    assert prepush_check.main([]) == 1
    assert capsys.readouterr().out.strip().splitlines()[-1] == "identity_ack: abcd1234 سقط"


def test_an_unknown_diff_is_treated_as_touching_the_interface(monkeypatch):
    # لا merge-base (فرعٌ وحيد/سجلٌّ مبتور): الأحوط تشغيلُ الحرّاس لا تخطّيها.
    monkeypatch.setattr(prepush_check, "changed_paths_vs_merge_base", lambda: None)
    assert prepush_check.interface_touched() is True


def test_the_identity_step_has_its_own_time_budget_documented():
    assert prepush_check.IDENTITY_TIMEOUT_SECONDS >= 120
    assert "D-376" in Path("scripts/prepush_check.py").read_text(encoding="utf-8")

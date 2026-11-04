"""«يمسّ:» في وصف الطلب يفتح فئةً محظورةً لهذا الطلب وحده بفحصٍ إضافيّ أخضر (D-521م)."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "amg", Path(__file__).resolve().parent.parent / "scripts" / "auto_merge_gate.py"
)
amg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(amg)

APPROVE = "اعتُمد من المالك مباشرةً بلا معاينة 8500 — 2026-11-04"


def _eval(monkeypatch, body, paths, checks):
    monkeypatch.setattr(
        amg,
        "sh_json",
        lambda args: {
            "body": body,
            "files": [{"path": p} for p in paths],
            "statusCheckRollup": checks,
        },
    )
    return amg.evaluate("1", None)


def _ok(name):
    return {"name": name, "conclusion": "SUCCESS"}


def test_forbidden_path_without_declaration_stays_blocked(monkeypatch):
    ok, why = _eval(
        monkeypatch, APPROVE, ["core/migrations/0100_x.py"], [_ok("مدقّق الهجرات — Expand/Contract")]
    )
    assert not ok and any("محظورة" in r for r in why)


def test_declared_category_opens_only_its_own_paths(monkeypatch):
    body = APPROVE + "\nيمسّ: الهجرات"
    checks = [_ok("مدقّق الهجرات — Expand/Contract")]
    assert _eval(monkeypatch, body, ["core/migrations/0100_x.py"], checks)[0]
    ok, why = _eval(
        monkeypatch, body, ["core/migrations/0100_x.py", "core/security/keys.py"], checks
    )
    assert not ok and any("security" in r for r in why)


def test_declared_category_needs_its_extra_check_green(monkeypatch):
    body = APPROVE + "\nيمسّ: الهجرات"
    ok, why = _eval(
        monkeypatch,
        body,
        ["core/migrations/0100_x.py"],
        [{"name": "مدقّق الهجرات — Expand/Contract", "conclusion": "FAILURE"}],
    )
    assert not ok and any("يمسّ: الهجرات" in r for r in why)
    ok, why = _eval(monkeypatch, body, ["core/migrations/0100_x.py"], [_ok("Ruff")])
    assert not ok and any("يمسّ: الهجرات" in r for r in why)


def test_unknown_category_is_ignored(monkeypatch):
    assert amg.declared_touches("يمسّ: شيءٌ آخر") == set()
    assert amg.declared_touches("يمسّ: الأمن، الأدوار") == {"الأمن", "الأدوار"}

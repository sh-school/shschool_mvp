"""[CI] سطرُ أرقام الجودة وبيئةُ الفحص المطابقة لـCI (W-20261003-008): محلّلاتٌ بلا شبكةٍ ولا أدوات."""

import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import quality_numbers as qn  # noqa: E402


def test_parse_mypy_reads_the_ratchet_line():
    assert qn.parse_mypy("mypy: 1,324 خطأً في 122 ملفّاً (المسجَّل 1,324).") == "1324/122 (مسجَّل 1324)"
    assert qn.parse_mypy("لا شيء") is None


def test_parse_ruff_counts_concise_lines_and_zero_when_clean():
    assert qn.parse_ruff("All checks passed!\n") == 0
    assert qn.parse_ruff("a.py:1:1: F401 x\nb.py:2:3: E501 y\nFound 2 errors.\n") == 2
    assert qn.parse_ruff("") is None


def test_parse_radon_counts_only_function_rows():
    out = "core/a.py\n    F 10:0 big - E (35)\n    M 20:4 C.m - F (45)\n"
    assert qn.parse_radon(out) == 2
    assert qn.parse_radon("") == 0


def test_unmeasured_tools_are_labelled_not_zero():
    values = qn.measure(set(), run=lambda cmd, timeout=0: None)
    assert set(values.values()) == {qn.UNMEASURED}


def test_the_line_is_one_line_with_all_numbers():
    text = qn.line({"mypy": "1/1", "ruff": "0", "CC≥31": "0"})
    assert "\n" not in text and text.startswith("أرقام الجودة: ") and "ruff=0" in text


def test_ci_step_is_non_blocking_and_pins_match_the_gate():
    wf = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "quality-gate.yml").read_text(encoding="utf-8")
    )
    steps = wf["jobs"]["mypy"]["steps"]
    step = next(s for s in steps if "quality_numbers" in s.get("run", ""))
    assert step.get("continue-on-error") is True, "خطوةُ الأرقام لا تحكم"
    pins = dict(re.findall(r"(ruff|radon)==([\d.]+)", step["run"]))
    gate = (ROOT / ".github" / "workflows" / "quality-gate.yml").read_text(encoding="utf-8")
    for tool, ver in pins.items():
        assert f"{tool}=={ver}" in gate.replace(
            step["run"], ""
        ), f"إصدار {tool} يخالف وظيفته الأصليّة"


def test_compose_check_uses_the_gate_database_and_pinned_tools():
    compose = yaml.safe_load((ROOT / "docker-compose.check.yml").read_text(encoding="utf-8"))
    db = compose["services"]["db"]
    assert db["image"].startswith("postgres:16") and db["environment"]["POSTGRES_DB"] == "test_db"
    assert db["tmpfs"], "القاعدةُ تُعاد فارغةً بكلّ تشغيل"
    inside = (ROOT / "scripts" / "ci_check_inside.sh").read_text(encoding="utf-8")
    assert "requirements-mypy.txt" in inside and "quality_numbers.py --strict" in inside


def test_strict_flags_only_measured_breaches():
    assert qn.breaches({"mypy": "1165/121 (مسجَّل 1165)", "ruff": "0", "CC≥31": "0"}) == []
    assert qn.breaches({"mypy": "1170/121 (مسجَّل 1165)", "ruff": "2", "CC≥31": "0"}) == [
        "mypy فوق المسجَّل",
        "ruff فوق الصفر",
    ]
    assert qn.breaches({"mypy": qn.UNMEASURED, "ruff": qn.UNMEASURED, "CC≥31": qn.UNMEASURED}) == []

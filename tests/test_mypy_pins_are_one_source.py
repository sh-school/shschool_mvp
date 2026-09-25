"""[CI] إصداراتُ فاحص الأنواع مصدرٌ واحد: `requirements-mypy.txt` (OWN-30).

أعدادُ الأخطاء في `tests/mypy_ratchet_baseline.json` تخرج من mypy وstubs بإصداراتٍ بعينها. كان التطويرُ على
mypy 2.3.1 وdjango-stubs 6.1.1 (`requirements-dev.txt`) والبوّابةُ على 1.10.0 و5.0.2 (سطرٌ حرفيٌّ في
`quality-gate.yml`) — فيُسجَّل `--update` عدداً لا تراه البوّابة، ويُقاس محلّيّاً ما لا يحكم به CI. وdependabot يقترح
ترقيةَ سطر التطوير أسبوعيّاً فيتّسع الافتراقُ من جديد.

فالإصداراتُ الثلاثة في ملفٍّ واحد، يستدعيه التطويرُ بـ`-r` ويثبّتُ منه CI، ولا يقترح dependabot ترقيتَها، ولا يسجّل
`--update` عدداً من إصدارٍ غيرها.
"""

import json
import pathlib
import re

import pytest
import yaml

from tests import mypy_ratchet as ratchet

DEV = pathlib.Path("requirements-dev.txt")
GATE = pathlib.Path(".github/workflows/quality-gate.yml")
DEPENDABOT = pathlib.Path(".github/dependabot.yml")
WORKFLOWS = sorted(pathlib.Path(".github/workflows").glob("*.yml"))
#: `mypy==1.2.3` أو `django-stubs==…` حرفيّاً في سطرٍ (لا في تعليق).
LITERAL_PIN = re.compile(r"^[^#\n]*\b(?:mypy|django-stubs|djangorestframework-stubs)==\d", re.M)


def test_each_checker_package_is_pinned_exactly_once_in_the_pin_file():
    lines = [
        line.strip()
        for line in ratchet.PINS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    assert sorted(line.split("==")[0] for line in lines) == sorted(ratchet.PINNED)
    assert all(re.fullmatch(r"[a-z-]+==\d+(\.\d+)+", line) for line in lines), lines


def test_dev_requirements_reuse_the_pin_file_and_never_repin():
    text = DEV.read_text(encoding="utf-8")

    assert re.search(
        r"^-r requirements-mypy\.txt\s*$", text, re.M
    ), "requirements-dev.txt لا يستدعي ملفَّ الإصدارات"
    assert not LITERAL_PIN.search(
        text
    ), "إصدارٌ حرفيٌّ لفاحص الأنواع في requirements-dev.txt — مكانُه requirements-mypy.txt"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_no_workflow_pins_the_checker_literally(path):
    assert not LITERAL_PIN.search(
        path.read_text(encoding="utf-8")
    ), f"{path.name}: إصدارُ فاحص الأنواع حرفيٌّ في سير العمل — يثبَّت من requirements-mypy.txt"


def test_the_mypy_job_installs_from_the_pin_file():
    steps = yaml.safe_load(GATE.read_text(encoding="utf-8"))["jobs"]["mypy"]["steps"]

    installs = [
        step["run"] for step in steps if "run" in step and "requirements-mypy.txt" in step["run"]
    ]

    assert installs, "وظيفةُ mypy لا تثبّت من requirements-mypy.txt"


def test_dependabot_never_proposes_the_checker_versions():
    updates = yaml.safe_load(DEPENDABOT.read_text(encoding="utf-8"))["updates"]
    pip = next(u for u in updates if u["package-ecosystem"] == "pip")
    ignored_entirely = {
        i["dependency-name"] for i in pip.get("ignore", []) if not i.get("versions")
    }

    assert set(ratchet.PINNED) <= ignored_entirely, set(ratchet.PINNED) - ignored_entirely


# ── السقّاطةُ ترفض التسجيلَ من إصدارٍ غيرِ الثابت ──────────────────────────────────


def _as_if_installed(monkeypatch, version):
    monkeypatch.setattr(ratchet, "installed_version", lambda name: version)


def test_a_matching_environment_has_no_skew(monkeypatch):
    monkeypatch.setattr(ratchet, "installed_version", ratchet.pinned_version)

    assert ratchet.version_skew() == []


def test_a_missing_or_different_checker_is_reported(monkeypatch):
    _as_if_installed(monkeypatch, "")
    assert len(ratchet.version_skew()) == len(ratchet.PINNED)
    assert "غائب" in ratchet.version_skew()[0]

    _as_if_installed(monkeypatch, "99.0.0")
    assert all("99.0.0" in line for line in ratchet.version_skew())


def test_update_is_refused_before_measuring_when_the_checker_is_not_the_pinned_one(
    monkeypatch, tmp_path, capsys
):
    """التسجيلُ من إصدارٍ آخر يكتب عدداً لا تراه البوّابة — فلا يُقاس ولا يُكتب شيء."""
    baseline = tmp_path / "baseline.json"
    monkeypatch.setattr(ratchet, "BASELINE", baseline)
    _as_if_installed(monkeypatch, "99.0.0")

    def _must_not_run():
        raise AssertionError("قيس mypy رغم رفض --update")

    monkeypatch.setattr(ratchet, "measure", _must_not_run)

    assert ratchet.main(["--update"]) == 2

    assert not baseline.exists()
    assert "رُفض --update" in capsys.readouterr().out


def test_a_plain_run_on_a_skewed_environment_only_warns(monkeypatch, capsys):
    recorded = json.loads(ratchet.BASELINE.read_text(encoding="utf-8"))["files"]
    _as_if_installed(monkeypatch, "99.0.0")
    monkeypatch.setattr(ratchet, "measure", lambda: dict(recorded))

    assert ratchet.main([]) == 0

    assert "تحذير" in capsys.readouterr().out

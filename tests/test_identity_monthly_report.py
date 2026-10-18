"""[IDENTITY] التقريرُ الشهريّ لالتزام الهويّة (W-20261016-017) — الأرقامُ الأربعة والاتجاهُ بلا حجب."""

from __future__ import annotations

import datetime as dt
import json
import pathlib

import yaml

from scripts import identity_monthly_report as imr

TODAY = dt.date(2026, 11, 1)
KNOWN = {
    "hex_outside_tokens": 22,
    "important": 16,
    "inline_style": 110,
    "inline_templates": 19,
    "visual_gate": imr.UNMEASURED,
    "hex_detail": {"templates": 20, "css_rules": 2},
}


def test_the_first_report_prints_the_four_numbers_without_a_trend():
    report = imr.build(KNOWN, None, TODAY)
    values = {r["key"]: r["value"] for r in report["rows"]}
    assert values == {
        "hex_outside_tokens": 22,
        "important": 16,
        "inline_style": 110,
        "visual_gate": imr.UNMEASURED,
    }
    assert all("أوّل قياس" in r["trend"] for r in report["rows"])
    text = imr.render_markdown(report)
    for number in ("22", "16", "110", imr.UNMEASURED):
        assert number in text


def test_a_rising_number_shows_its_trend_and_does_not_fail():
    previous = imr.build({**KNOWN, "important": 10}, None, dt.date(2026, 10, 1))
    report = imr.build(KNOWN, previous, TODAY)
    important = next(r for r in report["rows"] if r["key"] == "important")
    assert important["trend"] == "▲ +6"
    assert next(r for r in report["rows"] if r["key"] == "inline_style")["trend"] == "═ 0"
    assert imr.main(["--no-write"]) == 0  # ارتفاعٌ أو لا، الخروج 0


def test_an_unmeasured_number_is_not_a_zero_and_has_no_trend():
    assert imr.trend(imr.UNMEASURED, 5) == "—"
    assert imr.trend(3, imr.UNMEASURED) == "—"
    assert imr.measure(None)["visual_gate"] == imr.UNMEASURED
    assert imr.measure(7)["visual_gate"] == 7


def test_the_run_writes_json_and_markdown_and_reads_the_previous_for_the_trend(tmp_path):
    assert imr.main(["--out", str(tmp_path)]) == 0
    first = json.loads((tmp_path / "monthly_report.json").read_text(encoding="utf-8"))
    assert (tmp_path / "monthly_report.md").exists()
    assert first["previous_date"] is None
    assert imr.main(["--out", str(tmp_path)]) == 0
    second = json.loads((tmp_path / "monthly_report.json").read_text(encoding="utf-8"))
    assert second["previous_date"] == first["date"]
    assert all(r["trend"] in {"═ 0", "—"} for r in second["rows"])


def test_the_workflow_runs_monthly_and_never_fails_on_a_number():
    root = pathlib.Path(__file__).resolve().parent.parent
    wf = yaml.safe_load(
        (root / ".github" / "workflows" / "identity-kpis.yml").read_text(encoding="utf-8")
    )
    crons = [s["cron"] for s in wf[True]["schedule"]]  # `on` يقرؤه YAML منطقياً True
    assert "0 3 1 * *" in crons
    steps = wf["jobs"]["monthly"]["steps"]
    step = next(s for s in steps if "identity_monthly_report" in str(s.get("run", "")))
    assert step.get("continue-on-error") is True


def test_the_headline_counts_are_raw_and_match_the_recorded_baseline_definitions():
    important, inline, templates = imr.raw_counts()
    sheets = pathlib.Path(__file__).resolve().parent.parent / "static" / "css" / "custom"
    assert important == sum(
        p.read_text(encoding="utf-8").count("!important") for p in sheets.rglob("*.css")
    )
    assert inline >= templates >= 0

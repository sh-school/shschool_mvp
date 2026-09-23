"""[ROADMAP] سكربتُ مؤشّرات التخطيط يعمل على الشجرة ويُخرج مؤشّراتِ LK1..LK5 معقولةً."""

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_measure_layout_kpis_reports_every_kpi():
    run = subprocess.run(
        [sys.executable, "scripts/measure_layout_kpis.py", str(ROOT), "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    out = json.loads(run.stdout)
    for key in (
        "LK1_pages_declaring_layout_pct",
        "LK2_breakpoints",
        "LK3_empty_state_coverage_pct",
        "LK4_role_dashboard_templates",
        "LK5_page_local_css_lines",
    ):
        assert key in out, key
    assert out["info_pages"] > 100
    assert 0 <= out["LK1_pages_declaring_layout_pct"] <= 100
    assert 0 <= out["LK3_empty_state_coverage_pct"] <= 100
    assert out["LK2_breakpoints"] >= 1

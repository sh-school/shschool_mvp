"""حارسُ خلوّ سير العمل من أيّ تجاهلٍ لمشورات pip-audit (W-20261026-012).

رُفع Twisted إلى 26.10.0 فأُصلحت المشوراتُ السبعُ التي كانت مأذونةً بالتجاهل (W-20261015-011 وW-20261021-002)،
فسقطت قائمةُ التجاهل ومهلةُ مراجعتها. وأيُّ `--ignore-vuln` جديدٌ يلزمه أمرُ المالك وبطاقتُه، لا إضافةٌ صامتة.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = (".github/workflows/security-scan.yml", ".github/workflows/quality.yml")


def test_no_advisory_is_ignored():
    for rel in WORKFLOWS:
        found = re.findall(r"--ignore-vuln\s+(\S+)", (ROOT / rel).read_text(encoding="utf-8"))
        assert not found, f"{rel}: تجاهلٌ غيرُ مأذون (يلزمه أمرُ المالك): {sorted(set(found))}"

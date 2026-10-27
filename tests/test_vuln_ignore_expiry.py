"""حارسُ انتهاء التجاهل الموثَّق للمشورات الستّ المأذونة (W-20261015-011 وW-20261021-002، أمر المالك).

التجاهلُ مؤقّتٌ: يفشل هذا الاختبارُ بعد 2026-11-14 فيُراجَع التجاهلُ أو يُرفع بدل أن يبقى منسيّاً، ولا يجوز أن يتّسع لمشورةٍ ثانية بلا أمر المالك.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = (".github/workflows/security-scan.yml", ".github/workflows/quality.yml")
ALLOWED = {
    "GHSA-8pqf-f4m5-798g",
    "GHSA-cwm5-jh59-mwxr",
    "GHSA-2qrf-pqgx-qh9v",
    "GHSA-3476-c5c2-fr73",
    "GHSA-53xc-49m8-p798",
    "GHSA-q7qq-6mhp-9rc4",
}
REVIEW_BY = datetime.date(2026, 11, 14)

# العلامةُ تُرضي سقّاطةَ الساعة (W-20261008-021) وتثبّت `timezone.now` وحدَه؛ أمّا `date.today()` أدناه فحقيقيٌّ عمداً لأنّه فخُّ الانتهاء.
pytestmark = pytest.mark.pin_clock


def _ignored(text: str) -> list[str]:
    return re.findall(r"--ignore-vuln\s+(\S+)", text)


def test_only_the_documented_advisories_are_ignored():
    for rel in WORKFLOWS:
        found = _ignored((ROOT / rel).read_text(encoding="utf-8"))
        assert found, f"{rel}: لا تجاهلَ موثَّقاً مع أنّه مقرَّر"
        assert set(found) <= ALLOWED, f"{rel}: تجاهلٌ غيرُ مأذون: {sorted(set(found) - ALLOWED)}"


def test_the_documented_ignore_has_not_expired():
    assert (
        datetime.date.today() <= REVIEW_BY
    ), "انتهت مهلةُ مراجعة التجاهل الموثَّق (2026-11-14): راجعِ المشورةَ وارفعِ التجاهلَ أو جدّدْه بأمر المالك"

"""حارسُ انتهاء التجاهل الموثَّق للمشورة GHSA-8pqf-f4m5-798g (W-20261015-011، أمر المالك 2026-10-15).

التجاهلُ مؤقّتٌ: يفشل هذا الاختبارُ بعد 2026-11-15 فيُراجَع التجاهلُ أو يُرفع بدل أن يبقى منسيّاً، ولا يجوز أن يتّسع لمشورةٍ ثانية بلا أمر المالك.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = (".github/workflows/security-scan.yml", ".github/workflows/quality.yml")
ALLOWED = {"GHSA-8pqf-f4m5-798g"}
REVIEW_BY = datetime.date(2026, 11, 15)

# العلامةُ تُرضي سقّاطةَ الساعة (W-20261008-021) وتثبّت `timezone.now` وحدَه؛ أمّا `date.today()` أدناه فحقيقيٌّ عمداً لأنّه فخُّ الانتهاء.
pytestmark = pytest.mark.pin_clock


def _ignored(text: str) -> list[str]:
    return re.findall(r"--ignore-vuln\s+(\S+)", text)


def test_only_the_documented_advisory_is_ignored():
    for rel in WORKFLOWS:
        found = _ignored((ROOT / rel).read_text(encoding="utf-8"))
        assert found, f"{rel}: لا تجاهلَ موثَّقاً مع أنّه مقرَّر"
        assert set(found) <= ALLOWED, f"{rel}: تجاهلٌ غيرُ مأذون: {sorted(set(found) - ALLOWED)}"


def test_the_documented_ignore_has_not_expired():
    assert (
        datetime.date.today() <= REVIEW_BY
    ), "انتهت مهلةُ مراجعة تجاهل GHSA-8pqf-f4m5-798g (2026-11-15): راجعِ المشورةَ وارفعِ التجاهلَ أو جدّدْه بأمر المالك"

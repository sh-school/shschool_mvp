"""إعادةُ محاولة Lighthouse عند الأخطاء العابرة — بلا متصفّح.

`subprocess.run` يُستبدَل بمزيّفٍ يُعيد نتائجَ مرسومةً سلفاً، فيُختبر المنطقُ وحده.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from tests import lighthouse_audit as lighthouse

URL = "http://live.test/teacher/schedule/"


def _report() -> str:
    """تقريرٌ مصغّرٌ يكفي `run` لاستخراج الدرجات."""
    return json.dumps(
        {
            "finalDisplayedUrl": URL,
            "categories": {"performance": {"score": 0.9}, "accessibility": {"score": 1}},
            "audits": {
                "largest-contentful-paint": {"numericValue": 1200},
                "total-blocking-time": {"numericValue": 100},
                "cumulative-layout-shift": {"numericValue": 0.01},
            },
        }
    )


def _ok() -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=_report(), stderr="")


def _fail(stderr: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=stderr)


def _fake_runs(monkeypatch: pytest.MonkeyPatch, results: list) -> list:
    """يستبدل `subprocess.run` بنتائجَ متتاليةٍ، ويُعيد قائمةَ الاستدعاءات للتحقّق منها."""
    calls: list = []

    def fake(command, **kwargs):
        calls.append(command)
        return results[len(calls) - 1]

    monkeypatch.setattr(lighthouse.subprocess, "run", fake)
    return calls


@pytest.mark.parametrize(
    "marker",
    ["NO_NAVSTART", "NO_FCP", "PROTOCOL_TIMEOUT", "Please run Lighthouse again"],
)
def test_transient_error_is_retried_once_then_succeeds(monkeypatch, marker):
    calls = _fake_runs(monkeypatch, [_fail(f"Error: {marker}"), _ok()])

    scores = lighthouse.run(URL, "sid=1", "/chrome")

    assert len(calls) == 2
    assert calls[0] == calls[1]  # الأمرُ نفسه في المحاولتين
    assert scores["performance"] == 90


def test_non_transient_error_is_not_retried(monkeypatch):
    calls = _fake_runs(monkeypatch, [_fail("Error: something else")])

    with pytest.raises(RuntimeError, match="بعد 1 محاولة"):
        lighthouse.run(URL, "sid=1", "/chrome")

    assert len(calls) == 1


def test_two_transient_failures_raise_with_attempt_count(monkeypatch):
    calls = _fake_runs(monkeypatch, [_fail("NO_NAVSTART"), _fail("NO_NAVSTART")])

    with pytest.raises(RuntimeError, match="بعد 2 محاولة"):
        lighthouse.run(URL, "sid=1", "/chrome")

    assert len(calls) == 2

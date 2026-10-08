"""[IDENTITY] الالتقاطُ الحيّ ينتظر اكتمالَ الرسوم البيانيّة (VI-13) — حارسٌ نصّيٌّ بلا متصفّح.

رسمُ لوحة القيادة يُنشأ بعد `fetch` غير متزامن، فلقطةٌ بعد 300ms ثابتةً كانت تسبقه أحياناً: لقطتان متتاليتان على الصفحة نفسِها تختلفان
(0.38% و0.25% في تشغيلَين متتاليَين على main، 2026-10-08) فيفشل فحصُ الحتميّة بلا تغييرٍ في أيّ صفحة. هذا الحارسُ يمنع أن يعود الالتقاطُ
إلى الانتظار بالزمن وحدَه؛ والتشغيلُ الحيّ نفسُه في `visual-snapshots.yml`.
"""

from __future__ import annotations

import pathlib
import re

SOURCE = (
    pathlib.Path(__file__).resolve().parent / "e2e" / "test_visual_snapshots_live.py"
).read_text(encoding="utf-8")


def _capture_body() -> str:
    match = re.search(r"\ndef _capture\(.*?(?=\n\ndef |\Z)", SOURCE, re.S)
    assert match, "لم أجد _capture في الالتقاط الحيّ"
    return match.group(0)


def test_the_capture_waits_for_the_charts_before_the_screenshot():
    body = _capture_body()
    assert "_wait_for_charts(page)" in body
    assert body.index("_wait_for_charts(page)") < body.index("page.screenshot(")


def test_the_wait_is_about_the_charts_themselves_not_a_longer_sleep():
    assert "window.Chart.getChart(c)" in SOURCE
    assert 'wait_for_load_state("networkidle"' in SOURCE
    assert "wait_for_function(CHARTS_READY" in SOURCE


def test_a_page_whose_chart_never_arrives_does_not_fail_the_capture():
    # الرسمُ الفاشلُ يبقى فارغاً في اللقطتين معاً (حتميّ)؛ فالمهلةُ تُبتلع لا تُسقط الاختبار.
    assert "except PlaywrightTimeout" in SOURCE

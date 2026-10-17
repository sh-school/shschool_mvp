"""[IDENTITY] قاعدةُ المذبذب وثباتُ الارتفاع للقطات الهويّة (W-20261016-013) — بلا متصفّح.

القاعدة: لقطةٌ تتجاوز العتبةَ تُعاد مرّةً واحدة؛ نجحت الإعادةُ فمذبذبةٌ تُوسَم ولا تحجب، وفشلت فهي فشلٌ حقيقيّ. العتباتُ لا تتغيّر.
"""

from __future__ import annotations

import pathlib

from tests import visual_snapshots as vs

LIVE = pathlib.Path(__file__).resolve().parent / "e2e" / "test_visual_snapshots_live.py"


def test_a_snapshot_within_the_limit_is_ok_without_retry():
    assert vs.decide_after_retry(0.0, None, vs.DETERMINISM_MAX) == vs.OK
    assert vs.decide_after_retry(vs.CHANGE_MAX, None, vs.CHANGE_MAX) == vs.OK


def test_a_flaky_snapshot_is_flagged_when_the_retry_passes_and_does_not_block():
    assert vs.decide_after_retry(0.02, 0.0, vs.DETERMINISM_MAX) == vs.FLAKY


def test_a_real_difference_repeats_in_the_retry_and_blocks():
    assert vs.decide_after_retry(0.02, 0.02, vs.DETERMINISM_MAX) == vs.FAIL
    assert vs.decide_after_retry(1.0, None, vs.CHANGE_MAX) == vs.FAIL  # لا إعادةَ أُجريت = فشل


def test_the_thresholds_are_unchanged():
    assert vs.DETERMINISM_MAX == 0.0005
    assert vs.CHANGE_MAX == 0.0025
    assert vs.PIXEL_TOLERANCE == 12


def test_the_change_limit_tolerates_host_render_noise_but_still_catches_a_blank_page():
    assert vs.decide_after_retry(0.0018, None, vs.CHANGE_MAX) == vs.OK  # أعلى ضجيجٍ قِيس بين المضيفين
    assert vs.decide_after_retry(0.0025, None, vs.CHANGE_MAX) == vs.OK  # عند الحدّ تماماً
    assert vs.decide_after_retry(1.0, None, vs.CHANGE_MAX) == vs.FAIL  # صفحةٌ فارغة
    assert vs.decide_after_retry(1.0, 1.0, vs.CHANGE_MAX) == vs.FAIL  # وتتكرّر في الإعادة


def test_the_capture_runs_on_a_pinned_host_with_deterministic_render_flags():
    workflow = (LIVE.parents[2] / ".github" / "workflows" / "visual-snapshots.yml").read_text(
        encoding="utf-8"
    )
    assert "runs-on: ubuntu-24.04" in workflow
    assert "ubuntu-latest" not in workflow
    assert "--force-color-profile=srgb" in vs.CHROMIUM_ARGS
    assert "vs.CHROMIUM_ARGS" in LIVE.read_text(encoding="utf-8")


def test_height_waits_for_two_equal_consecutive_reads():
    reads = iter([900, 1000, 1200, 1200])
    waited = []
    assert vs.stable_height(lambda: next(reads), lambda: waited.append(1)) == 1200
    assert len(waited) == 3


def test_height_returns_last_read_when_it_never_settles():
    values = iter(range(100, 200))
    assert vs.stable_height(lambda: next(values), lambda: None, attempts=3) == 103


def test_the_live_capture_uses_the_retry_rule_and_the_stable_height():
    text = LIVE.read_text(encoding="utf-8")
    assert "vs.stable_height(" in text
    assert text.count("vs.decide_after_retry(") >= 3
    assert "flaky.json" in text

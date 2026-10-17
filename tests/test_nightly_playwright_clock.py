"""[CLOCK] الوظيفةُ الليليّة تشغّل Playwright بساعةٍ مجمَّدة أيضاً (W-20261016-010).

خطوةُ Playwright الليليّةُ كانت بالساعة الحيّة وحدَها؛ فلمّا فشلت لوحةٌ على 1366 بسبب «اليوم» (W-20261016-008) لم يسبق ذلك إنذارٌ يفرّق
بين التراجع والحساسيّةِ لليوم. تُضاف خطوةٌ ثانيةٌ بالأوامر نفسِها ولحظةٍ مجمَّدةٍ، وهنا يُحرس أنّها باقيةٌ وأنّ لحظتها هي أربعاءُ الدوام
(`FIXED_NOW`) كي لا تنجرف عن `pin_clock`، وأنّ قائمةَ ملفّاتها هي قائمةُ الخطوة الحيّة.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import re

from tests.visual_snapshots import FIXED_NOW

NIGHTLY = pathlib.Path(__file__).resolve().parent.parent / ".github" / "workflows" / "nightly.yml"
_STEP = re.compile(r'- name: "(Playwright[^"]*)"\n(.*?)(?=\n      - name:|\n      #|\Z)', re.S)


def _playwright_steps() -> dict[str, str]:
    return {m.group(1): m.group(2) for m in _STEP.finditer(NIGHTLY.read_text(encoding="utf-8"))}


def _pytest_targets(step: str) -> str:
    return re.sub(r"\s+", " ", step.split("run: |", 1)[1]).strip()


def test_there_is_a_live_and_a_frozen_playwright_step():
    steps = _playwright_steps()
    frozen = [name for name, body in steps.items() if "SCHOOLOS_TEST_NOW" in body]
    live = [name for name, body in steps.items() if "SCHOOLOS_TEST_NOW" not in body]
    assert len(frozen) == 1 and len(live) == 1, steps.keys()


def test_the_frozen_step_uses_the_ordinary_school_wednesday():
    body = next(b for b in _playwright_steps().values() if "SCHOOLOS_TEST_NOW" in b)
    value = re.search(r'SCHOOLOS_TEST_NOW: "([^"]+)"', body).group(1)
    assert dt.datetime.fromisoformat(value) == FIXED_NOW
    assert FIXED_NOW.weekday() == 2  # الأربعاء: يومُ دوامٍ عاديّ


def test_both_steps_run_the_same_files_and_always_run():
    live, frozen = (
        next(b for b in _playwright_steps().values() if ("SCHOOLOS_TEST_NOW" in b) is flag)
        for flag in (False, True)
    )
    assert _pytest_targets(live) == _pytest_targets(frozen)
    assert "if: always()" in frozen

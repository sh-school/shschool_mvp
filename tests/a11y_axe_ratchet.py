"""سقّاطةُ axe-core — ما يُقرأ فعلياً في متصفّحٍ حيّ، لا مصدرُ القالب.

`tests/a11y_ratchet.py` يفحص مصدر القالب نصّياً؛ وهذا يفتح الصفحةَ في متصفّحٍ حقيقيّ
(Playwright + Chromium) بعد تسجيل الدخول، ويُشغّل محرّك axe-core نفسَه عليها —
فيُمسك ما لا يظهر في المصدر: تباينَ لونٍ فعليّاً محسوباً، وترتيبَ DOM، ودَوراً
مُركَّباً من CSS وJS معاً.

القياسُ الأوّل (P0-1، 2026-09-18) وجد مخالفاتٍ حقيقيّةً موجودةً فعلاً على الإنتاج:
`scrollable-region-focusable` في صفحة الأيقونات، و`landmark-one-main`/`region` في
صفحة الدخول المستقلّة، و`image-redundant-alt` متكرّرةً، و`aria-allowed-role` في
لوحتي مدير/نائب مدير. فالخطُّ الأساس هنا **لا يبدأ من صفر** — يُسجَّل بهذه
المخالفات نفسِها، لأنّ إصلاحها بندٌ منفصلٌ لاحق؛ والحارسُ هنا يمنع أن تزيد لا أن
يُصلحها.

نفسُ منطق `tests/design_ratchet.py`: لكلّ صفحةٍ ولكلّ قاعدة axe عددُ عُقَدها
المخالفة. زاد → سقط البناء. نقص ولم يُسجَّل → سقط كذلك حتّى يُثبَّت التحسّن.
"""

from __future__ import annotations

import json
import pathlib
from collections import Counter

from axe_playwright_python.sync_playwright import Axe

BASELINE = pathlib.Path("tests/a11y_axe_ratchet_baseline.json")

#: مستوياتُ WCAG المفحوصة — 2.0/2.1 أ وAA، لا التجريبيّةَ (`best-practice`) التي
#: تتغيّر بين إصدارات axe-core بلا علاقةٍ بكود المنصّة.
AXE_OPTIONS = {
    "resultTypes": ["violations"],
    "runOnly": {"type": "tag", "values": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]},
}


def measure_page(page) -> dict[str, int]:
    """عددُ العُقَد المخالفة لكلّ قاعدة axe في الصفحة المفتوحة حالياً بالمتصفّح."""
    results = Axe().run(page, options=AXE_OPTIONS)
    counts: dict[str, int] = {}
    for violation in results.response["violations"]:
        counts[violation["id"]] = len(violation["nodes"])
    return counts


def compare(baseline: dict, current: dict) -> tuple[list[str], list[str]]:
    """(ما زاد، ما نقص ولم يُسجَّل) — كلٌّ سطرٌ يُقرأ: الصفحة، القاعدة، قبل → بعد."""
    worse, stale = [], []
    for page_name in sorted(set(baseline) | set(current)):
        before = baseline.get(page_name, {})
        now = current.get(page_name, {})
        for rule in sorted(set(before) | set(now)):
            was, is_ = before.get(rule, 0), now.get(rule, 0)
            if is_ > was:
                worse.append(f"{page_name}: {rule} {was} → {is_}")
            elif is_ < was:
                stale.append(f"{page_name}: {rule} {was} → {is_}")
    return worse, stale


def totals(data: dict) -> Counter:
    counts: Counter = Counter()
    for rules in data.values():
        counts.update(rules)
    return counts


def read_baseline() -> dict:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def write_baseline(data: dict) -> None:
    BASELINE.write_text(
        json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

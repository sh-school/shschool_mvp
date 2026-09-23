"""Lighthouse للجوال (Q-03) — درجتا الأداء والوصوليّة على خمس صفحاتٍ رئيسة، ليلاً.

مِلفُّ Lighthouse الافتراضيّ للجوال هو ما تطلبه الخطّة (§2، K13 وK25): شاشةُ جوالٍ وشبكةُ
Slow 4G (RTT 150ms) ومعالجٌ أبطأ أربعاً، بالمحاكاة (`simulate`) لا بالخنق الحقيقيّ.

**لماذا ليلاً لا في كلّ طلب دمج** (قرارُ المالك 2026-09-23): الصفحةُ الواحدة ثلاثُ دقائق
محلّيّاً، فخمسٌ في وظيفةٍ حاجبةٍ تضيف ربعَ ساعةٍ لكلّ طلب. ودرجةُ الأداء تتذبذب بضعَ نقاطٍ
بين تشغيلٍ وآخر (حتى 14 نقطة) فلا تصلح سقّاطةً صارمة. وما يلزم كلَّ طلبٍ محروسٌ أصلاً: CLS وLCP والحمولة
في `tests/web_vitals.py`، وأهدافُ اللمس في `tests/mobile_audit.py`.

**ودرجةُ الأداء هنا ليست درجةَ الإنتاج:** `live_server` يخدم الأصولَ خاماً بلا ضغطٍ ولا
تصغير، فالرقمُ أسوأ من الإنتاج ويصلح لمقارنة ليلةٍ بليلة لا للحكم على المنصّة.

السقّاطة: الوصوليّةُ لا تنزل أبداً (ثابتةٌ بين التشغيلات)، والأداءُ لا ينزل أكثر من
`PERF_TOLERANCE` نقطةً عن الأساس. والتحسّنُ لا يُسقط شيئاً — يُثبَّت بـ`LIGHTHOUSE_UPDATE=1`.
"""

from __future__ import annotations

import json
import os
import pathlib
import shlex
import subprocess

BASELINE = pathlib.Path("tests/lighthouse_baseline.json")

#: الإصدارُ مثبَّتٌ: قواعدُ الدرجات تتغيّر بين الإصدارات الكبرى بلا علاقةٍ بكود المنصّة.
LIGHTHOUSE = "npx --yes lighthouse@12.8.2"

#: نقاطُ الأداء المسموحُ نزولُها عن الأساس قبل أن يُعدّ انحداراً. التذبذبُ المقيس على لوحة المدير
#: 54 و64 و68 في ثلاث تجارب (14 نقطة، والتباطؤُ في المعالج المحاكى هو السبب: TBT من 125 إلى 545ms)،
#: فالسماحُ 15 لا يُطلق قضيّةً كاذبةً لضجيجٍ ويُمسك انحداراً حقيقيّاً (>15 نقطة).
PERF_TOLERANCE = 15


def run(url: str, cookie: str, chrome_path: str) -> dict[str, float]:
    """درجتا الصفحة (0–100) وقيمُها الأساسيّة، بمِلفّ الجوال الافتراضيّ."""
    command = shlex.split(os.environ.get("LIGHTHOUSE_BIN", LIGHTHOUSE)) + [
        url,
        "--chrome-flags=--headless=new --no-sandbox --disable-dev-shm-usage",
        "--only-categories=performance,accessibility",
        "--output=json",
        "--output-path=stdout",
        "--quiet",
        "--extra-headers",
        json.dumps({"Cookie": cookie}),
    ]
    # Lighthouse يقرأ المتصفّحَ من `CHROME_PATH` وحده، لا من `--chrome-path`.
    env = {**os.environ, "CHROME_PATH": chrome_path}
    done = subprocess.run(command, capture_output=True, text=True, env=env, timeout=600)
    if done.returncode:
        raise RuntimeError(f"Lighthouse سقط على {url}:\n{done.stderr[-1500:]}")
    report = json.loads(done.stdout)
    if not report["finalDisplayedUrl"].startswith(url.split("?")[0]):
        raise RuntimeError(f"أُعيد التوجيه إلى {report['finalDisplayedUrl']} — الدخولُ لم يثبت")
    audits = report["audits"]
    return {
        "performance": round(report["categories"]["performance"]["score"] * 100),
        "accessibility": round(report["categories"]["accessibility"]["score"] * 100),
        "lcp_ms": round(audits["largest-contentful-paint"]["numericValue"]),
        "tbt_ms": round(audits["total-blocking-time"]["numericValue"]),
        "cls": round(audits["cumulative-layout-shift"]["numericValue"], 3),
    }


def compare(baseline: dict, current: dict) -> list[str]:
    """الانحداراتُ وحدها: وصوليّةٌ نزلت، أو أداءٌ نزل فوق السماح، أو صفحةٌ بلا أساس."""
    regressions = []
    for page, now in sorted(current.items()):
        before = baseline.get(page)
        if before is None:
            regressions.append(f"{page}: لا أساسَ لها — سجّله بـLIGHTHOUSE_UPDATE=1")
            continue
        if now["accessibility"] < before["accessibility"]:
            regressions.append(
                f"{page}: الوصوليّة {before['accessibility']} → {now['accessibility']}"
            )
        if now["performance"] < before["performance"] - PERF_TOLERANCE:
            regressions.append(
                f"{page}: الأداء {before['performance']} → {now['performance']} "
                f"(السماح {PERF_TOLERANCE})"
            )
    return regressions


def read_baseline() -> dict:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def write_baseline(data: dict) -> None:
    BASELINE.write_text(
        json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

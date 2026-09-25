"""[CSS] فواصلُ التعليقات الزخرفيّة قصيرة — الحرفُ منها ثلاثةُ بايتات في UTF-8 ولا يصل المتصفّحَ.

كانت في أنماط المنصّة 197 فاصلاً من `═`/`─` (سطرٌ من 58 حرفاً = 174 بايتاً) يبلغ مجموعُها 25,284 بايتاً
من الحجم الخامّ الذي تعدّه ميزانيّةُ `css_kb` (`tests/web_vitals.py`) — وهذه ميزانيّةٌ على ما يخدمه خادمُ
الاختبار خاماً لا على ما ينزل المتصفّح (`rcssmin` يُسقط التعليقات فلا يتغيّر المصغَّرُ بايتاً). وقد بلغ هامشُها
142 بايتاً (2026-09-25) فسقطت طلباتٌ لأنّها كتبت تعليقاً؛ ولا رفعَ للسقف (VD8). فقُصِّرت الفواصلُ إلى 20 حرفاً
في السطر الفاصل الصِّرف و3 أحرفٍ بعد العنوان، وأُثبت أنّ المصغَّر المشحون **متطابقٌ بايتاً بايتاً** قبلها وبعدها.

الحارسُ يمنع عودتَها: لا فاصلَ زخرفيّاً أطولَ من `MAX_RUN`. العنوانُ هو المعلومة؛ والخطُّ الذي يملأ العرضَ
كلَّه زخرفةٌ تُدفع بالبايتات في كلّ تحميلٍ للاختبار وتُغيّر أسطراً كثيرةً حين يُعدَّل عنوانٌ فتتصادم به الجلساتُ المتوازية.
"""

from __future__ import annotations

import re

from tests.css_source import read_css

#: أطولُ فاصلٍ زخرفيٍّ متّصلٍ مسموح (حرفاً). السطرُ الفاصلُ الصِّرف 20، وبعد العنوان 3.
MAX_RUN = 24

DECORATION = "═─━"
RUN_RE = re.compile(f"[{DECORATION}]" + "{%d,}" % (MAX_RUN + 1))


def long_runs(css: str) -> list[tuple[int, int]]:
    """(رقمُ السطر، طولُ الفاصل) لكلّ فاصلٍ زخرفيٍّ أطولَ من الحدّ."""
    found = []
    for number, line in enumerate(css.split("\n"), start=1):
        found += [(number, len(match.group(0))) for match in RUN_RE.finditer(line)]
    return found


def test_no_decorative_comment_rule_is_longer_than_the_limit():
    css = read_css()
    bad = long_runs(css)
    listing = ", ".join(f"سطر {n} ({length})" for n, length in bad[:20])
    assert not bad, (
        f"{len(bad)} فاصلاً زخرفيّاً أطولَ من {MAX_RUN} حرفاً في أنماط المنصّة (الحرفُ 3 بايتات في الحجم الخامّ): "
        f"{listing} — اكتب العنوانَ وقصِّر الخطّ."
    )


def test_the_detector_sees_what_it_claims_to_see():
    short = "/* " + "═" * MAX_RUN + " */"
    long = "/* ── عنوان " + "─" * (MAX_RUN + 1) + " */"
    assert long_runs(short) == []
    assert long_runs(f"{short}\n{long}") == [(2, MAX_RUN + 1)]

"""لا عرضَ ثابتاً يتجاوز 320px يبلغ شاشةً ضيّقة — WCAG 2.2 SC 1.4.10 (إعادة التدفّق).

المعيار: تكبيرٌ حتى 400% (أو نافذةٌ بعرض 320px CSS) بلا تمريرٍ أفقيٍّ
للمحتوى الرئيسي؛ الجداولُ المُغلَّفة (`.table-wrap` وأخواتها) مستثناةٌ
صراحةً — وثيقةُ WCAG نفسُها تستثني البيانات الجدوليّة.

قياسٌ مباشر في المتصفّح المدمج يومَ 2026-09-18 (عرض 320×700، صفحتان
مختلفتان تماماً: `/dashboard/` و`/reports/`) وجد فارقاً ثابتاً 7px بين
`scrollWidth` و`clientWidth` على **كلتيهما بالتساوي** رغم اختلاف
محتواهما الكامل — توقيعُ عيّنةٍ بيئيّة (حيّز شريط تمرير) لا محتوًى
حقيقيّاً أعرضَ من الشاشة؛ لا صفحةَ تفشل فعلياً في التدفّق. المرشّحُ
الوحيدُ الذي كشفه مسحٌ نصّيٌّ أوّليّ — `.report-student-dropdown` عند
`static/css/custom.css:3304` (`width: 340px`) — تبيّن أنّه عرضٌ بعد سطح
مكتب (`@media (min-width: 641px)`) فقط؛ قاعدةٌ لاحقةٌ بنفس الاختصاص
(3308) تُبطله إلى `width: auto` في الهاتف — لا خللَ، لكنّ هذا الحارسَ
يمنع أن يتكرّر خطأً حقيقيّاً من هذا الشكل بالضبط مستقبلاً.

**المنهجية هنا ساكنة** (لا متصفّح): لكلّ مُحدِّدٍ بسيط، يُحسب آخر تصريحٍ
فعليٍّ يبلغه عند 320px (بترتيب الطبقات ثمّ ترتيب المصدر — الطبقةُ
الأحدث تغلب، وداخل الطبقة نفسِها السطرُ الأحدث يغلب)، ويُرفَض إن كان
عرضاً ثابتاً > 320px. قاعدةٌ داخل `@media (min-width: N>320px)` لا
تُحتسَب أصلاً — لا تبلغ 320px بتعريفها.
"""

from __future__ import annotations

import pathlib
import re

from tests.css_contrast import iter_rules, strip_noise

CSS_PATH = pathlib.Path("static/css/custom.css")

#: WCAG 1.4.10 يستثني صراحةً البيانات الجدوليّة التي تحتاج عرضاً وارتفاعاً
#: معاً ليُقرأ محتواها (جدولٌ ذو أعمدةٍ كثيرة). هذه أغلفةُ التمرير المعروفة.
SCROLLABLE_EXCEPTIONS = {
    "table-wrap",
    "table-wrap-scroll",
    "per-grid-wrap",
    "asg-guard-scroll",
    "report-tab",  # شريطُ تبويبٍ يُمرَّر أفقيّاً بذاته — مكوّنٌ صغيرٌ محتوًى، لا الصفحة
}

MAX_REACHABLE_WIDTH = 320


def _css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


def _declared_order(css: str) -> list[str]:
    m = re.search(r"@layer\s+([^{;]+);", strip_noise(css))
    assert m, "لا سطرَ `@layer a, b, …;` — الترتيبُ غيرُ معلَن"
    return [n.strip() for n in m.group(1).split(",") if n.strip()]


def _layer_of(ctx) -> str | None:
    for head in ctx:
        m = re.search(r"@layer\s+([\w-]+)\s*$", head)
        if m:
            return m.group(1)
    return None


def _reachable_at_320(ctx) -> bool:
    """False إن كانت القاعدةُ محصورةً بعرضٍ أدنى أوسع من 320px — لا تبلغه أصلاً."""
    for head in ctx:
        if "print" in head:
            return False  # الطباعةُ خارج نطاق إعادة التدفّق الشاشيّة
        m = re.search(r"@media[^{]*min-width:\s*(\d+)px", head)
        if m and int(m.group(1)) > MAX_REACHABLE_WIDTH:
            return False
    return True


def _is_exception(selector: str) -> bool:
    return any(exc in selector for exc in SCROLLABLE_EXCEPTIONS)


def _px_over_320(value: str) -> int | None:
    v = value.strip()
    m = re.fullmatch(r"(\d+)px", v)
    if not m:
        return None
    n = int(m.group(1))
    return n if n > MAX_REACHABLE_WIDTH else None


def test_no_fixed_width_exceeds_320px_at_a_reachable_viewport():
    css = _css()
    order = _declared_order(css)

    # آخرُ قاعدةٍ فعليّةٍ تبلغ 320px لكلّ (مُحدِّدٍ بسيط، خاصّية) — بترتيب
    # (فهرسُ الطبقة، ترتيبُ المصدر) تصاعديّاً؛ الأخيرُ في القائمة هو الغالب.
    winners: dict[tuple[str, str], tuple[int, int, str]] = {}
    for doc_i, (sel, decls, ctx) in enumerate(iter_rules(css)):
        if not _reachable_at_320(ctx):
            continue
        layer = _layer_of(ctx)
        layer_i = order.index(layer) if layer in order else -1
        for part in sel.split(","):
            part = " ".join(part.split())
            if not part or _is_exception(part):
                continue
            for prop in ("width", "min-width"):
                if prop not in decls:
                    continue
                key = (part, prop)
                rank = (layer_i, doc_i)
                prev = winners.get(key)
                if prev is None or rank > prev[:2]:
                    winners[key] = (layer_i, doc_i, decls[prop])

    offenders = []
    for (sel, prop), (_li, _di, value) in winners.items():
        px = _px_over_320(value)
        if px:
            offenders.append(f"  {sel[:60]}  {{ {prop}: {value} }}")

    offenders.sort()
    assert not offenders, (
        f"{len(offenders)} مُحدِّداً بعرضٍ ثابتٍ > 320px يبلغ شاشةً ضيّقة "
        "(WCAG 1.4.10 — إعادة التدفّق):\n" + "\n".join(offenders[:25])
    )


def test_the_scan_actually_reaches_the_stylesheet():
    """تفكيكٌ يُخفق يُنتج صفرَ قواعدَ فينجح الحارسُ كاذباً."""
    css = _css()
    rules = list(iter_rules(css))
    assert len(rules) >= 2000, f"لم يُفكَّك إلّا {len(rules)} قاعدةً — المسحُ فارغ"
    with_width = sum(1 for _s, d, _c in rules if "width" in d or "min-width" in d)
    assert with_width >= 100, f"{with_width} قاعدةً فقط بها width/min-width — المسحُ لا يرى الخاصّيّتين"

"""[MOBILE] المنطقةُ الآمنة من رموز `--safe-*` لا من `env()` مباشرةً (H-04).

كان `env(safe-area-inset-*)` مكتوباً مباشرةً في موضعين (الشريطُ السفليّ وشريطُ الرجوع في التطبيق المثبَّت)،
فحين تُفعَّل المنطقةُ الآمنة بـ`viewport-fit=cover` (M-04) لا يعرف من يبدّل الوسمَ أين الباقي — وشريطُ التثبيت
والتوستُ والترويسةُ تنسى الشقَّ فتدخل تحته. فالرموزُ الثلاثةُ تُعرَّف مرّةً في `10-foundation.css`،
ومن يحتاج حافّةً يقرأ الرمزَ. والحارسُ يمنع عودةَ `env()` المباشر.

القيمةُ اليوم 0 (الوسمُ غائب)، فاستهلاكُ الرموز لا يغيّر شيئاً حتّى M-04 — وهذا شرطُ H-04: تجهيزٌ لا تغيير.
"""

import pathlib
import re

from tests.css_contrast import iter_rules
from tests.css_source import read_css

ENV_USE = re.compile(r"env\(\s*safe-area-inset-[a-z]+")
COMMENT = re.compile(r"/\*.*?\*/", re.S)
TOKENS = ("--safe-top", "--safe-bottom", "--safe-inline")
FOUNDATION = pathlib.Path("static/css/custom/10-foundation.css")
SCANNED = ("static/**/*.css", "static/**/*.js", "templates/**/*.html")


def _uses_outside_the_tokens() -> list[str]:
    found = []
    for pattern in SCANNED:
        for path in pathlib.Path(".").glob(pattern):
            if path == FOUNDATION:
                continue
            text = COMMENT.sub("", path.read_text(encoding="utf-8", errors="ignore"))
            if ENV_USE.search(text):
                found.append(path.as_posix())
    return sorted(found)


def test_no_file_reads_the_safe_area_directly():
    found = _uses_outside_the_tokens()
    assert (
        not found
    ), f"`env(safe-area-inset-*)` مكتوبٌ مباشرةً في {found} — اقرأ var(--safe-top|bottom|inline)"


def test_each_token_is_defined_once_with_a_zero_fallback():
    css = COMMENT.sub("", FOUNDATION.read_text(encoding="utf-8"))
    for token in TOKENS:
        definitions = re.findall(rf"{re.escape(token)}\s*:\s*([^;]+);", css)
        assert len(definitions) == 1, f"{token}: {len(definitions)} تعريفاً"
        assert ENV_USE.search(definitions[0]), f"{token} لا يقرأ env(safe-area-inset-*)"
        assert re.search(
            r",\s*0px\s*\)", definitions[0]
        ), f"{token} بلا احتياطٍ 0px — يكسر المتصفّحَ القديم"
    assert len(ENV_USE.findall(css)) == 4, "الأربعُ: top وbottom ويمين ويسار (inline يأخذ الأكبر)"


def _decls(selector: str) -> dict[str, str]:
    merged: dict[str, str] = {}
    for sel, decls, ctx in iter_rules(read_css()):
        if any("media" in c for c in ctx) or " ".join(sel.split()) != selector:
            continue
        merged.update(decls)
    return merged


def test_the_edge_anchored_elements_read_the_tokens():
    """ما يلتصق بحافّة الشاشة يقرأ رمزها: الشريطُ السفليّ وشريطُ التثبيت من أسفل، والترويسةُ والتوستُ والرسائلُ من أعلى."""
    assert "var(--safe-bottom)" in _decls(".mobile-bottom-nav")["padding"]
    # قاعدةُ `utilities` هي الفعّالة (تغلب `components` بالطبقة) — وفيها `inset-block-end` لا `bottom`
    assert "var(--safe-bottom)" in _decls(".pwa-banner")["inset-block-end"]
    assert "var(--safe-top)" in _decls(".site-header")["padding"]
    # الشريطُ اللزجُ تحت الترويسة: إن كبُرت الترويسةُ بالحافّة العليا وجب أن يبدأ لزوجُه بعدها، وإلّا تداخلا
    assert "var(--safe-top)" in _decls(".site-nav")["top"]
    assert "var(--safe-top)" in _decls("#toast-container")["top"]
    assert "var(--safe-top)" in _decls(".msgs-wrap")["top"]


def test_the_standalone_back_bar_reads_the_top_token():
    html = pathlib.Path("templates/components/app_back_bar.html").read_text(encoding="utf-8")
    assert "var(--safe-top)" in html and not ENV_USE.search(html)

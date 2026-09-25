"""[MOBILE H-04] المنطقةُ الآمنة (الشقّ وشريطُ الإيماءات) رموزٌ لا `env()` مبعثرة.

`env(safe-area-inset-*)` يُكتب مرّةً واحدةً في `:root` (`--safe-top` و`--safe-bottom` و`--safe-inline`)،
وتقرؤه الترويسةُ والشريطُ السفليّ والإشعارُ وشريطُ التثبيت — فإذا أُضيف `viewport-fit=cover` (M-04)
تحرّكت كلُّها معاً بموضعٍ واحد.

M-04 (K8): `viewport-fit=cover` في `base.html` يُدخل المحتوى تحت الشقّ والحافّة، فلا بدّ أن تقرأ كلُّ حافّةٍ
رمزَها: الأعلى `--safe-top`، والأسفل `--dock-pad` (≥ 8px حتى بلا شريط إيماءات) بدل 72 و80 الحرفيّتين، والجانبان
`--edge-inline` (هامشُ المحتوى الأصليّ لا يقلّ عن الشقّ في الوضع الأفقيّ) — وتعبيرُه مكتوبٌ مرّةً واحدة.

- البديلُ `0px` بوحدته: `0` بلا وحدةٍ يُبطل كلَّ `calc(48px + …)` فيسقط `top` و`padding` في كلّ المحرّكات.
- `--safe-inline` متماثلٌ (`max` للجانبين): أسماءُ `env()` فيزيائيّةٌ (left/right) والمنصّةُ RTL منطقيّة.
- الورقةُ المستقلّة `app_back_bar.html` لا تحمّل `:root` المنصّة، فتعرّف `--safe-top` محلّياً باسمه.
"""

import re
from pathlib import Path

import pytest

from core.styleguide import scale_tokens
from tests.css_source import read_css

ROOT = Path(__file__).resolve().parent.parent
TOKENS = ("safe-top", "safe-bottom", "safe-inline")
ENV = re.compile(r"env\(safe-area-inset-")
DEFINITION = re.compile(r"--safe-(?:top|bottom|inline):")


def _scan_sources():
    """كلُّ قالبٍ وسكربتٍ يصل المتصفّحَ — قوالبُ الأصل وقوالبُ التطبيقات (`<app>/templates`)."""
    roots = [ROOT / "templates", ROOT / "static" / "js"]
    roots += sorted(
        p for p in ROOT.glob("*/templates") if p.parent.name not in {"static", "staticfiles"}
    )
    for base in roots:
        for path in sorted(base.rglob("*")):
            if path.suffix in {".html", ".js"} and ".min." not in path.name:
                yield path.relative_to(ROOT).as_posix(), path.read_text(encoding="utf-8")


def test_the_three_tokens_are_defined_in_root():
    assert {t["name"] for t in scale_tokens()["safe"]} == set(TOKENS)


def test_every_fallback_carries_its_unit():
    for line in read_css().splitlines():
        if DEFINITION.search(line):
            assert "0px" in line and not re.search(r",\s*0\s*\)", line), line.strip()


def test_env_is_written_only_inside_a_token_definition():
    stray = []
    css = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), read_css(), flags=re.S)
    for name, text in [("css", css), *_scan_sources()]:
        for number, line in enumerate(text.splitlines(), 1):
            if ENV.search(line) and not DEFINITION.search(line):
                stray.append(f"{name}:{number}: {line.strip()[:100]}")
    assert not stray, "env(safe-area) خارجَ تعريف رمزٍ — اقرأ `var(--safe-*)`:\n  " + "\n  ".join(
        stray
    )


@pytest.mark.parametrize(
    ("selector", "token"),
    [
        (".site-header {", "--safe-top"),
        (".site-nav {", "--safe-top"),
        ("#toast-container {", "--safe-top"),
        (".msgs-wrap {", "--safe-top"),
        (".mobile-bottom-nav {", "--dock-pad"),
        (".pwa-banner {", "--dock-pad"),
        (".pwa-banner {", "--safe-inline"),
        (".site-header .nav-inner {", "--edge-inline"),
        ("#main-content {", "--edge-inline"),
        ("#toast-container {", "--edge-inline"),
        (".nav-inner {", "--safe-inline"),
        (".site-footer {", "--safe-inline"),
        (".msgs-wrap {", "--safe-inline"),
        (".emergency-banner {", "--safe-top"),
        (".emergency-banner {", "--safe-inline"),
    ],
)
def test_the_fixed_chrome_reads_its_token(selector, token):
    css = read_css()
    blocks = []
    start = css.find(selector)
    while start != -1:  # للمحدِّد قواعدُ عدّة (رموزُ لونٍ في الأساس وغيرُها) — يكفي أن تقرأها إحداها
        blocks.append(css[start : css.index("}", start)])
        start = css.find(selector, start + 1)
    assert any(f"var({token})" in block for block in blocks), f"{selector} لا تقرأ {token}"


def test_the_standalone_back_bar_defines_the_token_locally():
    text = (ROOT / "templates/components/app_back_bar.html").read_text(encoding="utf-8")
    assert re.search(r"--safe-top:\s*env\(safe-area-inset-top, 0px\)", text)
    assert "padding: var(--safe-top) 12px 0" in text


def _root_value(name):
    css = read_css()
    found = re.search(rf"^\s*--{re.escape(name)}:\s*([^;]+);", css, re.M)
    assert found, f"--{name} غيرُ معرَّفٍ في :root"
    return " ".join(found.group(1).split())


def test_the_viewport_extends_under_the_notch_and_every_edge_reads_its_token():
    """K8: الوسمُ حاضرٌ في القالب الأصل، وما يقرؤه المحتوى من الحافّة رموزٌ معرَّفة."""
    html = (ROOT / "templates/base/base.html").read_text(encoding="utf-8")
    viewport = re.search(r'<meta name="viewport" content="([^"]+)"', html)
    assert viewport and "viewport-fit=cover" in viewport.group(1), viewport and viewport.group(1)
    assert _root_value("dock-h").endswith("rem"), "ارتفاعُ الشريط السفليّ بـrem فيتبع تكبيرَ الخطّ"
    assert (
        _root_value("dock-pad") == "max(var(--sp-2), var(--safe-bottom))"
    ), "حشوةُ الشريط السفليّ من أسفله لا تقلّ عن 8px حتى بلا شريط إيماءات"
    assert _root_value("edge-inline") == (
        "max(clamp(var(--sp-3), 1.4vw, 28px), var(--safe-inline))"
    )


def test_the_content_margin_expression_is_written_once():
    """هامشُ المحتوى عن الحافّة رمزٌ واحد — نسخةٌ ثانيةٌ تتباعد فتدخل تحت الشقّ في موضعٍ دون آخر."""
    css = re.sub(r"/\*.*?\*/", "", read_css(), flags=re.S)
    assert css.count("clamp(var(--sp-3), 1.4vw, 28px)") == 1


@pytest.mark.parametrize("literal", ["72px", "80px"])
def test_the_bottom_nav_reservation_has_no_literal_height(literal):
    """`body` وشريطُ التثبيت و`.per-bar` والقائمةُ الفرعيّةُ العائمة تقرأ `--dock-h` لا رقماً مكرَّراً."""
    css = re.sub(r"/\*.*?\*/", "", read_css(), flags=re.S)
    stray = [
        line.strip()
        for line in css.splitlines()
        if re.search(rf"(?<![\d.]){literal}", line)  # لا `280px` ولا `1.72px`
        and re.search(r"padding-bottom|bottom:|inset-block-end|max-height", line)
    ]
    assert not stray, f"{literal} حرفيٌّ في حجز الشريط السفليّ — اقرأ var(--dock-h): {stray}"

"""[MOBILE M-05 / K9] كلُّ `100vh` يتبعه `100dvh` — فلا قصَّ ولا تمريرَ زائداً حين يتحرّك شريطُ المتصفّح.

`100vh` على متصفّح الجوال هو الارتفاعُ **والشريطُ مطويٌّ**: فحين يظهر شريطُ العنوان (عند فتح الصفحة، وعند
التمرير لأعلى) يزيد الارتفاعُ الحقيقيُّ المرئيّ عمّا حُسب له. فلوحةُ الهامبرغر تُقصّ من أسفلها (آخرُ روابطها
تحت الشاشة لا تُنال)، وصفحةُ الدخول والأخطاء وعدمِ الاتّصال تتمرّر لسطرٍ زائد. و`100dvh` هو الارتفاعُ
المرئيُّ الآن.

القاعدةُ: كلُّ تصريحٍ فيه `100vh` يتبعه في القاعدة نفسِها تصريحٌ بالخاصيّة نفسِها وقيمتِه بـ`100dvh`
(احتياطٌ ثمّ الأحدث: المتصفّحُ الذي لا يفهم `dvh` يُسقط الثاني ويُبقي الأوّل). ولا `100vh` في JS —
الارتفاعُ مِلكُ CSS (لوحةُ الهامبرغر تأخذ `--nb-top` من `base.js`).

المقياسُ K9 = عددُ مواضع `100vh` بلا `dvh` (مصدرُها، لا `tailwind.min.css` المستورد).
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

#: مستوردٌ مصغَّر — لا يُحرَّر، ولا نطالبه.
VENDOR = {"static/css/tailwind.min.css"}

COMMENT = re.compile(r"/\*.*?\*/", re.S)
#: `prop: value` وفي قيمته `100vh` (وقيمةٌ لا تجاوز `;` `{` `}` ولا علامةَ اقتباس السمة).
DECLARATION = re.compile(r"([\w-]+)\s*:\s*([^;{}\"']*\b100vh\b[^;{}\"']*)")


def _strip_comments(text: str) -> str:
    return COMMENT.sub("", text)


def unpaired_declarations(text: str) -> list[str]:
    """تصريحاتُ `100vh` التي لا يتبعها في قاعدتها تصريحٌ بـ`100dvh` بالخاصيّة نفسِها."""
    text = _strip_comments(text)
    missing = []
    for found in DECLARATION.finditer(text):
        prop, value = found.group(1), found.group(2).strip()
        wanted = re.escape(value.replace("100vh", "100dvh"))
        # ما بعدها إلى نهاية القاعدة (`}`) أو نهاية سمّة `style="…"` — لا أبعد.
        rest = re.split(r"[}\"']", text[found.end() :], maxsplit=1)[0]
        if not re.search(
            rf"(?<![\w-]){re.escape(prop)}\s*:\s*{wanted}\s*(?:;|$)", rest.strip() + ";"
        ):
            missing.append(f"{prop}: {value}")
    return missing


def _sources():
    for pattern in ("static/css/**/*.css", "templates/**/*.html"):
        for path in sorted(ROOT.glob(pattern)):
            if path.relative_to(ROOT).as_posix() not in VENDOR:
                yield path


def _js_sources():
    yield from sorted((ROOT / "static/js").glob("*.js"))  # vendor/ مستورَدٌ


def test_every_100vh_has_its_dvh_after_it():
    unpaired = {}
    for path in _sources():
        missing = unpaired_declarations(path.read_text(encoding="utf-8"))
        if missing:
            unpaired[path.relative_to(ROOT).as_posix()] = missing
    assert not unpaired, (
        "`100vh` بلا `100dvh` بعده في القاعدة نفسِها — يُقصّ على الجوال حين يظهر شريطُ المتصفّح:\n  "
        + "\n  ".join(f"{name}: {', '.join(items)}" for name, items in unpaired.items())
    )


def test_scripts_do_not_size_by_100vh():
    """الارتفاعُ في CSS؛ والسكربتُ يمرّر متغيّراً (`--nb-top`) لا معادلةً."""
    offenders = []
    for path in _js_sources():
        code = _strip_comments(path.read_text(encoding="utf-8"))
        code = "\n".join(line.split("//")[0] for line in code.splitlines())
        if re.search(r"\b100d?vh\b", code):
            offenders.append(path.name)
    assert not offenders, f"ارتفاعٌ بـvh في سكربت: {offenders}"


def test_the_hamburger_panel_takes_its_top_from_one_variable():
    """`mobMenuTop` يضبط `--nb-top`، وCSS يحسب منه الارتفاعَ الأقصى بـ`dvh`."""
    js = (ROOT / "static/js/base.js").read_text(encoding="utf-8")
    start = js.index("function mobMenuTop")
    body = js[start : js.index("\n}\n", start)]
    assert "setProperty('--nb-top'" in body
    css = _strip_comments(
        (ROOT / "static/css/custom/20-components.css").read_text(encoding="utf-8")
    )
    panels = re.findall(r"\.nb-bar\s*\{[^{}]*\btop:\s*var\(--nb-top[^{}]*\}", css)
    assert len(panels) == 1, "قاعدةُ لوحة الهامبرغر غيرُ موجودةٍ أو مكرَّرة"
    assert "max-height: calc(100dvh - var(--nb-top" in panels[0]


# ── الفاحصُ نفسُه: يفشل حيث يجب ─────────────────────────────


@pytest.mark.parametrize(
    "css",
    [
        ".a { height: 100vh; }",  # بلا بديل
        ".a { height: 100dvh; height: 100vh; }",  # البديلُ قبل الاحتياط: يغلب الاحتياطُ فيبطله
        ".a { height: 100vh; min-height: 100dvh; }",  # بديلٌ لخاصيّةٍ أخرى
        ".a { max-height: calc(100vh - 54px); max-height: calc(100dvh - 40px); }",  # قيمةٌ مختلفة
        '<div style="height: 100vh">',  # سمّةٌ بلا بديل
        ".a { height: 100vh; } .b { height: 100dvh; }",  # البديلُ في قاعدةٍ أخرى
    ],
)
def test_the_checker_flags_unpaired_declarations(css):
    assert unpaired_declarations(css)


@pytest.mark.parametrize(
    "css",
    [
        ".a { height: 100vh; height: 100dvh; }",
        ".a { max-height: calc(100vh - var(--x, 54px)); max-height: calc(100dvh - var(--x, 54px)); }",
        ".a { height: 100vh; height: 100dvh }",  # بلا فاصلةٍ منقوطةٍ أخيرة
        '<div style="height: 100vh; height: 100dvh">',
        "/* calc(100vh - 450px) قديمٌ */ .a { color: red; }",  # تعليقٌ لا تصريح
        ".a { min-height: 60vh; }",  # ليس 100vh
    ],
)
def test_the_checker_accepts_paired_declarations(css):
    assert not unpaired_declarations(css)

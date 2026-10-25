"""[GUARD] لا حوارات المتصفح الأصليّة في واجهة المنصّة (W-20261010-019).

`window.confirm` يخرج عن هويّة المنصّة: إنجليزيّ «localhost says / OK / Cancel» لا يتبع العربيّةَ ولا الوضعَ الليليّ.
والتأكيدُ في المنصّة نافذةٌ واحدة يملكها `base.js` عبر `data-confirm`؛ ومن JS يُستدعى بنموذجٍ مخفيٍّ كما في
`class-grid.js::confirmThen`. فهذا الحارسُ يفشل إن ظهر `confirm(` الأصليّ في `static/js` أو `templates`.
و`alert(` الأصليّ سقّاطةٌ لا تزيد: القائمُ منه لا يُعدّ إذنًا بغيره، وإنقاصُه يُنزِل السقفَ.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = [
    p
    for base, pattern in (("static/js", "*.js"), ("templates", "*.html"))
    for p in (ROOT / base).rglob(pattern)
    if ".min." not in p.name and "vendor" not in p.parts
]

#: `confirm(` مجرّدةً أو `window.confirm(` — لا `confirmThen(` ولا `data-confirm` ولا `_confirm(` ولا `.confirm(` لكائنٍ آخر.
NATIVE_CONFIRM = re.compile(r"(?<![\w.$-])(?:window\.)?confirm\s*\(")
NATIVE_ALERT = re.compile(r"(?<![\w.$-])(?:window\.)?alert\s*\(")

#: سقّاطة alert: القائمُ اليومَ (file_upload.html وexport-center.js) — يتناقص ولا يزيد.
ALERT_CEILING = 2


def _code_only(path: Path) -> str:
    """نصُّ الملف بلا تعليقاتٍ: `/* */` و`//` وتعليقاتُ القوالب `{# #}` و`{% comment %}` و`<!-- -->`."""
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"\{#.*?#\}", "", text, flags=re.S)
    text = re.sub(r"\{%\s*comment[^%]*%\}.*?\{%\s*endcomment\s*%\}", "", text, flags=re.S)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)(^|\s)//.*$", r"\1", text)


def _hits(pattern: re.Pattern) -> list[str]:
    return [
        f"{p.relative_to(ROOT).as_posix()}:{m.group(0)}"
        for p in FILES
        for m in pattern.finditer(_code_only(p))
    ]


def test_no_native_confirm_anywhere_in_static_js_or_templates():
    assert _hits(NATIVE_CONFIRM) == []


def test_native_alert_is_a_ratchet_that_never_grows():
    found = _hits(NATIVE_ALERT)
    assert len(found) <= ALERT_CEILING, found


def test_the_guard_actually_sees_a_native_confirm_and_ignores_the_platform_one():
    assert NATIVE_CONFIRM.search("if (!window.confirm('x')) return;")
    assert NATIVE_CONFIRM.search("if (confirm('x')) go();")
    assert not NATIVE_CONFIRM.search("confirmThen('x', next)")
    assert not NATIVE_CONFIRM.search('<form data-confirm="x">')
    assert not NATIVE_CONFIRM.search("form.confirmed = true; reconfirm(x)")

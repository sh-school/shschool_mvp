"""[A11Y] `aria-pressed` لا يُوضع على رابط (VI-25).

axe يردّ `aria-pressed` على `<a href>` (قاعدةُ `aria-allowed-attr`): الخاصّيّةُ للأزرار المبدِّلة (`role="button"`)، والرابطُ ينقل ولا يبدّل.
كان رابطُ «غير المقروء فقط» في صندوق الإشعارات يحملها فكان العُقدةَ الوحيدةَ المسجَّلةَ في سقّاطة axe (`notification_inbox`)؛ وأُصلح بـ`aria-current`.
السقّاطةُ الحيّةُ تحرس الصفحاتِ التي تُقاس؛ وهذا الفحصُ يحرس كلَّ القوالب بلا متصفّح.
"""

import pathlib
import re

TEMPLATES = pathlib.Path("templates")
LINK_WITH_PRESSED = re.compile(r"<a\b[^>]*\baria-pressed\b", re.S)


def _hits(text: str) -> list[str]:
    return [m.group(0)[:80] for m in LINK_WITH_PRESSED.finditer(text)]


def test_no_template_puts_aria_pressed_on_a_link():
    offenders = {}
    for path in sorted(TEMPLATES.rglob("*.html")):
        hits = _hits(path.read_text(encoding="utf-8"))
        if hits:
            offenders[path.as_posix()] = hits
    assert not offenders, (
        "`aria-pressed` على رابط (axe: aria-allowed-attr) — استعمل `aria-current` للرابط أو اجعله `<button>`:\n  "
        + "\n  ".join(f"{path}: {hits}" for path, hits in offenders.items())
    )


def test_the_detector_sees_a_link_and_ignores_a_button():
    assert _hits('<a href="/x" class="c" aria-pressed="true">س</a>')
    assert _hits('<a\n href="/x"\n aria-pressed="{{ v }}">')
    assert not _hits('<button type="button" aria-pressed="true">س</button>')
    assert not _hits('<a href="/x" aria-current="true">س</a>')

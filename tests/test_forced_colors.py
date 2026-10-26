"""حارس وضع الألوان القسريّ (W-20261016-006): كتلةٌ واحدةٌ داخل @layer تعيد الحدَّ وحلقةَ التركيز ولا تُخفي شيئاً."""

import pathlib
import re

CSS = pathlib.Path(__file__).resolve().parent.parent / "static" / "css" / "custom"


def _blocks() -> list[tuple[str, str]]:
    out = []
    for p in CSS.glob("*.css"):
        text = p.read_text(encoding="utf-8")
        for m in re.finditer(r"@media \(forced-colors: active\) \{(.*?)\n\}", text, flags=re.S):
            out.append((p.name, m.group(1)))
    return out


def test_exactly_one_forced_colors_block_in_the_themes_layer():
    blocks = _blocks()
    assert [name for name, _ in blocks] == ["40-themes.css"]
    text = (CSS / "40-themes.css").read_text(encoding="utf-8")
    assert text.index("@layer themes") < text.index("@media (forced-colors: active)")


def test_the_block_restores_border_and_focus_ring_without_hiding_anything():
    body = _blocks()[0][1]
    assert "ButtonText" in body and "Highlight" in body
    assert "display: none" not in body and "display:none" not in body

"""يبني نسخةَ Tajawal بحركاتٍ ملوَّنة (COLR v0) — قرارُ المالك 2026-09-20.

CSS لا يلوّن الحركةَ منفصلةً عن حرفها، ولفُّها في عنصرٍ يقطع وصلَ الحروف (جُرّب فسقط). فالحلُّ في
الخطّ نفسه: كلُّ حركةٍ (فتحةٌ وضمّةٌ وكسرةٌ وسكونٌ وشدّةٌ وتنوينٌ وألفٌ خنجريّة والأشكالُ المركّبة)
تُرسم طبقةً بلونٍ من لوحة CPAL (الفهرس 0) بدل لون النصّ، وباقي الحروف كما هي. فيبقى الشكلُ والوصلُ
والتموضعُ كما في الأصل، ويبدّل CSS اللونَ بـ`@font-palette-values` لكلّ ثيمٍ وخلفيّة (10-foundation).
والمتصفّحُ الذي لا يعرف COLR يرسم الحركةَ بلون النصّ كالمعتاد — لا يضيع شيء.

    python scripts/build_tashkeel_fonts.py

المُدخل: `static/fonts/Tajawal-{Regular,Medium,Bold}.ttf`، والمُخرَج `…-tk.ttf` و`…-tk.woff2` (الأصلُ لا يُمسّ).
الترخيص: Tajawal بترخيص OFL؛ تُعدَّل أسماءُ العائلة بلاحقة «Tashkeel» لأنّ الخطّ المعدَّل لا يحمل الاسمَ الأصليّ.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fontTools.colorLib.builder import buildCOLR, buildCPAL
from fontTools.ttLib import TTFont

FONTS = Path(__file__).resolve().parent.parent / "static" / "fonts"
WEIGHTS = ("Regular", "Medium", "Bold")
#: لونُ الحركة الافتراضيّ (اللوحة 0، الفهرس 0) — أزرقُ الهويّة على السطح الفاتح؛ يُبدَّل بـ`@font-palette-values`.
DEFAULT_BLUE = (0x1D / 255, 0x4E / 255, 0xD8 / 255, 1.0)


def mark_glyphs(font: TTFont) -> list[str]:
    """كلُّ ما يصنّفه الخطُّ حركةً (GDEF class 3): الحركاتُ المفردةُ وأشكالُها المركّبة."""
    classes = font["GDEF"].table.GlyphClassDef.classDefs
    return [name for name, cls in classes.items() if cls == 3]


def build(weight: str) -> tuple[Path, Path]:
    source = FONTS / f"Tajawal-{weight}.ttf"
    font = TTFont(source)
    order = list(font.getGlyphOrder())
    glyf, hmtx = font["glyf"], font["hmtx"]

    layers: dict[str, list[tuple[str, int]]] = {}
    for name in mark_glyphs(font):
        layer = f"{name}.tk"
        glyf[layer] = glyf[name]
        hmtx[layer] = hmtx[name]
        order.append(layer)
        layers[name] = [(layer, 0)]
    font.setGlyphOrder(order)

    font["COLR"] = buildCOLR(layers, version=0)
    font["CPAL"] = buildCPAL([[DEFAULT_BLUE]])
    for record in font["name"].names:
        if record.nameID in (1, 4, 16):
            record.string = record.toUnicode().replace("Tajawal", "Tajawal Tashkeel")
        elif record.nameID == 6:
            record.string = record.toUnicode().replace("Tajawal", "TajawalTashkeel")

    ttf = FONTS / f"Tajawal-{weight}-tk.ttf"
    font.save(ttf)
    woff2 = FONTS / f"Tajawal-{weight}-tk.woff2"
    web = TTFont(ttf)
    web.flavor = "woff2"
    web.save(woff2)
    return ttf, woff2


if __name__ == "__main__":
    for weight in WEIGHTS:
        ttf, woff2 = build(weight)
        print(f"{weight}: {ttf.stat().st_size // 1024} KB ttf · {woff2.stat().st_size // 1024} KB woff2", file=sys.stdout)

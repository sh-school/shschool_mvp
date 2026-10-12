"""هويّةُ التطبيق حرفُ «ش» أبيضُ على العنّابيّ — لا شعارَ وزارةٍ في أيّ أصلٍ (W-20261011-012، قرار المالك D-386م/D-387م).

كانت الأيقوناتُ مشتقّةً من `static/brand/logoMaroon.png` (شعارُ الدولة كما في ترويسة الوزارة)؛ فأُزيل الشعارُ من المنصّة
كلِّها وصارت الأيقوناتُ تُرسم من الخطّ بـ`manage.py build_app_icons`. وهذا الحارسُ يثبّت الحالةَ الجديدة:
- ملفّاتُ الشعار وأداةُ اشتقاقها لم تعد في المستودع فلا يخدمها رابط.
- كلُّ أيقونةٍ بلونَين فقط: العنّابيُّ والأبيض (والبادجُ أبيضُ على شفّاف).
- ما يبقى في `static/brand/` توقيعُ المطوّر وحدَه، والأيقوناتُ كلُّها في `static/icons/v2/` (مجلّدٌ مرقَّم: انظر `test_pwa_icon_urls_are_versioned`).
"""

import pathlib

import numpy as np
from PIL import Image

from core.brand import MAROON, ON_FILL

BRAND = pathlib.Path("static/brand")
ICONS = pathlib.Path("static/icons/v2")

REMOVED = ("logoMaroon.png", "logowhite.png", "emblem.svg", "emblem-white.svg")
DEVELOPER_SIGNATURE = {"azkia-logo.svg", "sufyan-logo.png"}
SQUARE_ICONS = (
    "icon-192.png",
    "icon-512.png",
    "favicon.png",
    "icon-maskable-192.png",
    "icon-maskable-512.png",
    "apple-touch-icon.png",
)


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    return tuple(int(hex_colour.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))


def test_the_ministry_logo_files_and_their_builder_are_gone():
    for name in REMOVED:
        assert not (BRAND / name).exists(), name
    assert not pathlib.Path("scripts/build_emblem.py").exists()


def test_the_brand_folder_holds_only_the_developer_signature():
    names = {p.name for p in BRAND.iterdir() if p.is_file()}
    assert names == DEVELOPER_SIGNATURE, names ^ DEVELOPER_SIGNATURE


def test_the_square_icons_are_white_on_maroon_and_nothing_else():
    allowed = {_rgb(MAROON), _rgb(ON_FILL)}
    for name in SQUARE_ICONS:
        image = Image.open(ICONS / name).convert("RGB")
        assert image.getpixel((0, 0)) == _rgb(MAROON), name
        colours = np.array(image).reshape(-1, 3)
        # التنعيمُ عند حافّة الحرف بين اللونين: كلُّ نقطةٍ على القطعة بين العنّابيّ والأبيض
        maroon, white = np.array(_rgb(MAROON)), np.array(_rgb(ON_FILL))
        span = white - maroon
        ratio = (colours - maroon) / span
        assert (np.abs(ratio - ratio[:, :1]) < 0.02).all(), name
        assert {tuple(c) for c in colours} >= allowed, name


def test_the_badge_is_a_white_glyph_on_transparent():
    pixels = np.array(Image.open(ICONS / "badge-72.png").convert("RGBA"))
    assert (pixels[:, :, 3] == 0).any() and (pixels[:, :, 3] == 255).any()
    visible = pixels[pixels[:, :, 3] > 0][:, :3]
    assert (visible == _rgb(ON_FILL)).all()


def test_the_favicon_ico_carries_the_small_tab_sizes():
    sizes = Image.open(ICONS / "favicon.ico").info["sizes"]
    assert {(16, 16), (32, 32)} <= sizes

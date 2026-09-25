"""شعارُ الواجهة مشتقٌّ من الأصل المسطَّح `static/brand/logoMaroon.png` — لا رسمةٌ أخرى ولا فلترُ تبييض.

كانت الترويسةُ وصفحةُ الدخول وترويسةُ الإدارة وصفحاتُ الخطأ وfavicon وأيقوناتُ التطبيق تعرض `icons/favicon.png`:
رسمةً مظلَّلةً منقوشةً (6371 لوناً، ونحو 40% فقط من تطابق الشكل مع الأصل)، وتُبيَّضُ بفلترٍ
`brightness(0) invert(1)` في أربعة مواضع، وحجمُها 60KB لتُعرض بـ72px.

فصار الأصلُ المسطَّحُ (لونٌ واحدٌ #8A1538 هو Al Adaam) مرجعاً وحيداً:
- `static/brand/emblem.svg` و`emblem-white.svg`: المتّجهُ نفسُه بلونَين، مُتتبَّعٌ من الأصل (`scripts/build_emblem.py`).
- الأيقوناتُ النقطيّةُ (`icons/`) تُرسم من المتّجه بلونٍ واحدٍ دقيق، بلا فلتر.
"""

import pathlib
import re

import numpy as np
from PIL import Image

from core.brand import MAROON, ON_FILL

BRAND = pathlib.Path("static/brand")
ICONS = pathlib.Path("static/icons")

#: ما يُعرض على العنّابيّ يقرأ النسخةَ البيضاءَ مباشرةً — لا فلترَ يحوّل العنّابيَّ إلى أبيض.
WHITE_ON_MAROON = (
    "templates/base/base.html",
    "templates/auth/login.html",
    "templates/admin/base_site.html",
    "templates/errors/_error_page.html",
)

#: أدنى تطابقٍ لشكل الأيقونة مع الأصل (تقاطعٌ على اتّحاد بعد ضبط الصندوق المحيط). الرسمةُ القديمة 0.40.
MIN_SILHOUETTE_MATCH = 0.80


def _silhouette(image: Image.Image, size: int = 256) -> np.ndarray:
    alpha = np.array(image.convert("RGBA"))[:, :, 3] > 128
    ys, xs = np.where(alpha)
    cropped = alpha[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    resized = Image.fromarray((cropped * 255).astype("uint8")).resize(
        (size, size), Image.Resampling.LANCZOS
    )
    return np.array(resized) > 128


def test_the_two_emblem_svgs_are_one_shape_in_two_fills():
    maroon = (BRAND / "emblem.svg").read_text(encoding="utf-8")
    white = (BRAND / "emblem-white.svg").read_text(encoding="utf-8")
    assert f'fill="{MAROON}"' in maroon and f'fill="{ON_FILL}"' in white
    assert (
        maroon.replace(f'fill="{MAROON}"', f'fill="{ON_FILL}"') == white
    )  # الشكلُ نفسُه بايتاً ببايت


def test_the_emblem_svg_stays_small():
    """متّجهٌ مضلَّعٌ من ثلاثة آلاف نقطة: نحو 18KB خاماً و7KB مضغوطاً — لا أثقلَ من النقطيّ الذي حلّ محلّه."""
    assert (BRAND / "emblem.svg").stat().st_size <= 30_000


def test_the_raster_icons_are_the_flat_brand_colour():
    """كلُّ نقطةٍ مرئيّةٍ في الأيقونات بلونٍ واحدٍ هو #8A1538 — لا تظليلَ ولا نقشَ ولا لونٌ أغمق منه."""
    brand_rgb = tuple(int(MAROON.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    for name in ("favicon.png", "icon-192.png", "icon-512.png", "badge-72.png"):
        pixels = np.array(Image.open(ICONS / name).convert("RGBA"))
        visible = pixels[pixels[:, :, 3] > 0][:, :3]
        assert len(visible) and (visible == brand_rgb).all(), name


def test_the_raster_icons_are_drawn_from_the_flat_original_not_another_artwork():
    original = _silhouette(Image.open(BRAND / "logoMaroon.png"))
    for name in ("favicon.png", "icon-192.png", "icon-512.png", "badge-72.png"):
        icon = _silhouette(Image.open(ICONS / name))
        match = (original & icon).sum() / (original | icon).sum()
        assert match >= MIN_SILHOUETTE_MATCH, (name, round(float(match), 3))


def test_the_maroon_surfaces_show_the_white_emblem_and_no_whitening_filter():
    for path in WHITE_ON_MAROON:
        html = pathlib.Path(path).read_text(encoding="utf-8")
        assert "brand/emblem-white.svg" in html, path
        assert "icons/favicon.png" not in re.sub(
            r'<link rel="(icon|apple-touch-icon)"[^>]*>', "", html
        ), path
    for path in pathlib.Path("static/css").rglob("*.css"):
        assert "brightness(0) invert(1)" not in path.read_text(encoding="utf-8"), path
    for path in WHITE_ON_MAROON:
        assert "brightness(0) invert(1)" not in pathlib.Path(path).read_text(encoding="utf-8"), path

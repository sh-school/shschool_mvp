"""أيقوناتُ التطبيق والتبويب والشارة — الرمزُ الكاملُ (الشينُ وحوله المضمار، أمرُ المالك 2026-11-16) على شريحةٍ داكنةٍ محايدة (W-20261014-009، قرار المالك 10-14).

    python manage.py build_app_icons

الأصلُ `static/brand/shahaniya-mark-white.svg` (الرمزُ الكاملُ أبيضَ بلا خلفيّة، علامةُ «الشحانية» v5 من سِمة) فيُرسم على لون الليل المحايد
`core.brand.DARK["SURFACE"]` لا على العنّابيّ. وشعارُ الوزارة لا أثرَ له هنا.

- `icon-192/512`: الرمزُ العنّابيُّ على لوحٍ كريميٍّ بزوايا مدوَّرةٍ شفّافة (v7) — فلا يخفت على شريط مهامّ أو رصيفٍ داكن.
- `icon-maskable-192/512` و`apple-touch-icon`: معتمةٌ كاملةٌ، ويقع **صندوقُ القلم** داخل الدائرة الآمنة
  (80% من الضلع لأندرويد؛ حاشيةٌ تُبعده عن انحناء الزوايا في iOS) بالمسافة الفعليّة من المركز.
- `favicon.png` و`favicon-dark.png` و`favicon.ico` و`favicon.svg`: الختمُ بلا خلفيّةٍ مقصوصَ الهوامش حتى يملأ 96% من العرض (طلبُ المالك 2026-11-26)، في `v7/` مع بقيّة الأيقونات.
- `badge-72`: القلمُ كلُّه أبيضَ على شفّاف — شارةُ الإشعار أحاديّةُ اللون يقصّها النظام.

الرسمُ بـ`svglib` و`reportlab` (في `requirements.txt`) لا بمتصفّح: أداةُ مطوّرٍ تُشغَّل عند تغيير الأصل وحدَه، ويُودَع ناتجُها.
"""

from __future__ import annotations

import io
import math
import re
from pathlib import Path

import numpy as np
from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image, ImageDraw

from core import brand

#: مجلّدٌ مرقَّم: Chrome 144+ لا يعيد تنزيل أيقونةٍ تغيّر محتواها ورابطُها واحد، فتغييرُ الأيقونة = رقمٌ جديد (v4…) لا استبدالُ ملفّ.
#: والمجلّداتُ السابقةُ (`v2` و`v3`) تبقى كما هي: عامِلُ خدمةٍ قديمٌ أو تطبيقٌ مثبَّتٌ قد يطلبها.
ICON_VERSION = "v7"
ICONS = Path(settings.BASE_DIR) / "static" / "icons" / ICON_VERSION
PEN_SVG = Path(settings.BASE_DIR) / "static" / "brand" / "shahaniya-mark-white.svg"
#: الأيقوناتُ الشفّافةُ (التبويب وأيقونتا `any`) على خلفيّاتٍ لا نتحكّم بها فاتحةً كانت أو داكنة: الرمزُ العنّابيّ لا الأبيض كي لا يختفي على التبويب الفاتح.
PEN_SVG_ON_ANY = Path(settings.BASE_DIR) / "static" / "brand" / "shahaniya-mark.svg"

#: لونُ الشريحة الداكنة المحايدة — لا عنّابيّ (قرارُ المالك: الشعارُ على سطحٍ داكنٍ/رماديّ).
BACKGROUND = brand.DARK["SURFACE"]
#: نصفُ قطر الدائرة الآمنة نسبةً إلى الضلع للأيقونة العامّة، والقابلةِ للقصّ (W3C 40%)، وآيفون (يقصّ الزوايا وحدَها).
ANY_SAFE_RADIUS = 0.46
MASKABLE_SAFE_RADIUS = 0.40
APPLE_SAFE_RADIUS = 0.46
#: تدويرُ زوايا اللوح الكريميّ نسبةً إلى الضلع — كما في `mockup_logos.html`.
FAVICON_CORNER = 0.22
#: الختمُ بحدوده المرسومة يملأ هذه النسبةَ من ضلع أيقونة التبويب (طلبُ المالك 2026-11-26: الحدُّ الأدنى 96%).
#: 97% لا أكثر: الهامشُ 1.5% (نحو 4 بكسل من 256) يُبقي حافّةَ الوسط شفّافةً فيحرسها الاختبار.
FAVICON_FILL = 0.97
#: الرسمُ بمقياسٍ أكبر ثمّ التصغير تنعيماً للحواف.
SUPERSAMPLE = 4

#: أيقونتا الغرض `any`: كانتا بلا خلفيّةٍ (قرارُ المالك 10-15) فخفت العنّابيُّ على شريط مهامّ داكن؛
#: فصارتا على لوحٍ كريميٍّ من لون أرضيّة المنصّة بزوايا مدوَّرة (تقييمُ الإنتاج، إذنُ المالك 2026-11-16).
ANY_BACKGROUND = brand.PAGE_BG
ANY_TARGETS = (
    ("icon-192.png", 192, ANY_SAFE_RADIUS),
    ("icon-512.png", 512, ANY_SAFE_RADIUS),
)
#: (الاسم، الضلع، نصفُ قطر الدائرة الآمنة) — مربّعاتٌ معتمةٌ بلا قصٍّ: `maskable` تلزمها خلفيّةٌ بالمواصفة،
#: و`apple-touch` يملأ iOS شفّافَها بالأسود فتبقى معتمةً (يحرسه tests/test_pwa_install.py).
SQUARE_TARGETS = (
    ("icon-maskable-192.png", 192, MASKABLE_SAFE_RADIUS),
    ("icon-maskable-512.png", 512, MASKABLE_SAFE_RADIUS),
    ("apple-touch-icon.png", 180, APPLE_SAFE_RADIUS),
)
#: مقاساتُ التبويب في ملفّ `.ico` — كلٌّ منها يُرسم بحجمه لا يُصغَّر من الأكبر.
ICO_SIZES = (16, 32, 48, 64, 128, 256)


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    return tuple(int(hex_colour.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _render_svg(svg: str, height_px: int, background: str | int) -> Image.Image:
    """يرسم نصَّ SVG بارتفاعٍ معلومٍ فوق لونٍ صلب (النتيجةُ RGB)."""
    from reportlab.graphics import renderPM
    from svglib.svglib import svg2rlg

    drawing = svg2rlg(io.StringIO(svg))
    scale = height_px / drawing.height
    drawing.scale(scale, scale)
    drawing.width, drawing.height = drawing.width * scale, drawing.height * scale
    return renderPM.drawToPIL(
        drawing,
        bg=background if isinstance(background, int) else int(background.lstrip("#"), 16),
        dpi=72,
    ).convert("RGB")


def _pen_svg(on_any: bool = False) -> str:
    return (PEN_SVG_ON_ANY if on_any else PEN_SVG).read_text(encoding="utf-8")


def _aspect() -> float:
    match = re.search(r'viewBox="[\d.-]+ [\d.-]+ ([\d.]+) ([\d.]+)"', _pen_svg())
    assert match, "viewBox مفقود في الأصل"
    return float(match.group(1)) / float(match.group(2))


def _pen_size(size: int, safe_radius: float) -> tuple[int, int]:
    """أبعادُ القلم بالبكسل على لوحةٍ ضلعُها `size` بحيث يقع ركنُ صندوقه داخل الدائرة الآمنة."""
    aspect = _aspect()
    height = 2 * safe_radius * size / math.sqrt(1 + aspect**2)
    return round(height * aspect), round(height)


def farthest_visible_point(image: Image.Image) -> float:
    """أبعدُ مسافةٍ (بالبكسل) عن مركز الصورة لأيّ بكسلٍ مرئيٍّ (ألفا > 0) — لقياس وقوع الرمز داخل الدائرة الآمنة."""
    alpha = image.convert("RGBA").getchannel("A")
    width, height = alpha.size
    pixels = alpha.load()
    centre_x, centre_y = (width - 1) / 2, (height - 1) / 2
    return max(
        (
            math.hypot(x - centre_x, y - centre_y)
            for y in range(height)
            for x in range(width)
            if pixels[x, y] > 0
        ),
        default=0.0,
    )


#: المعتمةُ (maskable وapple-touch): أبعدُ بكسلٍ من الرمز عن المركز ÷ الضلع (أمرُ المالك 2026-11-16: نحو 0.38، والحدُّ الآمن 0.40).
SQUARE_FILL_RADIUS = 0.38


def _drawn_radius_ratio() -> float:
    """أبعدُ بكسلٍ مرسومٍ عن مركز الأصل نسبةً إلى ارتفاعه — الرمزُ دائريٌّ وفي ملفّه هامش، فصندوقُه لا يصلح مقياساً."""
    probe = 512
    image = np.asarray(_render_svg(_pen_svg(), probe, BACKGROUND), dtype=int)
    ys, xs = np.where(np.abs(image - np.array(_rgb(BACKGROUND))).sum(axis=2) > 24)
    centre_x, centre_y = (image.shape[1] - 1) / 2, (image.shape[0] - 1) / 2
    return float(np.sqrt((xs - centre_x) ** 2 + (ys - centre_y) ** 2).max()) / probe


def render_square(size: int, safe_radius: float) -> Image.Image:
    """الرمزُ على مربّعٍ داكنٍ معتم، مُوسَّطاً، وأبعدُ نقطةٍ منه عند `SQUARE_FILL_RADIUS` من الضلع (داخل الدائرة الآمنة)."""
    assert SQUARE_FILL_RADIUS < safe_radius
    height = int(SQUARE_FILL_RADIUS * size / _drawn_radius_ratio())
    width = round(height * _aspect())
    pen = _render_svg(_pen_svg(), height * SUPERSAMPLE, BACKGROUND).resize(
        (width, height), Image.Resampling.LANCZOS
    )
    canvas = Image.new("RGB", (size, size), _rgb(BACKGROUND))
    canvas.paste(pen, ((size - width) // 2, (size - height) // 2))
    return canvas


def _render_svg_rgba(svg: str, height_px: int) -> Image.Image:
    """يرسم SVG بخلفيّةٍ شفّافةٍ فعلاً: مرّتان على أسودَ وأبيضَ ثمّ يُستخرج الألفا من فرقهما."""
    on_black = np.asarray(_render_svg(svg, height_px, 0), dtype=np.float64)
    on_white = np.asarray(_render_svg(svg, height_px, 0xFFFFFF), dtype=np.float64)
    alpha = np.clip(1.0 - (on_white - on_black).mean(axis=2) / 255.0, 0.0, 1.0)
    safe = np.where(alpha[..., None] > 0, alpha[..., None], 1.0)
    colour = np.clip(on_black / safe, 0, 255)
    out = np.dstack([colour, alpha * 255.0]).round().astype(np.uint8)
    return Image.fromarray(out, "RGBA")


#: التبويبُ الداكن: العنّابيُّ يخفت عليه، فيبيضّ الرمزُ في SVG بقاعدةٍ داخل الملفّ (CSS يغلب سمةَ `fill`)، ولمن لا يدعم SVG `favicon-dark.png`.
FAVICON_DARK_STYLE = (
    f"<style>@media (prefers-color-scheme: dark){{path{{fill:{brand.ON_FILL}}}}}</style>"
)


#: ارتفاعُ الرسم الذي تُقاس عليه حدودُ الختم ويُصغَّر منه كلُّ مقاس.
FAVICON_PROBE = 2048


def _seal_square(image: Image.Image) -> tuple[float, float, float]:
    """المربّعُ (يسار، أعلى، ضلع) المحيطُ بالمرسوم، مُوسَّطاً، ويملأ المرسومُ منه `FAVICON_FILL`."""
    box = image.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    assert box, "الرسمُ فارغ"
    left, top, right, bottom = box
    side = max(right - left, bottom - top) / FAVICON_FILL
    return (left + right - side) / 2, (top + bottom - side) / 2, side


def favicon_svg() -> str:
    """`favicon.svg`: الرمزُ العنّابيُّ نفسُه بلا تغييرٍ في المسار، بـviewBox مربّعٍ على حدود الختم وقاعدةِ الوضع الداكن."""
    svg = _pen_svg(on_any=True)
    source = re.search(r'viewBox="([\d.-]+) ([\d.-]+) ([\d.]+) ([\d.]+)"', svg)
    assert source, "viewBox مفقود في الأصل"
    min_x, min_y, _, height = (float(v) for v in source.groups())
    left, top, side = _seal_square(_render_svg_rgba(svg, FAVICON_PROBE))
    unit = height / FAVICON_PROBE
    view = f"{min_x + left * unit:.2f} {min_y + top * unit:.2f} {side * unit:.2f} {side * unit:.2f}"
    svg = svg.replace(source.group(0), f'viewBox="{view}"', 1)
    head, sep, rest = svg.partition("<title>")
    assert sep, "وسمُ title مفقودٌ في الأصل"
    return head + FAVICON_DARK_STYLE + sep + rest


def render_favicon(size: int, on_any: bool = True) -> Image.Image:
    """التبويبُ: الختمُ بلا خلفيّةٍ (ألفا) مقصوصَ الهوامش يملأ المربّع."""
    pen = _render_svg_rgba(_pen_svg(on_any=on_any), FAVICON_PROBE)
    left, top, side = _seal_square(pen)
    # القصُّ قد يتجاوز حدودَ الرسم فيُملأ الزائدُ شفّافاً.
    square = pen.crop((round(left), round(top), round(left + side), round(top + side)))
    return square.resize((size, size), Image.Resampling.LANCZOS)


def write_favicons() -> None:
    """أيقوناتُ التبويب الأربعُ في `ICONS` (`v7/`)، ومجلّدُ `v7/` يُنشأ إن لزم."""
    ICONS.mkdir(parents=True, exist_ok=True)
    render_favicon(256).save(ICONS / "favicon.png", optimize=True)
    render_favicon(48, on_any=False).save(ICONS / "favicon-dark.png", optimize=True)
    (ICONS / "favicon.svg").write_text(favicon_svg(), encoding="utf-8", newline="\n")
    frames = [render_favicon(size) for size in ICO_SIZES]
    frames[-1].save(
        ICONS / "favicon.ico",
        sizes=[(size, size) for size in ICO_SIZES],
        append_images=frames[:-1],
    )


def _rounded_plate(size: int, colour: str, corner: float) -> Image.Image:
    """لوحٌ بلونٍ واحدٍ وزوايا مدوَّرةٍ شفّافة — يُرسم أكبرَ ثمّ يُصغَّر تنعيماً للحافّة."""
    big = size * SUPERSAMPLE
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, big - 1, big - 1), radius=round(big * corner), fill=255
    )
    plate = Image.new("RGBA", (size, size), (*_rgb(colour), 255))
    plate.putalpha(mask.resize((size, size), Image.Resampling.LANCZOS))
    return plate


def render_any(size: int, safe_radius: float) -> Image.Image:
    """أيقونةُ `any`: الرمزُ العنّابيُّ على لوحٍ كريميٍّ مدوَّر الزوايا، بحجم الرمز السابق نفسِه داخل الدائرة الآمنة."""
    width, height = _pen_size(size, safe_radius)
    pen = _render_svg_rgba(_pen_svg(on_any=True), height * SUPERSAMPLE).resize(
        (width, height), Image.Resampling.LANCZOS
    )
    canvas = _rounded_plate(size, ANY_BACKGROUND, FAVICON_CORNER)
    canvas.alpha_composite(pen, ((size - width) // 2, (size - height) // 2))
    return canvas


def render_badge(size: int) -> Image.Image:
    """شارةُ الإشعار: القلمُ كلُّه أبيضَ على شفّاف (قناعُه من رسمه نفسِه بلونٍ واحد)."""
    width, height = _pen_size(size, ANY_SAFE_RADIUS + 0.04)
    solid = re.sub(r'fill="#[0-9A-Fa-f]{6}"', f'fill="{brand.ON_FILL}"', _pen_svg())
    mask = (
        _render_svg(solid, height * SUPERSAMPLE, brand.PRINT_INK)
        .convert("L")
        .resize((width, height), Image.Resampling.LANCZOS)
    )
    badge = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    layer = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    layer.putalpha(mask)
    badge.paste(layer, ((size - width) // 2, (size - height) // 2))
    return badge


class Command(BaseCommand):
    help = (
        "يولّد أيقوناتِ التطبيق والتبويب والشارة من الشعار المشتقّ «قلمٌ وشعلة» على شريحةٍ داكنةٍ محايدة"
    )

    def handle(self, *args: object, **options: object) -> None:
        ICONS.mkdir(parents=True, exist_ok=True)
        write_favicons()
        self.stdout.write("كُتبت أيقوناتُ التبويب (favicon.*)")
        for name, size, safe_radius in ANY_TARGETS:
            render_any(size, safe_radius).save(ICONS / name, optimize=True)
            self.stdout.write(f"كُتبت {name}: {size}×{size} (لوحٌ كريميّ)")
        for name, size, safe_radius in SQUARE_TARGETS:
            render_square(size, safe_radius).save(ICONS / name, optimize=True)
            self.stdout.write(f"كُتبت {name}: {size}×{size}")
        render_badge(128).save(ICONS / "badge-72.png", optimize=True)
        self.stdout.write(self.style.SUCCESS("تمّت أيقوناتُ التطبيق"))

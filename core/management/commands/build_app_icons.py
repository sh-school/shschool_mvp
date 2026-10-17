"""أيقوناتُ التطبيق والتبويب والشارة — المشتقُّ «قلمٌ وشعلة» على شريحةٍ داكنةٍ محايدة (W-20261014-009، قرار المالك 10-14).

    python manage.py build_app_icons

الأصلُ `static/brand/schoolos-pen.svg` (قلمٌ وشعلةٌ، ألوانُه عنّابيّةٌ وذهبيّةٌ تضيع على العنّابيّ) فيُرسم على لون الليل المحايد
`core.brand.DARK["SURFACE"]` لا على العنّابيّ. وشعارُ الوزارة لا أثرَ له هنا.

- `icon-192/512`: مربّعٌ معتمٌ يقع القلمُ كلُّه داخل الدائرة الآمنة العامّة.
- `icon-maskable-192/512` و`apple-touch-icon`: معتمةٌ كاملةٌ، ويقع **صندوقُ القلم** داخل الدائرة الآمنة
  (80% من الضلع لأندرويد؛ حاشيةٌ تُبعده عن انحناء الزوايا في iOS) بالمسافة الفعليّة من المركز.
- `favicon.png` و`favicon.ico`: مربّعٌ بزوايا مدوَّرةٍ شفّافةٍ (22% كما في مرجع المطابقة) والقلمُ يملأ ارتفاعَه تقريباً.
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
from PIL import Image

from core import brand

#: مجلّدٌ مرقَّم: Chrome 144+ لا يعيد تنزيل أيقونةٍ تغيّر محتواها ورابطُها واحد، فتغييرُ الأيقونة = رقمٌ جديد (v4…) لا استبدالُ ملفّ.
#: والمجلّداتُ السابقةُ (`v2` و`v3`) تبقى كما هي: عامِلُ خدمةٍ قديمٌ أو تطبيقٌ مثبَّتٌ قد يطلبها.
ICON_VERSION = "v4"
ICONS = Path(settings.BASE_DIR) / "static" / "icons" / ICON_VERSION
PEN_SVG = Path(settings.BASE_DIR) / "static" / "brand" / "schoolos-pen.svg"

#: لونُ الشريحة الداكنة المحايدة — لا عنّابيّ (قرارُ المالك: الشعارُ على سطحٍ داكنٍ/رماديّ).
BACKGROUND = brand.DARK["SURFACE"]
#: نصفُ قطر الدائرة الآمنة نسبةً إلى الضلع للأيقونة العامّة، والقابلةِ للقصّ (W3C 40%)، وآيفون (يقصّ الزوايا وحدَها).
ANY_SAFE_RADIUS = 0.46
MASKABLE_SAFE_RADIUS = 0.40
APPLE_SAFE_RADIUS = 0.46
#: تدويرُ زوايا التبويب نسبةً إلى الضلع — كما في `mockup_logos.html`.
FAVICON_CORNER = 0.22
#: القلمُ في التبويب يملأ هذه النسبةَ من الارتفاع (الفاصلُ مع الحافّة المدوَّرة).
FAVICON_FILL = 0.88
#: الرسمُ بمقياسٍ أكبر ثمّ التصغير تنعيماً للحواف.
SUPERSAMPLE = 4

#: (الاسم، الضلع، نصفُ قطر الدائرة الآمنة) — مربّعاتٌ معتمةٌ بلا قصٍّ.
SQUARE_TARGETS = (
    ("icon-192.png", 192, ANY_SAFE_RADIUS),
    ("icon-512.png", 512, ANY_SAFE_RADIUS),
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


def _pen_svg() -> str:
    return PEN_SVG.read_text(encoding="utf-8")


def _aspect() -> float:
    match = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', _pen_svg())
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


def render_square(size: int, safe_radius: float) -> Image.Image:
    """القلمُ على مربّعٍ داكنٍ معتم، مُوسَّطاً داخل الدائرة الآمنة."""
    width, height = _pen_size(size, safe_radius)
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


def render_favicon(size: int) -> Image.Image:
    """التبويبُ: القلمُ والشعلةُ بلا خلفيّةٍ (ألفا) يملآن ارتفاعَ المربّع (ملاحظةُ المالك 10-15)."""
    height = round(size * FAVICON_FILL)
    width = round(height * _aspect())
    pen = _render_svg_rgba(_pen_svg(), height * SUPERSAMPLE).resize(
        (width, height), Image.Resampling.LANCZOS
    )
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
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
        for name, size, safe_radius in SQUARE_TARGETS:
            render_square(size, safe_radius).save(ICONS / name, optimize=True)
            self.stdout.write(f"كُتبت {name}: {size}×{size}")
        render_favicon(256).save(ICONS / "favicon.png", optimize=True)
        render_badge(128).save(ICONS / "badge-72.png", optimize=True)
        frames = [render_favicon(size) for size in ICO_SIZES]
        frames[-1].save(
            ICONS / "favicon.ico",
            sizes=[(size, size) for size in ICO_SIZES],
            append_images=frames[:-1],
        )
        self.stdout.write(self.style.SUCCESS("تمّت أيقوناتُ التطبيق"))

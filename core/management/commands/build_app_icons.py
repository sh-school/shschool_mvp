"""أيقوناتُ التطبيق والتبويب — حرفُ «ش» أبيضُ على العنّابيّ (W-20261011-012، قرار المالك D-386م/D-387م).

    python manage.py build_app_icons

شعارُ الوزارة أُزيل من المنصّة كلِّها، فتُرسم الأيقوناتُ هنا من الخطّ (Tajawal Bold) لا من صورة:

- `icon-192/512` و`favicon.png` و`favicon.ico`: «ش» بيضاء على مربّعٍ عنّابيّ #8A1538.
- `icon-maskable-192/512` و`apple-touch-icon`: معتمةٌ كاملةٌ، والحرفُ يقع **كلُّ نقطةٍ منه** داخل الدائرة الآمنة
  (80% من الضلع لأندرويد؛ حاشيةٌ تُبعده عن انحناء الزوايا في iOS) بالمسافة الفعليّة من المركز.
- `badge-72`: «ش» بيضاء على شفّاف (شارةُ الإشعار أحاديّةُ اللون يقصّها النظام).
"""

from __future__ import annotations

import math
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image, ImageDraw, ImageFont

from core import brand

#: مجلّدٌ مرقَّم: Chrome 144+ لا يعيد تنزيل أيقونةٍ تغيّر محتواها ورابطُها واحد، فتغييرُ الأيقونة = رقمٌ جديد (v3…) لا استبدالُ ملفّ.
ICON_VERSION = "v2"
ICONS = Path(settings.BASE_DIR) / "static" / "icons" / ICON_VERSION
FONT = Path(settings.BASE_DIR) / "static" / "fonts" / "Tajawal-Bold.ttf"
GLYPH = "ش"  # ش
#: نصفُ قطر الدائرة التي يقع الحرفُ فيها في الأيقونات غير القابلة للقصّ.
ANY_SAFE_RADIUS = 0.42

#: نصفُ قطر الدائرة الآمنة نسبةً إلى الضلع — مواصفةُ W3C للأيقونة القابلة للقصّ.
MASKABLE_SAFE_RADIUS = 0.40
#: iOS يقصّ الزوايا وحدها، فتكفي حاشيةٌ تُبعد الشعارَ عن انحنائها.
APPLE_SAFE_RADIUS = 0.46
#: شفّافيّةٌ دون هذه تُعدّ فراغاً — حوافُّ التنعيم لا تُحسب شعاراً.
VISIBLE_ALPHA = 8

#: (الاسم، الضلع، نصفُ قطر الدائرة الآمنة) — مربّعاتٌ عنّابيّةٌ معتمة.
SQUARE_TARGETS = (
    ("icon-192.png", 192, ANY_SAFE_RADIUS),
    ("icon-512.png", 512, ANY_SAFE_RADIUS),
    ("favicon.png", 256, ANY_SAFE_RADIUS),
    ("icon-maskable-192.png", 192, MASKABLE_SAFE_RADIUS),
    ("icon-maskable-512.png", 512, MASKABLE_SAFE_RADIUS),
    ("apple-touch-icon.png", 180, APPLE_SAFE_RADIUS),
)


def farthest_visible_point(image: Image.Image) -> float:
    """أبعدُ نقطةٍ مرئيّةٍ عن مركز الصورة، بالبكسل — زوايا البكسل لا مراكزُه."""
    width, height = image.size
    cx, cy = width / 2, height / 2
    alpha = image.getchannel("A").tobytes()  # بايتٌ لكلّ بكسل، صفّاً بعد صفّ
    farthest = 0.0
    for y in range(height):
        dy = max(abs(y - cy), abs(y + 1 - cy))
        row = y * width
        for x in range(width):
            if alpha[row + x] >= VISIBLE_ALPHA:
                dx = max(abs(x - cx), abs(x + 1 - cx))
                farthest = max(farthest, math.hypot(dx, dy))
    return farthest


def glyph_mask(farthest_ratio: float, size: int) -> Image.Image:
    """قناعُ الحرف (قناةٌ ألفا) على لوحةٍ مربّعة، مُوسَّطاً ومُصغَّراً حتى تقع أبعدُ نقطةٍ منه داخل الدائرة الآمنة."""
    probe = 1024
    font = ImageFont.truetype(str(FONT), probe)
    canvas = Image.new("L", (probe * 2, probe * 2), 0)
    ImageDraw.Draw(canvas).text((probe, probe), GLYPH, font=font, fill=255, anchor="mm")
    box = canvas.getbbox()
    if box is None:
        raise RuntimeError("الخطُّ لم يرسم الحرف")
    cropped = canvas.crop(box)
    # أبعدُ زاويةٍ في المربّع المحيط عن مركزه — أحوطُ من اللازم قليلاً فيبقى الحرفُ آمناً
    scale = farthest_ratio * size / (math.hypot(*cropped.size) / 2)
    side = (max(1, round(cropped.width * scale)), max(1, round(cropped.height * scale)))
    scaled = cropped.resize(side, Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    mask.paste(scaled, ((size - side[0]) // 2, (size - side[1]) // 2))
    return mask


def render_square(size: int, safe_radius: float) -> Image.Image:
    """«ش» بيضاء على مربّعٍ عنّابيٍّ معتم."""
    canvas = Image.new("RGB", (size, size), brand.MAROON)
    canvas.paste(Image.new("RGB", (size, size), brand.ON_FILL), mask=glyph_mask(safe_radius, size))
    return canvas


def render_badge(size: int) -> Image.Image:
    """شارةُ الإشعار: «ش» بيضاء على شفّاف."""
    badge = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    badge.putalpha(glyph_mask(ANY_SAFE_RADIUS + 0.05, size))
    return badge


class Command(BaseCommand):
    help = "يولّد أيقوناتِ التطبيق والتبويب: «ش» بيضاء على العنّابيّ"

    def handle(self, *args: object, **options: object) -> None:
        for name, size, safe_radius in SQUARE_TARGETS:
            render_square(size, safe_radius).save(ICONS / name, optimize=True)
            self.stdout.write(f"كُتبت {name}: {size}×{size}")
        render_badge(128).save(ICONS / "badge-72.png", optimize=True)
        render_square(256, ANY_SAFE_RADIUS).save(
            ICONS / "favicon.ico",
            sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
        self.stdout.write(self.style.SUCCESS("تمّت أيقوناتُ التطبيق"))

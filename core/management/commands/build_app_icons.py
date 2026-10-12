"""أيقوناتُ التطبيق والتبويب — شعارُ المدرسة «الكوفيّ المربّع» أبيضَ على العنّابيّ (W-20261012-001، قرار المالك D-394م).

    python manage.py build_app_icons

الرمزُ مرسومٌ هنا من مستطيلاتٍ على شبكةٍ لا من صورة، وهو نفسُه الرمزُ `c2` الذي اختاره المالك من مقترحات الشعار:
شبكةُ 10×9 خليّةً، كلُّ خليّةٍ 10 وحداتٍ في لوحةٍ 120×120، ونقطةُ الرأس العليا بلونٍ مميَّز (الذهبيّ). وشعارُ الوزارة لا أثرَ له.

- `icon-192/512` و`favicon.png` و`favicon.ico`: الرمزُ أبيضَ ونقطتُه ذهبيّةٌ على مربّعٍ عنّابيّ بلون الهويّة (`core.brand.MAROON`).
- `icon-maskable-192/512` و`apple-touch-icon`: معتمةٌ كاملةٌ، ويقع **كلُّ ركنٍ من الرمز** داخل الدائرة الآمنة
  (80% من الضلع لأندرويد؛ حاشيةٌ تُبعده عن انحناء الزوايا في iOS) بالمسافة الفعليّة من المركز.
- `badge-72`: الرمزُ كلُّه (والنقطةُ معه) أبيضَ على شفّاف — شارةُ الإشعار أحاديّةُ اللون يقصّها النظام.
"""

from __future__ import annotations

import math
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image, ImageDraw

from core import brand

#: مجلّدٌ مرقَّم: Chrome 144+ لا يعيد تنزيل أيقونةٍ تغيّر محتواها ورابطُها واحد، فتغييرُ الأيقونة = رقمٌ جديد (v4…) لا استبدالُ ملفّ.
#: والمجلّدُ السابقُ (`v2`) يبقى كما هو: عامِلُ خدمةٍ قديمٌ أو تطبيقٌ مثبَّتٌ قد يطلبه.
ICON_VERSION = "v3"
ICONS = Path(settings.BASE_DIR) / "static" / "icons" / ICON_VERSION

#: لوحةُ الرمز بالوحدات، ومركزُها.
GRID = 120
CENTRE = GRID / 2

#: مستطيلاتُ الرمز (x, y, عرض, ارتفاع) بوحدات اللوحة — مطابقةٌ للرمز `c2` في ملف مقترحات الشعار.
BODY_RECTS = (
    (100, 55, 10, 20),
    (80, 55, 10, 20),
    (60, 55, 10, 20),
    (40, 75, 70, 10),
    (40, 85, 10, 20),
    (10, 95, 40, 10),
    (10, 65, 10, 40),
    (70, 35, 10, 10),
    (90, 35, 10, 10),
)
#: نقطةُ الرأس العليا — لونُها المميَّز في الأيقونات الملوَّنة، وأبيضُ في الأحاديّة.
DOT_RECT = (80, 15, 10, 10)
DOT_COLOUR = brand.GOLD

#: أبعدُ ركنٍ في الرمز عن مركز اللوحة بالوحدات — به تُحسب الدائرةُ الآمنة (ركنُ الساق السفليّ الأيسر).
FARTHEST_UNITS = max(
    math.hypot(px - CENTRE, py - CENTRE)
    for x, y, w, h in (*BODY_RECTS, DOT_RECT)
    for px in (x, x + w)
    for py in (y, y + h)
)

#: نصفُ قطر الدائرة التي يقع الرمزُ فيها في الأيقونات غير القابلة للقصّ، نسبةً إلى الضلع.
ANY_SAFE_RADIUS = 0.42
#: التبويبُ: الخليّةُ سُدسَ عشرَ الضلع تماماً (16 خليّةً على الضلع) فتقع حوافُّها على حدود البكسل في 16 و32 و48 و64…
#: بلا تنعيمٍ يُعتم الرمزَ في المقاسات الصغيرة.
FAVICON_RADIUS = FARTHEST_UNITS / (GRID + 40)
#: نصفُ قطر الدائرة الآمنة نسبةً إلى الضلع — مواصفةُ W3C للأيقونة القابلة للقصّ.
MASKABLE_SAFE_RADIUS = 0.40
#: iOS يقصّ الزوايا وحدها، فتكفي حاشيةٌ تُبعد الشعارَ عن انحنائها.
APPLE_SAFE_RADIUS = 0.46
#: شفّافيّةٌ دون هذه تُعدّ فراغاً — حوافُّ التنعيم لا تُحسب شعاراً.
VISIBLE_ALPHA = 8
#: الرسمُ بمقياسٍ أكبر ثمّ التصغير: حوافُّ الخلايا تُنعَّم بتغطية البكسل لا بالتقريب.
SUPERSAMPLE = 4

#: (الاسم، الضلع، نصفُ قطر الدائرة الآمنة) — مربّعاتٌ عنّابيّةٌ معتمة.
SQUARE_TARGETS = (
    ("icon-192.png", 192, ANY_SAFE_RADIUS),
    ("icon-512.png", 512, ANY_SAFE_RADIUS),
    ("favicon.png", 256, FAVICON_RADIUS),
    ("icon-maskable-192.png", 192, MASKABLE_SAFE_RADIUS),
    ("icon-maskable-512.png", 512, MASKABLE_SAFE_RADIUS),
    ("apple-touch-icon.png", 180, APPLE_SAFE_RADIUS),
)
#: مقاساتُ التبويب في ملفّ `.ico` — كلٌّ منها يُرسم بحجمه لا يُصغَّر من الأكبر فتبقى الخلايا حادّة.
ICO_SIZES = (16, 32, 48, 64, 128, 256)


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


def _to_pixel_edge(position: float) -> float:
    """الإزاحةُ التي تنقل موضعاً (بوحدات المقياس الأكبر) إلى أقرب حدِّ بكسلٍ في الصورة النهائيّة."""
    return round(position / SUPERSAMPLE) * SUPERSAMPLE - position


def _mask(
    rects: tuple[tuple[int, int, int, int], ...], size: int, safe_radius: float
) -> Image.Image:
    """قناعُ المستطيلات على لوحة `size`، مُوسَّطاً ومُصغَّراً حتى يقع أبعدُ ركنٍ في الرمز داخل الدائرة الآمنة."""
    big = size * SUPERSAMPLE
    unit = safe_radius * big / FARTHEST_UNITS
    offset_x = big / 2 - CENTRE * unit
    offset_y = offset_x
    if safe_radius == FAVICON_RADIUS:
        # خطُّ الشبكة الأوّلُ (x=10، y=15) على حدّ بكسلٍ كاملٍ لا في منتصفه، فلا يتنعّم صفُّ الخلايا ويبقى حادّاً.
        offset_x += _to_pixel_edge(offset_x + 10 * unit)
        offset_y += _to_pixel_edge(offset_y + 15 * unit)
    canvas = Image.new("L", (big, big), 0)
    draw = ImageDraw.Draw(canvas)
    for x, y, w, h in rects:
        draw.rectangle(
            (
                round(offset_x + x * unit),
                round(offset_y + y * unit),
                round(offset_x + (x + w) * unit) - 1,
                round(offset_y + (y + h) * unit) - 1,
            ),
            fill=255,
        )
    return canvas.resize((size, size), Image.Resampling.BOX)


def render_square(size: int, safe_radius: float) -> Image.Image:
    """الرمزُ أبيضَ ونقطتُه ذهبيّةٌ على مربّعٍ عنّابيٍّ معتم."""
    canvas = Image.new("RGB", (size, size), brand.MAROON)
    canvas.paste(brand.ON_FILL, mask=_mask(BODY_RECTS, size, safe_radius))
    canvas.paste(DOT_COLOUR, mask=_mask((DOT_RECT,), size, safe_radius))
    return canvas


def render_badge(size: int) -> Image.Image:
    """شارةُ الإشعار: الرمزُ كلُّه أبيضُ على شفّاف."""
    badge = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    badge.putalpha(_mask((*BODY_RECTS, DOT_RECT), size, ANY_SAFE_RADIUS + 0.05))
    return badge


class Command(BaseCommand):
    help = "يولّد أيقوناتِ التطبيق والتبويب: شعار المدرسة (الكوفيّ المربّع) أبيضَ على العنّابيّ"

    def handle(self, *args: object, **options: object) -> None:
        ICONS.mkdir(parents=True, exist_ok=True)
        for name, size, safe_radius in SQUARE_TARGETS:
            render_square(size, safe_radius).save(ICONS / name, optimize=True)
            self.stdout.write(f"كُتبت {name}: {size}×{size}")
        render_badge(128).save(ICONS / "badge-72.png", optimize=True)
        frames = [render_square(size, FAVICON_RADIUS) for size in ICO_SIZES]
        frames[-1].save(
            ICONS / "favicon.ico",
            sizes=[(size, size) for size in ICO_SIZES],
            append_images=frames[:-1],
        )
        self.stdout.write(self.style.SUCCESS("تمّت أيقوناتُ التطبيق"))

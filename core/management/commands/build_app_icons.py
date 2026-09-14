"""أيقوناتُ التطبيق المثبَّت التي يقصّها النظام — من الشعار الشفّاف.

    python manage.py build_app_icons

الشعارُ (`static/icons/icon-512.png`) عنّابيٌّ على شفّافٍ يملأ المربّعَ إلى حوافّه،
وهو الصالحُ لغرض `any`. لكنّ النظامَين يقصّان الأيقونةَ المثبَّتة:

- أندرويد يضع الأيقونةَ القابلةَ للقصّ (`maskable`) في قناعٍ قد يكون دائرةً، ولا
  يضمن إلّا دائرةً قطرُها 80% من الضلع. فالشعارُ المعلَن `any maskable` كان يفقد
  طرفَي السيفين ورأسَ الصاري، ويُملأ شفّافُه بلونٍ داكن.
- iOS يملأ شفّافَ `apple-touch-icon` بالأسود — عنّابيٌّ على أسود لا يُرى.

فيُولَّد هنا نسخٌ معتمةٌ على لون السطح: الشعارُ يُصغَّر حتى تقع **كلُّ نقطةٍ مرئيّةٍ
منه** داخل الدائرة الآمنة، بالمسافة الفعليّة من المركز لا بمربّعه المحيط — فالمربّعُ
المحيط أحوطُ من اللازم بـ√2 ويُصغّر الشعارَ بلا داعٍ.
"""

from __future__ import annotations

import math
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image

from core import brand

ICONS = Path(settings.BASE_DIR) / "static" / "icons"
SOURCE = ICONS / "icon-512.png"

#: نصفُ قطر الدائرة الآمنة نسبةً إلى الضلع — مواصفةُ W3C للأيقونة القابلة للقصّ.
MASKABLE_SAFE_RADIUS = 0.40
#: iOS يقصّ الزوايا وحدها، فتكفي حاشيةٌ تُبعد الشعارَ عن انحنائها.
APPLE_SAFE_RADIUS = 0.46
#: شفّافيّةٌ دون هذه تُعدّ فراغاً — حوافُّ التنعيم لا تُحسب شعاراً.
VISIBLE_ALPHA = 8

TARGETS = (
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


def render(emblem: Image.Image, farthest: float, size: int, safe_radius: float) -> Image.Image:
    scale = safe_radius * size / farthest
    side = math.floor(emblem.width * scale)
    scaled = emblem.resize((side, side), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), brand.SURFACE)
    offset = (size - side) // 2
    canvas.alpha_composite(scaled, (offset, offset))
    return canvas.convert("RGB")


class Command(BaseCommand):
    help = "يولّد أيقوناتِ التطبيق القابلةَ للقصّ وأيقونةَ iOS من الشعار"

    def handle(self, *args: object, **options: object) -> None:
        emblem = Image.open(SOURCE).convert("RGBA")
        farthest = farthest_visible_point(emblem)
        for name, size, safe_radius in TARGETS:
            render(emblem, farthest, size, safe_radius).save(ICONS / name, optimize=True)
            self.stdout.write(f"كُتبت {name}: {size}×{size}")
        self.stdout.write(self.style.SUCCESS("تمّت أيقوناتُ التطبيق"))

"""توليدُ ورقة الرموز من قاموس الأيقونات.

    python manage.py build_icon_sprite            # يكتب static/icons/sprite.svg
    python manage.py build_icon_sprite --check    # يسقط إن اختلف الملفُّ عن ناتجه
    python manage.py build_icon_sprite --refresh <icons.json>

``--refresh`` يعيد اقتطاعَ ``core/icon_sources/hugeicons.json`` من ملفّ
الحزمة الكامل (``npm pack @iconify-json/hugeicons`` ثمّ ``package/icons.json``)
بالأسماء التي يطلبها القاموسُ وحدها — فلا تدخل المستودعَ ستّةُ آلاف رسمٍ لا
تُستعمل، ولا يُنسخ رسمٌ باليد.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core import icon_sprite
from core.icons import ICONS


def _library_names() -> set[str]:
    names = {"school"}  # إطارُ رمز الجناح المحلّيّ
    for icon in ICONS.values():
        if icon.kind == "hi":
            names.add(icon.source)
        elif icon.kind == "cmp":
            names.add(icon.source.split("+")[0])
    return names


class Command(BaseCommand):
    help = "يولّد static/icons/sprite.svg من core/icons.py"

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true", help="تحقّقٌ بلا كتابة")
        parser.add_argument(
            "--refresh", metavar="ICONS_JSON", help="إعادةُ اقتطاع المصدر من ملفّ الحزمة الكامل"
        )

    def handle(self, *args, check=False, refresh=None, **options):
        if refresh:
            self._refresh(Path(refresh))

        sprite = icon_sprite.build_sprite()
        # نهايةُ السطر لا تُحسب: غيت على Windows يسحب الملفَّ بـCRLF
        current = (
            icon_sprite.SPRITE.read_text(encoding="utf-8").replace("\r\n", "\n")
            if icon_sprite.SPRITE.exists()
            else ""
        )
        if check:
            if current != sprite:
                raise CommandError(
                    "ورقةُ الرموز تخالف القاموس — شغّل: python manage.py build_icon_sprite"
                )
            self.stdout.write(self.style.SUCCESS(f"الورقةُ مطابقة — {len(ICONS)} أيقونة"))
            return
        icon_sprite.SPRITE.write_text(sprite, encoding="utf-8", newline="\n")
        self.stdout.write(
            self.style.SUCCESS(
                f"كُتبت {icon_sprite.SPRITE.name}: {len(ICONS)} أيقونة، {len(sprite):,} بايت"
            )
        )

    def _refresh(self, path: Path) -> None:
        full = json.loads(path.read_text(encoding="utf-8"))
        package = json.loads((path.parent / "package.json").read_text(encoding="utf-8"))
        wanted = sorted(_library_names())
        missing = [n for n in wanted if n not in full["icons"]]
        if missing:
            raise CommandError(f"رسومٌ يطلبها القاموسُ وليست في الحزمة: {', '.join(missing)}")
        subset = {
            "package": package["name"],
            "version": package["version"],
            "license": icon_sprite.library()["license"],
            "width": full.get("width", 24),
            "height": full.get("height", 24),
            "icons": {n: full["icons"][n]["body"] for n in wanted},
        }
        icon_sprite.SOURCE.write_text(
            json.dumps(subset, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
        )
        icon_sprite.library.cache_clear()
        self.stdout.write(
            f"اقتُطع المصدر: {len(wanted)} رسماً من {package['name']}@{package['version']}"
        )

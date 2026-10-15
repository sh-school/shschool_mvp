"""أيقوناتُ التطبيق: المشتقُّ «قلمٌ وشعلة» على شريحةٍ داكنةٍ محايدة (W-20261014-009، قرار المالك 10-14؛ يحلّ محلّ «ش» v3).

- أيقوناتُ `static/icons/v4/` مرسومةٌ من `static/brand/schoolos-pen.svg` على `core.brand.DARK["SURFACE"]` لا على العنّابيّ.
- ما يبقى في `static/brand/` توقيعُ المطوّر وشعارا المنصّة (الكاملُ والمشتقّ)؛ ولا ملفَّ شعارِ وزارةٍ فيه.
- شارةُ الإشعار أبيضُ على شفّاف يقصّها النظام، وتباينُ الشريحة مع الأيقونة محفوظ.
- لا مرجعَ في الشيفرة إلى مجلّدٍ سابقٍ (`v2`/`v3`)، وكلُّ أيقونةٍ مذكورةٍ بمسارها موجودة.
"""

import pathlib
import re

import numpy as np
import pytest
from PIL import Image

from core.brand import DARK, ON_FILL
from core.management.commands.build_app_icons import ICON_VERSION

ROOT = pathlib.Path(__file__).resolve().parent.parent
BRAND = ROOT / "static/brand"
ICONS = ROOT / "static/icons/v4"

REMOVED = ("logoMaroon.png", "logowhite.png", "emblem.svg", "emblem-white.svg", "ministry_logo.png")
BRAND_FILES = {"azkia-logo.svg", "sufyan-logo.png", "schoolos-full.svg", "schoolos-pen.svg"}
SQUARE_ICONS = (
    "icon-192.png",
    "icon-512.png",
    "icon-maskable-192.png",
    "icon-maskable-512.png",
    "apple-touch-icon.png",
)
#: ما يُفحص بحثاً عن مراجع الأيقونات: القوالبُ والسكربتاتُ والمانيفستاتُ وشيفرةُ الإشعارات.
SOURCE_SUFFIXES = {".html", ".js", ".json", ".py", ".css"}
SOURCE_ROOTS = ("templates", "static/js", "static/css", "notifications", "core", "parents", "pwa")


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    return tuple(int(hex_colour.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))


def test_the_icon_folder_is_the_current_version():
    assert ICON_VERSION == "v4" and ICONS.is_dir()


def test_the_ministry_logo_files_are_not_in_the_static_brand_folder():
    for name in REMOVED:
        assert not (BRAND / name).exists(), name
    assert not (ROOT / "scripts/build_emblem.py").exists()


def test_the_brand_folder_holds_only_the_platform_marks_and_the_developer_signature():
    names = {p.name for p in BRAND.iterdir() if p.is_file()}
    assert names == BRAND_FILES, names ^ BRAND_FILES


@pytest.mark.parametrize("name", SQUARE_ICONS)
def test_the_square_icons_sit_on_the_neutral_dark_chip_not_on_maroon(name):
    image = Image.open(ICONS / name).convert("RGB")
    assert image.getpixel((0, 0)) == _rgb(DARK["SURFACE"]), name
    assert image.getpixel((image.width - 1, image.height - 1)) == _rgb(DARK["SURFACE"]), name
    centre = np.array(image)[
        image.height // 4 : image.height * 3 // 4, image.width // 2 - 8 : image.width // 2 + 8
    ]
    assert (centre != np.array(_rgb(DARK["SURFACE"]))).any(), "الرمزُ غائبٌ عن وسط الأيقونة"


@pytest.mark.parametrize(
    "name, safe",
    [
        ("icon-maskable-192.png", 0.40),
        ("icon-maskable-512.png", 0.40),
        ("apple-touch-icon.png", 0.46),
    ],
)
def test_the_symbol_stays_inside_the_safe_circle(name, safe):
    """كلُّ بكسلٍ مخالفٍ للخلفيّة يقع داخل الدائرة الآمنة (مع سماحٍ للتنعيم)."""
    image = np.array(Image.open(ICONS / name).convert("RGB")).astype(int)
    size = image.shape[0]
    ys, xs = np.where(np.abs(image - np.array(_rgb(DARK["SURFACE"]))).sum(axis=2) > 24)
    radius = np.sqrt((xs - size / 2) ** 2 + (ys - size / 2) ** 2).max() / size
    assert radius <= safe + 0.02, (name, radius)


def test_the_badge_is_the_whole_symbol_in_white_on_transparent():
    pixels = np.array(Image.open(ICONS / "badge-72.png").convert("RGBA"))
    assert (pixels[:, :, 3] == 0).any() and (pixels[:, :, 3] == 255).any()
    visible = pixels[pixels[:, :, 3] > 0][:, :3]
    assert (visible == _rgb(ON_FILL)).all(), "الشارةُ أحاديّةُ اللون"


def test_the_favicon_has_no_background_plate():
    """بلا خلفيّة (ملاحظةُ المالك 10-15): الزوايا والحوافُّ شفّافةٌ والقلمُ معتمٌ في الوسط، ولا لونَ لوحٍ صلباً."""
    pixels = np.array(Image.open(ICONS / "favicon.png").convert("RGBA"))
    assert pixels[0, 0, 3] == 0 and pixels[0, -1, 3] == 0
    assert pixels[pixels.shape[0] // 2, 4, 3] == 0, "حافّةُ الوسط شفّافةٌ لا لوحٌ"
    assert (pixels[:, :, 3] > 250).any(), "القلمُ مرئيّ"
    assert (pixels[:, :, 3] == 0).mean() > 0.5, "أغلبُ المربّع شفّاف"


def test_the_favicon_ico_carries_the_small_tab_sizes():
    sizes = Image.open(ICONS / "favicon.ico").info["sizes"]
    assert {(16, 16), (32, 32), (48, 48)} <= sizes


def _source_files():
    for root in SOURCE_ROOTS:
        base = ROOT / root
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix in SOURCE_SUFFIXES and "migrations" not in path.parts:
                yield path


def test_no_reference_to_a_superseded_icon_folder():
    """مجلّداتُ الأيقونات السابقة (`v2`…) تبقى على القرص لتطبيقٍ قديم، لكنّ الشيفرةَ لا تشير إليها."""
    stale = []
    pattern = re.compile(r"icons/v(\d+)/")
    current = int(ICON_VERSION.lstrip("v"))
    for path in [*_source_files(), *ROOT.glob("*.py")]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for found in pattern.findall(text):
            if int(found) != current and path.name != pathlib.Path(__file__).name:
                stale.append(f"{path.relative_to(ROOT)}: icons/v{found}/")
    assert not stale, stale


def test_every_icon_named_by_path_exists():
    missing = []
    for path in _source_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name in re.findall(r"icons/v\d+/([\w.-]+\.(?:png|ico|svg|webp))", text):
            if not (ICONS / name).exists():
                missing.append(f"{path.relative_to(ROOT)}: {name}")
    assert not missing, missing


@pytest.mark.parametrize(
    "worker, prefix",
    [("templates/pwa/sw_global.js", "global"), ("templates/parents/pwa/sw.js", "parents")],
)
def test_the_service_worker_cache_name_moved_with_the_icons(worker, prefix):
    """تغيّرُ أيقونةٍ مذكورةٍ في عامل الخدمة يرفع اسمَ ذاكرته فتُبطَل النسخةُ القديمة عند المستخدمين."""
    source = (ROOT / worker).read_text(encoding="utf-8")
    name = re.search(rf"CACHE_NAME\s*=\s*'schoolos-{prefix}-v(\d+)'", source)
    assert name and int(name.group(1)) >= (7 if prefix == "global" else 6)

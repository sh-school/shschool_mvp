"""شعارُ المدرسة «الكوفيّ المربّع» أيقونةُ التطبيق — ولا شعارَ وزارةٍ في أيّ أصلٍ (W-20261012-001، قرار المالك D-394م).

سبق ذلك W-20261011-012 (D-386م/D-387م): أُزيل شعارُ الوزارة من المنصّة كلِّها وصارت الأيقوناتُ تُرسم بـ`manage.py build_app_icons`.
وهذا الحارسُ يثبّت الحالةَ كما هي:
- ملفّاتُ شعار الوزارة وأداةُ اشتقاقها لم تعد في المستودع فلا يخدمها رابط.
- كلُّ أيقونةٍ مربّعةٍ بثلاثة ألوانٍ فقط: العنّابيُّ والأبيضُ والذهبيُّ لنقطة الرأس (والبادجُ أبيضُ على شفّاف).
- الرمزُ مطابقٌ للرمز `c2` المختار: مساحةُ مستطيلاته وموضعُ نقطتِه.
- تباينُ الرمز على العنّابيّ ≥ 3:1 (WCAG للعناصر الرسوميّة).
- ما يبقى في `static/brand/` توقيعُ المطوّر وحدَه، والأيقوناتُ كلُّها في `static/icons/v3/` (مجلّدٌ مرقَّم).
- لا مرجعَ في الشيفرة إلى مجلّدٍ سابقٍ (`v2`)، وكلُّ أيقونةٍ مذكورةٍ بمسارها موجودة.
"""

import pathlib
import re

import numpy as np
import pytest
from PIL import Image

from core.brand import GOLD, MAROON, ON_FILL
from core.management.commands.build_app_icons import (
    ANY_SAFE_RADIUS,
    BODY_RECTS,
    CENTRE,
    DOT_RECT,
    FARTHEST_UNITS,
    GRID,
    ICON_VERSION,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
BRAND = ROOT / "static/brand"
ICONS = ROOT / "static/icons/v3"

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
#: ما يُفحص بحثاً عن مراجع الأيقونات: القوالبُ والسكربتاتُ والمانيفستاتُ وشيفرةُ الإشعارات.
SOURCE_SUFFIXES = {".html", ".js", ".json", ".py", ".css"}
SOURCE_ROOTS = ("templates", "static/js", "static/css", "notifications", "core", "parents", "pwa")


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    return tuple(int(hex_colour.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))


def _luminance(colour: tuple[int, int, int]) -> float:
    def channel(value: int) -> float:
        v = value / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in colour)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_the_icon_folder_is_the_current_version():
    assert ICON_VERSION == "v3" and ICONS.is_dir()


def test_the_ministry_logo_files_and_their_builder_are_gone():
    for name in REMOVED:
        assert not (BRAND / name).exists(), name
    assert not (ROOT / "scripts/build_emblem.py").exists()


def test_the_brand_folder_holds_only_the_developer_signature():
    names = {p.name for p in BRAND.iterdir() if p.is_file()}
    assert names == DEVELOPER_SIGNATURE, names ^ DEVELOPER_SIGNATURE


def _on_blend_line(pixels: np.ndarray, foreground: tuple[int, int, int]) -> np.ndarray:
    """أيّ البكسلات تقع على القطعة بين العنّابيّ واللون الأماميّ (حوافُّ التنعيم)، بسماحٍ لتقريب الأعداد الصحيحة."""
    maroon = np.array(_rgb(MAROON), dtype=float)
    span = np.array(foreground, dtype=float) - maroon
    t = np.clip(((pixels - maroon) @ span) / float(span @ span), 0, 1)
    return np.linalg.norm(pixels - (maroon + t[:, None] * span), axis=1) <= 2.0


@pytest.mark.parametrize("name", SQUARE_ICONS)
def test_the_square_icons_use_maroon_white_and_gold_only(name):
    image = Image.open(ICONS / name).convert("RGB")
    assert image.getpixel((0, 0)) == _rgb(MAROON), name
    pixels = np.array(image).reshape(-1, 3).astype(float)
    on_white = _on_blend_line(pixels, _rgb(ON_FILL))
    on_gold = _on_blend_line(pixels, _rgb(GOLD))
    assert (on_white | on_gold).all(), "لونٌ غريبٌ على الأيقونة"
    colours = {tuple(int(v) for v in c) for c in pixels}
    assert {_rgb(MAROON), _rgb(ON_FILL), _rgb(GOLD)} <= colours, "الأيقونةُ ثلاثيّةُ الألوان"


def test_the_symbol_is_the_chosen_one_in_the_big_icon():
    """مساحةُ المستطيلات البيضاء وموضعُ النقطة الذهبيّة كما في الرمز `c2` عند نصف قطر الدائرة الآمنة المعتمد."""
    size = 512
    image = Image.open(ICONS / "icon-512.png").convert("RGB")
    unit = ANY_SAFE_RADIUS * size / FARTHEST_UNITS
    pixels = np.array(image)

    white = int((pixels == np.array(_rgb(ON_FILL))).all(axis=2).sum())
    cells = np.zeros((GRID, GRID), dtype=bool)  # اتّحادُ المستطيلات: بعضُها يتداخل في الركن
    for x, y, w, h in BODY_RECTS:
        cells[y : y + h, x : x + w] = True
    expected = int(cells.sum()) * unit * unit
    assert abs(white - expected) / expected < 0.03, (white, expected)

    x, y, w, h = DOT_RECT
    cx = int(size / 2 + (x + w / 2 - CENTRE) * unit)
    cy = int(size / 2 + (y + h / 2 - CENTRE) * unit)
    assert tuple(pixels[cy, cx]) == _rgb(GOLD)


def test_the_symbol_contrasts_with_the_maroon_background():
    maroon = _rgb(MAROON)
    assert _contrast(_rgb(ON_FILL), maroon) >= 3
    assert _contrast(_rgb(GOLD), maroon) >= 3


def test_the_badge_is_the_whole_symbol_in_white_on_transparent():
    pixels = np.array(Image.open(ICONS / "badge-72.png").convert("RGBA"))
    assert (pixels[:, :, 3] == 0).any() and (pixels[:, :, 3] == 255).any()
    visible = pixels[pixels[:, :, 3] > 0][:, :3]
    assert (visible == _rgb(ON_FILL)).all(), "الشارةُ أحاديّةُ اللون"
    # النقطةُ العليا داخلةٌ في الشارة الأحاديّة
    size = pixels.shape[0]
    unit = (ANY_SAFE_RADIUS + 0.05) * size / FARTHEST_UNITS
    x, y, w, h = DOT_RECT
    cx = int(size / 2 + (x + w / 2 - CENTRE) * unit)
    cy = int(size / 2 + (y + h / 2 - CENTRE) * unit)
    assert pixels[cy, cx, 3] == 255


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
    assert name and int(name.group(1)) >= 5

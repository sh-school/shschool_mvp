"""يشتقّ شعارَ الواجهة المتّجهيَّ وأيقوناتِه من الأصل المسطَّح — أداةُ مطوِّرٍ لا تُشغَّل في الإنتاج.

    python scripts/build_emblem.py            # من جذر المشروع
    python manage.py build_app_icons          # ثمّ: المقصوصاتُ وأيقونةُ iOS من icon-512.png

الأصلُ `static/brand/logoMaroon.png` (295×295) لونٌ واحدٌ مسطّحٌ (العنّابيّ Al Adaam) بحوافّ ناعمة. تُتتبَّع حوافُّه من ألفا
مكبَّرةٍ 8× (تكعيبيّاً) لا من البكسلات، فيخرج مضلَّعٌ بأجزاءٍ من البكسل:

- `static/brand/emblem.svg` و`emblem-white.svg`: المتّجهُ بلونَين (الأبيضُ لما يُعرض على العنّابيّ، بلا فلتر).
- `static/icons/{icon-512,icon-192,favicon,badge-72}.png`: تُرسم من المتّجه بلونٍ دقيقٍ واحد (لوحةُ 32 مستوى
  ألفا، نحو 5–16KB بدل 20–205KB) — فلا تظليلَ ولا نقشَ ولا لونٌ يخالف العنّابيَّ الرسميّ.
- `static/icons/icon-{192,512}.webp`: النسخُ غيرُ المستعمَلة اليومَ، تُبقى متّسقةً مع الرسمة.

يحتاج: numpy وPillow وopencv-python-headless وPyMuPDF (كلُّها للتطوير؛ ليست في requirements).
`tests/test_brand_emblem.py` يحرس النتيجة: لونٌ واحد، وتطابقُ الشكل مع الأصل، وبلا فلتر تبييض.
"""

import sys
from pathlib import Path

import cv2
import fitz  # PyMuPDF — يرسم SVG بألفا
import numpy as np
from PIL import Image

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
sys.path.insert(0, str(ROOT.resolve()))  # الألوانُ تُقرأ من core.brand لا تُنسخ

from core.brand import MAROON, ON_FILL  # noqa: E402
SOURCE = ROOT / "static" / "brand" / "logoMaroon.png"
BRAND = ROOT / "static" / "brand"
ICONS = ROOT / "static" / "icons"

MAROON_RGB = tuple(int(MAROON[i : i + 2], 16) for i in (1, 3, 5))
SCALE = 8  # التكبيرُ قبل التتبّع
EPSILON = 1.2  # تبسيطُ المضلَّع بوحدة البكسل المكبَّر (1/8 بكسلٍ أصليّ)
ALPHA_LEVELS = 32  # مستوياتُ الشفّافيّة في لوحة الـPNG


def trace() -> tuple[str, int]:
    """(بياناتُ المسار، ضلعُ ViewBox المكبَّر) — المربّعُ المحيطُ بالشعار يتوسّطه."""
    alpha = np.array(Image.open(SOURCE).convert("RGBA"))[:, :, 3]
    ys, xs = np.where(alpha > 128)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    side = int(max(x1 - x0, y1 - y0))
    origin_x = int(round((x0 + x1) / 2 - side / 2)) * SCALE
    origin_y = int(round((y0 + y1) / 2 - side / 2)) * SCALE
    big = cv2.resize(alpha, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_CUBIC)
    _, binary = cv2.threshold(big, 127, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    parts = []
    for contour in contours:
        points = cv2.approxPolyDP(contour, EPSILON, True).reshape(-1, 2)
        if len(points) < 3:
            continue
        xs_, ys_ = points[:, 0] - origin_x, points[:, 1] - origin_y
        path = f"M{xs_[0]} {ys_[0]}"
        for i in range(1, len(points)):
            path += f"l{xs_[i] - xs_[i - 1]} {ys_[i] - ys_[i - 1]}"
        parts.append(path + "z")
    return "".join(parts), side * SCALE


def svg(path: str, box: int, fill: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {box} {box}" '
        f'width="{box // SCALE}" height="{box // SCALE}">'
        f'<path fill="{fill}" fill-rule="evenodd" d="{path}"/></svg>'
    )


def render(svg_text: str, size: int) -> Image.Image:
    page = fitz.open(stream=svg_text.encode("utf-8"), filetype="svg")[0]
    zoom = size / page.rect.width
    pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=True)
    return Image.frombytes("RGBA", (pixmap.width, pixmap.height), pixmap.samples)


def save_flat_png(image: Image.Image, target: Path) -> None:
    """لونٌ واحدٌ دقيقٌ + ألفا بـ32 مستوى — لوحةُ PNG بدل RGBA كاملة."""
    alpha = np.array(image)[:, :, 3]
    indices = np.rint(alpha.astype(float) * (ALPHA_LEVELS - 1) / 255).astype("uint8")
    palette = Image.fromarray(indices, "P")
    palette.putpalette(list(MAROON_RGB) * ALPHA_LEVELS)
    transparency = bytes(round(i * 255 / (ALPHA_LEVELS - 1)) for i in range(ALPHA_LEVELS))
    palette.save(target, "PNG", optimize=True, transparency=transparency)


def main() -> None:
    path, box = trace()
    maroon, white = svg(path, box, MAROON), svg(path, box, ON_FILL)
    (BRAND / "emblem.svg").write_text(maroon, encoding="utf-8", newline="\n")
    (BRAND / "emblem-white.svg").write_text(white, encoding="utf-8", newline="\n")
    print(f"emblem.svg: {(BRAND / 'emblem.svg').stat().st_size} بايت")
    for name, size in (("icon-512.png", 512), ("icon-192.png", 192), ("favicon.png", 256), ("badge-72.png", 128)):
        save_flat_png(render(maroon, size), ICONS / name)
        print(f"{name}: {(ICONS / name).stat().st_size} بايت")
    for name, size in (("icon-512.webp", 512), ("icon-192.webp", 192)):
        render(maroon, size).save(ICONS / name, "WEBP", lossless=True, quality=100, method=6)
    print("ثمّ: python manage.py build_app_icons")


if __name__ == "__main__":
    main()

"""التطبيقُ المثبَّت على الجوال يفتح بشاشةٍ كاملة (قرارُ 2026-09-14).

`fullscreen` يُخفي شريطَ الحالة وأزرارَ النظام في أندرويد، وما لا يدعمه يرجع
من نفسه إلى `standalone`. لكنّ كشفَ «التطبيق مثبَّت» كان يسأل عن `standalone`
وحدَه، فلو بقي كذلك لظهر شريطُ «ثبّت المنصّة» داخل التطبيق المثبَّت نفسِه.
"""

import json
import math
import re
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from core.management.commands.build_app_icons import (
    APPLE_SAFE_RADIUS,
    MASKABLE_SAFE_RADIUS,
    farthest_visible_point,
)

ROOT = Path(__file__).resolve().parent.parent
MANIFESTS = ["templates/pwa/manifest_global.json", "templates/parents/pwa/manifest.json"]


def _read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def _icons(manifest):
    block = re.search(r'"icons":\s*(\[.*?\])', _read(manifest), re.S).group(1)
    return json.loads(block)


@pytest.mark.parametrize("manifest", MANIFESTS)
def test_installed_app_opens_fullscreen(manifest):
    display = re.search(r'"display":\s*"([^"]+)"', _read(manifest))
    assert display and display.group(1) == "fullscreen"


@pytest.mark.parametrize("manifest", MANIFESTS)
def test_screen_rotation_is_not_locked(manifest):
    """الجداولُ العريضة تُقرأ أفقيّاً، والجهازُ اللوحيُّ يُمسك بالعرض."""
    assert '"orientation"' not in _read(manifest)


@pytest.mark.parametrize("manifest", MANIFESTS)
def test_the_cropped_icon_is_a_separate_file(manifest):
    """`any maskable` معاً يعني ملفّاً واحداً للغرضين، فيُقصّ الشعارُ الممتدُّ إلى حوافّه."""
    icons = _icons(manifest)
    assert all(i["purpose"] in ("any", "maskable") for i in icons)
    for purpose in ("any", "maskable"):
        assert {i["sizes"] for i in icons if i["purpose"] == purpose} == {"192x192", "512x512"}
    for icon in icons:
        assert (ROOT / icon["src"].lstrip("/")).exists(), icon["src"]


@pytest.mark.parametrize(
    "name, safe_radius",
    [
        ("icon-maskable-192.png", MASKABLE_SAFE_RADIUS),
        ("icon-maskable-512.png", MASKABLE_SAFE_RADIUS),
        ("apple-touch-icon.png", APPLE_SAFE_RADIUS),
    ],
)
def test_cropped_icons_are_opaque_and_the_emblem_fits_the_safe_circle(name, safe_radius):
    icon = Image.open(ROOT / "static" / "icons" / name)
    assert icon.mode == "RGB", "الشفّافُ يُملأ بالأسود في iOS وبلونٍ داكنٍ في أندرويد"

    # الشعارُ ما خالف لونَ الزاوية بأكثرَ من 24 في أيّ قناة
    difference = ImageChops.difference(icon, Image.new("RGB", icon.size, icon.getpixel((0, 0))))
    emblem = ImageChops.lighter(ImageChops.lighter(*difference.split()[:2]), difference.split()[2])
    emblem = emblem.point(lambda v: 255 if v > 24 else 0)
    probe = Image.merge("RGBA", (emblem, emblem, emblem, emblem))
    # بكسلٌ واحدٌ سماحاً للتنعيم عند الحافّة
    assert farthest_visible_point(probe) <= safe_radius * icon.width + math.sqrt(2)


@pytest.mark.parametrize("template", ["templates/base/base.html", "templates/auth/login.html"])
def test_ios_home_screen_uses_the_opaque_icon(template):
    assert "icons/apple-touch-icon.png" in _read(template)


@pytest.mark.parametrize("source", ["static/js/base.js", "templates/parents/dashboard.html"])
def test_fullscreen_counts_as_installed(source):
    text = _read(source)
    assert "display-mode: fullscreen" in text
    assert "display-mode: standalone" in text


def test_global_manifest_is_valid_json(client_as, school, teacher_user):
    response = client_as(teacher_user).get("/manifest.json")
    assert json.loads(response.content)["display"] == "fullscreen"


def test_the_app_is_named_from_the_school_record(client_as, school, teacher_user):
    """الاسمُ من سجلّ المدرسة لا نصٌّ مُثبَّت (قرار 2026-09-14) — والمنصّةُ متعدّدةُ المدارس.

    وعلامةُ تنصيصٍ في الاسم لا تكسر JSON.
    """
    school.name = 'مدرسة "التجربة" الثانوية'
    school.city = "الوكرة"
    school.save(update_fields=["name", "city"])

    manifest = json.loads(client_as(teacher_user).get("/manifest.json").content)

    assert manifest["name"] == school.name
    assert manifest["short_name"] == school.city
    assert school.name in manifest["description"]


@pytest.mark.parametrize(
    "template",
    [
        "templates/pwa/manifest_global.json",
        "templates/base/base.html",
        "templates/parents/dashboard.html",
    ],
)
def test_no_school_name_is_frozen_in_the_app_identity(template):
    assert "الشحانية" not in _read(template)

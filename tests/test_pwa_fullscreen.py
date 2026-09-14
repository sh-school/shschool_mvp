"""التطبيقُ المثبَّت على الجوال يفتح بشاشةٍ كاملة (قرارُ 2026-09-14).

`fullscreen` يُخفي شريطَ الحالة وأزرارَ النظام في أندرويد، وما لا يدعمه يرجع
من نفسه إلى `standalone`. لكنّ كشفَ «التطبيق مثبَّت» كان يسأل عن `standalone`
وحدَه، فلو بقي كذلك لظهر شريطُ «ثبّت المنصّة» داخل التطبيق المثبَّت نفسِه.
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "manifest", ["templates/pwa/manifest_global.json", "templates/parents/pwa/manifest.json"]
)
def test_installed_app_opens_fullscreen(manifest):
    display = re.search(r'"display":\s*"([^"]+)"', _read(manifest))
    assert display and display.group(1) == "fullscreen"


@pytest.mark.parametrize("source", ["static/js/base.js", "templates/parents/dashboard.html"])
def test_fullscreen_counts_as_installed(source):
    text = _read(source)
    assert "display-mode: fullscreen" in text
    assert "display-mode: standalone" in text


def test_global_manifest_is_valid_json(client_as, school, teacher_user):
    response = client_as(teacher_user).get("/manifest.json")
    assert json.loads(response.content)["display"] == "fullscreen"

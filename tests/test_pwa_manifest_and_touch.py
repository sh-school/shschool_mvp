"""[MOBILE Q-12، Q-08] المنصّةُ مثبَّتةً تطبيقاً، واللمسُ بلا تأخير.

Q-12 — المانيفستان (العامّ وبوّابةُ وليّ الأمر) متّسقان:
- `display: standalone` (قرارُ D9): تطبيقُ عملٍ يحتاج شريطَ الحالة وزرَّ الرجوع، و`fullscreen` يخفيهما.
- `id` ثابت: `start_url` في العامّ يتغيّر بالدور، وبلا `id` تُشتقّ هويّةُ التطبيق منه فيصير لكلّ دورٍ تطبيقٌ.
- لا `orientation`: قفلُ الاتّجاه يخالف WCAG 1.3.4.

Q-08 — `touch-action: manipulation` على التحكّمات فلا ينتظر المتصفّحُ نقرةً مزدوجة، و`aria-current="page"`
على عنصر الشريط السفليّ الحاليّ فيعلن القارئُ موضعَ المستخدم.
"""

import json
import re
from pathlib import Path

import pytest
from django.urls import reverse

from tests.css_source import read_css

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parent.parent


def _manifest(client, url):
    response = client.get(url)
    assert response.status_code == 200
    return json.loads(response.content.decode())


@pytest.fixture
def manifests(client, client_as, parent_user):
    return {
        "global": _manifest(client, reverse("global_manifest")),
        # بوّابةُ وليّ الأمر خلف الدخول — مانيفستُها كذلك.
        "parents": _manifest(client_as(parent_user), reverse("pwa_manifest")),
    }


def test_both_manifests_are_standalone_with_a_stable_id_and_no_orientation_lock(manifests):
    for name, data in manifests.items():
        assert data["display"] == "standalone", name
        assert data.get("id"), name
        assert "orientation" not in data, name
        assert data["lang"] == "ar" and data["dir"] == "rtl", name
    assert manifests["global"]["id"] != manifests["parents"]["id"]


def test_the_global_id_does_not_follow_the_role_start_url(client, teacher_user, client_as):
    anonymous = _manifest(client, reverse("global_manifest"))
    teacher = _manifest(client_as(teacher_user), reverse("global_manifest"))

    assert anonymous["start_url"] != teacher["start_url"]  # يتغيّر بالدور
    assert anonymous["id"] == teacher["id"]  # والهويّةُ واحدة


def test_controls_do_not_wait_for_a_double_tap():
    css = re.sub(r"/\*.*?\*/", "", read_css(), flags=re.S)
    rule = re.search(r"([^{}]*)\{\s*touch-action:\s*manipulation;?\s*\}", css)
    assert rule, "لا touch-action: manipulation على التحكّمات"
    selectors = {s.strip() for s in rule.group(1).split(",")}
    assert {"a", "button", "input", "select", "textarea", "summary"} <= selectors, selectors


def test_the_current_bottom_nav_item_is_announced():
    source = (ROOT / "static" / "js" / "base.js").read_text(encoding="utf-8")
    assert re.search(
        r"\.mobile-nav-item\.active'\)\.forEach\(function\s*\(a\)\s*\{\s*a\.setAttribute\('aria-current', 'page'\)",
        source,
    ), "عنصرُ الشريط السفليّ الحاليّ بلا aria-current"

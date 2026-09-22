"""[PRIVACY] P1-3 — عاملُ خدمة بوّابة وليّ الأمر لا يحفظ صفحةً شخصيّة.

كان يحفظ كلَّ صفحةٍ تحت /parents/ — درجاتِ الابن وغيابَه وسلوكَه — بلا نظرٍ في
حالة الردّ ولا في ``no-store``، ويعرضها بلا شبكةٍ لمن يفتح الجهاز بعد الخروج.
والعاملُ ملفُّ JavaScript لا يُشغَّل هنا، فالحارسُ يقرأ نصَّه: ما يُحفظ، ومتى.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings

SW = Path(settings.BASE_DIR) / "templates" / "parents" / "pwa" / "sw.js"


@pytest.fixture(scope="module")
def source():
    return SW.read_text(encoding="utf-8")


def test_cache_version_moved_past_the_one_that_held_pages(source):
    """رفعُ الإصدار هو ما يمحو ذاكرةَ v2 من الأجهزة عند التفعيل."""
    name = re.search(r"CACHE_NAME\s*=\s*'schoolos-parents-v(\d+)'", source)

    assert name and int(name.group(1)) >= 3


def test_only_the_offline_page_is_precached(source):
    assets = re.search(r"CACHE_ASSETS\s*=\s*\[([^\]]*)\]", source).group(1)

    assert "'/parents/'" not in assets
    assert assets.strip() == "OFFLINE_URL"


def test_navigations_are_never_written_to_the_cache(source):
    block = re.search(r"mode === 'navigate'\)\s*\{(.*?)\n  \}", source, re.S).group(1)

    assert "cache.put" not in block
    assert "OFFLINE_URL" in block


def test_every_cache_write_is_guarded(source):
    """لا حفظَ إلّا لثابتٍ ناجحٍ لا يمنع الخادمُ حفظَه."""
    assert "if (!isStatic(url)) return;" in source
    writes = source.count("cache.put(")
    guarded = len(
        re.findall(
            r"if \(cacheable\(res\)\) \{\s*const clone = res\.clone\(\);\s*caches\.open", source
        )
    )

    assert writes == guarded == 2


def test_notification_icons_exist(source):
    for icon in re.findall(r"'(/static/icons/[^']+)'", source):
        assert (Path(settings.BASE_DIR) / icon.lstrip("/")).exists(), icon


@pytest.mark.django_db
def test_logout_clears_the_browser_cache(client_as, teacher_user):
    client = client_as(teacher_user)

    response = client.post("/auth/logout/")

    assert response.status_code == 302
    assert response["Clear-Site-Data"] == '"cache"'

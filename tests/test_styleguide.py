"""[DESIGN] دليلُ الهويّة الواحد — يعرض ما في المصدر، لا نسخةً منه.

كان للمنصّة دليلان وصفحةُ أيقونات: القديمُ يكتب ألوانَ العلامة أرقاماً تباعدت
عن `:root`، وصفحةُ الأيقونات تعرض ورقةَ Lucide القديمة (محذوفةٌ 2026-09-18)
بلا معنى واحدٍ منها في الكود. فهنا يُقاس أنّ الدليلَ نافذةٌ على المصدر: كلُّ
لونٍ في `:root` يُعرض باسمه، وكلُّ معنًى في `core/icons.py`.
"""

import re

import pytest
from django.urls import reverse

from core.icons import ICONS
from core.styleguide import colour_token_groups, icon_dictionary_groups
from core.templatetags.ui import KPI_TONES
from tests.css_source import read_css


def _tokens():
    return [name for group in colour_token_groups() for name in group["tokens"]]


def test_the_palette_lists_the_brand_and_state_colours_by_name():
    names = _tokens()

    for expected in ("maroon", "maroon-fg", "on-fill", "status-danger-fg", "chart-1", "swap-fg"):
        assert expected in names, expected
    assert len(names) == len(set(names))


def test_the_palette_holds_colours_only():
    """الظلُّ والمسافةُ والخطُّ رموزٌ في `:root` أيضاً — لكنّ مربّعَ اللون لا يرسمها."""
    names = set(_tokens())

    for not_a_colour in ("shadow-sm", "focus-ring", "radius", "sp-4", "text-sm", "q-font-ui"):
        assert not_a_colour not in names, not_a_colour


def test_every_hex_token_in_root_reaches_the_palette():
    """رمزٌ يُضاف إلى `:root` برقمٍ سداسيٍّ يظهر في الدليل بلا تعديل."""
    css = re.sub(r"/\*.*?\*/", "", read_css(), flags=re.S)
    first_root = re.search(r":root\s*\{([^}]*)\}", css).group(1)
    hex_tokens = set(re.findall(r"--([\w-]+)\s*:\s*#[0-9A-Fa-f]{3,8}\s*;", first_root))

    assert hex_tokens and hex_tokens <= set(_tokens()), sorted(hex_tokens - set(_tokens()))


def test_the_icon_page_lists_every_meaning_in_the_dictionary():
    groups = icon_dictionary_groups()
    listed_keys = {entry["key"] for group in groups for entry in group["icons"]}

    assert listed_keys == set(ICONS)
    assert sum(len(group["icons"]) for group in groups) == len(ICONS)


@pytest.mark.django_db
def test_the_old_guide_route_is_a_permanent_redirect(client, teacher_user):
    client.force_login(teacher_user)

    response = client.get("/styleguide/")

    assert response.status_code == 301
    assert response["Location"] == reverse("ui_components")


@pytest.mark.django_db
def test_the_guide_renders_every_component_and_links_the_icons(client, developer_user):
    client.force_login(developer_user)

    html = client.get(reverse("ui_components")).content.decode()

    assert 'style="--swatch:var(--maroon)"' in html
    assert reverse("icon_preview") in html
    for tone in KPI_TONES:
        assert f'class="ui-kpi kpi-{tone}' in html, tone
    for tone in ("success", "warning", "danger", "info"):
        assert f"ui-entity__status is-{tone}" in html
    assert "ui-entity__status is-neutral" in html
    assert 'class="action-card action-primary"' in html
    assert "ui-section is-flush" in html
    for badge in ("success", "danger", "warning", "info", "maroon", "gray"):
        assert f"status-badge status-{badge}" in html


@pytest.mark.django_db
def test_the_icon_page_renders_every_meaning(client, developer_user):
    client.force_login(developer_user)

    html = client.get(reverse("icon_preview")).content.decode()

    for key in ICONS:
        assert f">{key}<" in html, key


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["ui_components", "icon_preview"])
def test_the_guide_is_for_the_platform_developer_only(client, teacher_user, principal_user, name):
    """قرارُ المالك 2026-09-20: لا يراه معلّمٌ ولا مدير — 403 — ولا زائرٌ غيرُ مسجَّل."""
    assert client.get(reverse(name)).status_code == 302
    for user in (teacher_user, principal_user):
        client.force_login(user)
        assert client.get(reverse(name)).status_code == 403, (name, user)

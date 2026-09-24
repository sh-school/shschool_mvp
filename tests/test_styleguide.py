"""[DESIGN] دليلُ الهويّة الواحد — يعرض ما في المصدر، لا نسخةً منه.

كان للمنصّة دليلان وصفحةُ أيقونات: القديمُ يكتب ألوانَ العلامة أرقاماً تباعدت
عن `:root`، وصفحةُ الأيقونات تعرض ورقةَ Lucide القديمة (محذوفةٌ 2026-09-18)
بلا معنى واحدٍ منها في الكود. فهنا يُقاس أنّ الدليلَ نافذةٌ على المصدر: كلُّ
لونٍ في `:root` يُعرض باسمه، وكلُّ معنًى في `core/icons.py`.
"""

import pathlib
import re

import pytest
from django.urls import reverse

from core.icons import ICONS
from core.styleguide import (
    breakpoints,
    colour_token_groups,
    icon_dictionary_groups,
    scale_tokens,
)
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


def test_the_scales_are_read_from_root_in_order():
    """سلالمُ الأسس من `:root` نفسِه — درجةٌ تُضاف هناك تظهر في الدليل بلا تعديل."""
    scales = scale_tokens()
    names = {key: [t["name"] for t in tokens] for key, tokens in scales.items()}

    assert names["text"][0] == "text-xs" and "text-3xl" in names["text"]
    assert "text-primary" not in names["text"]
    assert names["space"][:3] == ["sp-0-5", "sp-1", "sp-1-5"] and names["space"][-1] == "sp-16"
    assert names["radius"][0] == "radius-sm" and names["radius"][-1] == "radius-pill"
    assert "shadow-sm" in names["shadow"] and "shadow-ink" not in names["shadow"]
    assert "transition-page" in names["motion"] and "lh-ar" in names["leading"]


def test_the_minimum_measures_are_read_from_root():
    """H-06: ارتفاعُ التحكّم والطبقاتُ والمنطقةُ الآمنة تُقرأ كالسلالم — رمزٌ جديدٌ يظهر بلا قالب."""
    scales = scale_tokens()
    layers = [t["name"] for t in scales["layer"]]

    assert "control-h" in [t["name"] for t in scales["control"]]
    assert layers[0] == "z-base" and layers.index("z-dropdown") < layers.index("z-modal")
    assert "safe" in scales  # فارغٌ حتّى H-04، والقسمُ يقول ذلك صراحةً


def test_the_breakpoints_match_the_layout_kpi_definition():
    """جدولُ الدليل هو مؤشّرُ الخارطة LK2 نفسُه: المتجاورتان بفارق 1px حدٌّ واحد."""
    points = [bp["px"] for bp in breakpoints()]
    css = re.sub(r"/\*.*?\*/", "", read_css(), flags=re.S)
    widths = sorted(
        {
            int(w)
            for cond in re.findall(r"@media\s*([^{]+)\{", css)
            for w in re.findall(r"(?:min|max)-width\s*:\s*(\d+)px", cond)
        }
    )
    expected = [w for prev, w in zip([-9, *widths], widths, strict=False) if w - prev > 1]

    assert points == expected
    assert 640 in points and all(b - a > 1 for a, b in zip(points, points[1:], strict=False))


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
    # الأسسُ وأنماطُ التخطيط: كلُّ سلّمٍ يُرسم من رموزه، والبطاقاتُ في تدفّقٍ واحد.
    assert 'class="card-flow"' in html
    assert "{#" not in html
    for sample in (
        "--size:var(--text-sm)",
        "--bar:var(--sp-4)",
        "--r:var(--radius-md)",
        "--shadow:var(--shadow-md)",
        "--swatch:var(--chart-1)",
    ):
        assert f'style="{sample}"' in html, sample
    assert "المقاييسُ والحدودُ الدنيا</h2>" in html
    for token in ("--control-h", "--z-modal"):
        assert f'<bdi dir="ltr">{token}</bdi>' in html, token
    for title in (
        "الخطّ",
        "التباعدُ والتقوّس",
        "الظلالُ والارتفاع",
        "الحركةُ والتركيز",
        "الجداول",
        "الرسومُ البيانيّة",
        "الشبكاتُ والتخطيط",
        "الوضعُ الداكن",
        "الترويسةُ والقائمةُ والذيل",
    ):
        assert f"· {title}</h2>" in html, title


@pytest.mark.django_db
def test_the_icon_page_renders_every_meaning(client, developer_user):
    client.force_login(developer_user)

    html = client.get(reverse("icon_preview")).content.decode()

    for key in ICONS:
        assert f">{key}<" in html, key
    # كلُّ مجموعةٍ بطاقةٌ في تدفّقٍ واحد، وعرضُها بعدد أيقوناتها؛ وألوانُ الأيقونة الستّةُ معروضة.
    assert 'class="card-flow"' in html
    for group in icon_dictionary_groups():
        assert f'<h2 class="ui-section__title">{group["label"]}</h2>' in html, group["label"]
    assert "ui-section is-full" in html and "ui-section is-wide" in html
    for tone in ("maroon", "success", "danger", "warning", "info", "muted"):
        assert f'class="icon-{tone}"' in html, tone
    # تعليقُ القالب لا يتسرّب نصّاً إلى الصفحة.
    assert "{#" not in html


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["ui_components", "icon_preview", "ui_layouts"])
def test_the_guide_is_for_the_platform_developer_only(client, teacher_user, principal_user, name):
    """قرارُ المالك 2026-09-20: لا يراه معلّمٌ ولا مدير — 403 — ولا زائرٌ غيرُ مسجَّل."""
    assert client.get(reverse(name)).status_code == 302
    for user in (teacher_user, principal_user):
        client.force_login(user)
        assert client.get(reverse(name)).status_code == 403, (name, user)


#: الأنماطُ السبعة بقرار D-16 (2026-09-23) — المواصفاتُ في docs/design/page_layouts.md.
LAYOUTS = ("dashboard", "hub", "list", "detail", "form", "sheet", "report")


@pytest.mark.django_db
def test_the_layouts_page_shows_the_seven_layouts_and_the_four_states(client, developer_user):
    client.force_login(developer_user)

    html = client.get(reverse("ui_layouts")).content.decode()

    for name in LAYOUTS:
        assert f"layout-{name}" in html, name
    # ثلاثةُ أجهزةٍ لكلّ نمط: سطحُ المكتب واللوحيّ والجوال.
    assert html.count('class="sg-wire"') == 3 * len(LAYOUTS)
    for state in ("تحميل", "فارغة", "خطأ", "ممتلئة"):
        assert state in html, state
    assert reverse("ui_components") in html


@pytest.mark.django_db
def test_the_guide_links_the_layouts_page(client, developer_user):
    client.force_login(developer_user)

    html = client.get(reverse("ui_components")).content.decode()

    assert reverse("ui_layouts") in html


def test_the_palette_groups_the_header_nav_menu_and_footer_tokens_together():
    """الترويسةُ والقائمةُ والقوائمُ المنسدلة والذيلُ مجموعةٌ واحدة في اللوحة — لا تتناثر في «أخرى»."""
    groups = {group["label"]: group["tokens"] for group in colour_token_groups()}

    chrome = groups["الترويسةُ والقائمةُ والذيل"]
    for name in (
        "header-bg",
        "nav-bg",
        "nav-fg",
        "nav-hover",
        "nav-mark",
        "menu-bg",
        "menu-hover",
        "menu-rule",
        "menu-label",
        "footer-bg",
        "footer-fg",
        "footer-fg-soft",
    ):
        assert name in chrome, name


_SWITCH_LINK = re.compile(
    r'<a href="(?P<href>/styleguide/[a-z]+/)" class="(?P<kind>btn-primary|btn-secondary) btn-sm"'
    r'(?P<current> aria-current="page")?>'
)


@pytest.mark.django_db
@pytest.mark.parametrize("page", ["ui_components", "icon_preview", "ui_layouts"])
def test_every_guide_page_carries_the_same_three_page_switch(client, developer_user, page):
    """مفتاحُ الدليل: أزرارُ صفحاته الثلاث دائمةٌ في ترويسة كلٍّ منها، والحاليّةُ مملوءةٌ وعليها aria-current."""
    client.force_login(developer_user)

    html = client.get(reverse(page)).content.decode()
    links = [m.groupdict() for m in _SWITCH_LINK.finditer(html)]

    assert [link["href"] for link in links] == [
        reverse("ui_components"),
        reverse("icon_preview"),
        reverse("ui_layouts"),
    ]
    current = [link for link in links if link["current"]]
    assert [link["href"] for link in current] == [reverse(page)]
    assert current[0]["kind"] == "btn-primary"
    assert all(link["kind"] == "btn-secondary" for link in links if not link["current"])


def test_the_layouts_spec_names_the_same_seven_layouts():
    spec = (pathlib.Path(__file__).resolve().parents[1] / "docs/design/page_layouts.md").read_text(
        encoding="utf-8"
    )
    assert sorted(set(re.findall(r"`layout-([a-z]+)`", spec)) - {"custom"}) == sorted(LAYOUTS)


# ── أنماطُ الدليل في ملفٍّ مستقلٍّ لا يُشحن لغير المطوّر ──

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_GUIDE_SHEET = "css/styleguide.css"


def test_only_the_guide_pages_load_the_guide_sheet():
    loaders = sorted(
        path.relative_to(_ROOT / "templates").as_posix()
        for path in (_ROOT / "templates").rglob("*.html")
        if _GUIDE_SHEET in path.read_text(encoding="utf-8")
    )
    assert loaders == [
        "styleguide/components.html",
        "styleguide/icon_preview.html",
        "styleguide/layouts.html",
    ]


def test_guide_classes_live_only_in_the_guide_sheet():
    """`sg-` في ملفّات المنصّة يعود إلى الحِمل المشحون لكلّ مستخدم."""
    assert not re.search(r"\.sg-[\w-]", read_css())
    assert ".sg-wire" in (_ROOT / "static" / _GUIDE_SHEET).read_text(encoding="utf-8")


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["ui_components", "icon_preview", "ui_layouts"])
def test_each_guide_page_links_the_guide_sheet(client, developer_user, name):
    client.force_login(developer_user)

    assert "styleguide" in client.get(reverse(name)).content.decode().split("</head>")[0]

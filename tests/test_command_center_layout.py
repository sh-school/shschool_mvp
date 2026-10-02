"""[COMMAND-CENTER] إعادةُ تخطيط الصفحة (W-20261002-027): ستُّ مجموعاتٍ مرتَّبةٌ، وبلاطةُ مؤشّرٍ برقمها الحقيقيّ وهدفها بدل القرص، وشريطُ «ما ينتظرك الآن».

ثوابتُ المحافظة: عقدُ اللقطة v1 لم يتغيّر، وكلُّ لوحةٍ في مجموعةٍ واحدة، والهدفُ يُبنى من عتبة المجمِّع لا من رقمٍ مخمَّن، والشريطُ لا يعرض ما لا يراه الخادم.
"""

import pathlib
import re

import pytest
from django.core.cache import cache
from django.urls import reverse

from command_center import contract, layout
from command_center.collectors import database, guards

pytestmark = pytest.mark.django_db

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def _page(client_as, developer_user):
    return client_as(developer_user).get(reverse("command_center:index")).content.decode()


def test_every_registered_panel_is_in_exactly_one_group():
    members = [key for _, _, keys in layout.GROUPS for key in keys]
    registered = {p.key for p in contract.PANELS}
    assert not registered - set(members), "لوحةٌ بلا مجموعة"
    assert len(members) == len(set(members)), "لوحةٌ في مجموعتين"
    # المسموحُ بما ليس مسجَّلاً بعدُ: لوحةُ الطابور (فرعٌ لم يُدمج) تُتجاوز عند غيابها
    assert set(members) - registered <= {"queue"}


def test_featured_and_targets_refer_to_real_panels_and_slots():
    keys = {p.key for p in contract.PANELS} | {"queue"}
    assert set(layout.FEATURED) <= keys
    assert set(layout.TARGETS) <= keys
    assert all(1 <= index <= contract.MAX_METRICS for index in layout.FEATURED.values())


def test_targets_are_built_from_the_collectors_own_thresholds():
    """لا رقمَ مخمَّناً: تتبع الأهدافُ العتباتِ إن تغيّرت."""
    assert str(round(database.CONN_WARN * 100)) in layout.TARGETS["database"]
    assert str(guards.BAD_MARGIN) in layout.TARGETS["guards"]
    from roadmap.admin_monitor import BACKUP_OK_HOURS

    assert str(BACKUP_OK_HOURS) in layout.TARGETS["production"]


def test_inside_a_group_the_worst_state_comes_first():
    contract.store("database", {"status": "bad", "headline": "x"})
    contract.store("messaging", {"status": "warn", "headline": "x"})
    contract.store("production", {"status": "ok", "headline": "x"})
    prod = next(g for g in layout.groups(contract.read_panels()) if g["key"] == "prod")
    order = [t["key"] for t in prod["tiles"]]
    assert order.index("database") < order.index("messaging") < order.index("production")
    assert prod["worst"] == "bad" and prod["worst_label"] == "✖ خطر"
    assert prod["ok"] == 1 and prod["total"] == 5


def test_the_strip_shows_only_what_the_server_sees():
    contract.store("ci", {"status": "bad", "headline": "x"})
    contract.store(
        "pulls", {"status": "ok", "headline": "x", "m3_l": "إيداعاتٌ غيرُ منشورة", "m3_v": "4"}
    )
    strip = layout.strip(contract.read_panels())
    assert strip["reds"] == ["فحوصُ CI"]
    assert strip["unpublished"] == "4"
    assert set(strip) == {
        "reds",
        "bad_count",
        "warns",
        "unknown",
        "unpublished",
        "unpublished_text",
    }  # لا قراراتٍ ولا ما في الدفتر المحلّيّ
    assert strip["bad_count"] == 1


def test_the_strip_never_invents_an_unpublished_count():
    assert layout.strip(contract.read_panels())["unpublished"] is None


def test_the_page_renders_groups_in_order_with_header_and_counter(client_as, developer_user):
    html = _page(client_as, developer_user)
    positions = [html.index(f'data-group="{key}"') for key, _, _ in layout.GROUPS]
    assert positions == sorted(positions)
    assert "الإنتاجُ وجاهزيّته" in html and "الأمانُ والامتثال" in html
    assert re.search(r'data-key="group\.prod\.state">[^<]*من 5 سليمة', html)


def test_the_dial_is_gone_and_each_row_shows_state_as_text_and_symbol(client_as, developer_user):
    html = _page(client_as, developer_user)
    assert "data-dial" not in html and "qc-dial" not in html and "data-gauge" not in html
    assert "؟ غير معلوم" in html  # الحالةُ نصّاً ورمزاً لا لوناً وحدَه


def test_every_panel_has_exactly_one_bar_with_its_reading(client_as, developer_user):
    """طلبُ المالك: بارٌ لكلّ مؤشّر. القيمةُ من قراءة اللوحة، وبلا قراءةٍ 0 مع نصٍّ بديل."""
    contract.store("ci", {"status": "ok", "headline": "x", "gauge": 82})
    html = _page(client_as, developer_user)
    assert html.count("progress-qatar qc-panel__bar") == len(
        contract.PANELS
    )  # بارُ الهويّة المركزيّ لا عنصرٌ محلّيّ
    assert "<progress" not in html
    assert re.search(
        r'aria-valuenow="82"[^>]*data-bar><span class="progress-qatar-fill pf-success" style="--progress-w:82%"',
        html,
    )
    assert 'aria-valuetext="لم تُجمَع بعدُ"' in html  # لوحةٌ لم تُجمَع: لا بارَ مملوءاً يوهم سليماً


def test_the_two_cards_sit_side_by_side_and_are_the_last_child_so_they_fill_without_scroll(
    client_as, developer_user
):
    html = _page(client_as, developer_user)
    assert (
        html.count('class="ui-grid-2 qc-cards"') == 1
    )  # شبكةُ بطاقتين: تتجاوران حيث يتّسع، و`qc-cards` يُطابقهما طولاً
    assert [title for title, _ in layout.CARDS] == ["التشغيلُ والأمان", "التسليمُ والجودةُ والخطّة"]
    for title, _ in layout.CARDS:
        assert title in html
    grid = html.index('class="ui-grid-2 qc-cards"')
    # البطاقتان آخرُ أبناء الغلاف فتملآن الباقيَ بلا تمرير (50-utilities: .ui-grid-2:last-child)
    assert html.index("data-qc-note") < grid


def test_cards_hold_every_group_once_in_a_fixed_order():
    placed = [key for _, keys in layout.CARDS for key in keys]
    assert sorted(placed) == sorted(key for key, _, _ in layout.GROUPS)
    grouped = layout.groups(contract.read_panels())
    cards = layout.cards(grouped)
    assert [[g["key"] for g in c["groups"]] for c in cards] == [
        ["prod", "security"],
        ["shipping", "quality", "plan"],
    ]


def test_each_panel_has_a_unique_key_per_metric_slot(client_as, developer_user):
    """الرقمُ الكبير يحمل مفتاحَ مؤشّره فلا يتكرّر في القائمة (وإلّا لم يجد التحديثُ الحيُّ المكانَ الصحيح)."""
    html = _page(client_as, developer_user)
    keys = re.findall(r'data-key="([a-z]+\.m[1-4][lv])"', html)
    assert len(keys) == len(set(keys))
    for panel in contract.PANELS:
        index = layout.FEATURED.get(panel.key)
        if index:
            assert f'data-key="{panel.key}.m{index}v"' in html
            assert f'data-row="{panel.key}.m{index}"' not in html


def test_the_strip_says_no_red_when_none_and_never_mentions_decisions(client_as, developer_user):
    html = _page(client_as, developer_user)
    strip = html.split('data-key="strip.reds"')[1].split("</p>")[0]
    assert "لا لوحةَ في حالة خطر" in html
    assert "قرار" not in strip
    # «الإيداعات غير المنشورة» لم تُجمَع لوحتُها: يُسمّى مجهولاً («؟») لا صفراً
    assert re.search(r'data-key="strip\.unpublished">؟<', html)


def test_the_panel_picker_and_its_cookie_are_gone_entirely(client_as, developer_user):
    """طلبُ المالك 2026-10-02: التخلّصُ من زرّ «المؤشّراتُ المعروضة» ومن كوده — لا زرَّ ولا نافذةَ ولا كوكي ولا مسارَ خادمٍ ولا سكربت."""
    html = _page(client_as, developer_user)
    for gone in (
        "المؤشّراتُ المعروضة",
        "data-qc-toggle",
        "data-qc-all",
        "data-qc-count",
        "qc-panels",
        "qcc_hidden",
        "data-modal-open",
    ):
        assert gone not in html, gone
    assert not (ROOT / "templates" / "command_center" / "_picker.html").exists()
    assert not (ROOT / "tests" / "test_command_center_picker.py").exists()
    script = (ROOT / "static" / "js" / "command_center.js").read_text(encoding="utf-8")
    views = (ROOT / "command_center" / "views.py").read_text(encoding="utf-8")
    for gone in ("qcc_hidden", "HIDDEN_COOKIE", "saveHidden", "applyChoices", "document.cookie"):
        assert gone not in script and gone not in views, gone
    assert "hidden_keys" not in views


def test_the_two_cards_are_stretched_to_the_same_size_even_in_the_no_scroll_mode():
    """`.ui-grid-2:last-child > .ui-section` تبدأ بارتفاع محتواها في وضع بلا تمرير؛ هذه القاعدةُ تمدّدهما معاً (آخرُ طبقةٍ فتغلب)."""
    css = (ROOT / "static" / "css" / "custom" / "50-utilities.css").read_text(encoding="utf-8")
    assert re.search(r"\.qc-cards:last-child > \.ui-section \{ align-self: stretch;", css)


def test_the_script_labels_match_the_server_labels_and_it_has_no_dial():
    source = (ROOT / "static" / "js" / "command_center.js").read_text(encoding="utf-8")
    match = re.search(r"var STATE_LABEL = \{([^}]*)\}", source)
    pairs = dict(re.findall(r'(\w+): "([^"]+)"', match.group(1)))
    assert pairs == layout.STATE_LABELS
    assert "paintDial" not in source and "data-dial" not in source
    assert "paintBar" in source and "[data-bar]" in source


# ── الهويّةُ المركزيّة: مكوّناتٌ لا ألوانٌ محلّيّة، ولا (i) مزيّفة ─────────────────────────────────────────


def test_the_strip_is_four_central_kpi_cards_with_live_keys(client_as, developer_user):
    html = _page(client_as, developer_user)
    assert html.count('class="ui-kpis"') == 1 and html.count('class="ui-kpi kpi-') == 4
    for key in ("strip.bad", "strip.warn", "strip.unknown", "strip.unpublished"):
        assert f'data-key="{key}"' in html
    for tone in ("kpi-red", "kpi-amber", "kpi-sky", "kpi-maroon"):
        assert tone in html


def test_no_always_shown_info_callout_with_a_fake_info_icon(client_as, developer_user):
    """«i لا تعمل» (المالك 2026-10-02): `callout "info" show=True` يرسم أيقونةَ (i) تبدو زرّاً وهي لا تعمل. المعلومةُ الحقيقيّةُ تلميحٌ بزرّ (ui-tip) في الترويسة وحدَها."""
    html = _page(client_as, developer_user)
    source = (ROOT / "templates" / "command_center" / "index.html").read_text(encoding="utf-8")
    live = re.sub(r"\{#.*?#\}", "", source, flags=re.S)  # بلا التعليقات (فيها ذكرُ الممنوع شرحاً)
    assert 'callout "info" show=True' not in live
    assert html.count('class="ui-tip ') <= 1  # تلميحُ الترويسة وحدَه


def test_status_badge_and_bar_use_the_central_identity_classes_and_no_local_colors(
    client_as, developer_user
):
    html = _page(client_as, developer_user)
    assert html.count("status-badge status-") >= len(contract.PANELS)
    css = (ROOT / "static" / "css" / "custom" / "33-modules-4.css").read_text(encoding="utf-8")
    block = css[css.index("/* مركز قيادة الجودة (QCC-01b") : css.index("/* نافذةُ التسجيل السريع")]
    assert not re.search(
        r"#[0-9a-fA-F]{3,8}\b|rgb\(|hsl\(", block
    ), "لونٌ حرفيّ — الهويّةُ رموزٌ var(--…) وحدَها"
    for old in ("accent-color", "--c:", "--fg:"):
        assert old not in block, old


def test_the_script_paints_the_central_bar_and_badge_not_local_elements():
    source = (ROOT / "static" / "js" / "command_center.js").read_text(encoding="utf-8")
    assert "--progress-w" in source and "progress-qatar-fill" in source
    assert "status-success" in source and "status-gray" in source
    assert "strip.counts" not in source

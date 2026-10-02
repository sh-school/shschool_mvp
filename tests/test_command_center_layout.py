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


def _page(client_as, developer_user, **cookies):
    client = client_as(developer_user)
    for name, value in cookies.items():
        client.cookies[name] = value
    return client.get(reverse("command_center:index")).content.decode()


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
        "warns",
        "unknown",
        "unpublished",
    }  # لا قراراتٍ ولا ما في الدفتر المحلّيّ


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
    assert html.count("<progress") == len(contract.PANELS)
    assert re.search(r'<progress[^>]*value="82"[^>]*data-bar', html)
    assert 'aria-valuetext="لم تُجمَع بعدُ"' in html  # لوحةٌ لم تُجمَع: لا بارَ مملوءاً يوهم سليماً


def test_the_two_cards_sit_side_by_side_and_are_the_last_child_so_they_fill_without_scroll(
    client_as, developer_user
):
    html = _page(client_as, developer_user)
    assert html.count('class="ui-grid-2"') == 1  # شبكةُ بطاقتين: تتجاوران حيث يتّسع
    assert [title for title, _ in layout.CARDS] == ["التشغيلُ والأمان", "التسليمُ والجودةُ والخطّة"]
    for title, _ in layout.CARDS:
        assert title in html
    grid = html.index('class="ui-grid-2"')
    # البطاقتان آخرُ أبناء الغلاف فتملآن الباقيَ بلا تمرير (50-utilities: .ui-grid-2:last-child)
    assert html.index("data-qc-none") < grid
    assert html.index("data-qc-toggle") < grid  # والمنتقي قبلهما


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
    strip = html.split('data-key="strip.reds"')[1].split("</p>")[0].split("</div>")[0]
    assert "لا لوحةَ في حالة خطر" in html
    assert "قرار" not in strip
    assert "الإيداعاتُ غيرُ المنشورة: غيرُ معلومة" in html  # لم تُجمَع لوحتُها: يُسمّى مجهولاً لا صفراً


def test_a_group_whose_panels_are_all_hidden_is_hidden_entirely(client_as, developer_user):
    keys = ",".join(next(g for g in layout.GROUPS if g[0] == "plan")[2])
    html = _page(client_as, developer_user, qcc_hidden=keys)
    assert re.search(r'<section class="qc-group" data-group="plan"[^>]*hidden', html)
    assert not re.search(r'<section class="qc-group" data-group="prod"[^>]*hidden', html)


def test_the_script_labels_match_the_server_labels_and_it_has_no_dial():
    source = (ROOT / "static" / "js" / "command_center.js").read_text(encoding="utf-8")
    match = re.search(r"var STATE_LABEL = \{([^}]*)\}", source)
    pairs = dict(re.findall(r'(\w+): "([^"]+)"', match.group(1)))
    assert pairs == layout.STATE_LABELS
    assert "paintDial" not in source and "data-dial" not in source
    assert "paintBar" in source and "[data-bar]" in source

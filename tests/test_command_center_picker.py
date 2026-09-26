"""[COMMAND-CENTER] قائمةُ اختيار المؤشّرات — إظهارُ اللوحات وإخفاؤها بمربّعات اختيارٍ يحفظها المتصفّح (كوكي `qcc_hidden`).

التفضيلُ للعرض وحدَه: الخادمُ يرسم المخفيَّ مخفيّاً من أوّل طلبٍ (بلا وميض)، ولا يقبل من الكوكي إلّا مفاتيحَ اللوحات المعروفة،
واللقطةُ والتنبيهُ عند الأحمر لا يتأثّران به. وأيُّ لوحةٍ تُضاف إلى `contract.PANELS` تظهر في القائمة بلا تعديل.
"""

import pathlib
import re

import pytest
from django.core.cache import cache

from command_center import contract, views

pytestmark = pytest.mark.django_db

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def _page(client, cookie=None):
    if cookie is not None:
        client.cookies[views.HIDDEN_COOKIE] = cookie
    return client.get("/command-center/").content.decode()


def _card_hidden(html, key):
    match = re.search(rf'<div data-card="{key}"([^>]*)>', html)
    assert match, key
    return "hidden" in match.group(1)


def test_every_panel_is_shown_by_default_and_the_counter_says_so(client_as, developer_user):
    html = _page(client_as(developer_user))
    assert not any(_card_hidden(html, p.key) for p in contract.PANELS)
    assert f"{len(contract.PANELS)} من {len(contract.PANELS)}" in html
    assert re.search(r"<div data-qc-none hidden>", html)


def test_the_cookie_hides_those_panels_from_the_first_paint(client_as, developer_user):
    html = _page(client_as(developer_user), "ci,pulls")
    assert _card_hidden(html, "ci") and _card_hidden(html, "pulls")
    assert not _card_hidden(html, "production")
    assert f"{len(contract.PANELS) - 2} من {len(contract.PANELS)}" in html
    assert re.search(r'data-qc-toggle="ci"(?![^>]*checked)', html)
    assert re.search(r'data-qc-toggle="production"[^>]*checked', html)


def test_unknown_or_hostile_cookie_values_are_ignored_and_never_echoed(client_as, developer_user):
    html = _page(client_as(developer_user), "<script>alert(1)</script>,production,../x,,")
    assert _card_hidden(html, "production")
    assert not _card_hidden(html, "ci")
    assert "<script>alert(1)</script>" not in html


def test_hiding_everything_shows_the_empty_notice(client_as, developer_user):
    html = _page(client_as(developer_user), ",".join(p.key for p in contract.PANELS))
    assert all(_card_hidden(html, p.key) for p in contract.PANELS)
    assert not re.search(r"<div data-qc-none hidden>", html)
    assert "كلُّ المؤشّرات مخفيّة" in html


def test_the_picker_lists_every_panel_once_as_a_native_checkbox(client_as, developer_user):
    html = _page(client_as(developer_user))
    assert 'data-modal-open="qc-panels"' in html and 'id="modal-qc-panels"' in html
    for panel in contract.PANELS:
        assert html.count(f'data-qc-toggle="{panel.key}"') == 1
    assert html.count('type="checkbox"') >= len(contract.PANELS)
    assert 'data-qc-all="show"' in html and 'data-qc-all="hide"' in html


def test_the_snapshot_and_the_alerts_do_not_depend_on_the_display_preference(
    client_as, developer_user
):
    client = client_as(developer_user)
    client.cookies[views.HIDDEN_COOKIE] = ",".join(p.key for p in contract.PANELS)
    body = client.get("/command-center/snapshot/").json()
    assert [p["key"] for p in body["panels"]] == [p.key for p in contract.PANELS]
    assert "hidden" not in body["panels"][0]
    source = (ROOT / "command_center" / "alerts.py").read_text(encoding="utf-8")
    assert "HIDDEN_COOKIE" not in source and "request" not in source.split('"""', 2)[2]


def test_the_script_and_the_view_agree_on_the_cookie_and_it_stays_scoped_to_the_page():
    script = (ROOT / "static" / "js" / "command_center.js").read_text(encoding="utf-8")
    assert f'var HIDDEN_COOKIE = "{views.HIDDEN_COOKIE}"' in script
    assert "Path=/command-center/" in script and "SameSite=Lax" in script
    assert "innerHTML" not in script

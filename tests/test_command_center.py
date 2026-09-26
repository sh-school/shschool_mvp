"""[COMMAND-CENTER] مركز قيادة الجودة — صفحةٌ في المنصّة لمطوّرها وحدَه، وقراءةُ cache فقط، وعقدُ اللقطة v1.

QCC-01b: طلبها المالكُ في المنصّة (بجانب خارطة التجويد، في «الإدارة ← أدوات المطوّر») لا في `/admin/`؛ فنُقلت من `/admin/command-center/`
(QCC-01) إلى `/command-center/` وحُذفت نسختُها. وهذا الملفُّ يحرس كلَّ مسارٍ بنفسه (مجهولٌ يُحوَّل إلى الدخول وغيرُ المطوّر 403)
ويحمّل urlconf كاملاً، ويثبت أنّ النسخةَ القديمة لم تبقَ.
"""

import importlib
import pathlib
import re
import time

import pytest
from django.conf import settings
from django.core.cache import cache
from django.core.checks import run_checks
from django.urls import get_resolver, resolve, reverse

from command_center import contract
from command_center import urls as cc_urls

pytestmark = pytest.mark.django_db

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def _routes():
    return [reverse(f"command_center:{p.name}") for p in cc_urls.urlpatterns]


# ── المسارُ وurlconf ──────────────────────────────────────────────────────────


def test_the_full_urlconf_loads_and_the_platform_paths_resolve():
    importlib.import_module(settings.ROOT_URLCONF)
    assert get_resolver().url_patterns
    assert not run_checks(tags=["urls"])
    assert resolve("/command-center/").view_name == "command_center:index"
    assert resolve("/command-center/snapshot/").view_name == "command_center:snapshot"
    # وما حوله لم يتأثّر: خارطةُ التجويد جارتُه والإدارةُ ودخولُها كما كانا
    assert resolve("/roadmap/").view_name == "improvement_roadmap"
    assert resolve("/admin/").view_name == "admin:index"
    assert resolve("/admin/login/").url_name == "admin_login_redirect"


def test_the_route_list_is_not_empty():
    assert len(_routes()) >= 2


def test_the_old_admin_copy_is_gone(client_as, developer_user):
    """QCC-01b: نسخةُ /admin/ حُذفت — لا مسارَ مزدوجٌ ولا إعادةُ توجيه."""
    developer_user.is_staff = True
    developer_user.save(update_fields=["is_staff"])
    client = client_as(developer_user)

    for path in ("/admin/command-center/", "/admin/command-center/snapshot/"):
        assert client.get(path).status_code == 404, path


def test_the_admin_menu_no_longer_carries_the_center():
    source = (ROOT / "core" / "admin_menu.py").read_text(encoding="utf-8")
    assert "command-center" not in source and "PAGES" not in source


# ── 403 لكلّ مسار ─────────────────────────────────────────────────────────────


def test_an_anonymous_visitor_is_sent_to_login_on_every_route(client):
    for url in _routes():
        response = client.get(url)
        assert response.status_code == 302, url
        assert "login" in response["Location"], url


def test_a_non_developer_gets_403_on_every_route(client_as, teacher_user, principal_user):
    """المعلّمُ والمدير (قيادةٌ لا مطوّر) — 403 لا صفحةٌ ولا تحويل."""
    for user in (teacher_user, principal_user):
        for url in _routes():
            assert client_as(user).get(url).status_code == 403, (user.pk, url)


def test_the_developer_gets_every_route(client_as, developer_user):
    for url in _routes():
        assert client_as(developer_user).get(url).status_code == 200, url


def test_the_routes_accept_get_only(client_as, developer_user):
    for url in _routes():
        assert client_as(developer_user).post(url).status_code == 405, url


# ── الصفحةُ ولقطتُها ──────────────────────────────────────────────────────────


def test_the_page_draws_every_panel_as_unknown_when_nothing_was_collected(
    client_as, developer_user
):
    html = client_as(developer_user).get("/command-center/").content.decode()
    assert html.count('data-panel="') == len(contract.PANELS)
    assert html.count("qc-panel is-unknown") == len(contract.PANELS)
    assert "qc-panel is-ok" not in html
    assert 'data-qc-url="/command-center/snapshot/"' in html


def test_the_snapshot_is_json_v1_in_panel_order_and_never_cached(client_as, developer_user):
    response = client_as(developer_user).get("/command-center/snapshot/")
    assert response["Content-Type"].startswith("application/json")
    assert "max-age=0" in response["Cache-Control"] or "no-store" in response["Cache-Control"]
    body = response.json()
    assert body["schema"] == contract.SCHEMA_VERSION == 1
    assert [p["key"] for p in body["panels"]] == [p.key for p in contract.PANELS]
    assert {p["status"] for p in body["panels"]} == {contract.UNKNOWN}
    assert all(p["age_seconds"] is None for p in body["panels"])


def test_building_the_snapshot_touches_no_database(django_assert_num_queries):
    """الحسابُ ليس عند الطلب: لوحاتُ اللقطة من الـcache وحدَه (مجمِّعاتُها في مهامّ Celery لاحقاً)."""
    contract.store("production", {"status": "ok"})
    with django_assert_num_queries(0):
        contract.snapshot()


# ── عقدُ اللقطة ───────────────────────────────────────────────────────────────


def test_a_collected_panel_is_read_back_with_its_status_and_age():
    contract.store("production", {"status": "ok", "headline": "الويب والعامل على إيداعٍ واحد"})
    panel = next(p for p in contract.read_panels() if p["key"] == "production")
    assert panel["status"] == contract.OK
    assert panel["headline"] == "الويب والعامل على إيداعٍ واحد"
    assert panel["age_seconds"] in (0, 1)


def test_unknown_is_never_green():
    panels = contract.read_panels()
    assert all(p["status"] == contract.UNKNOWN for p in panels)
    # ولا لوحةٌ بمغلَّفٍ بلا حالةٍ مفهومةٍ تُقرأ سليمةً
    contract.store("ci", {"headline": "بلا status"})
    assert next(p for p in contract.read_panels() if p["key"] == "ci")["status"] == contract.UNKNOWN


def test_a_stale_ok_is_shown_as_a_warning_not_green():
    contract.store("guards", {"status": "ok"})
    refresh = next(p for p in contract.PANELS if p.key == "guards").refresh
    later = time.time() + refresh * contract.STALE_AFTER_REFRESHES + 5
    panel = next(p for p in contract.read_panels(later) if p["key"] == "guards")
    assert panel["status"] == contract.WARN
    # والأحمرُ القديم يبقى أحمر: القِدَمُ لا يخفّف الخطر
    contract.store("roadmap", {"status": "bad"})
    assert (
        next(p for p in contract.read_panels(later) if p["key"] == "roadmap")["status"]
        == contract.BAD
    )


def test_a_failed_refresh_keeps_the_last_good_value_but_stops_being_green():
    contract.store("pulls", {"status": "ok", "headline": "آخرُ قيمةٍ سليمة"})
    contract.store("pulls", {}, ok=False, err="http_403")
    panel = next(p for p in contract.read_panels() if p["key"] == "pulls")
    assert panel["headline"] == "آخرُ قيمةٍ سليمة"
    assert panel["status"] == contract.WARN
    assert panel["ok"] is False and panel["err"] == "http_403"


def test_the_store_refuses_what_the_contract_forbids():
    with pytest.raises(ValueError):
        contract.store("no_such_panel", {"status": "ok"})
    with pytest.raises(ValueError):
        contract.store("ci", {"status": "ok", "nested": {"a": 1}})
    with pytest.raises(ValueError):
        contract.store("ci", {"status": "ok", "headline": "س" * (contract.MAX_STRING + 1)})


def test_an_unreadable_cache_shows_unknown_instead_of_failing_the_page(monkeypatch):
    def boom(*_args, **_kwargs):
        raise ConnectionError("redis down")

    monkeypatch.setattr(cache, "get_many", boom)
    panels = contract.read_panels()
    assert {p["status"] for p in panels} == {contract.UNKNOWN}


# ── القائمةُ الرئيسيّة (الإدارة ← أدوات المطوّر) ─────────────────────────────────────


def _developer_principal(principal_user):
    """قائمةُ «الإدارة» تُرسم لأدوار القيادة، و«أدوات المطوّر» فيها لمن هو في مجموعة developers (كما في test_roadmap)."""
    from django.contrib.auth.models import Group

    principal_user.groups.add(Group.objects.get_or_create(name="developers")[0])
    return principal_user


def test_the_developer_sees_the_link_in_the_main_menu_above_the_roadmap(client_as, principal_user):
    url = reverse("command_center:index")
    html = client_as(_developer_principal(principal_user)).get("/dashboard/").content.decode()

    assert f'href="{url}"' in html
    assert (
        html.index(reverse("ui_layouts"))
        < html.index(f'href="{url}"')
        < html.index(reverse("improvement_roadmap"))
    ), "بين «أنماط التخطيط» و«خارطة التجويد»: فوقَ الخارطة مباشرةً"
    assert 'aria-label="مركز قيادة الجودة' in html


def test_a_non_developer_never_sees_the_link(client_as, teacher_user, principal_user):
    url = reverse("command_center:index")

    assert url not in client_as(teacher_user).get("/dashboard/").content.decode()
    assert url not in client_as(principal_user).get("/dashboard/").content.decode()


# ── الحدودُ ───────────────────────────────────────────────────────────────────


def test_core_never_imports_the_center():
    """اتّجاهُ الاعتماد: command_center يستورد core لا العكس (الرابطُ في القائمة نصٌّ لا استيراد)."""
    pattern = re.compile(r"^\s*(?:from|import)\s+command_center\b", re.MULTILINE)
    offenders = [
        str(path.relative_to(ROOT))
        for path in (ROOT / "core").rglob("*.py")
        if pattern.search(path.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert not offenders, offenders


def test_the_script_is_wrapped_and_builds_no_html():
    source = (ROOT / "static" / "js" / "command_center.js").read_text(encoding="utf-8")
    assert "(function () {" in source and source.rstrip().endswith("})();")
    for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert forbidden not in source, forbidden


def test_the_center_styles_live_in_the_platform_css_and_not_in_the_admin_theme():
    """QCC-01b: الصفحةُ في المنصّة فأنماطُها في `static/css/custom/` (ملفُّ الوحدات)، ولا شيءَ منها في `admin_theme.css`."""
    assert ".qc-" not in (ROOT / "static" / "css" / "admin_theme.css").read_text(encoding="utf-8")
    modules = (ROOT / "static" / "css" / "custom" / "33-modules-4.css").read_text(encoding="utf-8")
    assert ".qc-panel" in modules and ".qc-grid" in modules


def test_the_page_is_a_platform_page_declaring_its_layout_and_using_the_components():
    source = (ROOT / "templates" / "command_center" / "index.html").read_text(encoding="utf-8")
    assert '{% extends "base/base.html" %}' in source
    assert '{% page_layout "dashboard" %}' in source
    for component in ("components/breadcrumbs.html", "page_header", "callout"):
        assert component in source, component
    assert "admin/base" not in source, "لا وراثةَ من قوالب الإدارة"

"""[COMMAND-CENTER] مركز قيادة الجودة (PR-A: القشرة) — للمطوّر وحدَه، وقراءةُ cache فقط، وعقدُ اللقطة v1.

المسارُ جذريٌّ تحت `/admin/` قبل `admin.site.urls`: لا حارسَ آليّاً هناك (يُستثنى من اختبار المسارات المحروسة)،
وخطأٌ في urlconf يُسقط الموقعَ كلَّه. فهذا الملفُّ يحرس كلَّ مسارٍ بنفسه، ويحمّل urlconf كاملاً.
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
from core import admin_menu

pytestmark = pytest.mark.django_db

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _staff(user):
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    return user


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def _routes():
    return [reverse(f"command_center:{p.name}") for p in cc_urls.urlpatterns]


# ── المسارُ وurlconf ──────────────────────────────────────────────────────────


def test_the_full_urlconf_loads_and_the_root_paths_resolve():
    importlib.import_module(settings.ROOT_URLCONF)
    assert get_resolver().url_patterns
    assert not run_checks(tags=["urls"])
    assert resolve("/admin/command-center/").view_name == "command_center:index"
    assert resolve("/admin/command-center/snapshot/").view_name == "command_center:snapshot"
    # وما حوله لم يتأثّر: الإدارةُ ودخولُها كما كانا
    assert resolve("/admin/").view_name == "admin:index"
    assert resolve("/admin/login/").url_name == "admin_login_redirect"


def test_the_center_route_comes_before_the_admin_catch_all():
    names = [
        getattr(p, "app_name", None) or getattr(p, "name", "") for p in get_resolver().url_patterns
    ]
    assert names.index("command_center") < names.index("admin")


def test_the_route_list_is_not_empty():
    assert len(_routes()) >= 2


# ── 403 لكلّ مسار ─────────────────────────────────────────────────────────────


def test_an_anonymous_visitor_is_sent_to_login_on_every_route(client):
    for url in _routes():
        response = client.get(url)
        assert response.status_code == 302, url
        assert "/admin/login/" in response["Location"], url


def test_a_logged_in_non_staff_user_never_gets_the_page(client_as, teacher_user):
    for url in _routes():
        response = client_as(teacher_user).get(url)
        assert response.status_code == 302, url


def test_a_staff_member_who_is_not_a_developer_gets_403_on_every_route(client_as, teacher_user):
    for url in _routes():
        response = client_as(_staff(teacher_user)).get(url)
        assert response.status_code == 403, url


def test_the_developer_gets_every_route(client_as, developer_user):
    for url in _routes():
        assert client_as(_staff(developer_user)).get(url).status_code == 200, url


# ── الصفحةُ ولقطتُها ──────────────────────────────────────────────────────────


def test_the_page_draws_every_panel_as_unknown_when_nothing_was_collected(
    client_as, developer_user
):
    html = client_as(_staff(developer_user)).get("/admin/command-center/").content.decode()
    assert html.count('data-panel="') == len(contract.PANELS)
    assert html.count("qc-panel--unknown") == len(contract.PANELS)
    assert "qc-panel--ok" not in html
    assert 'data-qc-url="/admin/command-center/snapshot/"' in html


def test_the_snapshot_is_json_v1_in_panel_order_and_never_cached(client_as, developer_user):
    response = client_as(_staff(developer_user)).get("/admin/command-center/snapshot/")
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


# ── القائمةُ ──────────────────────────────────────────────────────────────────


def test_the_developer_sees_the_center_in_the_admin_nav(client_as, developer_user):
    html = client_as(_staff(developer_user)).get("/admin/").content.decode()
    assert 'href="/admin/command-center/"' in html


def test_a_non_developer_staff_member_does_not_see_the_center_in_the_nav(client_as, teacher_user):
    html = client_as(_staff(teacher_user)).get("/admin/").content.decode()
    assert "/admin/command-center/" not in html


def test_the_menu_pages_resolve_and_live_under_the_admin():
    for page in admin_menu.PAGES:
        assert page.url.startswith("/admin/"), page
        assert resolve(page.url), page


def test_the_menu_adds_a_developer_page_only_for_the_developer():
    def names(developer):
        menu = admin_menu.build_menu([], "/admin/", developer=developer)
        return [i["name"] for g in menu for s in g["sections"] for i in s["items"]]

    assert "مركز قيادة الجودة" in names(True)
    assert "مركز قيادة الجودة" not in names(False)


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


def test_the_center_styles_live_in_the_admin_theme_and_not_in_the_platform_css():
    assert ".qc-panel" in (ROOT / "static" / "css" / "admin_theme.css").read_text(encoding="utf-8")
    for path in (ROOT / "static" / "css" / "custom").glob("*.css"):
        assert ".qc-" not in path.read_text(encoding="utf-8"), path.name

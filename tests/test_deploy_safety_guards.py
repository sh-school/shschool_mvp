"""حرّاسُ حادثة 2026-09-17: غاب بيانُ الثابت عن الحاويات فسقطت كلُّ صفحة،
و/health/ أخضر، وصفحةُ الخطأ نفسُها ساقطة، والنشرُ وقعَ في منتصف الدوام."""

from __future__ import annotations

import importlib.util
import pathlib
from datetime import UTC, datetime

import pytest
import yaml
from django.template.loader import render_to_string

import core.views_health as views_health

ROOT = pathlib.Path(__file__).resolve().parent.parent


class _MissingManifest:
    def url(self, name):
        raise ValueError(f"Missing staticfiles manifest entry for '{name}'")


# ── /health/ يرفض نسخةً بلا ثابت ─────────────────────────────


@pytest.mark.django_db
def test_health_reports_static_ready(client):
    data = client.get("/health/").json()
    assert data["checks"]["static"] == "ok"


@pytest.mark.django_db
def test_health_fails_when_static_manifest_is_missing(client, monkeypatch):
    monkeypatch.setattr(views_health, "staticfiles_storage", _MissingManifest())
    resp = client.get("/health/")
    assert resp.status_code == 503
    assert resp.json()["checks"]["static"] == "error: ValueError"


def test_static_probe_is_a_real_file():
    assert (ROOT / "static" / views_health.STATIC_PROBE).is_file()


# ── صفحةُ الخطأ لا تسأل بيانَ الثابت ─────────────────────────


def test_500_page_renders_without_static_manifest(monkeypatch):
    import django.contrib.staticfiles.storage as storage_module

    monkeypatch.setattr(storage_module, "staticfiles_storage", _MissingManifest())
    html = render_to_string("500.html")
    assert "500" in html
    assert "/static/fonts/Tajawal-Regular.woff2" in html


def test_error_page_has_no_static_tag():
    text = (ROOT / "templates" / "errors" / "_error_page.html").read_text(encoding="utf-8")
    assert "{% static " not in text


# ── فحصُ ما بعد النشر يطلب صفحةً تُرسم ───────────────────────


def test_post_deploy_checks_request_the_login_page():
    doc = yaml.safe_load(
        (ROOT / ".github/workflows/deploy-railway.yml").read_text(encoding="utf-8")
    )
    for job in ("post-deploy-canary", "smoke-test"):
        runs = "\n".join(s.get("run", "") for s in doc["jobs"][job]["steps"])
        assert "/auth/login/" in runs, job


# ── نافذة النشر ───────────────────────────────────────────────


def _load_window():
    spec = importlib.util.spec_from_file_location(
        "deploy_window", ROOT / "scripts" / "deploy_window.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def window():
    return _load_window()


def _utc(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=UTC)


@pytest.mark.parametrize(
    ("now", "blocked"),
    [
        (_utc(2026, 9, 17, 6, 15), True),  # الخميس 09:15 قطر — لحظة الحادثة
        (_utc(2026, 9, 17, 4, 0), True),  # الخميس 07:00 قطر — أوّل النافذة
        (_utc(2026, 9, 17, 3, 59), False),  # الخميس 06:59
        (_utc(2026, 9, 17, 11, 0), False),  # الخميس 14:00 — آخرها مفتوح
        (_utc(2026, 9, 13, 8, 0), True),  # الأحد 11:00
        (_utc(2026, 9, 18, 8, 0), False),  # الجمعة
        (_utc(2026, 9, 19, 8, 0), False),  # السبت
    ],
)
def test_school_hours_in_qatar_time(window, now, blocked):
    assert window.in_school_hours(now) is blocked


def test_merge_queue_is_blocked_during_school_hours(window):
    allowed, message = window.decide("merge_group", _utc(2026, 9, 17, 6, 15), [])
    assert not allowed
    assert window.LABEL in message


def test_labelled_hotfix_passes_during_school_hours(window):
    allowed, _ = window.decide("merge_group", _utc(2026, 9, 17, 6, 15), [window.LABEL])
    assert allowed


def test_pull_request_is_never_blocked(window):
    assert window.decide("pull_request", _utc(2026, 9, 17, 6, 15), None)[0]


def test_merge_queue_outside_hours_passes(window):
    assert window.decide("merge_group", _utc(2026, 9, 17, 12, 0), None)[0]


def test_queue_ref_yields_pr_number(window):
    ref = "refs/heads/gh-readonly-queue/main/pr-313-07309c96abc"
    assert window.queued_pr_number(ref) == 313
    assert window.queued_pr_number("") is None


def test_deploy_window_gates_the_required_summary():
    doc = yaml.safe_load((ROOT / ".github/workflows/quality-gate.yml").read_text(encoding="utf-8"))
    summary = doc["jobs"]["gate-summary"]
    assert summary["name"] == "ملخص بوابة الجودة"
    assert "deploy-window" in summary["needs"]
    fail_step = next(s for s in summary["steps"] if "if" in s)
    assert "needs.deploy-window.result" in fail_step["if"]
    assert "merge_group" in doc[True]  # يُشغَّل في طابور الدمج

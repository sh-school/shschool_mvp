"""[COMMAND-CENTER] استقبالُ القياس الميدانيّ (Q-04) ولوحةُ «تجربة المستخدم الفعليّة».

عقدُ الحمولة في `docs/rum_client_contract_2026-09.md`: تحقّقٌ صارمٌ يرمي صامتاً، وردٌّ 204 دائماً، وتجميعٌ في دلاءَ لا صفوفٍ خام، وبلا IP ولا وكيلٍ ولا مرجعٍ
ولا هويّة. واللوحةُ تحكم على **الهاتف** بعتبات Core Web Vitals، ولا تُحمَّر دون عيّنةٍ كافية، والمطفأُ «انتبه» بعنوانٍ صريحٍ لا سليمٌ زائف.
"""

import json
import pathlib

import pytest
from django.core.cache import cache
from django.test import Client

from command_center import collectors, contract, rum
from command_center.collectors import ux

pytestmark = pytest.mark.django_db

ROOT = pathlib.Path(__file__).resolve().parent.parent
SAMPLE = {
    "v": 1,
    "lcp": 2100,
    "inp": 80,
    "cls": 0.18,
    "dev": "phone",
    "lay": "list",
    "nav": "navigate",
    "net": "3g",
}
NOW = 1_800_000_000.0


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def _raw(**changes):
    body = {**SAMPLE, **changes}
    return json.dumps({k: v for k, v in body.items() if v != "__drop__"}).encode()


def _feed(device, lcp=None, inp=None, cls=None, times=1, now=NOW):
    for _ in range(times):
        rum.record({"dev": device, "lcp": lcp, "inp": inp, "cls": cls}, now)


def _panel():
    return next(p for p in contract.read_panels() if p["key"] == "ux")


# ── التحقّق الصارم ────────────────────────────────────────────────────────────


def test_the_documented_example_is_accepted_and_only_device_and_metrics_survive():
    assert rum.parse(_raw()) == {"dev": "phone", "lcp": 2100.0, "inp": 80.0, "cls": 0.18}


def test_null_metrics_are_fine_but_not_all_null():
    assert rum.parse(_raw(inp=None))["inp"] is None
    assert rum.parse(_raw(lcp=None, inp=None, cls=None)) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"v": 2},
        {"v": "1"},
        {"dev": "watch"},
        {"dev": None},
        {"lcp": -1},
        {"lcp": 60001},
        {"inp": 10001},
        {"cls": 10.1},
        {"lcp": "2100"},
        {"lcp": True},
        {"lay": "elsewhere"},
        {"nav": "teleport"},
        {"net": "5g"},
    ],
)
def test_out_of_contract_payloads_are_dropped_whole(changes):
    assert rum.parse(_raw(**changes)) is None


def test_garbage_oversize_and_non_objects_are_dropped():
    assert rum.parse(b"") is None
    assert rum.parse(b"not json") is None
    assert rum.parse(b"[1,2,3]") is None
    assert rum.parse(b"\xff\xfe") is None
    assert rum.parse(_raw(lay="x" * 500)) is None  # يتجاوز 400 بايت
    assert len(_raw()) < rum.MAX_BODY_BYTES


def test_unknown_extra_fields_are_ignored_not_rejected():
    assert rum.parse(_raw(extra="ignored")) == {
        "dev": "phone",
        "lcp": 2100.0,
        "inp": 80.0,
        "cls": 0.18,
    }


# ── التجميع والدلاء ───────────────────────────────────────────────────────────


def test_bucket_edges_land_on_the_core_web_vitals_thresholds():
    lcp, inp, cls = rum.METRICS["lcp"], rum.METRICS["inp"], rum.METRICS["cls"]
    assert lcp.upper(lcp.bucket(2499)) == 2500 and lcp.upper(lcp.bucket(4000)) == 4250
    assert inp.upper(inp.bucket(199)) == 200 and inp.upper(inp.bucket(499)) == 500
    assert cls.upper(cls.bucket(0.09)) == 0.1 and cls.upper(cls.bucket(0.24)) == 0.25


def test_p75_is_the_upper_edge_of_the_bucket_holding_the_75th_percentile():
    _feed("phone", lcp=1000, times=80)
    _feed("phone", lcp=3000, times=20)
    assert rum.summary("phone", now=NOW)["lcp"] == {"n": 100, "p75": 1250.0}  # 80% دون الثانية
    _feed("phone", lcp=3000, times=20)  # صار 66% فقط دونها: p75 ينتقل إلى دلو 3000
    assert rum.summary("phone", now=NOW)["lcp"] == {"n": 120, "p75": 3250.0}


def test_values_beyond_the_range_go_to_the_overflow_bucket():
    _feed("phone", lcp=30000, times=5)
    assert rum.summary("phone", now=NOW)["lcp"]["p75"] == 10250.0


def test_only_the_last_seven_days_and_only_that_device_are_counted():
    _feed("phone", lcp=1000, times=3, now=NOW)
    _feed("phone", lcp=1000, times=5, now=NOW - 8 * 86400)
    _feed("desktop", lcp=1000, times=7, now=NOW)
    assert rum.summary("phone", now=NOW)["lcp"]["n"] == 3
    assert rum.summary("desktop", now=NOW)["lcp"]["n"] == 7


def test_the_global_rate_limit_drops_the_flood_silently(monkeypatch):
    monkeypatch.setattr(rum, "RATE_PER_MINUTE", 2)
    results = [
        rum.record({"dev": "phone", "lcp": 1000, "inp": None, "cls": None}, NOW) for _ in range(4)
    ]
    assert results == [True, True, False, False]
    assert rum.summary("phone", now=NOW)["lcp"]["n"] == 2


def test_the_rating_needs_a_sample_and_never_says_poor_on_a_thin_one():
    assert rum.rating("lcp", 2000, 10) == "none"
    assert rum.rating("lcp", None, 500) == "none"
    assert rum.rating("lcp", 2500, 40) == "good"
    assert rum.rating("lcp", 3000, 40) == "needs"
    assert rum.rating("lcp", 4500, 40) == "needs"  # ضعيفٌ لكنّ العيّنةَ دون 100
    assert rum.rating("lcp", 4500, 100) == "poor"
    assert rum.rating("cls", 0.1, 50) == "good" and rum.rating("inp", 200, 50) == "good"


# ── نقطةُ الاستقبال ───────────────────────────────────────────────────────────


def _post(client, body, **extra):
    return client.post("/rum/collect/", data=body, content_type="application/json", **extra)


def test_the_endpoint_is_off_while_rum_endpoint_is_empty(client_as, teacher_user, settings):
    settings.RUM_ENDPOINT = ""
    response = _post(client_as(teacher_user), _raw())
    assert response.status_code == 204 and response.content == b""
    assert rum.summary("phone")["lcp"]["n"] == 0


def test_a_valid_beacon_is_counted_and_answered_204_without_a_body(
    client_as, teacher_user, settings
):
    settings.RUM_ENDPOINT = "/rum/collect/"
    response = _post(client_as(teacher_user), _raw())
    assert response.status_code == 204 and response.content == b""
    assert rum.summary("phone")["lcp"]["n"] == 1


def test_a_rejected_beacon_gets_the_same_204_and_counts_nothing(client_as, teacher_user, settings):
    settings.RUM_ENDPOINT = "/rum/collect/"
    client = client_as(teacher_user)
    for body in (b"junk", _raw(dev="watch"), _raw(lcp=99999)):
        assert _post(client, body).status_code == 204
    assert _post(client, _raw(), CONTENT_LENGTH="9999").status_code == 204
    assert rum.summary("phone")["lcp"]["n"] == 0


def test_only_post_and_the_csrf_check_is_waived_because_a_beacon_has_no_header(
    client_as, teacher_user, settings
):
    settings.RUM_ENDPOINT = "/rum/collect/"
    client = client_as(teacher_user)
    assert client.get("/rum/collect/").status_code == 405
    strict = Client(enforce_csrf_checks=True)
    strict.cookies = client.cookies
    assert _post(strict, _raw()).status_code == 204
    assert rum.summary("phone")["lcp"]["n"] == 1


def test_an_anonymous_visitor_goes_through_the_normal_login_gate(client, settings):
    settings.RUM_ENDPOINT = "/rum/collect/"
    response = _post(client, _raw())
    assert response.status_code == 302 and "login" in response["Location"]
    assert rum.summary("phone")["lcp"]["n"] == 0


def test_the_receiver_never_reads_identity_or_network_details():
    for name in ("rum_views.py", "rum.py"):
        code = (ROOT / "command_center" / name).read_text(encoding="utf-8")
        code = code.split('"""', 2)[2]  # بلا الوثيقة: الكلماتُ هنا شروحٌ لا استعمال
        for forbidden in (
            "request.user",
            "request.session",
            "REMOTE_ADDR",
            "X_FORWARDED",
            "USER_AGENT",
            "HTTP_REFERER",
            "COOKIES",
        ):
            assert forbidden not in code, (name, forbidden)


# ── اللوحة ────────────────────────────────────────────────────────────────────


def test_the_panel_is_registered_and_collected_locally():
    assert any(p.key == "ux" for p in contract.PANELS) and "ux" in collectors.LOCAL


def test_disabled_measurement_is_amber_with_an_honest_headline(settings):
    settings.RUM_ENDPOINT = ""
    ux.collect(NOW)
    panel = _panel()
    assert panel["status"] == contract.WARN and panel["gauge"] is None
    assert "مطفأ" in panel["headline"] and "DPO" in panel["detail"]


def test_a_thin_phone_sample_is_amber_with_no_verdict(settings):
    settings.RUM_ENDPOINT = "/rum/collect/"
    _feed("phone", lcp=1000, inp=50, cls=0.01, times=5)
    ux.collect(NOW)
    panel = _panel()
    assert panel["status"] == contract.WARN and panel["gauge"] is None
    assert "عيّنةٌ غيرُ كافية" in panel["headline"]


def test_a_good_phone_experience_is_green_and_full(settings):
    settings.RUM_ENDPOINT = "/rum/collect/"
    _feed("phone", lcp=1500, inp=100, cls=0.02, times=60)
    _feed("desktop", lcp=900, inp=40, cls=0.0, times=40)
    ux.collect(NOW)
    panel = _panel()
    assert panel["status"] == contract.OK and panel["gauge"] == 100
    assert {"label": "عيّنات 7 أيّام", "value": "100"} in panel["metrics"]
    assert "مكتب:" in panel["detail"]


def test_poor_phone_lcp_with_enough_samples_is_red_and_names_the_metric(settings):
    settings.RUM_ENDPOINT = "/rum/collect/"
    _feed("phone", lcp=6000, inp=100, cls=0.02, times=120)
    ux.collect(NOW)
    panel = _panel()
    assert panel["status"] == contract.BAD
    assert panel["headline"] == "ضعفٌ على الهاتف: LCP"
    assert panel["gauge"] == 65


def test_needs_improvement_is_amber_and_a_desktop_problem_alone_does_not_judge_the_phone(settings):
    settings.RUM_ENDPOINT = "/rum/collect/"
    _feed("phone", lcp=3000, inp=100, cls=0.02, times=60)
    _feed("desktop", lcp=9000, inp=900, cls=0.9, times=200)
    ux.collect(NOW)
    panel = _panel()
    assert panel["status"] == contract.WARN and panel["gauge"] == 88

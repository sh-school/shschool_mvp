"""[Q-04، الواجهة / K22] عميلُ القياس الميدانيّ: يرسل أرقامَ الأداء بلا هويّةٍ، ومطفأٌ حتى يُفعَّل.

`static/js/rum.js` يقيس LCP وINP وCLS ويرسلها **مجمَّعةً** عند مغادرة الصفحة بـ`sendBeacon`. وخصوصيّتُه (PDPPL) شرطُ
تفعيله: الحمولةُ أرقامٌ وفئةُ جهازٍ ونمطُ تخطيطٍ من قائمةٍ ثابتة — لا مسارَ ولا مرجعَ ولا وكيلَ مستخدمٍ ولا تخزينَ ولا
معرّف. وهذا الملفُّ ينفي ذلك (بندُ الخطّة «اختبارٌ ينفي بياناتٍ شخصيّةً في الحمولة») لكنّه لا يغني عن مراجعة الـDPO.

ومطفأٌ افتراضاً: بلا `RUM_ENDPOINT` لا يُصدر `base.html` السكربتَ ولا يطلبه المتصفّح.
"""

import re
from pathlib import Path

import pytest
from django.test import override_settings
from django.urls import reverse

ROOT = Path(__file__).resolve().parent.parent
RUM = (ROOT / "static/js/rum.js").read_text(encoding="utf-8")
CODE = re.sub(r"/\*.*?\*/", "", RUM, flags=re.S)  # ما عدا التعليقات: قد تذكر الممنوعَ لتنفيَه


def test_the_payload_carries_only_numbers_and_fixed_categories():
    body = re.search(r"JSON\.stringify\(\{(.*?)\}\);", CODE, re.S)
    assert body, "لم أجد بناءَ الحمولة"
    keys = set(re.findall(r"^\s*(\w+):", body.group(1), re.M))
    assert keys == {
        "v",
        "lcp",
        "inp",
        "cls",
        "dev",
        "lay",
        "nav",
        "net",
    }, f"حقلٌ جديدٌ في الحمولة يحتاج موافقةَ الـDPO: {sorted(keys)}"


@pytest.mark.parametrize(
    "token",
    [
        "location",
        "referrer",
        "userAgent",
        "localStorage",
        "sessionStorage",
        "cookie",
        "indexedDB",
        "pathname",
        "href",
        "textContent",
        "innerText",
        "innerHTML",
        "getAttribute",
        "dataset",
        "fetch(",
        "XMLHttpRequest",
    ],
)
def test_the_client_reads_nothing_that_can_identify_a_person(token):
    assert token not in CODE, f"rum.js يقرأ `{token}` — بابٌ للهويّة أو المسار أو المحتوى"


def test_the_only_free_text_is_a_fixed_list_of_layout_names():
    lists = {
        name: set(re.findall(r"'([\w-]+)'", block))
        for name, block in re.findall(r"var (LAYOUTS|NAV|NET) = \[(.*?)\];", CODE)
    }
    assert lists["LAYOUTS"] == {
        "dashboard",
        "hub",
        "list",
        "detail",
        "form",
        "sheet",
        "report",
        "custom",
    }
    assert lists["NAV"] == {"navigate", "reload", "back_forward", "prerender"}
    assert lists["NET"] == {"slow-2g", "2g", "3g", "4g"}
    assert "pick(NAV," in CODE and "pick(NET," in CODE, "قيمةٌ من المتصفّح تدخل الحمولةَ بلا تنقية"


def test_it_sends_once_by_beacon_when_the_page_is_left():
    assert "sendBeacon" in CODE
    assert "visibilitychange" in CODE and "pagehide" in CODE
    assert re.search(r"if \(sent \|\|", CODE) and "sent = true" in CODE, "قد يُرسل مرّتَين فيثقّل p75"
    assert "Math.random()" in CODE, "لا عيّنةَ: كلُّ صفحةٍ تُرسل"


def test_it_is_off_unless_the_page_hands_it_an_endpoint():
    assert "!cfg || !cfg.endpoint" in CODE, "لا مفتاحَ إيقافٍ داخل السكربت"


# ── الإعدادُ والقالب ───────────────────────────────────────────────────────


def test_the_setting_defaults_to_off(settings):
    from django.conf import settings as live

    assert live.RUM_ENDPOINT == "", "التفعيلُ قرارٌ بعد موافقة الـDPO لا أصلٌ في الإعدادات"
    assert 0 <= settings.RUM_SAMPLE_PERCENT <= 100


def _page(client_as, principal_user):
    return client_as(principal_user).get(reverse("dashboard"), follow=True).content.decode()


def test_the_page_omits_the_script_while_off(client_as, principal_user):
    html = _page(client_as, principal_user)
    assert "js/rum.js" not in html
    assert "rum: null" in html


@override_settings(RUM_ENDPOINT="/rum/collect/", RUM_SAMPLE_PERCENT=25)
def test_the_page_hands_the_client_its_endpoint_and_sample_when_on(client_as, principal_user):
    html = _page(client_as, principal_user)
    assert "js/rum.js" in html
    assert 'endpoint: "/rum/collect/", sample: 25' in html


@override_settings(RUM_ENDPOINT="/rum/collect/", RUM_SAMPLE_PERCENT=500)
def test_the_sample_is_clamped_to_a_percentage(client_as, principal_user):
    assert "sample: 100" in _page(client_as, principal_user)

"""[COMMAND-CENTER] لوحةُ «الامتثال (PDPPL)» — ثلاثةُ فحوصٍ قانونيّةٍ بأعدادٍ لا أسماء (قرارُ المالك 2026-09-27).

الخرقُ الفائتُ موعدُه أحمرُ وحدَه بين الفحوص، ومحوٌ معلَّقٌ شهراً أحمر، والاحتفاظُ المعطَّلُ أو الذي لم يُنفَّذ «انتبه» لا سليم.
وما يُخزَّن أعدادٌ وأعمارٌ فقط: لا عنوانَ خرقٍ ولا سببَ محو (المستودعُ والـcache بلا بياناتٍ شخصيّة).
"""

import json
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from command_center import collectors, contract
from command_center.collectors import compliance
from core.models.audit import BreachReport, ErasureRequest

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def _panel():
    return next(p for p in contract.read_panels() if p["key"] == "compliance")


def _breach(school, hours_ago, status="discovered", title="عنوانٌ حسّاس لا يُخزَّن"):
    return BreachReport.objects.create(
        school=school,
        title=title,
        description="وصفٌ",
        discovered_at=timezone.now() - timedelta(hours=hours_ago),
        status=status,
    )


def _erasure(school, days_ago, status="pending"):
    request = ErasureRequest.objects.create(school=school, reason="سببٌ خاصّ", status=status)
    ErasureRequest.objects.filter(pk=request.pk).update(
        created_at=timezone.now() - timedelta(days=days_ago)
    )
    return request


def test_the_panel_is_registered_and_collected_locally():
    assert "compliance" in collectors.LOCAL
    assert any(p.key == "compliance" for p in contract.PANELS)


def test_the_level_rules():
    assert compliance.breach_level(0, 0, None) == contract.OK
    assert compliance.breach_level(1, 0, 60) == contract.OK
    assert compliance.breach_level(1, 0, 5) == contract.WARN
    assert compliance.breach_level(2, 1, 60) == contract.BAD
    assert compliance.erasure_level(0, 0) == contract.OK
    assert compliance.erasure_level(2, 3) == contract.OK
    assert compliance.erasure_level(2, 8) == contract.WARN
    assert compliance.erasure_level(2, 31) == contract.BAD
    assert compliance.retention_level(0, 3) == contract.WARN  # معطَّل
    assert compliance.retention_level(730, None) == contract.WARN  # لم يُنفَّذ بعد
    assert compliance.retention_level(730, 3) == contract.OK
    assert compliance.retention_level(730, 10) == contract.WARN
    assert compliance.retention_level(730, 17) == contract.BAD


def test_a_breach_past_its_ncsa_deadline_makes_the_panel_red(school, settings):
    settings.PDPPL_DATA_RETENTION_DAYS = 730
    _breach(school, hours_ago=100)  # الموعدُ 72 ساعة
    compliance.collect()
    panel = _panel()
    assert panel["status"] == contract.BAD
    assert panel["headline"] == "1 من بلاغات الخرق فات موعدُ إشعارها"
    assert {"label": "بلاغاتُ خرقٍ مفتوحة", "value": "1"} in panel["metrics"]


def test_a_breach_close_to_its_deadline_is_amber_and_a_notified_one_is_not_open(school, settings):
    settings.PDPPL_DATA_RETENTION_DAYS = 730
    _breach(school, hours_ago=60)  # يبقى 12 ساعة
    _breach(school, hours_ago=200, status="notified")
    _breach(school, hours_ago=300, status="resolved")
    compliance.collect()
    panel = _panel()
    assert panel["status"] == contract.WARN
    assert {"label": "بلاغاتُ خرقٍ مفتوحة", "value": "1"} in panel["metrics"]


def test_an_erasure_request_pending_for_a_month_is_red_and_a_completed_one_is_ignored(
    school, settings
):
    settings.PDPPL_DATA_RETENTION_DAYS = 730
    _erasure(school, days_ago=40)
    _erasure(school, days_ago=400, status="completed")
    _erasure(school, days_ago=400, status="rejected")
    compliance.collect()
    panel = _panel()
    assert panel["status"] == contract.BAD
    assert any(
        m["label"] == "طلباتُ محوٍ مفتوحة" and m["value"].startswith("1 ") for m in panel["metrics"]
    )


def test_disabled_retention_is_amber_not_healthy(school, settings):
    settings.PDPPL_DATA_RETENTION_DAYS = 0
    compliance.collect()
    panel = _panel()
    assert panel["status"] == contract.WARN
    assert {"label": "مدّةُ الاحتفاظ", "value": "معطَّلة"} in panel["metrics"]


def test_a_real_retention_run_is_seen_as_recent_and_makes_the_panel_green(school, settings):
    """الثابتُ `RETENTION_LOG_PREFIX` يطابق ما يكتبه `governance.retention._record` فعلاً — وإلّا بقيت اللوحةُ «لم يُنفَّذ» أبداً."""
    from governance.retention import enforce_retention

    settings.PDPPL_DATA_RETENTION_DAYS = 730
    enforce_retention()
    assert compliance._last_retention_run_days(timezone.now()) == 0
    compliance.collect()
    panel = _panel()
    assert panel["status"] == contract.OK and panel["gauge"] == 100
    assert panel["headline"] == "لا خروقَ مفتوحةً ولا محوَ متأخّراً"
    assert {"label": "آخرُ إنفاذٍ للاحتفاظ", "value": "قبل 0 يوماً"} in panel["metrics"]


def test_no_recorded_run_is_amber_with_the_honest_wording(school, settings):
    settings.PDPPL_DATA_RETENTION_DAYS = 730
    compliance.collect()
    panel = _panel()
    assert panel["status"] == contract.WARN
    assert {"label": "آخرُ إنفاذٍ للاحتفاظ", "value": "لم يُنفَّذ بعدُ"} in panel["metrics"]


def test_nothing_personal_reaches_the_cache(school, settings):
    settings.PDPPL_DATA_RETENTION_DAYS = 730
    _breach(school, hours_ago=100, title="اسمُ طالبٍ في العنوان")
    _erasure(school, days_ago=40)
    compliance.collect()
    blob = json.dumps(_panel(), ensure_ascii=False)
    assert "اسمُ طالبٍ" not in blob and "سببٌ خاصّ" not in blob and "وصفٌ" not in blob


def test_a_broken_query_fails_the_panel_and_keeps_the_last_good_value(
    school, settings, monkeypatch
):
    settings.PDPPL_DATA_RETENTION_DAYS = 730
    compliance.collect()
    assert _panel()["status"] == contract.WARN  # لم يُنفَّذ إنفاذٌ بعد

    def boom(now):
        raise RuntimeError("db")

    monkeypatch.setattr(compliance, "_breaches", boom)
    outcome = collectors.run({"compliance": compliance.collect})
    assert outcome == {"compliance": False}
    assert _panel()["status"] == contract.WARN  # بقيت آخرُ قيمةٍ سليمة

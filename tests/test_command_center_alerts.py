"""[COMMAND-CENTER] التنبيهُ الحيّ عند الأحمر — إشعارٌ في جرس المطوّر (QCC-03، قرارُ المالك 2026-09-27: حيٌّ لا تجريبيّ).

الأحمرُ وحدَه يُنذر بعد تأكيدٍ دقيقتين، ولا يتكرّر إلّا كلَّ ست ساعات، وعودتُه إشعارٌ واحد، وللمطوّر سقفٌ 12 في اليوم،
و«غيرُ معلوم» لا يُنذر ولا يُصفّر، ومفتاحُ الإيقاف يسري فوراً، وعطلُ الإرسال لا يُسقط الجمع.
"""

import time

import pytest
from django.core.cache import cache

from command_center import alerts, collectors, contract
from notifications.models import InAppNotification

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _live(settings):
    settings.QCC_NOTIFY_ENABLED = True
    cache.clear()
    yield
    cache.clear()


def _set(status, panel="production", headline="فحصان في خطر"):
    contract.store(panel, {"status": status, "headline": headline})


def _bell(user):
    return list(InAppNotification.objects.filter(user=user).order_by("created_at"))


def test_a_red_panel_is_only_pending_until_it_stays_red_for_two_minutes(developer_user):
    now = time.time()
    _set("bad")
    assert alerts.evaluate(now) == []
    assert alerts.evaluate(now + 60) == []
    assert _bell(developer_user) == []
    assert alerts.evaluate(now + 121) == ["fired:production"]
    (note,) = _bell(developer_user)
    assert note.priority == "urgent" and note.related_url == "/command-center/"
    assert "صحّةُ الإنتاج والنشر" in note.title and "فحصان في خطر" in note.body


def test_a_firing_panel_is_not_repeated_every_cycle_only_after_six_hours(developer_user):
    now = time.time()
    _set("bad")
    alerts.evaluate(now)
    alerts.evaluate(now + 130)
    assert alerts.evaluate(now + 200) == []
    assert alerts.evaluate(now + 3600) == []
    assert alerts.evaluate(now + 130 + alerts.RENOTIFY_SECONDS + 1) == ["renotified:production"]
    assert len(_bell(developer_user)) == 2


def test_recovery_is_one_notification_and_resets_the_state(developer_user):
    now = time.time()
    _set("bad")
    alerts.evaluate(now)
    alerts.evaluate(now + 130)
    _set("ok")
    assert alerts.evaluate(now + 200) == ["resolved:production"]
    assert alerts.evaluate(now + 260) == []
    titles = [n.title for n in _bell(developer_user)]
    assert len(titles) == 2 and "خرجت من حالة الخطر" in titles[1]
    _set("bad")  # أحمرُ جديدٌ يبدأ من التأكيد لا من الإنذار
    assert alerts.evaluate(now + 300) == []


def test_a_blip_that_recovers_before_confirmation_never_alerts(developer_user):
    now = time.time()
    _set("bad")
    alerts.evaluate(now)
    _set("ok")
    alerts.evaluate(now + 60)
    _set("bad")
    assert alerts.evaluate(now + 130) == []
    assert _bell(developer_user) == []


@pytest.mark.parametrize("status", ["warn", "ok"])
def test_only_red_alerts_amber_and_green_are_a_page_not_a_notification(developer_user, status):
    now = time.time()
    _set(status)
    for step in (0, 130, 400):
        assert alerts.evaluate(now + step) == []
    assert _bell(developer_user) == []


def test_unknown_neither_alerts_nor_clears_a_firing_red(developer_user):
    now = time.time()
    _set("bad")
    alerts.evaluate(now)
    alerts.evaluate(now + 130)
    cache.delete(contract.cache_key("production"))  # اللوحةُ صارت «غيرَ معلومة»
    assert alerts.evaluate(now + 200) == []
    _set("bad")
    assert alerts.evaluate(now + 260) == []  # ما زالت firing: لا إنذارَ ثانٍ
    assert len(_bell(developer_user)) == 1


def test_every_developer_is_told_and_a_teacher_is_not(developer_user, teacher_user):
    now = time.time()
    _set("bad")
    alerts.evaluate(now)
    alerts.evaluate(now + 130)
    assert len(_bell(developer_user)) == 1
    assert _bell(teacher_user) == []


def test_a_developer_without_a_current_membership_is_skipped_but_the_state_advances(
    developer_user, db
):
    developer_user.memberships.update(is_active=False)
    now = time.time()
    _set("bad")
    alerts.evaluate(now)
    assert alerts.evaluate(now + 130) == ["fired:production"]
    assert InAppNotification.objects.count() == 0


def test_the_daily_cap_is_twelve_per_developer(developer_user):
    now = time.time()
    for _ in range(alerts.DAILY_CAP + 5):
        assert alerts.notify("عنوان", "نصّ", "production", "urgent", now) in (0, 1)
    assert len(_bell(developer_user)) == alerts.DAILY_CAP


@pytest.mark.parametrize("how", ["setting", "kill"])
def test_the_kill_switch_stops_alerts_instantly(developer_user, settings, how):
    now = time.time()
    _set("bad")
    if how == "setting":
        settings.QCC_NOTIFY_ENABLED = False
    else:
        cache.set(alerts.KILL_KEY, 1)
    assert not alerts.enabled()
    alerts.evaluate(now)
    assert alerts.evaluate(now + 130) == []
    assert _bell(developer_user) == []


def test_a_failing_notification_never_breaks_evaluation(developer_user, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(InAppNotification.objects, "create", boom)
    now = time.time()
    _set("bad")
    alerts.evaluate(now)
    assert alerts.evaluate(now + 130) == ["fired:production"]


def test_a_broken_evaluation_is_swallowed_by_the_collection_cycle(monkeypatch):
    monkeypatch.setattr(
        alerts, "evaluate", lambda now=None: (_ for _ in ()).throw(RuntimeError("x"))
    )
    assert alerts.safe_evaluate() == []


def test_every_collection_cycle_ends_with_an_alert_evaluation(monkeypatch):
    seen = []
    monkeypatch.setattr(alerts, "safe_evaluate", lambda: seen.append("evaluated"))
    collectors.run({"a": lambda: None})
    assert seen == ["evaluated"]


def test_the_alert_text_carries_no_third_party_text():
    """عنوانُ اللوحة من `PANELS` وجملتُها من ثوابت المجمِّع — لا عنوانُ طلبٍ ولا اسمُ كاتب."""
    title, body = alerts._red_text({"title": "فحوصُ CI", "headline": "main أحمرُ منذ 2 تشغيل"})
    assert title == "مركز قيادة الجودة: «فحوصُ CI» في حالة خطر"
    assert body == "main أحمرُ منذ 2 تشغيل — افتح مركز القيادة لمعرفة السبب."
    assert alerts._red_text({"title": "x", "headline": ""})[1] == "افتح مركز القيادة لمعرفة السبب."

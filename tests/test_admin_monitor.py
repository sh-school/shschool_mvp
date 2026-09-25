"""بطاقاتُ مراقبةِ المطوّر في رئيسيّة الإدارة: للمطوّر وحدَه، وبلا هويّاتِ أشخاص، ولا تُسقط الصفحةَ إن تعطّلت بطاقة."""

import pytest

from roadmap import admin_monitor
from roadmap.admin_monitor import BAD, Card

pytestmark = pytest.mark.django_db


def _staff(user):
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    return user


def test_the_developer_sees_every_card(client_as, developer_user):
    html = client_as(_staff(developer_user)).get("/admin/").content.decode()
    assert html.count("adm-card__title") == len(admin_monitor.BUILDERS)
    assert "<h1" in html


def test_a_non_developer_staff_member_sees_no_cards(client_as, teacher_user):
    response = client_as(_staff(teacher_user)).get("/admin/")
    assert response.status_code == 200
    assert "adm-card" not in response.content.decode()


def test_one_broken_card_does_not_drop_the_others(monkeypatch):
    def boom():
        raise RuntimeError("x")

    monkeypatch.setattr(admin_monitor, "BUILDERS", (boom, lambda: Card("ب", "1", "د")))
    assert [c.title for c in admin_monitor.build_cards()] == ["ب"]


def test_a_dead_letter_turns_the_notification_card_red(monkeypatch):
    class _Qs:
        def filter(self, **_):
            return self

        def values_list(self, *_, **__):
            return []

        def count(self):
            return 3

    import notifications.models as nm

    monkeypatch.setattr(nm.NotificationDelivery, "objects", _Qs())
    monkeypatch.setattr(nm.DeadLetterMessage, "objects", _Qs())
    assert admin_monitor.notifications().level == BAD


def test_the_worst_card_comes_first(monkeypatch):
    monkeypatch.setattr(
        admin_monitor,
        "BUILDERS",
        (
            lambda: Card("أ", "1", "د"),
            lambda: Card("ب", "1", "د", BAD),
            lambda: Card("ج", "1", "د", admin_monitor.WARN),
        ),
    )
    assert [c.title for c in admin_monitor.build_cards()] == ["ب", "ج", "أ"]


def test_a_missing_worker_heartbeat_is_red(monkeypatch):
    from core import worker_heartbeat

    monkeypatch.setattr(worker_heartbeat, "last_beat", lambda: None)
    assert admin_monitor.worker().level == BAD


def test_long_numbers_are_hidden_in_the_recent_actions_text():
    from core.templatetags.admin_menu import hide_ids

    assert hide_ids("Access Log for 12345678901 @ 2026-09-02") == "Access Log for •••• @ 2026-09-02"

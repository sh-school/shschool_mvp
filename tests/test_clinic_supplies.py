"""
tests/test_clinic_supplies.py — قائمةُ صلاحية مستلزمات العيادة وتنبيهُ الممرّض (W-20261020-040)

العتبتان 30/60 يوماً (قرارُ منصّةٍ)، والترتيبُ بأقرب انتهاء، والحالةُ نصٌّ لا لونٌ وحدَه،
وأنّ انقضاء الصلاحية لا يخصم ولا يحذف، وأنّ التنبيه مرّةٌ لكلّ (ممرّض، صنف، فئة)، وحصرُ الشاشة بالممرّض.
"""

import datetime as dt

import pytest
from django.test import Client
from django.urls import reverse

from clinic import supplies
from clinic.models import ClinicSupplyItem
from notifications.models import InAppNotification

TODAY = dt.date(2026, 10, 25)


def _client(user):
    c = Client()
    c.force_login(user)
    return c


def _item(school, name, days, qty=5):
    return ClinicSupplyItem.objects.create(
        school=school, name=name, expiry_date=TODAY + dt.timedelta(days=days), quantity=qty
    )


@pytest.mark.parametrize(
    ("days", "state"),
    [
        (-1, supplies.EXPIRED),
        (0, supplies.SOON),
        (30, supplies.SOON),
        (31, supplies.WARNING),
        (60, supplies.WARNING),
        (61, supplies.OK),
    ],
)
def test_classify_thresholds(days, state):
    assert supplies.classify(TODAY + dt.timedelta(days=days), TODAY) == state


def test_states_are_distinguished_by_text_not_color_alone():
    labels = {label for label, _ in supplies.STATE_LABELS.values()}
    assert len(labels) == len(supplies.STATE_LABELS)  # نصٌّ فريدٌ لكلّ فئة
    assert "30" in supplies.STATE_LABELS[supplies.SOON][0]
    assert "60" in supplies.STATE_LABELS[supplies.WARNING][0]


@pytest.mark.django_db
def test_list_is_ordered_by_nearest_expiry(school):
    _item(school, "ج", 90)
    _item(school, "أ", 10)
    _item(school, "ب", -3)
    names = [i.name for i in supplies.annotated_items(school, TODAY)]
    assert names == ["ب", "أ", "ج"]


@pytest.mark.django_db
def test_expiry_never_deducts_or_deletes(school, nurse_user):
    item = _item(school, "ضمادات", -10, qty=7)
    supplies.annotated_items(school, TODAY)
    supplies.alert_nurses(school, TODAY)
    item.refresh_from_db()
    assert item.quantity == 7
    assert ClinicSupplyItem.objects.filter(pk=item.pk).exists()


@pytest.mark.django_db
def test_alert_goes_to_nurse_once_per_item_and_state(school, nurse_user, teacher_user):
    _item(school, "مطهّر", 20)
    _item(school, "سليم", 200)
    first = supplies.alert_nurses(school, TODAY)
    again = supplies.alert_nurses(school, TODAY)
    assert (first, again) == (1, 0)
    rows = InAppNotification.objects.filter(user=nurse_user)
    assert rows.count() == 1
    assert "مطهّر" in rows.first().title
    assert not InAppNotification.objects.filter(user=teacher_user).exists()
    # دخولُ الصنف فئةً أشدّ ينبّه من جديد
    assert supplies.alert_nurses(school, TODAY + dt.timedelta(days=5)) == 0  # الفئةُ نفسها (30)
    assert supplies.alert_nurses(school, TODAY + dt.timedelta(days=30)) == 1  # صار منتهياً


@pytest.mark.django_db
def test_empty_stock_is_not_alerted(school, nurse_user):
    _item(school, "فارغ", -2, qty=0)
    assert supplies.alert_nurses(school, TODAY) == 0


@pytest.mark.django_db
def test_screen_is_nurse_only_and_lists_state_text(school, nurse_user, teacher_user):
    _item(school, "كمّامات", 45)
    url = reverse("clinic:supplies")
    assert _client(teacher_user).get(url).status_code in (302, 403)
    resp = _client(nurse_user).get(url)
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "كمّامات" in body and "ينتهي خلال 60 يوماً" in body


@pytest.mark.django_db
def test_add_and_delete_are_manual_posts_scoped_to_school(school, nurse_user):
    c = _client(nurse_user)
    r = c.post(
        reverse("clinic:supply_add"),
        {"name": "قفازات", "expiry_date": "2027-01-01", "quantity": "12"},
    )
    assert r.status_code == 302
    item = ClinicSupplyItem.objects.get(name="قفازات")
    assert (item.school_id, item.quantity) == (school.id, 12)
    bad = c.post(reverse("clinic:supply_add"), {"name": "", "expiry_date": "x", "quantity": "-1"})
    assert bad.status_code == 400
    assert c.post(reverse("clinic:supply_delete", args=[item.id])).status_code == 302
    assert not ClinicSupplyItem.objects.filter(pk=item.pk).exists()
    assert c.get(reverse("clinic:supply_delete", args=[item.id])).status_code == 405


def test_beat_is_off_by_default_and_on_with_flag():
    from clinic.supply_beat import clinic_supply_beat

    assert clinic_supply_beat({}) == {}
    on = clinic_supply_beat({"CLINIC_SUPPLY_BEAT": "1"})
    assert on["clinic-alert-supply-expiry"]["task"] == "clinic.alert_supply_expiry"

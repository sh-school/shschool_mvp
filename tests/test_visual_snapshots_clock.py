"""[IDENTITY] ساعةُ لقطات الهويّة مثبَّتة (VI-13، W-20261008-005) — بلا متصفّح.

كان أساسُ `main` يُلتقط بساعة الجهاز فيفشل كلُّ طلبٍ يُشغَّل في يومٍ آخر (تشغيلُ main@20381b76 نفسِه يوم الأساس + 1 أعطى ثماني لقطاتٍ
متغيّرة بالنسب نفسها). هذه الاختبارات تحرس التثبيتَ لا الصفحات: أن يتبعه `localdate()`، وأن تُصيّر الصفحاتُ التي تغيّرت التاريخَ
المثبَّتَ لا تاريخَ اليوم، وأن يستعمله الالتقاطُ الحيّ فلا يعود الحارسُ يقرأ ساعةَ الجهاز بصمت.
"""

from __future__ import annotations

import datetime as dt
import pathlib

import pytest
from django.utils import timezone

from tests import visual_snapshots as vs
from tests.test_a11y_live_pages import _url

pytestmark = pytest.mark.django_db

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOHA = vs.FIXED_NOW.tzinfo


def test_the_fixed_instant_is_an_ordinary_wednesday_in_doha():
    assert vs.FIXED_NOW.tzinfo is not None
    local = vs.FIXED_NOW.astimezone(DOHA)
    assert (local.weekday(), local.date()) == (2, dt.date(2026, 10, 7))


def test_the_frozen_clock_pins_now_and_the_local_date_and_then_restores():
    before = timezone.now()
    with vs.frozen_clock():
        assert timezone.now() == vs.FIXED_NOW
        assert timezone.localdate() == dt.date(2026, 10, 7)
        assert timezone.localtime().weekday() == 2
    assert timezone.now() != vs.FIXED_NOW
    assert abs((timezone.now() - before).total_seconds()) < 60


def test_the_clock_can_be_pinned_to_another_day_for_the_sensitivity_probe():
    thursday = vs.FIXED_NOW + dt.timedelta(days=1)
    with vs.frozen_clock(thursday):
        assert timezone.localdate() == dt.date(2026, 10, 8)
        assert timezone.localtime().weekday() == 3


def test_the_daily_report_shows_the_pinned_date_not_todays(client_as, principal_user):
    with vs.frozen_clock():
        html = client_as(principal_user).get(_url("daily_report")).content.decode()
    assert "07/10/2026" in html
    assert "الأربعاء" in html


def test_the_floors_page_follows_the_pinned_weekday(client_as, admin_supervisor_user):
    with vs.frozen_clock():
        wednesday = client_as(admin_supervisor_user).get(_url("wings:floors")).content.decode()
    with vs.frozen_clock(vs.FIXED_NOW + dt.timedelta(days=1)):
        thursday = client_as(admin_supervisor_user).get(_url("wings:floors")).content.decode()
    # الصفحةُ تتبع اليومَ المثبَّت (وكان اختلافُ اليوم وراء 100% في لقطة الجوال).
    assert wednesday.count("الخميس") != thursday.count("الخميس") or len(wednesday) != len(thursday)


def test_the_live_capture_pins_both_clocks():
    """الالتقاطُ الحيّ يثبّت ساعةَ الخادم وساعةَ المتصفّح — لا يعود يقرأ ساعةَ الجهاز بصمت (الاختبارُ نفسُه لا يُشغَّل إلا من visual-snapshots)."""
    source = (ROOT / "tests/e2e/test_visual_snapshots_live.py").read_text(encoding="utf-8")
    assert "vs.frozen_clock()" in source
    assert "context.clock.set_fixed_time(vs.FIXED_NOW)" in source

"""بطاقةُ «صحّة Git» في رئيسيّة الإدارة (REP-10 ب): آخرُ قراءةٍ لـRK1..RK3 من الخارطة وعمرُها — أرقامٌ وتواريخُ وحدَها.

القياسُ الفعليّ على جهاز المطوّر (`scripts/prune_local_branches.sh --json`) ولا سبيلَ إليه من التطبيق: صورةُ الحاوية بلا git والإنتاجُ بلا `.git`.
فالبطاقةُ لا تدّعي قياساً حيّاً: تعرض آخرَ قراءةٍ مسجَّلةٍ في الخارطة وعمرَها، وتصفرّ حين تتأخّر وتحمرّ حين لا يُعتدّ بها — فلا يُطمأنّ
بقراءةٍ قديمةٍ ولا بغيابها.
"""

import datetime
import re

import pytest

from roadmap import admin_monitor
from roadmap.admin_monitor import BAD, OK, WARN
from roadmap.models import RoadmapKpi

pytestmark = pytest.mark.django_db

TODAY = datetime.date(2026, 10, 5)
FRESH = TODAY - datetime.timedelta(days=1)


def _reading(code, current, target, measured=FRESH, target_text=""):
    RoadmapKpi.objects.update_or_create(
        code=code,
        defaults={
            "lane": "ops",
            "name": code,
            "current": current,
            "target": target,
            "direction": "down",
            "measured_at": measured,
            "target_text": target_text,
        },
    )


@pytest.fixture(autouse=True)
def _no_seeded_readings():
    """هجراتُ الخارطة تبذر RK1..RK3 بقيمٍ حقيقيّة؛ كلُّ اختبارٍ يبدأ من لا شيءٍ ويضع قراءاتِه."""
    RoadmapKpi.objects.filter(code__in=["RK1", "RK2", "RK3"]).delete()


def _healthy(measured=FRESH):
    _reading("RK1", 40, 40, measured, "≤ 40")
    _reading("RK2", 0, 0, measured)
    _reading("RK3", 0, 0, measured)


def test_no_reading_is_shown_as_unmeasured_not_as_healthy():
    card = admin_monitor.git_health(TODAY)

    assert card.level == WARN
    assert card.value == "غير مقيس"


def test_every_indicator_on_target_and_fresh_is_green():
    _healthy()

    card = admin_monitor.git_health(TODAY)

    assert card.level == OK
    assert card.value == "3 من 3 على الهدف"
    assert "أقدمُ قراءةٍ قبل 1 يوماً" in card.detail


def test_clutter_above_target_is_yellow_and_names_the_target():
    _healthy()
    _reading("RK1", 322, 40, target_text="≤ 40")

    card = admin_monitor.git_health(TODAY)

    assert card.level == WARN
    assert card.value == "2 من 3 على الهدف"
    assert "فروعٌ محلّيّة 322 (الهدف ≤ 40)" in card.detail


def test_unique_work_with_a_single_copy_above_target_is_red_not_yellow():
    """فقدانُ عملٍ فريدٍ لا يُسترجع — ليس نظافةً مؤجَّلة."""
    _healthy()
    _reading("RK2", 1, 0)

    card = admin_monitor.git_health(TODAY)

    assert card.level == BAD
    assert "عملٌ فريدٌ بنسخةٍ وحيدة 1 (الهدف 0)" in card.detail


def test_a_reading_older_than_eight_days_is_late_and_older_than_fifteen_is_not_trusted():
    _healthy(TODAY - datetime.timedelta(days=9))
    late = admin_monitor.git_health(TODAY)

    _healthy(TODAY - datetime.timedelta(days=16))
    stale = admin_monitor.git_health(TODAY)

    assert late.level == WARN and "متأخّرة" in late.detail
    assert stale.level == BAD and "لا يُعتدّ بها" in stale.detail


def test_the_age_is_the_oldest_reading_not_the_newest():
    _healthy()
    _reading("RK3", 0, 0, TODAY - datetime.timedelta(days=20))

    card = admin_monitor.git_health(TODAY)

    assert card.level == BAD
    assert "أقدمُ قراءةٍ قبل 20 يوماً" in card.detail


def test_an_undated_reading_is_not_green():
    _healthy()
    _reading("RK2", 0, 0, measured=None)

    card = admin_monitor.git_health(TODAY)

    assert card.level == WARN
    assert "بلا تاريخ" in card.detail


def test_an_indicator_without_a_reading_is_counted_not_ignored():
    _reading("RK1", 40, 40, target_text="≤ 40")
    _reading("RK2", 0, 0)

    card = admin_monitor.git_health(TODAY)

    assert card.level == WARN
    assert "1 بلا قراءة" in card.detail
    assert card.value == "2 من 3 على الهدف"


def test_the_card_is_on_the_developer_home_and_links_to_the_roadmap():
    assert admin_monitor.git_health in admin_monitor.BUILDERS
    _healthy()

    assert admin_monitor.git_health(TODAY).url == "/roadmap/"


def test_the_card_text_holds_only_labels_numbers_and_dates():
    """لا هويّةَ شخصٍ ولا اسمَ فرعٍ ولا مساراً ولا رقماً طويلاً — عدّاداتٌ فقط (PDPPL)."""
    _healthy()
    _reading("RK1", 322, 40, target_text="≤ 40")

    detail = admin_monitor.git_health(TODAY).detail

    assert not re.search(r"\d{5,}", detail)
    assert not re.search(r"[A-Za-z]{3,}", re.sub(r"RK\d", "", detail)), detail

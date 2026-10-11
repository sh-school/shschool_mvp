"""بابُ الرصد المؤقّت تلقائيٌّ بغياب الجدول الحيّ (W-20261010-055، قرارُ المالك 10-10: لا مفتاحَ طوارئ يدويّ).

معيارُ «الجدول الحيّ» واحد: `ScheduleSlot` نشطةٌ للمدرسة والسنة الجارية (0301) — لا حالةُ `approved` وحدَها.
"""

import pytest
from django.template import Context, Template
from django.test import RequestFactory
from django.urls import reverse

from operations.models import ScheduleSlot
from operations.services import provisional_session as door
from tests.test_week_page import YEAR, world  # noqa: F401
from tests.test_week_page import _slot as make_slot

pytestmark = pytest.mark.django_db


@pytest.fixture
def bare(world):
    """عالمٌ بلا حصصٍ حيّةٍ: العالمُ المشتركُ يأتي بحصصه فتُمحى ليبدأ كلُّ اختبارٍ من «لا جدولَ»."""
    ScheduleSlot.objects.all().delete()
    return world


def _render(user):
    request = RequestFactory().get("/")
    request.user = user
    return Template(
        "{% load provisional_door %}{% provisional_enabled as prov %}{% if prov %}DOOR{% else %}GRID{% endif %}"
    ).render(Context({"request": request}))


class TestTheLiveScheduleCriterion:
    def test_no_slots_means_no_live_schedule(self, bare):
        assert not door.has_live_schedule(bare["school"])
        assert door.enabled(bare["school"]) is True

    def test_an_active_slot_is_a_live_schedule(self, bare, settings):
        settings.PROVISIONAL_GRID_ENABLED = True
        from datetime import time

        from operations.models import Subject

        subject = Subject.objects.create(school=bare["school"], name_ar="العلوم", code="SCI")
        make_slot(bare, bare["t1"], 0, 1, time(7, 10), time(7, 55), subject)

        assert door.has_live_schedule(bare["school"])
        assert door.enabled(bare["school"]) is False

    def test_an_inactive_slot_is_not_live(self, bare):
        from datetime import time

        from operations.models import Subject

        subject = Subject.objects.create(school=bare["school"], name_ar="العلوم", code="SCI")
        make_slot(bare, bare["t1"], 0, 1, time(7, 10), time(7, 55), subject)
        ScheduleSlot.objects.update(is_active=False)

        assert not door.has_live_schedule(bare["school"])

    def test_approved_generation_without_active_slots_is_not_live(self, bare):
        from operations.models import ScheduleGeneration

        ScheduleGeneration.objects.create(
            school=bare["school"], academic_year=YEAR, status="approved"
        )

        assert not door.has_live_schedule(bare["school"])

    def test_active_slots_without_an_approved_generation_are_live(self, bare):
        from datetime import time

        from operations.models import ScheduleGeneration, Subject

        subject = Subject.objects.create(school=bare["school"], name_ar="العلوم", code="SCI")
        make_slot(bare, bare["t1"], 0, 1, time(7, 10), time(7, 55), subject)

        assert not ScheduleGeneration.objects.filter(status="approved").exists()
        assert door.has_live_schedule(bare["school"])

    def test_without_a_school_the_old_key_decides(self, settings):
        settings.PROVISIONAL_GRID_ENABLED = True
        assert door.enabled() is True
        settings.PROVISIONAL_GRID_ENABLED = False
        assert door.enabled() is False
        assert not door.has_live_schedule(None)


class TestTheTemplateTag:
    def test_door_without_a_live_schedule_and_grid_with_one(self, bare):
        from datetime import time

        from operations.models import Subject

        assert _render(bare["t1"]) == "DOOR"
        subject = Subject.objects.create(school=bare["school"], name_ar="العلوم", code="SCI")
        make_slot(bare, bare["t1"], 0, 1, time(7, 10), time(7, 55), subject)
        assert _render(bare["t1"]) == "GRID"


def test_the_teacher_dashboard_swaps_the_card_for_the_sessions(bare, client):
    from datetime import time

    from operations.models import Subject

    client.force_login(bare["t1"])
    response = client.get(reverse("dashboard"), HTTP_HOST="localhost")
    assert response.status_code == 200, response.status_code
    before = response.content.decode()
    assert "شُعبي للرصد" in before and "رصدُ الغياب (مؤقّت" in before

    subject = Subject.objects.create(school=bare["school"], name_ar="العلوم", code="SCI")
    make_slot(bare, bare["t1"], 0, 1, time(7, 10), time(7, 55), subject)
    after = client.get(reverse("dashboard"), HTTP_HOST="localhost").content.decode()
    assert "شُعبي للرصد" not in after and "رصدُ الغياب (مؤقّت" not in after

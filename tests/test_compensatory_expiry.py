"""طلباتُ التعويض المفتوحة التي فات وقتُها تُنهى يومياً (2026-09-25).

كانت `CompensatoryService.expire_overdue` مكتوبةً لا يستدعيها شيء، وقاعدتُها الوحيدة «أكثرُ من أسبوعين
من الإنشاء» — فطلبٌ لزميلٍ لم يردّ يبقى معلَّقاً بعد أن يصير يومُ تعويضه في الماضي ولا يقبله أحد
(`_not_past`)، فيُعدّ انشغالاً في طلبات صاحبه ويسدّ خانةَ يومه. فصارت تُنهي كلَّ طلبٍ مفتوحٍ مضى يومُه،
وتستدعيها مهمّةٌ يوميّةٌ تعمل في كلّ مدرسةٍ في نطاقها.
"""

import datetime as dt

import pytest

from operations.models import CompensatorySession
from operations.services import CompensatoryService
from tests.conftest import SchoolFactory
from tests.test_compensatory_bell import TODAY, world  # noqa: F401 — الاختبارُ نفسُ عالَمِه

pytestmark = pytest.mark.django_db

PAST = TODAY - dt.timedelta(days=1)
FUTURE = TODAY + dt.timedelta(days=2)


def _comp(world, day, period, status="pending"):
    return CompensatorySession.objects.create(
        school=world["school"],
        teacher=world["teacher"],
        original_slot=world["ground_slot"],
        absence=world["absence"],
        compensatory_date=day,
        compensatory_period=period,
        class_group=world["ground"],
        subject=world["subject"],
        status=status,
    )


def _status(comp):
    return CompensatorySession.objects.get(pk=comp.pk).status


class TestExpiringWhatCanNoLongerBeAccepted:
    @pytest.mark.parametrize("status", ["colleague", "pending"])
    def test_an_open_request_whose_day_has_passed_expires(self, world, status):
        comp = _comp(world, PAST, 2, status)

        assert CompensatoryService.expire_overdue(world["school"]) == 1
        assert _status(comp) == "expired"

    def test_today_and_the_future_stay_open(self, world):
        today = _comp(world, TODAY, 2)
        later = _comp(world, FUTURE, 3, "colleague")

        assert CompensatoryService.expire_overdue(world["school"]) == 0
        assert (_status(today), _status(later)) == ("pending", "colleague")

    @pytest.mark.parametrize("status", ["approved", "completed", "cancelled"])
    def test_a_settled_request_is_never_touched(self, world, status):
        comp = _comp(world, PAST, 2, status)

        assert CompensatoryService.expire_overdue(world["school"]) == 0
        assert _status(comp) == status

    def test_a_request_older_than_two_weeks_expires_even_for_a_future_day(self, world):
        """القاعدةُ القديمة باقية — لا يُترك طلبٌ قديمٌ مفتوحاً."""
        old = _comp(world, FUTURE, 3)
        CompensatorySession.objects.filter(pk=old.pk).update(
            created_at=dt.datetime.combine(TODAY - dt.timedelta(days=15), dt.time(9, 0), dt.UTC)
        )

        assert CompensatoryService.expire_overdue(world["school"]) == 1
        assert _status(old) == "expired"

    def test_only_the_given_school_is_touched(self, world):
        mine = _comp(world, PAST, 2)

        other = SchoolFactory()
        assert CompensatoryService.expire_overdue(other) == 0
        assert _status(mine) == "pending"

    def test_it_is_idempotent(self, world):
        _comp(world, PAST, 2)

        assert CompensatoryService.expire_overdue(world["school"]) == 1
        assert CompensatoryService.expire_overdue(world["school"]) == 0

    def test_an_expired_request_frees_its_slot_for_a_new_one(self, world):
        """قيدُ التفرّد يستثني المنتهيَ: لا يسدّ الفراغَ على صاحبه."""
        first = _comp(world, PAST, 2)
        CompensatoryService.expire_overdue(world["school"])

        second = _comp(world, PAST, 2)

        assert second.pk != first.pk and _status(second) == "pending"


class TestTheDailyTask:
    def test_it_expires_across_schools_and_reports_the_count(self, world):
        from operations.tasks import expire_overdue_compensatory_task

        comp = _comp(world, PAST, 2)

        result = expire_overdue_compensatory_task()

        assert result["expired"] >= 1 and result["failed_schools"] == 0
        assert _status(comp) == "expired"

    def test_a_broken_school_does_not_stop_the_others(self, world, monkeypatch):
        from operations.tasks import expire_overdue_compensatory_task

        comp = _comp(world, PAST, 2)
        broken = SchoolFactory()
        real = CompensatoryService.expire_overdue

        def flaky(school):
            if school.pk == broken.pk:
                raise RuntimeError("مدرسةٌ معطوبة")
            return real(school)

        monkeypatch.setattr(CompensatoryService, "expire_overdue", staticmethod(flaky))

        result = expire_overdue_compensatory_task()

        assert result["failed_schools"] == 1
        assert _status(comp) == "expired", "عطبُ مدرسةٍ لا يمنع غيرَها"

    def test_it_is_scheduled_daily_before_school(self):
        from shschool.celery import app

        entry = app.conf.beat_schedule["expire-overdue-compensatory"]

        assert entry["task"] == "operations.expire_overdue_compensatory"
        assert entry["schedule"].hour == {4} and entry["schedule"].minute == {15}

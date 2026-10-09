"""منسّق شؤون الطلبة يتابع الغياب ويرصد ويصحّح ويحصره في المدرسة كلِّها (W-20261001-020).

قرارا المالك المباشران 2026-10-08: D-266م (يُضاف إلى الأدوار المسمّاة في سياسة جدول الشعبة كقيادة الغياب:
قراءةٌ وكتابةٌ وتصحيحٌ على كلّ الأجنحة، والتصحيحُ بسببٍ إلزاميّ) وD-267م (حاصرُ الغياب العامّ بالدور).
ولا يعتمد (الاعتمادُ ملغى بـD-245م)، ولا يدير الأنشطة، ولا يغيّر الأدوار.
"""

import pytest

from core.capabilities import has_capability
from operations.attendance_policy import (
    can_approve,
    can_correct_grid,
    can_read_grid,
    can_write_grid,
)
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import SUNDAY, _staff, at
from wings.services import holds_school_wide

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _grid_on(settings):
    settings.PROVISIONAL_GRID_ENABLED = True


@pytest.fixture
def coordinator(school):
    return _staff(school, "student_affairs_coordinator", "منسق شؤون الطلبة", "29000009901")


class TestReadWriteCorrect:
    def test_it_reads_any_wing_grid(self, coordinator, klass):
        assert can_read_grid(coordinator, klass, SUNDAY)

    def test_it_writes_in_the_window(self, coordinator, klass):
        assert can_write_grid(coordinator, klass, SUNDAY, now=at(9, 0))

    def test_it_cannot_write_after_the_window_closes(self, coordinator, klass):
        assert can_write_grid(coordinator, klass, SUNDAY, now=at(14, 1)).reason == "after_window"

    def test_it_corrects_after_the_window(self, coordinator, klass):
        assert can_correct_grid(coordinator, klass, SUNDAY, now=at(15, 0))

    def test_it_cannot_correct_another_day(self, coordinator, klass):
        later = at(15, 0).replace(day=SUNDAY.day + 1)
        assert can_correct_grid(coordinator, klass, SUNDAY, now=later).reason == "not_today"


class TestNoApproval:
    def test_it_does_not_approve_a_pending_entry(self, coordinator, session):
        """D-266م: لا يعتمد — حتى وهو حاصرُ الغياب العامّ الذي كان معتمِدًا ثانيًا."""
        verdict = can_approve(coordinator, session)

        assert not verdict
        assert verdict.reason == "not_approver"


class TestSchoolWide:
    def test_it_holds_school_wide_by_its_role(self, coordinator):
        assert holds_school_wide(coordinator)
        assert has_capability(coordinator, "wings.school_wide")

    def test_it_records_the_wing_day(self, coordinator):
        assert has_capability(coordinator, "wings.record_day")

    def test_a_teacher_does_not_hold_it(self, school):
        teacher = _staff(school, "teacher", "معلّم", "29000009902")

        assert not holds_school_wide(teacher)
        assert not has_capability(teacher, "wings.school_wide")

    def test_it_does_not_hold_the_wing_exclusive_powers(self, coordinator):
        assert not has_capability(coordinator, "wings.excuse_after_deadline")
        # تكليفُ البديل صار له بقرار المالك 2026-10-08 («كلُّ ما يخص الطلاب»).
        assert has_capability(coordinator, "wings.assign_cover")

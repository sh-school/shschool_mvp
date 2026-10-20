"""معاينةُ الخطوة التصعيديّة قبل الحفظ — W-20260928-007.

تطابق المعاينةُ ما يكتبه `create_infraction` بعد الحفظ، ولا تكتب شيئاً.
"""

import pytest

from behavior.models import BehaviorInfraction
from behavior.services import BehaviorService
from tests.conftest import SchoolFactory, UserFactory


@pytest.mark.django_db
class TestPreviewEscalation:
    def test_preview_matches_stored_step_on_first_record(self):
        school = SchoolFactory()
        student = UserFactory()
        reporter = UserFactory()

        preview = BehaviorService.preview_escalation(student, school, level=2)
        infraction = BehaviorService.create_infraction(
            school=school,
            student=student,
            reporter=reporter,
            level=2,
            description="مخالفة أولى",
        )

        assert preview["prior"] == 0
        assert preview["step"] == infraction.escalation_step

    def test_preview_advances_after_a_prior_record(self):
        school = SchoolFactory()
        student = UserFactory()
        reporter = UserFactory()
        BehaviorService.create_infraction(
            school=school, student=student, reporter=reporter, level=2, description="أولى"
        )

        preview = BehaviorService.preview_escalation(student, school, level=2)
        second = BehaviorService.create_infraction(
            school=school, student=student, reporter=reporter, level=2, description="ثانية"
        )

        assert preview["prior"] == 1
        assert preview["step"] == second.escalation_step

    def test_preview_writes_nothing(self):
        school = SchoolFactory()
        student = UserFactory()
        before = BehaviorInfraction.objects.count()

        BehaviorService.preview_escalation(student, school, level=1)

        assert BehaviorInfraction.objects.count() == before

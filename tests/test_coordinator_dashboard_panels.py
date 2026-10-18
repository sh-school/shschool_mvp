"""أقسام لوحة منسّق شؤون الطلبة (W-20261018-001): بالقدرات القائمة، ولا رقمَ هاتفٍ، ولا قسمَ لمن لا قدرةَ له."""

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse
from django.utils import timezone

from behavior.models import BehaviorInfraction
from tests.operations.test_absence_followup import (  # noqa: F401
    _calendar_first,
    _post_action,
    absent_both,
    second_wing,
    staff,
)
from tests.test_period_register import (  # noqa: F401
    kids,
    klass,
    other_teacher,
    subjects,
    supervisor,
    teacher,
    year,
)

pytestmark = pytest.mark.django_db

#: غيابُ الاختبار مسجَّلٌ يومَ الأحد، فتُثبَّت الساعةُ عليه كي تقرأه اللوحةُ «اليومَ».
SUNDAY_NOON = dt.datetime(2026, 9, 13, 12, 0, tzinfo=ZoneInfo("Asia/Qatar"))


def _dash(client_as, user):
    return client_as(user).get(reverse("student_affairs:dashboard"))


def _body(client_as, user):
    resp = _dash(client_as, user)
    assert resp.status_code == 200
    return resp.content.decode()


class TestCoordinatorPanels:
    @pytest.mark.pin_clock(SUNDAY_NOON)
    def test_the_two_links_and_the_counts_appear(self, client_as, staff, absent_both):
        body = _body(client_as, staff["coordinator"])
        assert reverse("daily_report") in body and reverse("absence_actions") in body
        assert "متابعة الغياب والتواصل" in body
        for label in ("تمّ جزئياً", "لم يتمّ", "لم تتمّ المتابعة"):
            assert label in body

    @pytest.mark.pin_clock(SUNDAY_NOON)
    def test_a_received_sick_leave_is_listed(self, client_as, staff, absent_both):
        _post_action(client_as, staff["coordinator"], absent_both[0], status="sick_leave_received")
        body = _body(client_as, staff["coordinator"])
        assert "استلام الإجازات المرضية" in body and absent_both[0].full_name in body

    @pytest.mark.pin_clock(SUNDAY_NOON)
    def test_the_guardian_number_shows_with_an_audit_row_and_no_name(
        self, client_as, staff, school, kids, absent_both
    ):
        from core.models import AuditLog
        from tests.operations.test_absence_followup import _family

        _family(school, kids[0])
        BehaviorInfraction.objects.create(
            school=school, student=kids[0], reported_by=staff["principal"], level=4
        )
        body = _body(client_as, staff["coordinator"])
        assert "tel:" in body
        from tests.operations.test_absence_followup import FATHER_NAME, FATHER_PHONE, MOTHER_NAME

        assert FATHER_PHONE in body and FATHER_NAME not in body and MOTHER_NAME not in body
        rows = AuditLog.objects.filter(object_repr__contains="لوحة شؤون الطلبة")
        assert rows.exists() and "phones" in str(rows.first().changes)

    def test_pledge_list_shows_today_level_two_and_open_level_four(
        self, client_as, staff, school, kids, absent_both
    ):
        BehaviorInfraction.objects.create(
            school=school, student=kids[0], reported_by=staff["principal"], level=2
        )
        BehaviorInfraction.objects.create(
            school=school, student=kids[1], reported_by=staff["principal"], level=4
        )
        body = _body(client_as, staff["coordinator"])
        assert "المستدعون للتعهّد" in body
        assert kids[0].full_name in body and kids[1].full_name in body
        assert "لم يُستدعَ بعد" in body and timezone.localdate() is not None

    def test_a_summoned_and_signed_infraction_reads_its_state(
        self, client_as, staff, school, kids, absent_both
    ):
        BehaviorInfraction.objects.create(
            school=school,
            student=kids[0],
            reported_by=staff["principal"],
            level=4,
            parent_summoned=True,
            parent_undertaking_signed=True,
        )
        assert "التعهدُ موقَّع" in _body(client_as, staff["coordinator"])

    def test_a_wing_supervisor_gets_no_pledge_list(self, client_as, supervisor, absent_both):
        body = _body(client_as, supervisor)
        assert "المستدعون للتعهّد" not in body


class TestBehaviorReportPhone:
    def test_the_coordinator_sees_the_number_and_the_teacher_does_not(
        self, client_as, staff, teacher, school, kids, absent_both
    ):
        from tests.conftest import MembershipFactory, RoleFactory
        from tests.operations.test_absence_followup import FATHER_PHONE, _family

        MembershipFactory(
            user=kids[0], school=school, role=RoleFactory(school=school, name="student")
        )
        _family(school, kids[0])
        url = reverse("behavior:behavior_report", args=[kids[0].id])
        seen = client_as(staff["coordinator"]).get(url)
        assert seen.status_code == 200 and FATHER_PHONE in seen.content.decode()
        other = client_as(teacher).get(url)
        assert other.status_code != 200 or FATHER_PHONE not in other.content.decode()

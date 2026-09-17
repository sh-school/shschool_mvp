"""ما بقي من مراجعة #290 — هواتفُ الأهل تُدقَّق، والعذرُ لا يعود إلى عامٍ مضى، والأيّامُ أيّام.

- **الهواتف** (قرارُ 2026-09-16، docs/privacy/guardian_phones.md): يراها كلُّ من يحمل الجناح،
  والبديلُ منهم — وكلُّ عرضٍ سطرٌ في سجلّ التدقيق بلا رقمٍ ولا اسم.
- **صفحةُ التصحيح** كانت تملأ «من/إلى» بآخر غيابٍ بلا عذرٍ في كلّ الأعوام، فيُرسَل عذرُ
  اليوم ومستندُه إلى النائب عن يونيو الماضي.
- **أكثرُ الطلاب غياباً** كان يعدّ سجلّاتِ الحصص وعنوانُه «أيّام».
"""

import datetime as dt
from unittest import mock

import pytest
from django.urls import reverse

from core.models import AuditLog, ParentStudentLink
from tests.conftest import MembershipFactory, RoleFactory, UserFactory
from tests.test_absence_excuses import MONDAY, _absent_day, _back  # noqa: F401
from tests.test_period_register import (  # noqa: F401
    SUNDAY,
    kids,
    klass,
    subjects,
    supervisor,
    teacher,
    year,
)

pytestmark = pytest.mark.django_db

PHONE = "55512345"


def _father(school, kid, phone=PHONE):
    father = UserFactory(full_name="وليُّ أمرٍ تجريبيّ", national_id="29300000082", phone=phone)
    MembershipFactory(user=father, school=school, role=RoleFactory(school=school, name="parent"))
    ParentStudentLink.objects.create(
        school=school, parent=father, student=kid, relationship="father"
    )
    return father


def _phone_views():
    return AuditLog.objects.filter(action="view", model_name="ParentStudentLink")


class TestGuardianPhonesLeaveATrace:
    def test_opening_the_file_with_a_phone_is_audited_without_the_number(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _father(school, kids[0])
        _absent_day(school, klass, kids[0], teacher, supervisor)

        body = (
            client_as(supervisor)
            .get(reverse("wings:absence_file", args=[kids[0].id]))
            .content.decode()
        )

        assert f'href="tel:{PHONE}"' in body
        entry = _phone_views().get()
        assert entry.user == supervisor
        assert entry.object_id == str(kids[0].id)
        assert entry.changes == {"phones": 1, "role": "admin_supervisor"}
        assert PHONE not in f"{entry.object_repr}{entry.changes}"
        assert "وليُّ أمرٍ تجريبيّ" not in entry.object_repr

    def test_each_opening_is_its_own_trace(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _father(school, kids[0])
        _absent_day(school, klass, kids[0], teacher, supervisor)
        client = client_as(supervisor)

        for _ in range(2):
            client.get(reverse("wings:absence_file", args=[kids[0].id]))

        assert _phone_views().count() == 2

    @pytest.mark.parametrize("phone", [None, ""])
    def test_no_phone_shown_means_no_trace(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor, phone
    ):
        if phone is not None:
            _father(school, kids[0], phone=phone)
        _absent_day(school, klass, kids[0], teacher, supervisor)

        response = client_as(supervisor).get(reverse("wings:absence_file", args=[kids[0].id]))

        assert response.status_code == 200
        assert not _phone_views().exists()


class TestTheCorrectionPageStaysInThisYear:
    def test_an_absence_from_last_year_does_not_fill_the_dates(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        last_june = dt.date(2026, 6, 14)
        _absent_day(school, klass, kids[0], teacher, supervisor, day=last_june)
        _back(school, klass, teacher, supervisor, SUNDAY)

        with mock.patch("django.utils.timezone.localdate", return_value=MONDAY):
            response = client_as(supervisor).get(
                reverse("wings:student_events", args=[klass.id, kids[0].id])
            )

        assert response.context["excuse_day"] == MONDAY

    def test_an_absence_this_year_still_fills_them(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _absent_day(school, klass, kids[0], teacher, supervisor)

        with mock.patch("django.utils.timezone.localdate", return_value=MONDAY):
            response = client_as(supervisor).get(
                reverse("wings:student_events", args=[klass.id, kids[0].id])
            )

        assert response.context["excuse_day"] == SUNDAY


class TestMostAbsentCountsDays:
    def test_a_full_day_of_periods_is_one_day(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _absent_day(school, klass, kids[0], teacher, supervisor, count=7)

        with mock.patch("django.utils.timezone.localdate", return_value=MONDAY):
            response = client_as(supervisor).get(reverse("student_affairs:attendance_overview"))

        rows = [s for s in response.context["worst_students"] if s["student__id"] == kids[0].id]
        assert len(rows) == 1
        row = rows[0]
        assert row["absence_count"] == 1
        assert row["badge"] == "status-info"
        assert "1 يوم" in response.content.decode()

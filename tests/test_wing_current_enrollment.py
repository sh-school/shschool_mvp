"""الطالبُ في جناحٍ واحدٍ في كلّ شاشة — بقيده الجاري لا بأيّ قيدٍ نشط.

مراجعةُ #285 المستقلّة: طالبٌ انتقل إلى جناحٍ آخر وبقي قيدُه القديمُ نشطاً (يقع بعد استيرادٍ
مصحَّح، ومئاتُ الطلبة يحملون قيدين) كان مشرفُ جناحه القديم يجده في البحث ويفتح صفحةَ تصحيحه
ويكتب عذرَه وإخطارَه ويُنبَّه عنه في لوحته، ومركزُ المعلومات يعدّه في بطاقة شعبته القديمة —
بينما شؤونُ الطلبة ومركزُ المعلومات يردّانه بـ404. فصار السؤالُ واحداً: `wings/scope.py`.
"""

import datetime as dt

import pytest
from django.urls import reverse

from core.models import StudentEnrollment, Wing
from operations.models import AbsenceExcuse, GuardianContact
from student_info.services import current_class_group
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)
from tests.test_absence_excuses import _absent_day  # noqa: F401
from tests.test_period_register import (  # noqa: F401
    SUNDAY,
    kids,
    klass,
    subjects,
    supervisor,
    teacher,
    year,
)
from wings.services import supervisor_watchlist

pytestmark = pytest.mark.django_db

MONDAY = SUNDAY + dt.timedelta(days=1)


@pytest.fixture
def moved(school, seeded_calendar, year, klass, supervisor):
    """طالبٌ قيدُه القديمُ في شعبة الجناح الأوّل (01/09)، والجديدُ في الجناح الثاني (10/09) — وكلاهما نشط."""
    other = UserFactory(full_name="مشرف الجناح الثاني", national_id="29500000001")
    MembershipFactory(
        user=other, school=school, role=RoleFactory(school=school, name="admin_supervisor")
    )
    wing2 = Wing.objects.create(
        school=school, code="w2", name="جناح 2", academic_year=year, supervisor=other
    )
    klass2 = ClassGroupFactory(
        school=school, grade="G7", section="2", level_type="prep", academic_year=year, wing=wing2
    )
    student = UserFactory(full_name="طالبٌ منقول", national_id="29500000011")
    MembershipFactory(user=student, school=school, role=RoleFactory(school=school, name="student"))
    StudentEnrollmentFactory(student=student, class_group=klass, enrolled_at=dt.date(2026, 9, 1))
    StudentEnrollmentFactory(student=student, class_group=klass2, enrolled_at=dt.date(2026, 9, 10))
    return {"student": student, "old": klass, "new": klass2, "new_supervisor": other}


class TestTheOldWingLetsGo:
    def test_the_search_does_not_find_him(self, seeded_calendar, client_as, supervisor, moved):
        body = (
            client_as(supervisor)
            .get(reverse("wings:student_search"), {"q": "منقول"})
            .content.decode()
        )

        assert "لا طالبَ بهذا الاسم أو الرقم في جناحك" in body

    def test_his_correction_page_and_file_are_404(
        self, seeded_calendar, client_as, supervisor, kids, moved
    ):
        client = client_as(supervisor)
        student, old = moved["student"], moved["old"]
        # الشاهدُ أنّ الـ404 ليس لعطبٍ في التجهيز: طالبُ جناحه الباقي يُفتح.
        assert client.get(reverse("wings:absence_file", args=[kids[0].id])).status_code == 200

        assert (
            client.get(reverse("wings:student_events", args=[old.id, student.id])).status_code
            == 404
        )
        assert client.get(reverse("wings:absence_file", args=[student.id])).status_code == 404

    def test_no_excuse_or_call_can_be_written_through_the_old_section(
        self, seeded_calendar, client_as, school, supervisor, moved
    ):
        client = client_as(supervisor)
        student, old = moved["student"], moved["old"]

        excuse = client.post(
            reverse("wings:excuse_grant", args=[old.id, student.id]),
            {"date_from": SUNDAY.isoformat(), "kind": "bereavement", "notes": "الأب"},
        )
        call = client.post(
            reverse("wings:guardian_contact_log", args=[old.id, student.id]),
            {"absence_date": SUNDAY.isoformat(), "outcome": "answered"},
        )

        assert (excuse.status_code, call.status_code) == (404, 404)
        assert not AbsenceExcuse.objects.exists() and not GuardianContact.objects.exists()

    def test_his_absence_does_not_alert_the_old_wing(
        self, school, seeded_calendar, year, teacher, supervisor, moved
    ):
        _absent_day(school, moved["old"], moved["student"], teacher, supervisor)

        watch = supervisor_watchlist(supervisor, school, year, MONDAY)

        assert moved["student"] not in [r.student for r in watch["awaiting_contact"]]


class TestTheNewWingHasHim:
    def test_his_new_supervisor_opens_his_file(self, seeded_calendar, client_as, moved):
        response = client_as(moved["new_supervisor"]).get(
            reverse("wings:absence_file", args=[moved["student"].id])
        )

        assert response.status_code == 200

    def test_the_student_info_card_counts_him_only_in_the_new_section(
        self, seeded_calendar, client_as, supervisor, moved
    ):
        response = client_as(supervisor).get(reverse("student_info:sections"))

        counts = {g.id: g.student_count for g in response.context["groups"]}
        assert counts[moved["old"].id] == 0

    def test_his_file_shows_the_section_that_decides_his_wing(
        self, seeded_calendar, school, year, moved
    ):
        assert current_class_group(moved["student"], year) == moved["new"]


class TestTheTieIsBrokenTheSameWayEverywhere:
    def test_two_enrollments_on_the_same_day_resolve_identically(
        self, school, seeded_calendar, year, klass, supervisor, moved
    ):
        """قيدان بالتاريخ نفسه: الترتيبُ نفسُه في `current_of` و`wings/scope.py`."""
        from wings.scope import student_scope

        student = moved["student"]
        StudentEnrollment.objects.filter(student=student).update(enrolled_at=dt.date(2026, 9, 10))
        current = StudentEnrollment.objects.current_of(student, school)
        in_old_wing = student.id in student_scope(supervisor, school).student_ids()

        assert in_old_wing == (current.class_group_id == klass.id)

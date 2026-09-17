"""مشرفُ الجناح: البدلاءُ مشاهدةٌ فقط، والكنترولُ لا شيءَ له فيه (قرارُ المستخدم 2026-09-17).

كانت `operations.reports` تفتح له تسجيلَ غياب المعلّم وتعيينَ بديله — فعلين
كتابيَّين وراء قدرةٍ اسمُها «تقارير» — وتفتح له نظامَ الكنترول كاملاً. والقرارُ:

- البدلاءُ: يقرأ قائمةَ الغيابات وتفاصيلَها وتقريرَي البدلاء والأحمال (بقيت
  `operations.reports`)، ولا يسجّل غياباً ولا يعيّن بديلاً (قدرةٌ جديدة
  `operations.substitutes_manage` تخصّ القيادة والمنسّق وحدَهم).
- الكنترول: أُخرج من `EXAM_CONTROL_ACCESS` تماماً.

المدير مرجعٌ في كلٍّ: يبقى كما كان — يكتب في الأوّل، ويفتح الثاني.
"""

from datetime import date, time

import pytest
from django.urls import reverse

from operations.models import ScheduleSlot, SubstituteAssignment, Subject, TeacherAbsence
from operations.services import SubstituteService
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def subject(school):
    return Subject.objects.create(school=school, name_ar="العلوم", code="SCI")


@pytest.fixture
def absent_teacher(school):
    user = UserFactory(full_name="معلّمٌ غائب")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


@pytest.fixture
def substitute_teacher(school):
    user = UserFactory(full_name="معلّمٌ متفرّغ")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


#: أحدُ الآحاد (يومُ دراسةٍ ثابت) — لا `date.today()`: الجمعةُ والسبتُ بلا
#: حصص، و`SubstituteService._date_to_day` يردّهما -1 فيختفي كلُّ شيءٍ يوم
#: اختبارٍ يقع فيهما.
ABSENCE_DATE = date(2026, 9, 20)


@pytest.fixture
def schedule_slot(school, class_group, absent_teacher, subject):
    return ScheduleSlot.objects.create(
        school=school,
        class_group=class_group,
        teacher=absent_teacher,
        subject=subject,
        day_of_week=SubstituteService._date_to_day(ABSENCE_DATE),
        period_number=1,
        start_time=time(7, 30),
        end_time=time(8, 15),
    )


@pytest.fixture
def absence(school, absent_teacher, principal_user):
    return TeacherAbsence.objects.create(
        school=school,
        teacher=absent_teacher,
        date=ABSENCE_DATE,
        reason="مرض",
        reported_by=principal_user,
    )


class TestSubstitutesAreViewOnlyForTheSupervisor:
    def test_the_register_button_hides_for_him_and_shows_for_the_principal(
        self, client_as, admin_supervisor_user, principal_user
    ):
        supervisor_body = client_as(admin_supervisor_user).get("/teacher/absences/").content.decode()
        principal_body = client_as(principal_user).get("/teacher/absences/").content.decode()

        assert "تسجيل غياب" not in supervisor_body
        assert "تسجيل غياب" in principal_body

    def test_he_cannot_open_or_post_the_registration_form(self, client_as, admin_supervisor_user):
        client = client_as(admin_supervisor_user)

        assert client.get("/teacher/absences/register/").status_code in (302, 403)
        resp = client.post(
            "/teacher/absences/register/",
            {"teacher": "x", "date": date.today().isoformat(), "reason": "مرض"},
        )
        assert resp.status_code in (302, 403)

    def test_the_assign_form_hides_behind_an_unassigned_chip(
        self, client_as, admin_supervisor_user, principal_user, absence, schedule_slot
    ):
        supervisor_body = (
            client_as(admin_supervisor_user).get(f"/teacher/absences/{absence.id}/").content.decode()
        )
        principal_body = (
            client_as(principal_user).get(f"/teacher/absences/{absence.id}/").content.decode()
        )

        assert 'class="slot-assign"' not in supervisor_body
        assert "لم يُعيَّن بديل" in supervisor_body
        assert 'class="slot-assign"' in principal_body

    def test_he_cannot_assign_a_substitute(
        self, client_as, admin_supervisor_user, absence, schedule_slot, substitute_teacher
    ):
        resp = client_as(admin_supervisor_user).post(
            reverse("assign_substitute", args=[absence.id, schedule_slot.id]),
            {"substitute": str(substitute_teacher.id)},
        )

        assert resp.status_code in (302, 403)
        assert not SubstituteAssignment.objects.filter(absence=absence, slot=schedule_slot).exists()

    def test_the_principal_still_assigns_as_before(
        self, client_as, principal_user, absence, schedule_slot, substitute_teacher
    ):
        resp = client_as(principal_user).post(
            reverse("assign_substitute", args=[absence.id, schedule_slot.id]),
            {"substitute": str(substitute_teacher.id)},
        )

        assert resp.status_code == 200
        assert SubstituteAssignment.objects.filter(
            absence=absence, slot=schedule_slot, substitute=substitute_teacher
        ).exists()

    def test_he_still_reads_both_reports(self, client_as, admin_supervisor_user):
        client = client_as(admin_supervisor_user)

        assert client.get("/teacher/reports/substitutes/").status_code == 200
        assert client.get("/teacher/reports/teacher-load/").status_code == 200


class TestExamControlHasNothingForTheSupervisor:
    def test_he_is_refused_the_dashboard(self, client_as, admin_supervisor_user):
        resp = client_as(admin_supervisor_user).get("/exam-control/")
        assert resp.status_code in (302, 403)

    def test_the_principal_still_opens_it(self, client_as, principal_user):
        resp = client_as(principal_user).get("/exam-control/")
        assert resp.status_code == 200

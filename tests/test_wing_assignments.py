"""سجلُّ تعيينات الأجنحة — مشرفٌ وميدانيٌّ بسجلٍّ زمنيّ (W-20261119-001، المرحلةُ 1 من 4).

الأثر: التعيينُ الجديد يغلق السابقَ ولا يحذفه فيُقرأ من حمل الجناحَ يومَ الماضي؛ والمعيَّنُ
ملاحظاً أو ميدانيّاً يرث صلاحيّاتِ جناحه بالتعيين لا بالدور (التحرّكاتُ وتغييرُ الوجهة) ولا يصوّت
في لجنة السلوك؛ والقاعدةُ ترفض دورين في جناحٍ أو الدورَ نفسَه في جناحين؛ والنسخُ من
`Wing.supervisor` لا يتكرّر.
"""

import datetime as dt
import importlib

import pytest
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from behavior.committee_services import case_supervisor_id, eligible_member_ids, may_act_on
from core.academic_calendar import academic_year_for_school
from core.models import AuditLog, Wing, WingAssignment, WingCoverage
from operations.class_exit import may_record_school_exit
from tests.conftest import BehaviorInfractionFactory, MembershipFactory, RoleFactory, UserFactory
from tests.test_period_register import klass, supervisor, teacher, year  # noqa: F401
from tests.test_supervisor_behavior_scope import mine  # noqa: F401
from wings.assignment_services import assign_wing_role

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

SUP = "wing_supervisor"
FIELD = "field_supervisor"


def _staff(school, role, national_id):
    user = UserFactory(full_name=f"موظف {role}", national_id=national_id)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


@pytest.fixture
def wings(school):
    year_ = academic_year_for_school(school)
    return [
        Wing.objects.create(school=school, code=f"a{i}", name=f"جناح {i}", academic_year=year_)
        for i in (1, 2)
    ]


@pytest.fixture
def boss(school):
    return _staff(school, "principal", "29000000001")


class TestHistory:
    def test_a_new_assignment_closes_the_previous_and_the_past_keeps_its_holder(
        self, school, wings, boss
    ):
        first = _staff(school, "admin_supervisor", "29000000002")
        second = _staff(school, "student_observer", "29000000003")
        today = timezone.localdate()
        past = today - dt.timedelta(days=10)
        assign_wing_role(wing=wings[0], role=SUP, user=first, by=boss, start_date=past)
        assign_wing_role(wing=wings[0], role=SUP, user=second, by=boss, start_date=today)

        wing = Wing.objects.get(pk=wings[0].pk)
        assert wing.current_supervisor(past) == first
        assert wing.current_supervisor(today - dt.timedelta(days=1)) == first
        assert wing.current_supervisor(today) == second
        closed = WingAssignment.objects.get(user=first)
        assert closed.end_date == today - dt.timedelta(days=1)
        assert closed.ended_by == boss  # أُغلق ولم يُحذف
        assert AuditLog.objects.filter(user=boss, object_repr__contains="تعيين").count() == 2

    def test_the_coverage_sits_above_the_assignment_and_holders_returns_both(
        self, school, wings, boss
    ):
        owner = _staff(school, "admin_supervisor", "29000000002")
        field = _staff(school, "student_observer", "29000000003")
        spare = _staff(school, "admin_supervisor", "29000000004")
        today = timezone.localdate()
        assign_wing_role(wing=wings[0], role=SUP, user=owner, by=boss, start_date=today)
        assign_wing_role(wing=wings[0], role=FIELD, user=field, by=boss, start_date=today)
        wing = Wing.objects.get(pk=wings[0].pk)
        assert tuple(wing.holders(today)) == (owner, field)
        WingCoverage.objects.create(wing=wing, substitute=spare, start_date=today)
        wing = Wing.objects.get(pk=wings[0].pk)
        assert wing.current_supervisor(today) == spare
        assert wing.holders(today).field == field

    def test_before_any_assignment_the_legacy_supervisor_still_holds(self, school, wings, boss):
        legacy = _staff(school, "admin_supervisor", "29000000002")
        Wing.objects.filter(pk=wings[0].pk).update(supervisor=legacy)
        assert Wing.objects.get(pk=wings[0].pk).current_supervisor() == legacy
        assert Wing.is_held_by(legacy)


class TestRules:
    def test_one_person_cannot_hold_two_roles_in_the_same_wing(self, school, wings, boss):
        person = _staff(school, "admin_supervisor", "29000000002")
        today = timezone.localdate()
        assign_wing_role(wing=wings[0], role=SUP, user=person, by=boss, start_date=today)
        with pytest.raises(ValidationError):
            assign_wing_role(wing=wings[0], role=FIELD, user=person, by=boss, start_date=today)

    def test_one_person_cannot_hold_the_same_role_in_two_wings(self, school, wings, boss):
        person = _staff(school, "admin_supervisor", "29000000002")
        today = timezone.localdate()
        assign_wing_role(wing=wings[0], role=SUP, user=person, by=boss, start_date=today)
        with pytest.raises(ValidationError):
            assign_wing_role(wing=wings[1], role=SUP, user=person, by=boss, start_date=today)

    def test_two_different_roles_in_two_different_wings_are_allowed(self, school, wings, boss):
        person = _staff(school, "admin_supervisor", "29000000002")
        today = timezone.localdate()
        assign_wing_role(wing=wings[0], role=SUP, user=person, by=boss, start_date=today)
        assign_wing_role(wing=wings[1], role=FIELD, user=person, by=boss, start_date=today)
        assert Wing.is_held_by(person)

    def test_the_database_refuses_what_clean_would_miss(self, school, wings, boss):
        person = _staff(school, "admin_supervisor", "29000000002")
        today = timezone.localdate()
        assign_wing_role(wing=wings[0], role=SUP, user=person, by=boss, start_date=today)
        with pytest.raises(IntegrityError), transaction.atomic():
            WingAssignment.objects.create(
                wing=wings[1], role=SUP, user=person, start_date=today, assigned_by=boss
            )

    def test_only_eligible_roles_are_assignable(self, school, wings, boss):
        teacher_ = _staff(school, "teacher", "29000000002")
        with pytest.raises(ValidationError):
            assign_wing_role(
                wing=wings[0], role=SUP, user=teacher_, by=boss, start_date=timezone.localdate()
            )


class TestInheritedPowers:
    def test_an_assigned_observer_opens_the_movements_board_an_unassigned_one_is_refused(
        self, client_as, school, wings, boss
    ):
        observer = _staff(school, "student_observer", "29000000002")
        stranger = _staff(school, "student_observer", "29000000003")
        url = reverse("student_affairs:movements_live")
        assert client_as(stranger).get(url).status_code in (302, 403)
        assign_wing_role(
            wing=wings[0], role=FIELD, user=observer, by=boss, start_date=timezone.localdate()
        )
        assert client_as(observer).get(url).status_code == 200
        assert may_record_school_exit(observer)
        assert not may_record_school_exit(stranger)

    def test_an_assigned_observer_gets_his_wing_only(self, school, wings, boss):
        from wings.services import wings_of

        observer = _staff(school, "student_observer", "29000000002")
        assign_wing_role(
            wing=wings[0], role=SUP, user=observer, by=boss, start_date=timezone.localdate()
        )
        got = wings_of(observer, school, academic_year_for_school(school))
        assert [w.pk for w in got] == [wings[0].pk]

    def test_the_assigned_do_not_vote_in_the_behavior_committee(
        self,
        school,
        seeded_calendar,
        mine,
        supervisor,
        teacher,
        klass,
        boss,  # noqa: F811
    ):
        observer = _staff(school, "student_observer", "29000000002")
        field = _staff(school, "student_observer", "29000000003")
        wing = klass.wing
        today = timezone.localdate()
        assign_wing_role(wing=wing, role=SUP, user=observer, by=boss, start_date=today)
        assign_wing_role(wing=wing, role=FIELD, user=field, by=boss, start_date=today)
        case = BehaviorInfractionFactory(school=school, student=mine, reported_by=teacher, level=3)
        assert case_supervisor_id(case) is None
        members = eligible_member_ids(school, case)
        assert observer.pk not in members
        assert field.pk not in members
        assert not may_act_on(observer, case)
        assert not may_act_on(field, case)


class TestManagementScreen:
    def test_the_assigner_assigns_and_the_page_lists_it(self, client_as, school, wings, boss):
        person = _staff(school, "admin_supervisor", "29000000002")
        client = client_as(boss)
        response = client.post(
            reverse("wings:management_assign", args=["a1"]),
            {"role": SUP, "user": str(person.pk), "start_date": timezone.localdate().isoformat()},
        )
        assert response.status_code == 302
        assert WingAssignment.objects.filter(user=person, wing__code="a1", role=SUP).exists()
        page = client.get(reverse("wings:management"))
        assert page.status_code == 200
        assert "إدارة الأجنحة" in page.content.decode()

    def test_others_are_refused(self, client_as, school, wings):
        assert client_as(_staff(school, "teacher", "29000000009")).get(
            reverse("wings:management")
        ).status_code in (302, 403)
        assert client_as(_staff(school, "vice_academic", "29000000008")).get(
            reverse("wings:management")
        ).status_code in (302, 403)


class TestMigrationCopy:
    def test_copying_twice_does_not_duplicate(self, school, wings):
        owner = _staff(school, "admin_supervisor", "29000000002")
        Wing.objects.filter(pk=wings[0].pk).update(supervisor=owner)
        module = importlib.import_module("core.migrations.0087_wing_assignment")
        module.copy_supervisors(apps, None)
        module.copy_supervisors(apps, None)
        assert WingAssignment.objects.filter(user=owner, role=SUP).count() == 1
        assert WingCoverage._meta.get_field("role").default == SUP

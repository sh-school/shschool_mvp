"""تعديلُ مخالفةٍ مسجَّلة من ملفّ الطالب مع سجلّ تدقيق (بلاغ 5D5D، W-20261111-005).

القرار (المالك 2026-11-11): من سجّل المخالفةَ يعدّلها؛ ومشرفُ الجناح لطلبة جناحه وحدَهم؛ ومعهم
منسّقُ شؤون الطلبة والنائبُ الإداريّ والمديرُ والأخصائيّان — ولا أحدَ غيرُهم (ليس منهم vice_academic).
"""

import pytest
from django.urls import reverse

from behavior.models import BehaviorInfraction, ViolationCategory
from core.models import AuditLog, Wing
from tests.conftest import (
    BehaviorInfractionFactory,
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    SchoolFactory,
    StudentEnrollmentFactory,
    UserFactory,
)
from tests.test_period_register import klass, supervisor, teacher, year  # noqa: F401

pytestmark = pytest.mark.django_db

_DAY = "2026-01-05"


def _staff(school, role):
    user = UserFactory(full_name=f"موظف {role}")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


def _student(school, group):
    user = UserFactory(full_name="طالب التعديل")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="student"))
    StudentEnrollmentFactory(student=user, class_group=group)
    return user


@pytest.fixture
def mine(school, seeded_calendar, klass, supervisor):  # noqa: F811
    return _student(school, klass)


@pytest.fixture
def theirs(school, seeded_calendar, year):  # noqa: F811
    wing = Wing.objects.create(school=school, code="w2", name="جناح 2", academic_year=year)
    group = ClassGroupFactory(
        school=school, grade="G8", section="2", level_type="prep", academic_year=year, wing=wing
    )
    return _student(school, group)


@pytest.fixture
def category():
    return ViolationCategory.objects.create(
        degree=1, code="1-1", name_ar="مخالفة بسيطة", category="A"
    )


@pytest.fixture
def infraction(school, mine, teacher):  # noqa: F811
    return BehaviorInfractionFactory(
        school=school,
        student=mine,
        reported_by=teacher,
        description="وصفٌ أوّل",
        disciplinary_action_type="verbal_warning",
    )


def _payload(**over):
    data = {
        "description": "وصفٌ بعد التعديل",
        "disciplinary_action_type": "verbal_warning",
        "date": _DAY,
        "violation_category": "",
        "violation_description": "",
    }
    data.update(over)
    return data


def _edit(client, infraction, **over):
    url = reverse("behavior:infraction_edit", kwargs={"infraction_id": infraction.pk})
    return client.post(url, _payload(**over))


class TestWhoMayEdit:
    @pytest.mark.parametrize(
        "role",
        ["principal", "vice_admin", "student_affairs_coordinator", "social_worker", "psychologist"],
    )
    def test_each_listed_role_edits(self, client_as, school, infraction, role):
        resp = _edit(client_as(_staff(school, role)), infraction)
        assert resp.status_code == 302
        infraction.refresh_from_db()
        assert infraction.description == "وصفٌ بعد التعديل"
        assert str(infraction.date) == _DAY

    def test_the_wing_supervisor_edits_his_wing(self, client_as, infraction, supervisor):  # noqa: F811
        assert _edit(client_as(supervisor), infraction).status_code == 302
        infraction.refresh_from_db()
        assert infraction.description == "وصفٌ بعد التعديل"

    def test_the_reporter_edits_even_outside_the_list(self, client_as, infraction, teacher):  # noqa: F811
        assert _edit(client_as(teacher), infraction).status_code == 302
        infraction.refresh_from_db()
        assert infraction.description == "وصفٌ بعد التعديل"

    @pytest.mark.parametrize("role", ["vice_academic", "teacher"])
    def test_others_are_refused(self, client_as, school, infraction, role):
        resp = _edit(client_as(_staff(school, role)), infraction)
        assert resp.status_code == 403
        infraction.refresh_from_db()
        assert infraction.description == "وصفٌ أوّل"

    def test_the_supervisor_is_refused_outside_his_wing(
        self,
        client_as,
        school,
        theirs,
        supervisor,  # noqa: F811
        teacher,  # noqa: F811
    ):
        other = BehaviorInfractionFactory(school=school, student=theirs, reported_by=teacher)
        assert _edit(client_as(supervisor), other).status_code == 403
        other.refresh_from_db()
        assert other.description != "وصفٌ بعد التعديل"

    def test_another_school_is_404(self, client_as, infraction):
        outsider_school = SchoolFactory()
        outsider = _staff(outsider_school, "principal")
        assert _edit(client_as(outsider), infraction).status_code == 404


class TestActionLimits:
    def test_an_action_outside_the_role_limits_is_refused(
        self,
        client_as,
        infraction,
        supervisor,  # noqa: F811
    ):
        resp = _edit(client_as(supervisor), infraction, disciplinary_action_type="written_pledge")
        assert resp.status_code == 200
        infraction.refresh_from_db()
        assert infraction.disciplinary_action_type == "verbal_warning"
        assert infraction.description == "وصفٌ أوّل"

    def test_an_action_inside_the_limits_passes(
        self,
        client_as,
        infraction,
        supervisor,  # noqa: F811
    ):
        _edit(
            client_as(supervisor), infraction, disciplinary_action_type="social_specialist_referral"
        )
        infraction.refresh_from_db()
        assert infraction.disciplinary_action_type == "social_specialist_referral"
        assert infraction.action_taken == "تحويل للأخصائي الاجتماعي"


class TestAuditAndLevel:
    def test_the_edit_is_audited_with_before_and_after(
        self, client_as, school, infraction, category
    ):
        boss = _staff(school, "principal")
        _edit(client_as(boss), infraction, violation_category=str(category.pk))
        # إشارةُ التدقيق العامّة تكتب صفّها أيضًا؛ فنحدّد صفَّ الخدمة بوصفه
        row = AuditLog.objects.get(
            action="update",
            model_name="BehaviorInfraction",
            object_id=str(infraction.pk),
            object_repr="مخالفة سلوكية — تعديل",
        )
        assert row.user == boss
        assert row.changes["violation_category"] == {"before": "", "after": "1-1"}
        assert row.changes["date"]["after"] == _DAY
        assert row.changes["description"] == {
            "before": len("وصفٌ أوّل"),
            "after": len("وصفٌ بعد التعديل"),
        }
        assert "disciplinary_action_type" not in row.changes

    def test_a_decided_committee_case_keeps_its_level(
        self,
        client_as,
        school,
        mine,
        teacher,
        category,  # noqa: F811
    ):
        decided = BehaviorInfractionFactory(
            school=school,
            student=mine,
            reported_by=teacher,
            level=3,
            is_resolved=True,
            description="قضية محسومة",
            disciplinary_action_type="verbal_warning",
        )
        boss = _staff(school, "principal")
        _edit(client_as(boss), decided, violation_category=str(category.pk))
        decided = BehaviorInfraction.objects.get(pk=decided.pk)
        assert decided.level == 3
        assert decided.violation_category_id is None
        assert decided.description == "قضية محسومة"

    def test_an_undecided_case_follows_the_category_degree(
        self, client_as, school, infraction, category
    ):
        BehaviorInfraction.objects.filter(pk=infraction.pk).update(level=2)
        _edit(
            client_as(_staff(school, "principal")), infraction, violation_category=str(category.pk)
        )
        infraction.refresh_from_db()
        assert infraction.level == 1


class TestProfileLink:
    def _links(self, client, student):
        resp = client.get(reverse("behavior:student_profile", kwargs={"student_id": student.pk}))
        assert resp.status_code == 200
        return resp.content.decode()

    def test_the_edit_link_shows_only_to_those_who_may(
        self,
        client_as,
        school,
        mine,
        infraction,
        teacher,  # noqa: F811
    ):
        url = reverse("behavior:infraction_edit", kwargs={"infraction_id": infraction.pk})
        assert url in self._links(client_as(_staff(school, "principal")), mine)
        # معلّمٌ لا يبلغ ملفَّ هذا الطالب (ليس من طلابه) فلا يصل إلى الرابط أصلًا
        assert (
            client_as(teacher)
            .get(reverse("behavior:student_profile", kwargs={"student_id": mine.pk}))
            .status_code
            == 403
        )
        assert url in self._links(client_as(_staff(school, "vice_admin")), mine)
        vice = _staff(school, "vice_academic")
        assert url not in self._links(client_as(vice), mine)

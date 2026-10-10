"""اطّلاعٌ على تفضيلات المعلّمين — W-20261010-026 (قرار المالك D-330م).

المديرُ والنائبُ الأكاديميّ يريان المدرسةَ، ومنسّقُ المادّة قسمَه، وغيرُهم يُمنع؛
والصفحةُ قراءةٌ فقط، و`schedule.preferences` لم تُوسَّع.
"""

import pytest
from django.urls import reverse

from core.models import Department
from operations.models import TeacherPreference
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

YEAR = "2026-2027"
URL_NAME = "teacher_preferences_overview"


def _member(school, role, name, department=None):
    user = UserFactory(full_name=name)
    MembershipFactory(
        user=user,
        school=school,
        role=RoleFactory(school=school, name=role),
        department_obj=department,
    )
    return user


def _pref(school, teacher, **kw):
    return TeacherPreference.objects.create(
        teacher=teacher, school=school, academic_year=YEAR, **kw
    )


@pytest.fixture
def world(school):
    math = Department.objects.create(school=school, name="الرياضيات", code="math")
    science = Department.objects.create(school=school, name="العلوم", code="science")
    t_math = _member(school, "teacher", "معلّم رياضيات", math)
    t_sci = _member(school, "teacher", "معلّم علوم", science)
    _pref(school, t_math, max_daily_periods=4, notes="ملاحظة الرياضيات", max_last_periods=3)
    _pref(school, t_sci, max_daily_periods=5, free_day=2)
    return {
        "math": math,
        "coordinator": _member(school, "coordinator", "منسّق الرياضيات", math),
        "no_dept": _member(school, "coordinator", "منسّق بلا قسم"),
        "principal": _member(school, "principal", "المدير"),
        "vice": _member(school, "vice_academic", "النائب الأكاديمي"),
    }


def _get(client_as, user):
    return client_as(user).get(reverse(URL_NAME) + f"?year={YEAR}")


@pytest.mark.django_db
class TestWhoSees:
    @pytest.mark.parametrize("who", ("principal", "vice"))
    def test_leadership_sees_every_teacher(self, client_as, world, who):
        resp = _get(client_as, world[who])
        assert resp.status_code == 200
        body = resp.content.decode()
        assert "معلّم رياضيات" in body and "معلّم علوم" in body

    def test_the_coordinator_sees_only_his_department(self, client_as, world):
        resp = _get(client_as, world["coordinator"])
        body = resp.content.decode()
        assert resp.status_code == 200
        assert "معلّم رياضيات" in body
        assert "معلّم علوم" not in body  # لا يتسرّب اسمُ معلّمٍ من قسمٍ آخر

    def test_a_coordinator_without_a_department_is_refused_and_logged(self, client_as, world):
        from core.models import AuditLog

        resp = _get(client_as, world["no_dept"])
        assert resp.status_code == 403
        assert AuditLog.objects.filter(
            user=world["no_dept"], object_repr__contains="no_department"
        ).exists()

    @pytest.mark.parametrize(
        "role",
        (
            "teacher",
            "ese_teacher",
            "vice_admin",
            "admin_supervisor",
            "secretary",
            "student_affairs_coordinator",
        ),
    )
    def test_other_roles_are_refused(self, client_as, school, world, role):
        assert _get(client_as, _member(school, role, f"مستخدم {role}")).status_code == 403


@pytest.mark.django_db
class TestReadOnly:
    def test_post_is_refused_and_nothing_changes(self, client_as, world):
        client = client_as(world["principal"])
        before = list(TeacherPreference.objects.values_list("id", "max_daily_periods", "notes"))
        assert client.post(reverse(URL_NAME), {"max_daily_periods": 1}).status_code == 405
        assert before == list(
            TeacherPreference.objects.values_list("id", "max_daily_periods", "notes")
        )

    def test_the_page_has_no_form(self, client_as, world):
        body = _get(client_as, world["principal"]).content.decode()
        table = body[body.index("<table") : body.index("</table>")]
        assert "<input" not in table and "<select" not in table and "<textarea" not in table
        assert 'name="max_daily_periods"' not in body

    def test_the_capability_did_not_widen_the_edit_one(self, world):
        from core.capabilities import capability

        # المدير يمرّ من كلّ فحصٍ بطبيعة دوره، فيُقاس السجلُّ نفسُه لا نتيجتُه.
        assert capability("schedule.preferences").roles == frozenset(
            {
                "teacher",
                "ese_teacher",
                "coordinator",
                "activities_coordinator",
                "e_projects_coordinator",
            }
        )
        assert capability("schedule.preferences_view").roles == frozenset(
            {"principal", "vice_academic", "coordinator"}
        )


@pytest.mark.django_db
class TestLastPeriodsCap:
    def test_only_the_principal_sees_the_administrative_cap(self, client_as, world):
        assert "أقصى سابعات" in _get(client_as, world["principal"]).content.decode()
        assert "أقصى سابعات" not in _get(client_as, world["vice"]).content.decode()
        assert "أقصى سابعات" not in _get(client_as, world["coordinator"]).content.decode()


@pytest.mark.django_db
def test_queries_do_not_grow_with_teachers(client_as, school, world, django_assert_max_num_queries):
    for i in range(12):
        t = _member(school, "teacher", f"معلّم إضافي {i}")
        _pref(school, t)
    client = client_as(world["principal"])
    with django_assert_max_num_queries(40):
        assert client.get(reverse(URL_NAME) + f"?year={YEAR}").status_code == 200

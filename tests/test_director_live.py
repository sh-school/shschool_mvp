"""[DASHBOARD] نقطةُ الاستطلاع الحيّ للمدير وصفحتُه (W-20261008-004، D-249م القسم 9).

العقد: JSON بحقل `schema` بلا أسماء، مخزَّنٌ 20 ث في ذاكرةٍ مشتركة، 403 لغير المدير، `no-store`. والصفحةُ تُرسم أرقاماً ورابطاً لا أسماء (D-171م).
"""

import json

import pytest
from django.core.cache import cache

from operations import day_selectors as day_summary
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.conftest import MembershipFactory, RoleFactory, StudentEnrollmentFactory, UserFactory

pytestmark = pytest.mark.django_db

URL = "/teacher/director-live/"


def _user(school, role, name="مستخدم اللوحة"):
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def test_a_principal_gets_a_json_snapshot_with_the_contract(client_as, school):
    response = client_as(_user(school, "principal")).get(URL)

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    assert "Cookie" in response["Vary"]
    data = response.json()
    assert data["schema"] == 1
    assert data["next_in"] == day_summary.LIVE_NEXT_IN
    assert data["phase"] in ("live", "final", "closed")
    assert {"headline", "absent_unexcused", "pending"} <= set(data["school"])


def test_other_roles_get_403_and_anonymous_is_sent_to_login(client_as, client, school):
    assert client_as(_user(school, "teacher")).get(URL).status_code == 403
    client.logout()
    assert client.get(URL).status_code in (302, 401, 403)


def test_the_summary_is_computed_once_for_many_requests_inside_the_shared_cache(
    client_as, school, monkeypatch
):
    calls = []
    real = day_summary.school_day_summary

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(day_summary, "school_day_summary", counting)
    api = client_as(_user(school, "principal"))

    for _ in range(5):
        assert api.get(URL).status_code == 200

    assert len(calls) == 1


def test_the_payload_and_the_page_carry_no_student_names(client_as, school, klass, kid):
    api = client_as(_user(school, "principal"))

    payload = json.dumps(api.get(URL).json(), ensure_ascii=False)
    page = api.get("/dashboard/").content.decode()

    assert kid.full_name not in payload
    assert kid.full_name not in page
    assert "data-director-live" in page or "لا دوامَ اليوم" in page
    assert StudentEnrollmentFactory is not None

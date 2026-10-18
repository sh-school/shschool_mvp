"""الاستطلاعُ الحيّ لشبكة الصفّ (W-20261012-015 المرحلة 1، D-410م): العقدُ، والصلاحيّةُ قبل الذاكرة، والاشتراكُ بالنطاق، وثباتُ الاستعلامات، وبلا أسماء.

يعيد استعمالَ أدوات `test_class_grid.py` (الساعةُ المثبَّتة والشعبةُ المُسنَدة) فلا يعتمد على ساعة التشغيل.
"""

import json

import pytest
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from operations.services import class_grid_live
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.test_class_grid import (  # noqa: F401
    _cells,
    _grid_on,
    _save,
    assigned,
    clock,
    kids,
    subject,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def _url(klass):
    return reverse("class_grid_live", args=[klass.id])


def test_the_contract_is_json_without_names_and_not_cacheable(
    client_as, assigned, teacher, kids, clock
):
    client = client_as(teacher)
    _save(client, assigned, 1, [_cells(kids[0], "absent")])

    response = client.get(_url(assigned))

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    assert "Cookie" in response["Vary"]
    data = response.json()
    assert data["schema"] == class_grid_live.LIVE_SCHEMA
    assert data["next_in"] == 60
    assert data["phase"] == "live"
    assert set(data) == {"schema", "next_in", "phase", "day", "generated_at", "cells"}
    assert data["cells"] == [
        {"c": 1, "s": str(kids[0].pk), "h": data["cells"][0]["h"], "st": "absent"}
    ]
    body = response.content.decode()
    assert all(student.full_name not in body for student in kids)
    assert teacher.full_name not in body


def test_a_stranger_gets_403_and_cannot_read_the_cached_payload(
    client_as, assigned, teacher, kids, clock, school
):
    from tests.conftest import MembershipFactory, RoleFactory, UserFactory

    client_as(teacher).get(_url(assigned))  # يملأ الذاكرةَ المشتركة
    stranger = UserFactory(full_name="غريب")
    MembershipFactory(user=stranger, school=school, role=RoleFactory(school=school, name="teacher"))

    response = client_as(stranger).get(_url(assigned))

    assert response.status_code == 403
    assert "cells" not in response.json()


def test_anonymous_is_sent_to_login(client, assigned):
    client.logout()
    assert client.get(_url(assigned)).status_code in (302, 401, 403)


def test_a_bad_date_is_not_a_server_error(client_as, assigned, teacher, clock):
    assert client_as(teacher).get(_url(assigned) + "?date=bad").status_code == 404


def test_a_second_user_in_the_same_scope_shares_one_computation(
    client_as, assigned, teacher, kids, clock, monkeypatch
):
    calls = []
    real = class_grid_live._compute

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(class_grid_live, "_compute", counting)
    client = client_as(teacher)

    first = client.get(_url(assigned)).json()
    second = client.get(_url(assigned)).json()

    assert len(calls) == 1
    assert first == second


def test_a_save_appears_in_the_next_computation(client_as, assigned, teacher, kids, clock):
    client = client_as(teacher)
    assert client.get(_url(assigned)).json()["cells"] == []
    cache.clear()  # مضيُّ 20 ثانيةً

    _save(client, assigned, 1, [_cells(kids[1], "late")])

    cells = client.get(_url(assigned)).json()["cells"]
    assert [(c["s"], c["st"]) for c in cells] == [(str(kids[1].pk), "late")]


def test_query_count_does_not_grow_with_the_roster(client_as, assigned, teacher, kids, clock):
    client = client_as(teacher)
    _save(client, assigned, 1, [_cells(k, "present") for k in kids])
    cache.clear()
    with CaptureQueriesContext(connection) as small:
        client.get(_url(assigned))

    from core.models import StudentEnrollment
    from tests.attendance_fixtures import ENROLLED
    from tests.conftest import StudentEnrollmentFactory, UserFactory

    for index in range(12):
        student = UserFactory(full_name=f"إضافيّ {index}", national_id=f"2900000300{index:02d}")
        StudentEnrollmentFactory(student=student, class_group=assigned, enrolled_at=ENROLLED)
    assert StudentEnrollment.objects.filter(class_group=assigned).count() == 15
    cache.clear()
    with CaptureQueriesContext(connection) as large:
        client.get(_url(assigned))

    assert len(large) == len(small)


def test_the_phase_becomes_final_after_the_window_closes(client_as, assigned, teacher, kids, clock):
    clock(15, 0)

    assert client_as(teacher).get(_url(assigned)).json()["phase"] == "final"


def test_payload_is_serialisable_and_has_only_ids_codes_and_statuses(
    client_as, assigned, teacher, kids, clock
):
    client = client_as(teacher)
    _save(client, assigned, 1, [_cells(kids[0], "absent"), _cells(kids[2], "present")])

    cell = client.get(_url(assigned)).json()["cells"][0]

    assert set(cell) == {"c", "s", "h", "st"}
    json.dumps(cell)

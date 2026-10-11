"""حصّةٌ فعّالةٌ بلا مادّة لا تُسقط ورقةَ الطباعة ولا صفحاتِ الجدول (W-20261010-038).

`slot.cell_subject|default:slot.subject.name_ar` كان يحلّ `name_ar` وسيطاً قبل الاستدعاء، فتنهار الورقةُ بـ500
(`VariableDoesNotExist`) حين تكون المادّةُ `None`. ثبت على 8500 بدور المدير ونائبه: الطباعةُ وصفحاتُ الجدول (وورقتها).
الجزئيّتان `pdf/week_grid.html` (جدولُ المعلّم والشعبة) و`pdf/matrix_table.html` (الجدولُ العامّ) تقرآن الحقلَ نفسه.
"""

import pytest
from django.urls import reverse

from tests.conftest import MembershipFactory, RoleFactory, UserFactory
from tests.test_week_page import YEAR, _slot, world  # noqa: F401

pytestmark = pytest.mark.django_db

import datetime as dt  # noqa: E402


@pytest.fixture
def vice_admin(school):
    role = RoleFactory(school=school, name="vice_admin")
    user = UserFactory(full_name="نائب الشؤون الإدارية")
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def subjectless(world):  # noqa: F811
    return _slot(world, world["t1"], 2, 3, dt.time(9, 0), dt.time(9, 45), None)


def _get(client, user, name, **params):
    client.force_login(user)
    return client.get(reverse(name), {"year": YEAR, **params}, HTTP_HOST="localhost")


VIEWS = [
    ("schedule_print", {"view": "all_teachers"}),
    ("schedule_print", {"view": "teacher"}),
    ("schedule_pages", {}),
    ("schedule_pages_paper", {}),
    ("weekly_schedule", {"view": "all_teachers"}),
]


@pytest.mark.parametrize(("name", "params"), VIEWS)
@pytest.mark.parametrize("who", ["principal", "vice_admin"])
def test_a_slot_without_a_subject_does_not_break_the_page(
    client,
    world,
    subjectless,
    vice_admin,
    who,
    name,
    params,  # noqa: F811
):
    user = world["principal"] if who == "principal" else vice_admin
    if params.get("view") == "teacher":
        params = {**params, "teacher": str(world["t1"].id)}

    response = _get(client, user, name, **params)

    assert response.status_code == 200, f"{name} {params} ← {response.status_code}"


def test_the_subjectless_cell_shows_a_dash_in_both_partials(client, world, subjectless):  # noqa: F811
    teacher = _get(
        client, world["principal"], "weekly_schedule", view="teacher", teacher=str(world["t1"].id)
    ).content.decode()
    general = _get(
        client, world["principal"], "weekly_schedule", view="all_teachers"
    ).content.decode()

    assert '<div class="slot-subject">—</div>' in teacher
    assert ' data-s="— — ' in general

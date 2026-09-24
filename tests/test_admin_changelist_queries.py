"""قوائمُ الإدارة الثقيلة لا يكبر عددُ استعلاماتها بعدد الصفوف (N+1).

قيس على قاعدة التطوير (1580 عضويّة، 1572 مستخدماً، 48 شعبة): العضويّات 373 استعلاماً، والشُّعب 88،
والمستخدمون 72، والحضورُ والحصصُ والجدولُ وإسنادُ المواد ~40 لكلٍّ منها — سؤالٌ لكلّ صفٍّ في كلّ صفحة.
فالحارسُ لا يثبّت رقماً بعينه (يتغيّر بالقالب والوسيط)، بل يقارن الصفحةَ بصفوفٍ قليلةٍ وبصفوفٍ كثيرة:
إن زاد العددُ مع الصفوف فهذا N+1 عاد.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import ClassGroup, Department
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def superuser(developer_user):
    developer_user.is_staff = developer_user.is_superuser = True
    developer_user.must_change_password = False
    developer_user.save()
    return developer_user


def _count(client, url):
    with CaptureQueriesContext(connection) as queries:
        response = client.get(url)
    assert response.status_code == 200, url
    return len(queries.captured_queries)


def _add_members(school, start, n):
    role = RoleFactory(school=school, name="teacher")
    for i in range(start, start + n):
        department = Department.objects.create(
            school=school,
            name=f"قسم {i}",
            code=f"d{i}",
            head=UserFactory(full_name=f"منسّق {i}"),
            sort_order=i,
        )
        MembershipFactory(user=UserFactory(), school=school, role=role, department_obj=department)


@pytest.mark.parametrize(
    "url_name",
    ["admin:core_membership_changelist", "admin:core_customuser_changelist"],
)
def test_membership_and_user_lists_do_not_query_per_row(client_as, superuser, school, url_name):
    client = client_as(superuser)
    _add_members(school, 0, 2)
    few = _count(client, reverse(url_name))
    _add_members(school, 2, 12)
    many = _count(client, reverse(url_name))
    assert many <= few + 2, f"{url_name}: {few} استعلاماً بصفوفٍ قليلة، {many} بصفوفٍ أكثر — N+1"


def test_class_group_list_does_not_query_per_row(client_as, superuser, school):
    client = client_as(superuser)
    for i in range(2):
        ClassGroupFactory(school=school, section=str(i))
    few = _count(client, reverse("admin:core_classgroup_changelist"))
    for i in range(2, 14):
        ClassGroupFactory(school=school, section=str(i))
    many = _count(client, reverse("admin:core_classgroup_changelist"))
    assert ClassGroup.objects.count() >= 14
    assert many <= few + 2, f"{few} → {many}"


def test_the_department_label_reads_the_prefetched_memberships(client_as, superuser, school):
    """عمودُ «القسم» في قائمة المستخدمين يقرأ العضويّاتِ المجلوبة سلفاً ويعرض القسمَ الصحيح."""
    _add_members(school, 0, 1)
    html = client_as(superuser).get(reverse("admin:core_customuser_changelist")).content.decode()
    assert "قسم 0" in html

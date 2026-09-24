"""حقولُ الجداول المضمَّنة في لوحة الإدارة لها اسمٌ محسوب — axe: label و select-name (حرجان).

اسمُ العمود في `<thead>` لا يربطه المتصفّحُ بالخليّة، فكانت كلُّ خليّةٍ في كلّ جدولٍ مضمَّن (13 في المشروع)
بلا `<label>`. والإصلاحُ مركزيٌّ: `templates/admin/edit_inline/tabular.html` تُضيف تسميةً مخفيّةً بصريّاً.
"""

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from tests.test_a11y_live_pages import unnamed_fields

pytestmark = pytest.mark.django_db


@pytest.fixture
def superuser(developer_user):
    """لوحةُ الإدارة لمن له `is_staff`؛ والمطوّرُ superuser فيها (لا يُقيَّد بمدرسة)."""
    developer_user.is_staff = developer_user.is_superuser = True
    developer_user.must_change_password = False
    developer_user.save()
    return developer_user


def test_the_membership_inline_cells_are_all_named(client_as, superuser, teacher_user):
    html = (
        client_as(superuser)
        .get(reverse("admin:core_customuser_change", args=[teacher_user.pk]))
        .content.decode()
    )
    assert "memberships-0-role" in html, "الجدولُ المضمَّن لم يُرسم"
    missing = [m for m in unnamed_fields(html) if "memberships-" in m]
    assert missing == [], missing


def test_the_delete_checkbox_of_an_existing_row_is_named(client_as, superuser, teacher_user):
    html = (
        client_as(superuser)
        .get(reverse("admin:core_customuser_change", args=[teacher_user.pk]))
        .content.decode()
    )
    assert "memberships-0-DELETE" in html
    assert 'for="id_memberships-0-DELETE"' in html


def test_unrelated_groups_do_not_break_the_page(client_as, superuser, teacher_user):
    Group.objects.create(name="x")
    response = client_as(superuser).get(
        reverse("admin:core_customuser_change", args=[teacher_user.pk])
    )
    assert response.status_code == 200

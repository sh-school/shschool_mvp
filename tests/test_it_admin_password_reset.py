"""إعادةُ تعيين كلمات المرور — نافذةُ فنّي تقنية المعلومات داخل المنصّة لا `/admin/`.

قرارُ المالك 2026-09-22: كلمةٌ عشوائيّةٌ لا حقلَ حرّ، تُعرض مرّةً واحدة، وتُلزم
بالتغيير عند الدخول التالي — ومقيَّدةٌ بمدرسة الفنّي لا بكلّ حسابٍ في المنصّة.
"""

import pytest

from core.models import AuditLog
from tests.conftest import MembershipFactory, RoleFactory, SchoolFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def it_tech(school):
    role = RoleFactory(school=school, name="it_technician")
    user = UserFactory(full_name="فنّي تقنية معلومات")
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def teacher(school):
    role = RoleFactory(school=school, name="teacher")
    user = UserFactory(full_name="معلّم الاختبار")
    MembershipFactory(user=user, school=school, role=role)
    return user


def test_a_teacher_is_refused(client_as, teacher):
    response = client_as(teacher).get("/core/it-admin/password-reset/")
    assert response.status_code == 403


def test_the_it_technician_sees_the_list(client_as, it_tech, teacher):
    response = client_as(it_tech).get("/core/it-admin/password-reset/")
    assert response.status_code == 200
    assert teacher.full_name in response.content.decode()


def test_reset_changes_the_password_and_forces_change_on_next_login(client_as, it_tech, teacher):
    old_hash = teacher.password
    response = client_as(it_tech).post(f"/core/it-admin/password-reset/{teacher.id}/", follow=True)

    teacher.refresh_from_db()
    assert teacher.password != old_hash
    assert teacher.must_change_password is True
    assert response.status_code == 200


def test_reset_is_logged_without_the_password_in_the_audit_trail(client_as, it_tech, teacher):
    client_as(it_tech).post(f"/core/it-admin/password-reset/{teacher.id}/")

    entry = AuditLog.objects.filter(model_name="CustomUser", object_id=str(teacher.id)).latest(
        "timestamp"
    )
    assert entry.action == "update"
    assert teacher.full_name in entry.object_repr
    assert "كلمة" in entry.object_repr


def test_a_get_request_is_refused_on_the_action_endpoint(client_as, it_tech, teacher):
    response = client_as(it_tech).get(f"/core/it-admin/password-reset/{teacher.id}/")
    assert response.status_code == 405


def test_cannot_reset_a_user_from_another_school(client_as, it_tech):
    other_school = SchoolFactory()
    other_role = RoleFactory(school=other_school, name="teacher")
    stranger = UserFactory(full_name="من مدرسةٍ أخرى")
    MembershipFactory(user=stranger, school=other_school, role=other_role)

    response = client_as(it_tech).post(f"/core/it-admin/password-reset/{stranger.id}/")

    assert response.status_code == 404

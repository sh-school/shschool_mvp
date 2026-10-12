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
    # W-20261003-019: لا اسمَ شخصيّاً في سجلٍّ ملحق — المعرّفُ المقنَّع يكفي المدقّقَ.
    assert teacher.full_name not in entry.object_repr
    assert str(teacher.id)[:8] in entry.object_repr
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


# ── البحث: الاسم أو الرقم الوظيفيّ وحدَهما (W-20261012-007، D-386م) ─────────────

URL = "/core/it-admin/password-reset/"


def _staff(school, name, employee_number):
    user = UserFactory(full_name=name, employee_number=employee_number)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


def _found(client_as, it_tech, q):
    response = client_as(it_tech).get(URL, {"q": q})
    assert response.status_code == 200
    return response, [row["full_name"] for row in response.context["rows"]]


def test_the_employee_number_finds_the_employee(client_as, school, it_tech):
    _staff(school, "المقصود", "EMP-48151")
    _staff(school, "غيره", "EMP-99002")

    _response, names = _found(client_as, it_tech, "EMP-48151")

    assert names == ["المقصود"]


def test_a_part_of_the_employee_number_finds_the_employee(client_as, school, it_tech):
    _staff(school, "المقصود", "EMP-48151")

    _response, names = _found(client_as, it_tech, "4815")

    assert names == ["المقصود"]


def test_the_name_search_works_as_before(client_as, school, it_tech):
    _staff(school, "عبدالله الكواري", "EMP-1")
    _staff(school, "سالم المري", "EMP-2")

    _response, names = _found(client_as, it_tech, "الكواري")

    assert names == ["عبدالله الكواري"]


def test_the_personal_number_finds_nobody_whole_or_in_part(client_as, school, it_tech):
    target = _staff(school, "المقصود", "EMP-48151")
    nid = target.national_id

    for q in (nid, nid[:6], nid[-5:]):
        response, names = _found(client_as, it_tech, q)
        assert names == [], q
        # صدى الاستعلام في حقل البحث مقبول؛ المحظور أن يعود بالموظف أو يظهر رقمُه في جدول النتائج.
        assert "المقصود" not in response.content.decode()
    # وبلا استعلامٍ يظهر الموظف في القائمة ولا يظهر رقمه الشخصيّ في الصفحة أبداً.
    response, names = _found(client_as, it_tech, "")
    assert "المقصود" in names
    assert nid not in response.content.decode()


def test_a_single_character_does_not_filter(client_as, school, it_tech):
    """حدٌّ أدنى حرفان: حرفٌ واحد لا يضيّق (فلا يطابق رقمٌ من خانةٍ واحدة الجميع بل يعرض القائمة كاملةً كبلا استعلام)."""
    _staff(school, "ألف", "EMP-1")
    _staff(school, "باء", "EMP-2")

    _response, names = _found(client_as, it_tech, "1")

    assert {"ألف", "باء"} <= set(names)


def test_the_rows_carry_no_personal_number(client_as, school, it_tech):
    _staff(school, "المقصود", "EMP-48151")

    response, _names = _found(client_as, it_tech, "")

    assert all("national_id" not in row for row in response.context["rows"])


def test_the_search_is_still_refused_to_a_teacher(client_as, teacher):
    assert client_as(teacher).get(URL, {"q": "اختبار"}).status_code == 403

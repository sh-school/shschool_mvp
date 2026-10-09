"""[PDPPL] اسمُ وليّ الأمر لمن يحتاجه وحدَه — بلاغ SOS-20261005-09F3 (بطاقة W-20261005-009).

معلّمٌ رأى اسمَ والدة طالبٍ في نافذة تسجيل المخالفة. والتحقيقُ أثبت أنّ «التقرير السلوكي» كان يعرض اسمَ وليّ الأمر
ويُرسل إليه لكلّ من يحمل `behavior.record` (المعلّمُ والمنسّقُ ومنسّقُ الأنشطة والمشاريع)، وهؤلاء يسجّلون ولا يتّصلون.

القاعدة (قاعدةُ الحاجة): الاسمُ لمن يتّصل بالأسرة أو يستدعيها أو يتابع — قدرةُ ``behavior.guardian_contact``:
قيادةٌ وأخصائيٌّ اجتماعيٌّ ومنسّقُ شؤون الطلبة وحاملُ الجناح. وغيرُهم يقرأ «وليّ الأمر مسجَّل» بلا اسم، ولا يُرسل.

ويثبّت الملفُّ القاعدةَ نفسَها على نافذتين أخريين بالدور: سجلُّ الطلبة وملفُّ الطالب. وملفُّ الغياب (قرارُ DPO
2026-09-16) خارج هذا الملفّ، يحرسه ``tests/test_guardian_phone_audit.py``.
لا أسماءَ حقيقيّةً هنا: اسمُ الوليّ علامةٌ مصطنعة تُبحث في الصفحة.
"""

from unittest.mock import patch

import pytest
from django.core import mail
from django.urls import reverse

from core.capabilities import capability, has_capability
from core.models import ParentStudentLink
from tests.conftest import MembershipFactory, RoleFactory, UserFactory
from tests.test_period_register import klass, supervisor, year  # noqa: F401 — جناحٌ ومشرفُه
from tests.test_supervisor_student_affairs_profile import (  # noqa: F401 — طالبُ جناحٍ ثانٍ خارج نطاق المشرف
    _student,
    other_klass,
    outsider,
)

pytestmark = pytest.mark.django_db

#: علامةٌ مصطنعة لا اسمُ شخصٍ حقيقيّ.
GUARDIAN = "وليّ-أمر-اختباري-٧٧"
REGISTERED = "وليّ الأمر مسجَّل"
SEND_FIELD = 'name="action" value="send"'

#: من يبلغ التقريرَ السلوكيّ فعلاً (`behavior.record` ثمّ حارسُه الداخليّ `BehaviorPermissions.can_report`):
#: يتّصل بالأسرة منهم هؤلاء، ويسجّل ولا يتّصل أولئك.
CONTACT_ROLES = ["principal", "vice_admin", "vice_academic", "social_worker", "admin_supervisor"]
RECORD_ONLY_ROLES = ["teacher", "ese_teacher", "coordinator"]
#: يحملون `behavior.record` ويردّهم حارسُ التقرير الداخليُّ أصلاً (سابقٌ لهذه البطاقة) — فلا اسمَ لهم من بابٍ آخر.
REFUSED_BY_REPORT_GUARD = [
    "activities_coordinator",
    "e_projects_coordinator",
    "student_affairs_coordinator",
]
#: من تمنحهم القدرةُ الاتّصالَ بالأسرة (والمنسّقُ يتّصل من شاشات شؤون الطلبة لا من هذا التقرير).
CAPABILITY_CONTACT_ROLES = [*CONTACT_ROLES, "student_affairs_coordinator"]


def _staff(school, role, nid):
    user = UserFactory(full_name=f"موظّف {role}", national_id=nid)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


@pytest.fixture
def child(school, klass, supervisor):
    """طالبٌ في جناح المشرف، لوالدٍ مسجَّل باسم العلامة."""
    student = _student(school, klass, "طالب الاختبار", "29400000055")
    guardian = UserFactory(full_name=GUARDIAN, national_id="29400000066", email="g@example.test")
    ParentStudentLink.objects.create(
        parent=guardian, student=student, school=school, relationship="mother", is_primary=True
    )
    return student


def _user_for(school, role, supervisor, n):
    return supervisor if role == "admin_supervisor" else _staff(school, role, f"2950000{n:04d}")


def _report(client_as, user, child):
    # نطاقُ «طلابُك فقط» له اختباراتُه (test_supervisor_behavior_scope)؛ هنا السؤالُ ما يُعرض لا من يبلغ.
    with patch("behavior.views._deny_unreachable", return_value=None):
        return client_as(user).get(reverse("behavior:behavior_report", args=[child.pk]))


# ══════════════════════════════════════════════════════════════════════
#  1. التقرير السلوكي — النافذةُ التي رآها المعلّم
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("role", CONTACT_ROLES)
def test_the_roles_that_contact_families_see_the_name_and_the_send_option(
    client_as, school, seeded_calendar, supervisor, child, role
):
    user = _user_for(school, role, supervisor, CONTACT_ROLES.index(role))
    response = _report(client_as, user, child)

    assert response.status_code == 200
    html = response.content.decode()
    assert GUARDIAN in html
    assert SEND_FIELD in html


@pytest.mark.parametrize("role", RECORD_ONLY_ROLES)
def test_the_roles_that_only_record_never_see_the_name_but_know_one_is_registered(
    client_as, school, seeded_calendar, supervisor, child, role
):
    user = _user_for(school, role, supervisor, 100 + RECORD_ONLY_ROLES.index(role))
    response = _report(client_as, user, child)

    assert response.status_code == 200
    html = response.content.decode()
    assert GUARDIAN not in html
    assert REGISTERED in html
    assert SEND_FIELD not in html
    assert GUARDIAN not in str(response.context.get("parent_links", ""))


@pytest.mark.parametrize("role", RECORD_ONLY_ROLES)
def test_a_recording_role_cannot_send_the_report_by_posting_it(
    client_as, school, seeded_calendar, supervisor, child, role
):
    user = _user_for(school, role, supervisor, 200 + RECORD_ONLY_ROLES.index(role))
    with patch("behavior.views._deny_unreachable", return_value=None):
        response = client_as(user).post(
            reverse("behavior:behavior_report", args=[child.pk]), {"action": "send"}
        )

    assert response.status_code == 403
    assert mail.outbox == []


@pytest.mark.parametrize("role", REFUSED_BY_REPORT_GUARD)
def test_roles_the_report_guard_already_refuses_see_no_name(
    client_as, school, seeded_calendar, supervisor, child, role
):
    user = _user_for(school, role, supervisor, 150 + REFUSED_BY_REPORT_GUARD.index(role))
    response = _report(client_as, user, child)

    assert response.status_code == 403
    assert GUARDIAN not in response.content.decode()


def test_a_student_with_no_guardian_shows_no_guardian_section_to_anyone(
    client_as, school, seeded_calendar, supervisor, klass
):
    orphan = _student(school, klass, "طالب بلا وليّ", "29400000088")
    teacher = _staff(school, "teacher", "29500009001")

    html = _report(client_as, teacher, orphan).content.decode()

    assert REGISTERED not in html
    assert SEND_FIELD not in html


def test_the_capability_is_exactly_the_contact_roles_among_the_recording_ones(school, supervisor):
    record = capability("behavior.record").expanded_roles
    contact = capability("behavior.guardian_contact").expanded_roles

    assert contact >= set(CAPABILITY_CONTACT_ROLES)
    assert record & contact >= set(CAPABILITY_CONTACT_ROLES)
    assert not (
        set(RECORD_ONLY_ROLES + ["activities_coordinator", "e_projects_coordinator"]) & contact
    )
    # وما لا يسجّل المخالفةَ ولا يتّصل لا يحمل القدرة: المعلّمُ مثلاً.
    assert not has_capability(_staff(school, "teacher", "29500009002"), "behavior.guardian_contact")


# ══════════════════════════════════════════════════════════════════════
#  2. سجلُّ الطلبة وملفُّ الطالب — القاعدةُ نفسُها بالدور (المواصفة)
# ══════════════════════════════════════════════════════════════════════

LIST_ROLES = [
    "principal",
    "vice_admin",
    "vice_academic",
    "student_affairs_coordinator",
    "coordinator",
    "social_worker",
    "psychologist",
    "admin_supervisor",
    # يرث المنسّقَ (`ROLE_INHERITS`) فيفتح السجلَّ بوراثته — قائمٌ قبل هذه البطاقة، رُفع لحكم 0104.
    "activities_coordinator",
]
NOT_LIST_ROLES = ["teacher", "ese_teacher", "e_projects_coordinator"]

PROFILE_ROLES = [
    "principal",
    "vice_admin",
    "vice_academic",
    "student_affairs_coordinator",
    "admin_supervisor",
]
NOT_PROFILE_ROLES = [
    "coordinator",
    "social_worker",
    "psychologist",
    "teacher",
    "ese_teacher",
    "activities_coordinator",
    "e_projects_coordinator",
]


@pytest.mark.parametrize("role", LIST_ROLES)
def test_the_student_register_shows_the_guardian_only_to_the_register_roles(
    client_as, school, seeded_calendar, supervisor, child, role
):
    user = _user_for(school, role, supervisor, 300 + LIST_ROLES.index(role))
    response = client_as(user).get(reverse("student_affairs:student_list"))

    assert response.status_code == 200
    assert GUARDIAN in response.content.decode()


@pytest.mark.parametrize("role", NOT_LIST_ROLES)
def test_the_student_register_is_closed_to_recording_staff(
    client_as, school, seeded_calendar, supervisor, child, role
):
    user = _user_for(school, role, supervisor, 400 + NOT_LIST_ROLES.index(role))
    response = client_as(user).get(reverse("student_affairs:student_list"))

    assert response.status_code == 403
    assert GUARDIAN not in response.content.decode()


@pytest.mark.parametrize("role", PROFILE_ROLES)
def test_the_student_file_shows_the_guardian_only_to_the_follow_up_roles(
    client_as, school, seeded_calendar, supervisor, child, role
):
    user = _user_for(school, role, supervisor, 500 + PROFILE_ROLES.index(role))
    response = client_as(user).get(reverse("student_affairs:student_profile", args=[child.pk]))

    assert response.status_code == 200
    assert GUARDIAN in response.content.decode()


@pytest.mark.parametrize("role", NOT_PROFILE_ROLES)
def test_the_student_file_is_closed_to_everyone_else(
    client_as, school, seeded_calendar, supervisor, child, role
):
    user = _user_for(school, role, supervisor, 600 + NOT_PROFILE_ROLES.index(role))
    response = client_as(user).get(reverse("student_affairs:student_profile", args=[child.pk]))

    assert response.status_code in (403, 404)
    assert GUARDIAN not in response.content.decode()


# ══════════════════════════════════════════════════════════════════════
#  3. الإرسالُ والنطاق (مواصفة 0104)
# ══════════════════════════════════════════════════════════════════════


def test_a_contact_role_sending_the_report_mails_the_guardian_not_the_screen(
    client_as, school, seeded_calendar, supervisor, child
):
    principal = _staff(school, "principal", "29500009010")
    with patch("behavior.views._deny_unreachable", return_value=None):
        client_as(principal).post(
            reverse("behavior:behavior_report", args=[child.pk]), {"action": "send"}
        )

    # الاسمُ في نصّ البريد هو اسمُ مستلمه نفسِه (مخاطبته)؛ لا يُكتب فيه اسمُ غيره.
    assert [m.to for m in mail.outbox] == [["g@example.test"]]


def test_the_wing_supervisor_cannot_open_the_report_of_a_student_outside_his_wing(
    client_as, school, seeded_calendar, supervisor, child, outsider
):
    ParentStudentLink.objects.create(
        parent=UserFactory(full_name=GUARDIAN + "-خارج", national_id="29400000067"),
        student=outsider,
        school=school,
        relationship="father",
    )
    response = client_as(supervisor).get(reverse("behavior:behavior_report", args=[outsider.pk]))

    assert response.status_code == 404
    assert GUARDIAN not in response.content.decode()


def test_a_teacher_cannot_open_the_report_of_a_student_who_is_not_hers(
    client_as, school, seeded_calendar, supervisor, child
):
    teacher = _staff(school, "teacher", "29500009011")
    response = client_as(teacher).get(reverse("behavior:behavior_report", args=[child.pk]))

    assert response.status_code == 403
    assert GUARDIAN not in response.content.decode()


def test_the_supervisor_register_lists_only_his_wing_guardians(
    client_as, school, seeded_calendar, supervisor, child, outsider
):
    ParentStudentLink.objects.create(
        parent=UserFactory(full_name="ولي-خارج-الجناح-٨٨", national_id="29400000068"),
        student=outsider,
        school=school,
        relationship="father",
    )
    html = client_as(supervisor).get(reverse("student_affairs:student_list")).content.decode()

    assert GUARDIAN in html
    assert "ولي-خارج-الجناح-٨٨" not in html

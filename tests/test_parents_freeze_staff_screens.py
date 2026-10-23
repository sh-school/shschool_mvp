"""[PDPPL] تحت تجميد أولياء الأمور لا يرى الطاقمُ اسمَ وليّ الأمر ولا هاتفَه — بلاغ SOS-20261021-09F3 (W-20261021-014).

القرارُ D-268م: «تجميد وإخفاء». كانت القوالبُ لا تقرأ المفتاحَ، فيظهر الاسمُ والهاتفُ لمشرف الجناح وللتقرير السلوكيّ
واستدعاءِ الوليّ. تغطّي الاختباراتُ كلَّ شاشةٍ بدورها في حالتَي التجميد، فبعد الفكّ يعود العرضُ كما قرّره مسؤولُ
الحماية (2026-09-16، docs/privacy/guardian_phones.md). لا أسماءَ حقيقيّةً: علاماتٌ مصطنعة تُبحث في الصفحة.
"""

from unittest.mock import patch

import pytest
from django.urls import reverse

from core.models import AuditLog, ParentStudentLink
from tests.conftest import MembershipFactory, RoleFactory, UserFactory
from tests.test_absence_excuses import _absent_day  # noqa: F401
from tests.test_period_register import (  # noqa: F401
    kids,
    klass,
    subjects,
    supervisor,
    teacher,
    year,
)
from tests.test_supervisor_student_affairs_profile import _student  # noqa: F401

pytestmark = pytest.mark.django_db

NAME = "وليّ-أمر-مجمَّد-٤٢"
PHONE = "55598765"


@pytest.fixture
def guardian(school, kids):
    father = UserFactory(
        full_name=NAME, national_id="29300000099", phone=PHONE, email="g42@example.test"
    )
    MembershipFactory(user=father, school=school, role=RoleFactory(school=school, name="parent"))
    ParentStudentLink.objects.create(
        school=school, parent=father, student=kids[0], relationship="father", is_primary=True
    )
    return father


@pytest.fixture
def child(school, klass, guardian):
    """طالبٌ في جناح المشرف (له عضويّةٌ في المدرسة) ولوليّ الأمر نفسِه."""
    student = _student(school, klass, "طالب الاختبار", "29400000055")
    ParentStudentLink.objects.create(
        school=school, parent=guardian, student=student, relationship="father", is_primary=True
    )
    return student


def _file(client_as, user, kid):
    return client_as(user).get(reverse("wings:absence_file", args=[kid.id])).content.decode()


def _report(client_as, user, kid):
    with patch("behavior.views._deny_unreachable", return_value=None):
        return client_as(user).get(reverse("behavior:behavior_report", args=[kid.pk]))


@pytest.mark.parametrize("frozen", [True, False])
def test_absence_file_hides_the_guardian_only_while_frozen(
    client_as, school, seeded_calendar, klass, kids, teacher, supervisor, guardian, settings, frozen
):
    settings.PARENTS_FROZEN = frozen
    _absent_day(school, klass, kids[0], teacher, supervisor)
    before = AuditLog.objects.filter(action="view", model_name="ParentStudentLink").count()

    html = _file(client_as, supervisor, kids[0])

    assert (NAME in html) is not frozen
    assert (PHONE in html) is not frozen
    # لا عرضَ للهاتف = لا أثرَ قراءةٍ كاذباً في سجلّ التدقيق
    after = AuditLog.objects.filter(action="view", model_name="ParentStudentLink").count()
    assert after - before == (0 if frozen else 1)


@pytest.mark.parametrize("frozen", [True, False])
def test_behavior_report_hides_name_phone_and_send_while_frozen(
    client_as, school, seeded_calendar, supervisor, child, settings, frozen
):
    settings.PARENTS_FROZEN = frozen
    response = _report(client_as, supervisor, child)

    html = response.content.decode()
    assert response.status_code == 200
    assert (NAME in html) is not frozen
    assert (PHONE in html) is not frozen
    assert ('name="action" value="send"' in html) is not frozen


@pytest.mark.parametrize("frozen", [True, False])
def test_summon_parent_screen_hides_the_guardian_while_frozen(
    client_as, school, seeded_calendar, child, settings, frozen
):
    settings.PARENTS_FROZEN = frozen
    vice = UserFactory(full_name="نائبٌ إداريّ", national_id="29000000777")
    MembershipFactory(user=vice, school=school, role=RoleFactory(school=school, name="vice_admin"))
    with patch("behavior.views._require_in_wing", return_value=None):
        response = client_as(vice).get(reverse("behavior:summon_parent_student", args=[child.pk]))

    html = response.content.decode()
    assert response.status_code == 200
    assert (NAME in html) is not frozen
    assert (PHONE in html) is not frozen

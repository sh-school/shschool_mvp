"""من لا جناحَ مُسنَداً له يقرأ سببَه ومن يُراجَع — لا قائمةً فارغةً صامتةً ولا 404 خاماً (W-20261021-015).

بلاغا الصندوق: مشرفا جناحٍ لا يظهر لهما الرصدُ ولا الفصول. والسببُ المحتمل بلا جناحٍ مُسنَدٍ لهما في عام اليوم
أو تكليفُ بديلٍ منتهٍ. ولا تغييرَ في سياسة الوصول (`wings_of`)، وإنّما في الوضوح.
"""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from core.academic_calendar import academic_year_for_school
from core.models import ClassGroup, Wing, WingCoverage
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def on_a_school_day(monkeypatch):
    """الأربعاءُ صباحاً: يومَ الجمعة لا تُعرض الشُّعب (لا دوام)."""
    frozen = timezone.make_aware(dt.datetime(2026, 9, 16, 9, 0))
    monkeypatch.setattr("django.utils.timezone.now", lambda: frozen)


def _staff(school, role, national_id):
    user = UserFactory(full_name=f"حسابُ {role}", national_id=national_id)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


@pytest.fixture
def owner(school):
    return _staff(school, "admin_supervisor", "29400000101")


@pytest.fixture
def principal(school):
    return _staff(school, "principal", "29400000102")


@pytest.fixture
def wing(school, owner):
    return Wing.objects.create(
        school=school,
        code="w4",
        name="جناح 4",
        academic_year=academic_year_for_school(school),
        supervisor=owner,
    )


def test_supervisor_with_a_wing_sees_the_wing_and_no_notice(client_as, wing, owner):
    client = client_as(owner)
    for name in ("wings:record_index", "wings:floors"):
        body = client.get(reverse(name)).content.decode()
        assert "راجع مدير المدرسة" not in body
    assert "جناح 4" in client.get(reverse("wings:record_index")).content.decode()


def test_supervisor_without_a_wing_this_year_is_told_why_and_whom_to_ask(client_as, school, wing):
    other = _staff(school, "admin_supervisor", "29400000103")
    client = client_as(other)

    for name in ("wings:record_index", "wings:floors"):
        resp = client.get(reverse(name))
        assert resp.status_code == 200
        body = resp.content.decode()
        assert "لا جناحَ مُسنَدٌ إليك في العام الدراسيّ" in body
        assert "راجع مدير المدرسة" in body


def test_wing_of_a_previous_year_does_not_count(client_as, school):
    """جناحٌ أصيلُه المستخدمُ لكن لعامٍ آخر لا يُحمل اليوم: الإسنادُ يخصّ العام الحالي."""
    user = _staff(school, "admin_supervisor", "29400000104")
    Wing.objects.create(
        school=school, code="w1", name="جناح قديم", academic_year="2000-2001", supervisor=user
    )
    body = client_as(user).get(reverse("wings:record_index")).content.decode()
    assert "جناح قديم" not in body
    assert "لا جناحَ مُسنَدٌ إليك في العام الدراسيّ" in body


def test_an_ended_substitution_is_named_as_the_reason(client_as, school, wing, principal):
    substitute = _staff(school, "admin_supervisor", "29400000105")
    today = timezone.localdate()
    WingCoverage.objects.create(
        wing=wing,
        substitute=substitute,
        assigned_by=principal,
        start_date=today - dt.timedelta(days=5),
        end_date=today - dt.timedelta(days=1),
    )
    body = client_as(substitute).get(reverse("wings:record_index")).content.decode()
    assert "انتهى تكليفُك بديلاً لجناحٍ" in body
    assert "راجع مدير المدرسة" in body


def test_class_link_without_a_wing_redirects_with_the_reason_not_a_raw_404(client_as, school, wing):
    other = _staff(school, "admin_supervisor", "29400000106")
    klass = ClassGroup.objects.create(
        school=school,
        grade="G7",
        section="أ1",
        level_type="prep",
        academic_year=academic_year_for_school(school),
        wing=wing,
    )
    client = client_as(other)
    resp = client.get(reverse("wings:record_section", args=[klass.id]), follow=True)
    assert resp.status_code == 200
    assert "راجع مدير المدرسة" in resp.content.decode()


def test_leadership_is_never_given_the_notice(client_as, wing, principal):
    for name in ("wings:floors",):
        assert "راجع مدير المدرسة" not in client_as(principal).get(reverse(name)).content.decode()

"""بوّابةُ موافقة وليّ الأمر — والكادرُ الذي هو وليُّ أمرٍ لا يُحجب عن عمله.

قرارُ المالك (2026-09-16):
- وليُّ الأمر الخالص باقٍ على حاله حرفاً: كلُّ مسارٍ غيرِ مستثنى يُحوَّل إلى الموافقة
  (أو ٤٠٣ ``consent_required`` في ``/api/``).
- الكادرُ الذي له عضويّةُ وليّ أمرٍ ولم يوافق يبلغ شاشاتِ عمله مباشرةً، وتظهر له
  صفحةُ الموافقة عند شاشات وليّ الأمر وحدَها.
- «بوابتي» تُفتح لكلّ كادرٍ له عضويّةُ وليّ أمر، ولا تعرض إلّا أبناءه.

وكان المعلّمُ الذي هو وليُّ أمرٍ محبوساً خارج المنصّة كلِّها: يُحوَّل إلى صفحة الموافقة،
وصفحةُ الموافقة تحت ``/parents/`` التي تردّه بدوره الحاكم.
"""

from unittest import mock

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.views import APIView

from api.permissions import IsParentOrAdmin
from core.models import ParentStudentLink
from core.parent_consent import (
    consent_blocks,
    holds_parent_membership,
    is_parent_facing,
    needs_parent_consent,
)
from tests.conftest import (
    BookBorrowingFactory,
    LibraryBookFactory,
    MembershipFactory,
    RoleFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

CONSENT_URL = "/parents/consent/"


def _member(school, *role_names, consent=False):
    user = UserFactory()
    for name in role_names:
        MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=name))
    if consent:
        user.consent_given_at = timezone.now()
        user.save(update_fields=["consent_given_at"])
    return user


def _child(school, name="ابن الموظف"):
    kid = UserFactory(full_name=name)
    MembershipFactory(user=kid, school=school, role=RoleFactory(school=school, name="student"))
    return kid


def _staff_parent(school, role_name, child):
    """كادرٌ بدوره ووليُّ أمرٍ مرتبطٌ بـ``child`` — ولم يوافق بعد."""
    user = _member(school, role_name, "parent")
    ParentStudentLink.objects.create(parent=user, student=child, school=school)
    return user


def _client(user):
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def pure_parent(parent_user):
    parent_user.consent_given_at = None
    parent_user.save(update_fields=["consent_given_at"])
    return parent_user


@pytest.fixture
def kid(school):
    return _child(school)


@pytest.fixture
def teacher_parent(school, kid):
    return _staff_parent(school, "teacher", kid)


@pytest.fixture
def vice_admin_parent(school, kid):
    return _staff_parent(school, "vice_admin", kid)


@pytest.fixture
def principal_parent(school, kid):
    return _staff_parent(school, "principal", kid)


# ── وليُّ الأمر الخالص: كما كان ─────────────────────────────────────────


@pytest.mark.parametrize("path", ["/dashboard/", "/notifications/", "/parents/"])
def test_pure_parent_is_redirected_to_consent(pure_parent, path):
    response = _client(pure_parent).get(path)

    assert response.status_code == 302
    assert response.url == reverse("parent_consent")


def test_pure_parent_gets_consent_required_on_the_api(pure_parent):
    response = _client(pure_parent).get("/api/v1/library/borrowings/")

    assert response.status_code == 403
    assert response.json()["code"] == "consent_required"


def test_pure_parent_on_a_staff_module_is_refused_by_the_gate_first(pure_parent):
    """حارسُ الوحدات يسبق وسيطَ الموافقة (ترتيبُ الإعدادات) — فالعيادةُ ٤٠٣ لا تحويل."""
    response = _client(pure_parent).get("/clinic/")

    assert response.status_code == 403


def test_pure_parent_exempt_paths_pass(pure_parent):
    client = _client(pure_parent)

    assert client.get(CONSENT_URL).status_code == 200
    assert client.get("/static/css/custom.css").get("Location") != reverse("parent_consent")
    logout = client.post("/auth/logout/")
    assert logout.get("Location") != reverse("parent_consent")


# ── الكادرُ الذي هو وليُّ أمر: عملُه أوّلاً ────────────────────────────


@pytest.mark.parametrize("fixture", ["teacher_parent", "vice_admin_parent"])
def test_staff_parent_reaches_the_staff_dashboard_without_consent(request, fixture):
    user = request.getfixturevalue(fixture)

    response = _client(user).get("/dashboard/")

    assert response.status_code == 200


def test_teacher_parent_opening_the_portal_meets_the_consent_page(teacher_parent, kid):
    client = _client(teacher_parent)

    response = client.get("/parents/")
    assert response.status_code == 302
    assert response.url == reverse("parent_consent")

    page = client.get(CONSENT_URL)
    assert page.status_code == 200
    body = page.content.decode()
    assert kid.full_name in body
    # زرُّ النموذج نفسُه ومفتاحُ الابن — لا `type="submit"` العامّ، فزرُّ الخروج في
    # القالب الأساسيّ يحمله في كلّ صفحة.
    assert f'name="consent_{kid.id}_grades"' in body
    assert "حفظ الإعدادات" in body
    # «إلغاء» يعيده إلى عمله لا إلى البوّابة التي تردّه هنا.
    assert f'href="{reverse("dashboard")}" class="btn-ghost"' in body


def test_pure_parent_consent_cancel_still_points_to_the_portal(pure_parent):
    body = _client(pure_parent).get(CONSENT_URL).content.decode()

    assert f'href="{reverse("parent_dashboard")}" class="btn-ghost"' in body


def test_staff_parent_without_a_linked_child_can_leave_the_consent_page(school):
    """عضويّةُ وليّ أمرٍ بلا ربط: لا شيءَ يوافق عليه — فلا يُحبس في صفحةٍ بلا مخرج."""
    lonely = _member(school, "teacher", "parent")

    body = _client(lonely).get(CONSENT_URL).content.decode()

    assert "حفظ الإعدادات" not in body
    assert f'href="{reverse("dashboard")}" class="btn-ghost"' in body


def test_pure_parent_without_a_linked_child_page_is_unchanged(school):
    lonely = _member(school, "parent")

    body = _client(lonely).get(CONSENT_URL).content.decode()

    assert "حفظ الإعدادات" not in body
    assert 'class="btn-ghost"' not in body


def test_after_consent_the_teacher_sees_only_their_own_child(school, teacher_parent, kid):
    stranger = _child(school, name="طالب غريب")
    client = _client(teacher_parent)

    posted = client.post(CONSENT_URL, {f"consent_{kid.id}_grades": "1"})
    assert posted.status_code == 302
    teacher_parent.refresh_from_db()
    assert teacher_parent.consent_given_at is not None

    response = client.get("/parents/")
    assert response.status_code == 200
    body = response.content.decode()
    assert kid.full_name in body
    assert stranger.full_name not in body


def test_staff_without_a_parent_membership_still_cannot_open_the_portal(teacher_user):
    client = _client(teacher_user)

    assert client.get("/parents/").status_code == 403
    assert client.get(CONSENT_URL).status_code == 403


def test_teacher_parent_cannot_manage_parent_links(teacher_parent):
    """المنحُ يفتح بوّابةَ الوحدة لا شاشاتِ الإدارة تحتها."""
    teacher_parent.consent_given_at = timezone.now()
    teacher_parent.save(update_fields=["consent_given_at"])

    assert _client(teacher_parent).get("/parents/admin/links/").status_code == 403


def test_principal_parent_manages_links_without_consent(principal_parent):
    response = _client(principal_parent).get("/parents/admin/links/")

    assert response.status_code == 200


def test_vice_admin_parent_api_parent_endpoint_needs_consent(vice_admin_parent, kid):
    client = _client(vice_admin_parent)

    for url in ("/api/v1/parent/children/", f"/api/v1/parent/children/{kid.id}/grades/"):
        response = client.get(url)
        assert response.status_code == 403, url
        assert response.json()["code"] == "consent_required"


# ── صلاحيّةُ الـAPI: الموافقةُ قبل تجاوز المدير ─────────────────────────


def _is_parent_or_admin(user):
    """الصلاحيّةُ وحدَها بلا وسيط — كما يبلغها طلبُ الرمز (JWT)."""
    request = APIRequestFactory().get("/api/v1/parent/children/")
    force_authenticate(request, user=user)
    drf_request = APIView().initialize_request(request)
    permission = IsParentOrAdmin()
    view = mock.Mock(kwargs={})
    return permission, permission.has_permission(drf_request, view)


def test_is_parent_or_admin_asks_for_consent_before_the_principal_bypass(principal_parent):
    permission, allowed = _is_parent_or_admin(principal_parent)
    assert allowed is False
    assert permission.code == "consent_required"
    assert permission.message == "يجب الموافقة على سياسة البيانات أولاً"

    principal_parent.consent_given_at = timezone.now()
    principal_parent.save(update_fields=["consent_given_at"])
    _, allowed = _is_parent_or_admin(principal_parent)
    assert allowed is True


def test_is_parent_or_admin_lets_a_plain_principal_through(principal_user):
    _, allowed = _is_parent_or_admin(principal_user)

    assert allowed is True


# ── ما كان الحجبُ العامّ يغلقه: الاستعاراتُ وتقاريرُ الابن ───────────────


def test_borrowings_api_hides_children_until_consent(school, teacher_parent, kid):
    book = LibraryBookFactory(school=school)
    own = str(BookBorrowingFactory(book=book, user=teacher_parent).id)
    child_loan = str(BookBorrowingFactory(book=book, user=kid).id)
    client = _client(teacher_parent)

    def ids():
        response = client.get("/api/v1/library/borrowings/")
        assert response.status_code == 200
        return {row["id"] for row in response.json()["results"]}

    assert ids() == {own}

    teacher_parent.consent_given_at = timezone.now()
    teacher_parent.save(update_fields=["consent_given_at"])
    assert ids() == {own, child_loan}


def test_child_result_report_needs_consent(school, vice_admin_parent, kid):
    url = reverse("student_result_pdf", args=[kid.id])
    client = _client(vice_admin_parent)

    assert client.get(url, {"preview": "1"}).status_code == 403

    vice_admin_parent.consent_given_at = timezone.now()
    vice_admin_parent.save(update_fields=["consent_given_at"])
    assert client.get(url, {"preview": "1"}).status_code == 200


def test_has_parent_access_requires_consent(school, vice_admin_parent, kid):
    from reports.views import _has_parent_access

    request = mock.Mock(user=vice_admin_parent)
    assert _has_parent_access(request, kid, school) is False

    vice_admin_parent.consent_given_at = timezone.now()
    assert _has_parent_access(request, kid, school) is True


# ── رابطُ «بوابتي» في قائمة الكادر ─────────────────────────────────────


def test_my_portal_link_shows_for_a_teacher_who_is_a_parent(teacher_parent):
    body = _client(teacher_parent).get("/dashboard/").content.decode()

    assert 'id="nav-my-portal"' in body
    assert reverse("parent_dashboard") in body


def test_my_portal_link_is_absent_for_a_plain_teacher(teacher_user):
    body = _client(teacher_user).get("/dashboard/").content.decode()

    assert 'id="nav-my-portal"' not in body
    assert 'id="mnav-my-portal"' not in body


@pytest.mark.parametrize("role_name", ["principal", "vice_admin"])
def test_my_portal_link_is_absent_for_leadership_without_a_parent_membership(school, role_name):
    """القيادةُ تفتح البوّابةَ بدورها — فالعضويّةُ وحدَها ما يُخفي الرابطَ عنها.

    ولولاها لظهرت «بوابتي» للمدير، ونقرُها ٤٠٣ «لأولياء الأمور فقط».
    """
    leader = _member(school, role_name)

    body = _client(leader).get("/dashboard/").content.decode()

    assert 'id="nav-my-portal"' not in body
    assert 'id="mnav-my-portal"' not in body
    assert "بوابتي" not in body


def test_my_portal_link_shows_in_the_mobile_nav_for_a_leader_who_is_a_parent(vice_admin_parent):
    body = _client(vice_admin_parent).get("/dashboard/").content.decode()

    assert 'id="nav-my-portal"' in body
    assert 'id="mnav-my-portal"' in body


def _mobile_portal_anchor(body):
    start = body.index('id="mnav-my-portal"')
    return body[start : body.index(">", start)]


def test_mobile_portal_is_not_lit_on_the_links_admin_screen(principal_parent):
    body = _client(principal_parent).get("/parents/admin/links/").content.decode()

    assert "active" not in _mobile_portal_anchor(body)


def test_mobile_portal_is_lit_inside_the_portal(teacher_parent):
    teacher_parent.consent_given_at = timezone.now()
    teacher_parent.save(update_fields=["consent_given_at"])

    body = _client(teacher_parent).get("/parents/").content.decode()

    assert "active" in _mobile_portal_anchor(body)


# ── السياسةُ نفسُها ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/parents/", True),
        ("/parents/grades/", True),
        ("/parents/push/subscribe/", True),
        ("/api/v1/parent/children/", True),
        ("/parents/admin/links/", False),
        ("/api/v1/students/", False),
        ("/dashboard/", False),
    ],
)
def test_is_parent_facing(path, expected):
    assert is_parent_facing(path) is expected


def test_anonymous_user_is_never_blocked():
    anonymous = AnonymousUser()

    assert consent_blocks(anonymous, "/dashboard/") is False
    assert needs_parent_consent(anonymous) is False
    assert holds_parent_membership(anonymous) is False


def test_consented_parent_is_never_blocked(parent_user):
    assert consent_blocks(parent_user, "/dashboard/") is False
    assert consent_blocks(parent_user, "/parents/") is False


def test_policy_matrix(school, pure_parent, teacher_parent, teacher_user):
    assert consent_blocks(pure_parent, "/dashboard/") is True
    assert consent_blocks(pure_parent, "/parents/consent/") is False
    assert consent_blocks(teacher_parent, "/dashboard/") is False
    assert consent_blocks(teacher_parent, "/parents/") is True
    assert consent_blocks(teacher_parent, "/parents/admin/links/") is False
    assert consent_blocks(teacher_user, "/parents/") is False
    assert holds_parent_membership(teacher_parent) is True
    assert holds_parent_membership(teacher_user) is False


def test_staff_on_a_staff_path_costs_no_query(teacher_parent, django_assert_num_queries):
    """السؤالُ الرخيصُ أوّلاً: الكادرُ خارج شاشات وليّ الأمر يُجاب عنه بلا استعلام."""
    teacher_parent.active_memberships  # يحمّلها حارسُ الوحدات قبل هذا الوسيط

    with django_assert_num_queries(0):
        assert consent_blocks(teacher_parent, "/dashboard/") is False
        assert consent_blocks(teacher_parent, "/parents/") is True

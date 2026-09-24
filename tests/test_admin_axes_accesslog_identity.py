"""سجلُّ الدخول في الإدارة يُظهر صاحبَ المحاولة: اسمَه ورقمَه الوظيفيّ — بلا سؤالٍ لكلّ صفّ."""

from __future__ import annotations

import pytest
from axes.models import AccessLog
from django.contrib.admin.sites import site
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from core.admin_axes import install
from tests.conftest import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def superuser(developer_user):
    developer_user.is_staff = developer_user.is_superuser = True
    developer_user.must_change_password = False
    developer_user.save()
    return developer_user


def _log(username):
    return AccessLog.objects.create(
        username=username, ip_address="10.0.0.1", user_agent="t", attempt_time=timezone.now()
    )


def _page(client):
    with CaptureQueriesContext(connection) as queries:
        response = client.get(reverse("admin:axes_accesslog_changelist"))
    assert response.status_code == 200
    return response.content.decode(), len(queries.captured_queries)


def test_the_accesslog_shows_the_owner_by_national_id_or_employee_number(client_as, superuser):
    by_national_id = UserFactory(full_name="سالم الناصر", employee_number="70001")
    by_employee_number = UserFactory(full_name="هند العلي", employee_number="70002")
    _log(by_national_id.national_id)
    _log("70002")
    _log("99999999999")  # لا يطابق أحداً — يبقى بلا اسم

    html, _ = _page(client_as(superuser))

    assert "سالم الناصر" in html and "70001" in html
    assert "هند العلي" in html and "70002" in html
    assert by_employee_number.full_name in html
    assert "الرقم الوظيفي" in html


def test_an_empty_username_does_not_match_users_without_an_employee_number(client_as, superuser):
    UserFactory(full_name="طالبٌ بلا رقمٍ وظيفيّ", employee_number="")
    _log("")
    html, _ = _page(client_as(superuser))
    assert "طالبٌ بلا رقمٍ وظيفيّ" not in html


def test_the_owner_columns_do_not_query_per_row(client_as, superuser):
    client = client_as(superuser)
    for i in range(2):
        user = UserFactory(employee_number=f"8000{i}")
        _log(user.national_id)
    _, few = _page(client)
    for i in range(2, 14):
        user = UserFactory(employee_number=f"8000{i}")
        _log(user.national_id)
    _, many = _page(client)
    assert many <= few + 1, f"{few} → {many}"


def test_installing_twice_keeps_a_single_registration():
    install()
    install()
    assert type(site._registry[AccessLog]).__name__ == "IdentifiedAccessLogAdmin"
    assert list(site._registry).count(AccessLog) == 1


def test_the_typed_national_id_is_masked_in_the_list(client_as, superuser):
    owner = UserFactory(full_name="مالكُ المحاولة", employee_number="70009")
    _log(owner.national_id)
    html, _ = _page(client_as(superuser))
    assert owner.national_id not in html, "الرقمُ الشخصيّ كاملاً ظهر في القائمة"
    assert f"****{owner.national_id[-4:]}" in html
    assert "مالكُ المحاولة" in html


def test_mask_keeps_employee_numbers_and_marks_empty():
    from core.admin_axes import mask_national_id

    assert mask_national_id("28181801642") == "****1642"
    assert mask_national_id("70009") == "70009"
    assert mask_national_id("NURSETEST7") == "NURSETEST7"
    assert mask_national_id("") == "—"


@pytest.mark.parametrize(
    "model_name,make",
    [
        (
            "accessattempt",
            lambda u: __import__("axes.models", fromlist=["x"]).AccessAttempt.objects.create(
                username=u,
                ip_address="10.0.0.2",
                user_agent="t",
                attempt_time=timezone.now(),
                get_data="",
                post_data="",
                failures_since_start=1,
            ),
        ),
        (
            "accessfailurelog",
            lambda u: __import__("axes.models", fromlist=["x"]).AccessFailureLog.objects.create(
                username=u, ip_address="10.0.0.3", user_agent="t", attempt_time=timezone.now()
            ),
        ),
    ],
)
def test_the_other_axes_lists_are_identified_and_masked(client_as, superuser, model_name, make):
    owner = UserFactory(full_name="صاحبُ محاولةٍ فاشلة", employee_number="70077")
    make(owner.national_id)
    html = client_as(superuser).get(reverse(f"admin:axes_{model_name}_changelist")).content.decode()
    assert "صاحبُ محاولةٍ فاشلة" in html and "70077" in html
    assert owner.national_id not in html, f"{model_name}: الرقمُ الشخصيّ كاملاً ظهر في القائمة"


def _attempt(username, failures):
    from axes.models import AccessAttempt

    return AccessAttempt.objects.create(
        username=username,
        ip_address="10.0.0.4",
        user_agent="t",
        attempt_time=timezone.now(),
        get_data="",
        post_data="",
        failures_since_start=failures,
    )


def test_the_attempts_list_speaks_arabic(client_as, superuser):
    """نصوصُ axes بلا ترجمةٍ عربيّة في كتالوجها — «Status» و«Locked Out» — تُستبدل في اللوحة (OWN-19)."""
    from axes.conf import settings as axes_settings

    limit = axes_settings.AXES_FAILURE_LIMIT
    _attempt("11111111111", limit)
    _attempt("22222222222", limit - 1)
    html = client_as(superuser).get(reverse("admin:axes_accessattempt_changelist")).content.decode()

    for english in ("Locked Out", "Attempt Remaining", "Status", "Expiration", "Clean up expired"):
        assert english not in html, f"بقي «{english}» في قائمة المحاولات"
    assert "حالة القفل" in html and "مقفل" in html and "باقٍ 1 من المحاولات" in html
    assert "حذف المحاولات المنتهية" in html


def test_the_arabic_lock_filter_keeps_the_axes_condition(client_as, superuser):
    from axes.conf import settings as axes_settings

    limit = axes_settings.AXES_FAILURE_LIMIT
    locked = UserFactory(full_name="محاولةٌ مقفلة", employee_number="80011")
    open_ = UserFactory(full_name="محاولةٌ باقية", employee_number="80022")
    _attempt(locked.national_id, limit)
    _attempt(open_.national_id, limit - 1)
    url = reverse("admin:axes_accessattempt_changelist")

    html = client_as(superuser).get(url, {"locked_out": "yes"}).content.decode()
    assert "محاولةٌ مقفلة" in html and "محاولةٌ باقية" not in html
    html = client_as(superuser).get(url, {"locked_out": "no"}).content.decode()
    assert "محاولةٌ باقية" in html and "محاولةٌ مقفلة" not in html

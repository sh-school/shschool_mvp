"""الإلزامُ بتغيير كلمة المرور يُلزم — لا صفحةَ غيرَ صفحة التغيير حتى يُبدّلها.

كان الإلزامُ عند الدخول وحدَه: `login_view` يحوّل إلى صفحة التغيير، ثمّ لا شيءَ
يمنع من كتابة `/dashboard/` في الشريط فيمضي بالمؤقّتة. وحين تكون المؤقّتةُ على
نمطٍ معروف (قرارُ 2026-09-13) فالإلزامُ الذي لا يُلزم بابٌ مفتوح.
"""

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

FORCE = "/auth/force_change_password/"
STRONG = "Qatar-School#2026-Strong"


@pytest.fixture
def flagged(client_as, teacher_user):
    teacher_user.must_change_password = True
    teacher_user.save(update_fields=["must_change_password"])
    return client_as(teacher_user)


def test_a_page_typed_in_the_address_bar_goes_to_the_change_page(flagged):
    response = flagged.get("/dashboard/")

    assert response.status_code == 302
    assert response.url == FORCE


def test_an_htmx_request_asks_the_browser_to_go_to_the_change_page(flagged):
    response = flagged.get("/dashboard/", HTTP_HX_REQUEST="true")

    assert response.status_code == 204
    assert response["HX-Redirect"] == FORCE


def test_a_background_request_is_refused_not_redirected(flagged):
    """عدّادُ الإشعارات كان يتبع التحويلَ فيقرأ صفحةَ HTML على أنّها JSON."""
    response = flagged.get(
        "/notifications/api/unread-count/", HTTP_X_REQUESTED_WITH="XMLHttpRequest"
    )

    assert response.status_code == 403
    assert response.json()["code"] == "password_change_required"


def test_the_change_page_and_logout_stay_reachable(flagged):
    assert flagged.get(FORCE).status_code == 200
    assert flagged.post(reverse("logout")).status_code in (200, 302)


def test_after_changing_the_password_the_platform_opens(flagged, teacher_user):
    flagged.post(FORCE, {"password1": STRONG, "password2": STRONG})

    teacher_user.refresh_from_db()
    assert teacher_user.must_change_password is False
    assert flagged.get("/dashboard/").status_code == 200


def test_a_user_without_the_flag_is_untouched(client_as, teacher_user):
    assert client_as(teacher_user).get("/dashboard/").status_code == 200

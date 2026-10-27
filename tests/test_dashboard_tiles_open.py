"""كلُّ بلاطةِ انتقالٍ في لوحة كلّ دورٍ تُفتح لصاحب الدور — W-20261027-031 (سواط 017 توصية 4، R15).

بلاطةُ «درجاتي» للطالب كانت تنتهي بـ403 بلا اختبارٍ يكشفها؛ فهذا الحارسُ يمرّ على كلّ دورٍ ويفتح كلَّ رابطٍ
`action-card` في لوحته (الوجهةُ نفسُها بعد تتبّع التحويل) ويُسقط 403/404/5xx.
"""

from __future__ import annotations

import re

import pytest
from django.urls import reverse

from core.landing import ROLE_LANDINGS
from core.models.access import Role
from tests.conftest import MembershipFactory, RoleFactory, UserFactory
from tests.test_staff_register_screen import school  # noqa: F401

pytestmark = pytest.mark.django_db

#: خطٌّ أساسيٌّ يكشفه هذا الحارسُ أوّلَ مرّة (2026-10-27): بلاطاتٌ تظهر لدورٍ ويحجبها وسيطُ الوحدة أو القدرة. يُنقَص ولا يُزاد؛
#: وإصلاحُها قرارُ صلاحيّةٍ للمالك (D-130م) فلا يُغيَّر دورٌ هنا بلا قراره.
KNOWN_BROKEN = {
    "vice_academic": {"/clinic/": 403, "/transport/": 403},
    "activities_coordinator": {"/analytics/": 403, "/student-affairs/list/": 403},
    "social_worker": {"/teacher/absences/": 403},
    "psychologist": {"/behavior/report/": 403, "/teacher/absences/": 403},
    "academic_advisor": {
        "/behavior/report/": 403,
        "/student-affairs/list/": 403,
        "/teacher/absences/": 403,
    },
}

_TILE_HREF = re.compile(r'<a href="([^"]+)" class="action-card')


def _user_with_role(school, role_name: str, index: int):
    user = UserFactory(full_name=f"مستخدم {role_name}", national_id=f"2930{index:06d}")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role_name))
    return user


@pytest.mark.parametrize(("index", "code"), list(enumerate(code for code, _l in Role.ROLES)))
def test_every_tile_of_the_role_dashboard_opens(client, school, index, code):
    if code in ROLE_LANDINGS:
        pytest.skip("دورٌ بوجهةٍ خاصّةٍ بلا لوحة بلاطات")
    client.force_login(_user_with_role(school, code, index))

    page = client.get("/dashboard/", follow=True)
    hrefs = sorted(set(_TILE_HREF.findall(page.content.decode())))

    broken = {}
    for href in hrefs:
        if href.startswith(("http", "#", "mailto:")):
            continue
        status = client.get(href, follow=True).status_code
        if status >= 400:
            broken[href] = status
    known = KNOWN_BROKEN.get(code, {})
    assert (
        broken == known
    ), f"بلاطاتٌ لا تُفتح للدور {code}: {broken} — الجديدُ يُصلَح، وما أُصلح من القائمة يُحذف من KNOWN_BROKEN"


def test_the_student_reaches_only_their_own_result(client, school):
    student = _user_with_role(school, "student", 900)
    other = _user_with_role(school, "student", 901)
    client.force_login(student)

    assert client.get(reverse("my_result")).status_code == 200
    assert client.get(reverse("student_result_pdf", args=[other.id])).status_code == 403
    assert client.get(reverse("reports_index")).status_code == 403

"""إعادةُ التوجيه تُبنى من قيمٍ مُتحقَّقٍ منها لا من مُدخَلِ الطلب (py/url-redirection).

W-20261002-004: كانت `create_evaluation` تُعيد `redirect(request.get_full_path())` و
`teacher_preferences` تُلصق `year` الخامَ في الرابط. فصارتا تُعيدان البناءَ بـ`urlencode`
ثمّ تتحقّقان بـ`url_has_allowed_host_and_scheme` — والاختباراتُ تثبّت أنّ الناتجَ نسبيٌّ
على المضيف نفسِه وأنّ حمولةً عدائيّةً في `year` لا تخرج من الرابط.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from quality import evaluation_views
from quality.evaluation_services import EvaluationRejectedError
from tests.conftest import MembershipFactory, RoleFactory, UserFactory
from tests.test_evaluation_review_round1 import YEAR, _seed, _staff, _url

pytestmark = pytest.mark.django_db


def test_rejected_evaluation_redirects_back_to_the_same_target(client, school, monkeypatch):
    _seed(school)
    teacher = _staff(school, "teacher", "معلّمٌ مُقيَّم")
    vice = _staff(school, "vice_academic", "النائب الأكاديمي")

    def _reject(**_kwargs):
        raise EvaluationRejectedError("مرفوض لسببٍ تجريبيّ")

    monkeypatch.setattr(evaluation_views, "save_evaluation_form", _reject)
    client.force_login(vice)

    response = client.post(_url(teacher, period="S2"), {"action": "submitted"})

    assert response.status_code == 302
    assert response["Location"] == (
        reverse("create_evaluation", kwargs={"employee_id": teacher.pk}) + f"?year={YEAR}&period=S2"
    )


def test_teacher_preferences_redirect_keeps_the_year_only(client, school):
    teacher = UserFactory(full_name="معلّمُ تفضيلات")
    MembershipFactory(user=teacher, school=school, role=RoleFactory(school=school, name="teacher"))
    client.force_login(teacher)
    payload = {"max_daily_periods": "5", "max_consecutive": "3", "max_gap": "", "free_day": ""}

    response = client.post(reverse("teacher_preferences") + f"?year={YEAR}", payload)

    assert response.status_code == 302
    assert response["Location"] == reverse("teacher_preferences") + f"?year={YEAR}"


def test_teacher_preferences_hostile_year_cannot_leave_the_query_string(client, school):
    teacher = UserFactory(full_name="معلّمٌ عدائيّ")
    MembershipFactory(user=teacher, school=school, role=RoleFactory(school=school, name="teacher"))
    client.force_login(teacher)
    payload = {"max_daily_periods": "5", "max_consecutive": "3", "max_gap": "", "free_day": ""}

    # `academic_year` حدُّه 9 أحرف، فالحمولةُ قصيرةٌ: `a&b=//e` تحاول فتحَ معاملٍ ومضيف.
    response = client.post(reverse("teacher_preferences") + "?year=a%26b%3D%2F%2Fe", payload)

    location = response["Location"]
    assert location.startswith(reverse("teacher_preferences") + "?year="), "نسبيٌّ على المضيف"
    assert "//" not in location, "لا مضيفَ خارجيّ"
    assert "&b=" not in location, "الحمولةُ رُمِّزت داخل قيمة year لا معاملاً جديداً"

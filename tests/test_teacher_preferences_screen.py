"""[SCHEDULE] تفضيلاتُ الجدول: «حصّةٌ واحدة» سقفٌ مشروعٌ لا خيارٌ ناقص.

كانت القائمةُ تبدأ من اثنتين، فمن أراد ألّا تقع له حصّتان متجاورتان البتّة
لم يجد ما يقوله. والقيدُ قائمٌ في المدرسة فعلاً، والمحرّكُ يقرؤه ولا يرفعه في
الاسترخاء — فنقصُ الخيار نقصٌ في الواجهة لا في المحرّك.

وكان الحفظُ يقرأ `int(request.POST[...])` على نصٍّ حرّ: يُسقط الصفحةَ بـ500
على حرفٍ واحد، ويقبل تسعةً وتسعين حصّةً متتالية. فصار المدى مغلقاً.
"""

import pytest
from django.urls import reverse

from operations.models import TeacherPreference
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def teacher(client, school):
    user = UserFactory(full_name="معلّمٌ يكره التجاور")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    client.force_login(user)
    return user


def _save(client, **fields):
    payload = {"max_daily_periods": "5", "max_consecutive": "3", "free_day": "", "notes": ""}
    payload.update(fields)
    return client.post(reverse("teacher_preferences"), payload)


def test_one_is_a_valid_ceiling(client, teacher):
    """حصّةٌ واحدة — أي لا تجاور — تُحفظ كما هي."""
    _save(client, max_consecutive="1")

    assert TeacherPreference.objects.get(teacher=teacher).max_consecutive == 1


def test_the_form_offers_it(client, teacher):
    page = client.get(reverse("teacher_preferences")).content.decode()

    assert 'value="1"' in page
    assert "لا تجاور" in page


def test_rubbish_does_not_crash_the_page(client, teacher):
    """حرفٌ في خانةٍ رقميّة كان يُسقط الصفحةَ بـ500."""
    response = _save(client, max_consecutive="abc")

    assert response.status_code in (200, 302)
    assert TeacherPreference.objects.get(teacher=teacher).max_consecutive == 3


def test_a_ceiling_outside_the_week_falls_back(client, teacher):
    _save(client, max_consecutive="99")

    assert TeacherPreference.objects.get(teacher=teacher).max_consecutive == 3

"""[SCHEDULE] تفضيلاتُ الجدول بعد D-418م: المعلّمُ يختار سقفَه اليوميَّ وحدَه.

كانت الشاشةُ تعرض «أقصى حصص متتالية» (و«حصّةٌ واحدة — لا تجاور» فيها) و«أقصى فجوة». فقرّر المالك
إخفاءهما (D-418م): الحلّالُ لا يقرأ التتالي، ولا قيمةَ آمنةً للفراغ حتى يُصلح (W-20261012-020..025).
فيبقيان في النموذج والأدمن — ومعلّمٌ وضع له الأدمنُ «لا تجاور» يبقى له ولو حفظ صفحتَه.

وكان الحفظُ يقرأ `int(request.POST[...])` على نصٍّ حرّ: يُسقط الصفحةَ بـ500
على حرفٍ واحد، ويقبل تسعةً وتسعين حصّة. فصار المدى مغلقاً، وما بقي في الشاشة منه حقلٌ واحد.
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
    payload = {"max_daily_periods": "5", "free_day": "", "notes": ""}
    payload.update(fields)
    return client.post(reverse("teacher_preferences"), payload)


def test_the_form_no_longer_offers_the_run_or_the_gap(client, teacher):
    page = client.get(reverse("teacher_preferences")).content.decode()

    assert 'name="max_consecutive"' not in page and 'name="max_gap"' not in page
    assert "لا تجاور" not in page and "أقصى فجوة" not in page


def test_an_admin_no_adjacency_cap_and_gap_survive_the_teacher_save(client, teacher):
    """«حصّةٌ واحدة» قيدٌ قائمٌ لمعلّمٍ في المدرسة: وضعه الأدمن فلا يمحوه حفظُ المعلّم ولا قيمٌ في الطلب."""
    client.get(reverse("teacher_preferences"))  # الصفُّ بعام الصفحة نفسه
    pref = TeacherPreference.objects.get(teacher=teacher)
    pref.max_consecutive, pref.max_gap = 1, 2
    pref.save()

    _save(client, max_consecutive="7", max_gap="0", notes="ملاحظة")

    pref.refresh_from_db()
    assert (pref.max_consecutive, pref.max_gap, pref.notes) == (1, 2, "ملاحظة")


def test_rubbish_does_not_crash_the_page(client, teacher):
    """حرفٌ في خانةٍ رقميّة كان يُسقط الصفحةَ بـ500 — فيعود إلى الافتراضيّ."""
    response = _save(client, max_daily_periods="abc")

    assert response.status_code in (200, 302)
    assert TeacherPreference.objects.get(teacher=teacher).max_daily_periods == 5


@pytest.mark.parametrize("posted", ["1", "3", "99"])
def test_a_daily_cap_outside_the_offered_range_falls_back(client, teacher, posted):
    _save(client, max_daily_periods=posted)

    assert TeacherPreference.objects.get(teacher=teacher).max_daily_periods == 5

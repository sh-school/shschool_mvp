"""[QUALITY] مؤشّرات المعايير في نموذج الزيارة الصفّية (W-20261106-011)."""

import pytest
from django.urls import reverse

from quality.management.commands.seed_observation_criteria import CRITERIA
from quality.observation_indicators import INDICATORS
from quality.observation_models import ObservationCriterion


def test_every_criterion_has_indicators():
    """المعايير الـ23 كلُّها لها مؤشّرات غير فارغة، بمفاتيح order من 1 إلى 23."""
    assert sorted(INDICATORS) == list(range(1, len(CRITERIA) + 1)) == list(range(1, 24))
    for order, items in INDICATORS.items():
        assert items and all(isinstance(t, str) and t.strip() for t in items), order


def test_indicator_text_is_verbatim_for_samples():
    """عيّنةٌ من أطراف الدليل: أوّل مؤشّر وآخره، وبنودٌ فيها علاماتٌ غير معتادة."""
    assert INDICATORS[1][0] == "متوافرة مع المعلم في غرفة الصف."
    assert INDICATORS[1][-1] == "مشاركة الخطة على منصة التعليم الإلكتروني"
    assert len(INDICATORS[1]) == 10
    assert INDICATORS[23][-1].endswith("إلخ ...).")
    assert [len(INDICATORS[k]) for k in (4, 12, 17, 20)] == [2, 8, 7, 8]


@pytest.mark.django_db
def test_form_renders_collapsed_indicators_only_where_present(client_as, school, coordinator_user):
    with_ind = ObservationCriterion.objects.create(
        school=school, domain="planning", text="معيار بمؤشّرات", order=4
    )
    ObservationCriterion.objects.create(
        school=school, domain="planning", text="معيار بلا مؤشّرات", order=99
    )
    html = client_as(coordinator_user).get(reverse("observation_create")).content.decode()

    assert html.count("<details") == 1
    assert "<summary" in html and "المؤشّرات" in html
    assert "<details open" not in html
    for t in INDICATORS[with_ind.order]:
        assert t in html

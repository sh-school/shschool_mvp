"""[W-20261010-050] تلميحاتُ صفحة تفضيلات المعلّم سطرٌ واحدٌ قصير يحفظ معنى «لا يُخرق» مقابل «نحاول ولا نضمن»."""

import re

import pytest
from django.urls import reverse

from operations.models import Subject, SubjectClassAssignment
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db
YEAR = "2026-2027"
URL = reverse("teacher_preferences") + f"?year={YEAR}"
MAX_HINT = 70


def _hint_after(body, field_id):
    """أوّلُ `ui-field-hint` يلي الحقلَ المسمّى — نصُّه بلا وسوم."""
    tail = body.split(f'id="{field_id}"', 1)[1]
    text = re.search(r'<p class="ui-field-hint">(.*?)</p>', tail, re.S).group(1)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text)).strip()


@pytest.fixture
def body(client, school):
    teacher = UserFactory(full_name="معلّمُ الجبر")
    MembershipFactory(user=teacher, school=school, role=RoleFactory(school=school, name="teacher"))
    subject = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    group = ClassGroupFactory(school=school, grade="G10", level_type="sec", academic_year=YEAR)
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=teacher,
        class_group=group,
        subject=subject,
        weekly_periods=4,
        is_active=True,
    )
    client.force_login(teacher)
    return client.get(URL).content.decode()


@pytest.mark.parametrize("field_id", ["max_consecutive", "max_gap"])
def test_a_hard_constraint_hint_is_one_short_line_that_says_it_is_never_broken(body, field_id):
    hint = _hint_after(body, field_id)

    assert len(hint) <= MAX_HINT, hint
    assert "لا يُخرق" in hint


def test_the_gap_hint_says_it_binds_only_when_a_number_is_chosen(body):
    assert "عند اختيار رقم" in _hint_after(body, "max_gap")


def test_the_daily_hint_says_it_is_a_preference_not_a_guarantee(body):
    hint = _hint_after(body, "max_daily")

    assert "نحاول ولا نضمن" in hint
    assert "لا يُخرق" not in hint


def test_the_daily_hint_keeps_its_computed_capacity_sentence(body):
    assert re.search(r"نصابُك\s*<b>4</b>\s*حصة", body)

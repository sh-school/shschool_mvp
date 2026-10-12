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
#: التتالي والفراغ أُخفيا (D-418م)، فبقي حقلٌ واحدٌ بتلميحه.
FIELDS = ["max_daily"]


def _group(body, field_id):
    """كتلةُ `form-group` التي فيها الحقلُ المسمّى، إلى بداية الكتلة التالية."""
    return next(g for g in body.split('<div class="form-group">')[1:] if f'id="{field_id}"' in g)


def _hint_after(body, field_id):
    """أوّلُ `ui-field-hint` يلي الحقلَ المسمّى — نصُّه بلا وسوم."""
    tail = body.split(f'id="{field_id}"', 1)[1]
    text = re.search(r'<p class="ui-field-hint">(.*?)</p>', tail, re.S).group(1)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text)).strip()


def _page_for_load(client, school, *loads):
    """صفحةُ معلّمٍ أنصبتُه في شُعبٍ بعدد `loads`."""
    teacher = UserFactory(full_name="معلّمُ الجبر")
    MembershipFactory(user=teacher, school=school, role=RoleFactory(school=school, name="teacher"))
    subject = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    for periods in loads:
        SubjectClassAssignment.objects.create(
            school=school,
            academic_year=YEAR,
            teacher=teacher,
            class_group=ClassGroupFactory(
                school=school, grade="G10", level_type="sec", academic_year=YEAR
            ),
            subject=subject,
            weekly_periods=periods,
            is_active=True,
        )
    client.force_login(teacher)
    return client.get(URL).content.decode()


@pytest.fixture
def body(client, school):
    return _page_for_load(client, school, 4)


@pytest.mark.parametrize("field_id", FIELDS)
def test_each_field_has_exactly_one_help_line(body, field_id):
    assert _group(body, field_id).count('class="ui-field-hint"') == 1


@pytest.mark.parametrize("field_id", FIELDS)
def test_each_help_line_is_short_apart_from_the_computed_load(body, field_id):
    hint = _hint_after(body, field_id).split("نصابُك", 1)[0].strip()

    assert len(hint) <= MAX_HINT, hint


@pytest.mark.parametrize("field_id", ["max_consecutive", "max_gap"])
def test_the_hidden_hard_constraints_leave_neither_a_field_nor_a_help_line(body, field_id):
    """D-418م: تلميحا «لا يُخرق» و«عند اختيار رقم» يسقطان مع حقلَيهما، ولا تبقى بطاقةُ «قيود صلبة» فارغة."""
    assert f'id="{field_id}"' not in body
    assert "لا يُخرق" not in body and "عند اختيار رقم" not in body
    assert "قيود صلبة" not in body


def test_the_daily_hint_says_it_is_a_preference_not_a_guarantee(body):
    hint = _hint_after(body, "max_daily")

    assert "نحاول ولا نضمن" in hint
    assert "لا يُخرق" not in hint


def test_the_daily_hint_keeps_its_computed_capacity_sentence(body):
    assert re.search(r"نصابُك\s*<b>4</b>\s*حصة", body)


def test_the_floor_sentence_is_silent_when_the_first_option_fits(body):
    """نصابُ 4 يحتمل حصّةً يوميّاً وأوّلُ الخيارات 4 (D-418م): «أدنى رقمٍ 1» يحيّر ولا يفيد."""
    assert "يحتمله" not in _hint_after(body, "max_daily")


def test_the_floor_sentence_names_a_floor_above_the_first_option(client, school):
    """نصابُ 24 على خمسة أيّامٍ يحتاج 5: فيُذكر الرقمُ ويُطفأ 4 قبل الاختيار."""
    page = _page_for_load(client, school, 6, 6, 6, 6)

    assert re.search(r"يحتمله نصابُك عادةً\s*<b>5</b>", page)
    four = re.search(r'<option value="4"[^>]*>', page).group(0)
    assert "disabled" in four

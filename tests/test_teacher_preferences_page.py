"""[SCHEDULE] تفضيلاتُ المعلّم: ما تَعِد به الشاشةُ يفعله المولّد.

    حقلٌ يَعِد ولا يفي أسوأُ من حقلٍ غائب.

`free_day` كان يُحمَّل ويُمرَّر ولا يُقرأ في قيدٍ ولا ترجيح — يدخل حسابَ السعة
وقياسَ المختبر فقط. فمعلّمٌ نصابُه أربعُ حصصٍ وأيّامُه خمسةٌ طلب تفريغَ يومٍ
فوُضعت له فيه حصّة، وتركُه فارغاً كان مجّانيّاً (قياس 2026-09-09).

والمدى في الشاشة كان «3456»، فالخياران 1 و2 محجوبان — وضحيّتُهم اثنا عشرَ
منسّقاً أنصبتُهم ثلاثٌ إلى ثمانٍ عمداً، وهم أحوجُ الناس إلى تجميع حصصهم.
"""

import pytest

from operations.models import ScheduleSlot
from operations.scheduler import ScheduleGrid, build_tasks
from operations.scheduler_constraints import WEIGHTS, evaluate_soft_constraints
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"
FREE = 2  # الثلاثاء


@pytest.fixture
def teacher(school):
    from operations.models import Subject, SubjectClassAssignment

    user = UserFactory(full_name="معلّمٌ طلب يومَ تفريغ")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    subject = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    group = ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year=YEAR)
    SubjectClassAssignment.objects.create(
        school=school,
        class_group=group,
        subject=subject,
        teacher=user,
        weekly_periods=4,
        academic_year=YEAR,
    )
    return user


def test_the_requested_free_day_costs_more_than_any_other(school, teacher):
    """الحاسمُ: يومُ التفريغ يحمل عقوبةً، وسواه لا يحمل."""
    task = build_tasks(school, YEAR)[0]
    prefs = {task.teacher_id: {"max_daily": 7, "max_consecutive": 7, "free_day": FREE}}
    grid = ScheduleGrid()

    on_free = evaluate_soft_constraints(grid, FREE, 3, task, prefs)
    on_other = evaluate_soft_constraints(grid, FREE + 1, 3, task, prefs)

    assert on_free.details.get("free_day") == WEIGHTS["free_day"]
    assert "free_day" not in on_other.details
    assert on_free.total > on_other.total


def test_without_a_preference_no_day_is_penalised(school, teacher):
    """بلا تفضيلٍ مكتوبٍ لا عقوبةَ — فلا يُخترع قيدٌ لمن لم يطلبه."""
    task = build_tasks(school, YEAR)[0]
    grid = ScheduleGrid()

    for day in range(5):
        assert "free_day" not in evaluate_soft_constraints(grid, day, 3, task, {}).details


def test_the_free_day_outweighs_gap_and_run(school, teacher):
    """وزنُه يعلو الفراغَ والتتابع — وإلّا لسقط أمامهما فلا يُلزم شيئاً."""
    assert WEIGHTS["free_day"] > WEIGHTS["gap"]
    assert WEIGHTS["free_day"] > WEIGHTS["consecutive"]


# ════════════════════ المدى في الشاشة ════════════════════


def test_the_screen_offers_every_period_the_view_accepts(client, school, teacher):
    """الواجهةُ لا تكون أضيقَ من النموذج: العرضُ يقبل 1–7 فتُعرض 1–7."""
    from django.urls import reverse

    client.force_login(teacher)
    body = client.get(
        reverse("teacher_preferences") + f"?year={YEAR}", HTTP_HOST="localhost"
    ).content.decode()

    for value in ScheduleSlot.PERIODS:
        assert f'value="{value}"' in body, f"الخيار {value} محجوبٌ عن المنسّقين"


def test_a_cap_below_the_share_is_disabled_not_refused_later(client, school, teacher):
    """ما لا يسع النصابَ يُطفأ قبل الاختيار، لا يُردّ بعد الحفظ."""
    from django.urls import reverse

    client.force_login(teacher)
    body = client.get(
        reverse("teacher_preferences") + f"?year={YEAR}", HTTP_HOST="localhost"
    ).content.decode()

    # نصابٌ 4 على 5 أيّامٍ = حصّةٌ واحدةٌ في اليوم على الأقلّ — فلا يُطفأ شيء.
    assert "نصابُك" in body, "النصابُ يُعرض قبل الاختيار لا بعده"

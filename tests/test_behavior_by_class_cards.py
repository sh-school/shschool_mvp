"""ملخّص السلوك: بطاقةٌ لكلّ شعبة (W-20261008-026) — المجاميع، نطاق الجناح، الصفر الظاهر، وثباتُ الاستعلامات."""

import pytest
from django.urls import reverse

from behavior.models import ViolationCategory
from behavior.selectors import infractions_by_class
from tests.conftest import BehaviorInfractionFactory, ClassGroupFactory, StudentEnrollmentFactory
from tests.test_supervisor_student_affairs_followup import _pupil, world  # noqa: F401


def _category(degree: int) -> ViolationCategory:
    return ViolationCategory.objects.get_or_create(
        degree=degree, code=f"T-{degree}", defaults={"name_ar": f"فئة {degree}", "category": "A"}
    )[0]


def _infract(school, student, reporter, degree, times=1):
    for _ in range(times):
        BehaviorInfractionFactory(
            school=school,
            student=student,
            reported_by=reporter,
            violation_category=_category(degree),
        )


@pytest.fixture
def cards_world(school, world):  # noqa: F811
    """شعبتان لكلٍّ منهما طالب؛ ثالثةٌ بلا مخالفات؛ مخالفاتٌ بدرجاتٍ مختلفة."""
    empty_class = ClassGroupFactory(
        school=school, grade="G9", section="3", level_type="prep", academic_year=world["year"]
    )
    _infract(school, world["own"], world["teacher"], 1, times=2)
    _infract(school, world["own"], world["teacher"], 3)
    _infract(school, world["other"], world["teacher"], 2)
    return {**world, "empty_class": empty_class}


def _cards(response):
    return {c["group"].pk: c for c in response.context["class_cards"]}


class TestCardsPerClass:
    def test_each_class_has_a_card_with_offenders_total_and_degrees(
        self, client_as, principal_user, cards_world
    ):
        response = client_as(principal_user).get(reverse("student_affairs:behavior_overview"))
        cards = _cards(response)

        own = cards[cards_world["own_class"].pk]
        assert (own["offenders"], own["total"]) == (1, 3)
        assert own["degrees"] == {1: 2, 2: 0, 3: 1, 4: 0}
        other = cards[cards_world["other_class"].pk]
        assert (other["offenders"], other["total"], other["degrees"][2]) == (1, 1, 1)

    def test_a_class_without_infractions_shows_zero_not_missing(
        self, client_as, principal_user, cards_world
    ):
        response = client_as(principal_user).get(reverse("student_affairs:behavior_overview"))

        empty = _cards(response)[cards_world["empty_class"].pk]
        assert (empty["offenders"], empty["total"]) == (0, 0)
        assert 'data-class-card="9/3"' in response.content.decode()

    def test_the_cards_sum_to_the_screen_totals_without_repeating_a_student(
        self, client_as, principal_user, cards_world
    ):
        response = client_as(principal_user).get(reverse("student_affairs:behavior_overview"))
        ctx = response.context

        assert (
            sum(c["total"] for c in ctx["class_cards"]) + ctx["unassigned_card"]["total"]
            == (ctx["total_infractions"])
        )
        assert (
            sum(c["offenders"] for c in ctx["class_cards"]) + (ctx["unassigned_card"]["offenders"])
            == ctx["students_with_infractions"]
        )

    def test_a_transferred_student_counts_in_the_current_class(
        self, school, client_as, principal_user, cards_world
    ):
        """D-201م: الطالبُ يرحّل مخالفاتِه معه — العدُّ في قيده الجاري لا في شعبته وقت المخالفة."""
        moved = cards_world["own"]
        StudentEnrollmentFactory(student=moved, class_group=cards_world["empty_class"])
        old = moved.enrollments.get(class_group=cards_world["own_class"])
        old.is_active = False
        old.save(update_fields=["is_active"])

        cards = _cards(client_as(principal_user).get(reverse("student_affairs:behavior_overview")))

        assert cards[cards_world["empty_class"].pk]["total"] == 3
        assert cards[cards_world["own_class"].pk]["total"] == 0


class TestWingScope:
    def test_a_wing_supervisor_sees_only_his_wings_class(self, client_as, cards_world):
        response = client_as(cards_world["supervisor"]).get(
            reverse("student_affairs:behavior_overview")
        )
        cards = _cards(response)

        assert set(cards) == {cards_world["own_class"].pk}
        assert cards[cards_world["own_class"].pk]["total"] == 3
        assert 'data-class-card="8/2"' not in response.content.decode()


class TestQueryCount:
    def test_queries_are_constant_however_many_classes(
        self, school, cards_world, django_assert_max_num_queries
    ):
        from behavior.models import BehaviorInfraction
        from wings.scope import student_scope

        for n in range(6):
            klass = ClassGroupFactory(
                school=school, grade="G10", section=str(n + 1), academic_year=cards_world["year"]
            )
            _infract(school, _pupil(school, klass, f"طالب {n}"), cards_world["teacher"], 2)
        scope = student_scope(cards_world["teacher"], school)
        infractions = BehaviorInfraction.objects.filter(school=school)

        with django_assert_max_num_queries(3):
            cards, _ = infractions_by_class(infractions, scope, school, cards_world["year"])
        assert len(cards) >= 9

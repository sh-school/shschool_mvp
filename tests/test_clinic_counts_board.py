"""
tests/test_clinic_counts_board.py — اللوحة العدديّة للعيادة (W-20261020-031)

قمعُ الخلايا الأقلّ من 5، وغيابُ الأسماء والمعرّفات والنصّ الصحّيّ، والمنعُ بلا القدرة،
ورؤيةُ المنسّق بالقدرة لا بدورٍ جديد.
"""

import pytest
from django.urls import reverse

from clinic import choices
from clinic.models import ClinicVisit
from clinic.services import SUPPRESS_BELOW, ClinicService, suppress_breakdown, suppress_small
from core.capabilities import has_capability

# ── القمع النقيّ ─────────────────────────────────────────────────────


def test_cells_between_one_and_four_are_suppressed_and_zero_and_five_are_shown():
    assert SUPPRESS_BELOW == 5
    assert [suppress_small(n) for n in (0, 1, 4, 5, 6)] == [0, None, None, 5, 6]


def test_a_single_suppressed_cell_also_hides_the_smallest_other_so_it_cannot_be_subtracted():
    out = suppress_breakdown({"a": 2, "b": 7, "c": 9})
    assert out == {"a": None, "b": None, "c": 9}


def test_no_secondary_suppression_when_nothing_or_several_cells_are_hidden():
    assert suppress_breakdown({"a": 6, "b": 0, "c": 8}) == {"a": 6, "b": 0, "c": 8}
    out = suppress_breakdown({"a": 1, "b": 3, "c": 9})
    assert out == {"a": None, "b": None, "c": 9}


def test_every_shown_cell_is_zero_or_at_least_five_for_any_input():
    for cells in ({"x": 1}, {"x": 4, "y": 5}, {"x": 5, "y": 5, "z": 1}, {"x": 0, "y": 2}):
        for value in suppress_breakdown(cells).values():
            assert value is None or value == 0 or value >= SUPPRESS_BELOW


# ── التجميع ──────────────────────────────────────────────────────────


def _visit(school, student, nurse, **kw):
    return ClinicVisit.objects.create(
        school=school, student=student, nurse=nurse, reason="سبب سرّيّ", **kw
    )


@pytest.mark.django_db
def test_board_suppresses_small_counts_and_shows_large_ones(school, nurse_user, student_user):
    for _ in range(6):
        _visit(
            school,
            student_user,
            nurse_user,
            service_code="bandage",
            service_group=choices.GROUP_FIRST_AID,
        )
    for _ in range(2):
        _visit(
            school,
            student_user,
            nurse_user,
            service_code="insulin",
            service_group=choices.GROUP_DIABETES,
            outcome=choices.OUTCOME_REFERRAL,
        )
    board = ClinicService.get_counts_board(school)
    assert board["today"] == 8
    assert board["referral_today"] is None  # 2 < 5
    by_group = {r["label"]: r["count"] for r in board["by_group_today"]}
    assert by_group["السكّري"] is None  # 2 < 5
    assert by_group["إسعافات أوّليّة"] is None  # قمعٌ ثانويّ: خليّةٌ واحدةٌ مقموعةٌ فتُخفى أصغرُ المتبقّية


@pytest.mark.django_db
def test_board_never_contains_names_identifiers_or_free_text(school, nurse_user, student_user):
    for _ in range(7):
        _visit(school, student_user, nurse_user, service_group=choices.GROUP_FIRST_AID)
    board = ClinicService.get_counts_board(school)
    dumped = repr(board)
    assert student_user.full_name not in dumped
    assert str(student_user.pk) not in dumped
    assert "سبب سرّيّ" not in dumped


@pytest.mark.django_db
def test_board_counts_only_this_school(school, nurse_user, student_user):
    for _ in range(6):
        _visit(school, student_user, nurse_user)
    other = type(school).objects.create(name="مدرسةٌ أخرى", code="OTHER-1")
    assert ClinicService.get_counts_board(other)["today"] == 0


# ── العرض والقدرة ────────────────────────────────────────────────────


@pytest.mark.django_db
def test_nurse_and_coordinator_open_the_board_but_a_teacher_gets_403(
    client_as, school, nurse_user, student_affairs_coordinator_user, teacher_user
):
    url = reverse("clinic:counts")
    assert client_as(nurse_user).get(url).status_code == 200
    assert client_as(student_affairs_coordinator_user).get(url).status_code == 200
    assert client_as(teacher_user).get(url).status_code == 403


@pytest.mark.django_db
def test_coordinator_has_the_capability_without_a_new_role(student_affairs_coordinator_user):
    assert has_capability(student_affairs_coordinator_user, "clinic.counts")
    assert not has_capability(student_affairs_coordinator_user, "clinic.write")


@pytest.mark.django_db
def test_rendered_page_has_no_name_and_marks_suppressed_cells(
    client_as, school, nurse_user, student_user
):
    for _ in range(2):
        _visit(school, student_user, nurse_user, service_group=choices.GROUP_FIRST_AID)
    body = client_as(nurse_user).get(reverse("clinic:counts")).content.decode()
    assert student_user.full_name not in body and "سبب سرّيّ" not in body
    assert "—" in body  # خليّةٌ مقموعة

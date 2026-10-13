"""[SCHEDULE] بطاقةُ قرار المسودّة في صفحة الجدولة (W-20261010-001، D-310م).

يحرس هذا الملفّ ثلاثةً: المؤشّراتُ الخمسةُ بأسمائها ومعانيها (لا سادسَ ولا ناقصَ)، وأنّ المصدرَ
لقطةُ V2 لا حسابٌ يُعاد، وأنّ الصفحةَ تفتح بالعرضين (V2 والمحرّك السابق) وتطوي القديمَ بلا أزرار.
"""

import pytest
from django.urls import reverse

from operations.schedule_decision import (
    decision_card,
    declared_relaxations,
    is_v2,
    row_summary,
    stop_reason,
)
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

YEAR = "2026-2027"

#: المؤشّراتُ الخمسةُ في D-310م — لا تُزاد ولا تُنقص إلّا بقرارٍ جديد من المالك.
FIVE = ["IND-02", "IND-04", "IND-08", "IND-13", "IND-16"]


def snapshot(**over):
    evaluation = {
        "InfeasibilityValue": 0,
        "required_periods": 871,
        "placed_periods": 871,
        "unplaced": [],
        "orphan_cells": 0,
        "hard_breaches": {},
        "hard_total": 0,
        "ObjectiveValue": 17614.0,
        "soft_counts": {"consecutive": 12},
        "accepted": True,
        "verdict": "أمثلُ بحسب الحلّال",
        "eased": {"HC5": 3},
    }
    evaluation.update(over.pop("evaluation", {}))
    base = {
        "engine": "cpsat_v2",
        "solver": {"status": "FEASIBLE"},
        "evaluation": evaluation,
        "relaxations": {"hc5_run_caps": [{"teacher": "a"}, {"teacher": "b"}]},
    }
    base.update(over)
    return base


def test_the_card_has_exactly_the_five_indicators_each_with_meaning_direction_and_cap():
    card = decision_card(snapshot())

    assert [i["code"] for i in card["indicators"]] == FIVE
    for ind in card["indicators"]:
        assert ind["label"] and ind["meaning"], ind["code"]
        assert ind["direction"] in ("الأعلى أفضل", "الأقلّ أفضل"), ind["code"]
        assert ind["cap"], ind["code"]


def test_what_is_not_measured_says_so_and_never_shows_a_guessed_number():
    by_code = {i["code"]: i for i in decision_card(snapshot())["indicators"]}

    for code in ("IND-04", "IND-13", "IND-16"):
        assert by_code[code]["value"] == "لم يُقَس"
        assert by_code[code]["measured"] is False
    assert by_code["IND-02"]["value"] == "871 من 871"
    assert by_code["IND-08"]["value"] == "12"
    assert "3 من المواضع خُفِّف بقرارٍ معلَن" in by_code["IND-08"]["cap"]


def test_the_three_numbers_come_from_the_stored_evaluation_not_a_recomputation():
    card = decision_card(
        snapshot(
            evaluation={
                "accepted": False,
                "hard_total": 2,
                "InfeasibilityValue": 4,
                "ObjectiveValue": 99.4,
            }
        )
    )

    assert (card["hard"], card["unplaced"], card["objective"]) == (2, 4, 99)
    assert card["accepted"] is False
    assert "لا تُعتمد بلا إقرار" in card["verdict"]


def test_the_technical_name_infeasibility_value_never_reaches_the_card_text():
    card = decision_card(snapshot())
    text = repr(card)

    assert "InfeasibilityValue" not in text
    assert "ObjectiveValue" not in text


def test_a_row_of_the_previous_engine_has_no_card_and_no_summary():
    legacy = {"unplaced": 3, "breaches": {"count": 1, "items": []}}

    assert not is_v2(legacy)
    assert decision_card(legacy) is None
    assert row_summary(legacy) is None
    assert decision_card(None) is None


def test_the_row_summary_states_placed_of_required_and_acceptance():
    ok = row_summary(snapshot())
    bad = row_summary(
        snapshot(evaluation={"accepted": False, "hard_total": 2, "InfeasibilityValue": 1})
    )

    assert (ok["placed"], ok["required"], ok["tone"]) == (871, 871, "success")
    assert bad["tone"] == "danger" and "2 خرقاً" in bad["state"]


def test_why_it_stopped_is_a_human_sentence_from_the_solver_status():
    assert "ضيقُ وقتٍ" in stop_reason(snapshot(solver={"status": "UNKNOWN"}))
    assert "لا أفضل منه" in stop_reason(snapshot(solver={"status": "OPTIMAL"}))
    assert stop_reason({}) == ""


def test_declared_relaxations_report_teachers_and_eased_positions():
    got = declared_relaxations(snapshot())

    assert got["teachers"] == 2 and got["eased"] == 3
    assert declared_relaxations(snapshot(relaxations={}))["teachers"] == 0


# ── الصفحة ─────────────────────────────────────────────────────────────


@pytest.fixture
def principal(school):
    role = RoleFactory(school=school, name="principal")
    user = UserFactory(full_name="مدير المدرسة")
    MembershipFactory(user=user, school=school, role=role)
    return user


def _assign(school):
    from operations.models import Subject, SubjectClassAssignment

    role = RoleFactory(school=school, name="teacher")
    teacher = UserFactory(full_name="معلّم")
    MembershipFactory(user=teacher, school=school, role=role)
    subject = Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")
    group = ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year=YEAR)
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=teacher,
        class_group=group,
        subject=subject,
        weekly_periods=6,
        is_active=True,
    )


def _generation(school, status, config=None):
    from operations.models import ScheduleGeneration

    return ScheduleGeneration.objects.create(
        school=school,
        academic_year=YEAR,
        status=status,
        total_slots_created=6,
        config_snapshot=config or {},
    )


@pytest.mark.django_db
def test_the_page_shows_the_decision_card_for_a_v2_draft(client_as, principal, school):
    _assign(school)
    _generation(school, "draft", snapshot())

    html = client_as(principal).get(reverse("smart_schedule") + f"?year={YEAR}").content.decode()

    assert "قرارُ المسودّة" in html
    for code in FIVE:
        assert code in html
    assert "871 من 871" in html
    assert "لم يُقَس" in html
    assert "InfeasibilityValue" not in html


@pytest.mark.django_db
def test_the_page_folds_archived_rows_of_the_previous_engine_without_buttons(
    client_as, principal, school
):
    from operations.models import ScheduleGeneration

    _assign(school)
    _generation(school, "archived")
    _generation(school, "approved")

    response = client_as(principal).get(reverse("smart_schedule") + f"?year={YEAR}")
    html = response.content.decode()

    assert response.status_code == 200
    assert "توليداتُ المحرّك السابق (2)" in html
    assert ScheduleGeneration.objects.filter(school=school).count() == 2, "لا حذفَ لبياناتها"
    folded = html.split("gen-legacy")[1].split("</details>")[0]
    assert "<button" not in folded and "<form" not in folded


@pytest.mark.django_db
def test_a_draft_of_the_previous_engine_keeps_its_buttons(client_as, principal, school):
    _assign(school)
    _generation(school, "draft")

    html = client_as(principal).get(reverse("smart_schedule") + f"?year={YEAR}").content.decode()

    assert "اعتماد" in html
    assert "gen-legacy" not in html


@pytest.mark.django_db
def test_feasibility_is_computed_on_demand_not_on_open(client_as, principal, school):
    _assign(school)
    url = reverse("smart_schedule") + f"?year={YEAR}"

    opened = client_as(principal).get(url).content.decode()
    asked = client_as(principal).get(url + "&feasibility=1").content.decode()

    assert "احسب الآن" in opened and "feas-chip" not in opened
    assert "feas-chip" in asked and "احسب الآن" not in asked

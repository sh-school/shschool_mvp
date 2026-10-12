"""قرارُ عذر الغياب عن الاختبار (W-20261001-012، D-402م، الدليل 04b ص. 28).

المعلّمُ يرصد «غائباً» فقط؛ والعذرُ يقرّره خمسةُ أدوارٍ بقدرةٍ واحدة `assessments.decide_excuse`،
بنوعٍ من القائمة المغلقة ومرجعٍ، ويُخزَّن من قرّر ومتى. المدير والنائبُ الأكاديميّ والمنسّق والمعلّم
مرفوضون — والمدير يرث الأكاديميَّ عبر ROLE_INHERITS فلا يتسرّب إليه القبولُ من هذا الباب.
"""

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from assessments.models import EXCUSE_TYPES, StudentAssessmentGrade
from assessments.services import GradeService
from core.capabilities import capability, has_capability
from tests.conftest import MembershipFactory, RoleFactory, UserFactory
from tests.test_grade_save_all import assessment  # noqa: F401 — فكسترُ التقييم نفسُه

pytestmark = pytest.mark.django_db

DECIDERS = [
    "student_affairs_coordinator",
    "vice_admin",
    "admin_supervisor",
    "social_worker",
    "psychologist",
]
REFUSED = [
    "principal",
    "vice_academic",
    "coordinator",
    "teacher",
    "ese_teacher",
    "academic_advisor",
]


def _staff(school, role_name):
    user = UserFactory(full_name=f"موظف {role_name}")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role_name))
    return user


def _row(assessment, student):
    return StudentAssessmentGrade.objects.get(assessment=assessment, student=student)


@pytest.fixture
def absent(client_as, teacher_user, assessment, student_user, enrolled_student):  # noqa: F811
    """غيابٌ رصده المعلّمُ بالمسار الحقيقيّ."""
    resp = client_as(teacher_user).post(
        f"/assessments/assessment/{assessment.id}/save-single/",
        {"student_id": str(student_user.id), "is_absent": "1"},
    )
    assert resp.status_code == 200
    return _row(assessment, student_user)


def _decide(c, assessment, student, **data):  # noqa: F811
    payload = {"student_id": str(student.id), "excuse_type": "illness", "reference": "شهادة 123"}
    return c.post(f"/assessments/assessment/{assessment.id}/decide-excuse/", {**payload, **data})


# ── المعلّم يرصد غائباً فقط ────────────────────────────────────────


def test_teacher_single_post_cannot_set_excuse_on_an_absence(
    client_as,
    teacher_user,
    assessment,
    student_user,
    enrolled_student,  # noqa: F811
):
    client_as(teacher_user).post(
        f"/assessments/assessment/{assessment.id}/save-single/",
        {"student_id": str(student_user.id), "is_absent": "1", "is_excused": "1"},
    )

    row = _row(assessment, student_user)
    assert row.is_absent is True
    assert row.is_excused is False
    assert row.excuse_type == "" and row.excuse_decided_by is None


def test_teacher_single_post_cannot_excuse_instead_of_a_grade(
    client_as,
    teacher_user,
    assessment,
    student_user,
    enrolled_student,  # noqa: F811
):
    client_as(teacher_user).post(
        f"/assessments/assessment/{assessment.id}/save-single/",
        {"student_id": str(student_user.id), "grade": "15", "is_excused": "1"},
    )

    row = _row(assessment, student_user)
    assert row.is_excused is False
    assert row.grade is not None


def test_teacher_save_all_cannot_set_excuse(
    client_as,
    teacher_user,
    assessment,
    student_user,
    enrolled_student,  # noqa: F811
):
    sid = student_user.id
    client_as(teacher_user).post(
        f"/assessments/assessment/{assessment.id}/save-all/",
        {f"absent_{sid}": "1", f"excused_{sid}": "1", f"grade_{sid}": "", f"notes_{sid}": ""},
    )

    row = _row(assessment, student_user)
    assert row.is_absent is True
    assert row.is_excused is False


# ── القدرة وأعضاؤها ───────────────────────────────────────────────


def test_the_capability_is_exactly_the_five_roles_even_after_inheritance():
    """وراثةُ الأدوار لا تُدخل المدير ولا النائبَ الأكاديميّ ولا المنسّق ولا المعلّم."""
    assert capability("assessments.decide_excuse").expanded_roles == frozenset(DECIDERS)


@pytest.mark.parametrize("role_name", DECIDERS)
def test_each_of_the_five_roles_holds_the_capability(school, role_name):
    assert has_capability(_staff(school, role_name), "assessments.decide_excuse")


@pytest.mark.parametrize("role_name", REFUSED)
def test_every_other_academic_role_does_not_hold_it(school, role_name):
    assert not has_capability(_staff(school, role_name), "assessments.decide_excuse")


# ── القرار ──────────────────────────────────────────────────────


@pytest.mark.parametrize("role_name", DECIDERS)
def test_each_of_the_five_roles_can_decide_an_excuse(
    client_as,
    school,
    assessment,
    student_user,
    absent,
    role_name,  # noqa: F811
):
    decider = _staff(school, role_name)

    resp = _decide(
        client_as(decider), assessment, student_user, excuse_type="force_majeure", reference="ب"
    )

    assert resp.status_code == 302
    row = _row(assessment, student_user)
    assert row.is_excused is True and row.is_absent is True and row.grade is None
    assert row.excuse_type == "force_majeure"
    assert row.excuse_reference == "ب"
    assert row.excuse_decided_by == decider
    assert row.excuse_decided_at is not None


@pytest.mark.parametrize("role_name", REFUSED)
def test_every_refused_role_gets_403_and_changes_nothing(
    client_as,
    school,
    assessment,
    student_user,
    absent,
    role_name,  # noqa: F811
):
    resp = _decide(client_as(_staff(school, role_name)), assessment, student_user)

    assert resp.status_code == 403
    row = _row(assessment, student_user)
    assert row.is_excused is False and row.excuse_type == ""


@pytest.mark.parametrize("role_name", REFUSED)
def test_every_refused_role_is_kept_out_of_the_queue_page(client_as, school, role_name):
    assert client_as(_staff(school, role_name)).get("/assessments/excuses/").status_code == 403


def test_the_service_itself_refuses_a_non_holder(school, assessment, student_user, absent):  # noqa: F811
    with pytest.raises(PermissionDenied):
        GradeService.decide_excuse(
            assessment, student_user, "illness", "x", _staff(school, "principal")
        )


def test_the_type_list_is_closed(client_as, school, assessment, student_user, absent):  # noqa: F811
    resp = _decide(
        client_as(_staff(school, "social_worker")), assessment, student_user, excuse_type="سفر"
    )

    assert resp.status_code == 302
    assert _row(assessment, student_user).is_excused is False


def test_the_closed_list_matches_the_manual(school):
    """ثلاثةُ أنواعٍ كما وردت في 04b ص. 28: مرضٌ، حادثٌ/ظرفٌ قهريّ، مهمةٌ رسمية."""
    assert [k for k, _ in EXCUSE_TYPES] == ["illness", "force_majeure", "official_mission"]


def test_a_reference_is_required(client_as, school, assessment, student_user, absent):  # noqa: F811
    _decide(client_as(_staff(school, "social_worker")), assessment, student_user, reference="  ")

    assert _row(assessment, student_user).is_excused is False


def test_an_excuse_needs_an_absence_recorded_by_the_teacher(
    client_as,
    school,
    assessment,
    student_user,
    enrolled_student,
    teacher_user,  # noqa: F811
):
    """لا صفَّ أصلاً، ثم صفٌّ حاضرٌ بدرجة: لا عذرَ لغيرِ الغياب."""
    decider = client_as(_staff(school, "social_worker"))
    _decide(decider, assessment, student_user)
    assert not StudentAssessmentGrade.objects.filter(assessment=assessment).exists()

    client_as(teacher_user).post(
        f"/assessments/assessment/{assessment.id}/save-single/",
        {"student_id": str(student_user.id), "grade": "12"},
    )
    _decide(decider, assessment, student_user)
    assert _row(assessment, student_user).is_excused is False


def test_an_excuse_cannot_be_decided_twice(school, assessment, student_user, absent):  # noqa: F811
    decider = _staff(school, "social_worker")
    GradeService.decide_excuse(assessment, student_user, "illness", "أ", decider)

    with pytest.raises(ValidationError):
        GradeService.decide_excuse(assessment, student_user, "force_majeure", "ب", decider)

    assert _row(assessment, student_user).excuse_type == "illness"


def test_an_excused_row_is_locked_against_the_teacher(
    client_as,
    school,
    teacher_user,
    assessment,
    student_user,
    absent,  # noqa: F811
):
    GradeService.decide_excuse(
        assessment, student_user, "illness", "أ", _staff(school, "psychologist")
    )

    client_as(teacher_user).post(
        f"/assessments/assessment/{assessment.id}/save-single/",
        {"student_id": str(student_user.id), "grade": "18"},
    )
    sid = student_user.id
    client_as(teacher_user).post(
        f"/assessments/assessment/{assessment.id}/save-all/",
        {f"grade_{sid}": "19", f"absent_{sid}": "0", f"notes_{sid}": ""},
    )

    row = _row(assessment, student_user)
    assert (row.is_absent, row.is_excused, row.grade) == (True, True, None)


# ── القديم لا يتغيّر والمحرّك يقرؤه كما هو ──────────────────────────


def test_a_legacy_excused_row_is_untouched_and_keeps_empty_decision_fields(
    client_as,
    teacher_user,
    assessment,
    student_user,
    enrolled_student,  # noqa: F811
):
    legacy = StudentAssessmentGrade.objects.create(
        assessment=assessment,
        student=student_user,
        school=assessment.school,
        is_absent=True,
        is_excused=True,
    )

    client_as(teacher_user).post(
        f"/assessments/assessment/{assessment.id}/save-single/",
        {"student_id": str(student_user.id), "grade": "10"},
    )

    legacy.refresh_from_db()
    assert (legacy.is_absent, legacy.is_excused, legacy.grade) == (True, True, None)
    assert legacy.excuse_type == "" and legacy.excuse_decided_at is None


def test_the_verdict_engine_reads_the_same_tuple_for_a_decided_excuse(
    school,
    assessment,
    student_user,
    absent,  # noqa: F811
):
    """المحرّكُ يفهرس (درجة، غائب، معذور)؛ والقرارُ يُنتج التركيبةَ نفسَها لمعذورٍ قائم."""
    GradeService.decide_excuse(
        assessment, student_user, "illness", "أ", _staff(school, "psychologist")
    )

    assert list(
        StudentAssessmentGrade.objects.filter(assessment=assessment).values_list(
            "grade", "is_absent", "is_excused"
        )
    ) == [(None, True, True)]


# ── الشاشة والقائمة والإدارة ────────────────────────────────────────


def test_the_queue_lists_the_absence_then_the_decided_excuse(
    client_as,
    school,
    assessment,
    student_user,
    absent,  # noqa: F811
):
    decider = _staff(school, "student_affairs_coordinator")
    c = client_as(decider)

    page = c.get("/assessments/excuses/")
    assert page.status_code == 200
    assert student_user.full_name in page.content.decode()
    assert "تثبيت العذر" in page.content.decode()

    _decide(c, assessment, student_user)
    page = c.get("/assessments/excuses/").content.decode()
    assert "آخرُ الأعذار المقرَّرة" in page
    assert decider.full_name in page


@pytest.mark.parametrize("role_name", DECIDERS)
def test_the_menu_offers_the_screen_to_the_five_roles_only(client_as, school, role_name):
    body = client_as(_staff(school, role_name)).get("/assessments/excuses/").content.decode()
    assert 'href="/assessments/excuses/"' in body


def test_the_menu_hides_the_screen_from_the_principal(client_as, school):
    body = client_as(_staff(school, "principal")).get("/dashboard/").content.decode()
    assert 'href="/assessments/excuses/"' not in body


def test_the_decision_fields_show_in_django_admin(
    client_as,
    developer_user,
    assessment,
    student_user,
    absent,  # noqa: F811
):
    developer_user.is_staff = developer_user.is_superuser = True
    developer_user.save(update_fields=["is_staff", "is_superuser"])

    page = client_as(developer_user).get(
        f"/admin/assessments/studentassessmentgrade/{absent.pk}/change/"
    )

    assert page.status_code == 200
    body = page.content.decode()
    for field in ("excuse_type", "excuse_reference", "excuse_decided_by", "excuse_decided_at"):
        assert f'name="{field}"' in body or f'name="{field}_0"' in body


@pytest.mark.parametrize(
    "role_name",
    ["student_affairs_coordinator", "admin_supervisor", "social_worker", "psychologist"],
)
def test_the_path_gate_opening_does_not_open_the_rest_of_assessments(
    client_as,
    school,
    assessment,
    role_name,  # noqa: F811
):
    """بوّابةُ المسار تسع الأدوار الأربعة، لكنّ حارسَ كلّ شاشةٍ بقدرته يردّهم عن الدرجات والإعداد."""
    c = client_as(_staff(school, role_name))

    assert c.get("/assessments/").status_code == 403
    assert c.get(f"/assessments/assessment/{assessment.id}/").status_code == 403
    assert c.get("/assessments/failing/").status_code == 403


def test_a_closed_year_is_refused_with_a_message_not_a_server_error(
    client_as,
    school,
    assessment,
    student_user,
    absent,  # noqa: F811
):
    setup = assessment.package.setup
    setup.academic_year = "2019-2020"
    setup.save(update_fields=["academic_year"])

    resp = _decide(client_as(_staff(school, "social_worker")), assessment, student_user)

    assert resp.status_code == 302
    assert _row(assessment, student_user).is_excused is False

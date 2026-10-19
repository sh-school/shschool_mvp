"""طلبُ الالتحاق (نموذج 07، المرحلة 1): طلبٌ بلا حسابٍ للطالب، ثم سلسلةُ التدقيق ← الاعتماد ← التشعيب ← الإدخال (W-20261001-033).

الأرقامُ الشخصيّةُ هنا قيمٌ وهميّةٌ للاختبار وحدَه؛ والحالةُ الصحّيّةُ نصٌّ عامّ بلا بيانٍ حقيقيّ.
"""

import datetime as dt

import pytest
from django.db import connection
from django.urls import reverse

from core.academic_calendar import academic_year_for_school
from core.models import CustomUser, StudentEnrollment
from student_affairs.admission_models import AdmissionApplication
from student_affairs.admission_services import apply_action, create_application
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    SchoolFactory,
    UserFactory,
)
from tests.transfer_chain_support import ALL_DOCS

pytestmark = pytest.mark.django_db

STUDENT_ID = "29900000001"
APPLICANT_ID = "27700000002"
HEALTH = "حالةٌ صحّيّةٌ للاختبار"

FORM = {
    "student_name": "طالبٌ جديدٌ للاختبار",
    "student_national_id": STUDENT_ID,
    "birth_date": "2013-03-04",
    "nationality": "قطري",
    "current_school": "مدرسةٌ سابقة",
    "grade": "G7",
    "health_status": HEALTH,
    "living_with": "both",
    "transport": "bus",
    "housing_area": "الوكرة",
    "housing_street": "شارع 12",
    "housing_house": "45",
    "applicant_name": "وليّ الأمر",
    "applicant_national_id": APPLICANT_ID,
    "applicant_relationship": "أب",
    "applicant_phone": "55550000",
    "declaration_accepted": "on",
}


@pytest.fixture
def klass(school):
    return ClassGroupFactory(
        school=school,
        grade="G7",
        section="1",
        level_type="prep",
        academic_year=academic_year_for_school(school),
    )


@pytest.fixture
def teacher(school):
    user = UserFactory(full_name="معلّمٌ للاختبار", national_id="29000001010")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


def _raw(application, column):
    with connection.cursor() as cur:
        cur.execute(
            f"SELECT {column} FROM student_affairs_admissionapplication WHERE id = %s",  # noqa: S608
            [str(application.pk)],
        )
        return cur.fetchone()[0]


def _application(school, actor, **override):
    data = {**FORM, "birth_date": dt.date(2013, 3, 4), "declaration_accepted": True, **override}
    return create_application(school, data, actor, "2026-2027")


def test_an_application_is_registered_without_a_student_account(
    client, principal_user, school, klass
):
    client.force_login(principal_user)
    users_before = CustomUser.objects.count()

    response = client.post(reverse("student_affairs:admission_create"), FORM)

    application = AdmissionApplication.objects.get(school=school)
    assert response.status_code == 302
    assert application.linked_student is None
    assert application.status == "pending"
    assert CustomUser.objects.count() == users_before  # لا حسابَ للطالب قبل الإدخال
    assert (application.housing_area, application.housing_street, application.housing_house) == (
        "الوكرة",
        "شارع 12",
        "45",
    )
    assert (application.transport, application.living_with) == ("bus", "both")
    assert application.declaration_accepted is True


def test_the_declaration_is_required(client, principal_user, school):
    client.force_login(principal_user)
    data = {k: v for k, v in FORM.items() if k != "declaration_accepted"}

    response = client.post(reverse("student_affairs:admission_create"), data)

    assert response.status_code == 200
    assert not AdmissionApplication.objects.exists()


def test_national_ids_and_health_are_encrypted_at_rest(principal_user, school):
    application = _application(school, principal_user)

    for column, plain in (
        ("student_national_id", STUDENT_ID),
        ("applicant_national_id", APPLICANT_ID),
        ("health_status", HEALTH),
    ):
        assert plain not in _raw(application, column)
        assert getattr(AdmissionApplication.objects.get(pk=application.pk), column) == plain


def test_the_list_and_detail_never_show_the_full_id_in_the_list(client, principal_user, school):
    application = _application(school, principal_user)
    client.force_login(principal_user)

    listing = client.get(reverse("student_affairs:admission_list")).content.decode()
    detail = client.get(
        reverse("student_affairs:admission_detail", args=[application.pk])
    ).content.decode()

    assert FORM["student_name"] in listing
    assert STUDENT_ID not in listing and HEALTH not in listing
    assert STUDENT_ID not in detail and APPLICANT_ID not in detail  # الرقمُ مستورٌ حتى في التفاصيل


def test_a_role_without_the_transfers_capability_is_refused(client, school, teacher):
    client.force_login(teacher)

    response = client.get(reverse("student_affairs:admission_list"))

    assert response.status_code in (302, 403)


def test_another_schools_application_is_not_reachable(client, principal_user, school):
    other = SchoolFactory()
    application = _application(other, principal_user)
    client.force_login(principal_user)

    response = client.get(reverse("student_affairs:admission_detail", args=[application.pk]))

    assert response.status_code == 404


def test_the_chain_links_the_student_account_only_at_entry(principal_user, school, klass):
    application = _application(school, principal_user)
    assert not CustomUser.objects.filter(national_id=STUDENT_ID).exists()

    apply_action(application, "review", "", principal_user, documents=ALL_DOCS)
    apply_action(application, "approved", "", principal_user)
    apply_action(application, "place", "", principal_user, class_group=klass)
    assert not CustomUser.objects.filter(national_id=STUDENT_ID).exists()
    student = apply_action(application, "enter", "", principal_user, gender="M")

    application.refresh_from_db()
    assert application.linked_student == student
    assert student.national_id == STUDENT_ID
    assert StudentEnrollment.objects.filter(student=student, class_group=klass).exists()
    assert application.entered_by == principal_user and application.entered_at


def test_the_order_of_stages_is_enforced(principal_user, school, klass):
    application = _application(school, principal_user)

    with pytest.raises(ValueError):
        apply_action(application, "approved", "", principal_user)  # قبل التدقيق
    apply_action(application, "review", "", principal_user, documents=ALL_DOCS)
    with pytest.raises(ValueError):
        apply_action(application, "place", "", principal_user, class_group=klass)  # قبل الاعتماد
    apply_action(application, "approved", "", principal_user)
    with pytest.raises(ValueError):
        apply_action(application, "enter", "", principal_user, gender="M")  # قبل التشعيب


def test_placing_needs_a_class_of_the_requested_grade(principal_user, school, klass):
    application = _application(school, principal_user)
    apply_action(application, "review", "", principal_user, documents=ALL_DOCS)
    apply_action(application, "approved", "", principal_user)
    other_grade = ClassGroupFactory(
        school=school, grade="G8", section="1", level_type="prep", academic_year=klass.academic_year
    )

    with pytest.raises(ValueError):
        apply_action(application, "place", "", principal_user, class_group=other_grade)
    with pytest.raises(ValueError):
        apply_action(application, "place", "", principal_user)


def test_a_rejection_needs_a_reason_and_leaves_no_account(principal_user, school):
    application = _application(school, principal_user)
    apply_action(application, "review", "", principal_user, documents=ALL_DOCS)

    with pytest.raises(ValueError):
        apply_action(application, "rejected", "", principal_user)
    apply_action(application, "rejected", "مستندات غير مطابقة", principal_user)

    application.refresh_from_db()
    assert application.status == "rejected"
    assert not CustomUser.objects.filter(national_id=STUDENT_ID).exists()


def test_no_log_line_carries_the_national_id_or_health(principal_user, school, caplog):
    application = _application(school, principal_user)
    apply_action(application, "review", "", principal_user, documents=ALL_DOCS)

    assert STUDENT_ID not in caplog.text and HEALTH not in caplog.text
    assert application.pk

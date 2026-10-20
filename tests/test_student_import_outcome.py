"""نتيجةُ استيراد الطلاب: لا «نجاحَ» عند صفر تسجيلات مع أخطاء، وتحقّقٌ مسبقٌ يسمّي الأعمدة الناقصة (W-20261004-016).

الأرقامُ الشخصيّةُ هنا وهميّةٌ للاختبار وحدَه.
"""

import io

import openpyxl
import pytest
from django.urls import reverse

from core.academic_calendar import academic_year_for_school
from core.ministry_import import import_outcome, ministry_missing_columns
from core.models import CustomUser, StudentEnrollment
from core.services import process_student_import
from tests.conftest import ClassGroupFactory, RoleFactory

pytestmark = pytest.mark.django_db

HEADER = ["الرقم", "الاسم", "الشعبة الصفية"]


def _upload(rows, header=HEADER):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(header)
    for row in rows:
        ws.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    buffer.name = "students.xlsx"
    return buffer


@pytest.fixture
def roles(school):
    for name in ("student", "parent"):
        RoleFactory(school=school, name=name)


@pytest.fixture
def klass(school):
    return ClassGroupFactory(
        school=school,
        grade="G7",
        section="1",
        level_type="prep",
        academic_year=academic_year_for_school(school),
    )


def test_a_file_without_the_class_column_is_refused_before_any_write(school, roles):
    users_before = CustomUser.objects.count()
    upload = _upload([["29900000011", "طالبٌ اختباريّ"]], header=["الرقم", "الاسم"])

    result = process_student_import(upload, school, academic_year_for_school(school))

    assert result["success"] is False
    assert result["missing_columns"] == ["الشعبة الصفية"]
    assert "الشعبة الصفية" in result["errors"][0]
    assert CustomUser.objects.count() == users_before  # صفرُ تغييرٍ في القاعدة


def test_the_required_names_come_from_the_header_map_not_a_copy():
    assert ministry_missing_columns({"student_nid": 0}) == ["الاسم", "الشعبة الصفية"]
    assert ministry_missing_columns({"student_nid": 0, "full_name": 1, "class_combined": 2}) == []


def test_zero_registrations_with_errors_is_not_called_a_success(school, roles):
    upload = _upload([["29900000012", "طالبٌ بلا شعبة", "07/9"]])

    result = process_student_import(upload, school, academic_year_for_school(school))

    assert result["success"] is False
    assert result["nothing_registered"] is True
    assert result["enrollments_created"] == 0 and result["error_count"] == 1


def test_a_complete_file_still_succeeds(school, roles, klass):
    upload = _upload([["29900000013", "طالبٌ مسجَّل", "07/1"]])

    result = process_student_import(upload, school, academic_year_for_school(school))

    assert result["success"] is True and result["nothing_registered"] is False
    assert StudentEnrollment.objects.filter(class_group=klass).count() == 1


def test_a_partial_file_is_still_a_success_with_its_errors_listed(school, roles, klass):
    upload = _upload(
        [["29900000014", "طالبٌ مسجَّل", "07/1"], ["29900000015", "طالبٌ بلا شعبة", "07/9"]]
    )

    result = process_student_import(upload, school, academic_year_for_school(school))

    assert result["success"] is True
    assert result["enrollments_created"] == 1 and result["error_count"] == 1


@pytest.mark.parametrize(
    ("registered", "errors", "success"),
    [(0, 3, False), (0, 0, True), (2, 0, True), (2, 5, True)],
)
def test_the_outcome_rule(registered, errors, success):
    assert import_outcome(registered, errors)["success"] is success


def test_the_page_shows_the_missing_column_by_name_and_no_success_title(
    client, school, roles, principal_user
):
    client.force_login(principal_user)
    upload = _upload([["29900000016", "طالبٌ اختباريّ"]], header=["الرقم", "الاسم"])

    page = client.post(reverse("student_import_export"), {"student_file": upload}).content.decode()

    assert "الشعبة الصفية" in page
    assert "اكتمل الاستيراد بنجاح" not in page


def test_the_page_says_nothing_was_registered_instead_of_success(
    client, school, roles, principal_user
):
    client.force_login(principal_user)
    upload = _upload([["29900000017", "طالبٌ بلا شعبة", "07/9"]])

    page = client.post(reverse("student_import_export"), {"student_file": upload}).content.decode()

    assert "لم يُسجَّل أي طالب في شعبة" in page
    assert "اكتمل الاستيراد بنجاح" not in page

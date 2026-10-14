"""
tests/test_student_update.py
StudentService.update_student — يحدّث المستخدم والملف معاً، ولا يغيّر الشعبة أبداً (D-343م، W-20261001-017).
"""

import pytest
from django.conf import settings

from core.models.academic import ClassGroup, StudentEnrollment
from core.models.access import Membership, Role
from core.models.user import CustomUser, Profile
from student_affairs.services import StudentService

YEAR = settings.CURRENT_ACADEMIC_YEAR


def _class(school, grade, section):
    return ClassGroup.objects.create(
        school=school,
        grade=grade,
        section=section,
        level_type="prep",
        academic_year=YEAR,
        is_active=True,
    )


@pytest.fixture
def enrolled_student(db, school):
    cg = _class(school, "G7", "أ")
    student = CustomUser.objects.create_user(
        must_change_password=False,
        national_id="29955500011",
        full_name="طالب الاختبار",
        password="x",
    )
    role, _ = Role.objects.get_or_create(school=school, name="student")
    Membership.objects.create(user=student, school=school, role=role, is_active=True)
    Profile.objects.create(user=student)
    StudentEnrollment.objects.create(student=student, class_group=cg, is_active=True)
    return student


@pytest.mark.django_db
def test_update_changes_the_data_but_never_the_class(enrolled_student, school):
    """تغييرُ الشعبة طلبُ انتقالٍ داخليّ يُعتمد: ولو وصل الصفُّ والشعبةُ في البيانات لا يُحرَّك التسجيل."""
    _class(school, "G7", "ب")  # شعبة أخرى موجودة، فلو عُمل بها لانتقل الطالب إليها
    StudentService.update_student(
        enrolled_student,
        school,
        {"full_name": "اسم محدّث", "grade": "G7", "section": "ب"},
    )
    enrolled_student.refresh_from_db()
    assert enrolled_student.full_name == "اسم محدّث"
    assert StudentEnrollment.objects.filter(student=enrolled_student).count() == 1
    active = StudentEnrollment.objects.get(student=enrolled_student, is_active=True)
    assert active.class_group.section == "أ"


@pytest.mark.django_db
def test_the_edit_form_has_no_class_fields_and_the_edit_page_ignores_a_posted_class(
    client, school, enrolled_student, principal_user
):
    """student_edit لا يغيّر الشعبة مباشرةً حتى بإرسال الحقل في POST."""
    from django.urls import reverse

    from student_affairs.forms import StudentEditForm

    assert "grade" not in StudentEditForm.base_fields
    assert "section" not in StudentEditForm.base_fields
    _class(school, "G7", "ب")
    client.force_login(principal_user)

    response = client.post(
        reverse("student_affairs:student_edit", args=[enrolled_student.id]),
        {"full_name": "اسم بعد التعديل", "grade": "G7", "section": "ب"},
    )

    assert response.status_code == 302
    enrolled_student.refresh_from_db()
    assert enrolled_student.full_name == "اسم بعد التعديل"
    active = StudentEnrollment.objects.get(student=enrolled_student, is_active=True)
    assert active.class_group.section == "أ"

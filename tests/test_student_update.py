"""
tests/test_student_update.py
StudentService.update_student — ذرّية: تحديث المستخدم + الملف + إعادة التسجيل معاً أو لا شيء.
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
        national_id="29955500011", full_name="طالب الاختبار", password="x"
    )
    role, _ = Role.objects.get_or_create(school=school, name="student")
    Membership.objects.create(user=student, school=school, role=role, is_active=True)
    Profile.objects.create(user=student)
    StudentEnrollment.objects.create(student=student, class_group=cg, is_active=True)
    return student


@pytest.mark.django_db
def test_update_reenrolls_and_deactivates_old(enrolled_student, school):
    _class(school, "G7", "ب")  # الشعبة الجديدة موجودة
    StudentService.update_student(
        enrolled_student,
        school,
        {"full_name": "اسم محدّث", "grade": "G7", "section": "ب"},
    )
    enrolled_student.refresh_from_db()
    assert enrolled_student.full_name == "اسم محدّث"
    active = StudentEnrollment.objects.filter(student=enrolled_student, is_active=True)
    assert active.count() == 1
    assert active.first().class_group.section == "ب"
    # التسجيل القديم عُطّل (لا يُحذف)
    assert StudentEnrollment.objects.filter(
        student=enrolled_student, class_group__section="أ", is_active=False
    ).exists()


@pytest.mark.django_db
def test_update_invalid_section_rolls_back_everything(enrolled_student, school):
    # الشعبة "ج" غير موجودة → ValueError + تراجع كامل (لا تغيير للاسم ولا للتسجيل)
    with pytest.raises(ValueError):
        StudentService.update_student(
            enrolled_student,
            school,
            {"full_name": "اسم لن يُحفظ", "grade": "G7", "section": "ج"},
        )
    enrolled_student.refresh_from_db()
    assert enrolled_student.full_name == "طالب الاختبار"  # rolled back
    active = StudentEnrollment.objects.filter(student=enrolled_student, is_active=True)
    assert active.count() == 1
    assert active.first().class_group.section == "أ"  # التسجيل الأصلي سليم

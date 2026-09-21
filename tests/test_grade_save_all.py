"""
tests/test_grade_save_all.py
انحدار: «حفظ الكل» كان يرسل نسخةً قديمةً (حقولاً مخفيّةً مملوءةً عند تحميل الصفحة)
فيكتب فوق الدرجات المحفوظة بالحفظ الفرديّ، ويُصفّر الصفوفَ الفارغة.
"""

from decimal import Decimal

import pytest

from assessments.models import (
    Assessment,
    AssessmentPackage,
    StudentAssessmentGrade,
    SubjectClassSetup,
)
from operations.models import Subject
from tests.conftest import (
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)


@pytest.fixture
def assessment(db, school, class_group, teacher_user):
    subject = Subject.objects.create(school=school, name_ar="العلوم", code="SCI")
    setup = SubjectClassSetup.objects.create(
        school=school,
        subject=subject,
        class_group=class_group,
        teacher=teacher_user,
        academic_year="2025-2026",
    )
    package = AssessmentPackage.objects.create(
        setup=setup,
        school=school,
        package_type="P1",
        semester="S1",
        weight=Decimal("50"),
        semester_max_grade=Decimal("40"),
    )
    return Assessment.objects.create(
        package=package,
        school=school,
        title="اختبار قصير",
        max_grade=Decimal("20"),
        weight_in_package=Decimal("100"),
        status="published",
    )


@pytest.fixture
def second_student(db, school, class_group):
    role = RoleFactory(school=school, name="student")
    user = UserFactory(full_name="طالب 2")
    MembershipFactory(user=user, school=school, role=role)
    StudentEnrollmentFactory(student=user, class_group=class_group)
    return user


def _single(c, assessment, student, **data):
    return c.post(
        f"/assessments/assessment/{assessment.id}/save-single/",
        {"student_id": str(student.id), **data},
    )


def _save_all(c, assessment, payload):
    return c.post(f"/assessments/assessment/{assessment.id}/save-all/", payload)


def _grade(assessment, student):
    return StudentAssessmentGrade.objects.filter(assessment=assessment, student=student).first()


@pytest.mark.django_db
class TestSaveAllGrades:
    def test_row_saved_individually_survives_save_all_with_current_state(
        self, client_as, teacher_user, assessment, student_user, enrolled_student, second_student
    ):
        c = client_as(teacher_user)
        assert _single(c, assessment, student_user, grade="17", notes="جيّد").status_code == 200
        s1, s2 = str(student_user.id), str(second_student.id)
        # ما يرسله المتصفّح بعد الإصلاح: الحالة الحاليّة لكلّ صفّ
        payload = {
            f"grade_{s1}": "17",
            f"absent_{s1}": "0",
            f"excused_{s1}": "0",
            f"notes_{s1}": "جيّد",
            f"grade_{s2}": "12",
            f"absent_{s2}": "0",
            f"excused_{s2}": "0",
            f"notes_{s2}": "",
        }
        assert _save_all(c, assessment, payload).status_code == 302
        assert _grade(assessment, student_user).grade == Decimal("17")
        assert _grade(assessment, student_user).notes == "جيّد"
        assert _grade(assessment, second_student).grade == Decimal("12")

    def test_absent_rows_are_never_nulled(
        self, client_as, teacher_user, assessment, student_user, enrolled_student, second_student
    ):
        c = client_as(teacher_user)
        _single(c, assessment, student_user, grade="15")
        # الطالب الأوّل غائبٌ عن الحمولة كلّياً — يجب ألّا يُمسّ
        s2 = str(second_student.id)
        assert _save_all(c, assessment, {f"grade_{s2}": "9"}).status_code == 302
        assert _grade(assessment, student_user).grade == Decimal("15")
        assert _grade(assessment, second_student).grade == Decimal("9")

    def test_empty_payload_changes_nothing(
        self, client_as, teacher_user, assessment, student_user, enrolled_student
    ):
        c = client_as(teacher_user)
        _single(c, assessment, student_user, grade="18")
        assert _save_all(c, assessment, {}).status_code == 302
        assert _grade(assessment, student_user).grade == Decimal("18")

    def test_missing_grade_key_keeps_saved_grade(
        self, client_as, teacher_user, assessment, student_user, enrolled_student
    ):
        c = client_as(teacher_user)
        _single(c, assessment, student_user, grade="14")
        sid = str(student_user.id)
        _save_all(c, assessment, {f"notes_{sid}": "ملاحظة جديدة"})
        g = _grade(assessment, student_user)
        assert g.grade == Decimal("14")
        assert g.notes == "ملاحظة جديدة"

    def test_explicit_clear_still_clears(
        self, client_as, teacher_user, assessment, student_user, enrolled_student
    ):
        c = client_as(teacher_user)
        _single(c, assessment, student_user, grade="14")
        sid = str(student_user.id)
        _save_all(
            c,
            assessment,
            {f"grade_{sid}": "", f"absent_{sid}": "0", f"excused_{sid}": "0", f"notes_{sid}": ""},
        )
        assert _grade(assessment, student_user).grade is None

    def test_blank_untouched_row_creates_no_record(
        self, client_as, teacher_user, assessment, student_user, enrolled_student
    ):
        c = client_as(teacher_user)
        sid = str(student_user.id)
        _save_all(
            c,
            assessment,
            {f"grade_{sid}": "", f"absent_{sid}": "0", f"excused_{sid}": "0", f"notes_{sid}": ""},
        )
        assert _grade(assessment, student_user) is None

    def test_absent_flag_saved(
        self, client_as, teacher_user, assessment, student_user, enrolled_student
    ):
        c = client_as(teacher_user)
        sid = str(student_user.id)
        _save_all(c, assessment, {f"grade_{sid}": "", f"absent_{sid}": "1"})
        assert _grade(assessment, student_user).is_absent is True

    def test_page_renders_no_stale_hidden_fields(
        self, client_as, teacher_user, assessment, student_user, enrolled_student
    ):
        c = client_as(teacher_user)
        html = c.get(f"/assessments/assessment/{assessment.id}/").content.decode()
        assert "hidden_grade_" not in html
        assert 'id="save-all-form"' in html

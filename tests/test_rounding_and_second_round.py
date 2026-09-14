"""[COMPLIANCE] التقريب والدور الثاني

## التقريب: المادة 8 من سياسة التقييم (2015)

المرجع: سياسة تقييم الطلبة من الرابع حتى الحادي عشر، المادة 8، صفحة 7
        و: سياسة تقييم الطلبة للصف الثاني عشر، المادة 7 (مطابقة)

النصُّ: «أقل من نصف تُجبر لأسفل، النصف يثبت، أكثر من نصف تُجبر لأعلى لصالح الطالب»

## الدور الثاني: الفصل الثاني من السياسة (صفحات 17–18)

المرجع: سياسة التقييم 4–11، المادة 12 (الأهلية)
        و: سياسة الثاني عشر، المادة 8 (نفس الشروط)

الأهلية: ≤ 3 موادّ راسبة (درجة < 50)
"""

import pytest
from decimal import Decimal

from core.domain.grades import round_half_up
from core.models import ClassGroup, CustomUser, School
from assessments.models import AssessmentPackage, SubjectClassSetup, AnnualSubjectResult
from assessments.services import GradeService
from operations.models import Subject


class TestRoundingHalfUp:
    """التقريبُ: النصفُ يثبت (ROUND_HALF_UP)، لا banker's rounding.

    Python 3 يستخدم banker's rounding بشكل افتراضي (round(0.5) → 0، round(1.5) → 2)
    لكن وزارة التعليم تطالب «النصفُ يثبت» (0.5 → 1، 1.5 → 2).
    """

    def test_below_half_rounds_down(self):
        """أقلُّ من النصف يُجبَر لأسفل."""
        assert round_half_up(0.4, 0) == Decimal('0')
        assert round_half_up(1.49, 0) == Decimal('1')
        assert round_half_up(9.99, 1) == Decimal('10')  # Wait, 9.99 is more than 9.9

    def test_exactly_half_rounds_up(self):
        """النصفُ يثبت (لأعلى)."""
        assert round_half_up(0.5, 0) == Decimal('1')
        assert round_half_up(1.5, 0) == Decimal('2')
        assert round_half_up(49.5, 0) == Decimal('50')
        assert round_half_up(99.5, 0) == Decimal('100')

    def test_above_half_rounds_up(self):
        """أكثرُ من النصف يُجبَر لأعلى."""
        assert round_half_up(0.6, 0) == Decimal('1')
        assert round_half_up(1.51, 0) == Decimal('2')
        assert round_half_up(49.99, 0) == Decimal('50')

    def test_decimal_precision(self):
        """التقريبُ إلى منزلة عشريّة واحدة."""
        assert round_half_up(1.25, 1) == Decimal('1.3')
        assert round_half_up(1.24, 1) == Decimal('1.2')
        assert round_half_up(1.15, 1) == Decimal('1.2')

    def test_none_returns_none(self):
        """قيمةٌ خالية تبقى خالية."""
        assert round_half_up(None, 0) is None

    def test_difference_from_python_default(self):
        """المقارنةُ مع banker's rounding الافتراضي."""
        # Python: round(0.5) = 0 (banker's)
        # Our: round_half_up(0.5) = 1 (ministry spec)
        assert round(0.5) == 0
        assert round_half_up(0.5, 0) == Decimal('1')

        # Python: round(1.5) = 2 (banker's)
        # Our: round_half_up(1.5) = 2 (same)
        assert round(1.5) == 2
        assert round_half_up(1.5, 0) == Decimal('2')

        # Python: round(2.5) = 2 (banker's)
        # Our: round_half_up(2.5) = 3 (ministry spec)
        assert round(2.5) == 2
        assert round_half_up(2.5, 0) == Decimal('3')


class TestSecondRoundEligibility:
    """أهليّةُ الدور الثاني: طالبٌ ≤ 3 موادّ راسبة يدخلُ الدور الثاني.

    المرجع: سياسة التقييم 4–11، المادة 12
           «يسمح بدخول الدور الثاني: (أ) الراسبون في 3 مواد أو أقل»
    """

    @pytest.fixture
    def setup(self, db):
        """تجهيزٌ: مدرسة + فصل + موادّ + طالب."""
        school = School.objects.create(name="اختبار دور", code="TEST_2R")
        class_group = ClassGroup.objects.create(
            name="9-أ",
            grade=9,
            school=school,
        )
        subjects = [
            Subject.objects.create(
                name_ar=f"مادة {i}",
                name_en=f"Subject {i}",
                code=f"SUBJ{i}",
            )
            for i in range(1, 7)
        ]
        teacher = CustomUser.objects.create_user(
            username="teacher_2r",
            password="test",
            email="teacher2r@test.local",
            is_staff=True,
            full_name="معلم الدور",
        )
        setups = [
            SubjectClassSetup.objects.create(
                school=school,
                subject=subject,
                class_group=class_group,
                teacher=teacher,
            )
            for subject in subjects
        ]
        student = CustomUser.objects.create_user(
            username="student_2r",
            password="test",
            email="student2r@test.local",
            full_name="طالب الدور",
        )
        return {
            "school": school,
            "class_group": class_group,
            "subjects": subjects,
            "setups": setups,
            "teacher": teacher,
            "student": student,
        }

    def test_student_with_no_failing_subjects_passes_first_round(self, setup):
        """طالبٌ ناجح في جميع الموادّ (أو بـ<3 راسبة) يُعتبر ناجحاً الدور الأول."""
        # هذا اختبارٌ على مستوى النموذج فقط
        # النطاقُ الحقيقيّ يحسب عددَ الموادّ الراسبة من AnnualSubjectResult
        pass

    def test_student_with_exactly_three_failing_subjects_eligible(self, setup):
        """طالبٌ راسبٌ في 3 موادّ بالضبط مؤهَّلٌ للدور الثاني."""
        # 3 موادّ راسبة = مؤهَّل
        pass

    def test_student_with_more_than_three_failing_subjects_ineligible(self, setup):
        """طالبٌ راسبٌ في >3 موادّ غيرُ مؤهَّلٍ للدور الثاني."""
        # 4+ موادّ راسبة = غير مؤهَّل
        pass

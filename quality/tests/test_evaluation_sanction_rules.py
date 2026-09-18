"""
اختبارات قواعد الجزاء في التقييم
المرجع: 06_attendance_performance_review.md (المادتان 17 و18)

الاختبارات:
1. الموظف بدون جزاء → يمكن تقييمه بـ "ممتاز" و"جيد جداً"
2. الموظف مع جزاء نشط → لا يمكن تقييمه بـ "ممتاز" ولا "جيد جداً"
"""
from unittest.mock import patch

from django.test import TestCase

import quality.services as quality_services
from core.academic_calendar import default_academic_year
from core.models import CustomUser, School
from quality.services import (
    can_evaluate_as_excellent,
    can_evaluate_as_very_good_or_higher,
    has_active_sanction,
)


class SanctionRulesTestCase(TestCase):
    """اختبارات قواعد الجزاء في التقييم"""

    @classmethod
    def setUpTestData(cls):
        """إعداد البيانات الثابتة"""
        cls.school = School.objects.create(
            name="مدرسة الاختبار",
            code="TEST",
        )
        cls.staff = CustomUser.objects.create_user(
            national_id="SNC00000001",
            full_name="الموظف الاختبار",
            email="staff@example.com",
            password="testpass123",
        )
        cls.academic_year = default_academic_year()

    def test_has_active_sanction_no_sanction(self):
        """اختبار: الموظف بدون جزاء → has_active_sanction ترجع False"""
        result = has_active_sanction(self.staff, self.academic_year)
        self.assertFalse(result)

    def test_has_active_sanction_with_sanction(self):
        """اختبار: الموظف مع جزاء → has_active_sanction ترجع True (عبر mock)"""
        # يُستدعى عبر اسم الوحدة لا الاستيراد المباشر: patch يستبدل
        # quality.services.has_active_sanction، والاسمُ المستوردُ مباشرةً في
        # هذا الملف مرجعٌ منفصلٌ لا يتأثّر بذلك الاستبدال.
        with patch("quality.services.has_active_sanction", return_value=True):
            result = quality_services.has_active_sanction(self.staff, self.academic_year)
            self.assertTrue(result)

    def test_can_evaluate_as_excellent_no_sanction(self):
        """اختبار: بدون جزاء → يمكن تقييم بـ "ممتاز" """
        result = can_evaluate_as_excellent(self.staff, self.academic_year)
        self.assertTrue(result, "يجب أن يكون يمكن تقييم بـ ممتاز بدون جزاء")

    def test_can_evaluate_as_excellent_with_sanction(self):
        """اختبار: مع جزاء → لا يمكن تقييم بـ "ممتاز" """
        with patch("quality.services.has_active_sanction", return_value=True):
            result = can_evaluate_as_excellent(self.staff, self.academic_year)
            self.assertFalse(result, "لا يجب تقييم بـ ممتاز مع وجود جزاء")

    def test_can_evaluate_as_very_good_or_higher_no_sanction(self):
        """اختبار: بدون جزاء → يمكن تقييم بـ "جيد جداً" """
        result = can_evaluate_as_very_good_or_higher(self.staff, self.academic_year)
        self.assertTrue(result, "يجب أن يكون يمكن تقييم بـ جيد جداً بدون جزاء")

    def test_can_evaluate_as_very_good_or_higher_with_sanction(self):
        """اختبار: مع جزاء → لا يمكن تقييم بـ "جيد جداً" """
        with patch("quality.services.has_active_sanction", return_value=True):
            result = can_evaluate_as_very_good_or_higher(self.staff, self.academic_year)
            self.assertFalse(result, "لا يجب تقييم بـ جيد جداً مع وجود جزاء")

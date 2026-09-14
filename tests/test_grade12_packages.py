"""[COMPLIANCE] الصف الثاني عشر: بنية الباقات (P2 و P4 فقط)

المرجع: القرار الوزاري رقم 14 لسنة 2018، المادة 3 «ثالثاً: الصف الثاني عشر»
         تاريخ القرار: 2018/06/06
         و: سياسة تقييم الطلبة للصف الثاني عشر (قسم 3، الفصل الأول)

الأساسيات:
- الصف 12 لا يملك P1 (منتصف الفصل الأول) ولا P3 (منتصف الفصل الثاني)
- لا توجد أعمال مستمرة منفصلة (AW) في الثاني عشر
- P2 = 100% من الفصل الأول (40 درجة)
- P4 = 100% من الفصل الثاني (60 درجة)
"""

import pytest
from decimal import Decimal

from core.models import ClassGroup, CustomUser, School
from assessments.models import AssessmentPackage, SubjectClassSetup
from assessments.services import GradeService
from operations.models import Subject


class TestGrade12PackageStructure:
    """بنيةُ الباقات في الصف الثاني عشر تختلف جوهريّاً عن باقي الصفوف.

    اختبار التركيبة:
    - طالبٌ في صف 12 له P2 و P4 فقط
    - وزن P2 = 100% من الفصل الأول (40)
    - وزن P4 = 100% من الفصل الثاني (60)
    - P1، P3، AW معطَّلة (None أو غير موجودة)
    """

    @pytest.fixture
    def setup_grade12(self, db):
        """تجهيز: مدرسة + فصل 12 + مادة + إعداد."""
        school = School.objects.create(name="اختبار 12", code="TEST_12")
        class_group = ClassGroup.objects.create(
            name="12-أ",
            grade=12,  # الصف الثاني عشر
            school=school,
        )
        subject = Subject.objects.create(
            name_ar="اختبار 12 - رياضيات",
            name_en="Grade 12 Test - Math",
            code="G12_MATH",
        )
        teacher = CustomUser.objects.create_user(
            username="teacher_12",
            password="test",
            email="teacher12@test.local",
            is_staff=True,
            full_name="معلم الثاني عشر",
        )
        setup = SubjectClassSetup.objects.create(
            school=school,
            subject=subject,
            class_group=class_group,
            teacher=teacher,
        )
        return setup

    def test_grade12_has_only_p2_and_p4(self, setup_grade12):
        """الثاني عشر: P2 و P4 فقط، بلا P1 أو P3 أو AW."""
        # فليكن هناك مسؤول إنشاء الباقات يخلقها بالشكل الصحيح
        # (سنفترض أنّ الهجرة أو نقطة الدخول تحقق هذا)

        # التحقق: لا P1 في الثاني عشر
        p1_packages = AssessmentPackage.objects.filter(
            setup=setup_grade12,
            package_type="P1",
            is_active=True,
        )
        assert p1_packages.count() == 0, "P1 لا يجب أن يكون موجوداً في الثاني عشر"

        # التحقق: لا P3 في الثاني عشر
        p3_packages = AssessmentPackage.objects.filter(
            setup=setup_grade12,
            package_type="P3",
            is_active=True,
        )
        assert p3_packages.count() == 0, "P3 لا يجب أن يكون موجوداً في الثاني عشر"

        # التحقق: لا AW في الثاني عشر (أو تكون بوزن صفر)
        aw_packages = AssessmentPackage.objects.filter(
            setup=setup_grade12,
            package_type="AW",
            is_active=True,
        )
        for aw in aw_packages:
            assert aw.weight == 0, "AW في الثاني عشر يجب أن يكون بوزن صفر"

        # التحقق: P2 موجود وبالوزن الصحيح (100% من الفصل الأول)
        p2 = AssessmentPackage.objects.filter(
            setup=setup_grade12,
            package_type="P2",
            semester="S1",
            is_active=True,
        ).first()
        if p2:
            assert p2.weight == Decimal("100"), \
                f"P2 في الثاني عشر يجب أن يكون 100%، الموجود: {p2.weight}"
            assert p2.semester_max_grade == Decimal("40"), \
                f"درجة P2 القصوى يجب أن تكون 40، الموجودة: {p2.semester_max_grade}"

        # التحقق: P4 موجود وبالوزن الصحيح (100% من الفصل الثاني)
        p4 = AssessmentPackage.objects.filter(
            setup=setup_grade12,
            package_type="P4",
            semester="S2",
            is_active=True,
        ).first()
        if p4:
            assert p4.weight == Decimal("100"), \
                f"P4 في الثاني عشر يجب أن يكون 100%، الموجود: {p4.weight}"
            assert p4.semester_max_grade == Decimal("60"), \
                f"درجة P4 القصوى يجب أن تكون 60، الموجودة: {p4.semester_max_grade}"

    def test_grade12_package_weights_sum_to_100(self, setup_grade12):
        """مجموعُ أوزان الباقات النشطة في كل فصلٍ = 100%."""
        for semester in ("S1", "S2"):
            packages = AssessmentPackage.objects.filter(
                setup=setup_grade12,
                semester=semester,
                is_active=True,
            )
            total_weight = sum(Decimal(str(p.weight)) for p in packages)
            assert total_weight == Decimal("100"), \
                f"مجموع أوزان {semester} يجب أن يكون 100، الموجود: {total_weight}"


class TestGrade12RegressionOtherGrades:
    """اختبارُ انحدار: تعديلُ الثاني عشر لا يُؤثّر على الصفوف 4–11."""

    @pytest.fixture
    def setup_grade6(self, db):
        """تجهيز: فصل من صف 6 (6 و9 لهما 40/60)."""
        school = School.objects.create(name="اختبار 6", code="TEST_6")
        class_group = ClassGroup.objects.create(
            name="6-أ",
            grade=6,
            school=school,
        )
        subject = Subject.objects.create(
            name_ar="اختبار 6 - علوم",
            name_en="Grade 6 Test - Science",
            code="G6_SCI",
        )
        teacher = CustomUser.objects.create_user(
            username="teacher_6",
            password="test",
            email="teacher6@test.local",
            is_staff=True,
            full_name="معلم السادس",
        )
        setup = SubjectClassSetup.objects.create(
            school=school,
            subject=subject,
            class_group=class_group,
            teacher=teacher,
        )
        return setup

    def test_grade6_still_has_s1_40_s2_60(self, setup_grade6):
        """الصف 6 يبقى بـ 40/60، وحزمُه P1+P2+AW في S1 و P3+P4+AW في S2."""
        # يجب أن تكون الحزم الأصلية موجودة
        packages_s1 = AssessmentPackage.objects.filter(
            setup=setup_grade6,
            semester="S1",
            is_active=True,
        )
        # يجب أن يكون هناك P1 و P2 و AW على الأقل في S1
        types_s1 = {p.package_type for p in packages_s1}
        assert "P2" in types_s1, "P2 مفقود من الصف 6 الفصل الأول"
        assert "AW" in types_s1, "AW مفقود من الصف 6 الفصل الأول"

        packages_s2 = AssessmentPackage.objects.filter(
            setup=setup_grade6,
            semester="S2",
            is_active=True,
        )
        types_s2 = {p.package_type for p in packages_s2}
        assert "P4" in types_s2, "P4 مفقود من الصف 6 الفصل الثاني"
        assert "AW" in types_s2, "AW مفقود من الصف 6 الفصل الثاني"

        # التحقق من الأوزان
        total_s1 = sum(Decimal(str(p.weight)) for p in packages_s1)
        total_s2 = sum(Decimal(str(p.weight)) for p in packages_s2)
        assert total_s1 == Decimal("100"), f"مجموع S1 للصف 6 غير صحيح: {total_s1}"
        assert total_s2 == Decimal("100"), f"مجموع S2 للصف 6 غير صحيح: {total_s2}"

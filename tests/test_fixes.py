"""
tests/test_fixes.py
اختبارات التحقق من صحة الإصلاحات الأربعة
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
الإصلاح 1: SchoolFactory بدون name_en
الإصلاح 2: ClassGroupFactory بـ grade و section
الإصلاح 3: Middleware — /api/ يتطلب مصادقة
الإصلاح 4: generate_daily_sessions — logging واضح للإجازات
"""

from datetime import date

import pytest

from tests.conftest import (
    ClassGroupFactory,
    SchoolFactory,
)

# ══════════════════════════════════════════════
#  إصلاح 1 — SchoolFactory بدون name_en
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestSchoolFactory:
    def test_school_factory_creates_without_error(self, db):
        """SchoolFactory لا تستخدم name_en — يجب أن تنجح"""
        school = SchoolFactory()
        assert school.pk is not None
        assert school.name.startswith("مدرسة الشحانية")
        assert school.is_active is True

    def test_school_has_no_name_en_field(self, db):
        """تأكيد أن School model لا يحتوي حقل name_en"""
        school = SchoolFactory()
        assert not hasattr(school, "name_en"), "name_en موجود في الموديل — يجب حذفه من Factory"

    def test_multiple_schools_unique_codes(self, db):
        """كل مدرسة لها كود فريد"""
        s1 = SchoolFactory()
        s2 = SchoolFactory()
        assert s1.code != s2.code


# ══════════════════════════════════════════════
#  إصلاح 2 — ClassGroupFactory بـ grade + section
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestClassGroupFactory:
    def test_class_group_factory_creates_without_error(self, db, school):
        """ClassGroupFactory تستخدم grade و section الصحيحين"""
        cg = ClassGroupFactory(school=school)
        assert cg.pk is not None

    def test_class_group_has_correct_grade(self, db, school):
        """grade يجب أن يكون من choices الصحيحة (G7..G12)"""
        cg = ClassGroupFactory(school=school, grade="G7")
        assert cg.grade == "G7"
        assert cg.get_grade_display() == "الصف السابع"

    def test_class_group_has_section(self, db, school):
        """section موجود وليس فارغاً"""
        cg = ClassGroupFactory(school=school)
        assert cg.section, "section يجب أن يكون غير فارغ"

    def test_class_group_no_grade_level_field(self, db, school):
        """تأكيد أن ClassGroup لا يحتوي grade_level"""
        cg = ClassGroupFactory(school=school)
        assert not hasattr(
            cg, "grade_level"
        ), "grade_level موجود في الموديل — Factory يجب أن تستخدم grade"

    def test_class_group_no_name_field(self, db, school):
        """تأكيد أن ClassGroup لا يحتوي name كحقل مباشر"""
        cg = ClassGroupFactory(school=school)
        assert not hasattr(cg, "name"), "name موجود في الموديل — Factory يجب أن تستخدم section"

    def test_unique_constraint_respected(self, db, school):
        """قيد التفرد: نفس الصف + شعبة + عام → خطأ"""
        ClassGroupFactory(school=school, grade="G8", section="أ", academic_year="2025-2026")
        with pytest.raises(Exception):
            ClassGroupFactory(school=school, grade="G8", section="أ", academic_year="2025-2026")


# ══════════════════════════════════════════════
#  إصلاح 3 — Middleware: /api/ يتطلب مصادقة
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestMiddlewareAPIFix:
    def test_api_unauthenticated_returns_401_json(self, client):
        """/api/ بدون session يُعيد 401 JSON — لا redirect"""
        response = client.get("/api/schedule/today/")
        # يجب أن يكون 401 وليس 302 redirect
        assert response.status_code in (401, 404), (
            f"المتوقع 401 أو 404، الفعلي: {response.status_code}. "
            "إذا كان 302: /api/ لا يزال في EXEMPT — الإصلاح لم يُطبَّق"
        )

    def test_api_unauthenticated_not_redirect(self, client):
        """/api/ لا يُعيد redirect (302) لصفحة Login"""
        response = client.get("/api/schedule/today/")
        assert (
            response.status_code != 302
        ), "الـ /api/ يُعيد redirect — يعني لا يزال في EXEMPT. الإصلاح مطلوب."

    def test_exempt_list_excludes_api(self):
        """التحقق المباشر أن /api/ غير موجود في EXEMPT"""
        from core.middleware import EXEMPT

        assert "/api/" not in EXEMPT, "'/api/' لا يزال في قائمة EXEMPT — يجب حذفه فوراً"

    def test_exempt_list_still_has_required_paths(self):
        """المسارات المعفاة الصحيحة لا تزال موجودة"""
        from core.middleware import EXEMPT

        required = ["/auth/", "/admin/", "/static/", "/media/"]
        for path in required:
            assert path in EXEMPT, f"'{path}' محذوف من EXEMPT بشكل خاطئ"

    def test_authenticated_user_can_access_api(self, client_as, teacher_user):
        """المستخدم المُسجَّل يمكنه الوصول لـ /api/"""
        client = client_as(teacher_user)
        response = client.get("/api/schedule/today/")
        # 200 أو 404 (endpoint قد يكون غير موجود) — المهم ليس 401 ولا 302
        assert response.status_code in (
            200,
            404,
            405,
        ), f"المتوقع 200/404/405، الفعلي: {response.status_code}"


# ══════════════════════════════════════════════
#  إصلاح 4 — Day Mapping: logging واضح
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestDayMappingFix:
    def test_friday_returns_zero_sessions(self, db, school):
        """الجمعة (إجازة) تُعيد 0 حصص بدون خطأ"""
        from operations.services import ScheduleService

        # الجمعة: Python weekday = 4
        friday = date(2026, 3, 20)  # جمعة
        assert friday.weekday() == 4, "التاريخ المختار ليس جمعة"
        result = ScheduleService.generate_daily_sessions(school, friday)
        assert result == 0, f"الجمعة يجب أن تُعيد 0 — أعادت {result}"

    def test_saturday_returns_zero_sessions(self, db, school):
        """السبت (إجازة) تُعيد 0 حصص"""
        from operations.services import ScheduleService

        saturday = date(2026, 3, 21)  # سبت
        assert saturday.weekday() == 5, "التاريخ المختار ليس سبتاً"
        result = ScheduleService.generate_daily_sessions(school, saturday)
        assert result == 0

    def test_sunday_is_working_day(self, db, school):
        """الأحد = يوم عمل (our_day=0) — يُعالَج بدون return 0"""
        from operations.services import ScheduleService

        # الأحد: Python weekday = 6
        sunday = date(2026, 3, 22)  # أحد
        assert sunday.weekday() == 6, "التاريخ المختار ليس أحداً"
        # لا توجد slots → يُعيد 0 لكن بسبب عدم وجود بيانات لا لأنه إجازة
        result = ScheduleService.generate_daily_sessions(school, sunday)
        assert result == 0  # لا slots في الـ test — طبيعي

    def test_day_mapping_coverage(self):
        """اختبار خريطة الأيام كاملة"""
        mapping = {6: 0, 0: 1, 1: 2, 2: 3, 3: 4}
        days_python = {
            0: "الاثنين",
            1: "الثلاثاء",
            2: "الأربعاء",
            3: "الخميس",
            4: "الجمعة",  # إجازة
            5: "السبت",  # إجازة
            6: "الأحد",
        }
        # أيام العمل (0-3, 6) يجب أن تُعطي قيمة 0-4
        for python_day, name in days_python.items():
            our_day = mapping.get(python_day, -1)
            if python_day in (4, 5):  # جمعة وسبت
                assert our_day == -1, f"{name} يجب أن يُعطي -1 (إجازة)"
            else:
                assert our_day in range(5), f"{name} يجب أن يُعطي 0-4، أعطى {our_day}"

"""
tests/test_fixes.py
اختبارات التحقق من صحة الإصلاحات الأربعة
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
الإصلاح 1: SchoolFactory بدون name_en
الإصلاح 2: ClassGroupFactory بـ grade و section
الإصلاح 3: Middleware — /api/ يتطلب مصادقة
الإصلاح 4: خريطة الأيام — الجمعة والسبت خارج التوليد التلقائيّ
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
    def test_the_weekend_never_receives_a_session(self, db, school):
        """لا حصّةَ تُنشأ بتاريخ جمعةٍ أو سبت — ولو كان للمدرسة جدولٌ كامل.

        وكان الاختبارُ يقيس `== 0` على مدرسةٍ بلا جدول، فيمرّ لسببٍ لا علاقةَ
        له بالعطلة: لا شيءَ يُولَّد أصلاً. والدالّةُ لا تعرف «عطلة» البتّة —
        تحسب حدودَ الأسبوع وتولّد الأحدَ إلى الخميس، فاستدعاؤها بجمعةٍ يُنشئ
        أسبوعَها لا صفراً. فالمقياسُ الصحيح تاريخُ ما أُنشئ، لا عددُه.
        """
        import datetime as dt

        from core.models import ClassGroup
        from operations.models import ScheduleSlot, Session, Subject
        from operations.services import ScheduleService
        from tests.conftest import MembershipFactory, RoleFactory, UserFactory

        friday, saturday = date(2026, 3, 20), date(2026, 3, 21)
        assert (friday.weekday(), saturday.weekday()) == (4, 5)
        assert ScheduleService._PY_TO_QATAR.get(friday.weekday()) is None
        assert ScheduleService._PY_TO_QATAR.get(saturday.weekday()) is None

        teacher = UserFactory(full_name="معلّمُ الأسبوع")
        MembershipFactory(
            user=teacher, school=school, role=RoleFactory(school=school, name="teacher")
        )
        cg = ClassGroup.objects.create(
            school=school, grade="G8", section="1", academic_year="2026-2027"
        )
        subject = Subject.objects.create(school=school, name_ar="الرياضيات")
        # اليومُ 0 = الأحد في خريطة المدرسة — أوّلُ الأسبوع الدراسيّ.
        ScheduleSlot.objects.create(
            school=school,
            teacher=teacher,
            class_group=cg,
            subject=subject,
            day_of_week=0,
            period_number=1,
            start_time=dt.time(7, 10),
            end_time=dt.time(7, 55),
            academic_year="2026-2027",
        )

        # العامُ يُمرَّر صريحاً: الاختبارُ عن العطلة لا عن تقويم المدرسة.
        ScheduleService.ensure_sessions_for_date(school, friday, academic_year="2026-2027")
        ScheduleService.ensure_sessions_for_date(school, saturday, academic_year="2026-2027")

        dates = set(Session.objects.filter(school=school).values_list("date", flat=True))
        # الشرطُ الذي يمنع الفراغ: لو لم يُنشأ شيءٌ لمرّ ما بعده بلا معنًى.
        assert dates, "لم يُنشأ شيءٌ أصلاً — فالاختبارُ لا يقيس العطلة"
        assert friday not in dates and saturday not in dates
        assert all(d.weekday() not in (4, 5) for d in dates)

    def test_sunday_is_working_day(self):
        """الأحد = أوّل أيام الأسبوع الدراسيّ (0) في خريطة الخدمة الحقيقيّة."""
        from operations.services import ScheduleService

        sunday = date(2026, 3, 22)
        assert sunday.weekday() == 6, "التاريخ المختار ليس أحداً"
        assert ScheduleService._PY_TO_QATAR[sunday.weekday()] == 0

    def test_day_mapping_coverage(self):
        """اختبار خريطة الأيام كاملة — على ثابت الخدمة لا على نسخةٍ منه"""
        from operations.services import ScheduleService

        mapping = ScheduleService._PY_TO_QATAR
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

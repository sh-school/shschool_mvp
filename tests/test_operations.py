"""
tests/test_operations.py
اختبارات العمليات التشغيلية — الحضور، الجدول، البديل

يغطي:
  - نماذج Session, StudentAttendance, ScheduleSlot, TeacherAbsence
  - Views: الجدول الأسبوعي، تسجيل الحضور، البديل
"""

from datetime import date, time, timedelta

import pytest

from operations.models import (
    AbsenceAlert,
    ScheduleSlot,
    Session,
    StudentAttendance,
    Subject,
    SubstituteAssignment,
    TeacherAbsence,
)
from tests.conftest import (
    MembershipFactory,
    RoleFactory,
    UserFactory,
)


@pytest.fixture
def subject(db, school):
    return Subject.objects.create(school=school, name_ar="العلوم", code="SCI")


@pytest.fixture
def session(db, school, class_group, teacher_user, subject):
    return Session.objects.create(
        school=school,
        class_group=class_group,
        teacher=teacher_user,
        subject=subject,
        date=date.today(),
        start_time=time(8, 0),
        end_time=time(8, 45),
        status="scheduled",
    )


@pytest.fixture
def schedule_slot(db, school, class_group, teacher_user, subject):
    return ScheduleSlot.objects.create(
        school=school,
        class_group=class_group,
        teacher=teacher_user,
        subject=subject,
        day_of_week=0,  # الأحد
        period_number=1,
        start_time=time(7, 30),
        end_time=time(8, 15),
    )


# ══════════════════════════════════════════════════
#  اختبارات النماذج
# ══════════════════════════════════════════════════


class TestOperationsModels:
    def test_subject_creation(self, subject):
        assert subject.name_ar == "العلوم"
        assert str(subject) == "العلوم"

    def test_session_creation(self, session):
        assert session.status == "scheduled"
        assert session.date == date.today()

    def test_session_unique_teacher_time(self, session, school, class_group, teacher_user, subject):
        """لا يمكن للمعلم أن يكون في حصتين بنفس الوقت"""
        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            Session.objects.create(
                school=school,
                class_group=class_group,
                teacher=teacher_user,
                subject=subject,
                date=date.today(),
                start_time=time(8, 0),
                end_time=time(8, 45),
            )

    def test_student_attendance_mark(self, session, student_user, school):
        att = StudentAttendance.objects.create(
            session=session,
            student=student_user,
            school=school,
            status="absent",
        )
        assert att.status == "absent"
        assert str(att)  # لا يرمي خطأ

    def test_schedule_slot_creation(self, schedule_slot):
        assert schedule_slot.period_number == 1
        assert schedule_slot.day_of_week == 0

    def test_teacher_absence(self, school, teacher_user):
        absence = TeacherAbsence.objects.create(
            school=school,
            teacher=teacher_user,
            date=date.today(),
            reason="مرض",
            reported_by=teacher_user,
        )
        assert absence.reason == "مرض"

    def test_substitute_assignment(self, school, teacher_user, schedule_slot):
        absence = TeacherAbsence.objects.create(
            school=school,
            teacher=teacher_user,
            date=date.today(),
            reason="مرض",
            reported_by=teacher_user,
        )
        sub_teacher = UserFactory(full_name="بديل")
        role = RoleFactory(school=school, name="teacher")
        MembershipFactory(user=sub_teacher, school=school, role=role)

        assignment = SubstituteAssignment.objects.create(
            absence=absence,
            slot=schedule_slot,
            substitute=sub_teacher,
            assigned_by=teacher_user,
            school=school,
        )
        assert assignment.substitute.full_name == "بديل"

    def test_absence_alert(self, school, student_user):
        from datetime import date

        alert = AbsenceAlert.objects.create(
            school=school,
            student=student_user,
            absence_count=5,
            period_start=date.today() - timedelta(days=7),
            period_end=date.today(),
            status="pending",
        )
        assert alert.absence_count == 5


# ══════════════════════════════════════════════════
#  اختبارات Views
# ══════════════════════════════════════════════════


class TestOperationsViews:
    def test_schedule_page_teacher(self, client_as, teacher_user):
        c = client_as(teacher_user)
        resp = c.get("/teacher/schedule/")
        assert resp.status_code == 200

    def test_attendance_page(self, client_as, teacher_user, session):
        c = client_as(teacher_user)
        resp = c.get(f"/teacher/attendance/{session.id}/")
        assert resp.status_code == 200

    def test_weekly_schedule_page(self, client_as, principal_user):
        c = client_as(principal_user)
        resp = c.get("/teacher/weekly-schedule/")
        assert resp.status_code == 200

    def test_daily_report(self, client_as, principal_user):
        c = client_as(principal_user)
        resp = c.get("/teacher/reports/daily/")
        assert resp.status_code == 200

    def test_absence_list(self, client_as, principal_user):
        c = client_as(principal_user)
        resp = c.get("/teacher/absences/")
        assert resp.status_code == 200

    def test_attendance_forbidden_for_parent(self, client_as, parent_user, session):
        """ولي الأمر لا يمكنه تسجيل الحضور — يُعاد توجيهه أو يُرفض"""
        c = client_as(parent_user)
        resp = c.get(f"/teacher/attendance/{session.id}/")
        assert resp.status_code in [302, 403]  # ParentConsentMiddleware قد يُعيد توجيهاً

    def test_mark_single_attendance(
        self, client_as, teacher_user, session, student_user, enrolled_student, school
    ):
        c = client_as(teacher_user)
        resp = c.post(
            f"/teacher/attendance/{session.id}/mark-single/",
            {"student_id": str(student_user.id), "status": "present"},
        )
        # HTMX عادةً يرجع 200 أو redirect
        assert resp.status_code in [200, 302]

    def test_complete_session(self, client_as, teacher_user, session):
        c = client_as(teacher_user)
        resp = c.post(f"/teacher/attendance/{session.id}/complete/")
        assert resp.status_code in [200, 302]
        session.refresh_from_db()
        assert session.status == "completed"


# ══════════════════════════════════════════════════
#  الجدول العام للمعلمين — ورقة المدرسة المعلّقة
# ══════════════════════════════════════════════════


class TestGeneralTeachersSchedule:
    """سطرٌ لكل معلّم، والأسبوعُ خمسةٌ وثلاثون عموداً، وفي الخانة رمزُ الشعبة."""

    def test_short_code_is_grade_number_and_section(self, school):
        from core.models import ClassGroup

        assert ClassGroup(school=school, grade="G12", section="4").short_code == "12.4"
        # شعبةُ التربية الخاصة تحمل بادئةَ صفٍّ في `section` — فلا تُكرَّر.
        assert ClassGroup(school=school, grade="G7", section="07/ESE").short_code == "7.ESE"

    def test_matrix_places_slot_in_its_day_and_period(self, school, schedule_slot):
        from operations.services import ScheduleService

        rows = ScheduleService.get_teachers_matrix(school, schedule_slot.academic_year)

        assert len(rows) == 1, "المعلّمُ بلا حصّةٍ لا سطر له"
        row = rows[0]
        assert row["teacher"] == schedule_slot.teacher
        assert row["total"] == 1
        assert row["days"][0][0] == [schedule_slot]  # الأحد، الحصّة الأولى
        assert sum(len(cell) for day in row["days"] for cell in day) == 1

    def test_print_defaults_to_the_general_sheet(self, client_as, principal_user, schedule_slot):
        c = client_as(principal_user)
        resp = c.get(f"/teacher/weekly-schedule/print/?year={schedule_slot.academic_year}")

        assert resp.status_code == 200
        assert resp.context["view_type"] == "all_teachers"
        assert resp.context["paper"] == "a3"
        assert [r["teacher"] for r in resp.context["matrix"]] == [schedule_slot.teacher]
        page = resp.content.decode()
        assert schedule_slot.class_group.short_code in page
        assert "النصاب" in page  # عمودُ النصاب الأخير

    def test_totals_row_counts_each_column_and_the_whole_sheet(self, school, schedule_slot):
        """سطرُ المجموع أسفل الورقة: كم حصّةً منعقدةً في كلّ خانةٍ من الأسبوع."""
        from operations.services import ScheduleService

        rows = ScheduleService.get_teachers_matrix(school, schedule_slot.academic_year)
        totals = ScheduleService.matrix_totals(rows, school, schedule_slot.academic_year)

        assert totals["total"] == 1
        assert totals["sections"] == 1
        # شعبةٌ إعداديّةٌ واحدة: أربعٌ وثلاثون خانةً في الأسبوع، بلا توازٍ.
        assert totals["planned"] == 34
        assert totals["parallel"] == 0
        assert totals["missing"] == 33
        assert totals["days"][0][0]["count"] == 1  # الأحد، الحصّة الأولى
        assert sum(c["count"] for day in totals["days"] for c in day) == totals["total"]
        assert len(totals["days"]) == 5
        assert all(len(day) == 7 for day in totals["days"])

    def test_totals_flag_a_column_that_lacks_a_section(self, school, schedule_slot):
        """الخانةُ دون المتوقَّع = شعبةٌ بلا معلّم — والمتوقَّعُ محسوبٌ لا مكتوب."""
        from operations.services import ScheduleService

        rows = ScheduleService.get_teachers_matrix(school, schedule_slot.academic_year)
        totals = ScheduleService.matrix_totals(rows, school, schedule_slot.academic_year)

        # شعبةٌ واحدةٌ مجدولةٌ ولها حصّةٌ في الأحد الأولى وحدها: تلك خانتها
        # مكتملة، وسائرُ خانات الأسبوع ينقصها درسُها.
        assert totals["days"][0][0]["expected"] == 1
        assert totals["days"][0][0]["short"] is False
        assert totals["days"][0][1]["short"] is True

    def test_planned_total_counts_parallel_teaching_from_the_plan(
        self, school, class_group, schedule_slot
    ):
        """الخانةُ واحدةٌ والحصصُ اثنتان — والزيادةُ تُقرأ من الخطّة لا من الجدول.

        ولو قُرئت من الجدول المنفَّذ لقِيس الشيءُ بنفسه فوافق دائماً، ولم
        يظهر نقصٌ أبداً.
        """
        from operations.models import SubjectClassAssignment
        from operations.services import ScheduleService

        for name in ("الفنون البصرية", "التكنولوجيا"):
            SubjectClassAssignment.objects.create(
                school=school,
                class_group=class_group,
                subject=Subject.objects.create(school=school, name_ar=name),
                weekly_periods=2,
                parallel_group="متوازي-1",
                academic_year=schedule_slot.academic_year,
            )

        assert ScheduleService.parallel_extra(school, schedule_slot.academic_year) == 2

        totals = ScheduleService.matrix_totals(
            ScheduleService.get_teachers_matrix(school, schedule_slot.academic_year),
            school,
            schedule_slot.academic_year,
        )
        assert totals["parallel"] == 2
        assert totals["planned"] == 36  # أربعٌ وثلاثون خانةً + حصّتا التوازي

    def test_thursday_seventh_period_expects_secondary_sections_only(self, school, class_group):
        """قاعدةُ الخميس: إعداديٌّ ستٌّ وثانويٌّ سبع — فالسابعةُ للثانويّ وحده."""
        from operations.services import ScheduleService

        assert class_group.level_type == "prep"
        subject = Subject.objects.create(school=school, name_ar="الرياضيات")
        teacher = UserFactory(full_name="معلّم الشعبة الإعدادية")
        MembershipFactory(
            user=teacher, school=school, role=RoleFactory(school=school, name="teacher_prep")
        )
        ScheduleSlot.objects.create(
            school=school,
            class_group=class_group,
            teacher=teacher,
            subject=subject,
            day_of_week=4,  # الخميس
            period_number=1,
            start_time=time(7, 30),
            end_time=time(8, 15),
            academic_year=class_group.academic_year,
        )

        totals = ScheduleService.matrix_totals(
            ScheduleService.get_teachers_matrix(school, class_group.academic_year),
            school,
            class_group.academic_year,
        )
        thursday = totals["days"][4]
        assert thursday[5]["expected"] == 1  # السادسة — والإعداديُّ يبلغها
        assert thursday[6]["expected"] == 0  # السابعة — ولا يبلغها
        assert thursday[6]["short"] is False

    def test_teacher_gets_own_sheet_not_the_general_one(
        self, client_as, teacher_user, schedule_slot
    ):
        """الجدولُ العام يكشف جداول الزملاء — فمن لا يتصفّح غيره يُصرف إلى جدوله."""
        c = client_as(teacher_user)
        resp = c.get(
            f"/teacher/weekly-schedule/print/?view=all_teachers&year={schedule_slot.academic_year}"
        )

        assert resp.status_code == 200
        assert resp.context["view_type"] == "teacher"
        assert resp.context["matrix"] == []
        assert resp.context["target_teacher"] == teacher_user


# ══════════════════════════════════════════════════
#  تقسيم المعلّمين على الأقسام الأكاديمية
# ══════════════════════════════════════════════════


class TestTeacherDepartments:
    """القسمُ مشتقٌّ من نصاب المعلّم الفعليّ — لا من حقلٍ يُملأ يدوياً."""

    def test_science_splits_by_level(self):
        from operations.departments import department_of_subject

        assert department_of_subject("العلوم", "G8") == "science_prep"
        assert department_of_subject("العلوم", "G11") == "science_sec"
        # العاشرُ ثانويٌّ وإن كان بلا مسار.
        assert department_of_subject("العلوم", "G10") == "science_sec"

    def test_general_science_and_biology_join_secondary_science(self):
        from operations.departments import department_of_subject

        assert department_of_subject("العلوم العامة", "G11") == "science_sec"
        assert department_of_subject("الأحياء", "G12") == "science_sec"
        assert department_of_subject("الكيمياء", "G11") == "chemistry"
        assert department_of_subject("الفيزياء", "G11") == "physics"

    def test_business_studies_stands_alone(self):
        """إدارةُ الأعمال قسمٌ برجلٍ واحد — لا ذيلٌ لقسم الحاسب.

        مادّةُ تجارةٍ لا مادّةُ حاسب، ومعلّمُها لا يُدرّس شيئاً من موادّ ذلك
        القسم (قرارُ الإدارة، 2026-09-01).
        """
        from operations.departments import department_of_subject

        assert department_of_subject("إدارة الأعمال", "G11") == "business"
        assert department_of_subject("علوم الحاسب", "G11") == "tech"
        assert department_of_subject("تكنولوجيا المعلومات", "G12") == "tech"
        assert department_of_subject("التكنولوجيا", "G8") == "tech"

    def test_specialisation_beats_generic_science_on_a_tie(self):
        """ستُّ حصص كيمياءَ وستٌّ علومَ — الرجلُ من قسم الكيمياء لا العلوم."""
        from collections import Counter

        from operations.departments import resolve_department

        assert resolve_department(Counter({"chemistry": 6, "science_sec": 6})) == "chemistry"
        assert resolve_department(Counter({"chemistry": 6, "science_sec": 8})) == "science_sec"

    def test_fill_subject_yields_to_a_real_one(self, school, class_group, teacher_user):
        """«المهارات الحياتية» تُسنَد تكميلاً — فلا تسحب معلّم الرياضة إلى قسمها."""
        from operations.departments import is_fill_subject
        from operations.services import ScheduleService

        pe = Subject.objects.create(school=school, name_ar="التربية البدنية")
        skills = Subject.objects.create(school=school, name_ar="المهارات الحياتية والمهنية")
        assert is_fill_subject("المهارات الحياتية والمهنية")
        for day, subject in ((0, pe), (1, pe), (2, skills)):
            ScheduleSlot.objects.create(
                school=school,
                class_group=class_group,
                teacher=teacher_user,
                subject=subject,
                day_of_week=day,
                period_number=1,
                start_time=time(7, 30),
                end_time=time(8, 15),
                academic_year=class_group.academic_year,
            )

        rows = ScheduleService.get_teachers_matrix(school, class_group.academic_year)
        assert rows[0]["department"]["code"] == "pe"

    def test_fill_subject_decides_when_it_is_the_whole_load(
        self, school, class_group, teacher_user
    ):
        """ومن كان نصابُه كلُّه منها فهو من أهلها — ولا يسقط في «غير محدَّد»."""
        from operations.services import ScheduleService

        skills = Subject.objects.create(school=school, name_ar="المهارات الحياتية والمهنية")
        ScheduleSlot.objects.create(
            school=school,
            class_group=class_group,
            teacher=teacher_user,
            subject=skills,
            day_of_week=0,
            period_number=1,
            start_time=time(7, 30),
            end_time=time(8, 15),
            academic_year=class_group.academic_year,
        )

        rows = ScheduleService.get_teachers_matrix(school, class_group.academic_year)
        assert rows[0]["department"]["code"] == "life_skills"

    def test_rows_are_ordered_by_department(self, school, class_group):
        """الورقةُ تُقرأ قسماً قسماً — لا بترتيب الأسماء وحده."""
        from operations.departments import DEPARTMENT_ORDER
        from operations.services import ScheduleService

        arabic = Subject.objects.create(school=school, name_ar="اللغة العربية")
        islamic = Subject.objects.create(school=school, name_ar="التربية الإسلامية")
        # «أ» تسبق «ب» أبجدياً، والشرعيةُ تسبق العربية في ترتيب الأقسام.
        for idx, (name, subject) in enumerate(((" أ معلّم", arabic), ("ب معلّم", islamic))):
            teacher = UserFactory(full_name=name)
            MembershipFactory(
                user=teacher, school=school, role=RoleFactory(school=school, name=f"teacher{idx}")
            )
            ScheduleSlot.objects.create(
                school=school,
                class_group=class_group,
                teacher=teacher,
                subject=subject,
                day_of_week=idx,
                period_number=1,
                start_time=time(7, 30),
                end_time=time(8, 15),
                academic_year=class_group.academic_year,
            )

        rows = ScheduleService.get_teachers_matrix(school, class_group.academic_year)
        codes = [r["department"]["code"] for r in rows]
        assert codes == ["sharia", "arabic"]
        assert DEPARTMENT_ORDER["sharia"] < DEPARTMENT_ORDER["arabic"]


# ══════════════════════════════════════════════════
#  ترتيبُ الشُّعب: من 7/1 إلى 12/4
# ══════════════════════════════════════════════════


class TestClassGroupOrdering:
    """`grade` نصٌّ («G7» … «G12»)، وترتيبُه الأبجديُّ يضع العاشرَ قبل السابع."""

    @pytest.fixture
    def ladder(self, db, school):
        from tests.conftest import ClassGroupFactory

        rows = [("G12", "4"), ("G7", "1"), ("G10", "2"), ("G9", "3"), ("G7", "2")]
        return [
            ClassGroupFactory(
                school=school, grade=grade, section=section, academic_year="2026-2027"
            )
            for grade, section in rows
        ]

    def test_the_default_order_reads_as_a_school_reads(self, school, ladder):
        from core.models import ClassGroup

        codes = [c.short_code for c in ClassGroup.objects.filter(school=school)]

        assert codes == ["7.1", "7.2", "9.3", "10.2", "12.4"]

    def test_in_school_order_survives_an_explicit_call(self, school, ladder):
        from core.models import ClassGroup

        codes = [c.short_code for c in ClassGroup.objects.filter(school=school).in_school_order()]

        assert codes == ["7.1", "7.2", "9.3", "10.2", "12.4"]

    def test_grade_number_reads_the_digits(self):
        from core.models.academic import grade_number

        assert [grade_number(g) for g in ("G7", "G9", "G10", "G12")] == [7, 9, 10, 12]
        assert grade_number("") == 99, "وما لا يُقرأ إلى الذيل — ولا يسقط"

    def test_the_weekly_grid_orders_the_sections_inside_a_cell(
        self, school, class_group, teacher_user, subject
    ):
        """خانةُ العرض العامّ تحمل شعبَ المدرسة كلَّها — فتُقرأ بترتيبها."""
        from operations.services import ScheduleService
        from tests.conftest import ClassGroupFactory

        senior = ClassGroupFactory(
            school=school, grade="G12", section="1", academic_year=class_group.academic_year
        )
        for group, teacher in ((senior, teacher_user), (class_group, UserFactory(full_name="آخر"))):
            if teacher is not teacher_user:
                MembershipFactory(
                    user=teacher, school=school, role=RoleFactory(school=school, name="teacher_b")
                )
            ScheduleSlot.objects.create(
                school=school,
                class_group=group,
                teacher=teacher,
                subject=subject,
                day_of_week=0,
                period_number=1,
                start_time=time(7, 30),
                end_time=time(8, 15),
                academic_year=class_group.academic_year,
            )

        cell = ScheduleService.get_weekly_schedule(school, None, None, class_group.academic_year)[
            0
        ][1]

        grades = [s.class_group.grade for s in cell]

        assert grades == ["G7", "G12"], "السابعُ أوّلاً وإن جاء الثاني عشرَ قبله في القاعدة"
        assert cell[-1].class_group_id == senior.id

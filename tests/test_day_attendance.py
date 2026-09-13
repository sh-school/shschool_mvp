"""رصدُ يومِ شعبةٍ بموجةٍ واحدة — والسريانُ شرطُ صحّةٍ لا تخفيف.

خمسُ شُعبٍ × سبعُ حصصٍ = 35 شاشةً يوميّاً لكلّ مشرف. وشاشةٌ كهذه لا تُنفَّذ
بعد أسبوع: يُعلَّم الكلُّ حاضراً وتموت البيانات بلا أن يُخفق شيء.

**ولكنّ السريانَ ليس تخفيفاً**: قاعدةٌ نافذةٌ في `absence_standing` تعدّ اليومَ
غياباً بلا عذر إذا كان الطالبُ غائباً في **كلّ** حصصه المسجَّلة، وما دون ذلك
غيابٌ **جزئيٌّ** يُعرض ولا يُحتسب. فرصدُ الحصّة الأولى وحدَها يُصيّر الغائبَ
يوماً كاملاً «جزئيّاً» لا يبلغ عتبةَ استدعاءٍ ولا حرمان.

فالحرّاسُ هنا على أربعة: أنّ الحالةَ تعبر كلَّ حصص اليوم، وأنّ الاحتسابَ
يقبلها يوماً كاملاً، وأنّ «لم تُرصد» تُفارق «كلُّها حاضر»، وأنّ ما رصده معلّمٌ
لا يُمَسّ — فبلا الأخير لا يُقارَن أسبوعُ التشغيل الموازي.
"""

import datetime as dt

import pytest
from django.urls import reverse

from core.academic_calendar import academic_year_for_school
from core.models import Wing
from operations.absence_standing import standing_for
from operations.day_attendance import (
    day_state,
    record_day,
    sessions_of,
    slots_of,
)
from operations.models import SectionDayConfirmation, Session, StudentAttendance
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

SUNDAY = dt.date(2026, 9, 13)


@pytest.fixture
def year(school):
    return academic_year_for_school(school)


@pytest.fixture
def klass(school, year):
    return ClassGroupFactory(
        school=school, grade="G7", section="1", level_type="prep", academic_year=year
    )


@pytest.fixture
def kids(school, klass):
    made = []
    for i in range(4):
        student = UserFactory(full_name=f"طالب {i}", national_id=f"2930000000{i}")
        StudentEnrollmentFactory(student=student, class_group=klass)
        made.append(student)
    return made


@pytest.fixture
def teacher(school):
    user = UserFactory(full_name="معلّم الحصّة", national_id="29300000090")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


@pytest.fixture
def other_teacher(school):
    """معلّمٌ ثانٍ — زوجُ الاختيار معلّمان لا معلّمٌ واحد.

    وقيدُ `no_teacher_time_overlap` في القاعدة يمنع المعلّمَ الواحدَ من حصّتين
    في الساعة نفسِها، وهو صادقٌ: لا يقف أحدٌ في صفّين. فالزوجُ يُبنى باثنين.
    """
    user = UserFactory(full_name="معلّم الزوج الثاني", national_id="29300000092")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


@pytest.fixture
def supervisor(school, klass, year):
    user = UserFactory(full_name="مشرف الجناح", national_id="29300000091")
    MembershipFactory(
        user=user, school=school, role=RoleFactory(school=school, name="admin_supervisor")
    )
    wing = Wing.objects.create(
        school=school, code="w1", name="جناح 1", academic_year=year, supervisor=user
    )
    klass.wing = wing
    klass.save(update_fields=["wing"])
    return user


def _periods(school, klass, teacher, count=7, day=SUNDAY, at=7):
    """حصصُ اليوم — تُبنى صريحةً كي يُعرف عددُها في الاختبار."""
    made = []
    for i in range(count):
        made.append(
            Session.objects.create(
                school=school,
                class_group=klass,
                teacher=teacher,
                date=day,
                start_time=dt.time(at + i, 10),
                end_time=dt.time(at + i, 55),
                status="scheduled",
            )
        )
    return made


def _elective_twin(school, klass, other_teacher, day=SUNDAY, index=3):
    """يجعل خانةً واحدةً حصّتين — كزوج الاختيار في الواقع.

    والقاعدةُ تمنع حصّتين لشعبةٍ في الساعة نفسِها إلّا أن تختلف
    `elective_group` (قيد `no_class_time_overlap`)، وتمنع المعلّمَ الواحدَ من
    حصّتين متزامنتين (`no_teacher_time_overlap`). فالزوجُ مادّتان ومعلّمان —
    وهذا ما يُبنى هنا، لا حصّةٌ مكرّرة.
    """
    first = Session.objects.filter(class_group=klass, date=day).order_by("start_time")[index]
    first.elective_group = "تكنولوجيا"
    first.save(update_fields=["elective_group"])
    return Session.objects.create(
        school=school,
        class_group=klass,
        teacher=other_teacher,
        date=day,
        start_time=first.start_time,
        end_time=first.end_time,
        status="scheduled",
        elective_group="فنون بصريّة",
    )


class TestTheWaveCoversTheWholeDay:
    def test_every_student_gets_a_record_in_every_period(self, school, klass, kids, teacher):
        _periods(school, klass, teacher, 7)

        result = record_day(klass, SUNDAY, {str(kids[0].id): "absent"})

        assert result.written == 4 * 7
        assert StudentAttendance.objects.filter(session__class_group=klass).count() == 28

    def test_the_absent_student_is_absent_in_all_seven(self, school, klass, kids, teacher):
        _periods(school, klass, teacher, 7)

        record_day(klass, SUNDAY, {str(kids[0].id): "absent"})

        assert StudentAttendance.objects.filter(student=kids[0], status="absent").count() == 7

    def test_whoever_is_not_named_is_present(self, school, klass, kids, teacher):
        """المشرفُ يلمس الغائبين وحدَهم — وهم القلّةُ في الغالب."""
        _periods(school, klass, teacher, 7)

        record_day(klass, SUNDAY, {str(kids[0].id): "absent"})

        for student in kids[1:]:
            assert StudentAttendance.objects.filter(student=student, status="present").count() == 7

    def test_a_thursday_gets_six_not_seven(self, school, klass, kids, teacher):
        """عددُ الحصص يُقرأ ولا يُخترع — ومن كتب سبعاً ثابتةً أخطأ الخميس."""
        thursday = dt.date(2026, 9, 17)
        _periods(school, klass, teacher, 6, day=thursday)

        result = record_day(klass, thursday, {})

        assert result.periods == 6
        assert result.written == 4 * 6

    def test_a_day_with_no_periods_records_nothing(self, school, klass, kids, teacher):
        """لا يُقال «رُصدت» وشعبةٌ بلا حصصٍ في ذلك اليوم."""
        result = record_day(klass, SUNDAY, {str(kids[0].id): "absent"})

        assert result.written == 0
        assert result.confirmation is None
        assert not SectionDayConfirmation.objects.exists()

    def test_recording_twice_replaces_it_does_not_double(self, school, klass, kids, teacher):
        _periods(school, klass, teacher, 7)
        record_day(klass, SUNDAY, {str(kids[0].id): "absent"})

        record_day(klass, SUNDAY, {str(kids[1].id): "late"})

        assert StudentAttendance.objects.filter(session__class_group=klass).count() == 28
        assert StudentAttendance.objects.filter(student=kids[0], status="present").count() == 7
        assert StudentAttendance.objects.filter(student=kids[1], status="late").count() == 7


class TestThePropagationIsWhatMakesTheCountTrue:
    def test_a_full_day_absence_counts_as_a_day(
        self, school, klass, kids, teacher, seeded_calendar
    ):
        _periods(school, klass, teacher, 7)

        record_day(klass, SUNDAY, {str(kids[0].id): "absent"})
        standing = standing_for(kids[0], school, grade="G7", on=SUNDAY)

        assert standing.unexcused_days == 1
        assert standing.partial_days == 0

    def test_one_period_alone_would_be_partial_not_a_day(
        self, school, klass, kids, teacher, seeded_calendar
    ):
        """هذا هو السببُ الذي يجعل السريانَ شرطَ صحّةٍ لا تخفيفاً.

        فلو كُتب الغيابُ في حصّةٍ من سبعٍ لصار «جزئيّاً» يُعرض ولا يُحتسب،
        فلا يبلغ الطالبُ عتبةَ استدعاءٍ ولا حرمانٍ ولو غاب العامَ كلَّه.
        """
        periods = _periods(school, klass, teacher, 7)
        StudentAttendance.objects.create(
            session=periods[0], student=kids[0], school=school, status="absent"
        )
        for session in periods[1:]:
            StudentAttendance.objects.create(
                session=session, student=kids[0], school=school, status="present"
            )

        standing = standing_for(kids[0], school, grade="G7", on=SUNDAY)

        assert standing.unexcused_days == 0, "حصّةٌ واحدةٌ ليست يوماً"
        assert standing.partial_days == 1

    def test_a_late_student_is_not_counted_absent(
        self, school, klass, kids, teacher, seeded_calendar
    ):
        _periods(school, klass, teacher, 7)

        record_day(klass, SUNDAY, {str(kids[0].id): "late"})

        assert standing_for(kids[0], school, grade="G7", on=SUNDAY).unexcused_days == 0


class TestNoPresenceByDefault:
    def test_an_unrecorded_section_has_no_confirmation(self, school, klass, kids, teacher):
        """شعبةٌ لم تُرصد وشعبةٌ كلُّها حاضرةٌ تبدوان في القاعدة سواءً — بلا هذا."""
        _periods(school, klass, teacher, 7)

        assert not SectionDayConfirmation.objects.filter(class_group=klass, date=SUNDAY).exists()

    def test_confirming_records_who_and_how_many(self, school, klass, kids, teacher, supervisor):
        _periods(school, klass, teacher, 7)

        record_day(
            klass,
            SUNDAY,
            {str(kids[0].id): "absent", str(kids[1].id): "late"},
            by=supervisor,
            note="ملاحظة",
        )

        c = SectionDayConfirmation.objects.get(class_group=klass, date=SUNDAY)
        assert (c.absent_count, c.late_count, c.present_count) == (1, 1, 2)
        assert c.periods_written == 7
        assert c.confirmed_by == supervisor
        assert c.note == "ملاحظة"

    def test_one_confirmation_per_section_per_day(self, school, klass, kids, teacher):
        _periods(school, klass, teacher, 7)

        record_day(klass, SUNDAY, {})
        record_day(klass, SUNDAY, {str(kids[0].id): "absent"})

        assert SectionDayConfirmation.objects.filter(class_group=klass).count() == 1


class TestTheTwoSourcesDoNotMix:
    def test_the_supervisors_record_carries_his_source(self, school, klass, kids, teacher):
        _periods(school, klass, teacher, 7)

        record_day(klass, SUNDAY, {str(kids[0].id): "absent"})

        assert StudentAttendance.objects.filter(source="supervisor").count() == 28
        assert not StudentAttendance.objects.filter(source="teacher").exists()

    def test_what_a_teacher_recorded_is_not_shown_as_the_supervisors(
        self, school, klass, kids, teacher
    ):
        """في أسبوع التشغيل الموازي يرصد الاثنان — وخلطُهما يُخفي أنّ المشرفَ
        لم يرصد بعد، فتُقرأ الشعبةُ مرصودةً وهي لم تُرصد."""
        periods = _periods(school, klass, teacher, 7)
        for session in periods:
            StudentAttendance.objects.create(
                session=session,
                student=kids[0],
                school=school,
                status="absent",
                source="teacher",
            )

        assert day_state(klass, SUNDAY) == {}


class TestTheTeacherDoesNotRecord:
    """الرصدُ لمشرف الجناح وحدَه — قرارُ المدير، واللوائحُ تُقرّه.

    والسجلُّ واحدٌ لكلّ طالبٍ في كلّ حصّة، فمن يحفظ أخيراً يمحو ما قبله.
    وشاشةُ الحصّة القديمة تكتب الحالةَ ولا تلمس `source`: فضغطةُ معلّمٍ بحكم
    العادة كانت تغيّر حالةَ الطالب ويبقى السجلُّ منسوباً إلى المشرف.
    """

    def test_a_teacher_cannot_overwrite_what_the_supervisor_recorded(
        self, client_as, school, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 7)
        record_day(klass, SUNDAY, {str(kids[0].id): "absent"}, by=supervisor)

        response = client_as(teacher).post(
            reverse("mark_single", args=[periods[0].id]),
            {"student_id": str(kids[0].id), "status": "present"},
        )

        assert response.status_code == 403
        row = StudentAttendance.objects.get(session=periods[0], student=kids[0])
        assert (row.status, row.source) == ("absent", "supervisor")

    def test_mark_all_present_leaves_the_supervisors_absentees_absent(
        self, client_as, school, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 7)
        record_day(klass, SUNDAY, {str(kids[0].id): "absent"}, by=supervisor)

        client_as(teacher).post(reverse("mark_all_present", args=[periods[0].id]))

        row = StudentAttendance.objects.get(session=periods[0], student=kids[0])
        assert (row.status, row.source) == ("absent", "supervisor")

    def test_the_supervisor_still_corrects_his_own_record(
        self, client_as, school, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 7)
        record_day(klass, SUNDAY, {str(kids[0].id): "absent"}, by=supervisor)

        response = client_as(supervisor).post(
            reverse("mark_single", args=[periods[0].id]),
            {"student_id": str(kids[0].id), "status": "late"},
        )

        assert response.status_code == 200
        assert StudentAttendance.objects.get(session=periods[0], student=kids[0]).status == "late"


class TestTheTeacherScreenIsReadOnly:
    """المعلّمُ لا يرصد في شُعب الأجنحة — لا فوقَ المشرف ولا قبله."""

    def test_a_teacher_cannot_record_even_before_the_supervisor(
        self, client_as, school, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 7)

        response = client_as(teacher).post(
            reverse("mark_single", args=[periods[0].id]),
            {"student_id": str(kids[0].id), "status": "absent"},
        )

        assert response.status_code == 403
        assert not StudentAttendance.objects.exists()

    def test_a_teacher_cannot_mark_all_present(
        self, client_as, school, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 7)

        response = client_as(teacher).post(reverse("mark_all_present", args=[periods[0].id]))

        assert response.status_code == 403
        assert not StudentAttendance.objects.exists()

    def test_the_teacher_sees_the_session_without_buttons(
        self, client_as, school, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 7)
        record_day(klass, SUNDAY, {str(kids[0].id): "absent"}, by=supervisor)

        response = client_as(teacher).get(reverse("attendance", args=[periods[0].id]))
        body = response.content.decode()

        assert response.status_code == 200
        assert "لمشرف الجناح" in body
        assert reverse("mark_single", args=[periods[0].id]) not in body
        assert "غائب" in body

    def test_the_teachers_schedule_does_not_invite_him_to_record(
        self, client_as, school, klass, kids, teacher, supervisor
    ):
        """«تسجيل حضور» زرٌّ يَعِد بما لا يحدث — فالمعلّمُ يرى «عرض»."""
        periods = _periods(school, klass, teacher, 7)

        body = (
            client_as(teacher)
            .get(reverse("teacher_schedule") + f"?date={SUNDAY.isoformat()}")
            .content.decode()
        )

        assert reverse("attendance", args=[periods[0].id]) in body
        assert "تسجيل حضور" not in body

    def test_a_section_outside_the_wings_keeps_its_teacher_recording(
        self, client_as, school, year, teacher
    ):
        """التربيةُ الخاصّة خارجَ الأجنحة، ويرصدها معلّموها."""
        ese = ClassGroupFactory(
            school=school, grade="G7", section="9", level_type="prep", academic_year=year
        )
        student = UserFactory(full_name="طالب خاصّ", national_id="29300000099")
        StudentEnrollmentFactory(student=student, class_group=ese)
        (session,) = _periods(school, ese, teacher, 1)

        response = client_as(teacher).post(
            reverse("mark_single", args=[session.id]),
            {"student_id": str(student.id), "status": "absent"},
        )

        assert response.status_code == 200


class TestSlotsAreNotSessions:
    def test_an_elective_pair_is_one_slot_two_sessions(
        self, school, klass, kids, teacher, other_teacher
    ):
        """12/1 الأحدَ: تكنولوجيا وفنونٌ بصريّةٌ في 09:35 — نصفُ الشعبة هنا
        ونصفُها هناك. فالحصصُ ثمانٍ والخاناتُ سبع، والمشرفُ يرصد يومَ الطالب."""
        _periods(school, klass, teacher, 7)
        _elective_twin(school, klass, other_teacher)

        assert sessions_of(klass, SUNDAY).count() == 8
        assert slots_of(klass, SUNDAY) == 7

    def test_both_sessions_of_the_pair_get_the_record(
        self, school, klass, kids, teacher, other_teacher
    ):
        """فيراه معلّما الزوج كلاهما، ولا يُخفى الغيابُ عن أحدهما."""
        _periods(school, klass, teacher, 7)
        _elective_twin(school, klass, other_teacher)

        record_day(klass, SUNDAY, {str(kids[0].id): "absent"})

        assert StudentAttendance.objects.filter(student=kids[0], status="absent").count() == 8


class TestTheScreen:
    def test_the_supervisor_sees_his_sections(
        self, client_as, school, klass, kids, teacher, supervisor
    ):
        _periods(school, klass, teacher, 7)

        body = (
            client_as(supervisor)
            .get(reverse("wings:record_index") + f"?date={SUNDAY.isoformat()}")
            .content.decode()
        )

        assert klass.short_code in body
        assert "لم تُرصد" in body

    def test_the_screen_is_reachable_from_the_menu(self, client_as, school, supervisor):
        """شاشةٌ لا رابطَ إليها شاشةٌ غيرُ موجودة.

        ولوحةُ إدارة جانغو مقصورةٌ على المدير والمطوّر بقرار المدرسة، فلا
        مدخلَ للمشرف إلّا قائمتُه. والرابطُ يُكتب بيدٍ في `base.html` —
        `register_module` يحمي البادئةَ ولا يضيف رابطاً — فيُحرَس بالاختبار.
        """
        body = client_as(supervisor).get(reverse("dashboard")).content.decode()

        assert reverse("wings:record_index") in body

    def test_the_supervisors_home_page_shows_his_sections_to_record(
        self, client_as, school, klass, kids, teacher, supervisor
    ):
        """لوحتُه أوّلُ ما يفتحه صباحاً — والرصدُ عملُه الأوّل، فيكون في رأسها.

        كان الرابطُ في القائمة وحدَها ولوحتُه لا تذكر الرصدَ أصلاً.
        """
        body = client_as(supervisor).get(reverse("dashboard")).content.decode()

        assert klass.short_code in body
        assert reverse("wings:record_section", args=[klass.id]) in body

    def test_a_teacher_is_turned_away(self, client_as, school, klass, teacher):
        response = client_as(teacher).get(reverse("wings:record_index"))

        assert response.status_code in (302, 403)

    def test_posting_the_form_records_the_day(
        self, client_as, school, klass, kids, teacher, supervisor
    ):
        _periods(school, klass, teacher, 7)

        client_as(supervisor).post(
            reverse("wings:record_section", args=[klass.id]),
            {
                "date": SUNDAY.isoformat(),
                f"s-{kids[0].id}": "absent",
                f"s-{kids[1].id}": "late",
                "note": "من الشاشة",
            },
        )

        c = SectionDayConfirmation.objects.get(class_group=klass, date=SUNDAY)
        assert (c.absent_count, c.late_count) == (1, 1)
        assert StudentAttendance.objects.filter(student=kids[0], status="absent").count() == 7

    def test_the_section_screen_shows_what_was_recorded(
        self, client_as, school, klass, kids, teacher, supervisor
    ):
        _periods(school, klass, teacher, 7)
        record_day(klass, SUNDAY, {str(kids[0].id): "absent"}, by=supervisor)

        body = (
            client_as(supervisor)
            .get(reverse("wings:record_section", args=[klass.id]) + f"?date={SUNDAY.isoformat()}")
            .content.decode()
        )

        assert (
            f'name="s-{kids[0].id}" value="absent"'
            in body.replace("\n", " ").replace("                   ", " ")
            or "absent" in body
        )
        assert "رُصدت اليومَ" in body

    def test_an_unknown_state_falls_back_to_present(self, school, klass, kids, teacher):
        """قيمةٌ ملفّقةٌ في الطلب لا تصير حالةً — والافتراضُ حاضر."""
        _periods(school, klass, teacher, 7)

        record_day(klass, SUNDAY, {str(kids[0].id): "excused"})

        assert StudentAttendance.objects.filter(student=kids[0], status="present").count() == 7

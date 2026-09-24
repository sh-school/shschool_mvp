"""الحصّةُ التعويضيّة: في حصّة زميلٍ بموافقته، وبوقت جرس طابق الشعبة ليومها (2026-09-24).

كان الاعتمادُ يأخذ أوّلَ إعدادٍ «عاديّ» في المدرسة: جرسَ الطابق الأرضيّ لكلّ شعبة،
وجرسَ الأحد–الأربعاء يومَ الخميس. فسادسةُ الثانويّ يومَ الخميس كانت تُكتب 11:35–12:20
وجرسُها 11:10–11:50. ثمّ إنّ الجدولَ المعتمدَ ممتلئ — لا حصّةَ فارغةً لشعبة — فكان
الاعتمادُ يصطدم بحصّة الشعبة القائمة: خطأُ خادمٍ إن وافق وقتُها، وحصّتان متداخلتان إن
خالفه. فقرّر المالك: التعويضُ في حصّة زميلٍ يدرّس الشعبة، يوافق هو ثمّ يعتمد المنسّق.
"""

import datetime as dt

import pytest
from django.core.management import call_command
from django.urls import reverse

from core.models import TimeBand
from operations.models import (
    CompensatorySession,
    ScheduleSlot,
    Session,
    StudentAttendance,
    Subject,
    TeacherAbsence,
)
from operations.services import CompensatoryService, ScheduleService
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"
#: أسبوعٌ دراسيٌّ في التقويم المبذور — اختباراتُ منتصف الفصل أيّامُ دوام.
SUNDAY = dt.date(2026, 10, 11)
THURSDAY = dt.date(2026, 10, 15)
FRIDAY = dt.date(2026, 10, 16)
#: في إجازة منتصف الفصل الأوّل (25–29 أكتوبر).
IN_THE_BREAK = dt.date(2026, 10, 27)


def _teacher(school, name):
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


def _slot(world, klass, teacher, day, period, start, end, subject=None):
    return ScheduleSlot.objects.create(
        school=world["school"],
        teacher=teacher,
        class_group=world[klass],
        subject=subject or world["subject"],
        day_of_week=day,
        period_number=period,
        start_time=start,
        end_time=end,
        academic_year=YEAR,
    )


TODAY = dt.date(2026, 10, 6)


def _today(monkeypatch, day):
    """يومُ الاختبار مثبَّتٌ: التعويضُ لا يقع في الماضي، وتواريخُ التقويم المبذور ثابتة."""
    from django.utils import timezone

    monkeypatch.setattr(timezone, "localdate", lambda *a, **k: day)


@pytest.fixture
def world(school, seeded_calendar, monkeypatch):
    """شعبةٌ أرضيّةٌ وأخرى ثانويّة، ومعلّمٌ يدرّسهما غاب قبل أسبوع، وزميلٌ للعلوم فيهما."""
    _today(monkeypatch, TODAY)
    call_command("seed_time_bands")
    bands = {b.code: b for b in TimeBand.objects.filter(school=school)}
    teacher = _teacher(school, "معلّمُ الطابقين")
    w = {
        "school": school,
        "teacher": teacher,
        "colleague": _teacher(school, "معلّمُ العلوم"),
        "subject": Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT"),
        "science": Subject.objects.create(school=school, name_ar="العلوم", code="SCI"),
        "ground": ClassGroupFactory(
            school=school,
            grade="G7",
            level_type="prep",
            academic_year=YEAR,
            time_band=bands["ground"],
        ),
        "upper": ClassGroupFactory(
            school=school,
            grade="G10",
            level_type="sec",
            academic_year=YEAR,
            time_band=bands["secondary"],
        ),
        "absence": TeacherAbsence.objects.create(
            school=school, teacher=teacher, date=SUNDAY - dt.timedelta(days=7)
        ),
    }
    # الحصّتان الفائتتان يومَ الاثنين — لا تمسّان أيّامَ التعويض.
    w["ground_slot"] = _slot(w, "ground", teacher, 1, 1, dt.time(7, 10), dt.time(8, 0))
    w["upper_slot"] = _slot(w, "upper", teacher, 1, 3, dt.time(8, 45), dt.time(9, 35))
    return w


def _science(world, klass, day, period, start, end):
    """حصّةُ الزميل في الشعبة — والجدولُ الحيّ ممتلئٌ بمثلها."""
    return _slot(world, klass, world["colleague"], day, period, start, end, world["science"])


def _request(world, klass, day, period, teacher=None):
    teacher = teacher or world["teacher"]
    return CompensatoryService.request_compensatory(
        school=world["school"],
        teacher=teacher,
        original_slot=world[f"{klass}_slot"],
        absence=world["absence"],
        compensatory_date=day,
        compensatory_period=period,
    )


def _through(world, klass, day, period, approver):
    """الطلبُ فموافقةُ الزميل (إن كان) فالاعتماد — ويُعيد حصّةَ التعويض."""
    comp = _request(world, klass, day, period)
    if comp.colleague_id:
        CompensatoryService.colleague_decide(comp, comp.colleague, accepted=True)
    CompensatoryService.approve_compensatory(comp, approved_by=approver)
    return CompensatorySession.objects.get(pk=comp.pk).session_created


class TestTheClassBellOfTheDay:
    def test_ground_on_thursday_takes_the_colleagues_lesson_at_its_bell(
        self, world, principal_user
    ):
        _science(world, "ground", 4, 6, dt.time(11, 55), dt.time(12, 40))

        lesson = _through(world, "ground", THURSDAY, 6, principal_user)

        assert (lesson.start_time, lesson.end_time) == (
            dt.time(11, 55),
            dt.time(12, 40),
        ), "سادسةُ الأرضيّ يومَ الخميس بعد الصلاة — لا 11:35 من جرس الأحد"
        assert (lesson.teacher, lesson.subject, lesson.original_teacher) == (
            world["teacher"],
            world["subject"],
            world["colleague"],
        ), "حصّةُ الزميل صارت لصاحب التعويض بمادّته، واسمُ الزميل محفوظ"
        assert Session.objects.filter(date=THURSDAY, class_group=world["ground"]).count() == 1

    def test_secondary_on_thursday_rings_its_own_bell(self, world, principal_user):
        # الشعبةُ فارغةٌ في وقتها هنا: حصّةٌ جديدة، والطلبُ إلى المنسّق مباشرةً.
        lesson = _through(world, "upper", THURSDAY, 6, principal_user)

        assert (lesson.start_time, lesson.end_time) == (dt.time(11, 10), dt.time(11, 50))
        assert lesson.original_teacher is None

    def test_secondary_on_sunday_rings_the_first_floor_bell(self, world, principal_user):
        _science(world, "upper", 0, 7, dt.time(12, 25), dt.time(13, 10))

        lesson = _through(world, "upper", SUNDAY, 7, principal_user)

        assert (lesson.start_time, lesson.end_time) == (
            dt.time(12, 25),
            dt.time(13, 10),
        ), "سابعةُ الطابق الأوّل قبل الصلاة، وسابعةُ الأرضيّ بعدها (12:40)"


class TestNoTimeNoLesson:
    def test_the_ground_floor_has_no_seventh_period_on_thursday(self, world):
        with pytest.raises(ValueError, match="لا حصّةَ 7 يومَ الخميس"):
            _request(world, "ground", THURSDAY, 7)
        assert not CompensatorySession.objects.exists()

    def test_a_weekend_is_refused(self, world):
        with pytest.raises(ValueError, match="عطلةُ نهاية الأسبوع"):
            _request(world, "upper", FRIDAY, 1)

    def test_a_holiday_is_refused_by_its_name(self, world):
        # غيابٌ قريبٌ من الإجازة: التعويضُ خلال أسبوعَي الغياب.
        world["absence"] = TeacherAbsence.objects.create(
            school=world["school"], teacher=world["teacher"], date=dt.date(2026, 10, 20)
        )
        with pytest.raises(ValueError, match="إجازة منتصف الفصل الأول"):
            _request(world, "upper", IN_THE_BREAK, 1)
        assert not Session.objects.filter(date=IN_THE_BREAK).exists(), "ولا يُولَّد يومُ الإجازة"

    def test_only_ones_own_missed_lesson(self, world):
        other = _teacher(world["school"], "معلّمٌ آخر")
        with pytest.raises(ValueError, match="من سجلّك أنت"):
            _request(world, "upper", SUNDAY, 5, teacher=other)


class TestWhichLessonMayBeTaken:
    def test_a_two_floor_teacher_is_busy_by_the_clock_not_by_the_number(self, world):
        # ثانيةُ الأرضيّ 8:00–8:50 وثالثةُ الطابق الأوّل 8:45–9:35: رقمان وخمسُ دقائق.
        _slot(world, "ground", world["teacher"], 0, 2, dt.time(8, 0), dt.time(8, 50))

        with pytest.raises(ValueError, match="المعلّم مشغولٌ"):
            _request(world, "upper", SUNDAY, 3)

    def test_a_lesson_with_attendance_is_not_taken(self, world, student_user):
        _science(world, "upper", 0, 5, dt.time(10, 50), dt.time(11, 35))
        ScheduleService.ensure_sessions_for_date(world["school"], SUNDAY)
        lesson = Session.objects.get(date=SUNDAY, class_group=world["upper"])
        StudentAttendance.objects.create(
            session=lesson, student=student_user, school=world["school"]
        )

        with pytest.raises(ValueError, match="رُصد حضورها"):
            _request(world, "upper", SUNDAY, 5)

    def test_a_lesson_is_claimed_once(self, world):
        _science(world, "upper", 0, 5, dt.time(10, 50), dt.time(11, 35))
        _request(world, "upper", SUNDAY, 5)
        second = _teacher(world["school"], "معلّمٌ ثانٍ غاب")
        world["upper_slot"] = _slot(world, "upper", second, 2, 1, dt.time(7, 10), dt.time(8, 0))
        world["absence"] = TeacherAbsence.objects.create(
            school=world["school"], teacher=second, date=SUNDAY - dt.timedelta(days=5)
        )

        with pytest.raises(ValueError, match="طُلبت لتعويضٍ آخر"):
            _request(world, "upper", SUNDAY, 5, teacher=second)

    def test_the_options_show_every_lesson_and_why(self, world):
        _science(world, "upper", 0, 5, dt.time(10, 50), dt.time(11, 35))
        _slot(world, "ground", world["teacher"], 0, 2, dt.time(8, 0), dt.time(8, 50))

        rows = {
            r["period"]: r
            for r in CompensatoryService.day_options(
                world["school"], world["teacher"], world["upper"], SUNDAY
            )
        }

        assert sorted(rows) == [1, 2, 3, 4, 5, 6, 7], "جرسُ الطابق الأوّل سبعُ حصص"
        assert (rows[5]["ok"], rows[5]["colleague"]) == (True, world["colleague"])
        assert rows[3]["ok"] is False and "مشغولٌ" in rows[3]["why"]


class TestTheColleagueConsentsFirst:
    @pytest.fixture
    def asked(self, world):
        _science(world, "upper", 0, 5, dt.time(10, 50), dt.time(11, 35))
        return _request(world, "upper", SUNDAY, 5)

    def test_the_request_waits_for_the_colleague(self, asked, world, principal_user):
        assert (asked.status, asked.colleague) == ("colleague", world["colleague"])
        with pytest.raises(ValueError, match="بحالة"):
            CompensatoryService.approve_compensatory(asked, approved_by=principal_user)

    def test_only_the_colleague_answers(self, asked, principal_user):
        with pytest.raises(ValueError, match="لصاحب الحصّة وحده"):
            CompensatoryService.colleague_decide(asked, principal_user, accepted=True)

    def test_declining_cancels_and_keeps_the_lesson(self, asked, world):
        CompensatoryService.colleague_decide(asked, world["colleague"], False, "عندي اختبار")

        asked.refresh_from_db()
        assert asked.status == "cancelled" and "اعتذر الزميل: عندي اختبار" in asked.notes
        assert asked.colleague_responded_at is not None
        lesson = Session.objects.get(date=SUNDAY, class_group=world["upper"])
        assert lesson.teacher == world["colleague"]

    def test_approval_asks_again_if_the_lesson_changed_hands(self, asked, world, principal_user):
        CompensatoryService.colleague_decide(asked, world["colleague"], accepted=True)
        # أُعيد بناءُ اليوم من خطّةٍ جديدة: الحصّةُ نفسُها لمعلّمٍ آخر لم يوافق.
        Session.objects.filter(date=SUNDAY, class_group=world["upper"]).update(
            teacher=_teacher(world["school"], "معلّمٌ جديد")
        )

        with pytest.raises(ValueError, match="تغيّر صاحبُ الحصّة"):
            CompensatoryService.approve_compensatory(asked, approved_by=principal_user)

        asked.refresh_from_db()
        assert (asked.status, asked.session_created) == ("pending", None)


class TestTheScreens:
    def test_the_list_shows_the_time_and_the_colleague_answers_from_it(
        self, world, principal_user, client
    ):
        _science(world, "upper", 4, 6, dt.time(11, 10), dt.time(11, 50))
        comp = _request(world, "upper", THURSDAY, 6)
        world["colleague"].must_change_password = False
        world["colleague"].save(update_fields=["must_change_password"])
        client.force_login(world["colleague"])

        body = client.get(reverse("compensatory_list"), HTTP_HOST="localhost").content.decode()
        assert reverse("compensatory_respond", args=[comp.pk]) in body, "يرى صاحبُ الحصّة الطلب"

        client.post(
            reverse("compensatory_respond", args=[comp.pk]),
            {"action": "accept"},
            HTTP_HOST="localhost",
        )
        comp.refresh_from_db()
        assert comp.status == "pending"

        CompensatoryService.approve_compensatory(comp, approved_by=principal_user)
        client.force_login(principal_user)
        body = client.get(reverse("compensatory_list"), HTTP_HOST="localhost").content.decode()
        assert "ح6 (11:10–11:50)" in body and "في حصّة معلّمُ العلوم" in body

    def test_the_options_partial_names_the_colleague(self, world, client):
        _science(world, "upper", 0, 5, dt.time(10, 50), dt.time(11, 35))
        client.force_login(world["teacher"])

        body = client.get(
            reverse("compensatory_options"),
            {"original_slot": world["upper_slot"].pk, "compensatory_date": SUNDAY.isoformat()},
            HTTP_HOST="localhost",
        ).content.decode()

        assert "ح5 · 10:50–11:35 · العلوم — معلّمُ العلوم" in body


# ═══════════ ما كشفته المراجعة (2026-09-24) ═══════════


class TestDatesAreBounded:
    def test_a_past_date_is_refused(self, world):
        with pytest.raises(ValueError, match="مضى تاريخُ التعويض"):
            _request(world, "upper", dt.date(2026, 10, 5), 5)

    def test_before_the_absence_is_refused(self, world):
        with pytest.raises(ValueError, match="بعد الغياب"):
            _request(world, "upper", world["absence"].date - dt.timedelta(days=1), 5)

    def test_beyond_the_next_week_is_refused(self, world):
        # الغيابُ 4/10: الأسبوعُ والذي يليه ينتهيان 18/10.
        with pytest.raises(ValueError, match="بعد الغياب"):
            _request(world, "upper", dt.date(2026, 10, 19), 5)

    def test_approval_is_refused_once_the_date_has_passed(self, world, principal_user, monkeypatch):
        _science(world, "upper", 0, 5, dt.time(10, 50), dt.time(11, 35))
        comp = _request(world, "upper", SUNDAY, 5)
        CompensatoryService.colleague_decide(comp, world["colleague"], accepted=True)
        _today(monkeypatch, SUNDAY + dt.timedelta(days=1))

        with pytest.raises(ValueError, match="مضى تاريخُ التعويض"):
            CompensatoryService.approve_compensatory(comp, approved_by=principal_user)

    def test_the_options_endpoint_does_not_generate_far_weeks(self, world, client):
        client.force_login(world["teacher"])
        far = (TODAY + dt.timedelta(days=90)).isoformat()

        body = client.get(
            reverse("compensatory_options"),
            {"original_slot": world["upper_slot"].pk, "compensatory_date": far},
            HTTP_HOST="localhost",
        ).content.decode()

        assert "اختر تاريخاً من اليوم إلى أربعة أسابيع" in body
        assert 'role="note"' in body, "سطرٌ ظاهرٌ لا أيقونةُ تلميح"
        assert not Session.objects.filter(date__gte=TODAY + dt.timedelta(days=60)).exists()


class TestNoSilentOverwrite:
    """حصّةٌ أخذها زميلٌ تعويضاً لا يُكتب فوقها إشغالٌ ولا تبديل."""

    @pytest.fixture
    def taken(self, world, principal_user):
        _science(world, "upper", 0, 5, dt.time(10, 50), dt.time(11, 35))
        lesson = _through(world, "upper", SUNDAY, 5, principal_user)
        absence = TeacherAbsence.objects.create(
            school=world["school"], teacher=world["colleague"], date=SUNDAY
        )
        return lesson, absence

    def test_the_colleagues_taken_lesson_is_no_longer_his_that_day(self, world, taken):
        from operations.services import SubstituteService

        _lesson, absence = taken

        assert list(SubstituteService.absence_slots(absence)) == []

    def test_nobody_can_be_assigned_to_it(self, world, taken):
        from operations.services import AbsenceSwapService, SubstituteService

        _lesson, absence = taken
        slot = ScheduleSlot.objects.get(teacher=world["colleague"], day_of_week=0)

        assert SubstituteService.coverage_candidates(absence, [slot])[slot.id] == []
        assert AbsenceSwapService.options(absence, slot) == []

    def test_a_direct_hand_over_is_refused_and_leaves_the_lesson(self, world, taken):
        from operations.services import SubstituteService

        lesson, _absence = taken
        slot = ScheduleSlot.objects.get(teacher=world["colleague"], day_of_week=0)
        other = _teacher(world["school"], "بديل")

        with pytest.raises(ValueError, match="أخذ زميلٌ هذه الحصّةَ تعويضاً"):
            SubstituteService.hand_over_session(world["school"], slot, SUNDAY, other)

        lesson.refresh_from_db()
        assert lesson.teacher == world["teacher"]

    def test_other_days_of_the_absence_are_untouched(self, world, taken):
        from operations.services import SubstituteService

        _science(world, "upper", 1, 2, dt.time(7, 55), dt.time(8, 40))
        monday = TeacherAbsence.objects.create(
            school=world["school"], teacher=world["colleague"], date=SUNDAY + dt.timedelta(days=1)
        )

        assert [s.period_number for s in SubstituteService.absence_slots(monday)] == [2]


class TestNoSelfApproval:
    @pytest.fixture
    def accepted(self, world):
        _science(world, "upper", 0, 5, dt.time(10, 50), dt.time(11, 35))
        comp = _request(world, "upper", SUNDAY, 5)
        CompensatoryService.colleague_decide(comp, world["colleague"], accepted=True)
        return comp

    def test_the_colleague_cannot_approve_what_he_consented_to(self, accepted, world):
        with pytest.raises(ValueError, match="طرفٌ فيه"):
            CompensatoryService.approve_compensatory(accepted, approved_by=world["colleague"])

    def test_the_requester_cannot_approve_his_own_request(self, accepted, world):
        with pytest.raises(ValueError, match="طرفٌ فيه"):
            CompensatoryService.approve_compensatory(accepted, approved_by=world["teacher"])

    def test_a_coordinator_outside_the_department_cannot_decide(self, accepted, coordinator_user):
        with pytest.raises(ValueError, match="خارج قسمك"):
            CompensatoryService.approve_compensatory(accepted, approved_by=coordinator_user)

        accepted.refresh_from_db()
        assert accepted.status == "pending"


class TestNoStuckRequests:
    @pytest.fixture
    def waiting(self, world):
        _science(world, "upper", 0, 5, dt.time(10, 50), dt.time(11, 35))
        return _request(world, "upper", SUNDAY, 5)

    def test_the_coordinator_can_reject_a_request_waiting_for_the_colleague(
        self, waiting, principal_user
    ):
        CompensatoryService.approve_compensatory(
            waiting, approved_by=principal_user, approved=False, rejection_reason="لا داعي"
        )

        waiting.refresh_from_db()
        assert waiting.status == "cancelled" and "لا داعي" in waiting.notes

    def test_approval_still_waits_for_the_colleague(self, waiting, principal_user):
        with pytest.raises(ValueError, match="اعتماد طلب بحالة"):
            CompensatoryService.approve_compensatory(waiting, approved_by=principal_user)

    def test_the_requester_withdraws_and_the_lesson_is_free_again(self, waiting, world):
        CompensatoryService.withdraw(waiting, world["teacher"])

        waiting.refresh_from_db()
        assert waiting.status == "cancelled"
        rows = CompensatoryService.day_options(
            world["school"], world["teacher"], world["upper"], SUNDAY
        )
        assert next(r for r in rows if r["period"] == 5)["ok"] is True

    def test_only_the_requester_withdraws(self, waiting, world):
        with pytest.raises(ValueError, match="لصاحب الطلب وحدَه"):
            CompensatoryService.withdraw(waiting, world["colleague"])

    def test_a_closed_request_cannot_be_withdrawn(self, waiting, world):
        CompensatoryService.withdraw(waiting, world["teacher"])
        with pytest.raises(ValueError, match="لصاحب الطلب وحدَه"):
            CompensatoryService.withdraw(waiting, world["teacher"])

    def test_the_list_offers_withdraw_to_the_requester(self, waiting, world, client):
        respond = reverse("compensatory_respond", args=[waiting.pk])
        world["teacher"].must_change_password = False
        world["teacher"].save(update_fields=["must_change_password"])
        client.force_login(world["teacher"])

        body = client.get(reverse("compensatory_list"), HTTP_HOST="localhost").content.decode()
        assert 'value="withdraw"' in body and respond in body

        client.post(respond, {"action": "withdraw"}, HTTP_HOST="localhost")
        waiting.refresh_from_db()
        assert waiting.status == "cancelled"


class TestMyOpenRequestsBusyMe:
    def test_a_second_request_in_the_same_period_is_refused_with_a_reason(self, world):
        _science(world, "upper", 0, 5, dt.time(10, 50), dt.time(11, 35))
        _request(world, "upper", SUNDAY, 5)

        # الأرضيُّ خامستُه 10:50–11:35 أيضاً: القيدُ في القاعدة بالرقم، فلا يُترك لخطئها الخام.
        with pytest.raises(ValueError, match="لك طلبُ تعويضٍ آخرُ في هذا الوقت"):
            _request(world, "ground", SUNDAY, 5)
        assert CompensatorySession.objects.count() == 1

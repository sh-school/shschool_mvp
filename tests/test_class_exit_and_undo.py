"""خروجُ الطالب بإذن المعلّم، ودقائقُ الحضور بالمادّة، والتراجعُ عن الخطأ (قرارات 2026-09-13).

- المعلّم ينقر «خرج بإذن» ثمّ «عاد»: لحظتان من النقرة، بلا إدخال.
- من لم يعد حتى نهاية الحصّة: يُعرض للمشرف «غائب · بإذن» ويُحفظ كذلك فلا يُحسب هارباً.
- دقائقُ الحضور بالمادّة = الجدول − الغياب − التأخّر − الخروج، محسوبةً من السجلّات.
- التراجع: المعلّم عن نقرته ما لم يثبّت المشرف؛ وأهلُ الرصد يحذفون حدثاً بسبب — وكلُّ تراجعٍ
  في سجلّ المراجعة، ويزول ما بُني عليه آليّاً.
"""

import re

import pytest
from django.urls import reverse

from core.models import AuditLog
from operations.class_exit import close_unreturned, come_back, leave
from operations.models import ClassExit, StudentAttendance
from operations.presence import presence_for
from tests.test_period_register import (  # noqa: F401 — التجهيزاتُ نفسُها
    SUNDAY,
    _auto,
    _confirm,
    _periods,
    at,
    kids,
    klass,
    other_teacher,
    subjects,
    supervisor,
    teacher,
    year,
)

pytestmark = pytest.mark.django_db


class TestTheTeacherLetsAStudentOut:
    def test_leave_then_return_records_both_moments(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)

        exit_ = leave(period, kids[0], "clinic", by=teacher, now=at(7, 20))
        come_back(period, kids[0], now=at(7, 32))

        exit_.refresh_from_db()
        assert (exit_.destination, exit_.minutes_away()) == ("clinic", 12)
        assert not StudentAttendance.objects.exists(), "خرج وعاد — حاضرٌ لا سجلَّ غياب"

    def test_a_second_leave_while_out_does_not_duplicate(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        leave(period, kids[0], "restroom", by=teacher, now=at(7, 20))

        leave(period, kids[0], "admin", by=teacher, now=at(7, 25))

        assert ClassExit.objects.count() == 1

    def test_who_never_came_back_is_absent_with_leave_not_an_escape(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        """خرج إلى العيادة في الثانية ولم يعد: «غائب · العيادة» — ولا هروبَ عليه."""
        periods = _periods(school, klass, teacher, 3)
        _confirm(klass, periods[0], {}, supervisor)
        leave(periods[1], kids[0], "clinic", by=teacher, now=at(8, 20))

        _confirm(klass, periods[1], {}, supervisor, now=at(9, 0))
        _confirm(klass, periods[2], {}, supervisor)

        row = StudentAttendance.objects.get(session=periods[1], student=kids[0])
        assert (row.status, row.whereabouts) == ("absent", "clinic")
        assert not _auto(kids[0], "class_escape").exists()
        exit_ = ClassExit.objects.get()
        assert exit_.returned_at is not None and exit_.minutes_away() == 35

    def test_close_unreturned_closes_at_the_bell_and_writes_no_attendance(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        """كان يكتب سطرَ `teacher_out` ويُغلق الخروجَ قبل الجرس إن ثُبّتت الحصّةُ في بدئها —
        فيسقط «عاد» من يد المعلّم. صار لا يُغلق قبل النهاية، ولا يكتب في سجلّ الحضور."""
        (period,) = _periods(school, klass, teacher, 1)
        _confirm(klass, period, {kids[0]: "present"}, supervisor, now=at(7, 30))
        exit_ = leave(period, kids[0], "clinic", by=teacher, now=at(7, 40))

        assert close_unreturned(period, now=at(7, 50)) == 0
        exit_.refresh_from_db()
        assert exit_.returned_at is None

        assert close_unreturned(period, now=at(7, 55)) == 1
        exit_.refresh_from_db()
        assert exit_.returned_at == at(7, 55)
        row = StudentAttendance.objects.get(session=period, student=kids[0])
        assert (row.status, row.source) == ("present", "supervisor")
        assert not StudentAttendance.objects.filter(source="teacher_out").exists()

    def test_the_supervisor_sees_the_unreturned_prefilled_absent_with_leave(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        """قبل أيّ تثبيت: الخانةُ «غائب» مختارةٌ والعيادةُ مكانُه — من الخروج نفسِه لا من سطرٍ مؤقّت."""
        (period,) = _periods(school, klass, teacher, 1)
        leave(period, kids[0], "clinic", by=teacher, now=at(7, 20))

        body = (
            client_as(supervisor)
            .get(reverse("wings:record_section", args=[klass.id]) + f"?date={SUNDAY.isoformat()}")
            .content.decode()
        )

        sid = kids[0].id
        assert re.search(rf'name="s-{sid}" value="absent" checked', body)
        assert not re.search(rf'name="s-{sid}" value="present" checked', body)
        select = re.search(rf'<select name="w-{sid}".*?</select>', body, re.S).group(0)
        assert re.search(r'<option value="clinic" selected>', select)
        assert not StudentAttendance.objects.exists(), "العرضُ لا يكتب"

    def test_the_endpoints_belong_to_the_sessions_teacher(
        self, client_as, school, seeded_calendar, klass, kids, teacher, other_teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        payload = {"student_id": str(kids[0].id), "destination": "clinic"}

        assert (
            client_as(other_teacher)
            .post(reverse("mark_exit", args=[period.id]), payload)
            .status_code
            == 403
        )
        response = client_as(teacher).post(reverse("mark_exit", args=[period.id]), payload)
        assert response.status_code == 200 and "عاد" in response.content.decode()
        response = client_as(teacher).post(reverse("mark_return", args=[period.id]), payload)
        assert response.status_code == 200 and "خرج بإذن" in response.content.decode()


class TestTheSupervisorIsNotified:
    """الطالبُ يأخذ بطاقةَ الخروج من الجناح من المشرف — فيُشعَر فوراً (قرارُ 2026-09-14)."""

    @pytest.mark.parametrize("destination", ["clinic", "admin"])
    def test_leaving_the_wing_notifies_its_holder(
        self, school, seeded_calendar, klass, kids, teacher, supervisor, destination
    ):
        from notifications.models import InAppNotification

        (period,) = _periods(school, klass, teacher, 1)

        leave(period, kids[0], destination, by=teacher, now=at(7, 20))

        notif = InAppNotification.objects.get(user=supervisor)
        assert kids[0].full_name in notif.title
        assert "بطاقةَ خروجٍ" in notif.body
        assert notif.priority == "high"

    def test_the_restroom_stays_inside_the_wing_and_is_silent(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        from notifications.models import InAppNotification

        (period,) = _periods(school, klass, teacher, 1)

        leave(period, kids[0], "restroom", by=teacher, now=at(7, 20))

        assert not InAppNotification.objects.filter(user=supervisor).exists()

    def test_a_section_outside_the_wings_has_nobody_to_notify(
        self, school, seeded_calendar, year, teacher
    ):
        from notifications.models import InAppNotification
        from tests.conftest import ClassGroupFactory, StudentEnrollmentFactory, UserFactory

        ese = ClassGroupFactory(
            school=school, grade="G7", section="9", level_type="prep", academic_year=year
        )
        student = UserFactory(full_name="طالب خاصّ", national_id="29300000098")
        StudentEnrollmentFactory(student=student, class_group=ese)
        (period,) = _periods(school, ese, teacher, 1)

        exit_ = leave(period, student, "clinic", by=teacher, now=at(7, 20))

        assert exit_.pk and not InAppNotification.objects.exists()


class TestPresenceMinutesBySubject:
    def test_minutes_are_schedule_minus_absence_late_and_exits(
        self, school, seeded_calendar, klass, kids, teacher, supervisor, subjects
    ):
        """ثلاثُ حصصٍ رياضيّات (45 د): غاب الأولى، وتأخّر 10 في الثانية، وخرج 12 في الثالثة
        ← حضر 135 − 45 − 10 − 12 = 68 دقيقة."""
        math, _science = subjects
        periods = _periods(school, klass, teacher, 3)
        for p in periods:
            p.subject = math
            p.save(update_fields=["subject"])
        _confirm(klass, periods[0], {kids[0]: "absent"}, supervisor)
        _confirm(klass, periods[1], {kids[0]: "late"}, supervisor, now=at(8, 20))
        leave(periods[2], kids[0], "restroom", by=teacher, now=at(9, 15))
        come_back(periods[2], kids[0], now=at(9, 27))
        _confirm(klass, periods[2], {}, supervisor)

        presence = presence_for(kids[0], school, SUNDAY, SUNDAY)

        row = presence.by_subject["الرياضيات"]
        assert (row.scheduled_periods, row.scheduled_minutes) == (3, 135)
        assert (
            row.absent_periods,
            row.late_count,
            row.late_minutes,
            row.exit_count,
            row.exit_minutes,
        ) == (1, 1, 10, 1, 12)
        assert row.present_minutes == 68
        assert row.present_pct == 50

    def test_escapes_are_counted_per_subject(
        self, school, seeded_calendar, klass, kids, teacher, supervisor, subjects
    ):
        math, science = subjects
        periods = _periods(school, klass, teacher, 3)
        periods[1].subject = science
        periods[1].save(update_fields=["subject"])
        _confirm(klass, periods[0], {}, supervisor)
        _confirm(klass, periods[1], {kids[0]: "absent"}, supervisor)
        _confirm(klass, periods[2], {}, supervisor)

        presence = presence_for(kids[0], school, SUNDAY, SUNDAY)

        assert presence.by_subject["العلوم"].escape_count == 1
        assert presence.total.escape_count == 1


class TestUndo:
    def test_the_teacher_undoes_a_late_tap_and_it_is_audited(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        from operations.period_register import tap_late

        (period,) = _periods(school, klass, teacher, 1)
        tap_late(period, kids[0], by=teacher, now=at(7, 22))

        response = client_as(teacher).post(
            reverse("undo_late_tap", args=[period.id]), {"student_id": str(kids[0].id)}
        )

        assert response.status_code == 200 and "دخل الآن" in response.content.decode()
        assert not StudentAttendance.objects.filter(student=kids[0]).exists()
        log = AuditLog.objects.get(action="delete")
        assert "تراجع" in log.object_repr and log.changes["late_minutes"] == 12

    def test_the_teacher_cannot_undo_what_the_supervisor_confirmed(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        _confirm(klass, period, {kids[0]: "late"}, supervisor, now=at(7, 30))

        client_as(teacher).post(
            reverse("undo_late_tap", args=[period.id]), {"student_id": str(kids[0].id)}
        )

        assert StudentAttendance.objects.filter(student=kids[0], source="supervisor").exists()

    def test_cancelling_an_exit_leaves_no_minutes(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        leave(period, kids[0], "clinic", by=teacher, now=at(7, 20))

        client_as(teacher).post(
            reverse("cancel_exit", args=[period.id]), {"student_id": str(kids[0].id)}
        )

        assert not ClassExit.objects.exists()
        assert presence_for(kids[0], school, SUNDAY, SUNDAY).total.exit_minutes == 0
        assert AuditLog.objects.filter(action="delete").exists()

    def test_deleting_an_event_from_the_profile_removes_its_auto_infraction(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        """رُصد متأخّراً 12 دقيقة على الطالب الخطأ: الحذفُ بسببٍ يُزيل مخالفةَ 1-01 معه."""
        (period,) = _periods(school, klass, teacher, 1)
        _confirm(klass, period, {kids[0]: "late"}, supervisor, now=at(7, 22))
        assert _auto(kids[0], "period_tardy").count() == 1
        row = StudentAttendance.objects.get(session=period, student=kids[0])

        response = client_as(supervisor).post(
            reverse("wings:attendance_event_delete", args=[row.pk]),
            {"reason": "رُصد على طالبٍ آخر"},
        )

        assert response.status_code == 302
        assert not StudentAttendance.objects.filter(pk=row.pk).exists()
        assert not _auto(kids[0], "period_tardy").exists()
        undo = AuditLog.objects.filter(
            action="delete", object_repr__startswith="حذفُ سجلّ حضور"
        ).get()
        assert undo.changes["reason"] == "رُصد على طالبٍ آخر"

    def test_deletion_needs_a_reason_and_the_recorders_role(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        _confirm(klass, period, {kids[0]: "absent"}, supervisor)
        row = StudentAttendance.objects.get(session=period, student=kids[0])
        url = reverse("wings:attendance_event_delete", args=[row.pk])

        client_as(supervisor).post(url, {"reason": ""})
        assert StudentAttendance.objects.filter(pk=row.pk).exists(), "بلا سببٍ لا حذف"
        assert client_as(teacher).post(url, {"reason": "خطأ"}).status_code in (302, 403)
        assert StudentAttendance.objects.filter(pk=row.pk).exists(), "المعلّمُ ليس من أهل الرصد"

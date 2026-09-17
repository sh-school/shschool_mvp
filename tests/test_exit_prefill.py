"""[LEGAL] «خرج بإذن» في كشف المشرف — بلا نقرةٍ زائدة، ولا «حاضر» كاذب، ولا «هروب» كاذب.

قرارُ المالك (2026-09-16) الذي تحرسه هذه الاختبارات:
- الكشفُ يُملأ عند القراءة ولا يُكتب قبل التثبيت: من لم يعد «غائب» بمكانه (العيادة،
  وإلّا «خرج بإذن») بعلامة «بإذن المعلّم». ودورةُ المياه والحصّةُ جارية «حاضر» بشارة.
- الأولويّة: ما رصده المشرف ← خروجٌ لم يعد صاحبُه ← نقرةُ التأخّر ← حاضر.
- الخروجُ الذي رآه المشرفُ يُحفظ على السطر (`exit`) أيّاً كان اختيارُه.
- عند الجرس: يُغلق المفتوح، ويُقلب الحاضرُ الذي لم يحسب الخروجَ غياباً بإذن — بسجلّ
  مراجعة، وتزول مخالفةُ التأخّر، ولا يُمسّ ما لم يُثبَّت.
- العودةُ قبل الجرس أو الإلغاء: الغيابُ المشتقُّ منه وحدَه يرجع حاضراً.
"""

import datetime as dt
import re

import pytest
from django.urls import reverse
from django.utils import timezone

from core.models import AuditLog
from operations.class_exit import close_unreturned, come_back, leave, unreturned_of
from operations.exit_reflection import finalize_exits_for_day
from operations.models import ClassExit, PeriodConfirmation, Session, StudentAttendance
from operations.period_register import periods_of, prefill_of
from operations.presence import presence_for
from tests.test_period_register import (  # noqa: F401 — التجهيزاتُ نفسُها
    SUNDAY,
    _auto,
    _confirm,
    _elective_twin,
    _periods,
    at,
    kids,
    klass,
    other_teacher,
    supervisor,
    teacher,
    year,
)

pytestmark = pytest.mark.django_db


def _page(client_as, user, klass, day=SUNDAY, p=None) -> str:
    url = reverse("wings:record_section", args=[klass.id]) + f"?date={day.isoformat()}"
    if p:
        url += f"&p={p}"
    return client_as(user).get(url).content.decode()


def _checked(body, sid) -> str | None:
    found = re.search(rf'name="s-{sid}" value="(\w+)" checked', body)
    return found.group(1) if found else None


def _selected(body, sid) -> str:
    select = re.search(rf'<select name="w-{sid}".*?</select>', body, re.S).group(0)
    found = re.search(r'<option value="(\w*)" selected>', select)
    return found.group(1) if found else ""


def _row(session, student):
    return StudentAttendance.objects.get(session=session, student=student)


def _trail():
    """سطورُ المراجعة التي يكتبها أثرُ الخروج — لا تعديلاتُ الحسابات في التجهيز."""
    return AuditLog.objects.filter(action="update", object_repr__startswith="أثرُ الخروج")


def _period(klass, session, day=SUNDAY):
    return next(p for p in periods_of(klass, day) if p.start == session.start_time)


# ══════════════════════════════════════════════════════════════════
# الملءُ عند القراءة
# ══════════════════════════════════════════════════════════════════


class TestTheRegisterIsPrefilled:
    def test_an_open_clinic_exit_prefills_absent_with_the_clinic_and_the_marker(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        exit_ = leave(period, kids[0], "clinic", by=teacher, now=at(7, 20))

        body = _page(client_as, supervisor, klass)

        sid = kids[0].id
        assert _checked(body, sid) == "absent"
        assert _selected(body, sid) == "clinic"
        assert re.search(
            r'value="absent" checked>\s*<span>غائب <small[^>]*>بإذن المعلّم</small>', body
        )
        assert "خرج 07:20 · العيادة" in body
        assert f'name="o-{sid}" value="{exit_.pk}"' in body
        assert f'data-student="{sid}" data-prefill="out"' in body
        assert _checked(body, kids[1].id) == "present"
        assert not StudentAttendance.objects.exists(), "العرضُ لا يكتب شيئاً"

    @pytest.mark.parametrize("destination", ["admin", "other"])
    def test_other_destinations_prefill_out_with_permit(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor, destination
    ):
        (period,) = _periods(school, klass, teacher, 1)
        leave(period, kids[0], destination, by=teacher, now=at(7, 20))

        body = _page(client_as, supervisor, klass)

        assert _checked(body, kids[0].id) == "absent"
        assert _selected(body, kids[0].id) == "out_permit"

    def test_an_open_restroom_trip_stays_present_until_the_bell(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (session,) = _periods(school, klass, teacher, 1)
        leave(session, kids[0], "restroom", by=teacher, now=at(7, 20))
        period = _period(klass, session)

        during = prefill_of(klass, SUNDAY, period, at(7, 30)).of(kids[0].id)
        after = prefill_of(klass, SUNDAY, period, at(7, 56)).of(kids[0].id)

        assert (during.status, during.whereabouts, during.marker) == ("present", "", "in_wing")
        assert during.away_note == "في دورة المياه منذ 07:20"
        assert not during.seen_exit, "لا يُحسب مرئيّاً ما لم يُعرض غياباً"
        assert (after.status, after.whereabouts, after.marker) == ("absent", "out_permit", "out")

    def test_the_restroom_badge_on_a_period_still_running(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        """يومٌ قادم: الحصّةُ لم تنتهِ بعد بساعة الخادم — فالشاشةُ «حاضر» وشارة."""
        day = timezone.localdate() + dt.timedelta(days=21)
        (session,) = _periods(school, klass, teacher, 1, day=day)
        leave(session, kids[0], "restroom", by=teacher, now=at(7, 20, day))

        body = _page(client_as, supervisor, klass, day=day)

        assert _checked(body, kids[0].id) == "present"
        assert "في دورة المياه منذ 07:20" in body
        assert f'name="o-{kids[0].id}"' not in body

    def test_a_student_who_came_back_is_not_prefilled(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        leave(period, kids[0], "clinic", by=teacher, now=at(7, 20))
        come_back(period, kids[0], now=at(7, 30))

        body = _page(client_as, supervisor, klass)

        assert _checked(body, kids[0].id) == "present"
        assert "بإذن المعلّم</small>" not in body

    def test_returning_after_the_bell_still_counts_as_unreturned(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        leave(period, kids[0], "clinic", by=teacher, now=at(7, 20))
        come_back(period, kids[0], now=at(7, 57))

        away = unreturned_of(klass, SUNDAY)[kids[0].id][period.start_time]

        assert (away.whereabouts, away.still_open) == ("clinic", False)

    def test_unreturned_of_is_one_query(
        self, school, seeded_calendar, klass, kids, teacher, supervisor, django_assert_num_queries
    ):
        periods = _periods(school, klass, teacher, 3)
        for i, session in enumerate(periods):
            leave(session, kids[i], "clinic", by=teacher, now=at(7 + i, 20))

        with django_assert_num_queries(1):
            outs = unreturned_of(klass, SUNDAY)

        assert len(outs) == 3

    def test_an_exit_after_the_supervisors_present_reopens_the_cell_absent(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        """«حاضر» كُتب قبل الخروج لا يعلم به — فيُفتح غائباً بإذن برقم الخروج."""
        (period,) = _periods(school, klass, teacher, 1)
        _confirm(klass, period, {kids[0]: "present"}, supervisor, now=at(7, 15))
        exit_ = leave(period, kids[0], "clinic", by=teacher, now=at(7, 20))

        body = _page(client_as, supervisor, klass)

        sid = kids[0].id
        assert (_checked(body, sid), _selected(body, sid)) == ("absent", "clinic")
        assert "خرج 07:20 · العيادة" in body
        assert f'name="o-{sid}" value="{exit_.pk}"' in body
        assert f'data-student="{sid}" data-prefill="out"' in body

    def test_a_manual_absence_keeps_its_place_and_the_exit_is_a_badge(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        _confirm(
            klass,
            period,
            {kids[0]: {"status": "absent", "whereabouts": "activity"}},
            supervisor,
            now=at(7, 15),
        )
        leave(period, kids[0], "clinic", by=teacher, now=at(7, 20))

        body = _page(client_as, supervisor, klass)

        sid = kids[0].id
        assert (_checked(body, sid), _selected(body, sid)) == ("absent", "activity")
        assert "خرج 07:20 · العيادة" in body
        assert f'name="o-{sid}"' not in body
        assert f'data-student="{sid}" data-prefill=""' in body

    def test_a_confirmed_derived_absence_is_shielded_from_the_bulk_button(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        """إعادةُ فتح حصّةٍ مثبّتة: الغيابُ المشتقُّ من الخروج يبقى «out» فلا يمحوه «الكلُّ حاضر»."""
        (period,) = _periods(school, klass, teacher, 1)
        exit_ = leave(period, kids[0], "clinic", by=teacher, now=at(7, 20))
        _confirm(klass, period, {}, supervisor, now=at(7, 25))
        assert _row(period, kids[0]).exit_id == exit_.pk

        body = _page(client_as, supervisor, klass)

        sid = kids[0].id
        assert f'data-student="{sid}" data-prefill="out"' in body
        assert f'name="o-{sid}" value="{exit_.pk}"' in body
        assert _checked(body, sid) == "absent"

    def test_the_supervisor_who_saw_a_later_exit_may_keep_his_present(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        _confirm(klass, period, {kids[0]: "present"}, supervisor, now=at(7, 15))
        exit_ = leave(period, kids[0], "clinic", by=teacher, now=at(7, 20))
        pick = prefill_of(klass, SUNDAY, _period(klass, period), at(8, 0)).of(kids[0].id)
        assert pick.seen_exit == str(exit_.pk)

        _confirm(
            klass,
            period,
            {kids[0]: {"status": "present", "exit": pick.seen_exit}},
            supervisor,
            now=at(8, 0),
        )
        flipped = finalize_exits_for_day(school, SUNDAY, now=at(8, 5))

        row = _row(period, kids[0])
        assert (row.status, row.exit_id, flipped) == ("present", exit_.pk, 0)
        assert not _trail().exists(), "اختيارُه وهو يرى الخروجَ لا يُبدَّل"

    def test_a_late_tap_yields_to_an_unreturned_exit(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        from operations.period_register import tap_late

        (session,) = _periods(school, klass, teacher, 1)
        tap_late(session, kids[0], by=teacher, now=at(7, 22))
        tap_late(session, kids[1], by=teacher, now=at(7, 22))
        leave(session, kids[0], "admin", by=teacher, now=at(7, 30))

        prefill = prefill_of(klass, SUNDAY, _period(klass, session), at(7, 40))

        assert prefill.of(kids[0].id).status == "absent"
        assert (prefill.of(kids[1].id).status, prefill.of(kids[1].id).tap) == ("late", 12)

    def test_a_new_teacher_event_changes_the_draft_key(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        from operations.period_register import tap_late

        (period,) = _periods(school, klass, teacher, 1)

        def key():
            return re.search(
                r'data-draft-key="([^"]+)"', _page(client_as, supervisor, klass)
            ).group(1)

        before = key()
        leave(period, kids[0], "clinic", by=teacher, now=at(7, 20))
        with_exit = key()
        tap_late(period, kids[1], by=teacher, now=at(7, 22))
        with_tap = key()

        assert len({before, with_exit, with_tap}) == 3
        assert with_tap == key(), "البصمةُ ثابتةٌ ما لم يتغيّر شيء"

    def test_the_bell_changes_the_fingerprint_of_a_restroom_trip(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        """الخروجُ نفسُه والنقراتُ نفسُها — لكنّ الخانةَ صارت «غائباً»، فالمسوّدةُ القديمةُ تسقط."""
        (session,) = _periods(school, klass, teacher, 1)
        leave(session, kids[0], "restroom", by=teacher, now=at(7, 40))
        period = _period(klass, session)

        during = prefill_of(klass, SUNDAY, period, at(7, 50)).fingerprint
        again = prefill_of(klass, SUNDAY, period, at(7, 52)).fingerprint
        after = prefill_of(klass, SUNDAY, period, at(7, 57)).fingerprint

        assert during == again
        assert during != after

    def test_the_beats_flip_changes_the_fingerprint(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (session,) = _periods(school, klass, teacher, 1)
        _confirm(klass, session, {}, supervisor, now=at(7, 15))
        leave(session, kids[0], "restroom", by=teacher, now=at(7, 40))
        before = prefill_of(klass, SUNDAY, _period(klass, session), at(7, 50)).fingerprint

        finalize_exits_for_day(school, SUNDAY, now=at(8, 0))

        after = prefill_of(klass, SUNDAY, _period(klass, session), at(8, 1)).fingerprint
        assert before != after

    def test_the_bulk_button_is_told_which_rows_to_skip(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        """«الكلُّ حاضر» يتخطّى `tr[data-prefill="out"]` في period-register.js."""
        import pathlib

        (period,) = _periods(school, klass, teacher, 1)
        leave(period, kids[0], "clinic", by=teacher, now=at(7, 20))

        body = _page(client_as, supervisor, klass)
        script = pathlib.Path("static/js/period-register.js").read_text(encoding="utf-8")

        assert f'data-student="{kids[0].id}" data-prefill="out"' in body
        assert f'data-student="{kids[1].id}" data-prefill=""' in body
        assert 'tr[data-prefill="out"]' in script

    def test_another_column_shows_the_exit_in_its_title(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 2)
        leave(periods[0], kids[0], "clinic", by=teacher, now=at(7, 20))

        body = _page(client_as, supervisor, klass, p="08:10")

        assert "خرج 07:20 · العيادة بإذن المعلّم ولم يعد" in body
        assert "بإذن المعلّم بإذن المعلّم" not in body
        assert _checked(body, kids[0].id) == "present", "الحصّةُ المفتوحة غيرُ حصّة الخروج"

    def test_the_track_note_reads_once_for_every_kind_of_exit(self):
        from operations.class_exit import Away
        from operations.period_register import away_note, track_note

        end = at(7, 55)
        legacy = Away(exit=None, whereabouts="clinic")
        restroom = Away(
            exit=None,
            whereabouts="out_permit",
            destination="restroom",
            left_at=at(7, 20),
            still_open=True,
        )

        assert away_note(legacy, at(8, 0), end) == "خرج"
        assert track_note(legacy, at(8, 0), end) == "خرج بإذن المعلّم ولم يعد"
        assert track_note(restroom, at(7, 30), end) == "في دورة المياه منذ 07:20 بإذن المعلّم"
        assert track_note(restroom, at(8, 0), end) == (
            "خرج 07:20 · دورة المياه بإذن المعلّم ولم يعد"
        )
        assert track_note(None, at(8, 0), end) == ""

    def test_the_notification_opens_the_exits_period(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        from notifications.models import InAppNotification

        periods = _periods(school, klass, teacher, 2)
        leave(periods[1], kids[0], "clinic", by=teacher, now=at(8, 20))

        notif = InAppNotification.objects.get(user=supervisor)
        assert "p=08:10" in notif.related_url


# ══════════════════════════════════════════════════════════════════
# التثبيت
# ══════════════════════════════════════════════════════════════════


class TestConfirmingThePrefill:
    def test_posting_the_rendered_form_saves_absent_with_leave_and_no_escape(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 3)
        _confirm(klass, periods[0], {}, supervisor)
        exit_ = leave(periods[1], kids[0], "clinic", by=teacher, now=at(8, 20))
        body = _page(client_as, supervisor, klass, p="08:10")
        sid = kids[0].id
        assert (_checked(body, sid), _selected(body, sid)) == ("absent", "clinic")

        client_as(supervisor).post(
            reverse("wings:record_period", args=[klass.id]),
            {
                "date": SUNDAY.isoformat(),
                "start": "08:10",
                **{f"s-{kid.id}": _checked(body, kid.id) for kid in kids},
                **{f"w-{kid.id}": _selected(body, kid.id) for kid in kids},
                f"o-{sid}": str(exit_.pk),
            },
        )
        _confirm(klass, periods[2], {}, supervisor)

        row = _row(periods[1], kids[0])
        assert (row.status, row.whereabouts, row.source, row.exit_id) == (
            "absent",
            "clinic",
            "supervisor",
            exit_.pk,
        )
        assert not _auto(kids[0], "class_escape").exists()

    def test_a_present_student_keeps_no_whereabouts(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)

        _confirm(
            klass, period, {kids[0]: {"status": "present", "whereabouts": "clinic"}}, supervisor
        )

        assert _row(period, kids[0]).whereabouts == ""

    def test_a_confirm_at_the_start_leaves_the_exit_open_for_the_teacher(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        exit_ = leave(period, kids[0], "clinic", by=teacher, now=at(7, 20))

        _confirm(klass, period, {}, supervisor, now=at(7, 25))

        row = _row(period, kids[0])
        assert (row.status, row.whereabouts, row.exit_id) == ("absent", "clinic", exit_.pk)
        exit_.refresh_from_db()
        assert exit_.returned_at is None
        assert come_back(period, kids[0], now=at(7, 40, SUNDAY)) is not None

    def test_the_supervisor_who_saw_the_exit_may_keep_him_present(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        exit_ = leave(period, kids[0], "clinic", by=teacher, now=at(7, 20))

        _confirm(
            klass,
            period,
            {kids[0]: {"status": "present", "exit": str(exit_.pk)}},
            supervisor,
            now=at(7, 30),
        )
        flipped = finalize_exits_for_day(school, SUNDAY, now=at(8, 0))

        row = _row(period, kids[0])
        assert (row.status, row.exit_id, flipped) == ("present", exit_.pk, 0)

    def test_a_stale_present_after_the_bell_is_not_saved(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        """كشفٌ فُتح قبل الخروج وأُرسل بعد الجرس «حاضراً»: لم يرَ المشرفُ الخروج."""
        (period,) = _periods(school, klass, teacher, 1)
        exit_ = leave(period, kids[0], "admin", by=teacher, now=at(7, 20))

        _confirm(klass, period, {kids[0]: "present"}, supervisor, now=at(8, 0))

        row = _row(period, kids[0])
        assert (row.status, row.whereabouts, row.exit_id) == ("absent", "out_permit", exit_.pk)
        assert _trail().filter(changes__exit=str(exit_.pk)).exists()
        assert PeriodConfirmation.objects.get().absent_count == 1


# ══════════════════════════════════════════════════════════════════
# نهايةُ الحصّة
# ══════════════════════════════════════════════════════════════════


class TestThePeriodEnds:
    def test_close_unreturned_waits_for_the_bell(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        exit_ = leave(period, kids[0], "clinic", by=teacher, now=at(7, 20))

        assert close_unreturned(period, now=at(7, 30)) == 0
        exit_.refresh_from_db()
        assert exit_.returned_at is None

        assert close_unreturned(period, now=at(8, 0)) == 1
        exit_.refresh_from_db()
        assert exit_.returned_at == at(7, 55)
        assert not StudentAttendance.objects.exists(), "لا سطرَ teacher_out بعد اليوم"

    def test_an_exit_after_the_confirmation_turns_present_into_absent_with_leave(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        _confirm(klass, period, {}, supervisor, now=at(7, 15))
        exit_ = leave(period, kids[0], "admin", by=teacher, now=at(7, 20))

        assert finalize_exits_for_day(school, SUNDAY, now=at(7, 50)) == 0
        assert _row(period, kids[0]).status == "present", "قبل الجرس لا شيء"

        assert finalize_exits_for_day(school, SUNDAY, now=at(8, 0)) == 1

        row = _row(period, kids[0])
        assert (row.status, row.whereabouts, row.exit_id, row.source) == (
            "absent",
            "out_permit",
            exit_.pk,
            "supervisor",
        )
        exit_.refresh_from_db()
        assert exit_.returned_at == at(7, 55)
        log = _trail().get()
        assert log.user is None and log.changes["after"]["status"] == "absent"
        c = PeriodConfirmation.objects.get()
        assert (c.present_count, c.absent_count) == (3, 1)

        assert finalize_exits_for_day(school, SUNDAY, now=at(8, 5)) == 0, "ثابتةُ التكرار"
        assert _trail().count() == 1

    def test_a_restroom_trip_unreturned_at_the_bell_is_absent_with_leave(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        _confirm(klass, period, {}, supervisor, now=at(7, 15))
        leave(period, kids[0], "restroom", by=teacher, now=at(7, 50))

        finalize_exits_for_day(school, SUNDAY, now=at(8, 0))

        row = _row(period, kids[0])
        assert (row.status, row.whereabouts) == ("absent", "out_permit")

    def test_a_late_cell_loses_its_tardy_infraction(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        _confirm(klass, period, {kids[0]: "late"}, supervisor, now=at(7, 30))
        assert _auto(kids[0], "period_tardy").count() == 1
        leave(period, kids[0], "clinic", by=teacher, now=at(7, 35))

        finalize_exits_for_day(school, SUNDAY, now=at(8, 0))

        row = _row(period, kids[0])
        assert (row.status, row.whereabouts, row.late_minutes) == ("absent", "clinic", None)
        assert not _auto(kids[0], "period_tardy").exists()

    def test_no_escape_follows_a_flipped_period(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 3)
        _confirm(klass, periods[0], {}, supervisor)
        _confirm(klass, periods[1], {}, supervisor, now=at(8, 15))
        leave(periods[1], kids[0], "clinic", by=teacher, now=at(8, 20))
        _confirm(klass, periods[2], {}, supervisor)

        finalize_exits_for_day(school, SUNDAY, now=at(9, 0))

        assert _row(periods[1], kids[0]).status == "absent"
        assert not _auto(kids[0], "class_escape").exists()
        assert not _auto(kids[0], "school_escape").exists()

    def test_an_unconfirmed_period_is_only_closed(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        exit_ = leave(period, kids[0], "clinic", by=teacher, now=at(7, 20))

        assert finalize_exits_for_day(school, SUNDAY, now=at(8, 0)) == 0

        assert not StudentAttendance.objects.exists()
        exit_.refresh_from_db()
        assert exit_.returned_at == at(7, 55)

    def test_both_sessions_of_an_elective_pair_are_flipped(
        self, client_as, school, seeded_calendar, klass, kids, teacher, other_teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 7)
        twin = _elective_twin(school, klass, other_teacher)
        _confirm(klass, periods[3], {}, supervisor, now=at(10, 15))
        leave(twin, kids[0], "clinic", by=other_teacher, now=at(10, 20))

        body = _page(client_as, supervisor, klass, p="10:10")
        assert _checked(body, kids[0].id) == "absent", "«حاضر» قبل الخروج لا يعلم به"
        assert "خرج 10:20 · العيادة" in body

        assert finalize_exits_for_day(school, SUNDAY, now=at(11, 0)) == 1

        for session in (periods[3], twin):
            row = _row(session, kids[0])
            assert (row.status, row.whereabouts) == ("absent", "clinic")

    def test_an_elective_twin_exit_prefills_the_shared_cell(
        self, client_as, school, seeded_calendar, klass, kids, teacher, other_teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 7)
        twin = _elective_twin(school, klass, other_teacher)
        exit_ = leave(twin, kids[0], "clinic", by=other_teacher, now=at(10, 20))

        body = _page(client_as, supervisor, klass, p="10:10")
        assert _checked(body, kids[0].id) == "absent"

        _confirm(
            klass,
            periods[3],
            {kids[0]: {"status": "absent", "whereabouts": "clinic", "exit": str(exit_.pk)}},
            supervisor,
        )
        assert Session.objects.filter(pk__in=[periods[3].pk, twin.pk]).count() == 2
        for session in (periods[3], twin):
            assert (_row(session, kids[0]).status, _row(session, kids[0]).exit_id) == (
                "absent",
                exit_.pk,
            )

    def test_a_finished_day_costs_the_beat_one_query(
        self, school, seeded_calendar, klass, kids, teacher, supervisor, django_assert_num_queries
    ):
        periods = _periods(school, klass, teacher, 2)
        _confirm(klass, periods[0], {}, supervisor, now=at(7, 15))
        leave(periods[0], kids[0], "admin", by=teacher, now=at(7, 20))
        leave(periods[1], kids[1], "clinic", by=teacher, now=at(8, 20))
        assert finalize_exits_for_day(school, SUNDAY, now=at(9, 0)) == 1

        with django_assert_num_queries(1):
            assert finalize_exits_for_day(school, SUNDAY, now=at(9, 5)) == 0

    def test_a_failed_flip_still_closes_the_exit_and_is_retried(
        self, school, seeded_calendar, klass, kids, teacher, supervisor, monkeypatch
    ):
        from operations import exit_reflection

        (period,) = _periods(school, klass, teacher, 1)
        _confirm(klass, period, {}, supervisor, now=at(7, 15))
        exit_ = leave(period, kids[0], "admin", by=teacher, now=at(7, 20))

        def boom(*args, **kwargs):
            raise RuntimeError("عطبٌ مصطنع")

        with monkeypatch.context() as patch:
            patch.setattr(exit_reflection, "refresh_counts", boom)
            assert finalize_exits_for_day(school, SUNDAY, now=at(8, 0)) == 0
        exit_.refresh_from_db()
        assert exit_.returned_at == at(7, 55), "الإغلاقُ لا يسقط مع القلب"
        assert _row(period, kids[0]).status == "present"

        assert finalize_exits_for_day(school, SUNDAY, now=at(8, 5)) == 1
        assert _row(period, kids[0]).status == "absent"

    def test_a_flip_without_the_confirmer_signs_escapes_with_the_teacher(
        self, school, seeded_calendar, klass, kids, teacher, supervisor, monkeypatch
    ):
        from operations import exit_reflection

        (period,) = _periods(school, klass, teacher, 1)
        _confirm(klass, period, {}, supervisor, now=at(7, 15))
        PeriodConfirmation.objects.update(confirmed_by=None)
        leave(period, kids[0], "admin", by=teacher, now=at(7, 20))
        signed = []
        monkeypatch.setattr(
            exit_reflection, "sync_escapes", lambda klass, day, by: signed.append(by) or 0
        )

        assert finalize_exits_for_day(school, SUNDAY, now=at(8, 0)) == 1

        assert signed == [teacher]

    def test_no_reporter_at_all_skips_the_escape_check_but_keeps_the_flip(
        self, school, seeded_calendar, klass, kids, teacher, supervisor, monkeypatch
    ):
        from operations import exit_reflection

        (period,) = _periods(school, klass, teacher, 1)
        _confirm(klass, period, {}, supervisor, now=at(7, 15))
        PeriodConfirmation.objects.update(confirmed_by=None)
        exit_ = leave(period, kids[0], "admin", by=teacher, now=at(7, 20))
        ClassExit.objects.filter(pk=exit_.pk).update(allowed_by=None)
        signed = []
        monkeypatch.setattr(
            exit_reflection, "sync_escapes", lambda klass, day, by: signed.append(by) or 0
        )

        assert finalize_exits_for_day(school, SUNDAY, now=at(8, 0)) == 1

        assert signed == []
        assert _row(period, kids[0]).status == "absent"

    def test_the_beat_task_runs_school_by_school(
        self, school, seeded_calendar, klass, kids, teacher, supervisor, monkeypatch
    ):
        from operations import exit_reflection
        from operations.tasks import finalize_period_exits_task

        seen = []
        monkeypatch.setattr(
            exit_reflection,
            "finalize_exits_for_day",
            lambda school, day, now: seen.append((school.pk, day)) or 0,
        )

        result = finalize_period_exits_task()

        assert (school.pk, timezone.localdate()) in seen
        assert result["failed_schools"] == 0

    def test_the_task_is_scheduled_every_five_minutes_on_school_days(self):
        from shschool.celery import app

        (entry,) = (
            e
            for e in app.conf.beat_schedule.values()
            if e["task"] == "operations.finalize_period_exits"
        )
        when = entry["schedule"]
        assert when.minute == set(range(0, 60, 5))
        assert when.day_of_week == {0, 1, 2, 3, 4}, "الأحد–الخميس"
        assert min(when.hour) <= 7 and max(when.hour) >= 13


# ══════════════════════════════════════════════════════════════════
# العودةُ والإلغاء
# ══════════════════════════════════════════════════════════════════


class TestTheStudentComesBack:
    def test_coming_back_before_the_bell_reverts_a_derived_absence(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        exit_ = leave(period, kids[0], "clinic", by=teacher, now=at(7, 20))
        _confirm(klass, period, {}, supervisor, now=at(7, 25))
        assert _row(period, kids[0]).status == "absent"

        come_back(period, kids[0], now=at(7, 40), by=teacher)

        row = _row(period, kids[0])
        assert (row.status, row.whereabouts, row.exit_id) == ("present", "", exit_.pk)
        log = _trail().get()
        assert log.user == teacher and log.changes["after"]["status"] == "present"
        assert PeriodConfirmation.objects.get().absent_count == 0

    def test_the_return_endpoint_reverts_through_the_teacher(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        """بساعة الخادم الحصّةُ في يومٍ قادم — فالعودةُ قبل الجرس."""
        day = timezone.localdate() + dt.timedelta(days=21)
        (period,) = _periods(school, klass, teacher, 1, day=day)
        leave(period, kids[0], "clinic", by=teacher, now=timezone.now())
        _confirm(klass, period, {}, supervisor, now=at(7, 15, day), day=day)

        client_as(teacher).post(
            reverse("mark_return", args=[period.id]), {"student_id": str(kids[0].id)}
        )

        assert _row(period, kids[0]).status == "present"
        assert _trail().get().user == teacher

    def test_a_manual_absence_is_never_reverted(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        leave(period, kids[0], "clinic", by=teacher, now=at(7, 20))
        _confirm(klass, period, {kids[0]: "absent"}, supervisor, now=at(7, 25))

        come_back(period, kids[0], now=at(7, 40), by=teacher)

        row = _row(period, kids[0])
        assert (row.status, row.exit_id) == ("absent", None)
        assert not _trail().exists()

    def test_coming_back_after_the_bell_keeps_the_absence(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        leave(period, kids[0], "clinic", by=teacher, now=at(7, 20))
        _confirm(klass, period, {}, supervisor, now=at(7, 25))

        come_back(period, kids[0], now=at(7, 58), by=teacher)

        assert _row(period, kids[0]).status == "absent"

    def test_cancelling_the_exit_reverts_a_derived_absence(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        leave(period, kids[0], "clinic", by=teacher, now=at(7, 20))
        _confirm(klass, period, {}, supervisor, now=at(7, 25))

        client_as(teacher).post(
            reverse("cancel_exit", args=[period.id]), {"student_id": str(kids[0].id)}
        )

        row = _row(period, kids[0])
        assert (row.status, row.whereabouts, row.exit_id) == ("present", "", None)
        assert not ClassExit.objects.exists()
        assert _trail().filter(user=teacher).exists()

    def test_deleting_the_exit_from_the_file_reverts_a_derived_absence(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        exit_ = leave(period, kids[0], "clinic", by=teacher, now=at(7, 20))
        _confirm(klass, period, {}, supervisor, now=at(7, 25))
        assert _row(period, kids[0]).status == "absent"

        client_as(supervisor).post(
            reverse("wings:exit_event_delete", args=[exit_.pk]), {"reason": "طالبٌ آخر"}
        )

        row = _row(period, kids[0])
        assert (row.status, row.whereabouts, row.exit_id) == ("present", "", None)
        assert not ClassExit.objects.exists()
        log = _trail().get()
        assert log.user == supervisor and "طالبٌ آخر" in log.changes["why"]
        assert PeriodConfirmation.objects.get().absent_count == 0

    def test_deleting_an_exit_leaves_a_manual_absence(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        exit_ = leave(period, kids[0], "clinic", by=teacher, now=at(7, 20))
        _confirm(klass, period, {kids[0]: "absent"}, supervisor, now=at(7, 25))

        client_as(supervisor).post(
            reverse("wings:exit_event_delete", args=[exit_.pk]), {"reason": "خطأ"}
        )

        assert _row(period, kids[0]).status == "absent"
        assert not _trail().exists()

    def test_a_return_between_render_and_post_is_not_saved_absent(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        exit_ = leave(period, kids[0], "clinic", by=teacher, now=at(7, 20))
        come_back(period, kids[0], now=at(7, 26), by=teacher)

        _confirm(
            klass,
            period,
            {kids[0]: {"status": "absent", "whereabouts": "clinic", "exit": str(exit_.pk)}},
            supervisor,
            now=at(7, 28),
        )

        row = _row(period, kids[0])
        assert (row.status, row.whereabouts, row.exit_id) == ("present", "", exit_.pk)


class TestPresenceMinutes:
    def test_an_unreturned_exit_is_not_subtracted_twice(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        leave(period, kids[0], "clinic", by=teacher, now=at(7, 20))
        _confirm(klass, period, {}, supervisor, now=at(9, 0))

        total = presence_for(kids[0], school, SUNDAY, SUNDAY).total

        assert (total.scheduled_minutes, total.absent_minutes) == (45, 45)
        assert (total.exit_count, total.exit_minutes, total.present_minutes) == (1, 0, 0)

"""[LEGAL] مخالفاتُ الرصد تبلغ الأسرة — قرارُ المالك (2026-09-16).

- الهروبُ من المدرسة (3-10) **فوراً** بعد الالتزام، بمسار المخالفة اليدويّة نفسِه.
- التأخّرُ عن الحصّة والهروبُ منها في **ملخّصٍ يوميٍّ واحد** لكلّ طالب، الساعة 15:00
  من الأحد إلى الخميس — ويومُه يومُ الحصّة، وحالتُه ساعةَ الإرسال.
- ما أُرسل لا يُعاد — ولو حُذفت المخالفةُ وأُعيدت كما كانت؛ وما جدّ بعد الإرسال
  يُرسَل **إضافةً** بعنوانٍ يسمّي يومَه.
- الرسالةُ عددٌ وتاريخٌ وإحالةٌ إلى البوابة، لا أكثر (تقليلُ البيانات).
- لمن يرى السلوكَ (`can_view_behavior`) ولم يسحب موافقتَه.
"""

import datetime as dt
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from django.urls import reverse

from behavior.digest import (
    count_phrase,
    school_days_back,
    send_day,
)
from behavior.models import AutoInfractionNotice, BehaviorInfraction
from behavior.services import BehaviorService
from behavior.tasks import send_auto_infraction_digest
from core.models import ConsentRecord, ParentStudentLink
from notifications.hub import (
    _CONSENT_DATA_TYPE,
    DEFAULT_CHANNELS,
    DEFAULT_PRIORITY,
    NotificationHub,
    _map_event_type,
)
from notifications.models import InAppNotification
from operations.models import Session
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    SchoolFactory,
    StudentEnrollmentFactory,
    UserFactory,
)
from tests.test_period_register import (  # noqa: F401 — التجهيزاتُ نفسُها
    SUNDAY,
    _confirm,
    _periods,
    kids,
    klass,
    supervisor,
    teacher,
    year,
)

pytestmark = pytest.mark.django_db

MONDAY = SUNDAY + dt.timedelta(days=1)
THURSDAY = SUNDAY - dt.timedelta(days=3)
FRIDAY = SUNDAY - dt.timedelta(days=2)

LATE = {"status": "late", "late_minutes": 10}


def _parent_of(school, student, **link):
    user = UserFactory(full_name="وليّ أمر")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="parent"))
    ParentStudentLink.objects.create(parent=user, student=student, school=school, **link)
    return user


@pytest.fixture
def parent(school, kids):
    return _parent_of(school, kids[0])


@pytest.fixture(autouse=True)
def no_external_delivery():
    """لا مزوّدَ خارجيّاً في الاختبار."""
    with patch("notifications.tasks.hub_send_notification_task.delay") as mock:
        yield mock


def _day(school, klass, teacher, supervisor, marks, day=SUNDAY, count=3):
    """يومٌ من `count` حصص تُثبَّت بالترتيب، و`marks[i]` رصدُ الحصّة i."""
    sessions = _periods(school, klass, teacher, count, day=day)
    for session, period_marks in zip(sessions, marks, strict=False):
        _confirm(klass, session, period_marks, supervisor, day=day)
    return sessions


def _tardy_and_class_escape(school, klass, teacher, supervisor, kid, day=SUNDAY):
    """تأخّرٌ في الأولى، وهروبٌ من الثانية، وحضورٌ في الثالثة."""
    return _day(
        school, klass, teacher, supervisor, [{kid: LATE}, {kid: "absent"}, {kid: "present"}], day
    )


def _digests(user):
    return InAppNotification.objects.filter(user=user, title__contains="ملخّص سلوك")


def _behaviour_calls(spy):
    return [
        c for c in spy.call_args_list if str(c.kwargs.get("event_type", "")).startswith("behavior")
    ]


@contextmanager
def _spy_dispatch():
    with patch.object(NotificationHub, "dispatch", wraps=NotificationHub.dispatch) as spy:
        yield spy


# ══════════════════════════════════════════════════════════════════
#  الرصدُ نفسُه
# ══════════════════════════════════════════════════════════════════


class TestConfirmingAPeriod:
    def test_tardiness_and_class_escape_send_nothing_at_confirmation(
        self,
        school,
        klass,
        kids,
        teacher,
        supervisor,
        parent,
        django_capture_on_commit_callbacks,
    ):
        # إنذاراتُ عتبات الغياب قد تخرج من التثبيت — والمقصودُ هنا حدثُ السلوك وحدَه.
        with (
            _spy_dispatch() as spy,
            patch("notifications.tasks.notify_behavior_task.delay") as manual,
            django_capture_on_commit_callbacks(execute=True),
        ):
            _tardy_and_class_escape(school, klass, teacher, supervisor, kids[0])

        rules = set(BehaviorInfraction.objects.values_list("auto_rule", flat=True))
        assert rules == {"period_tardy", "class_escape"}
        assert _behaviour_calls(spy) == []
        manual.assert_not_called()
        assert not InAppNotification.objects.filter(user=parent, event_type="behavior").exists()
        assert not AutoInfractionNotice.objects.exists()

    def test_school_escape_reaches_the_parent_at_once_by_the_manual_path(
        self,
        school,
        klass,
        kids,
        teacher,
        supervisor,
        parent,
        django_capture_on_commit_callbacks,
    ):
        hidden = _parent_of(school, kids[0], can_view_behavior=False)
        with django_capture_on_commit_callbacks(execute=True):
            _day(
                school,
                klass,
                teacher,
                supervisor,
                [{kids[0]: "present"}, {kids[0]: "absent"}, {kids[0]: "absent"}],
            )

        escape = BehaviorInfraction.objects.get(auto_rule="school_escape")
        got = InAppNotification.objects.get(user=parent, event_type="behavior")
        assert got.related_object_id == str(escape.pk)
        assert got.related_url == reverse("parent_behavior")
        assert kids[0].full_name in got.title
        assert "2026/09/13" in got.body
        # حجبت المدرسةُ السلوكَ عنه — فلا يبلغه الرصدُ من باب الإشعار.
        assert not InAppNotification.objects.filter(user=hidden).exists()
        notice = AutoInfractionNotice.objects.get()
        assert (notice.kind, notice.auto_rule, notice.date) == (
            "immediate",
            "school_escape",
            SUNDAY,
        )

    def test_school_escape_is_queued_once_even_when_recreated(
        self,
        school,
        klass,
        kids,
        teacher,
        supervisor,
        parent,
        django_capture_on_commit_callbacks,
    ):
        kid = kids[0]
        with (
            patch("notifications.tasks.notify_behavior_task.delay") as manual,
            django_capture_on_commit_callbacks(execute=True),
        ):
            sessions = _day(
                school,
                klass,
                teacher,
                supervisor,
                [{kid: "present"}, {kid: "absent"}, {kid: "absent"}],
            )
            first = BehaviorInfraction.objects.get(auto_rule="school_escape")
            _confirm(klass, sessions[2], {kid: "absent"}, supervisor)  # تثبيتٌ ثانٍ
            _confirm(klass, sessions[2], {kid: "present"}, supervisor)  # عاد: هروبٌ من الحصّة
            assert not BehaviorInfraction.objects.filter(auto_rule="school_escape").exists()
            _confirm(klass, sessions[2], {kid: "absent"}, supervisor)  # بل لم يعد

        again = BehaviorInfraction.objects.get(auto_rule="school_escape")
        assert again.pk != first.pk
        assert manual.call_count == 1
        assert manual.call_args.kwargs["infraction_id"] == str(first.pk)
        assert manual.call_args.kwargs["school_id"] == str(school.id)

    def test_a_failed_publish_frees_the_marker_for_the_next_recreation(
        self,
        school,
        klass,
        kids,
        teacher,
        supervisor,
        parent,
        django_capture_on_commit_callbacks,
    ):
        kid = kids[0]
        with patch(
            "notifications.tasks.notify_behavior_task.delay", side_effect=OSError("الوسيط")
        ) as manual:
            with django_capture_on_commit_callbacks(execute=True):
                sessions = _day(
                    school,
                    klass,
                    teacher,
                    supervisor,
                    [{kid: "present"}, {kid: "absent"}, {kid: "absent"}],
                )
            assert manual.call_count == 1
            assert not AutoInfractionNotice.objects.exists()

            manual.side_effect = None
            with django_capture_on_commit_callbacks(execute=True):
                _confirm(klass, sessions[2], {kid: "present"}, supervisor)
                _confirm(klass, sessions[2], {kid: "absent"}, supervisor)

        assert manual.call_count == 2
        again = BehaviorInfraction.objects.get(auto_rule="school_escape")
        assert manual.call_args.kwargs["infraction_id"] == str(again.pk)
        assert AutoInfractionNotice.objects.get().kind == "immediate"


# ══════════════════════════════════════════════════════════════════
#  الملخّص
# ══════════════════════════════════════════════════════════════════


class TestTheDigest:
    def test_one_message_counts_the_days_automatic_infractions(
        self, school, klass, kids, teacher, supervisor, parent
    ):
        _tardy_and_class_escape(school, klass, teacher, supervisor, kids[0])

        assert send_day(school, SUNDAY, today=SUNDAY) == 1

        got = _digests(parent).get()
        assert got.title == f"ملخّص سلوك اليوم — {kids[0].full_name}"
        assert got.body == (
            "رُصدت لابنكم مخالفتان آليّتان في كشف الحصص يوم 13/9. التفاصيل في بوابة وليّ الأمر."
        )
        assert got.related_url == reverse("parent_behavior")
        assert (got.event_type, got.priority) == ("behavior", "medium")
        # لا مادّةَ ولا وقتَ ولا رقمَ حصّة — في أيّ قناة.
        assert "الحصّة" not in got.body and ":" not in got.body
        notices = AutoInfractionNotice.objects.all()
        assert {n.auto_rule for n in notices} == {"period_tardy", "class_escape"}
        assert {(n.kind, n.recipients) for n in notices} == {("digest", 1)}
        assert len({n.message_id for n in notices}) == 1

    @pytest.mark.parametrize(
        ("count", "phrase"),
        [
            (1, "مخالفةٌ آليّةٌ واحدة"),
            (2, "مخالفتان آليّتان"),
            (3, "3 مخالفاتٍ آليّة"),
            (10, "10 مخالفاتٍ آليّة"),
            (11, "11 مخالفةً آليّة"),
            (99, "99 مخالفةً آليّة"),
            (100, "100 مخالفةٍ آليّة"),
            (102, "102 مخالفةٍ آليّة"),
            (104, "104 مخالفاتٍ آليّة"),
            (111, "111 مخالفةً آليّة"),
        ],
    )
    def test_the_count_agrees_with_its_noun(self, count, phrase):
        assert count_phrase(count) == phrase

    def test_hand_written_infractions_and_school_escape_are_not_in_it(
        self, school, klass, kids, teacher, supervisor, parent
    ):
        kid = kids[0]
        sessions = _day(
            school, klass, teacher, supervisor, [{kid: "present"}, {kid: "absent"}, {kid: "absent"}]
        )
        BehaviorService.create_infraction(
            school=school,
            student=kid,
            reporter=supervisor,
            level=1,
            description="مخالفةٌ باليد",
            session=sessions[0],
        )
        assert BehaviorInfraction.objects.filter(auto_rule="school_escape").exists()

        assert send_day(school, SUNDAY, today=SUNDAY) == 0
        assert not _digests(parent).exists()
        assert not AutoInfractionNotice.objects.exclude(kind="immediate").exists()

    def test_a_day_without_automatic_infractions_sends_nothing(
        self, school, klass, kids, teacher, supervisor, parent
    ):
        _day(school, klass, teacher, supervisor, [{}, {}, {}])
        assert send_day(school, SUNDAY, today=SUNDAY) == 0
        assert not InAppNotification.objects.filter(user=parent).exists()
        assert not AutoInfractionNotice.objects.exists()

    def test_a_corrected_infraction_is_not_listed(
        self, school, klass, kids, teacher, supervisor, parent
    ):
        sessions = _day(school, klass, teacher, supervisor, [{kids[0]: LATE}, {}, {}])
        _confirm(klass, sessions[0], {kids[0]: "present"}, supervisor)

        assert send_day(school, SUNDAY, today=SUNDAY) == 0
        assert not _digests(parent).exists()
        assert not AutoInfractionNotice.objects.exists()

    def test_it_reads_the_session_day_not_the_writing_day(
        self, school, klass, kids, teacher, supervisor, parent
    ):
        # تصحيحُ يوم الخميس كُتب يومَ الأحد.
        _day(school, klass, teacher, supervisor, [{kids[0]: LATE}], day=THURSDAY)
        BehaviorInfraction.objects.update(date=SUNDAY)

        assert send_day(school, SUNDAY, today=SUNDAY) == 0
        assert send_day(school, THURSDAY, today=SUNDAY) == 1
        got = _digests(parent).get()
        assert got.title == f"ملخّص سلوك يوم 10/9 — {kids[0].full_name}"
        assert "يوم 10/9" in got.body

    def test_a_cancelled_session_is_left_out_without_failing(
        self, school, klass, kids, teacher, supervisor, parent
    ):
        sessions = _day(school, klass, teacher, supervisor, [{kids[0]: LATE}, {}, {}])
        Session.objects.filter(pk=sessions[0].pk).update(status="cancelled")

        assert send_day(school, SUNDAY, today=SUNDAY) == 0
        assert not AutoInfractionNotice.objects.exists()


# ══════════════════════════════════════════════════════════════════
#  لا تكرار — وما جدّ يُضاف
# ══════════════════════════════════════════════════════════════════


class TestOnceOnly:
    def test_running_twice_sends_once(self, school, klass, kids, teacher, supervisor, parent):
        _tardy_and_class_escape(school, klass, teacher, supervisor, kids[0])

        assert send_day(school, SUNDAY, today=SUNDAY) == 1
        assert send_day(school, SUNDAY, today=SUNDAY) == 0
        send_auto_infraction_digest(day=SUNDAY.isoformat())
        send_auto_infraction_digest(day=SUNDAY.isoformat())

        assert _digests(parent).count() == 1
        assert AutoInfractionNotice.objects.count() == 2

    def test_a_later_infraction_is_sent_alone_as_a_supplement(
        self, school, klass, kids, teacher, supervisor, parent
    ):
        sessions = _day(school, klass, teacher, supervisor, [{kids[0]: LATE}, {}, {}])
        assert send_day(school, SUNDAY, today=SUNDAY) == 1

        # بعد العصر: المشرفُ يصحّح الثالثة — تأخّرٌ جديد.
        _confirm(klass, sessions[2], {kids[0]: LATE}, supervisor)
        assert send_day(school, SUNDAY, today=MONDAY) == 1

        first, extra = _digests(parent).order_by("created_at")
        assert first.title.startswith("ملخّص سلوك اليوم")
        assert extra.title == f"إضافةٌ إلى ملخّص سلوك يوم 13/9 — {kids[0].full_name}"
        assert extra.body.startswith("رُصدت لابنكم مخالفةٌ آليّةٌ واحدة في كشف الحصص يوم 13/9.")
        supplement = AutoInfractionNotice.objects.get(kind="supplement")
        assert supplement.start_time == sessions[2].start_time
        assert str(supplement.message_id) == extra.related_object_id

        assert send_day(school, SUNDAY, today=MONDAY) == 0
        assert _digests(parent).count() == 2

    def test_a_deleted_and_recreated_infraction_is_not_sent_again(
        self, school, klass, kids, teacher, supervisor, parent
    ):
        sessions = _day(school, klass, teacher, supervisor, [{kids[0]: LATE}, {}, {}])
        first = BehaviorInfraction.objects.get()
        assert send_day(school, SUNDAY, today=SUNDAY) == 1

        _confirm(klass, sessions[0], {kids[0]: "present"}, supervisor)
        _confirm(klass, sessions[0], {kids[0]: LATE}, supervisor)
        assert BehaviorInfraction.objects.get().pk != first.pk

        assert send_day(school, SUNDAY, today=MONDAY) == 0
        assert _digests(parent).count() == 1

    def test_a_failed_dispatch_leaves_no_marker_and_the_next_run_sends(
        self, school, klass, kids, teacher, supervisor, parent
    ):
        _tardy_and_class_escape(school, klass, teacher, supervisor, kids[0])

        with patch.object(NotificationHub, "dispatch", side_effect=RuntimeError("مزوّدٌ ساقط")):
            assert send_day(school, SUNDAY, today=SUNDAY) == 0
        assert not AutoInfractionNotice.objects.exists()
        assert not _digests(parent).exists()

        assert send_day(school, SUNDAY, today=SUNDAY) == 1
        assert _digests(parent).count() == 1

    def test_a_failure_the_hub_swallows_still_rolls_the_marker_back(
        self, school, klass, kids, teacher, supervisor, parent
    ):
        # الـHub يحتوي فشلَ كلِّ مستلمٍ ويعود طبيعيّاً — فلا يكفي أن يُفحص الرفع.
        _tardy_and_class_escape(school, klass, teacher, supervisor, kids[0])

        with patch("notifications.hub._prepare_recipient", side_effect=RuntimeError("تفضيلات")):
            assert send_day(school, SUNDAY, today=SUNDAY) == 0
        assert not AutoInfractionNotice.objects.exists()
        assert not _digests(parent).exists()

        assert send_day(school, SUNDAY, today=SUNDAY) == 1
        assert _digests(parent).count() == 1

    def test_a_partial_failure_keeps_the_message_for_who_got_it(
        self, school, klass, kids, teacher, supervisor, parent
    ):
        other = _parent_of(school, kids[0])
        _tardy_and_class_escape(school, klass, teacher, supervisor, kids[0])

        from notifications import hub

        real = hub._prepare_recipient

        def failing_for_other(user, prepared, results):
            if user.pk == other.pk:
                raise ValueError("تفضيلات")
            return real(user, prepared, results)

        with patch.object(hub, "_prepare_recipient", side_effect=failing_for_other):
            assert send_day(school, SUNDAY, today=SUNDAY) == 1

        assert _digests(parent).count() == 1
        assert not _digests(other).exists()
        assert set(AutoInfractionNotice.objects.values_list("recipients", flat=True)) == {1}
        # إعادتُها للجميع تكرّرها على من استلم.
        assert send_day(school, SUNDAY, today=SUNDAY) == 0
        assert _digests(parent).count() == 1

    def test_a_concurrent_run_that_marked_first_wins(
        self, school, klass, kids, teacher, supervisor, parent
    ):
        """تشغيلان حسبا المعلَّقَ معاً — والقيدُ الفريدُ وحده يمنع الثاني."""
        sessions = _day(school, klass, teacher, supervisor, [{kids[0]: LATE}, {}, {}])

        from behavior import digest

        real = digest._parents_of

        def the_other_worker_commits_first(student, in_school):
            AutoInfractionNotice.objects.create(
                school=in_school,
                student=student,
                date=SUNDAY,
                auto_rule="period_tardy",
                start_time=sessions[0].start_time,
                kind="digest",
                recipients=1,
            )
            return real(student, in_school)

        with patch.object(digest, "_parents_of", side_effect=the_other_worker_commits_first):
            assert send_day(school, SUNDAY, today=SUNDAY) == 0

        assert not _digests(parent).exists()
        assert AutoInfractionNotice.objects.count() == 1


# ══════════════════════════════════════════════════════════════════
#  من يستلم
# ══════════════════════════════════════════════════════════════════


class TestRecipients:
    def test_only_parents_who_see_behaviour_and_kept_their_consent(
        self, school, klass, kids, teacher, supervisor, parent
    ):
        hidden = _parent_of(school, kids[0], can_view_behavior=False)
        withdrawn = _parent_of(school, kids[0])
        ConsentRecord.objects.create(
            school=school, parent=withdrawn, student=kids[0], data_type="behavior", is_given=False
        )
        _tardy_and_class_escape(school, klass, teacher, supervisor, kids[0])

        assert send_day(school, SUNDAY, today=SUNDAY) == 1

        assert _digests(parent).count() == 1
        assert not InAppNotification.objects.filter(user__in=[hidden, withdrawn]).exists()
        assert set(AutoInfractionNotice.objects.values_list("recipients", flat=True)) == {1}

    def test_nobody_to_tell_leaves_the_day_open_for_a_parent_linked_later(
        self, school, klass, kids, teacher, supervisor
    ):
        _tardy_and_class_escape(school, klass, teacher, supervisor, kids[0])

        assert send_day(school, SUNDAY, today=SUNDAY) == 0
        assert not AutoInfractionNotice.objects.exists()
        assert not InAppNotification.objects.filter(title__contains="ملخّص سلوك").exists()

        # رُبط غداً — فيستلم ملخّصَ اليوم كاملاً، لا «إضافةً» إلى ما لم يره.
        late_parent = _parent_of(school, kids[0])
        assert send_day(school, SUNDAY, today=MONDAY) == 1
        got = _digests(late_parent).get()
        assert got.title == f"ملخّص سلوك يوم 13/9 — {kids[0].full_name}"
        assert got.body.startswith("رُصدت لابنكم مخالفتان آليّتان")

    def test_the_parent_portal_lists_automatic_infractions_on_their_day(
        self, client, school, klass, kids, teacher, supervisor, parent
    ):
        from django.utils import timezone

        parent.consent_given_at = timezone.now()
        parent.save(update_fields=["consent_given_at"])
        _day(school, klass, teacher, supervisor, [{kids[0]: LATE}], day=THURSDAY)
        BehaviorInfraction.objects.update(date=SUNDAY)

        client.force_login(parent)
        response = client.get(reverse("parent_behavior"))

        assert response.status_code == 200
        row = response.context["children_behavior"][0]
        assert [i.auto_rule for i in row["infractions"]] == ["period_tardy"]
        assert "10/09" in response.content.decode()

    def test_the_portal_orders_by_session_day_and_shows_the_recent_days_in_full(
        self, client, school, klass, kids, teacher, supervisor, parent
    ):
        from django.utils import timezone

        parent.consent_given_at = timezone.now()
        parent.save(update_fields=["consent_given_at"])
        wednesday = THURSDAY - dt.timedelta(days=1)
        # اثنتا عشرة مخالفة في ثلاثة أيّام، والخميسُ والأربعاءُ كُتبا يومَ الأحد.
        four_late = [{kids[0]: LATE}] * 4
        for day in (wednesday, THURSDAY):
            _day(school, klass, teacher, supervisor, four_late, day=day, count=4)
        BehaviorInfraction.objects.update(date=SUNDAY)
        _day(school, klass, teacher, supervisor, four_late, day=SUNDAY, count=4)
        assert BehaviorInfraction.objects.count() == 12

        client.force_login(parent)
        with patch.object(timezone, "localdate", return_value=MONDAY):
            response = client.get(reverse("parent_behavior"))

        rows = response.context["children_behavior"][0]["infractions"]
        assert len(rows) == 12
        days = [inf.shown_day for inf in rows]
        assert days == [SUNDAY] * 4 + [THURSDAY] * 4 + [wednesday] * 4
        starts = [inf.session.start_time for inf in rows[:4]]
        assert starts == sorted(starts, reverse=True)


# ══════════════════════════════════════════════════════════════════
#  المهمّة المجدولة
# ══════════════════════════════════════════════════════════════════


def _tardy_in_another_school():
    """مدرسةٌ ثانيةٌ بطالبٍ متأخّرٍ يومَ الأحد، ووليِّ أمره."""
    other = SchoolFactory()
    group = ClassGroupFactory(school=other)
    student = UserFactory(full_name="طالب المدرسة الأخرى")
    StudentEnrollmentFactory(student=student, class_group=group)
    session = Session.objects.create(
        school=other,
        class_group=group,
        teacher=UserFactory(full_name="معلّم المدرسة الأخرى"),
        date=SUNDAY,
        start_time=dt.time(7, 10),
        end_time=dt.time(7, 55),
        status="scheduled",
    )
    BehaviorService.create_infraction(
        school=other,
        student=student,
        reporter=UserFactory(),
        level=1,
        description="تأخّر",
        session=session,
        auto_rule="period_tardy",
    )
    return other, _parent_of(other, student)


class TestTheScheduledTask:
    def test_schools_are_isolated_and_one_failure_blocks_nobody(
        self, school, klass, kids, teacher, supervisor, parent
    ):
        second_parent = _parent_of(school, kids[1])
        _day(school, klass, teacher, supervisor, [{kids[0]: LATE, kids[1]: LATE}])
        other, other_parent = _tardy_in_another_school()

        from behavior import digest

        real = digest._parents_of

        def failing_for_the_first_kid(student, in_school):
            if student.pk == kids[0].pk:
                raise RuntimeError("سجلٌّ تالف")
            return real(student, in_school)

        with patch.object(digest, "_parents_of", side_effect=failing_for_the_first_kid):
            result = send_auto_infraction_digest(day=SUNDAY.isoformat())

        assert result == {"sent": 2, "failed_schools": 0}
        assert not _digests(parent).exists()
        assert _digests(second_parent).get().title.endswith(kids[1].full_name)
        mine = _digests(other_parent).get()
        assert mine.school_id == other.id
        assert InAppNotification.objects.filter(title__contains="ملخّص سلوك").count() == 2

        # الأوّلُ يُرسَل في التشغيل التالي — علامتُه تراجعت مع فشله.
        assert send_auto_infraction_digest(day=SUNDAY.isoformat()) == {
            "sent": 1,
            "failed_schools": 0,
        }
        assert _digests(parent).count() == 1

    def test_a_school_whose_scope_fails_does_not_stop_the_others(
        self, school, klass, kids, teacher, supervisor, parent
    ):
        _day(school, klass, teacher, supervisor, [{kids[0]: LATE}])
        other, other_parent = _tardy_in_another_school()

        from core import celery_tasks

        real = celery_tasks.school_rls_scope

        def refuse_the_first(school_id):
            if str(school_id) == str(school.id):
                raise ValueError("Celery tenant mismatch")
            return real(school_id)

        with patch.object(celery_tasks, "school_rls_scope", side_effect=refuse_the_first):
            result = send_auto_infraction_digest(day=SUNDAY.isoformat())

        assert result == {"sent": 1, "failed_schools": 1}
        assert not _digests(parent).exists()
        assert _digests(other_parent).count() == 1

    def test_friday_is_not_a_school_day(self, school, klass, kids, teacher, supervisor, parent):
        _day(school, klass, teacher, supervisor, [{kids[0]: LATE}], day=FRIDAY)

        assert FRIDAY not in school_days_back(FRIDAY)
        assert send_auto_infraction_digest(day=FRIDAY.isoformat()) == {
            "sent": 0,
            "failed_schools": 0,
        }
        assert not AutoInfractionNotice.objects.exists()

    def test_the_sweep_catches_a_past_day_and_names_it(
        self, school, klass, kids, teacher, supervisor, parent
    ):
        _day(school, klass, teacher, supervisor, [{kids[0]: LATE}], day=THURSDAY)

        assert school_days_back(SUNDAY) == [
            dt.date(2026, 9, 7),
            dt.date(2026, 9, 8),
            dt.date(2026, 9, 9),
            THURSDAY,
            SUNDAY,
        ]
        send_auto_infraction_digest(day=SUNDAY.isoformat())

        assert _digests(parent).get().title == f"ملخّص سلوك يوم 10/9 — {kids[0].full_name}"

    def test_what_the_register_wrote_before_launch_is_never_sent(
        self, school, klass, kids, teacher, supervisor, parent
    ):
        """الهجرةُ 0018 خطُّ الإطلاق — أوّلُ تشغيلٍ لا يحمل أسبوعاً مضى."""
        import importlib

        from django.apps import apps

        kid, runner = kids[0], kids[1]
        _day(school, klass, teacher, supervisor, [{kid: LATE}], day=THURSDAY)
        # الأحد: تأخّرٌ وهروبٌ من حصّة للأوّل، وهروبٌ من المدرسة للثاني.
        sessions = _day(
            school,
            klass,
            teacher,
            supervisor,
            [
                {kid: LATE, runner: "present"},
                {kid: "absent", runner: "absent"},
                {kid: "present", runner: "absent"},
            ],
        )
        # السابقُ للإطلاق لم يمرّ بالإبلاغ الفوريّ — علامتُه تأتي من الهجرة وحدها.
        AutoInfractionNotice.objects.all().delete()

        baseline = importlib.import_module("behavior.migrations.0018_auto_notice_baseline")
        baseline.mark_existing(apps, None)
        baseline.mark_existing(apps, None)  # يُعاد بلا أثر

        assert set(AutoInfractionNotice.objects.values_list("kind", "recipients")) == {
            ("baseline", None)
        }
        assert AutoInfractionNotice.objects.count() == 4
        assert send_auto_infraction_digest(day=SUNDAY.isoformat()) == {
            "sent": 0,
            "failed_schools": 0,
        }
        assert not InAppNotification.objects.filter(title__contains="ملخّص سلوك").exists()

        # وما جدّ بعد الإطلاق عن يومٍ سبقه يُرسَل ملخّصاً — لا «إضافةً» إلى ما لم يُرسَل.
        _confirm(klass, sessions[2], {kid: LATE, runner: "absent"}, supervisor)
        assert send_auto_infraction_digest(day=MONDAY.isoformat())["sent"] == 1
        got = _digests(parent).get()
        assert got.title == f"ملخّص سلوك يوم 13/9 — {kid.full_name}"
        assert got.body.startswith("رُصدت لابنكم مخالفةٌ آليّةٌ واحدة")

    def test_the_backfill_command_refuses_a_malformed_school(self):
        from django.core.management import CommandError, call_command

        with pytest.raises(CommandError):
            call_command("send_behavior_digest", "--school", "abc")

    def test_it_is_scheduled_at_three_on_school_days(self):
        from shschool.celery import app

        app.loader.import_default_modules()
        entries = [
            e
            for e in app.conf.beat_schedule.values()
            if e["task"] == "behavior.send_auto_infraction_digest"
        ]
        assert len(entries) == 1
        when = entries[0]["schedule"]
        assert when.hour == {15}
        assert when.minute == {0}
        assert when.day_of_week == {0, 1, 2, 3, 4}
        assert "behavior.send_auto_infraction_digest" in app.tasks

    def test_the_hub_knows_the_event(self):
        assert DEFAULT_CHANNELS["behavior_digest"] == ["in_app", "push", "whatsapp", "email"]
        assert "sms" not in DEFAULT_CHANNELS["behavior_digest"]
        assert DEFAULT_PRIORITY["behavior_digest"] == "medium"
        assert _CONSENT_DATA_TYPE["behavior_digest"] == "behavior"
        assert _map_event_type("behavior_digest") == "behavior"

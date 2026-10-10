"""[W-20261010-014] تنبيهٌ آليٌّ لمُهَل الخرق: إشعار NCSA، وإخطار الأفراد (م.14)، واستكمال الإشعار المبدئي.

العتباتُ من إعدادٍ مركزيّ (`BREACH_ALERT_THRESHOLDS`): قبل الموعد بـ`pre_hours`، وعند الموعد، ثم يوماً بيوم.
لكلّ (خرق، مرحلة، عتبة) تنبيهٌ واحدٌ لكلّ مستلم، فإعادةُ تشغيل المهمّة لا تكرّر. كلُّ البياناتِ اصطناعيّة.
"""

from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from core.models import AuditLog, BreachReport, School
from notifications import tasks
from notifications.models import InAppNotification
from notifications.tasks import breach_alert_events, check_breach_deadlines_task
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

SECRET_TITLE = "خرقٌ يذكر الطالب فلان بن فلان"
HOUR = timedelta(hours=1)


@pytest.fixture
def school(db):
    return School.objects.create(name="مدرسة التنبيهات", code="SHH-BSA")


def _member(school, role_name, **fields):
    user = UserFactory(**fields)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role_name))
    return user


@pytest.fixture
def people(school):
    return {
        "assignee": _member(school, "teacher"),
        "dpo": _member(school, "platform_developer"),
        "principal": _member(school, "principal"),
        "reporter": _member(school, "teacher"),
        "bystander": _member(school, "teacher"),
    }


def _breach(school, people, **fields):
    """خرقٌ مفتوحٌ لا مرحلةَ مفتوحةً فيه؛ يُهيَّأ للاختبار بما يلزم."""
    defaults = {
        "school": school,
        "title": SECRET_TITLE,
        "description": "وصف",
        "discovered_at": timezone.now() - 100 * HOUR,
        # بعيدٌ في المستقبل: لا تنبيهَ NCSA إلا في الاختبارات التي تطلبه
        "ncsa_deadline": timezone.now() + 500 * HOUR,
        "reported_by": people["reporter"],
        "assigned_to": people["assignee"],
        "affected_count": 7,
    }
    defaults.update(fields)
    return BreachReport.objects.create(**defaults)


def _individuals(school, people, offset, **extra):
    """خرقٌ إخطارُ أفراده واجبٌ بموعدٍ بعد `offset` من الآن (سالبٌ = فات)."""
    return _breach(
        school,
        people,
        individuals_status="required",
        individuals_deadline=timezone.now() + offset,
        **extra,
    )


def _notes(breach, stage=None, threshold=None):
    qs = InAppNotification.objects.filter(related_url=f"/breach/{breach.pk}/")
    if stage:
        qs = qs.filter(related_object_id=f"{breach.pk}:{stage}:{threshold}")
    return qs


def _recipients(breach, **kw):
    return set(_notes(breach, **kw).values_list("user_id", flat=True))


class TestThresholds:
    @pytest.mark.parametrize(
        ("offset_hours", "expected"),
        [
            (30, None),
            (24.5, None),
            (20, "pre"),
            (1, "pre"),
            (-1, "due"),
            (-23, "due"),
            (-25, "day_1"),
            (-50, "day_2"),
        ],
    )
    def test_individuals_pre_due_then_daily(self, school, people, offset_hours, expected):
        breach = _individuals(school, people, timedelta(hours=offset_hours))
        events = breach_alert_events(breach, timezone.now())
        if expected is None:
            assert events == []
        else:
            assert [(e["stage"], e["threshold"]) for e in events] == [("individuals", expected)]
            assert events[0]["overdue"] is (expected != "pre")

    @pytest.mark.parametrize(("offset_hours", "expected"), [(13, None), (11, "pre"), (-1, "due")])
    def test_ncsa_pre_window_is_twelve_hours(self, school, people, offset_hours, expected):
        breach = _breach(
            school, people, ncsa_deadline=timezone.now() + timedelta(hours=offset_hours)
        )
        got = [e["threshold"] for e in breach_alert_events(breach, timezone.now())]
        assert got == ([expected] if expected else [])

    @pytest.mark.parametrize(("offset_hours", "expected"), [(30, None), (20, "pre"), (-2, "due")])
    def test_completion_of_an_initial_notice(self, school, people, offset_hours, expected):
        breach = _breach(
            school,
            people,
            ncsa_notice_stage="initial",
            ncsa_notified_at=timezone.now() - 10 * HOUR,
            status="notified",
            ncsa_completion_due_at=timezone.now() + timedelta(hours=offset_hours),
        )
        events = breach_alert_events(breach, timezone.now())
        assert [(e["stage"], e["threshold"]) for e in events] == (
            [("completion", expected)] if expected else []
        )

    def test_thresholds_come_from_the_central_setting_not_a_literal(
        self, school, people, monkeypatch
    ):
        breach = _individuals(school, people, 20 * HOUR)
        assert [e["threshold"] for e in breach_alert_events(breach, timezone.now())] == ["pre"]
        monkeypatch.setitem(tasks.BREACH_ALERT_THRESHOLDS, "individuals", {"pre_hours": 2})
        assert breach_alert_events(breach, timezone.now()) == []

    def test_several_stages_alert_together_one_event_each(self, school, people):
        breach = _breach(
            school,
            people,
            ncsa_deadline=timezone.now() - 2 * HOUR,
            individuals_status="required",
            individuals_deadline=timezone.now() + 5 * HOUR,
        )
        assert sorted(e["stage"] for e in breach_alert_events(breach, timezone.now())) == [
            "individuals",
            "ncsa",
        ]


class TestStopsWhenDone:
    @pytest.mark.parametrize(
        "changes",
        [
            {"individuals_status": "notified"},
            {"individuals_status": "not_required"},
            {"individuals_status": "not_assessed"},
            {"status": "resolved"},
        ],
        ids=["notified", "not_required", "not_assessed", "closed"],
    )
    def test_individuals_alert_stops(self, school, people, changes):
        breach = _individuals(school, people, -3 * HOUR)
        assert len(breach_alert_events(breach, timezone.now())) == 1
        BreachReport.objects.filter(pk=breach.pk).update(**changes)
        breach.refresh_from_db()
        assert breach_alert_events(breach, timezone.now()) == []

    @pytest.mark.parametrize(
        "changes",
        [{"ncsa_notice_stage": "complete"}, {"status": "resolved"}],
        ids=["completed", "closed"],
    )
    def test_completion_alert_stops(self, school, people, changes):
        breach = _breach(
            school,
            people,
            ncsa_notice_stage="initial",
            ncsa_notified_at=timezone.now() - 10 * HOUR,
            status="notified",
            ncsa_completion_due_at=timezone.now() - 2 * HOUR,
        )
        assert len(breach_alert_events(breach, timezone.now())) == 1
        BreachReport.objects.filter(pk=breach.pk).update(**changes)
        breach.refresh_from_db()
        assert breach_alert_events(breach, timezone.now()) == []

    @pytest.mark.parametrize(
        "changes",
        [
            {"ncsa_notified_at": timezone.now(), "status": "notified"},
            {"ncsa_notice_stage": "initial", "ncsa_notified_at": timezone.now()},
            {"status": "resolved"},
        ],
        ids=["notified", "initial_notice_sent", "closed"],
    )
    def test_ncsa_alert_stops(self, school, people, changes):
        breach = _breach(school, people, ncsa_deadline=timezone.now() - 2 * HOUR)
        assert [e["stage"] for e in breach_alert_events(breach, timezone.now())] == ["ncsa"]
        BreachReport.objects.filter(pk=breach.pk).update(**changes)
        breach.refresh_from_db()
        assert "ncsa" not in [e["stage"] for e in breach_alert_events(breach, timezone.now())]


class TestTaskDelivery:
    def test_before_the_deadline_the_assignee_and_dpo_only(self, school, people):
        breach = _individuals(school, people, 10 * HOUR)

        result = check_breach_deadlines_task()

        assert result["by_stage"] == {"individuals": 1} and result["warnings"] >= 1
        assert _recipients(breach, stage="individuals", threshold="pre") == {
            people["assignee"].pk,
            people["dpo"].pk,
        }

    def test_after_the_deadline_the_principal_joins_and_the_reporter_never(self, school, people):
        breach = _individuals(school, people, -2 * HOUR)

        check_breach_deadlines_task()

        got = _recipients(breach, stage="individuals", threshold="due")
        assert got == {people["assignee"].pk, people["dpo"].pk, people["principal"].pk}
        assert people["reporter"].pk not in got and people["bystander"].pk not in got

    def test_with_no_assignee_nor_dpo_the_principal_is_alerted_even_early(self, school, people):
        people["dpo"].memberships.all().delete()
        breach = _individuals(school, people, 10 * HOUR, assigned_to=None)

        check_breach_deadlines_task()

        assert _recipients(breach) == {people["principal"].pk}

    def test_ncsa_recipients_are_unchanged(self, school, people):
        breach = _breach(school, people, ncsa_deadline=timezone.now() + 5 * HOUR)

        check_breach_deadlines_task()

        assert _recipients(breach, stage="ncsa", threshold="pre") == {
            people["assignee"].pk,
            people["dpo"].pk,
            people["principal"].pk,
            people["reporter"].pk,
        }

    def test_a_rerun_does_not_repeat(self, school, people):
        breach = _individuals(school, people, -2 * HOUR)
        check_breach_deadlines_task()
        first = _notes(breach).count()

        again = check_breach_deadlines_task()

        assert first == 3 and _notes(breach).count() == first
        assert again["by_stage"] == {"individuals": 1}  # يُحسب الحدثُ ولا يُكرَّر الإشعار

    def test_the_next_day_brings_a_new_threshold(self, school, people):
        breach = _individuals(school, people, -2 * HOUR)
        check_breach_deadlines_task()
        BreachReport.objects.filter(pk=breach.pk).update(
            individuals_deadline=timezone.now() - 27 * HOUR
        )

        check_breach_deadlines_task()

        assert _recipients(breach, stage="individuals", threshold="due")
        assert _recipients(breach, stage="individuals", threshold="day_1")
        assert _notes(breach).count() == 6
        assert "متأخّر منذ 1 يوم" in _notes(breach, stage="individuals", threshold="day_1")[0].body

    def test_each_stage_has_its_own_title(self, school, people):
        breach = _breach(
            school,
            people,
            ncsa_notice_stage="initial",
            ncsa_notified_at=timezone.now() - 10 * HOUR,
            status="notified",
            ncsa_completion_due_at=timezone.now() - 2 * HOUR,
            individuals_status="required",
            individuals_deadline=timezone.now() - 2 * HOUR,
        )

        check_breach_deadlines_task()

        titles = {n.title for n in _notes(breach)}
        assert any("إخطار الأفراد" in t for t in titles)
        assert any("استكمال إشعار" in t for t in titles)

    def test_text_has_no_personal_data_nor_breach_title(self, school, people):
        breach = _individuals(school, people, -2 * HOUR)

        check_breach_deadlines_task()

        for note in _notes(breach):
            assert "فلان" not in note.title + note.body
            assert note.priority == "urgent"
            assert note.related_url == f"/breach/{breach.pk}/"

    def test_the_task_neither_changes_the_breach_nor_writes_audit_rows(self, school, people):
        breach = _individuals(school, people, -2 * HOUR)
        before = BreachReport.objects.values().get(pk=breach.pk)
        audit_before = AuditLog.objects.filter(model_name="BreachReport").count()

        check_breach_deadlines_task()

        assert BreachReport.objects.values().get(pk=breach.pk) == before
        assert AuditLog.objects.filter(model_name="BreachReport").count() == audit_before

    def test_closed_and_finished_breaches_are_silent(self, school, people):
        closed = _individuals(school, people, -2 * HOUR, status="resolved")
        done = _individuals(school, people, -2 * HOUR)
        BreachReport.objects.filter(pk=done.pk).update(individuals_status="notified")

        result = check_breach_deadlines_task()

        assert result["by_stage"] == {}
        assert not _notes(closed).exists() and not _notes(done).exists()

    def test_query_count_stays_bounded_for_several_breaches(self, school, people):
        for _ in range(4):
            _individuals(school, people, -2 * HOUR)

        with CaptureQueriesContext(connection) as ctx:
            check_breach_deadlines_task()

        assert len(ctx) <= 120, len(ctx)

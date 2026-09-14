"""الاحتفاظُ بالبيانات — ما يُحذف يُحذف، وما يُحفظ لا يُلمَس، والوثيقةُ تحكم كلَّ جدول.

`docs/privacy/data_retention.md` هي السياسة، و`core/retention.py` يُنفِّذ شطرَ
«يُحذف» منها. وهذا الملفُّ يربطهما:

- لكلّ صنفٍ محذوف: القديمُ يذهب والحديثُ يبقى — وما ينتهي بذاته يذهب عند أجله.
- الأصنافُ المحفوظة لا تُمسّ ولو قدُمت.
- **كلُّ جدولٍ في القاعدة له حكمٌ في الوثيقة** — وجدولٌ جديدٌ بلا حكمٍ يُسقط البناء.
- الصفرُ يعطّل، والعرضُ لا يحذف، والتنفيذُ يترك سطراً في التدقيق بالأعداد لا الأسماء،
  والتشغيلُ الثاني لا يجد ما يحذفه.
"""

from __future__ import annotations

import json
import pathlib
import re
from datetime import timedelta

import pytest
from django.apps import apps
from django.contrib.sessions.models import Session
from django.core.management import CommandError, call_command
from django.utils import timezone

from core.models import AuditLog
from core.retention import RULES, enforce_retention
from tests.conftest import UserFactory

pytestmark = pytest.mark.django_db

DOC = pathlib.Path("docs/privacy/data_retention.md")
DAYS = 30
NOW = timezone.now()
OLD = NOW - timedelta(days=DAYS + 1)
FRESH = NOW - timedelta(days=1)

RULE_KEYS = {rule.key for rule in RULES}


@pytest.fixture
def retention(settings):
    settings.PDPPL_DATA_RETENTION_DAYS = DAYS
    return DAYS


def _backdate(obj, when, field="created_at"):
    """`auto_now_add` لا يقبل قيمةً عند الإنشاء — فيُكتب التاريخُ بعده."""
    type(obj)._default_manager.filter(pk=obj.pk).update(**{field: when})
    return obj


def _run(**kwargs):
    return enforce_retention(now=NOW, **kwargs)


# ══════════════════════════════════════════════════════════════════════
#  ما ينتهي بذاته
# ══════════════════════════════════════════════════════════════════════


class TestExpiresOnItsOwn:
    def test_expired_sessions_go_and_live_ones_stay(self, retention):
        Session.objects.create(
            session_key="e" * 32, session_data="x", expire_date=NOW - timedelta(hours=1)
        )
        Session.objects.create(
            session_key="l" * 32, session_data="x", expire_date=NOW + timedelta(hours=1)
        )

        report = _run()

        assert report.counts["sessions.expired"] == 1
        assert set(Session.objects.values_list("session_key", flat=True)) == {"l" * 32}

    def test_expired_jwt_tokens_go_with_their_blacklist_entry(self, retention):
        from rest_framework_simplejwt.token_blacklist.models import (
            BlacklistedToken,
            OutstandingToken,
        )

        dead = OutstandingToken.objects.create(
            jti="dead", token="t", expires_at=NOW - timedelta(hours=1)
        )
        BlacklistedToken.objects.create(token=dead)
        OutstandingToken.objects.create(jti="live", token="t", expires_at=NOW + timedelta(days=1))

        report = _run()

        assert report.counts["jwt.expired"] == 1
        assert list(OutstandingToken.objects.values_list("jti", flat=True)) == ["live"]
        assert not BlacklistedToken.objects.exists()


# ══════════════════════════════════════════════════════════════════════
#  يُحذف بعد N يوماً
# ══════════════════════════════════════════════════════════════════════


def _axes_row(model, when, **extra):
    # (username, ip, user_agent) مفتاحٌ فريدٌ في axes — فوكيلُ المستخدم يميّز الصفوف.
    row = model.objects.create(
        username="9990000001",
        ip_address="10.0.0.9",
        user_agent=f"probe-{when:%Y%m%d}",
        http_accept="*/*",
        path_info="/login/",
        **extra,
    )
    return _backdate(row, when, "attempt_time")


class TestAxes:
    def test_old_attempts_logs_and_failures_go(self, retention):
        from axes.models import AccessAttempt, AccessFailureLog, AccessLog

        _axes_row(AccessAttempt, OLD, failures_since_start=3, get_data="", post_data="")
        _axes_row(AccessAttempt, FRESH, failures_since_start=1, get_data="", post_data="")
        _axes_row(AccessLog, OLD)
        _axes_row(AccessLog, FRESH)
        _axes_row(AccessFailureLog, OLD, locked_out=True)
        _axes_row(AccessFailureLog, FRESH, locked_out=False)

        report = _run()

        assert report.counts["axes.attempts"] == 1
        assert report.counts["axes.access_log"] == 1
        assert report.counts["axes.failure_log"] == 1
        assert AccessAttempt.objects.get().failures_since_start == 1
        assert AccessLog.objects.count() == 1
        assert AccessFailureLog.objects.get().locked_out is False


@pytest.fixture
def pipeline(school):
    """واقعةٌ بتسليمٍ نهائيٍّ وسجلٍّ ونيّةٍ — كلُّها قديمة — وتُعاد أدواتُ بنائها."""
    from notifications.models import (
        NotificationDelivery,
        NotificationDispatch,
        NotificationEnqueueIntent,
        NotificationLog,
    )

    recipient = UserFactory()

    def build(*, dispatch_at=OLD, status="sent", log_at=OLD, intent=True):
        dispatch = _backdate(
            NotificationDispatch.objects.create(school=school, event_type="probe"), dispatch_at
        )
        delivery = _backdate(
            NotificationDelivery.objects.create(
                dispatch=dispatch,
                school=school,
                recipient=recipient,
                channel="email",
                status=status,
            ),
            dispatch_at,
        )
        log = None
        if log_at is not None:
            log = _backdate(
                NotificationLog.objects.create(
                    school=school,
                    delivery=delivery,
                    recipient="someone@example.test",
                    channel="email",
                    body="نصٌّ يحمل اسمَ طالب",
                    status="sent",
                ),
                log_at,
                "sent_at",
            )
        intent_row = None
        if intent:
            intent_row = _backdate(
                NotificationEnqueueIntent.objects.create(
                    school=school,
                    dispatch=dispatch,
                    recipient=recipient,
                    title="عنوان",
                    body="نصّ",
                ),
                dispatch_at,
            )
        return dispatch, delivery, log, intent_row

    return build


class TestNotificationPipeline:
    def test_a_finished_old_chain_is_removed_children_first(self, retention, pipeline):
        from notifications.models import (
            NotificationDelivery,
            NotificationDispatch,
            NotificationEnqueueIntent,
            NotificationLog,
        )

        pipeline()

        report = _run()

        assert report.counts["notifications.logs"] == 1
        assert report.counts["notifications.intents"] == 1
        assert report.counts["notifications.deliveries"] == 1
        assert report.counts["notifications.dispatches"] == 1
        for model in (
            NotificationLog,
            NotificationEnqueueIntent,
            NotificationDelivery,
            NotificationDispatch,
        ):
            assert not model.objects.exists(), model.__name__

    def test_an_open_delivery_keeps_its_whole_chain(self, retention, pipeline):
        from notifications.models import (
            NotificationDelivery,
            NotificationDispatch,
            NotificationEnqueueIntent,
        )

        pipeline(status="pending", log_at=None)

        report = _run()

        assert report.counts["notifications.deliveries"] == 0
        assert report.counts["notifications.intents"] == 0
        assert report.counts["notifications.dispatches"] == 0
        assert NotificationDelivery.objects.count() == 1
        assert NotificationEnqueueIntent.objects.count() == 1
        assert NotificationDispatch.objects.count() == 1

    def test_a_fresh_attempt_log_protects_its_old_delivery(self, retention, pipeline):
        from notifications.models import (
            NotificationDelivery,
            NotificationDispatch,
            NotificationLog,
        )

        pipeline(log_at=FRESH, intent=False)

        report = _run()

        assert report.counts["notifications.logs"] == 0
        assert report.counts["notifications.deliveries"] == 0
        assert report.counts["notifications.dispatches"] == 0
        assert NotificationLog.objects.count() == 1
        assert NotificationDelivery.objects.count() == 1
        assert NotificationDispatch.objects.count() == 1

    def test_only_resolved_dead_letters_go(self, retention, school):
        from notifications.models import DeadLetterMessage

        _backdate(DeadLetterMessage.objects.create(school=school, kind="email", resolved=True), OLD)
        _backdate(
            DeadLetterMessage.objects.create(school=school, kind="email", resolved=False), OLD
        )
        _backdate(
            DeadLetterMessage.objects.create(school=school, kind="email", resolved=True), FRESH
        )

        report = _run()

        assert report.counts["notifications.dead_letters"] == 1
        remaining = set(DeadLetterMessage.objects.values_list("resolved", flat=True))
        assert DeadLetterMessage.objects.count() == 2
        assert remaining == {True, False}


class TestBellAndPush:
    def test_old_in_app_notifications_go_read_or_not(self, retention, school):
        from notifications.models import InAppNotification

        user = UserFactory()
        _backdate(
            InAppNotification.objects.create(user=user, school=school, title="قديم", is_read=False),
            OLD,
        )
        _backdate(
            InAppNotification.objects.create(user=user, school=school, title="حديث", is_read=True),
            FRESH,
        )

        report = _run()

        assert report.counts["notifications.in_app"] == 1
        assert InAppNotification.objects.get().title == "حديث"

    def test_only_dead_and_unused_push_subscriptions_go(self, retention, school):
        from notifications.models import PushSubscription

        user = UserFactory()

        def sub(endpoint, *, active, created, last_used=None):
            row = PushSubscription.objects.create(
                user=user,
                school=school,
                endpoint=endpoint,
                p256dh="k",
                is_active=active,
                last_used=last_used,
            )
            return _backdate(row, created)

        sub("https://push.test/dead-old", active=False, created=OLD)
        sub("https://push.test/dead-recent", active=False, created=OLD, last_used=FRESH)
        sub("https://push.test/alive-old", active=True, created=OLD)

        report = _run()

        assert report.counts["notifications.push_subscriptions"] == 1
        assert set(PushSubscription.objects.values_list("endpoint", flat=True)) == {
            "https://push.test/dead-recent",
            "https://push.test/alive-old",
        }


class TestImportLogs:
    def test_old_import_logs_go(self, retention, school):
        from staging.models import ImportLog

        _backdate(ImportLog.objects.create(school=school, file_name="قديم.xlsx"), OLD, "started_at")
        _backdate(
            ImportLog.objects.create(school=school, file_name="حديث.xlsx"), FRESH, "started_at"
        )

        report = _run()

        assert report.counts["staging.import_logs"] == 1
        assert ImportLog.objects.get().file_name == "حديث.xlsx"


# ══════════════════════════════════════════════════════════════════════
#  ما يُحفظ
# ══════════════════════════════════════════════════════════════════════


class TestRetainedRecordsAreNeverTouched:
    def test_student_staff_and_audit_records_survive_however_old(
        self,
        retention,
        school,
        behavior_infraction,
        health_record,
        clinic_visit,
        book_borrowing,
        principal_user,
    ):
        from behavior.models import BehaviorInfraction
        from clinic.models import ClinicVisit, HealthRecord
        from core.models import ConsentRecord, CustomUser, Membership, PermissionAuditLog
        from library.models import BookBorrowing

        _backdate(behavior_infraction, OLD)
        _backdate(clinic_visit, OLD, "visit_date")
        PermissionAuditLog.objects.create(
            school=school, actor=principal_user, target=principal_user, action="role_assigned"
        )
        ConsentRecord.objects.create(
            school=school, parent=principal_user, student=clinic_visit.student, data_type="all"
        )
        AuditLog.objects.create(user=principal_user, action="view", model_name="HealthRecord")
        before = {
            model: model.objects.count()
            for model in (
                BehaviorInfraction,
                HealthRecord,
                ClinicVisit,
                BookBorrowing,
                CustomUser,
                Membership,
                PermissionAuditLog,
                ConsentRecord,
            )
        }
        audit_before = AuditLog.objects.count()

        _run()

        for model, count in before.items():
            assert model.objects.count() == count, model.__name__
        # سطرُ الملخّص وحدَه زاد — ولم ينقص شيء.
        assert AuditLog.objects.count() == audit_before + 1

    def test_the_rules_touch_only_the_tables_the_policy_says(self):
        assert len(RULE_KEYS) == len(RULES), "مفتاحُ قاعدةٍ مكرَّر"
        tables = {rule.table for rule in RULES}
        assert "core_auditlog" not in tables
        assert not any(
            table.startswith(("assessments_", "clinic_", "core_health")) for table in tables
        )


# ══════════════════════════════════════════════════════════════════════
#  الوثيقةُ تحكم كلَّ جدول
# ══════════════════════════════════════════════════════════════════════


def _doc_sections():
    """أسماءُ الجداول من العمود الأوّل في جداول القسمين — لا من ذكرٍ عابرٍ في شرح."""
    text = DOC.read_text(encoding="utf-8")
    deleted = text.split("## 3.", 1)[1].split("## 4.", 1)[0]
    retained = text.split("## 4.", 1)[1].split("## 5.", 1)[0]
    names = re.compile(r"^\| `([a-z][a-z0-9_]+)` \|", re.M)
    return set(names.findall(deleted)), set(names.findall(retained))


class TestEveryTableHasARuling:
    def test_every_database_table_appears_in_the_policy(self):
        deleted, retained = _doc_sections()
        every = {m._meta.db_table for m in apps.get_models(include_auto_created=True)}
        unruled = sorted(every - deleted - retained)
        assert not unruled, f"جداولُ بلا حكمٍ في docs/privacy/data_retention.md: {unruled}"

    def test_no_table_is_both_deleted_and_retained(self):
        deleted, retained = _doc_sections()
        both = sorted(deleted & retained)
        assert not both, f"جداولُ في القسمين معاً: {both}"

    def test_every_rule_table_is_documented_as_deleted_and_nothing_else_is(self):
        deleted, _ = _doc_sections()
        rule_tables = {rule.table for rule in RULES}
        assert rule_tables <= deleted, sorted(rule_tables - deleted)
        # ما في الوثيقة تحت «يُحذف» ولا قاعدةَ له — إلّا ما يتبع أباه بالتسلسل.
        cascade_only = {"token_blacklist_outstandingtoken", "token_blacklist_blacklistedtoken"}
        every = {m._meta.db_table for m in apps.get_models(include_auto_created=True)}
        undocumented = sorted((deleted & every) - rule_tables - cascade_only)
        assert not undocumented, f"موصوفةٌ بالحذف بلا قاعدةٍ تُنفِّذه: {undocumented}"


# ══════════════════════════════════════════════════════════════════════
#  التعطيل والعرض والأثر والتكرار
# ══════════════════════════════════════════════════════════════════════


class TestSwitchesAndTrail:
    def test_zero_disables_everything_and_leaves_no_trail(self, settings):
        settings.PDPPL_DATA_RETENTION_DAYS = 0
        Session.objects.create(
            session_key="z" * 32, session_data="x", expire_date=NOW - timedelta(hours=1)
        )

        report = _run()

        assert report.enabled is False
        assert report.counts == {}
        assert Session.objects.count() == 1
        assert not AuditLog.objects.filter(action="delete").exists()

    def test_dry_run_counts_without_deleting_or_logging(self, retention, school):
        from notifications.models import InAppNotification

        _backdate(
            InAppNotification.objects.create(user=UserFactory(), school=school, title="x"), OLD
        )

        report = _run(dry_run=True)

        assert report.dry_run is True
        assert report.counts["notifications.in_app"] == 1
        assert InAppNotification.objects.count() == 1
        assert not AuditLog.objects.filter(action="delete").exists()

    def test_the_trail_carries_counts_only(self, retention, school):
        from notifications.models import NotificationLog

        _backdate(
            NotificationLog.objects.create(
                school=school, recipient="parent@example.test", body="اسمُ الطالب هنا"
            ),
            OLD,
            "sent_at",
        )

        _run()

        trail = AuditLog.objects.get(action="delete")
        assert trail.user is None
        assert trail.model_name == "other"
        assert trail.changes["event"] == "data_retention_enforced"
        assert trail.changes["retention_days"] == DAYS
        assert trail.changes["deleted"]["notifications.logs"] == 1
        assert set(trail.changes["deleted"]) == RULE_KEYS
        assert trail.changes["total"] == 1
        flat = json.dumps(trail.changes, ensure_ascii=False) + trail.object_repr
        assert "parent@example.test" not in flat
        assert "اسمُ الطالب" not in flat

    def test_a_second_run_finds_nothing(self, retention, school):
        from notifications.models import InAppNotification

        _backdate(
            InAppNotification.objects.create(user=UserFactory(), school=school, title="x"), OLD
        )

        assert _run().total == 1
        assert _run().total == 0
        # التنفيذُ الثاني واقعةٌ أيضاً — سطرٌ لكلّ تنفيذ ولو صفراً.
        assert AuditLog.objects.filter(action="delete").count() == 2

    def test_batches_smaller_than_the_set_still_finish(self, retention, school):
        from notifications.models import InAppNotification

        user = UserFactory()
        for i in range(5):
            _backdate(InAppNotification.objects.create(user=user, school=school, title=str(i)), OLD)

        report = _run(batch_size=2)

        assert report.counts["notifications.in_app"] == 5
        assert not InAppNotification.objects.exists()


# ══════════════════════════════════════════════════════════════════════
#  الأمرُ والمهمّة
# ══════════════════════════════════════════════════════════════════════


class TestCommandAndTask:
    def test_the_command_previews_by_default_and_applies_on_request(
        self, retention, school, capsys
    ):
        from notifications.models import InAppNotification

        _backdate(
            InAppNotification.objects.create(user=UserFactory(), school=school, title="x"), OLD
        )

        call_command("enforce_retention")
        out = capsys.readouterr().out
        assert "عرضٌ فقط" in out
        assert InAppNotification.objects.count() == 1

        call_command("enforce_retention", "--apply")
        out = capsys.readouterr().out
        assert "سجلّ التدقيق" in out
        assert not InAppNotification.objects.exists()

    def test_the_command_refuses_contradictory_flags(self, retention):
        with pytest.raises(CommandError):
            call_command("enforce_retention", "--dry-run", "--apply")

    def test_the_command_says_so_when_disabled(self, settings, capsys):
        settings.PDPPL_DATA_RETENTION_DAYS = 0
        call_command("enforce_retention", "--apply")
        assert "معطَّل" in capsys.readouterr().out
        assert not AuditLog.objects.filter(action="delete").exists()

    def test_the_task_is_registered_and_returns_the_summary(self, retention):
        from shschool.celery import app

        app.loader.import_default_modules()
        assert "core.enforce_data_retention" in app.tasks

        result = app.tasks["core.enforce_data_retention"].apply(kwargs={"dry_run": True}).get()

        assert result["event"] == "data_retention_enforced"
        assert result["dry_run"] is True
        assert set(result["deleted"]) == RULE_KEYS

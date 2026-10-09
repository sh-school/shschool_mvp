"""
tests/test_breach_individuals_and_phased_notice.py
W-20261002-006: مهلةٌ وحالةٌ لإخطار الأفراد المتأثّرين (م.14 + دليل NCSA v2.0) مع أثرٍ في AuditLog.
W-20261002-007: إشعار NCSA على مراحل (مبدئي بأسباب النقص وموعد الاستكمال ثمّ مكتمل) دون أن يوقف
الاستكمالُ اللاحق احتسابَ المهلة الأصليّة.

لا أسماءَ حقيقيّة ولا أرقامَ هويّة: بياناتٌ اصطناعيّة فقط.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from breach import services
from breach.services import InvalidTransitionError
from core.models import AuditLog, BreachReport


@pytest.fixture
def breach(db, school, principal_user):
    return BreachReport.objects.create(
        school=school,
        title="خرقٌ اصطناعيّ للاختبار",
        description="وصف",
        discovered_at=timezone.now() - timedelta(hours=10),
        affected_count=5,
        immediate_action="عزل النظام",
        containment_action="تغيير كلمات المرور",
        notification_text="نصّ إشعارٍ اصطناعي",
        reported_by=principal_user,
    )


def _audit(breach):
    return list(
        AuditLog.objects.filter(object_id=str(breach.pk), action="update").order_by("timestamp")
    )


# ── 007: الإشعار على مراحل ───────────────────────────────────────────


@pytest.mark.django_db
class TestPhasedNcsaNotice:
    def test_initial_notice_requires_reasons_and_a_future_due_date(self, breach, principal_user):
        soon = timezone.now() + timedelta(days=2)
        with pytest.raises(InvalidTransitionError):
            services.record_ncsa_notice(
                breach,
                complete=False,
                missing_reasons=" ",
                completion_due_at=soon,
                user=principal_user,
            )
        with pytest.raises(InvalidTransitionError):
            services.record_ncsa_notice(
                breach,
                complete=False,
                missing_reasons="التحقيق جارٍ",
                completion_due_at=None,
                user=principal_user,
            )
        with pytest.raises(InvalidTransitionError):
            services.record_ncsa_notice(
                breach,
                complete=False,
                missing_reasons="التحقيق جارٍ",
                completion_due_at=timezone.now() - timedelta(hours=1),
                user=principal_user,
            )
        breach.refresh_from_db()
        assert breach.status == "discovered" and breach.ncsa_notified_at is None

    def test_initial_notice_stamps_the_original_deadline_clock_and_audits(
        self, breach, principal_user
    ):
        due = timezone.now() + timedelta(days=3)
        done = services.record_ncsa_notice(
            breach,
            complete=False,
            missing_reasons="عددُ المتأثرين لم يُحسم",
            completion_due_at=due,
            user=principal_user,
        )
        assert done.status == "notified"
        assert done.ncsa_notice_stage == "initial"
        assert done.ncsa_notified_at is not None
        assert done.ncsa_missing_reasons == "عددُ المتأثرين لم يُحسم"
        assert done.ncsa_completion_due_at == due
        assert done.is_overdue is False  # المهلةُ توقّفت بالإشعار الأوّل
        row = _audit(breach)[-1]
        assert row.changes["ncsa_notice_stage"] == "initial"
        assert row.changes["ncsa_completion_due_at"] == due.isoformat()

    def test_completion_does_not_touch_the_original_notified_time(self, breach, principal_user):
        due = timezone.now() + timedelta(days=3)
        first = services.record_ncsa_notice(
            breach, complete=False, missing_reasons="س", completion_due_at=due, user=principal_user
        )
        stamped = first.ncsa_notified_at
        done = services.complete_ncsa_notice(first, user=principal_user)
        assert done.ncsa_notice_stage == "complete"
        assert done.ncsa_notified_at == stamped  # لا تحديثَ يعيد احتسابَ المهلة
        assert done.ncsa_completed_at is not None and done.ncsa_completed_at >= stamped
        row = _audit(breach)[-1]
        assert row.changes["ncsa_notice_stage"] == "complete"
        assert row.changes["completed_after_due"] is False

    def test_completion_after_the_declared_date_is_flagged(self, breach, principal_user):
        due = timezone.now() + timedelta(days=1)
        first = services.record_ncsa_notice(
            breach, complete=False, missing_reasons="س", completion_due_at=due, user=principal_user
        )
        BreachReport.objects.filter(pk=first.pk).update(
            ncsa_completion_due_at=timezone.now() - timedelta(hours=2)
        )
        services.complete_ncsa_notice(first, user=principal_user)
        assert _audit(breach)[-1].changes["completed_after_due"] is True

    def test_cannot_complete_without_an_open_initial_notice(self, breach, principal_user):
        with pytest.raises(InvalidTransitionError):
            services.complete_ncsa_notice(breach, user=principal_user)

    def test_cannot_resolve_while_the_initial_notice_is_incomplete(self, breach, principal_user):
        services.record_ncsa_notice(
            breach,
            complete=False,
            missing_reasons="س",
            completion_due_at=timezone.now() + timedelta(days=1),
            user=principal_user,
        )
        with pytest.raises(InvalidTransitionError):
            services.transition(breach, "resolved", user=principal_user)
        services.complete_ncsa_notice(breach, user=principal_user)
        assert services.transition(breach, "resolved", user=principal_user).status == "resolved"

    def test_complete_notice_in_one_step(self, breach, principal_user):
        done = services.record_ncsa_notice(breach, complete=True, user=principal_user)
        assert done.ncsa_notice_stage == "complete" and done.status == "notified"

    def test_legacy_status_button_counts_as_a_complete_notice(self, breach, principal_user):
        done = services.transition(breach, "notified", user=principal_user)
        assert done.ncsa_notice_stage == "complete"

    def test_second_notice_is_rejected(self, breach, principal_user):
        services.record_ncsa_notice(breach, complete=True, user=principal_user)
        with pytest.raises(InvalidTransitionError):
            services.record_ncsa_notice(breach, complete=True, user=principal_user)


# ── 006: إخطار الأفراد المتأثّرين ────────────────────────────────────


@pytest.mark.django_db
class TestIndividualsNotification:
    def test_new_breach_starts_not_assessed(self, breach):
        assert breach.individuals_status == "not_assessed"
        assert breach.individuals_deadline is None
        assert breach.individuals_overdue is False

    def test_required_defaults_the_deadline_to_the_ncsa_deadline_and_audits(
        self, breach, principal_user
    ):
        done = services.assess_individuals(
            breach, required=True, note="بياناتٌ صحيّة", user=principal_user
        )
        assert done.individuals_status == "required"
        assert done.individuals_deadline == breach.ncsa_deadline
        assert done.individuals_assessed_at is not None
        row = _audit(breach)[-1]
        assert row.changes["individuals_status"] == "required"
        assert row.changes["individuals_deadline"] == breach.ncsa_deadline.isoformat()

    def test_explicit_deadline_wins(self, breach, principal_user):
        custom = timezone.now() + timedelta(hours=20)
        done = services.assess_individuals(
            breach, required=True, note="", deadline=custom, user=principal_user
        )
        assert done.individuals_deadline == custom

    def test_not_required_needs_a_written_reason_and_clears_the_deadline(
        self, breach, principal_user
    ):
        with pytest.raises(InvalidTransitionError):
            services.assess_individuals(breach, required=False, note="  ", user=principal_user)
        done = services.assess_individuals(
            breach, required=False, note="لا ضررَ جسيم: البياناتُ مشفّرةٌ", user=principal_user
        )
        assert done.individuals_status == "not_required"
        assert done.individuals_deadline is None
        assert done.individuals_assessment_note.startswith("لا ضررَ")

    def test_overdue_and_hours_remaining(self, breach, principal_user):
        services.assess_individuals(
            breach,
            required=True,
            note="س",
            deadline=timezone.now() + timedelta(hours=5, minutes=30),
            user=principal_user,
        )
        breach.refresh_from_db()
        assert breach.individuals_hours_remaining == 5 and breach.individuals_overdue is False
        BreachReport.objects.filter(pk=breach.pk).update(
            individuals_deadline=timezone.now() - timedelta(minutes=1)
        )
        breach.refresh_from_db()
        assert breach.individuals_overdue is True and breach.individuals_hours_remaining == 0

    def test_notified_stamps_once_and_flags_lateness(self, breach, principal_user):
        services.assess_individuals(
            breach,
            required=True,
            note="س",
            deadline=timezone.now() - timedelta(hours=1),
            user=principal_user,
        )
        done = services.record_individuals_notified(breach, channel="sms", user=principal_user)
        assert done.individuals_status == "notified" and done.individuals_notified_at
        assert done.individuals_notified_channel == "sms"
        assert _audit(breach)[-1].changes["notified_after_deadline"] is True
        with pytest.raises(InvalidTransitionError):
            services.record_individuals_notified(breach, channel="sms", user=principal_user)
        with pytest.raises(InvalidTransitionError):  # لا يُعاد التقدير بعد الإخطار الفعليّ
            services.assess_individuals(breach, required=False, note="ن", user=principal_user)

    def test_cannot_notify_individuals_not_assessed_as_required(self, breach, principal_user):
        with pytest.raises(InvalidTransitionError):
            services.record_individuals_notified(breach, channel="sms", user=principal_user)

    def test_cannot_resolve_while_individuals_are_pending(self, breach, principal_user):
        services.transition(breach, "assessing", user=principal_user)
        services.assess_individuals(breach, required=True, note="س", user=principal_user)
        with pytest.raises(InvalidTransitionError):
            services.transition(breach, "resolved", user=principal_user)
        services.record_individuals_notified(breach, channel="email", user=principal_user)
        assert services.transition(breach, "resolved", user=principal_user).status == "resolved"

    def test_closing_without_assessment_is_audited_not_blocked(self, breach, principal_user):
        services.transition(breach, "assessing", user=principal_user)
        services.transition(breach, "resolved", user=principal_user)
        assert _audit(breach)[-1].changes["closed_without_individuals_assessment"] is True

    def test_resolved_breach_is_frozen(self, breach, principal_user):
        services.transition(breach, "assessing", user=principal_user)
        services.transition(breach, "resolved", user=principal_user)
        with pytest.raises(InvalidTransitionError):
            services.assess_individuals(breach, required=True, note="س", user=principal_user)


# ── الواجهة والإدارة والعزل ─────────────────────────────────────────


@pytest.mark.django_db
class TestMinimumFieldsDecisionOwnerAndFixedDeadline:
    """مواصفة 0104: «مكتمل» بحدٍّ أدنى؛ «غير لازم» بسببٍ وصاحبِ قرار؛ والمهلةُ ثابتةٌ من الاكتشاف."""

    def test_complete_notice_is_refused_while_minimum_fields_are_missing(
        self, breach, principal_user
    ):
        BreachReport.objects.filter(pk=breach.pk).update(
            affected_count=0, containment_action="", notification_text=""
        )
        breach.refresh_from_db()
        assert set(services.ncsa_minimum_gaps(breach)) == {
            "نصّ الإشعار",
            "إجراءات الاحتواء",
            "عدد المتأثرين",
        }
        with pytest.raises(InvalidTransitionError) as exc:
            services.record_ncsa_notice(breach, complete=True, user=principal_user)
        assert "ينقصه" in str(exc.value)
        with pytest.raises(InvalidTransitionError):
            services.transition(breach, "notified", user=principal_user)
        breach.refresh_from_db()
        assert breach.status == "discovered" and breach.ncsa_notified_at is None

    def test_incomplete_data_goes_through_the_initial_notice_then_completion_needs_the_minimum(
        self, breach, principal_user
    ):
        BreachReport.objects.filter(pk=breach.pk).update(affected_count=0)
        breach.refresh_from_db()
        first = services.record_ncsa_notice(
            breach,
            complete=False,
            missing_reasons="العددُ لم يُحسم",
            completion_due_at=timezone.now() + timedelta(days=2),
            user=principal_user,
        )
        with pytest.raises(InvalidTransitionError):
            services.complete_ncsa_notice(first, user=principal_user)
        BreachReport.objects.filter(pk=breach.pk).update(affected_count=40)
        first.refresh_from_db()
        assert (
            services.complete_ncsa_notice(first, user=principal_user).ncsa_notice_stage
            == "complete"
        )

    def test_deadline_is_fixed_from_discovery_and_survives_every_update(
        self, breach, principal_user
    ):
        original = breach.ncsa_deadline
        assert original == breach.discovered_at + timedelta(hours=72)
        services.transition(breach, "assessing", user=principal_user)
        services.assess_individuals(breach, required=True, note="س", user=principal_user)
        services.record_ncsa_notice(
            breach,
            complete=False,
            missing_reasons="س",
            completion_due_at=timezone.now() + timedelta(days=1),
            user=principal_user,
        )
        services.complete_ncsa_notice(breach, user=principal_user)
        breach.refresh_from_db()
        assert breach.ncsa_deadline == original
        breach.title = "عنوانٌ معدَّل"
        breach.save()
        breach.refresh_from_db()
        assert breach.ncsa_deadline == original

    def test_decision_owner_is_recorded_and_channel_is_required(self, breach, principal_user):
        done = services.assess_individuals(
            breach, required=False, note="لا ضررَ جسيم", user=principal_user
        )
        assert done.individuals_decided_by_id == principal_user.pk
        services.assess_individuals(breach, required=True, note="س", user=principal_user)
        with pytest.raises(InvalidTransitionError):
            services.record_individuals_notified(breach, channel="", user=principal_user)
        with pytest.raises(InvalidTransitionError):
            services.record_individuals_notified(breach, channel="fax", user=principal_user)

    def test_audit_rows_carry_states_and_dates_only(self, breach, principal_user):
        services.assess_individuals(
            breach, required=True, note="نصٌّ حرٌّ لا يدخل السجلّ", user=principal_user
        )
        services.record_individuals_notified(breach, channel="portal", user=principal_user)
        for row in _audit(breach):
            assert "نصٌّ حرٌّ" not in str(row.changes)
            assert "نصٌّ حرٌّ" not in row.object_repr

    def test_dashboard_marks_overdue_individuals_like_ncsa(self, client_as, school, principal_user):
        late = BreachReport.objects.create(
            school=school,
            title="متأخّر",
            description="d",
            discovered_at=timezone.now() - timedelta(hours=90),
            reported_by=principal_user,
        )
        services.assess_individuals(late, required=True, note="س", user=principal_user)
        html = client_as(principal_user).get("/breach/").content.decode()
        assert "إخطار الأفراد فات" in html
        late.refresh_from_db()
        assert late.individuals_overdue is True


@pytest.mark.django_db
class TestViewsAndIsolation:
    def test_detail_shows_both_tracks(self, client_as, principal_user, breach):
        html = client_as(principal_user).get(f"/breach/{breach.pk}/").content.decode()
        assert "إخطار الأفراد المتأثّرين" in html
        assert "لم يُقيَّم بعدُ" in html
        assert f"/breach/{breach.pk}/ncsa-notice/" in html

    def test_assess_endpoint_rejects_missing_reason_with_arabic_message(
        self, client_as, principal_user, breach
    ):
        resp = client_as(principal_user).post(
            f"/breach/{breach.pk}/individuals/", {"required": "0", "note": ""}, follow=True
        )
        breach.refresh_from_db()
        assert breach.individuals_status == "not_assessed"
        assert "اذكر سببَ عدم لزوم الإخطار" in resp.content.decode()

    def test_assess_then_notified_via_http(self, client_as, principal_user, breach):
        c = client_as(principal_user)
        c.post(f"/breach/{breach.pk}/individuals/", {"required": "1", "note": "ضررٌ جسيم"})
        breach.refresh_from_db()
        assert breach.individuals_status == "required"
        c.post(f"/breach/{breach.pk}/individuals/notified/")  # بلا قناة: مرفوض
        breach.refresh_from_db()
        assert breach.individuals_status == "required"
        c.post(f"/breach/{breach.pk}/individuals/notified/", {"channel": "letter"})
        breach.refresh_from_db()
        assert (
            breach.individuals_status == "notified"
            and breach.individuals_notified_channel == "letter"
        )

    def test_initial_notice_via_http_and_history_wording(self, client_as, principal_user, breach):
        c = client_as(principal_user)
        due = (timezone.localtime() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
        c.post(
            f"/breach/{breach.pk}/ncsa-notice/",
            {"is_initial": "on", "missing_reasons": "التحقيق جارٍ", "completion_due_at": due},
        )
        breach.refresh_from_db()
        assert breach.ncsa_notice_stage == "initial"
        html = c.get(f"/breach/{breach.pk}/").content.decode()
        assert "إشعار مبدئي" in html
        assert "التحقيق جارٍ" in html
        c.post(f"/breach/{breach.pk}/ncsa-complete/")
        breach.refresh_from_db()
        assert breach.ncsa_notice_stage == "complete"
        assert "استُكمل إشعار NCSA" in c.get(f"/breach/{breach.pk}/").content.decode()

    def test_initial_notice_via_http_without_reasons_is_rejected(
        self, client_as, principal_user, breach
    ):
        due = (timezone.localtime() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
        client_as(principal_user).post(
            f"/breach/{breach.pk}/ncsa-notice/",
            {"is_initial": "on", "missing_reasons": "", "completion_due_at": due},
        )
        breach.refresh_from_db()
        assert breach.status == "discovered"

    def test_dashboard_counts_pending_and_overdue_individuals(
        self, client_as, school, principal_user, breach
    ):
        services.assess_individuals(breach, required=True, note="س", user=principal_user)
        late = BreachReport.objects.create(
            school=school,
            title="متأخّر",
            description="d",
            discovered_at=timezone.now() - timedelta(hours=90),
            reported_by=principal_user,
        )
        services.assess_individuals(late, required=True, note="س", user=principal_user)
        stats = client_as(principal_user).get("/breach/").context["stats"]
        assert stats["individuals_pending"] == 2
        assert stats["individuals_overdue"] == 1

    def test_other_school_cannot_touch_the_breach(self, client_as, breach):
        from tests.conftest import MembershipFactory, RoleFactory, SchoolFactory, UserFactory

        other_school = SchoolFactory()
        outsider = UserFactory(full_name="مستخدم اصطناعي")
        MembershipFactory(
            user=outsider,
            school=other_school,
            role=RoleFactory(school=other_school, name="principal"),
        )
        c = client_as(outsider)
        assert c.post(f"/breach/{breach.pk}/individuals/", {"required": "1"}).status_code == 404
        assert c.post(f"/breach/{breach.pk}/ncsa-complete/").status_code == 404
        breach.refresh_from_db()
        assert breach.individuals_status == "not_assessed"


@pytest.mark.django_db
class TestMigrationBackfill:
    def test_backfill_marks_prior_notified_breaches_complete(self, breach):
        import importlib

        from django.apps import apps

        mod = importlib.import_module("core.migrations.0081_breach_individuals_and_phased_ncsa")
        stamped = timezone.now() - timedelta(hours=3)
        BreachReport.objects.filter(pk=breach.pk).update(
            status="notified", ncsa_notified_at=stamped, ncsa_notice_stage="none"
        )
        mod.backfill_ncsa_stage(apps, None)
        breach.refresh_from_db()
        assert breach.ncsa_notice_stage == "complete"
        assert breach.ncsa_completed_at == stamped


@pytest.mark.django_db
class TestAdminRegistration:
    def test_breach_report_is_registered_with_full_admin(self, client_as, breach):
        from tests.conftest import UserFactory

        admin_client = client_as(UserFactory(is_staff=True, is_superuser=True))
        resp = admin_client.get("/admin/core/breachreport/")
        assert resp.status_code == 200
        resp = admin_client.get(f"/admin/core/breachreport/{breach.pk}/change/")
        assert resp.status_code == 200
        html = resp.content.decode()
        assert "إخطار الأفراد المتأثّرين" in html and "إشعار NCSA" in html

    def test_admin_cannot_add_and_notice_fields_are_read_only(self):
        from django.contrib import admin as dj_admin

        model_admin = dj_admin.site._registry[BreachReport]
        assert model_admin.has_add_permission(None) is False
        for field in ("ncsa_notice_stage", "individuals_status", "individuals_deadline"):
            assert field in model_admin.readonly_fields

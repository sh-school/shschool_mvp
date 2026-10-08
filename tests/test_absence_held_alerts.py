"""[ATTENDANCE] تنبيهاتُ الغياب «المحجوزة» وإخطارُ وليّ الأمر بزرّ حاصر الغياب وحدَه (قرارُ المالك D-246م).

الثوابت: التنبيهُ يُنشأ `held` ولا يُرسَل لوليّ الأمر شيءٌ من أيّ مسار (المسحُ ولا المساران القديمان ولا مرسِلُ 07:00 ولا الزرّ اليدويّ)؛
والإخطارُ يُصدره حاصرُ الغياب (`admin_supervisor` + `wings.school_wide`) بزرّه بعد ح4، مرّةً واحدةً، لمستلمٍ من الروابط المسجَّلة لا من الطلب؛
والفشلُ يرجع إلى `held` لا `pending`؛ ومن صُحّح غيابُه يُوسَم `resolved` بلا إرسال.
"""

import datetime as dt
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from core.models import TimeBand
from operations.end_of_day import sweep_absence_gates, would_create
from operations.models import AbsenceAlert, TimeSlotConfig
from operations.services import AttendanceService
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import SUNDAY, at
from tests.test_absence_alerts import _absent, student, subject, year_window  # noqa: F401
from tests.test_school_wide_absence_supervisor import (  # noqa: F401
    _staff,
    general,
    plain_supervisor,
    principal,
)
from wings import absence_notice_services as absence_notices
from wings.absence_notice_services import IssueRefused

pytestmark = pytest.mark.django_db

DISPATCH = "notifications.hub.NotificationHub.dispatch_to_parents"


@pytest.fixture
def held(db, school, student):
    """تنبيهٌ محجوز من أمس (فيجوز إصدارُه في أيّ وقت)."""
    alert = AbsenceAlert.objects.create(
        school=school,
        student=student,
        absence_count=5,
        gate="s1_midterm",
        period_start=dt.date(2025, 9, 1),
        period_end=dt.date(2026, 6, 30),
        status="held",
    )
    AbsenceAlert.objects.filter(pk=alert.pk).update(created_at=at(8, 0) - timedelta(days=1))
    alert.refresh_from_db()
    return alert


def _due(days=5):
    from operations.absence_policy import gates_for

    gate = next(g for g in gates_for("G7") if g.key == "s1_midterm")
    return patch("wings.absence_notice_services._still_due", return_value=(True, gate, days))


# ── المنشأ: محجوز، بلا إرسال ──


def test_the_sweep_and_the_old_entry_point_both_create_held_without_any_parent_send(
    school, class_group, teacher_user, subject, student, year_window
):
    start, _ = year_window
    _absent(school, class_group, teacher_user, subject, student, start, 9)
    day = start + timedelta(days=8)

    with patch(DISPATCH) as dispatch:
        sweep_absence_gates(school, day)
        AttendanceService.check_absence_threshold(student, school, on=day)  # المسارُ القديم
    statuses = set(AbsenceAlert.objects.filter(student=student).values_list("status", flat=True))

    assert statuses == {"held"}, "كلُّ تنبيهٍ جديدٍ يُنشأ محجوزاً"
    dispatch.assert_not_called()
    assert AbsenceAlert.objects.filter(student=student).count() == 3, "get_or_create: لا تكرار"


def test_no_path_sends_to_a_parent_from_a_held_alert_except_the_button(school, held, student):
    """الاختبارُ الإلزاميّ: مرسِلُ 07:00 والزرّ اليدويّ ومهمّةُ الإرسال والمسحُ — كلُّها لا تلتقط المحجوز."""
    from notifications.services import NotificationService
    from notifications.tasks import send_pending_absence_alerts_task

    with (
        patch(DISPATCH) as dispatch,
        patch.object(NotificationService, "notify_absence", wraps=None) as notify,
    ):
        NotificationService.send_pending_absence_alerts(school)  # زرّ الإرسال اليدويّ
        send_pending_absence_alerts_task()  # مهمّةُ 07:00
        sweep_absence_gates(school, SUNDAY)  # المسح
    held.refresh_from_db()

    assert held.status == "held"
    dispatch.assert_not_called()
    notify.assert_not_called()


# ── الزرّ: الأدوار والتوقيت ──


def test_only_the_school_wide_absence_holder_may_issue(
    school, held, plain_supervisor, teacher_user
):
    for user in (plain_supervisor, teacher_user):
        with pytest.raises(IssueRefused):
            absence_notices.issue(user, school, held.pk, now=at(15, 0))
    held.refresh_from_db()
    assert held.status == "held"


def test_a_same_day_alert_waits_for_the_end_of_period_four(
    school, class_group, student, general, year_window
):
    band = TimeBand.objects.create(school=school, code="ground", name="الأرضيّ", floor="ground")
    TimeSlotConfig.objects.create(
        school=school,
        band=band,
        day_type="regular",
        period_number=4,
        start_time=dt.time(9, 0),
        end_time=dt.time(9, 45),
    )
    type(class_group).objects.filter(pk=class_group.pk).update(time_band=band)
    alert = AbsenceAlert.objects.create(
        school=school,
        student=student,
        absence_count=5,
        gate="s1_midterm",
        period_start=dt.date(2025, 9, 1),
        period_end=dt.date(2026, 6, 30),
        status="held",
    )
    AbsenceAlert.objects.filter(pk=alert.pk).update(created_at=at(8, 0))

    with _due(), patch(DISPATCH) as dispatch:
        with pytest.raises(IssueRefused):
            absence_notices.issue(general, school, alert.pk, now=at(9, 30))
        dispatch.assert_not_called()
        result = absence_notices.issue(general, school, alert.pk, now=at(9, 46))

    assert result.status == "sent"
    alert.refresh_from_db()
    assert alert.status == "notified"


# ── الزرّ: التفرّد والفشل والتصحيح ──


def test_issuing_twice_sends_once_and_the_second_is_refused(school, held, general):
    with _due(), patch(DISPATCH) as dispatch:
        first = absence_notices.issue(general, school, held.pk, now=at(15, 0))
        with pytest.raises(IssueRefused):
            absence_notices.issue(general, school, held.pk, now=at(15, 1))

    assert first.status == "sent"
    assert dispatch.call_count == 1


def test_a_lost_race_on_the_claim_is_refused_without_sending(school, held, general):
    """طلبٌ آخرُ سبق إلى المطالبة الذرّيّة (held→pending) بين القراءة والتحويل."""
    real_filter = AbsenceAlert.objects.filter

    def racing(*args, **kwargs):
        queryset = real_filter(*args, **kwargs)
        if kwargs.get("status") == "held" and "pk" in kwargs:
            real_filter(pk=kwargs["pk"]).update(status="issuing")  # سبقه غيرُه
        return queryset

    with _due(), patch(DISPATCH) as dispatch, patch.object(AbsenceAlert.objects, "filter", racing):
        with pytest.raises(IssueRefused):
            absence_notices.issue(general, school, held.pk, now=at(15, 0))

    dispatch.assert_not_called()


def test_a_failed_send_returns_the_alert_to_held_not_pending(school, held, general):
    with _due(), patch(DISPATCH, side_effect=RuntimeError("boom")):
        with pytest.raises(IssueRefused):
            absence_notices.issue(general, school, held.pk, now=at(15, 0))
    held.refresh_from_db()

    assert held.status == "held", "لا يلتقطه مرسِلُ 07:00 ولا يخرج إخطارٌ بلا كاتب"


def test_a_corrected_absence_is_resolved_without_sending(school, held, general):
    with (
        patch("wings.absence_notice_services._still_due", return_value=(False, None, 0)),
        patch(DISPATCH) as dispatch,
    ):
        result = absence_notices.issue(general, school, held.pk, now=at(15, 0))
    held.refresh_from_db()

    assert result.status == "resolved" and held.status == "resolved"
    dispatch.assert_not_called()


def test_the_audit_carries_ids_and_the_gate_but_no_names(school, held, general, student):
    from core.models import AuditLog

    with _due(), patch(DISPATCH):
        absence_notices.issue(general, school, held.pk, now=at(15, 0))
    audit = AuditLog.objects.get(object_id=str(held.pk), changes__action="issued")

    assert audit.changes["gate"] == "s1_midterm" and audit.changes["action"] == "issued"
    assert student.full_name not in str(audit.changes)


# ── الشاشة ──


def test_the_notices_screen_is_404_for_everyone_but_the_holder(
    client_as, school, held, general, plain_supervisor
):
    url = reverse("wings:absence_notices")
    issue_url = reverse("wings:absence_notice_issue", args=[held.pk])

    assert client_as(plain_supervisor).get(url).status_code == 404
    assert client_as(plain_supervisor).post(issue_url).status_code == 404
    page = client_as(general).get(url)
    assert page.status_code == 200 and "إصدار الإخطار" in page.content.decode()


# ── التقرير (قراءةٌ فقط) والهجرة ──


def test_the_report_command_reads_only_and_counts_what_the_sweep_would_create(
    school, class_group, teacher_user, subject, student, year_window, capsys
):
    start, _ = year_window
    _absent(school, class_group, teacher_user, subject, student, start, 9)
    day = start + timedelta(days=8)
    before = AbsenceAlert.objects.count()

    expected = would_create(school, day)
    call_command("absence_alerts_report", school=school.code, day=day.isoformat())
    out = capsys.readouterr().out

    assert expected == 3 and AbsenceAlert.objects.count() == before, "قراءةٌ لا تكتب"
    assert "سيُنشئ مسحُ" in out and "معلَّقةٌ سيرسلها 07:00" in out
    sweep_absence_gates(school, day)
    assert would_create(school, day) == 0


def test_the_held_status_migration_is_a_reversible_choices_only_change(db):
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    forward = ("operations", "0074_absence_alert_held_status")
    back = ("operations", "0073_class_grid_constraints")
    MigrationExecutor(connection).migrate([back])
    assert forward not in MigrationExecutor(connection).loader.applied_migrations
    MigrationExecutor(connection).migrate([forward])
    assert forward in MigrationExecutor(connection).loader.applied_migrations


# ── طلبةُ التربية الخاصّة (ESE): بلا إنذار «منتصف الفصل» (D-255م) ──


def _make_ese(class_group):
    type(class_group).objects.filter(pk=class_group.pk).update(section="07/ESE", wing=None)
    class_group.refresh_from_db()


def _gates_of(student):
    return sorted(AbsenceAlert.objects.filter(student=student).values_list("gate", flat=True))


@pytest.mark.parametrize(
    ("days", "ese_gates", "regular_gates"),
    [
        (3, [], ["s1_midterm"]),  # عند 5: العاديُّ يُنذَر، وطالبُ ESE لا
        (6, ["s1_final"], ["s1_final", "s1_midterm"]),  # عند 8 يُنذَر ESE
        (
            9,
            ["s1_final"],
            ["s1_final", "s1_midterm", "s2_midterm"],
        ),  # تجاوز 8؛ وعند 11 لا إنذارَ لـESE
        (
            13,
            ["s1_final", "s2_final"],
            ["s1_final", "s1_midterm", "s2_final", "s2_midterm"],
        ),  # عند 15
    ],
)
def test_an_ese_student_gets_only_the_final_gates_and_a_regular_student_is_unchanged(
    school, class_group, teacher_user, subject, student, year_window, days, ese_gates, regular_gates
):
    start, _ = year_window
    _absent(school, class_group, teacher_user, subject, student, start, days)
    day = start + timedelta(days=days)

    AttendanceService.raise_absence_alerts(student, school, on=day)
    regular = _gates_of(student)
    AbsenceAlert.objects.filter(student=student).delete()
    _make_ese(class_group)
    AttendanceService.raise_absence_alerts(student, school, on=day)

    assert regular == regular_gates, "الطالبُ العاديّ كما هو"
    assert _gates_of(student) == ese_gates
    assert set(AbsenceAlert.objects.filter(student=student).values_list("status", flat=True)) <= {
        "held"
    }


def test_an_ese_student_is_derived_from_the_class_not_a_flag_and_the_days_are_unchanged(
    school, class_group, teacher_user, subject, student, year_window
):
    from operations.absence_standing import standing_for

    start, _ = year_window
    _absent(school, class_group, teacher_user, subject, student, start, 6)
    day = start + timedelta(days=6)
    before = standing_for(student, school, grade="G7", on=day).unexcused_days
    _make_ese(class_group)

    after = standing_for(student, school, grade="G7", on=day, ese=True).unexcused_days

    assert before == after == 6, "حسابُ أيّام الغياب لا يتغيّر"


# ── الحالة الوسيطة «قيد الإصدار» (ملاحظة 0104، P2) ──


def test_the_bulk_sender_never_touches_an_issuing_alert(school, held):
    from notifications.services import NotificationService
    from notifications.tasks import send_pending_absence_alerts_task

    AbsenceAlert.objects.filter(pk=held.pk).update(status="issuing")

    with patch(DISPATCH) as dispatch, patch.object(NotificationService, "notify_absence") as notify:
        NotificationService.send_pending_absence_alerts(school)
        send_pending_absence_alerts_task()
    held.refresh_from_db()

    assert held.status == "issuing"
    dispatch.assert_not_called()
    notify.assert_not_called()


def test_a_crash_between_the_claim_and_the_end_is_reconciled_back_to_held_without_sending(
    school, held, general
):
    """العمليةُ توقّفت بعد المطالبة (إعادةُ نشر): بعد المهلة يعود التنبيهُ إلى «محجوز» ولا يُرسَل شيء."""
    with _due(), patch(DISPATCH, side_effect=KeyboardInterrupt):
        with pytest.raises(KeyboardInterrupt):
            absence_notices.issue(general, school, held.pk, now=at(15, 0))
    held.refresh_from_db()
    assert held.status == "issuing", "علق في الوسيطة"

    fresh = absence_notices.reconcile_stuck(school)
    assert fresh == 0, "قبل المهلة لا يُمسّ (قد يكون إرسالٌ جارياً)"

    late = absence_notices.reconcile_stuck(
        school, now=timezone.now() + timedelta(minutes=absence_notices.STUCK_MINUTES + 1)
    )
    held.refresh_from_db()
    assert late == 1 and held.status == "held"


def test_a_failed_send_is_audited_without_names(school, held, general, student):
    from core.models import AuditLog

    with _due(), patch(DISPATCH, side_effect=RuntimeError("boom")):
        with pytest.raises(IssueRefused):
            absence_notices.issue(general, school, held.pk, now=at(15, 0))

    failed = AuditLog.objects.get(object_id=str(held.pk), changes__action="issue_failed")
    assert student.full_name not in str(failed.changes)


def test_the_screen_shows_the_readable_gate_label_not_the_raw_key(client_as, school, held, general):
    page = client_as(general).get(reverse("wings:absence_notices")).content.decode()

    assert "منتصف الفصل الأول" in page and "s1_midterm" not in page


def test_the_preview_seed_refuses_to_run_outside_the_preview_environment(db):
    """ملاحظة 0104: سكربتُ البذر يُنفَّذ بـmanage.py shell على أيّ قاعدة؛ فأوّلُ سطرٍ يرفض خارج المعاينة (testing ليست معاينة)."""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parent.parent / "docs" / "preview_held_alerts_seed.py"
    ).read_text(encoding="utf-8")

    with pytest.raises(SystemExit) as refused:
        exec(compile(source, "preview_held_alerts_seed.py", "exec"), {"__name__": "__main__"})  # noqa: S102

    assert "للمعاينة المركزيّة" in str(refused.value)
    assert AbsenceAlert.objects.count() == 0, "لم يُكتب شيء"


# ── بذر المعاينة: ذرّيّ، لا يصطدم بالقائم، و down مقيَّد ──


def _run_seed(monkeypatch, action):
    from pathlib import Path

    monkeypatch.setenv("SEED_ACTION", action)
    monkeypatch.setattr("core.preview_accounts.in_preview_environment", lambda: True)
    source = (
        Path(__file__).resolve().parent.parent / "docs" / "preview_held_alerts_seed.py"
    ).read_text(encoding="utf-8")
    exec(compile(source, "preview_held_alerts_seed.py", "exec"), {"__name__": "__main__"})  # noqa: S102


@pytest.fixture
def seeded_world(db, school, year, klass, kid, teacher, wing):
    """مدرسةٌ بتقويمٍ مبذورٍ وشعبةٍ ذاتِ جناحٍ وطالبٍ ومعلّمٍ مُسنَد — وجلساتٌ قائمةٌ للمعلّم تحجز خاناتِ البذر الأولى (القاعدةُ ليست فارغة)."""
    from core.academic_calendar import academic_year_window
    from operations.models import Session, Subject, SubjectClassAssignment
    from tests.conftest import ClassGroupFactory

    call_command("seed_academic_calendar", school=school.code, verbosity=0)
    subject = Subject.objects.create(school=school, name_ar="العلوم", code="SCI")
    SubjectClassAssignment.objects.create(
        school=school,
        class_group=klass,
        subject=subject,
        teacher=teacher,
        weekly_periods=2,
        academic_year=year,
    )
    other = ClassGroupFactory(
        school=school, grade="G8", section="9", level_type="prep", academic_year=year, wing=wing
    )
    start, _ = academic_year_window(school)
    for offset in range(40):  # المعلّمُ مشغولٌ في الخانة الأولى بشعبةٍ أخرى طوال أسابيع
        Session.objects.create(
            school=school,
            class_group=other,
            teacher=teacher,
            subject=subject,
            date=start + timedelta(days=offset),
            start_time=dt.time(5, 0),
            end_time=dt.time(5, 45),
            status="completed",
        )
    return school


def test_the_seed_up_skips_existing_conflicts_and_raises_held_alerts(
    seeded_world, kid, monkeypatch
):
    from operations.models import Session

    _run_seed(monkeypatch, "up")
    tagged = Session.objects.filter(notes="preview-held-alerts-seed")

    assert tagged.count() == 5, "خمسةُ أيّامٍ رغم تصادم الخانة الأولى"
    assert AbsenceAlert.objects.filter(student=kid, status="held").exists()


def test_a_failed_seed_up_leaves_nothing_behind(seeded_world, kid, monkeypatch):
    from operations.models import Session

    with patch.object(AttendanceService, "raise_absence_alerts", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            _run_seed(monkeypatch, "up")

    assert not Session.objects.filter(notes="preview-held-alerts-seed").exists()
    assert not AbsenceAlert.objects.filter(student=kid).exists()


def test_seed_down_removes_only_what_the_seed_made(seeded_world, kid, monkeypatch):
    from operations.models import Session

    before_alert = AbsenceAlert.objects.create(
        school=seeded_world,
        student=kid,
        absence_count=1,
        gate="s1_final",
        period_start=dt.date(2025, 9, 1),
        period_end=dt.date(2026, 6, 30),
        status="resolved",
    )
    AbsenceAlert.objects.filter(pk=before_alert.pk).update(
        created_at=timezone.now() - timedelta(days=30)
    )
    other_sessions = Session.objects.count()

    _run_seed(monkeypatch, "up")
    _run_seed(monkeypatch, "down")

    assert Session.objects.count() == other_sessions, "الجلساتُ القائمةُ لم تُمسّ"
    assert not Session.objects.filter(notes="preview-held-alerts-seed").exists()
    assert AbsenceAlert.objects.filter(pk=before_alert.pk).exists(), "تنبيهٌ سابقٌ للبذر يبقى"
    assert AbsenceAlert.objects.filter(student=kid).count() == 1

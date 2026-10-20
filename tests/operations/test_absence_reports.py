"""تقارير الغياب الدوريّة (W-20261020-005 الخطوتان 5 و6): لقطاتٌ ثابتةٌ بنسخٍ، وموعدٌ لكلّ نوع، وأرشيفٌ بصلاحيّة المتابعة."""

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from core.models import CalendarEvent
from operations.absence_reports_beat import absence_reports_beat
from operations.models import AbsenceReportSnapshot
from operations.services import absence_snapshots as snaps
from tests.operations.test_absence_followup import (  # noqa: F401
    _calendar_first,
    absent_both,
    second_wing,
    staff,
)
from tests.test_period_register import (  # noqa: F401
    SUNDAY,
    kids,
    klass,
    other_teacher,
    subjects,
    supervisor,
    teacher,
    year,
)

pytestmark = pytest.mark.django_db

NOON = dt.time(12, 0)


def _at(day, t=NOON):
    return dt.datetime.combine(day, t)


def test_calendar_helpers_follow_the_qatar_week():
    assert snaps.last_thursday(2026, 10) == dt.date(2026, 10, 29)
    assert snaps.week_bounds(dt.date(2026, 10, 21)) == (
        dt.date(2026, 10, 18),
        dt.date(2026, 10, 22),
    )
    assert snaps.week_bounds(dt.date(2026, 10, 18)) == (
        dt.date(2026, 10, 18),
        dt.date(2026, 10, 22),
    )


def test_the_daily_report_is_due_only_after_the_second_period(school, absent_both):
    specs = snaps.due_specs(school, _at(SUNDAY))
    daily = [s for s in specs if s.kind == snaps.DAILY]
    assert daily and daily[0].start == daily[0].end == SUNDAY


def test_generating_counts_students_and_is_stamped_and_idempotent(school, absent_both):
    spec = snaps.ReportSpec(snaps.DAILY, "", SUNDAY, SUNDAY)
    snap = snaps.generate(school, spec)
    payload = snap.payload
    assert snap.revision == 1 and snap.school_days == 1 and snap.generated_at
    from wings.ministry_selectors import ministry_summary

    total = ministry_summary(school, SUNDAY).total
    # الوحدةُ الطالب، والأرقامُ تطابق شاشةَ الوزارة حرفياً
    assert payload["school"]["absent"] == total.absent_both >= 1
    assert payload["school"]["enrolled"] == total.enrolled
    assert payload["wings"], "الأجنحةُ في اللقطة"
    # لا اسمَ طالبٍ ولا رقمٍ شخصيّ في المحتوى
    assert "طالب" not in str(payload)
    assert not any(s == spec for s in snaps.due_specs(school, _at(SUNDAY)))


def test_recompute_adds_a_revision_and_never_edits_the_old_one(school, absent_both):
    spec = snaps.ReportSpec(snaps.DAILY, "", SUNDAY, SUNDAY)
    first = snaps.generate(school, spec)
    second = snaps.generate(school, spec)
    assert (first.revision, second.revision) == (1, 2)
    first.payload = {}
    with pytest.raises(PermissionDenied):
        first.save()
    assert AbsenceReportSnapshot.objects.filter(school=school).count() == 2


def test_quarterly_reports_are_one_per_grade_scope_from_its_own_midterm_end(
    school, seeded_calendar
):
    events = list(
        CalendarEvent.objects.filter(academic_year__school=school, event_type="midterm_exam")
    )
    first = min(events, key=lambda e: e.end_date)
    now = _at(first.end_date + dt.timedelta(days=1))
    quarterly = [s for s in snaps.due_specs(school, now) if s.kind == snaps.QUARTERLY]
    assert {s.scope for s in quarterly} <= set(snaps.QUARTER_SCOPES)
    for spec in quarterly:
        ends = {e.end_date for e in events if e.grade_scope == spec.scope}
        assert spec.end in ends and spec.end < now.date()


def test_the_beat_is_off_unless_the_flag_is_set():
    assert absence_reports_beat({}) == {}
    entry = absence_reports_beat({"ABSENCE_REPORTS_BEAT": "1"})
    assert (
        entry["generate-due-absence-reports"]["task"] == "operations.generate_due_absence_reports"
    )


def test_archive_is_open_to_followup_holders_and_closed_to_a_teacher(
    client_as, staff, teacher, school, absent_both
):
    snap = snaps.generate(school, snaps.ReportSpec(snaps.DAILY, "", SUNDAY, SUNDAY))
    assert client_as(staff["principal"]).get(reverse("absence_reports_archive")).status_code == 200
    detail = client_as(staff["principal"]).get(reverse("absence_report_detail", args=[snap.pk]))
    assert detail.status_code == 200 and "أعد الحساب الآن" in detail.content.decode()
    for name, args in (("absence_reports_archive", []), ("absence_report_detail", [snap.pk])):
        assert client_as(teacher).get(reverse(name, args=args)).status_code == 403


def test_the_recompute_button_creates_a_new_revision(client_as, staff, school, absent_both):
    snap = snaps.generate(school, snaps.ReportSpec(snaps.DAILY, "", SUNDAY, SUNDAY))
    resp = client_as(staff["principal"]).post(reverse("absence_report_recompute", args=[snap.pk]))
    assert resp.status_code == 302
    assert AbsenceReportSnapshot.objects.filter(school=school, period_start=SUNDAY).count() == 2


def test_the_recompute_is_post_only(client_as, staff, school, absent_both):
    snap = snaps.generate(school, snaps.ReportSpec(snaps.DAILY, "", SUNDAY, SUNDAY))
    resp = client_as(staff["principal"]).get(reverse("absence_report_recompute", args=[snap.pk]))
    assert resp.status_code == 405


def test_exports_are_audited_with_who_and_which_filter_and_never_a_name(
    client_as, staff, absent_both
):
    from core.models import AuditLog

    resp = client_as(staff["principal"]).get(
        reverse("absence_followup_xlsx"), {"date": SUNDAY.isoformat(), "q": "الجناح"}
    )
    assert resp.status_code == 200
    row = AuditLog.objects.filter(changes__kind="operations.absence_followup_xlsx").latest(
        "timestamp"
    )
    assert row.user_id == staff["principal"].id and "q=" in row.object_repr
    assert "طالب" not in row.object_repr and row.changes["rows"] >= 1


def test_the_wing_supervisor_cannot_export_guardian_phones(client_as, supervisor, absent_both):
    # يرى المشرفُ شاشةَ جناحه، أمّا ملفٌّ فيه هواتفُ الأولياء فلحَمَلة قدرة الطباعة وحدَهم (D-171م)
    for name in ("absence_followup_xlsx", "absence_followup_pdf"):
        resp = client_as(supervisor).get(reverse(name), {"date": SUNDAY.isoformat()})
        assert resp.status_code == 403

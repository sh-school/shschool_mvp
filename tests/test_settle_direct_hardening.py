"""تقويةُ أمر التسوية وتقريرُ فرق الأرقام (D-271م، S3): نافذةُ تواريخ، تخطّي المتعارض بدل الإجهاض، التقاطُ كلّ خطأ لإدخاله وحدَه، سطرُ تدقيقٍ بالمعرّفات، وتقريرٌ قراءةٌ فقط."""

import datetime as dt
import io
from unittest.mock import patch

import pytest
from django.core.management import call_command

from core.models import AuditLog
from operations import attendance_entries
from operations.attendance_entries import settle_pending
from operations.models import AttendanceDecision, AttendanceEntry, StudentAttendance
from operations.services import class_grid as grid
from operations.settlement_diff import diff_report
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import at
from tests.test_class_grid import _grid_on, assigned, clock, kids, subject  # noqa: F401

pytestmark = pytest.mark.django_db


def _write_all(user, school, klass, kids, status="absent", number=1):
    return grid.save_column(
        user,
        school,
        klass.id,
        number,
        [{"student": str(k.pk), "status": status, "head": ""} for k in kids],
        now=at(9, 0),
    )


@pytest.fixture
def pending(school, assigned, teacher, kids, clock):
    """ثلاثةُ إدخالاتٍ معلَّقةٍ كالتي بقيت من الاعتماد القديم: الكتابةُ الفوريّةُ معطَّلةٌ وقتَ الإنشاء فلا قرارَ لها."""
    with patch.object(attendance_entries, "_decide_directly"):
        _write_all(teacher, school, assigned, kids)
    assert AttendanceEntry.objects.count() == 3 and not AttendanceDecision.objects.exists()
    return list(AttendanceEntry.objects.order_by("entered_at"))


def test_count_reports_the_conflict_in_advance_and_writes_nothing(school, pending, kids, teacher):
    blocked = pending[1]
    StudentAttendance.objects.create(
        session=blocked.session,
        student=blocked.student,
        school=school,
        status="present",
        source="supervisor",
    )

    report = settle_pending(school)

    assert (report.eligible, len(report.conflicts), report.to_settle) == (3, 1, 2)
    assert report.conflicts == [str(blocked.pk)]
    assert not AttendanceDecision.objects.exists(), "العدُّ لا يكتب"


def test_apply_skips_the_conflict_and_settles_the_rest_without_aborting(school, pending):
    blocked = pending[1]
    StudentAttendance.objects.create(
        session=blocked.session,
        student=blocked.student,
        school=school,
        status="present",
        source="supervisor",
    )

    report = settle_pending(school, apply=True)

    assert (report.settled, len(report.conflicts), report.errors) == (2, 1, [])
    assert AttendanceDecision.objects.count() == 2
    assert not AttendanceDecision.objects.filter(entry=blocked).exists(), "المتعارضُ لم يُكتب فوقه"
    audit = AuditLog.objects.get(object_repr__contains="تسويةٌ جماعيّةٌ")
    assert audit.changes["settled"] == 2 and audit.changes["conflict_ids"] == [str(blocked.pk)]


def test_an_unexpected_error_on_one_entry_does_not_stop_the_others(school, pending):
    real = attendance_entries._decide
    bad = pending[0]

    def flaky(entry, *args, **kwargs):
        if entry.pk == bad.pk:
            raise RuntimeError("boom")
        return real(entry, *args, **kwargs)

    with patch.object(attendance_entries, "_decide", flaky):
        report = settle_pending(school, apply=True)

    assert report.settled == 2 and report.errors == [str(bad.pk)]
    assert AttendanceDecision.objects.count() == 2


def test_the_date_window_limits_what_is_settled(school, pending):
    day = pending[0].session.date
    far = day + dt.timedelta(days=10)

    inside = settle_pending(school, since=day, until=day)
    outside = settle_pending(school, since=far)

    assert inside.eligible == 3 and outside.eligible == 0
    assert settle_pending(school, apply=True, since=far).settled == 0
    assert not AttendanceDecision.objects.exists()


def test_the_command_counts_by_default_and_writes_ids_only_to_the_file(school, pending, tmp_path):
    blocked = pending[1]
    StudentAttendance.objects.create(
        session=blocked.session,
        student=blocked.student,
        school=school,
        status="present",
        source="supervisor",
    )
    out = io.StringIO()
    ids = tmp_path / "ids.txt"

    call_command(
        "settle_direct_entries", "--since", "2000-01-01", "--ids-out", str(ids), stdout=out
    )

    text = out.getvalue()
    assert "عدٌّ فقط" in text and "مؤهَّل 3" in text and "سيُسوّى فعلاً 2" in text
    assert str(blocked.pk) in ids.read_text(encoding="utf-8")
    assert not AttendanceDecision.objects.exists()
    for bad in (blocked.student.full_name,):
        assert bad not in text and bad not in ids.read_text(encoding="utf-8")


def test_the_diff_report_is_read_only_and_counts_what_would_be_added(school, pending):
    rows_before = StudentAttendance.objects.count()
    decisions_before = AttendanceDecision.objects.count()

    data = diff_report(school)

    assert StudentAttendance.objects.count() == rows_before, "قراءةٌ فقط"
    assert AttendanceDecision.objects.count() == decisions_before
    assert data["eligible"] == 3 and data["conflicts_skipped"] == 0
    assert data["rows_added"] == {"absent": 3}
    assert data["students_with_entries"] == 3
    assert (
        sum(sum(c.values()) for w in data["by_day_wing_status"].values() for c in w.values()) == 3
    )


def test_the_diff_report_command_prints_both_scenarios_without_names(school, pending, tmp_path):
    out = io.StringIO()
    path = tmp_path / "diff.json"

    call_command("settlement_diff_report", "--since", "2000-01-01", "--out", str(path), stdout=out)

    text = out.getvalue()
    assert "[كلُّ التواريخ]" in text and "[من 2000-01-01]" in text
    names = [p.student.full_name for p in pending]
    assert not any(name in text or name in path.read_text(encoding="utf-8") for name in names)
    assert not AttendanceDecision.objects.exists()

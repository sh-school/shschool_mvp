"""جدولُ الشعبة العموديّ لرصد الغياب (W-20261006-005، قرارا المالك D-238م–D-240م): الصلاحيةُ من الإسناد، حصّةُ العمود عند أوّل حفظ،
الحالةُ الصريحةُ و`expected_head`، الفارغُ حاضراً، النافذةُ بتوقيت المدرسة، المفتاحُ مطفأً 404، وعدُّ الاستعلامات.

الزمنُ مثبَّتٌ بـfixture مصنوعٍ (`clock`) فلا يعتمد الاختبارُ ساعةَ التشغيل أبداً.
"""

import datetime as dt
import json

import pytest
from django.db import IntegrityError, connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from core.models import AuditLog
from operations.attendance_entries import EntryRefusedError, submit_entry
from operations.attendance_policy import (
    can_correct_grid,
    can_read_grid,
    can_write_grid,
    grid_window,
)
from operations.models import AttendanceEntry, Session, Subject, SubjectClassAssignment
from operations.services import class_grid as grid
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import ENROLLED, SUNDAY, _staff, at
from tests.conftest import ClassGroupFactory, StudentEnrollmentFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def clock(monkeypatch):
    """ساعةٌ مثبَّتةٌ قابلةٌ للتحريك: الأحد 09:00 بتوقيت الدوحة (بعد ح1 و ح2 وقبل ح3 12:45)."""
    state = {"now": at(9, 0)}
    monkeypatch.setattr(timezone, "now", lambda: state["now"])

    def move(hour, minute=0):
        state["now"] = at(hour, minute)

    return move


@pytest.fixture(autouse=True)
def _grid_on(settings):
    settings.PROVISIONAL_GRID_ENABLED = True


@pytest.fixture
def subject(school):
    return Subject.objects.create(school=school, name_ar="العلوم", code="SCI")


@pytest.fixture
def assigned(school, year, klass, teacher, subject, band, bells):
    """الشعبةُ بجرس ground ومعلّمٌ مُسنَدةٌ إليه (ح1 07:10 وح2 08:00 وح3 12:45)."""
    type(klass).objects.filter(pk=klass.pk).update(time_band=band)
    klass.refresh_from_db()
    SubjectClassAssignment.objects.create(
        school=school,
        class_group=klass,
        subject=subject,
        teacher=teacher,
        weekly_periods=2,
        academic_year=year,
    )
    return klass


@pytest.fixture
def kids(school, assigned):
    people = []
    for index in range(3):
        student = UserFactory(full_name=f"طالب {index}", national_id=f"2900000200{index}")
        StudentEnrollmentFactory(student=student, class_group=assigned, enrolled_at=ENROLLED)
        people.append(student)
    return people


def _cells(student, status, head=""):
    return {"student": str(student.pk), "status": status, "head": head}


def _save(client, klass, number, cells, **extra):
    return client.post(
        reverse("class_grid_save", args=[klass.id]),
        data=json.dumps({"period": number, "cells": cells, **extra}),
        content_type="application/json",
    )


# ── المفتاح: مطفأً لا شيء ──────────────────────────────────────────────────────


# ── العرض: لا حصّةَ عند العرض ──────────────────────────────────────────────────


def test_viewing_the_grid_creates_no_session_and_lists_the_roster(
    client_as, assigned, teacher, kids, clock
):
    response = client_as(teacher).get(reverse("class_grid", args=[assigned.id]))

    assert response.status_code == 200
    body = response.content.decode()
    assert all(student.full_name in body for student in kids)
    assert "ح1" in body and "ح2" in body and "ح3" in body
    assert not Session.objects.filter(provisional=True).exists()


def test_a_teacher_of_another_class_gets_404_on_read_and_write(
    client_as, school, year, band, assigned, other_teacher, kids, clock
):
    client = client_as(other_teacher)
    assert client.get(reverse("class_grid", args=[assigned.id])).status_code == 404
    assert _save(client, assigned, 1, [_cells(kids[0], "absent")]).status_code == 404
    assert (
        client.get(reverse("class_grid_history", args=[assigned.id, kids[0].pk, 1])).status_code
        == 404
    )
    assert not AttendanceEntry.objects.exists()


def test_the_developer_reaches_nothing(client_as, school, assigned, kids, clock):
    developer = _staff(school, "platform_developer", "المطوّر", "29000009999")
    client = client_as(developer)
    assert client.get(reverse("class_grid", args=[assigned.id])).status_code == 404
    assert _save(client, assigned, 1, [_cells(kids[0], "absent")]).status_code == 404


# ── الكتابة: حصّةُ العمود وحالةٌ صريحة ─────────────────────────────────────────


def test_the_first_save_creates_the_column_session_with_a_deterministic_assigned_teacher(
    client_as, school, assigned, teacher, holder, kids, clock
):
    client = client_as(holder)  # حاملُ الجناح (مشرفٌ إداريّ) يكتب ولا يصير Session.teacher
    response = _save(client, assigned, 1, [_cells(kids[0], "absent")])

    assert response.status_code == 200
    column = Session.objects.get(provisional=True)
    assert (column.teacher_id, column.period_number, column.date) == (teacher.id, 1, SUNDAY)
    assert (column.start_time, column.class_group_id) == (dt.time(7, 10), assigned.id)
    entry = AttendanceEntry.objects.get()
    assert (entry.entered_by_id, entry.status, entry.origin) == (holder.id, "absent", "grid")


def test_two_columns_of_one_writer_for_many_classes_do_not_collide(
    school, year, band, subject, assigned, teacher, bells, clock
):
    """لا قيدَ (معلّم، تاريخ، رقم) للمؤقّتة بعد 0073: كاتبٌ يحفظ ح1 لعدّة شعبٍ لا يصادم."""
    other = ClassGroupFactory(
        school=school,
        grade="G7",
        section="2",
        level_type="prep",
        academic_year=year,
        wing=assigned.wing,
        time_band=band,
    )
    SubjectClassAssignment.objects.create(
        school=school,
        class_group=other,
        subject=subject,
        teacher=teacher,
        weekly_periods=2,
        academic_year=year,
    )
    for klass in (assigned, other):
        student = UserFactory(
            full_name=f"ط {klass.section}", national_id=f"2900000300{klass.section}"
        )
        StudentEnrollmentFactory(student=student, class_group=klass, enrolled_at=ENROLLED)
        result = grid.save_column(
            teacher, school, klass.id, 1, [_cells(student, "absent")], now=at(9, 0)
        )
        assert len(result.saved) == 1
    assert Session.objects.filter(provisional=True, teacher=teacher, period_number=1).count() == 2


def test_the_provisional_class_period_constraint_carries_the_elective_group(
    school, assigned, teacher
):
    kwargs = {
        "school": school,
        "class_group": assigned,
        "teacher": teacher,
        "date": SUNDAY,
        "start_time": dt.time(7, 10),
        "end_time": dt.time(7, 55),
        "period_number": 1,
        "provisional": True,
    }
    Session.objects.create(**kwargs)
    Session.objects.create(**kwargs, elective_group="ب")  # مجموعةُ اختيارٍ أخرى: مسموح
    with pytest.raises(IntegrityError):
        Session.objects.create(**kwargs)


def test_a_column_that_has_not_started_is_refused_for_everyone(
    client_as, assigned, teacher, holder, kids, clock
):
    for who in (teacher, holder):
        response = _save(
            client_as(who), assigned, 3, [_cells(kids[0], "absent")]
        )  # ح3 12:45 والساعة 09:00
        assert response.status_code == 403 and response.json()["reason"] == "before_start"
    assert (
        not AttendanceEntry.objects.exists()
        and not Session.objects.filter(provisional=True).exists()
    )


def test_every_assigned_teacher_writes_every_started_column(
    client_as, school, year, subject, assigned, teacher, other_teacher, kids, clock
):
    """D-238م: معلّمو الإسناد يكتبون كلَّ الأعمدة — ولو كان معلّمُ ح2 غيرَ كاتب ح1."""
    SubjectClassAssignment.objects.create(
        school=school,
        class_group=assigned,
        subject=subject,
        teacher=other_teacher,
        weekly_periods=2,
        academic_year=year,
    )
    assert _save(client_as(teacher), assigned, 1, [_cells(kids[0], "absent")]).status_code == 200
    assert (
        _save(client_as(other_teacher), assigned, 1, [_cells(kids[1], "absent")]).status_code == 200
    )
    assert (
        _save(client_as(other_teacher), assigned, 2, [_cells(kids[0], "present")]).status_code
        == 200
    )
    assert AttendanceEntry.objects.filter(entered_by=other_teacher).count() == 2


def test_the_legacy_entry_path_still_refuses_a_non_session_teacher(
    school, year, subject, assigned, teacher, other_teacher, kids, clock
):
    """لا تخفيفَ لـ`can_enter`: معلّمٌ مُسنَدٌ لا يكتب بالمسار القديم في حصّةٍ ليست حصّتَه."""
    SubjectClassAssignment.objects.create(
        school=school,
        class_group=assigned,
        subject=subject,
        teacher=other_teacher,
        weekly_periods=2,
        academic_year=year,
    )
    result = grid.save_column(
        other_teacher, school, assigned.id, 1, [_cells(kids[0], "absent")], now=at(9, 0)
    )
    column = Session.objects.get(pk=result.session_id)
    assert column.teacher_id == other_teacher.id  # الكاتبُ مُسنَدٌ فهو Session.teacher
    with pytest.raises(EntryRefusedError) as refused:
        submit_entry(teacher, column, kids[1], "absent", now=at(9, 0))
    assert refused.value.reason == "not_teacher"


def test_unknown_or_foreign_students_are_rejected_by_the_server(
    client_as, school, assigned, teacher, kids, clock
):
    stranger = UserFactory(full_name="غريب", national_id="29000000091")
    response = _save(
        client_as(teacher), assigned, 1, [_cells(stranger, "absent"), _cells(kids[0], "absent")]
    )
    body = response.json()
    assert response.status_code == 207 and body["errors"][0]["code"] == "not_enrolled"
    assert AttendanceEntry.objects.count() == 1


def test_a_stale_expected_head_is_a_conflict_and_writes_nothing(
    client_as, school, assigned, teacher, other_teacher, year, subject, kids, clock
):
    SubjectClassAssignment.objects.create(
        school=school,
        class_group=assigned,
        subject=subject,
        teacher=other_teacher,
        weekly_periods=2,
        academic_year=year,
    )
    first = client_as(teacher)
    _save(first, assigned, 1, [_cells(kids[0], "absent")])
    head = str(AttendanceEntry.objects.get().pk)

    # آخرُ يصحّح الخليّةَ أوّلاً، ثمّ يأتي طلبٌ يحمل الرأسَ القديم
    assert (
        _save(
            client_as(other_teacher),
            assigned,
            1,
            [_cells(kids[0], "present", head)],
            reason="تصحيحٌ",
        ).status_code
        == 200
    )
    stale = _save(first, assigned, 1, [_cells(kids[0], "late", head)])

    body = stale.json()
    assert stale.status_code == 207 and len(body["conflicts"]) == 1
    assert (
        body["conflicts"][0]["status"] == "present"
        and body["conflicts"][0]["by"] == other_teacher.full_name
    )
    assert AttendanceEntry.objects.count() == 2  # لا صفَّ ثالث


def test_retrying_the_same_request_does_not_create_a_second_row(
    client_as, assigned, teacher, kids, clock
):
    client = client_as(teacher)
    _save(client, assigned, 1, [_cells(kids[0], "absent")])
    again = _save(
        client, assigned, 1, [_cells(kids[0], "absent")]
    )  # الرأسُ نفسُه القديم والقيمةُ نفسُها
    assert again.status_code == 200 and AttendanceEntry.objects.count() == 1


def test_changing_a_cell_supersedes_the_head_with_a_fixed_reason(
    client_as, assigned, teacher, kids, clock
):
    client = client_as(teacher)
    _save(client, assigned, 1, [_cells(kids[0], "absent")])
    head = str(AttendanceEntry.objects.get().pk)
    _save(client, assigned, 1, [_cells(kids[0], "present", head)])

    rows = list(AttendanceEntry.objects.order_by("entered_at"))
    assert (
        len(rows) == 2
        and rows[1].supersedes_id == rows[0].pk
        and rows[1].correction_reason == "تعديلٌ من جدول الشعبة"
    )


def test_the_save_is_per_cell_a_conflict_does_not_lose_the_rest(
    client_as, assigned, teacher, kids, clock
):
    client = client_as(teacher)
    _save(client, assigned, 1, [_cells(kids[0], "absent")])
    mixed = _save(
        client,
        assigned,
        1,
        [
            _cells(kids[0], "present", "00000000-0000-0000-0000-000000000000"),
            _cells(kids[1], "absent"),
        ],
    )
    body = mixed.json()
    assert mixed.status_code == 207 and len(body["saved"]) == 1 and len(body["conflicts"]) == 1


# ── الفارغُ حاضراً ─────────────────────────────────────────────────────────────


def test_empty_cells_become_default_present_only_when_the_column_is_saved_with_fill(
    client_as, assigned, teacher, kids, clock
):
    client = client_as(teacher)
    plain = _save(client, assigned, 1, [_cells(kids[0], "absent")])
    assert plain.json()["defaults"] == 0 and AttendanceEntry.objects.count() == 1

    filled = _save(client, assigned, 2, [_cells(kids[0], "absent")], fill_empty=True)
    assert filled.json()["defaults"] == 2
    defaults = AttendanceEntry.objects.filter(origin="grid_default")
    assert defaults.count() == 2 and all(e.status == "present" for e in defaults)
    audit = AuditLog.objects.filter(object_repr="جدول الشعبة — حفظُ عمود", changes__period=2).get()
    assert audit.changes["default_present"] == 2 and "full_name" not in json.dumps(audit.changes)


def test_fixing_a_default_present_uses_the_fixed_central_reason(
    client_as, assigned, teacher, kids, clock
):
    client = client_as(teacher)
    _save(client, assigned, 1, [], fill_empty=True)
    default = AttendanceEntry.objects.filter(student=kids[0]).get()
    _save(client, assigned, 1, [_cells(kids[0], "absent", str(default.pk))])
    fix = AttendanceEntry.objects.get(supersedes=default)
    assert fix.correction_reason == "تصحيحُ حاضرٍ افتراضيّ" and fix.origin == "grid"


# ── النافذة بتوقيت المدرسة ─────────────────────────────────────────────────────


def test_the_window_is_central_07_10_to_14_00(school):
    opens, closes = grid_window(SUNDAY)
    assert (opens, closes) == (at(7, 10), at(14, 0))


def test_before_the_window_opens_no_one_writes(client_as, assigned, teacher, kids, clock):
    clock(7, 0)
    response = _save(client_as(teacher), assigned, 1, [_cells(kids[0], "absent")])
    assert response.status_code == 403 and response.json()["reason"] in {
        "before_window",
        "before_start",
    }


def test_after_14_00_the_teacher_is_locked_and_the_holder_corrects_with_a_reason(
    client_as, assigned, teacher, holder, kids, clock
):
    client_as_teacher = client_as(teacher)
    _save(client_as_teacher, assigned, 1, [_cells(kids[0], "absent")])
    head = str(AttendanceEntry.objects.get().pk)
    clock(14, 30)

    locked = _save(client_as_teacher, assigned, 1, [_cells(kids[0], "present", head)])
    assert locked.status_code == 403 and locked.json()["reason"] == "after_window"

    boss = client_as(holder)
    # السببُ اختياريّ (قرارُ المالك 2026-10-09): يكفي كاتبُ التصحيح ووقتُه، ويُوضع سببٌ ثابتٌ إن لم يُكتب
    fixed = _save(boss, assigned, 1, [_cells(kids[0], "present", head)])
    assert fixed.status_code == 200
    mine = AttendanceEntry.objects.get(entered_by=holder)
    assert mine.correction_reason == "تعديلٌ من جدول الشعبة" and mine.entered_at
    assert AuditLog.objects.filter(object_repr="جدول الشعبة — تصحيحٌ بعد الإغلاق").exists()


# ── الأدوار ────────────────────────────────────────────────────────────────────


def test_the_date_is_doha_not_utc_for_the_teacher_write(
    client_as, assigned, teacher, kids, clock, monkeypatch
):
    """يعادل حارسَ ملكيّة الحصّة القديم: 21:30 UTC من الأحد = 00:30 من الاثنين بالدوحة، فيومُ الأحد مضى والمعلّمُ لا يكتبه (W-20261002-026)."""
    late = dt.datetime(2026, 9, 13, 21, 30, tzinfo=dt.UTC)
    monkeypatch.setattr(timezone, "now", lambda: late)

    response = _save(
        client_as(teacher),
        assigned,
        1,
        [_cells(kids[0], "absent")],
        date=SUNDAY.isoformat(),
    )

    assert response.status_code == 403
    assert not AttendanceEntry.objects.exists()


def test_the_academic_deputy_reads_but_never_writes(client_as, school, assigned, kids, clock):
    deputy = _staff(school, "vice_academic", "النائب الأكاديميّ", "29000001030")
    client = client_as(deputy)
    assert client.get(reverse("class_grid", args=[assigned.id])).status_code == 200
    refused = _save(client, assigned, 1, [_cells(kids[0], "absent")])
    assert refused.status_code == 403 and refused.json()["reason"] == "read_only"
    assert not AttendanceEntry.objects.exists()


@pytest.mark.parametrize("role", ["principal", "vice_admin", "admin_supervisor"])
def test_the_administrative_leadership_writes_every_column(
    client_as, school, assigned, kids, clock, role
):
    boss = _staff(school, role, f"قيادة {role}", f"2900000{abs(hash(role)) % 10**4:04d}01")
    assert _save(client_as(boss), assigned, 2, [_cells(kids[0], "absent")]).status_code == 200


def test_the_policy_units(school, assigned, teacher, other_teacher, holder, clock):
    assert can_read_grid(teacher, assigned, SUNDAY) and not can_read_grid(
        other_teacher, assigned, SUNDAY
    )
    assert can_write_grid(teacher, assigned, SUNDAY, now=at(9, 0))
    assert (
        can_write_grid(teacher, assigned, SUNDAY, period_start=dt.time(12, 45), now=at(9, 0)).reason
        == "before_start"
    )
    assert can_write_grid(teacher, assigned, SUNDAY, now=at(14, 1)).reason == "after_window"
    assert (
        can_write_grid(teacher, assigned, SUNDAY, now=at(9, 0) + dt.timedelta(days=1)).reason
        == "not_today"
    )
    assert not can_correct_grid(teacher, assigned, SUNDAY, now=at(15, 0))
    assert can_correct_grid(holder, assigned, SUNDAY, now=at(15, 0))


# ── المتأخّر: الحصّةُ الجارية وقتَ الضغط ─────────────────────────────────────────


def test_late_is_attributed_to_the_current_period_at_the_press(
    client_as, assigned, teacher, kids, clock
):
    clock(7, 30)  # ح1 جاريةٌ (07:10–07:55)
    client = client_as(teacher)
    response = client.post(
        reverse("class_grid_late", args=[assigned.id]), {"student": str(kids[0].pk)}
    )
    assert response.status_code == 200
    entry = AttendanceEntry.objects.get()
    assert (entry.status, entry.session.period_number) == (
        "late",
        1,
    ) and entry.tardiness_minutes == 20


def test_late_with_no_current_period_is_refused(client_as, assigned, teacher, kids, clock):
    clock(10, 0)  # بين ح2 وح3: لا حصّةَ جاريةً
    response = client_as(teacher).post(
        reverse("class_grid_late", args=[assigned.id]), {"student": str(kids[0].pk)}
    )
    assert response.status_code == 403 and response.json()["reason"] == "no_current_period"


# ── سجلُّ الخليّة والأداء ──────────────────────────────────────────────────────


def test_the_cell_history_shows_who_wrote_and_who_corrected(
    client_as, assigned, teacher, holder, kids, clock
):
    _save(client_as(teacher), assigned, 1, [_cells(kids[0], "absent")])
    head = str(AttendanceEntry.objects.get().pk)
    _save(client_as(holder), assigned, 1, [_cells(kids[0], "present", head)], reason="تصحيحٌ")

    body = (
        client_as(holder)
        .get(reverse("class_grid_history", args=[assigned.id, kids[0].pk, 1]))
        .content.decode()
    )
    assert teacher.full_name in body and holder.full_name in body and "صُحِّح" in body


def test_the_read_query_count_is_flat_in_the_number_of_students(
    client_as, school, assigned, teacher, clock
):
    """عدُّ الاستعلامات ثابتٌ بعدد الطلبة: شعبةٌ بـ30 ثمّ بـ60 تُقرأ بالعدد نفسِه، وتحت حدٍّ مطلق (خطُّ أساسٍ مقيس: 36 بعد استعلام تغطية البديل)."""

    def measure():
        with CaptureQueriesContext(connection) as queries:
            assert (
                client_as(teacher).get(reverse("class_grid", args=[assigned.id])).status_code == 200
            )
        return len(queries)

    def enroll(start, stop):
        for index in range(start, stop):
            student = UserFactory(full_name=f"ط{index:03d}", national_id=f"2900{index:07d}")
            StudentEnrollmentFactory(student=student, class_group=assigned, enrolled_at=ENROLLED)

    enroll(0, 30)
    measure()  # تسخينٌ: ذاكرةُ التقويم وما يُحسب مرّةً لا يُحسب في القياس
    thirty = measure()
    enroll(30, 60)
    sixty = measure()
    assert thirty == sixty and thirty <= 37, (thirty, sixty)


# ── «اطفئ الشبكة»: مع المفتاح لا يُفتح كشفُ الحصّة القديم لمن يملك الجدول ───────────


# ── خروجُ الطالب من الفصل: بمسار ClassExit القائم، في الحصّة الجارية وقتَ الضغط ─────────


def _exit(client, klass, student, **data):
    return client.post(
        reverse("class_grid_exit", args=[klass.id]), {"student": str(student.pk), **data}
    )


def test_the_exit_button_opens_a_class_exit_in_the_current_period_with_a_destination(
    client_as, assigned, teacher, kids, clock
):
    from operations.models import ClassExit

    clock(7, 30)  # ح1 جاريةٌ
    response = _exit(client_as(teacher), assigned, kids[0], action="leave", destination="clinic")

    assert response.status_code == 200
    exit_ = ClassExit.objects.get()
    assert (exit_.destination, exit_.student_id, exit_.session.period_number) == (
        "clinic",
        kids[0].pk,
        1,
    )
    assert exit_.allowed_by_id == teacher.id and exit_.returned_at is None


def test_the_return_button_closes_the_open_exit(client_as, assigned, teacher, kids, clock):
    from operations.models import ClassExit

    clock(7, 30)
    client = client_as(teacher)
    _exit(client, assigned, kids[0], action="leave", destination="restroom")
    clock(7, 40)
    assert _exit(client, assigned, kids[0], action="return").json()["returned"] is True
    assert ClassExit.objects.get().returned_at is not None


def test_an_unknown_destination_becomes_other(client_as, assigned, teacher, kids, clock):
    from operations.models import ClassExit

    clock(7, 30)
    _exit(client_as(teacher), assigned, kids[0], action="leave", destination="mars")
    assert ClassExit.objects.get().destination == "other"


def test_a_student_marked_absent_cannot_leave(client_as, assigned, teacher, kids, clock):
    clock(7, 30)
    client = client_as(teacher)
    _save(client, assigned, 1, [_cells(kids[0], "absent")])
    response = _exit(client, assigned, kids[0], action="leave", destination="clinic")
    assert response.status_code == 403 and response.json()["reason"] == "student_absent"


def test_the_exit_needs_a_current_period_and_a_writer(
    client_as, school, assigned, teacher, kids, clock
):
    client = client_as(teacher)
    clock(10, 0)  # بين الحصّتين
    assert _exit(client, assigned, kids[0], action="leave").json()["reason"] == "no_current_period"
    clock(7, 30)
    deputy = _staff(school, "vice_academic", "النائب الأكاديميّ", "29000001030")
    refused = _exit(client_as(deputy), assigned, kids[0], action="leave")
    assert refused.status_code == 403 and refused.json()["reason"] == "read_only"


def test_the_page_shows_the_open_exit_and_the_destination_list(
    client_as, assigned, teacher, kids, clock
):
    clock(7, 30)
    client = client_as(teacher)
    _exit(client, assigned, kids[0], action="leave", destination="clinic")
    body = client.get(reverse("class_grid", args=[assigned.id])).content.decode()
    i = body.find("cg-acts", body.find("<tbody"))
    assert "خارج: العيادة" in body, body[i : i + 900]
    assert "دورة المياه" in body and "data-exit-return" in body


# ── ساعةُ المعاينة المفترَضة: DEBUG وحدَه ─────────────────────────────────────────


def test_the_fake_clock_works_only_with_debug_on(
    settings, client_as, assigned, teacher, kids, monkeypatch
):
    """`ATTENDANCE_GRID_FAKE_TIME` يقدّم الساعةَ للمعاينة وحدَها: مع DEBUG مطفأٍ لا أثرَ له (إنتاجٌ بمتغيّرٍ خاطئٍ لا يفتح الجدولَ ليلاً)."""
    monkeypatch.setattr(timezone, "now", lambda: at(2, 0))  # الثانية فجراً: خارجَ النافذة
    settings.ATTENDANCE_GRID_FAKE_TIME = "07:11"
    client = client_as(teacher)

    settings.DEBUG = False
    refused = _save(client, assigned, 1, [_cells(kids[0], "absent")])
    assert refused.status_code == 403 and refused.json()["reason"] == "before_window"

    settings.DEBUG = True
    accepted = _save(client, assigned, 1, [_cells(kids[0], "absent")])
    assert accepted.status_code == 200 and AttendanceEntry.objects.count() == 1


def test_a_student_corrected_to_present_can_leave(client_as, assigned, teacher, kids, clock):
    clock(7, 30)
    client = client_as(teacher)
    _save(client, assigned, 1, [_cells(kids[0], "absent")])
    head = AttendanceEntry.objects.get(student=kids[0]).pk
    _save(client, assigned, 1, [_cells(kids[0], "present", str(head))])
    response = _exit(client, assigned, kids[0], action="leave", destination="clinic")
    assert response.status_code == 200, response.content


# ── منقولٌ من tests/test_mark_single_ownership.py (حُذف مسارُ mark_single في 21aeeecbd) بالأسماء نفسِها ──────────────
# الحارسُ كان: «معلّمُ الحصّة وحدَه، داخل النافذة، بتوقيت الدوحة، والمطوّرُ لا يُدخل، والتدقيقُ بالقيمتين». ينتقل إلى الجدول.


def test_the_session_teacher_marks_inside_the_window(client_as, assigned, teacher, kids, clock):
    response = _save(client_as(teacher), assigned, 1, [_cells(kids[0], "absent")])
    assert response.status_code == 200
    row = AttendanceEntry.objects.get(student=kids[0])
    assert (row.status, row.entered_by_id) == ("absent", teacher.id)


def test_another_teacher_may_not_mark_a_colleagues_session(
    client_as, assigned, other_teacher, kids, clock
):
    """الثغرةُ بعينها: زميلٌ يحمل attendance.mark يكتب حصّةَ غيره."""
    response = _save(client_as(other_teacher), assigned, 1, [_cells(kids[0], "absent")])
    assert response.status_code in (403, 404)
    assert not AttendanceEntry.objects.exists()


def test_a_coordinator_who_is_not_the_session_teacher_may_not_mark(
    client_as, school, assigned, kids, clock
):
    coordinator = _staff(school, "coordinator", "منسّق", "29000004012")
    response = _save(client_as(coordinator), assigned, 1, [_cells(kids[0], "absent")])
    assert response.status_code in (403, 404)
    assert not AttendanceEntry.objects.exists()


def test_the_teacher_may_not_mark_before_the_session_starts(
    client_as, assigned, teacher, kids, clock
):
    clock(7, 9)
    response = _save(client_as(teacher), assigned, 1, [_cells(kids[0], "absent")])
    assert response.status_code == 403
    assert not AttendanceEntry.objects.exists()


def test_the_teacher_may_not_mark_after_the_window_closes(
    client_as, assigned, teacher, kids, clock
):
    clock(14, 1)
    response = _save(client_as(teacher), assigned, 1, [_cells(kids[0], "absent")])
    assert response.status_code == 403
    assert not AttendanceEntry.objects.exists()


def test_the_teacher_may_not_mark_the_next_day(client_as, assigned, teacher, kids, monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: at(9, 0, day=SUNDAY + dt.timedelta(days=1)))
    response = _save(
        client_as(teacher), assigned, 1, [_cells(kids[0], "absent")], date=SUNDAY.isoformat()
    )
    assert response.status_code == 403
    assert not AttendanceEntry.objects.exists()


def test_a_cancelled_session_may_not_be_marked(client_as, assigned, teacher, kids, clock):
    """الحصّةُ الملغاةُ لا تُرصد: عمودٌ حصّتُه ملغاةٌ يرفضه الخادم."""
    Session.objects.create(
        school=assigned.school,
        class_group=assigned,
        teacher=teacher,
        date=SUNDAY,
        start_time=dt.time(7, 10),
        end_time=dt.time(7, 55),
        period_number=1,
        status="cancelled",
        provisional=True,
    )
    response = _save(client_as(teacher), assigned, 1, [_cells(kids[0], "absent")])
    assert response.status_code != 200
    assert not AttendanceEntry.objects.exists()


def test_recorders_still_mark_any_wingless_session(client_as, school, assigned, kids, clock):
    """أهلُ الرصد غيرُ المقيَّدين بجناحٍ (النائبُ الإداريّ والمدير) يكتبون العمودَ بلا قيدِ معلّم الحصّة."""
    for kid, (role, nid) in zip(
        kids, (("vice_admin", "29000004021"), ("principal", "29000004023")), strict=False
    ):
        recorder = _staff(school, role, role, nid)
        response = _save(client_as(recorder), assigned, 1, [_cells(kid, "present")])
        assert response.status_code == 200, role


def test_the_developer_may_not_mark_even_as_a_superuser(client_as, school, assigned, kids, clock):
    """D-128م: المطوّرُ لا يُدخل ولو كان superuser."""
    developer = _staff(school, "platform_developer", "المطوّر", "29000004030")
    developer.is_superuser = True
    developer.save(update_fields=["is_superuser"])
    response = _save(client_as(developer), assigned, 1, [_cells(kids[0], "absent")])
    assert response.status_code in (403, 404)
    assert not AttendanceEntry.objects.exists()


def test_the_teachers_changes_are_audited_with_before_and_after(
    client_as, assigned, teacher, kids, clock
):
    """رصدُ المعلّم نهائيٌّ **بتدقيقٍ كامل**: كلُّ تغييرٍ إدخالٌ مُلحَق بالقيمتين، وسجلُّ التدقيق بالمعرّفات لا الأسماء."""
    client = client_as(teacher)
    first = _save(client, assigned, 1, [_cells(kids[0], "absent")])
    assert first.status_code == 200
    head = str(AttendanceEntry.objects.get(student=kids[0]).pk)
    _save(client, assigned, 1, [_cells(kids[0], "present", head)])
    rows = {row.pk: row for row in AttendanceEntry.objects.filter(student=kids[0])}
    root = next(row for row in rows.values() if row.supersedes_id is None)
    chain = [root, next(row for row in rows.values() if row.supersedes_id == root.pk)]
    assert [row.status for row in chain] == ["absent", "present"]
    assert chain[1].supersedes_id == chain[0].pk
    assert all(row.entered_by_id == teacher.id for row in chain)
    lines = list(AuditLog.objects.filter(model_name="other", user=teacher))
    assert lines
    assert all(kids[0].full_name not in str(line.changes) for line in lines)


def test_a_recorders_marking_is_not_double_audited_by_this_path(
    client_as, school, assigned, kids, clock
):
    """كاتبٌ واحدٌ لكلّ إدخال: أهلُ الرصد يكتبون بإدخالٍ واحدٍ لا بإدخالين."""
    recorder = _staff(school, "vice_admin", "النائب", "29000004031")
    _save(client_as(recorder), assigned, 1, [_cells(kids[0], "present")])
    assert AttendanceEntry.objects.filter(student=kids[0], entered_by=recorder).count() == 1


# ── التغطية بالتبديل والتعويض (W-20261002-017، D-125م) ───────────────────────────────────────────


@pytest.fixture
def lesson_slot(school, assigned, teacher, subject):
    from operations.models import ScheduleSlot

    return ScheduleSlot.objects.create(
        school=school,
        teacher=teacher,
        class_group=assigned,
        subject=subject,
        day_of_week=0,
        period_number=1,
        start_time=dt.time(7, 10),
        end_time=dt.time(7, 55),
        academic_year=assigned.academic_year
        if isinstance(assigned.academic_year, str)
        else str(assigned.academic_year),
    )


def _swap(school, lesson_slot, mine, theirs, **extra):
    from operations.models import TeacherSwap

    return TeacherSwap.objects.create(
        school=school,
        teacher_a=mine,
        teacher_b=theirs,
        slot_a=lesson_slot,
        slot_b=lesson_slot,
        swap_date_a=extra.pop("swap_date_a", SUNDAY),
        swap_date_b=extra.pop("swap_date_b", SUNDAY),
        status=extra.pop("status", "executed"),
        **extra,
    )


def test_a_teacher_a_swapped_in_for_today_writes_the_class_column(
    client_as, school, assigned, teacher, kids, lesson_slot, clock
):
    """`teacher_b` يأخذ حصّةَ `slot_a` يومَ `swap_date_a`: يكتب عمودَ الشعبة، ولا يكتب في غير يومه ولا قبل التنفيذ."""
    stranger = _staff(school, "teacher", "معلّمٌ بُدِّلت إليه", "29000007001")
    client = client_as(stranger)
    assert client.get(reverse("class_grid", args=[assigned.id])).status_code == 404
    swap = _swap(school, lesson_slot, teacher, stranger, status="approved")
    assert _save(client, assigned, 1, [_cells(kids[0], "absent")]).status_code == 404
    swap.status = "executed"
    swap.save(update_fields=["status"])
    assert _save(client, assigned, 1, [_cells(kids[0], "absent")]).status_code == 200
    swap.swap_date_a = SUNDAY + dt.timedelta(days=7)
    swap.save(update_fields=["swap_date_a"])
    assert _save(client, assigned, 1, [_cells(kids[1], "absent")]).status_code == 404


def test_the_requester_takes_the_payback_slot_on_the_second_date(
    client_as, school, assigned, teacher, kids, lesson_slot, clock
):
    """`teacher_a` يأخذ حصّةَ `slot_b` يومَ `swap_date_b` (وليس يومَ `swap_date_a`)."""
    away = _staff(school, "teacher", "طالبُ التبديل", "29000007002")
    _swap(school, lesson_slot, away, teacher, swap_date_a=SUNDAY - dt.timedelta(days=1))
    client = client_as(away)
    assert _save(client, assigned, 1, [_cells(kids[0], "absent")]).status_code == 200


def test_an_approved_or_completed_compensatory_session_covers_only_its_date(
    client_as, school, assigned, teacher, kids, subject, clock
):
    from operations.models import CompensatorySession, ScheduleSlot, TeacherAbsence

    owner = _staff(school, "teacher", "صاحبُ التعويض", "29000007003")
    slot = ScheduleSlot.objects.create(
        school=school,
        teacher=owner,
        class_group=assigned,
        subject=subject,
        day_of_week=0,
        period_number=2,
        start_time=dt.time(8, 0),
        end_time=dt.time(8, 45),
        academic_year=str(assigned.academic_year),
    )
    absence = TeacherAbsence.objects.create(school=school, teacher=owner, date=SUNDAY)
    session = CompensatorySession.objects.create(
        school=school,
        teacher=owner,
        original_slot=slot,
        absence=absence,
        compensatory_date=SUNDAY,
        compensatory_period=2,
        class_group=assigned,
        subject=subject,
        status="pending",
    )
    client = client_as(owner)
    for refused in ("colleague", "pending", "cancelled", "expired"):
        session.status = refused
        session.save(update_fields=["status"])
        assert client.get(reverse("class_grid", args=[assigned.id])).status_code == 404, refused
    for allowed in ("approved", "completed"):
        session.status = allowed
        session.save(update_fields=["status"])
        assert client.get(reverse("class_grid", args=[assigned.id])).status_code == 200, allowed
    session.compensatory_date = SUNDAY + dt.timedelta(days=7)
    session.save(update_fields=["compensatory_date"])
    assert client.get(reverse("class_grid", args=[assigned.id])).status_code == 404


def test_a_substitute_still_covers_and_the_other_roles_are_unchanged(
    client_as, school, assigned, teacher, other_teacher, holder, kids, lesson_slot, clock
):
    from operations.models import SubstituteAssignment, TeacherAbsence

    absence = TeacherAbsence.objects.create(school=school, teacher=teacher, date=SUNDAY)
    SubstituteAssignment.objects.create(
        school=school,
        absence=absence,
        slot=lesson_slot,
        substitute=other_teacher,
        status="assigned",
    )
    assert (
        _save(client_as(other_teacher), assigned, 1, [_cells(kids[0], "absent")]).status_code == 200
    )
    # الدور الأصليّ باقٍ (D-238م: كلُّ معلّمي الإسناد يكتبون كلَّ الأعمدة)
    assert _save(client_as(teacher), assigned, 1, [_cells(kids[1], "absent")]).status_code == 200
    assert can_correct_grid(holder, assigned, SUNDAY, now=at(15, 0))
    assert not can_correct_grid(other_teacher, assigned, SUNDAY, now=at(15, 0))


def test_the_coverage_lookup_adds_a_flat_number_of_queries(
    school, assigned, teacher, lesson_slot, clock
):
    from operations.attendance_policy import is_covering_class

    stranger = _staff(school, "teacher", "غريب", "29000007004")
    with CaptureQueriesContext(connection) as queries:
        assert not is_covering_class(stranger, assigned, SUNDAY)
    assert len(queries) <= 3

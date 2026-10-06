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
from operations.services import provisional_session as provisional
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


def test_with_the_switch_off_every_route_is_404(
    client_as, settings, assigned, teacher, kids, clock
):
    settings.PROVISIONAL_GRID_ENABLED = False
    client = client_as(teacher)
    assert client.get(reverse("class_grid", args=[assigned.id])).status_code == 404
    assert _save(client, assigned, 1, [_cells(kids[0], "absent")]).status_code == 404
    assert (
        client.post(
            reverse("class_grid_late", args=[assigned.id]), {"student": str(kids[0].pk)}
        ).status_code
        == 404
    )
    url = reverse("class_grid_history", args=[assigned.id, kids[0].pk, 1])
    assert client.get(url).status_code == 404
    assert not Session.objects.filter(provisional=True).exists()


def test_the_provisional_picker_swaps_with_the_grid(client_as, settings, assigned, teacher, clock):
    """تبادلٌ: المفتاحُ يشغّل الجدولَ ويُخفي المنتقي (404 للمنتقي)."""
    client = client_as(teacher)
    assert client.get(reverse("provisional_class", args=[assigned.id])).status_code == 404
    assert client.get(reverse("provisional_classes")).status_code == 200


def test_the_legacy_key_is_a_temporary_alias_until_the_new_one_is_set(settings):
    settings.PROVISIONAL_GRID_ENABLED = False
    settings.PROVISIONAL_GRID_ENABLED_SET = False
    settings.PROVISIONAL_SESSIONS_ENABLED = True
    assert (
        provisional.enabled() is True
        and provisional.picker_enabled() is True
        and not provisional.grid_enabled()
    )
    settings.PROVISIONAL_GRID_ENABLED_SET = True  # ضُبط الجديدُ صراحةً (ولو بصفر) فلا يُقرأ المهجور
    assert provisional.enabled() is False


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
        _save(client_as(other_teacher), assigned, 1, [_cells(kids[0], "present", head)]).status_code
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
    no_reason = _save(boss, assigned, 1, [_cells(kids[0], "present", head)])
    assert no_reason.status_code == 403 and no_reason.json()["reason"] == "reason_required"
    fixed = _save(
        boss, assigned, 1, [_cells(kids[0], "present", head)], reason="وصل متأخّراً وأُثبت حضورُه"
    )
    assert fixed.status_code == 200
    assert AttendanceEntry.objects.filter(entered_by=holder).count() == 1
    assert AuditLog.objects.filter(object_repr="جدول الشعبة — تصحيحٌ بعد الإغلاق").exists()


# ── الأدوار ────────────────────────────────────────────────────────────────────


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
    _save(client_as(holder), assigned, 1, [_cells(kids[0], "present", head)])

    body = (
        client_as(holder)
        .get(reverse("class_grid_history", args=[assigned.id, kids[0].pk, 1]))
        .content.decode()
    )
    assert teacher.full_name in body and holder.full_name in body and "صُحِّح" in body


def test_the_read_query_count_is_flat_in_the_number_of_students(
    client_as, school, assigned, teacher, clock
):
    """عدُّ الاستعلامات ثابتٌ بعدد الطلبة: شعبةٌ بـ30 ثمّ بـ60 تُقرأ بالعدد نفسِه، وتحت حدٍّ مطلق (خطُّ أساسٍ مقيس: 32)."""

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
    assert thirty == sixty and thirty <= 35, (thirty, sixty)


# ── «اطفئ الشبكة»: مع المفتاح لا يُفتح كشفُ الحصّة القديم لمن يملك الجدول ───────────


def test_with_the_switch_on_the_old_session_sheet_redirects_to_the_class_grid(
    client_as, assigned, teacher, session, clock
):
    """الكشفُ القديمُ (الشبكة) `/teacher/attendance/<حصّة>/` يُحيل المعلّمَ المُسنَدَ إلى جدول شعبته."""
    Session.objects.filter(pk=session.pk).update(teacher=teacher, class_group=assigned)
    response = client_as(teacher).get(reverse("attendance", args=[session.id]))
    assert response.status_code == 302
    assert response.url == reverse("class_grid", args=[assigned.id])


def test_with_the_switch_off_the_old_sheet_is_untouched(
    settings, client_as, assigned, teacher, session, clock
):
    settings.PROVISIONAL_GRID_ENABLED = False
    Session.objects.filter(pk=session.pk).update(teacher=teacher, class_group=assigned)
    response = client_as(teacher).get(reverse("attendance", args=[session.id]))
    assert response.status_code != 302 or "grid" not in response.url


def test_a_substitute_without_an_assignment_keeps_the_old_sheet_as_a_fallback(
    client_as, school, assigned, other_teacher, session, clock
):
    """بديلٌ سُلّمتْه الحصّةُ ولا إسنادَ له في الشعبة: لا جدولَ له فلا يُحال، ويبقى الكشفُ القديمُ بديلاً."""
    Session.objects.filter(pk=session.pk).update(teacher=other_teacher, class_group=assigned)
    response = client_as(other_teacher).get(reverse("attendance", args=[session.id]))
    assert not (response.status_code == 302 and "grid" in response.url)


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

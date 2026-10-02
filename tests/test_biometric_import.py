"""استيرادُ كشف البصمة اليوميّ — التحليلُ والمعاينةُ والاعتمادُ والشاشة.

الكشفُ هنا اصطناعيٌّ بصيغة جهاز الحضور الحقيقيّة (61 عموداً بمرساة «Department:» وأعمدة
Total/Absent/Attend العطلى)، وأسماؤه وأرقامُه من فراغٍ لا من أيّ كشفٍ حقيقيّ — فلا بياناتِ
موظّفين في المستودع. والمرجعُ الحاكم لقواعد الحضور ``docs/compliance/staff_attendance_spec.md``؛
هذا الملفّ لا يعيد اختبارَها (لها ملفّاتُها) بل يثبت أنّ الاستيرادَ يوجّه إليها ولا يخترع غيرها.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, time

import pytest
from django.urls import reverse
from django.utils import timezone

from core.models import AuditLog
from staff_affairs.attendance import StaffAttendanceService
from staff_affairs.attendance import biometric_services as biometric
from staff_affairs.models import StaffAttendance, StaffAttendanceExemption
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

DAY = date(2026, 2, 2)
NOW = datetime(2026, 2, 15, 12, 0)


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    import staff_affairs.attendance as attendance_module

    monkeypatch.setattr(
        attendance_module,
        "_now",
        lambda: timezone.localtime(timezone.make_aware(NOW)),
        raising=False,
    )


def _person(school, number, role="teacher"):
    user = UserFactory(full_name=f"موظف اصطناعي {number}", employee_number=str(number))
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


@pytest.fixture
def secretary(school):
    return _person(school, 90001, "secretary")


def _line(number, code="102", check_in="06:50AM", check_out="02:00PM", day="02/02/2026"):
    """سطرُ الجهاز: ترويسةُ التقرير ثمّ البيانات، وأعمدةٌ عطلى في آخره كما في الملفّ الحقيقيّ."""
    cells = [""] * 61
    head = [
        "Date :", day, "Monday", "Employee Number", "Name", "Status", "Early Entry", "In ",
        "Late Entry", "Early Exit", "Out ", "Overtime", "Exit During Work", "Working Hours",
        "Shift", "Department:", " Synthetic School",
    ]  # fmt: skip
    cells[: len(head)] = head
    cells[17] = str(number)
    cells[19] = f"SYNTHETIC PERSON {number}"
    cells[21] = code
    cells[24] = check_in
    cells[31] = check_out
    cells[41] = "Main Shfit"
    cells[43:60] = [
        "Permission Name:", "", "From:", "12:00 AM", "To:", "12:00 AM", "Duration:", "0",
        "Total :", "1", "Absent :", "12", "Vacation :", "0", "Attend :", "-11", day,
    ]  # fmt: skip
    cells[60] = "Page -1 of 1"
    return cells


def _csv(*lines) -> bytes:
    out = io.StringIO()
    csv.writer(out).writerows(lines)
    return out.getvalue().encode("utf-8")


def _rows(*lines):
    return biometric.parse(_csv(*lines)).rows


class TestParse:
    def test_reads_the_useful_fields_by_anchor(self):
        parsed = biometric.parse(_csv(_line(1001, "102", "06:57AM", "12:04PM")))
        row = parsed.rows[0]
        assert (row.employee_number, row.day) == ("1001", DAY)
        assert (row.check_in, row.check_out) == (time(6, 57), time(12, 4))
        assert parsed.issues == []

    def test_midnight_placeholder_means_no_punch(self):
        row = _rows(_line(1002, "103", "12:00AM", "11:00AM"))[0]
        assert row.check_in is None
        assert row.check_out == time(11, 0)
        assert row.device_status == biometric.DEVICE_MISSING_IN

    def test_unknown_device_code_is_reported_not_imported(self):
        parsed = biometric.parse(_csv(_line(1003, "999"), _line(1004)))
        assert [r.employee_number for r in parsed.rows] == ["1004"]
        assert "999" in parsed.issues[0].message

    def test_bad_time_is_reported_with_its_line(self):
        parsed = biometric.parse(_csv(_line(1005, check_in="25:99AM")))
        assert parsed.rows == []
        assert parsed.issues[0].line == 1

    def test_a_file_that_is_not_a_device_export_is_rejected(self):
        with pytest.raises(biometric.BiometricFileError):
            biometric.parse(b"name,grade\nx,9\n")

    def test_arabic_windows_encoding_is_read(self):
        text = _csv(_line(1006)).decode("utf-8").replace("Main Shfit", "الدوام")
        assert biometric.parse(text.encode("cp1256")).rows[0].employee_number == "1006"

    def test_oversized_file_is_rejected(self):
        with pytest.raises(biometric.BiometricFileError):
            biometric.parse(b"x" * (biometric.MAX_BYTES + 1))


class TestPreview:
    def _plan(self, school, actor, *lines):
        parsed = biometric.parse(_csv(*lines))
        return biometric.preview(school, actor, parsed.rows, parsed.issues)

    def _actions(self, plan):
        return {i.row.employee_number: i.action for i in plan.items}

    def test_new_row_is_classified_by_the_existing_rules(self, school, secretary):
        _person(school, 2001)
        _person(school, 2002)
        plan = self._plan(
            school, secretary, _line(2001, check_in="06:50AM"), _line(2002, check_in="07:20AM")
        )
        statuses = {i.row.employee_number: (i.status, i.late_minutes) for i in plan.items}
        assert statuses == {"2001": ("present", 0), "2002": ("late", 20)}
        assert plan.writable == 2

    def test_after_nine_without_cover_is_absent(self, school, secretary):
        _person(school, 2003)
        assert (
            self._plan(school, secretary, _line(2003, check_in="09:30AM")).items[0].status
            == "absent"
        )

    def test_unknown_employee_number_is_unmatched(self, school, secretary):
        assert self._actions(self._plan(school, secretary, _line(9999))) == {"9999": "unmatched"}

    def test_employee_of_another_school_is_unmatched(self, school, secretary):
        from tests.conftest import SchoolFactory

        other = SchoolFactory()
        outsider = UserFactory(full_name="غريب", employee_number="2100")
        MembershipFactory(
            user=outsider, school=other, role=RoleFactory(school=other, name="teacher")
        )
        assert self._actions(self._plan(school, secretary, _line(2100))) == {"2100": "unmatched"}

    def test_missing_entry_punch_is_never_guessed(self, school, secretary):
        _person(school, 2004)
        plan = self._plan(school, secretary, _line(2004, "103", "12:00AM", "11:00AM"))
        assert plan.items[0].action == biometric.MISSING_IN
        assert plan.writable == 0

    def test_exempt_staff_is_skipped(self, school, secretary):
        staff = _person(school, 2005)
        StaffAttendanceExemption.objects.create(
            school=school, staff=staff, start_date=date(2026, 1, 1), created_by=secretary
        )
        assert self._actions(self._plan(school, secretary, _line(2005))) == {"2005": "exempt"}

    def test_own_row_is_not_recorded_by_oneself(self, school, secretary):
        assert self._actions(self._plan(school, secretary, _line(90001))) == {"90001": "self"}

    def test_duplicate_row_in_the_file_is_flagged(self, school, secretary):
        _person(school, 2006)
        actions = [i.action for i in self._plan(school, secretary, _line(2006), _line(2006)).items]
        assert actions == [biometric.NEW, biometric.INVALID]

    def test_future_day_is_invalid(self, school, secretary):
        _person(school, 2007)
        plan = self._plan(school, secretary, _line(2007, day="01/03/2026"))
        assert plan.items[0].action == biometric.INVALID

    def test_checkout_before_checkin_is_dropped_with_a_note(self, school, secretary):
        _person(school, 2008)
        item = self._plan(school, secretary, _line(2008, "102", "08:00AM", "07:00AM")).items[0]
        assert item.action == biometric.NEW and item.check_out is None and item.note

    def test_preview_writes_nothing(self, school, secretary):
        _person(school, 2009)
        self._plan(school, secretary, _line(2009))
        assert not StaffAttendance.objects.exists()


class TestCommit:
    def test_commit_records_through_mark_with_the_source_tag(self, school, secretary):
        staff = _person(school, 3001)
        result = biometric.commit(school, secretary, _rows(_line(3001, check_in="07:20AM")))
        record = StaffAttendance.objects.get(staff=staff, date=DAY)
        assert (record.status, record.late_minutes, record.check_in) == ("late", 20, time(7, 20))
        assert result.written == 1
        entry = AuditLog.objects.filter(
            model_name="other", object_repr__startswith="StaffAttendance"
        ).first()
        assert entry.changes["source"] == biometric.SOURCE

    def test_reimport_is_idempotent(self, school, secretary):
        _person(school, 3002)
        rows = _rows(_line(3002))
        biometric.commit(school, secretary, rows)
        second = biometric.commit(school, secretary, rows)
        assert (second.written, second.skipped_same) == (0, 1)
        assert StaffAttendance.objects.count() == 1

    def test_missing_entry_punch_writes_nothing(self, school, secretary):
        _person(school, 3003)
        result = biometric.commit(
            school, secretary, _rows(_line(3003, "103", "12:00AM", "11:00AM"))
        )
        assert result.written == 0 and not StaffAttendance.objects.exists()

    def test_manual_record_with_other_times_is_not_overwritten_by_default(self, school, secretary):
        staff = _person(school, 3004)
        StaffAttendanceService.mark(
            school=school, staff=staff, day=DAY, status="present", actor=secretary,
            check_in=time(6, 30),
        )  # fmt: skip
        rows = _rows(_line(3004, check_in="06:55AM"))
        kept = biometric.commit(school, secretary, rows)
        assert kept.written == 0
        assert StaffAttendance.objects.get(staff=staff, date=DAY).check_in == time(6, 30)
        forced = biometric.commit(school, secretary, rows, overwrite_conflicts=True)
        assert forced.written == 1
        assert StaffAttendance.objects.get(staff=staff, date=DAY).check_in == time(6, 55)

    def test_checkout_completes_an_existing_entry_without_a_decision(self, school, secretary):
        staff = _person(school, 3005)
        StaffAttendanceService.mark(
            school=school, staff=staff, day=DAY, status="present", actor=secretary,
            check_in=time(6, 50),
        )  # fmt: skip
        result = biometric.commit(
            school, secretary, _rows(_line(3005, check_in="06:50AM", check_out="01:00PM"))
        )
        assert result.written == 1
        assert StaffAttendance.objects.get(staff=staff, date=DAY).check_out == time(13, 0)

    def test_early_leave_is_counted_by_the_existing_rule(self, school, secretary):
        staff = _person(school, 3006)
        biometric.commit(
            school, secretary, _rows(_line(3006, check_in="06:50AM", check_out="12:30PM"))
        )
        assert StaffAttendance.objects.get(staff=staff, date=DAY).early_leave_minutes == 90

    def test_summary_is_audited_without_names(self, school, secretary):
        _person(school, 3007)
        biometric.commit(school, secretary, _rows(_line(3007)))
        entry = AuditLog.objects.filter(object_repr__startswith="BiometricImport").get()
        assert entry.changes["written"] == 1
        assert "اصطناعي" not in str(entry.changes)


class TestScreens:
    URL = "staff_affairs:attendance_import"

    def _upload(self, client, *lines, name="كشف.csv"):
        from django.core.files.uploadedfile import SimpleUploadedFile

        return client.post(reverse(self.URL), {"file": SimpleUploadedFile(name, _csv(*lines))})

    def test_secretary_sees_the_upload_page(self, client_as, secretary):
        assert client_as(secretary).get(reverse(self.URL)).status_code == 200

    def test_teacher_is_denied(self, client_as, school):
        assert client_as(_person(school, 4001)).get(reverse(self.URL)).status_code == 403

    def test_upload_previews_without_writing(self, client_as, school, secretary):
        _person(school, 4002)
        response = self._upload(client_as(secretary), _line(4002))
        assert response.status_code == 200
        assert response.context["plan"].writable == 1
        assert not StaffAttendance.objects.exists()

    def test_non_csv_upload_is_refused(self, client_as, secretary):
        response = self._upload(client_as(secretary), _line(1), name="كشف.xlsx")
        assert response.status_code == 200 and "plan" not in response.context

    def test_commit_writes_then_redirects_to_the_board(self, client_as, school, secretary):
        staff = _person(school, 4003)
        client = client_as(secretary)
        token = self._upload(client, _line(4003)).context["token"]
        response = client.post(reverse("staff_affairs:attendance_import_commit"), {"token": token})
        assert response.status_code == 302 and "date=2026-02-02" in response["Location"]
        assert StaffAttendance.objects.filter(staff=staff, date=DAY).exists()

    def test_commit_with_a_wrong_token_writes_nothing(self, client_as, school, secretary):
        _person(school, 4004)
        client = client_as(secretary)
        self._upload(client, _line(4004))
        response = client.post(reverse("staff_affairs:attendance_import_commit"), {"token": "x"})
        assert response.status_code == 200 and not StaffAttendance.objects.exists()

    def test_token_is_single_use(self, client_as, school, secretary):
        _person(school, 4005)
        client = client_as(secretary)
        token = self._upload(client, _line(4005)).context["token"]
        commit = reverse("staff_affairs:attendance_import_commit")
        client.post(commit, {"token": token})
        again = client.post(commit, {"token": token})
        assert again.status_code == 200 and StaffAttendance.objects.count() == 1

    def test_menu_link_reaches_the_secretary(self, client_as, secretary):
        html = client_as(secretary).get(reverse("dashboard")).content.decode()
        assert reverse(self.URL) in html

    def test_deputy_is_not_offered_the_link_nor_admitted(self, client_as, school):
        deputy = _person(school, 4010, "vice_admin")
        client = client_as(deputy)
        assert reverse(self.URL) not in client.get(reverse("dashboard")).content.decode()
        assert client.get(reverse(self.URL)).status_code == 403

    def test_oversized_upload_is_refused_before_reading(self, client_as, secretary):
        from django.core.files.uploadedfile import SimpleUploadedFile

        big = SimpleUploadedFile("كشف.csv", b"x" * (biometric.MAX_BYTES + 1))
        response = client_as(secretary).post(reverse(self.URL), {"file": big})
        assert response.status_code == 200 and "plan" not in response.context


class TestLimitsAndSchoolScope:
    def test_too_many_rows_are_rejected(self, monkeypatch):
        monkeypatch.setattr(biometric, "MAX_ROWS", 2)
        with pytest.raises(biometric.BiometricFileError):
            biometric.parse(_csv(_line(1), _line(2), _line(3)))

    def test_commit_matches_inside_the_session_school_only(self, school, secretary):
        from tests.conftest import SchoolFactory

        other = SchoolFactory()
        outsider = UserFactory(full_name="غريب", employee_number="5100")
        MembershipFactory(
            user=outsider, school=other, role=RoleFactory(school=other, name="teacher")
        )
        result = biometric.commit(school, secretary, _rows(_line(5100)))
        assert result.written == 0 and not StaffAttendance.objects.exists()


class TestImportWindow:
    """قرارُ المالك D-117م: لا يُستورد يومٌ أقدمُ من شهرٍ من تاريخ الاستيراد (والساعةُ هنا 2026-02-15)."""

    def _action(self, school, secretary, day):
        parsed = biometric.parse(_csv(_line(6001, day=day)))
        return biometric.preview(school, secretary, parsed.rows, parsed.issues).items[0]

    def test_last_day_inside_the_window_passes(self, school, secretary):
        _person(school, 6001)
        assert self._action(school, secretary, "15/01/2026").action == biometric.NEW

    def test_day_before_the_window_is_rejected_with_its_limit(self, school, secretary):
        _person(school, 6001)
        item = self._action(school, secretary, "14/01/2026")
        assert item.action == biometric.INVALID
        assert "15/01/2026" in item.note

    def test_window_start_clamps_to_the_shorter_month(self):
        assert biometric.window_start(date(2026, 3, 31)) == date(2026, 2, 28)
        assert biometric.window_start(date(2026, 1, 10)) == date(2025, 12, 10)

    def test_commit_does_not_write_a_day_outside_the_window(self, school, secretary):
        _person(school, 6001)
        result = biometric.commit(school, secretary, _rows(_line(6001, day="14/01/2026")))
        assert result.written == 0 and not StaffAttendance.objects.exists()


class TestAttendanceBoardSearch:
    """لوحةُ الرصد (نمط سجلّ): حقلُ بحثٍ وترشيحٌ بالحالة وتنقّلٌ بين الأيّام — الترشيحُ نفسُه في المتصفّح."""

    def _page(self, client_as, user, **params):
        return client_as(user).get(reverse("staff_affairs:attendance_board"), params)

    def test_page_declares_the_list_layout(self, client_as, secretary):
        html = self._page(client_as, secretary).content.decode()
        assert "layout-list" in html and "page-noscroll" in html

    def test_search_and_state_fields_and_script_are_offered(self, client_as, secretary):
        html = self._page(client_as, secretary).content.decode()
        for needle in (
            'id="board-q"',
            'id="board-status"',
            "attendance-board.js",
            'id="att-board-list"',
        ):
            assert needle in html

    def test_search_and_state_come_back_from_the_url(self, client_as, secretary):
        html = self._page(client_as, secretary, q="سعد", status="late").content.decode()
        assert 'value="سعد"' in html
        assert re.search(r'<option value="late"[^>]*selected', html)

    def test_unknown_state_is_ignored(self, client_as, secretary):
        html = self._page(client_as, secretary, status="<script>").content.decode()
        assert "<script>" not in html.split('id="board-status"')[1].split("</select>")[0]

    def test_previous_and_next_day_links(self, client_as, secretary):
        html = self._page(client_as, secretary, date="2026-02-02").content.decode()
        assert "?date=2026-02-01" in html and "?date=2026-02-03" in html

    def test_today_has_no_next_day_link(self, client_as, secretary):
        today = timezone.localdate()
        html = self._page(client_as, secretary, date=today.isoformat()).content.decode()
        assert 'rel="next"' not in html and 'rel="prev"' in html

    def test_rows_carry_the_state_the_filter_reads(self, client_as, school, secretary):
        staff = _person(school, 7001)
        StaffAttendanceService.mark(
            school=school, staff=staff, day=DAY, status="present", actor=secretary,
            check_in=time(6, 40),
        )  # fmt: skip
        html = self._page(client_as, secretary, date=DAY.isoformat()).content.decode()
        assert 'data-state="present"' in html and 'data-state="unmarked"' in html


class TestAbsentFromFile:
    """كادرُ المنصّة الذي لا سطرَ له في الكشف يُعرض — فيُكشف المنقولون الذين لم تُسجَّل مغادرتُهم."""

    def _plan(self, school, actor, *lines):
        parsed = biometric.parse(_csv(*lines))
        return biometric.preview(school, actor, parsed.rows, parsed.issues)

    def test_staff_without_a_row_are_listed_and_those_with_a_row_are_not(self, school, secretary):
        listed, silent = _person(school, 8001), _person(school, 8002)
        plan = self._plan(school, secretary, _line(8001))
        names = {p.pk for _, people in plan.absent_from_file for p in people}
        assert silent.pk in names and listed.pk not in names

    def test_exempt_staff_are_not_listed(self, school, secretary):
        exempt = _person(school, 8003)
        StaffAttendanceExemption.objects.create(
            school=school, staff=exempt, start_date=date(2026, 1, 1), created_by=secretary
        )
        plan = self._plan(school, secretary, _line(8001))
        assert exempt.pk not in {p.pk for _, people in plan.absent_from_file for p in people}

    def test_departed_staff_are_not_listed(self, school, secretary):
        from core.models.access import Membership

        gone = _person(school, 8004)
        Membership.objects.filter(user=gone).update(is_active=False)
        plan = self._plan(school, secretary, _line(8001))
        assert gone.pk not in {p.pk for _, people in plan.absent_from_file for p in people}

    def test_nothing_is_recorded_for_them(self, school, secretary):
        _person(school, 8005)
        biometric.commit(school, secretary, _rows(_line(8001)))
        assert not StaffAttendance.objects.filter(staff__employee_number="8005").exists()

    def test_the_screen_shows_the_section(self, client_as, school, secretary):
        from django.core.files.uploadedfile import SimpleUploadedFile

        _person(school, 8006)
        response = client_as(secretary).post(
            reverse("staff_affairs:attendance_import"),
            {"file": SimpleUploadedFile("كشف.csv", _csv(_line(8001)))},
        )
        assert "ولم يظهروا في الكشف" in response.content.decode()

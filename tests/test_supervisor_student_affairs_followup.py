"""[SECURITY] متابعةُ شؤون الطلبة للمشرف الإداريّ — مفتوحةٌ له، ومقصورةٌ على جناحه.

قرارا المستخدم 2026-09-14 و2026-09-15:
- يفتح المشرفُ ملخّصَ الغياب والسلوك والتأخّر الصباحيّ بتصديراتها (Excel وPDF)،
  ويرصد التأخّرَ الصباحيَّ ويُلغيه (الدليل التنظيميّ م 3.4.2.2).
- وكلُّ ما يراه فيها طلبةُ جناحه وحدهم: الصفوفُ والأعدادُ والرسمُ والتنبيهاتُ
  وأسطرُ التصدير ومرشِّحُ الشعبة. ومعرّفُ طالبٍ أو سجلٍّ من جناحٍ آخر يعود 404.
- ولا يُلغي تأخّرَ الحصّة المرصودَ من كشف الجناح، ولا تأخّرَ يومٍ مضى.
- والقيادةُ على حالها: المدرسةُ كلُّها، بلا استعلامِ نطاقٍ واحد.
"""

import datetime as dt
import json
from io import BytesIO

import openpyxl
import pytest
from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone

from core.models import AuditLog, Wing
from operations.models import AbsenceAlert, Session, StudentAttendance
from tests.conftest import (
    BehaviorInfractionFactory,
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)
from wings.scope import StudentScope

pytestmark = pytest.mark.django_db

OWN = "طالبُ الجناح الأوّل"
OTHER = "طالبُ الجناح الثاني"


# ══════════════════════════════════════════════════════════════════
# التجهيز: جناحان، لكلٍّ شعبةٌ وطالبٌ وحصّةُ اليوم
# ══════════════════════════════════════════════════════════════════


def _staff(school, role, name):
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


def _pupil(school, klass, name):
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="student"))
    StudentEnrollmentFactory(student=user, class_group=klass)
    return user


def _wing(school, year, code, name, supervisor, klass):
    wing = Wing.objects.create(
        school=school, code=code, name=name, academic_year=year, supervisor=supervisor
    )
    klass.wing = wing
    klass.save(update_fields=["wing"])
    return wing


@pytest.fixture
def world(school, seeded_calendar):
    year = seeded_calendar
    today = timezone.localdate()
    supervisor = _staff(school, "admin_supervisor", "مشرف الجناح الأوّل")
    other_supervisor = _staff(school, "admin_supervisor", "مشرف الجناح الثاني")
    teacher = _staff(school, "teacher", "معلّم الحصص")
    own_class = ClassGroupFactory(
        school=school, grade="G7", section="1", level_type="prep", academic_year=year
    )
    other_class = ClassGroupFactory(
        school=school, grade="G8", section="2", level_type="prep", academic_year=year
    )
    _wing(school, year, "w1", "جناح 1", supervisor, own_class)
    _wing(school, year, "w2", "جناح 2", other_supervisor, other_class)
    own = _pupil(school, own_class, OWN)
    other = _pupil(school, other_class, OTHER)
    own_session = _session(school, own_class, teacher, today, 7)
    other_session = _session(school, other_class, teacher, today, 8)
    return {
        "year": year,
        "today": today,
        "supervisor": supervisor,
        "teacher": teacher,
        "own_class": own_class,
        "other_class": other_class,
        "own": own,
        "other": other,
        "own_session": own_session,
        "other_session": other_session,
    }


def _session(school, klass, teacher, day, hour):
    return Session.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher,
        date=day,
        start_time=dt.time(hour, 10),
        end_time=dt.time(hour, 55),
        status="scheduled",
    )


def _mark(school, session, student, status, *, morning=False):
    return StudentAttendance.objects.create(
        school=school,
        session=session,
        student=student,
        status=status,
        tardiness_recorded_at=timezone.now() if morning else None,
    )


def _names(rows, key="student__full_name"):
    return {row[key] for row in rows}


def _workbook_text(response) -> str:
    book = openpyxl.load_workbook(BytesIO(response.content))
    return " ".join(
        str(cell)
        for sheet in book.worksheets
        for row in sheet.iter_rows(values_only=True)
        for cell in row
        if cell is not None
    )


@pytest.fixture
def pdf_as_html(monkeypatch):
    """الـPDF نصُّه HTML — فيُقرأ ما كان سيُطبع بلا محرّك طباعة."""
    monkeypatch.setattr(
        "student_affairs.views.render_pdf",
        lambda html, filename, *args, **kwargs: HttpResponse(html),
    )


# ══════════════════════════════════════════════════════════════════
# الأبواب: مفتوحةٌ للمشرف، ومغلقةٌ على من لم يُفتح له
# ══════════════════════════════════════════════════════════════════

FOLLOW_UP_PAGES = [
    "student_affairs:attendance_overview",
    "student_affairs:attendance_export",
    "student_affairs:attendance_pdf",
    "student_affairs:behavior_overview",
    "student_affairs:behavior_export",
    "student_affairs:behavior_pdf",
    "student_affairs:tardiness_list",
    "student_affairs:tardiness_export",
    "student_affairs:tardiness_pdf",
]


class TestTheDoors:
    @pytest.mark.parametrize("url_name", FOLLOW_UP_PAGES)
    def test_the_supervisor_opens_every_follow_up_page(
        self, client_as, world, pdf_as_html, url_name
    ):
        response = client_as(world["supervisor"]).get(reverse(url_name))

        assert response.status_code == 200, url_name

    def test_the_supervisor_searches_for_a_late_student(self, client_as, world):
        response = client_as(world["supervisor"]).get(
            reverse("student_affairs:tardiness_search") + "?q=طالبُ"
        )

        assert response.status_code == 200

    @pytest.mark.parametrize("role", ["teacher", "student_observer", "services_worker"])
    def test_whoever_was_not_given_follow_up_stays_out(self, client_as, school, world, role):
        """البديلُ المكلَّف بالجناح لا يأخذ شؤونَ الطلبة (قرار 2026-09-15)."""
        user = _staff(school, role, f"دور {role}")
        client = client_as(user)

        assert client.get(reverse("student_affairs:attendance_overview")).status_code == 403
        response = client.post(
            reverse("student_affairs:tardiness_record"), {"student_id": str(world["own"].id)}
        )
        assert response.status_code == 403
        assert not StudentAttendance.objects.exists()


# ══════════════════════════════════════════════════════════════════
# الغياب
# ══════════════════════════════════════════════════════════════════


@pytest.fixture
def absences(school, world):
    for student, session in ((world["own"], "own_session"), (world["other"], "other_session")):
        _mark(school, world[session], student, "absent")
        AbsenceAlert.objects.create(
            school=school,
            student=student,
            absence_count=6,
            period_start=world["today"] - dt.timedelta(days=30),
            period_end=world["today"],
        )


class TestAttendanceIsTheWing:
    def test_the_overview_counts_and_lists_only_the_wing(self, client_as, world, absences):
        response = client_as(world["supervisor"]).get(
            reverse("student_affairs:attendance_overview")
        )
        ctx = response.context

        assert ctx["summary"]["total"] == 1
        assert ctx["summary"]["absent"] == 1
        assert _names(ctx["worst_students"]) == {OWN}
        assert {a.student.full_name for a in ctx["alerts"]} == {OWN}
        assert [row["session__class_group__grade"] for row in ctx["class_breakdown"]] == ["G7"]
        assert json.loads(ctx["chart_absent_json"])[-1] == 100
        assert "جناح 1" in ctx["page_subtitle"]
        assert OTHER not in response.content.decode()

    def test_leadership_still_sees_the_whole_school_without_a_scope_query(
        self, client_as, principal_user, world, absences, monkeypatch
    ):
        def _no_scope_query(self):
            raise AssertionError("القيادةُ لا يُحسب لها نطاقُ جناح")

        monkeypatch.setattr(StudentScope, "student_ids", _no_scope_query)

        response = client_as(principal_user).get(reverse("student_affairs:attendance_overview"))
        ctx = response.context

        assert ctx["summary"]["total"] == 2
        assert _names(ctx["worst_students"]) == {OWN, OTHER}
        assert {a.student.full_name for a in ctx["alerts"]} == {OWN, OTHER}
        assert "جناح" not in ctx["page_subtitle"]
        assert reverse("daily_report") in response.content.decode()

    def test_a_requested_year_does_not_widen_the_supervisor(self, client_as, principal_user, world):
        url = reverse("student_affairs:attendance_overview") + "?year=2020-2021"

        assert client_as(world["supervisor"]).get(url).context["year"] == world["year"]
        assert client_as(principal_user).get(url).context["year"] == "2020-2021"

    def test_the_whole_school_daily_report_is_not_offered_to_the_supervisor(self, client_as, world):
        body = (
            client_as(world["supervisor"])
            .get(reverse("student_affairs:attendance_overview"))
            .content.decode()
        )

        assert reverse("daily_report") not in body

    def test_the_excel_carries_only_the_wing_and_says_so(self, client_as, world, absences):
        response = client_as(world["supervisor"]).get(reverse("student_affairs:attendance_export"))

        text = _workbook_text(response)
        assert OWN in text
        assert OTHER not in text
        trail = AuditLog.objects.get(
            action="export", changes__kind="student_affairs.attendance_xlsx"
        )
        assert trail.changes["rows"] == 2  # سطرُ الأكثر غياباً وسطرُ حضور اليوم — لطالبه وحدَه
        assert "جناح 1" in trail.object_repr

    def test_the_pdf_carries_only_the_wing(self, client_as, world, absences, pdf_as_html):
        body = (
            client_as(world["supervisor"])
            .get(reverse("student_affairs:attendance_pdf"))
            .content.decode()
        )

        assert OWN in body
        assert OTHER not in body
        assert "جناح 1" in body


# ══════════════════════════════════════════════════════════════════
# السلوك
# ══════════════════════════════════════════════════════════════════


@pytest.fixture
def infractions(school, world):
    for student in (world["own"], world["other"]):
        BehaviorInfractionFactory(school=school, student=student, reported_by=world["teacher"])


class TestBehaviourIsTheWing:
    def test_the_overview_counts_the_wing_and_divides_by_the_wing(
        self, client_as, world, infractions
    ):
        ctx = (
            client_as(world["supervisor"]).get(reverse("student_affairs:behavior_overview")).context
        )

        assert ctx["total_infractions"] == 1
        assert ctx["today_infractions"] == 1
        assert ctx["total_students"] == 1
        assert ctx["infraction_pct"] == 100
        assert _names(ctx["worst_students"]) == {OWN}
        assert sum(json.loads(ctx["chart_data_json"])) == 1
        assert "جناح 1" in ctx["wing_subtitle"]

    def test_leadership_counts_the_school(self, client_as, principal_user, world, infractions):
        ctx = client_as(principal_user).get(reverse("student_affairs:behavior_overview")).context

        assert ctx["total_infractions"] == 2
        assert _names(ctx["worst_students"]) == {OWN, OTHER}
        assert sum(json.loads(ctx["chart_data_json"])) == 2
        assert ctx["wing_subtitle"] == ""

    def test_the_excel_and_pdf_carry_only_the_wing(
        self, client_as, world, infractions, pdf_as_html
    ):
        client = client_as(world["supervisor"])

        text = _workbook_text(client.get(reverse("student_affairs:behavior_export")))
        body = client.get(reverse("student_affairs:behavior_pdf")).content.decode()

        assert OWN in text and OTHER not in text
        assert OWN in body and OTHER not in body
        trail = AuditLog.objects.get(action="export", changes__kind="student_affairs.behavior_xlsx")
        assert trail.changes["rows"] == 1


# ══════════════════════════════════════════════════════════════════
# التأخّر الصباحيّ — القراءة
# ══════════════════════════════════════════════════════════════════


@pytest.fixture
def lateness(school, world):
    return {
        "own": _mark(school, world["own_session"], world["own"], "late", morning=True),
        "other": _mark(school, world["other_session"], world["other"], "late", morning=True),
    }


class TestTardinessListIsTheWing:
    def test_the_list_and_its_numbers_are_the_wing(self, client_as, world, lateness):
        ctx = client_as(world["supervisor"]).get(reverse("student_affairs:tardiness_list")).context

        assert [rec.student.full_name for rec in ctx["late_records"]] == [OWN]
        assert set(ctx["cumulative_counts"]) == {world["own"].id}
        assert ctx["total_students_today"] == 1
        assert ctx["weekly_late"] == 1
        assert [chip["count"] for chip in ctx["class_chips"]] == [1]

    def test_another_wings_section_typed_by_hand_is_empty(self, client_as, world, lateness):
        other = world["other_class"]
        url = (
            reverse("student_affairs:tardiness_list")
            + f"?grade={other.grade}&section={other.section}"
        )

        ctx = client_as(world["supervisor"]).get(url).context

        assert ctx["late_records"] == []
        assert ctx["total_late"] == 0

    def test_leadership_lists_the_school(self, client_as, principal_user, world, lateness):
        ctx = client_as(principal_user).get(reverse("student_affairs:tardiness_list")).context

        assert {rec.student.full_name for rec in ctx["late_records"]} == {OWN, OTHER}
        assert ctx["total_students_today"] == 2
        assert ctx["weekly_late"] == 2

    def test_the_excel_and_pdf_carry_only_the_wing(self, client_as, world, lateness, pdf_as_html):
        client = client_as(world["supervisor"])

        text = _workbook_text(client.get(reverse("student_affairs:tardiness_export")))
        body = client.get(reverse("student_affairs:tardiness_pdf")).content.decode()

        assert OWN in text and OTHER not in text
        assert OWN in body and OTHER not in body
        trail = AuditLog.objects.get(
            action="export", changes__kind="student_affairs.tardiness_xlsx"
        )
        assert trail.changes["rows"] == 1
        assert "جناح 1" in trail.object_repr

    def test_no_cancel_button_for_a_period_lateness(self, client_as, school, world):
        period_late = _mark(school, world["own_session"], world["own"], "late")

        body = client_as(world["supervisor"]).get(reverse("student_affairs:tardiness_list"))

        assert reverse("student_affairs:tardiness_delete", args=[period_late.pk]) not in (
            body.content.decode()
        )


# ══════════════════════════════════════════════════════════════════
# التأخّر الصباحيّ — البحث والرصد والإلغاء
# ══════════════════════════════════════════════════════════════════


class TestTardinessSearch:
    def _found(self, client, q="طالبُ"):
        response = client.get(reverse("student_affairs:tardiness_search") + f"?q={q}")
        return {row["name"] for row in response.json()["results"]}

    def test_the_supervisor_finds_only_his_wing(self, client_as, world):
        assert self._found(client_as(world["supervisor"])) == {OWN}

    def test_another_wings_student_by_name_is_not_found(self, client_as, world):
        assert self._found(client_as(world["supervisor"]), "الثاني") == set()

    def test_leadership_finds_the_school(self, client_as, principal_user, world):
        assert self._found(client_as(principal_user)) == {OWN, OTHER}


class TestTardinessRecord:
    def _record(self, client, student):
        return client.post(
            reverse("student_affairs:tardiness_record"), {"student_id": str(student.id)}
        )

    def test_another_wings_student_is_404_and_nothing_is_written(self, client_as, world):
        client = client_as(world["supervisor"])
        trails_before = AuditLog.objects.filter(action="create").count()

        response = self._record(client, world["other"])

        assert response.status_code == 404
        assert not StudentAttendance.objects.exists()
        assert AuditLog.objects.filter(action="create").count() == trails_before

    def test_a_forged_student_id_is_404(self, client_as, world):
        response = client_as(world["supervisor"]).post(
            reverse("student_affairs:tardiness_record"), {"student_id": "not-a-uuid"}
        )

        assert response.status_code == 404

    def test_his_wings_student_is_recorded_at_the_gate_on_his_own_class(self, client_as, world):
        response = self._record(client_as(world["supervisor"]), world["own"])

        assert response.status_code == 302
        row = StudentAttendance.objects.get(student=world["own"])
        assert (row.status, row.source, row.whereabouts) == ("late", "supervisor", "gate")
        assert row.session_id == world["own_session"].id
        assert row.tardiness_recorded_at is not None
        trail = AuditLog.objects.get(action="create", object_id=str(row.pk))
        assert "جناح 1" in trail.object_repr

    def test_no_class_today_means_no_record_not_another_class(self, client_as, world):
        """لا حصّةَ لشعبته اليوم: لا يُعلَّق التأخّرُ على حصّة شعبةٍ في جناحٍ آخر."""
        world["own_session"].delete()

        response = self._record(client_as(world["supervisor"]), world["own"])

        assert response.status_code == 302
        assert not StudentAttendance.objects.exists()

    def test_leadership_keeps_the_school_fallback(self, client_as, principal_user, world):
        world["own_session"].delete()

        self._record(client_as(principal_user), world["own"])

        row = StudentAttendance.objects.get(student=world["own"])
        assert row.session_id == world["other_session"].id
        assert (row.source, row.whereabouts) == ("teacher", "")


class TestTardinessDelete:
    def _delete(self, client, row):
        return client.post(reverse("student_affairs:tardiness_delete", args=[row.pk]))

    def _unchanged(self, row):
        row.refresh_from_db()
        return row.status == "late"

    def test_another_wings_row_is_404(self, client_as, world, lateness):
        response = self._delete(client_as(world["supervisor"]), lateness["other"])

        assert response.status_code == 404
        assert self._unchanged(lateness["other"])

    def test_a_period_lateness_from_the_register_is_404(self, client_as, school, world):
        row = _mark(school, world["own_session"], world["own"], "late")

        assert self._delete(client_as(world["supervisor"]), row).status_code == 404
        assert self._unchanged(row)

    def test_a_past_days_lateness_is_404(self, client_as, school, world):
        yesterday = _session(
            school, world["own_class"], world["teacher"], world["today"] - dt.timedelta(days=1), 7
        )
        row = _mark(school, yesterday, world["own"], "late", morning=True)

        assert self._delete(client_as(world["supervisor"]), row).status_code == 404
        assert self._unchanged(row)

    def test_his_morning_lateness_today_is_cancelled(self, client_as, world):
        client = client_as(world["supervisor"])
        client.post(
            reverse("student_affairs:tardiness_record"), {"student_id": str(world["own"].id)}
        )
        row = StudentAttendance.objects.get(student=world["own"])

        response = self._delete(client, row)

        assert response.status_code == 302
        row.refresh_from_db()
        assert (row.status, row.whereabouts, row.tardiness_recorded_at) == ("present", "", None)

    def test_leadership_cancels_as_before(self, client_as, principal_user, school, world):
        row = _mark(school, world["other_session"], world["other"], "late")

        assert self._delete(client_as(principal_user), row).status_code == 302
        row.refresh_from_db()
        assert row.status == "present"

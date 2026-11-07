"""تقرير السلوك اليومي (W-20261107-010): صفحةٌ بتاريخ يومٍ ومرشّحَي الجناح والصفّ وتصديرُ PDF وExcel.

ما يُحرس: يومُ المخالفة (حصّتُها إن وُجدت وإلّا `date`) فالآليّةُ المصحَّحةُ لاحقاً تظهر في يوم حصّتها، ونطاقُ الدور
(المعلّمُ لطلبته والمقيَّدُ بجناحه لجناحه والقيادةُ للمدرسة)، وتطابقُ الملفّين مع المعروض عدداً وترتيباً، وأثرُ التدقيق بلا
نصّ الوصف، وغيابُ الرقم الشخصيّ وولي الأمر، وثباتُ عدد الاستعلامات أمام عدد الصفوف.
"""

import datetime as dt
from io import BytesIO

import openpyxl
import pytest
from django.db import connection
from django.http import Http404, QueryDict
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from behavior.models import BehaviorInfraction, ViolationCategory
from behavior.selectors import daily_filters, daily_infractions
from core.academic_calendar import academic_year_for_school
from core.exports.runner import run_job
from core.models import AuditLog, ExportJob, Wing
from operations.models import ScheduleSlot, Session
from reports.export_builders import build_behavior_daily_pdf, build_behavior_daily_xlsx
from tests.conftest import (
    BehaviorInfractionFactory,
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)
from wings.scope import student_scope

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

SECRET = "وصفٌ سرّيٌّ لا يخرج من الصفحة"
NATIONAL_ID = "29300000777"
AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


@pytest.fixture
def year(school, seeded_calendar):
    return academic_year_for_school(school)


@pytest.fixture
def today():
    return timezone.localdate()


@pytest.fixture
def wing_a(school, year):
    return Wing.objects.create(school=school, code="wa", name="جناح أ", academic_year=year)


@pytest.fixture
def wing_b(school, year):
    return Wing.objects.create(school=school, code="wb", name="جناح ب", academic_year=year)


@pytest.fixture
def klass_a(school, year, wing_a):
    return ClassGroupFactory(
        school=school, grade="G7", section="1", academic_year=year, wing=wing_a
    )


@pytest.fixture
def klass_b(school, year, wing_b):
    return ClassGroupFactory(
        school=school, grade="G8", section="2", academic_year=year, wing=wing_b
    )


@pytest.fixture
def category(db):
    return ViolationCategory.objects.create(code="T-1", name_ar="إزعاجٌ في الصف", degree=2)


def _staff(school, name, role):
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


def _student(school, group, name, national_id=""):
    user = UserFactory(full_name=name, **({"national_id": national_id} if national_id else {}))
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="student"))
    StudentEnrollmentFactory(student=user, class_group=group)
    return user


def _infraction(school, student, reporter, category=None, day=None, **extra):
    item = BehaviorInfractionFactory(
        school=school,
        student=student,
        reported_by=reporter,
        violation_category=category,
        description=SECRET,
        **extra,
    )
    # `date` يومُ الكتابة (auto_now_add) من `date.today()` الحقيقيّ لا الساعة المثبَّتة: يُضبط دائماً بعد الإنشاء
    BehaviorInfraction.objects.filter(pk=item.pk).update(date=day or timezone.localdate())
    return item


@pytest.fixture
def principal(school):
    return _staff(school, "مدير المدرسة", "principal")


@pytest.fixture
def reporter(school):
    return _staff(school, "الراصد فلان", "teacher")


def _rows(school, user, day, year, **kw):
    return daily_infractions(school, user, day, scope=student_scope(user, school), year=year, **kw)


class TestTheDay:
    def test_the_page_defaults_to_today_and_lists_the_columns(
        self, client_as, school, principal, reporter, klass_a, category, today
    ):
        pupil = _student(school, klass_a, "سالم الطالب", national_id=NATIONAL_ID)
        _infraction(school, pupil, reporter, category)

        resp = client_as(principal).get(reverse("behavior:daily_report"))

        assert resp.status_code == 200
        assert resp.context["day"] == today
        (row,) = resp.context["rows"]
        assert row["student"] == "سالم الطالب" and row["violation"] == "إزعاجٌ في الصف"
        assert row["reporter"] == "الراصد فلان" and row["class_text"].endswith("/ 1")
        body = resp.content.decode()
        assert SECRET not in body and NATIONAL_ID not in body
        assert "ولي" not in body.split("<table", 1)[1]  # لا عمودَ لوليّ الأمر

    def test_an_auto_infraction_corrected_later_shows_on_its_session_day_not_the_writing_day(
        self, school, principal, klass_a, year, today
    ):
        yesterday = today - dt.timedelta(days=1)
        teacher = _staff(school, "معلّم الحصّة", "teacher")
        pupil = _student(school, klass_a, "طالبٌ متأخّر")
        session = Session.objects.create(
            school=school,
            class_group=klass_a,
            teacher=teacher,
            date=yesterday,
            start_time=dt.time(7, 10),
            end_time=dt.time(7, 55),
        )
        # كُتبت اليوم (date=today) عن حصّة الأمس — كما يفعل التصحيحُ اللاحق للرصد
        _infraction(school, pupil, None, session=session, auto_rule="period_tardy")

        assert [r["student"] for r in _rows(school, principal, yesterday, year)] == ["طالبٌ متأخّر"]
        assert _rows(school, principal, today, year) == []

    def test_a_manual_infraction_without_a_session_uses_its_writing_day(
        self, school, principal, reporter, klass_a, year, today
    ):
        pupil = _student(school, klass_a, "طالبٌ")
        old = today - dt.timedelta(days=3)
        _infraction(school, pupil, reporter, day=old)

        assert len(_rows(school, principal, old, year)) == 1
        assert _rows(school, principal, today, year) == []

    def test_the_auto_reporter_is_named_as_the_monitoring(
        self, school, principal, klass_a, year, today
    ):
        pupil = _student(school, klass_a, "طالبٌ")
        _infraction(school, pupil, None, auto_rule="class_escape")

        assert _rows(school, principal, today, year)[0]["reporter"] == "الرصد الآليّ"

    def test_a_bad_date_falls_back_to_today(self, school, klass_a, today):
        scope = student_scope(_staff(school, "مدير", "principal"), school)

        assert daily_filters(QueryDict("date=غلط"), scope)[0] == today


class TestTheFilters:
    @pytest.fixture
    def both(self, school, reporter, klass_a, klass_b):
        a = _student(school, klass_a, "طالب الجناح أ")
        b = _student(school, klass_b, "طالب الجناح ب")
        _infraction(school, a, reporter)
        _infraction(school, b, reporter)
        return a, b

    def test_wing_filter(self, school, principal, both, wing_b, year, today):
        rows = _rows(school, principal, today, year, wing_id=wing_b.pk)

        assert [r["student"] for r in rows] == ["طالب الجناح ب"]

    def test_grade_filter(self, school, principal, both, year, today):
        rows = _rows(school, principal, today, year, grade="G7")

        assert [r["student"] for r in rows] == ["طالب الجناح أ"]

    def test_rows_follow_the_school_order(self, school, principal, both, year, today):
        assert [r["student"] for r in _rows(school, principal, today, year)] == [
            "طالب الجناح أ",
            "طالب الجناح ب",
        ]


class TestTheScope:
    def test_a_teacher_sees_only_his_students(
        self, client_as, school, reporter, klass_a, klass_b, year
    ):
        mine = _student(school, klass_a, "طالبي")
        theirs = _student(school, klass_b, "ليس طالبي")
        ScheduleSlot.objects.create(
            school=school,
            teacher=reporter,
            class_group=klass_a,
            day_of_week=0,
            period_number=1,
            start_time=dt.time(7, 30),
            end_time=dt.time(8, 15),
            academic_year=year,
        )
        _infraction(school, mine, reporter)
        _infraction(school, theirs, reporter)

        resp = client_as(reporter).get(reverse("behavior:daily_report"))

        assert [r["student"] for r in resp.context["rows"]] == ["طالبي"]

    def test_a_wing_supervisor_gets_his_wing_and_a_404_outside_it(
        self, school, reporter, klass_a, klass_b, wing_a, wing_b, year, today
    ):
        supervisor = _staff(school, "مشرف الجناح", "admin_supervisor")
        wing_a.supervisor = supervisor
        wing_a.save(update_fields=["supervisor"])
        _infraction(school, _student(school, klass_a, "في جناحه"), reporter)
        _infraction(school, _student(school, klass_b, "في جناح غيره"), reporter)
        scope = student_scope(supervisor, school)

        assert [r["student"] for r in _rows(school, supervisor, today, year)] == ["في جناحه"]
        assert daily_filters(QueryDict(f"wing={wing_a.pk}"), scope)[1] == wing_a.pk
        with pytest.raises(Http404):
            daily_filters(QueryDict(f"wing={wing_b.pk}"), scope)

    def test_the_statistics_capability_guards_the_page(self, client_as, school):
        student = _staff(school, "طالب", "student")

        assert client_as(student).get(reverse("behavior:daily_report")).status_code in (302, 403)


class TestTheQueries:
    def test_the_query_count_does_not_grow_with_the_rows(
        self, school, principal, reporter, klass_a, year, today
    ):
        def count():
            with CaptureQueriesContext(connection) as ctx:
                _rows(school, principal, today, year)
            return len(ctx)

        _infraction(school, _student(school, klass_a, "أوّل"), reporter)
        count()  # تسخين: ما يُخزَّن على المستخدم أوّل مرّة لا يُحسب على الصفوف
        few = count()
        for i in range(8):
            _infraction(school, _student(school, klass_a, f"طالب {i}"), reporter)

        assert count() == few


class TestTheExports:
    @pytest.fixture
    def three(self, school, reporter, klass_a, klass_b, category):
        a = _student(school, klass_a, "باء طالب", national_id=NATIONAL_ID)
        c = _student(school, klass_b, "جيم طالب")
        b = _student(school, klass_a, "ألف طالب")
        for pupil in (a, c, b):
            _infraction(school, pupil, reporter, category)

    @pytest.fixture
    def captured(self, monkeypatch):
        seen: list[str] = []

        def fake(html, paper_size="A4"):
            seen.append(html)
            return b"%PDF-stub"

        monkeypatch.setattr("core.pdf_utils.render_pdf_bytes", fake)
        return seen

    def test_the_excel_matches_the_page_in_count_and_order(
        self, client_as, school, principal, three, today
    ):
        shown = [
            r["student"]
            for r in client_as(principal).get(reverse("behavior:daily_report")).context["rows"]
        ]
        params = QueryDict(f"date={today.isoformat()}")

        result = build_behavior_daily_xlsx(school, principal, params)

        ws = openpyxl.load_workbook(BytesIO(result.content)).active
        header = next(r for r in ws.iter_rows() if r[1].value == "الطالب")
        names = [ws.cell(row=header[0].row + i, column=2).value for i in range(1, len(shown) + 1)]
        assert names == shown and result.rows == len(shown) == 3
        text = " ".join(str(c.value) for row in ws.iter_rows() for c in row)
        assert SECRET not in text and NATIONAL_ID not in text

    def test_the_pdf_matches_the_page_and_is_landscape_without_secrets(
        self, client_as, school, principal, three, today, captured
    ):
        shown = [
            r["student"]
            for r in client_as(principal).get(reverse("behavior:daily_report")).context["rows"]
        ]

        result = build_behavior_daily_pdf(school, principal, QueryDict(f"date={today}"))

        html = captured[0]
        assert result.rows == 3 and "A4 landscape" in html
        positions = [html.index(name) for name in shown]
        assert positions == sorted(positions)
        assert SECRET not in html and NATIONAL_ID not in html

    def test_the_request_audits_the_kind_without_the_description_and_the_worker_the_rows(
        self, client_as, school, principal, three, today, captured, monkeypatch
    ):
        monkeypatch.setattr("core.tasks.run_export_job.apply_async", lambda *a, **k: None)

        resp = client_as(principal).get(reverse("behavior:daily_export", args=["pdf"]), **AJAX)

        assert resp.status_code == 202
        asked = AuditLog.objects.get(action="export", object_repr__startswith="behavior.daily_pdf")
        assert SECRET not in f"{asked.object_repr}{asked.changes}"
        job = ExportJob.objects.get()
        assert QueryDict(job.query_string)["date"] == today.isoformat()
        run_job(str(job.id))
        built = AuditLog.objects.get(object_repr="behavior.daily_pdf:built")
        assert built.changes["rows"] == 3 and built.changes["full_national_id"] is False

    def test_an_unknown_format_and_a_foreign_wing_are_404(self, client_as, principal, wing_b):
        assert (
            client_as(principal).get(reverse("behavior:daily_export", args=["doc"])).status_code
            == 404
        )
        assert (
            client_as(principal)
            .get(reverse("behavior:daily_export", args=["pdf"]) + "?wing=not-a-uuid")
            .status_code
            == 404
        )

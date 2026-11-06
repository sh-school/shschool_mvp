"""[BEHAVIOR] التقرير السلوكي اليومي: صفحةٌ بتاريخ يوم وتصديرُ PDF وExcel (W-20261107-004، بلاغ SOS-20261018-CA7E).

يحرس: يومَ المخالفة (الحصّةُ إن وُجدت وإلا الكتابة)، ونطاقَ الدور (مشرفُ الجناح لجناحه و404 خارجَه، والمعلّمُ لطلبته)،
وتطابقَ الملفّين مع الشاشة عدداً وترتيباً، وسطرَ التدقيق بلا وصفٍ، وغيابَ الرقم الشخصيّ وولي الأمر، وثباتَ عدد الاستعلامات.
"""

import datetime as dt
from io import BytesIO
from unittest import mock

import pytest
from django.db import connection
from django.http import Http404
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from behavior.models import BehaviorInfraction
from behavior.selectors import daily_infractions
from core.academic_calendar import academic_year_for_school
from core.models import AuditLog
from operations.models import Session
from tests.conftest import BehaviorInfractionFactory
from tests.test_period_register import klass, supervisor, teacher  # noqa: F401
from tests.test_supervisor_behavior_scope import (  # noqa: F401 — أجهزةُ الجناح نفسُها
    far_klass,
    mine,
    principal,
    theirs,
)

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

DAILY = "behavior:daily_report"
DESCRIPTION = "وصفٌ سرّيّ لا يخرج في الملفّ"


@pytest.fixture
def year(school, seeded_calendar):  # noqa: F811
    """عامُ الشعبة والجناح بعد بذر التقويم: الساعةُ مثبَّتة، فبدونه يُحسب عامٌ احتياطيٌّ غيرُ عامِ نطاق المشرف."""
    return academic_year_for_school(school)


def _on(day, student, school, reporter, **extra):
    """مخالفةٌ يومُ كتابتها `day` (`date` يُضبط بعد الإنشاء لأنّه `auto_now_add`)."""
    inf = BehaviorInfractionFactory(
        school=school, student=student, reported_by=reporter, description=DESCRIPTION, **extra
    )
    BehaviorInfraction.objects.filter(pk=inf.pk).update(date=day)
    return inf


def _request(user, school):
    request = RequestFactory().get("/")
    request.user = user
    request.school = school
    return request


def _names(data):
    return [r["student"] for r in data["rows"]]


class TestTheDay:
    def test_default_is_today(self, client_as, school, principal, mine, theirs):  # noqa: F811
        today = timezone.localdate()
        _on(today, mine, school, principal)
        _on(today - dt.timedelta(days=1), theirs, school, principal)
        response = client_as(principal).get(reverse(DAILY))
        assert response.status_code == 200
        assert [r["student"] for r in response.context["rows"]] == [mine.full_name]

    def test_invalid_date_falls_back_to_today(self, client_as, principal):  # noqa: F811
        response = client_as(principal).get(reverse(DAILY), {"date": "ليس-تاريخا"})
        assert response.status_code == 200
        assert response.context["day_value"] == timezone.localdate().isoformat()

    def test_auto_infraction_corrected_later_shows_on_its_session_day(
        self,
        school,
        principal,
        mine,
        klass,
        teacher,  # noqa: F811
    ):
        session_day = dt.date(2026, 9, 13)
        session = Session.objects.create(
            school=school,
            class_group=klass,
            teacher=teacher,
            date=session_day,
            start_time=dt.time(7, 10),
            end_time=dt.time(7, 55),
            status="scheduled",
        )
        # كُتبت بعد ثلاثة أيّام من حصّتها (تصحيحُ المشرف لاحقاً) فيومُ كتابتها غيرُ يوم حصّتها.
        _on(
            session_day + dt.timedelta(days=3),
            mine,
            school,
            principal,
            session=session,
            auto_rule="period_tardy",
        )
        request = _request(principal, school)
        assert _names(daily_infractions(request, school, session_day)) == [mine.full_name]
        written = session_day + dt.timedelta(days=3)
        assert _names(daily_infractions(request, school, written)) == []


class TestScope:
    def test_supervisor_sees_his_wing_only(self, school, supervisor, principal, mine, theirs):  # noqa: F811
        today = timezone.localdate()
        _on(today, mine, school, principal)
        _on(today, theirs, school, principal)
        data = daily_infractions(_request(supervisor, school), school, today)
        assert _names(data) == [mine.full_name]
        assert [w.code for w in data["wings"]] == ["w1"]

    def test_supervisor_gets_404_for_a_wing_outside_his_own(
        self,
        school,
        supervisor,
        far_klass,
        mine,  # noqa: F811
    ):
        far_wing = far_klass.wing
        with pytest.raises(Http404):
            daily_infractions(
                _request(supervisor, school), school, timezone.localdate(), wing_id=str(far_wing.pk)
            )

    def test_unknown_wing_is_404_not_empty(self, school, principal):  # noqa: F811
        with pytest.raises(Http404):
            daily_infractions(
                _request(principal, school),
                school,
                timezone.localdate(),
                wing_id="00000000-0000-0000-0000-000000000000",
            )

    def test_teacher_sees_his_students(self, client_as, school, teacher, principal, mine, theirs):  # noqa: F811
        today = timezone.localdate()
        _on(today, mine, school, principal)
        _on(today, theirs, school, principal)
        with mock.patch("behavior.selectors.get_teacher_student_ids", return_value={mine.id}):
            response = client_as(teacher).get(reverse(DAILY))
        assert response.status_code == 200
        assert [r["student"] for r in response.context["rows"]] == [mine.full_name]

    def test_wing_and_grade_filters(self, school, principal, mine, theirs, far_klass):  # noqa: F811
        today = timezone.localdate()
        _on(today, mine, school, principal)
        _on(today, theirs, school, principal)
        request = _request(principal, school)
        by_wing = daily_infractions(request, school, today, wing_id=str(far_klass.wing.pk))
        assert _names(by_wing) == [theirs.full_name]
        assert _names(daily_infractions(request, school, today, grade="G7")) == [mine.full_name]


class TestExports:
    def _two_rows(self, school, principal, mine, theirs):  # noqa: F811
        today = timezone.localdate()
        _on(today, theirs, school, principal, level=2)
        _on(today, mine, school, principal, level=1)
        return today

    def test_xlsx_matches_screen_and_audits_without_description(
        self,
        client_as,
        school,
        principal,
        mine,
        theirs,  # noqa: F811
    ):
        from openpyxl import load_workbook

        today = self._two_rows(school, principal, mine, theirs)
        client = client_as(principal)
        shown = [r["student"] for r in client.get(reverse(DAILY)).context["rows"]]
        response = client.get(reverse("behavior:daily_xlsx"), {"date": today.isoformat()})
        assert response.status_code == 200
        ws = load_workbook(BytesIO(response.content)).active
        header = next(row for row in ws.iter_rows(values_only=True) if row and row[0] == "م")
        assert header[1:] == ("الطالب", "الشعبة", "المخالفة", "الدرجة", "الخطوة", "الراصد")
        exported = [row[1] for row in ws.iter_rows(values_only=True) if isinstance(row[0], int)]
        assert exported == shown and len(exported) == 2
        text = " ".join(str(c) for row in ws.iter_rows(values_only=True) for c in row if c)
        assert DESCRIPTION not in text
        assert "الرقم الشخصي" not in text and "ولي" not in text
        log = AuditLog.objects.filter(action="export", changes__kind="behavior.daily_xlsx").get()
        assert log.changes["rows"] == 2 and log.changes["full_national_id"] is False
        assert DESCRIPTION not in str(log.changes) + log.object_repr

    def test_pdf_matches_screen_and_audits(self, client_as, school, principal, mine, theirs):  # noqa: F811
        today = self._two_rows(school, principal, mine, theirs)
        captured = {}

        def fake_render(html, paper_size="A4"):
            captured["html"] = html
            return b"%PDF-fake"

        with mock.patch("core.pdf_utils.render_pdf_bytes", fake_render):
            response = client_as(principal).get(
                reverse("behavior:daily_pdf"), {"date": today.isoformat()}
            )
        assert response.status_code == 200 and response["Content-Type"] == "application/pdf"
        html = captured["html"]
        assert html.index(mine.full_name) < html.index(
            theirs.full_name
        )  # ترتيبُ الشاشة: 7/1 قبل 8/2
        assert DESCRIPTION not in html and "الرقم الشخصي" not in html
        log = AuditLog.objects.filter(action="export", changes__kind="behavior.daily_pdf").get()
        assert log.changes["rows"] == 2

    def test_real_pdf_renders_arabic(self, client_as, school, principal, mine, theirs):  # noqa: F811
        today = self._two_rows(school, principal, mine, theirs)
        response = client_as(principal).get(
            reverse("behavior:daily_pdf"), {"date": today.isoformat()}
        )
        assert response.status_code == 200
        assert response.content.startswith(b"%PDF")


class TestQueryCount:
    def test_queries_do_not_grow_with_rows(self, school, principal, mine, theirs, klass):  # noqa: F811
        from tests.conftest import StudentEnrollmentFactory, UserFactory

        today = timezone.localdate()
        request = _request(principal, school)

        def count():
            with CaptureQueriesContext(connection) as ctx:
                daily_infractions(request, school, today)
            return len(ctx)

        _on(today, mine, school, principal)
        count()  # تسخينٌ: أوّلُ نداءٍ يملأ مخبّآتِ التقويم والنطاق فلا يُقاس
        before = count()
        for i in range(6):
            kid = UserFactory(full_name=f"طالب إضافي {i}")
            StudentEnrollmentFactory(student=kid, class_group=klass)
            _on(today, kid, school, principal)
        assert count() == before

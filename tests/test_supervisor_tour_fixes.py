"""ما كشفته جولةُ المتصفّح (2026-09-16) على شاشات المشرف والنائب — كلُّ إصلاحٍ باختبار.

الجولةُ مرّت بحسابَي المشرف والنائب على الجوّال والحاسوب، وراجع مراجعون مستقلّون صورَها.
"""

import datetime as dt

import pytest
from django.urls import reverse

from core.models import ParentStudentLink
from operations.guardian_contact import ContactError, log_contact
from operations.models import GuardianContact
from tests.conftest import MembershipFactory, RoleFactory, UserFactory
from tests.test_absence_excuses import (  # noqa: F401 — التجهيزاتُ نفسُها
    MONDAY,
    _absent_day,
    _back,
    _report,
    vice_admin,
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

THURSDAY = SUNDAY + dt.timedelta(days=4)


class TestTheCallIsAboutARecordedAbsence:
    def test_a_call_for_a_day_he_attended_is_refused(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        """صفحةُ التصحيح كانت تملأ التاريخَ باليوم، فتسجّل ضغطةٌ «ردّ» ليومٍ حضره — ولا تُحذف."""
        _back(school, klass, teacher, supervisor, SUNDAY)

        with pytest.raises(ContactError, match="لا غيابَ مرصوداً"):
            log_contact(
                student=kids[0],
                school=school,
                absence_date=SUNDAY,
                outcome="answered",
                by=supervisor,
            )
        assert not GuardianContact.objects.exists()

    def test_the_correction_page_points_at_the_last_absence_not_today(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _absent_day(school, klass, kids[0], teacher, supervisor)
        _back(school, klass, teacher, supervisor, MONDAY)

        response = client_as(supervisor).get(
            reverse("wings:student_events", args=[klass.id, kids[0].id])
        )

        body = response.content.decode()
        assert response.context["excuse_day"] == SUNDAY
        assert 'value="2026-09-13"' in body
        assert response.context["events_count"] == 7
        assert "احفظ العذر" in body and "اقبل العذر" not in body


class TestTheFileShowsWhomToCall:
    def test_the_guardian_and_his_phone_are_on_the_file(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        father = UserFactory(
            full_name="وليُّ أمرٍ تجريبيّ", national_id="29300000081", phone="55512345"
        )
        MembershipFactory(
            user=father, school=school, role=RoleFactory(school=school, name="parent")
        )
        ParentStudentLink.objects.create(
            school=school, parent=father, student=kids[0], relationship="father"
        )
        _absent_day(school, klass, kids[0], teacher, supervisor)

        body = (
            client_as(supervisor)
            .get(reverse("wings:absence_file", args=[kids[0].id]))
            .content.decode()
        )

        assert "وليُّ أمرٍ تجريبيّ" in body
        assert 'href="tel:55512345"' in body

    def test_notify_opens_the_call_panel_on_its_day(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _absent_day(school, klass, kids[0], teacher, supervisor)
        url = reverse("wings:absence_file", args=[kids[0].id])

        opened = client_as(supervisor).get(url, {"call": "2026-09-13"}).content.decode()
        closed = client_as(supervisor).get(url).content.decode()

        assert '<details class="af-act" open>' in opened
        assert '<details class="af-act" open>' not in closed

    def test_the_dashboard_says_notify_and_opens_the_panel(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        from tests.test_period_register import _periods

        _absent_day(school, klass, kids[0], teacher, supervisor, day=SUNDAY)
        _periods(school, klass, teacher, 7, day=MONDAY)

        from unittest import mock

        with mock.patch("django.utils.timezone.localdate", return_value=MONDAY):
            body = client_as(supervisor).get(reverse("dashboard")).content.decode()

        assert "?call=2026-09-13#day-2026-09-13" in body
        assert "أخطِر" in body


class TestTheVicePage:
    def test_each_request_is_a_card_with_two_labelled_forms_and_the_file(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor, vice_admin
    ):
        from operations.excuses import grant_excuse

        _absent_day(school, klass, kids[0], teacher, supervisor)
        _back(school, klass, teacher, supervisor, MONDAY)
        grant_excuse(
            student=kids[0],
            school=school,
            date_from=SUNDAY,
            date_to=SUNDAY,
            kind="medical",
            document=_report(),
            by=supervisor,
            today=THURSDAY,
            forward_if_late=True,
        )

        body = client_as(vice_admin).get(reverse("wings:excuse_requests")).content.decode()

        assert "<table" not in body.split("بانتظار قرارك", 1)[1]
        assert body.count('class="xr-form') == 2
        assert "سببُ القبول" in body and "سببُ الرفض" in body
        assert reverse("wings:absence_file", args=[kids[0].id]) in body

    def test_the_vice_admin_dashboard_is_his_own(
        self, client_as, school, seeded_calendar, vice_admin
    ):
        body = client_as(vice_admin).get(reverse("dashboard")).content.decode()

        assert "لوحة النائب الإداريّ" in body
        assert "لوحة تحكم المدير" not in body

    def test_accepting_counts_periods_as_the_file_does(
        self, client_as, school, seeded_calendar, klass, kids, teacher, other_teacher, supervisor
    ):
        """زوجُ الاختيار حصّتان في خانةٍ واحدة: الرسالةُ تعدّ الخانات (7) كما يعدّها الملفّ، لا السجلّات (8)."""
        from django.contrib.messages import get_messages

        from operations.models import StudentAttendance
        from tests.test_period_register import _elective_twin

        _absent_day(school, klass, kids[0], teacher, supervisor)
        twin = _elective_twin(school, klass, other_teacher)
        StudentAttendance.objects.create(
            session=twin, student=kids[0], school=school, status="absent", marked_by=supervisor
        )

        response = client_as(supervisor).post(
            reverse("wings:absence_file_excuse", args=[kids[0].id]),
            {
                "date_from": "2026-09-13",
                "date_to": "2026-09-13",
                "kind": "bereavement",
                "notes": "الجدّ",
            },
        )

        texts = [str(m) for m in get_messages(response.wsgi_request)]
        assert any("وغُطّي 7 حصّةً" in t for t in texts), texts


class TestTheSupervisorsFrame:
    def test_his_student_links_are_one_dropdown(
        self, client_as, school, seeded_calendar, klass, supervisor
    ):
        body = client_as(supervisor).get(reverse("dashboard")).content.decode()

        assert 'id="btn-wing-students"' in body
        assert 'id="m-wing-students"' in body
        for name in (
            "wings:student_search",
            "daily_report",
            "behavior:report_infraction",
            "behavior:dashboard",
        ):
            assert f'href="{reverse(name)}"' in body, name
        assert "شؤون طلبة جناحي</a>" not in body, "لا روابطَ مستقلّةَ تلفّ الشريط"

    def test_a_tile_he_cannot_open_is_not_shown(
        self, client_as, school, seeded_calendar, klass, supervisor
    ):
        body = client_as(supervisor).get(reverse("dashboard")).content.decode()

        assert reverse("staff_affairs:dashboard") not in body
        assert "طلبة جناحي" in body

    def test_breadcrumbs_have_no_double_separator_and_the_dashboard_no_duplicate(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        import re

        _absent_day(school, klass, kids[0], teacher, supervisor)
        client = client_as(supervisor)
        for url in (reverse("dashboard"), reverse("wings:absence_file", args=[kids[0].id])):
            crumbs = re.search(
                r'<nav class="breadcrumbs".*?</nav>', client.get(url).content.decode(), re.S
            ).group(0)
            seps = re.findall(r"bc-sep[^>]*>/</span>\s*(<[^>]+>)", crumbs)
            assert all("bc-sep" not in nxt for nxt in seps), url
            assert crumbs.count(">الرئيسية<") == 1, url


class TestStudentAffairsForTheSupervisor:
    def test_no_attendance_yet_shows_a_dash_not_zero_percent(
        self, client_as, school, seeded_calendar, klass, supervisor
    ):
        response = client_as(supervisor).get(reverse("student_affairs:attendance_overview"))

        assert response.status_code == 200
        assert response.context["pct_label"] == "—"

    def test_the_trend_skips_days_without_records(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        from unittest import mock

        _absent_day(school, klass, kids[0], teacher, supervisor)
        with mock.patch("django.utils.timezone.localdate", return_value=THURSDAY):
            response = client_as(supervisor).get(reverse("student_affairs:attendance_overview"))

        import json

        assert json.loads(response.context["chart_labels_json"]) == ["13/9"]

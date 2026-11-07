"""التقرير السلوكيّ اليوميّ (W-20261107-013، بلاغ SOS-20261018-CA7E ب1): صفحةٌ بتاريخ يومٍ وتصديرٌ PDF وExcel.

يومُ المخالفة يومُ حصّتها إن وُجدت وإلا `date` (يومُ الكتابة)؛ والنطاقُ نطاقُ صاحب الطلب؛ والملفّان يطابقان الشاشة
عدداً وترتيباً ويكتب العاملُ سطرَ تدقيقٍ بلا وصفٍ؛ والاستعلاماتُ ثابتةٌ أمام عدد الصفوف.
"""

import datetime as dt
from io import BytesIO
from unittest import mock

import openpyxl
import pytest
from django.db import connection
from django.http import Http404
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from behavior.models import BehaviorInfraction, ViolationCategory
from behavior.selectors import daily_report
from core.exports.runner import run_job
from core.models import AuditLog, ExportJob
from operations.models import Session
from tests.conftest import (
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)
from tests.test_period_register import klass, supervisor, year  # noqa: F401
from tests.test_supervisor_behavior_scope import (  # noqa: F401 — أجهزةُ الجناح والمشرف نفسُها
    far_klass,
    mine,
    principal,
    theirs,
)
from tests.visual_snapshots import FIXED_NOW

# الساعةُ مثبَّتةٌ: «اليوم» يُقرأ في الاختبار وفي التقرير معاً فلا يتقاطعان عند منتصف الليل
pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

# «اليوم» هو يومُ الساعة المثبَّتة نفسُه الذي يقرؤه التقرير (لا يومُ استيراد الملفّ)
TODAY = timezone.localdate(FIXED_NOW)
YESTERDAY = TODAY - dt.timedelta(days=1)
DESCRIPTION = "وصفٌ سرّيٌّ لا يخرج من الصفحة ولا من الملفّ"


def _infraction(school, student, *, session=None, rule="", level=1, category=None, by=None):
    inf = BehaviorInfraction.objects.create(
        school=school,
        student=student,
        reported_by=by,
        session=session,
        auto_rule=rule,
        level=level,
        violation_category=category,
        description=DESCRIPTION,
    )
    # `auto_now_add` يقرأ تاريخَ النظام الحقيقيّ لا الساعةَ المثبَّتة، فنضبط يومَ الكتابة على يوم الاختبار
    BehaviorInfraction.objects.filter(pk=inf.pk).update(date=TODAY)
    inf.date = TODAY
    return inf


def _session(school, group, teacher, day):
    return Session.objects.create(
        school=school,
        class_group=group,
        teacher=teacher,
        date=day,
        start_time=dt.time(8, 0),
        end_time=dt.time(8, 45),
        status="completed",
    )


@pytest.fixture
def staff(school):
    user = UserFactory(full_name="الراصد")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


class TestTheDayOfTheInfraction:
    def test_an_auto_infraction_corrected_later_shows_on_its_session_day(
        self,
        school,
        seeded_calendar,
        klass,
        mine,
        staff,
        principal,  # noqa: F811
    ):
        # التصحيحُ يُكتب اليومَ (`date` = اليوم) عن حصّةٍ كانت أمس
        past = _session(school, klass, staff, YESTERDAY)
        _infraction(school, mine, session=past, rule="period_tardy")

        yesterday = daily_report(school, principal, {"date": YESTERDAY.isoformat()})
        today = daily_report(school, principal, {"date": TODAY.isoformat()})

        assert [r["student"] for r in yesterday["rows"]] == [mine.full_name]
        assert yesterday["rows"][0]["reporter"] == "الرصد الآلي"
        assert today["rows"] == []

    def test_a_manual_infraction_without_a_session_uses_its_written_day(
        self,
        school,
        seeded_calendar,
        klass,
        mine,
        staff,
        principal,  # noqa: F811
    ):
        _infraction(school, mine, by=staff)

        assert len(daily_report(school, principal, {})["rows"]) == 1  # الافتراضيُّ اليوم
        assert daily_report(school, principal, {"date": YESTERDAY.isoformat()})["rows"] == []

    def test_a_broken_date_falls_back_to_today(
        self,
        school,
        seeded_calendar,
        klass,
        mine,
        staff,
        principal,  # noqa: F811
    ):
        _infraction(school, mine, by=staff)

        assert len(daily_report(school, principal, {"date": "ليس تاريخاً"})["rows"]) == 1


class TestTheScope:
    def test_the_supervisor_gets_his_wing_and_a_404_outside_it(
        self,
        school,
        seeded_calendar,
        mine,
        theirs,
        supervisor,
        far_klass,
        staff,  # noqa: F811
    ):
        _infraction(school, mine, by=staff)
        _infraction(school, theirs, by=staff)

        data = daily_report(school, supervisor, {})
        assert [r["student"] for r in data["rows"]] == [mine.full_name]
        assert len(data["wing_options"]) == 1

        with pytest.raises(Http404):
            daily_report(school, supervisor, {"wing": str(far_klass.wing_id)})

    def test_the_principal_filters_by_wing_and_grade(
        self,
        school,
        seeded_calendar,
        mine,
        theirs,
        supervisor,
        far_klass,
        staff,
        principal,  # noqa: F811
    ):
        _infraction(school, mine, by=staff)
        _infraction(school, theirs, by=staff)

        everyone = daily_report(school, principal, {})
        by_wing = daily_report(school, principal, {"wing": str(far_klass.wing_id)})
        by_grade = daily_report(school, principal, {"grade": "G7"})

        assert len(everyone["rows"]) == 2
        assert [r["student"] for r in by_wing["rows"]] == [theirs.full_name]
        assert [r["student"] for r in by_grade["rows"]] == [mine.full_name]

    def test_a_teacher_sees_only_his_students(
        self,
        school,
        seeded_calendar,
        mine,
        theirs,
        staff,
        principal,  # noqa: F811
    ):
        _infraction(school, mine, by=staff)
        _infraction(school, theirs, by=staff)

        with mock.patch("behavior.selectors.get_teacher_student_ids", return_value={theirs.id}):
            data = daily_report(school, staff, {})

        assert [r["student"] for r in data["rows"]] == [theirs.full_name]


class TestThePage:
    def test_it_lists_the_columns_without_description_id_or_guardian(
        self,
        school,
        seeded_calendar,
        klass,
        mine,
        staff,
        principal,
        client_as,  # noqa: F811
    ):
        mine.national_id = "29000000001"
        mine.save(update_fields=["national_id"])
        category = ViolationCategory.objects.create(code="1-77", name_ar="إزعاجٌ في الممرّ")
        _infraction(school, mine, by=staff, category=category)

        resp = client_as(principal).get(reverse("behavior:daily_report"))

        body = resp.content.decode()
        assert resp.status_code == 200
        for text in (mine.full_name, "07/1", "إزعاجٌ في الممرّ", "الدرجة", "الخطوة", staff.full_name):
            assert text in body
        assert DESCRIPTION not in body and "29000000001" not in body
        table = body[body.index("<table") : body.index("</table>")]
        assert "ولي" not in table and "وليّ" not in table  # لا عمودَ لوليّ الأمر في الجدول

    def test_it_is_closed_to_those_without_the_capability(self, school, seeded_calendar, client_as):
        parent = UserFactory(full_name="وليّ")
        MembershipFactory(
            user=parent, school=school, role=RoleFactory(school=school, name="parent")
        )

        assert client_as(parent).get(reverse("behavior:daily_report")).status_code in (302, 403)

    def test_an_unknown_wing_is_404_in_the_page(
        self,
        school,
        seeded_calendar,
        principal,
        client_as,  # noqa: F811
    ):
        url = reverse("behavior:daily_report")

        assert client_as(principal).get(url, {"wing": "ليس-جناحاً"}).status_code == 404

    def test_the_menu_tab_sits_beside_statistics_for_those_who_can_open_it(
        self,
        school,
        seeded_calendar,
        principal,
        client_as,  # noqa: F811
    ):
        resp = client_as(principal).get(reverse("behavior:daily_report"))

        assert reverse("behavior:daily_report") in resp.content.decode()
        assert "التقرير اليومي" in resp.content.decode()

    def test_the_social_worker_menu_has_the_tab_after_statistics(
        self, school, seeded_calendar, client_as
    ):
        worker = UserFactory(full_name="أخصائي")
        MembershipFactory(
            user=worker, school=school, role=RoleFactory(school=school, name="social_worker")
        )

        html = client_as(worker).get(reverse("behavior:daily_report")).content.decode()

        menu = html[html.index('id="m-sw-behavior"') :]
        assert menu.index(reverse("behavior:statistics")) < menu.index(
            reverse("behavior:daily_report")
        )


def _run(school, user, kind, query):
    job = ExportJob.objects.create(school=school, requested_by=user, kind=kind, query_string=query)
    assert run_job(str(job.id))["ok"] is True
    job.refresh_from_db()
    return job


class TestTheExports:
    @pytest.fixture
    def several(self, school, seeded_calendar, klass, mine, theirs, staff):  # noqa: F811
        extra = UserFactory(full_name="أ طالبٌ ثالث")
        MembershipFactory(
            user=extra, school=school, role=RoleFactory(school=school, name="student")
        )
        StudentEnrollmentFactory(student=extra, class_group=klass)
        for student in (mine, extra, theirs):
            _infraction(school, student, by=staff, level=2)

    def test_xlsx_matches_the_screen_in_count_and_order_and_audits_without_text(
        self,
        school,
        several,
        principal,  # noqa: F811
    ):
        screen = daily_report(school, principal, {})["rows"]

        job = _run(school, principal, "behavior.daily_xlsx", "")

        sheet = openpyxl.load_workbook(BytesIO(bytes(job.content))).active
        cells = [[c for c in row if c is not None] for row in sheet.iter_rows(values_only=True)]
        names = [r[1] for r in cells if len(r) > 1 and r[1] in {s["student"] for s in screen}]
        assert names == [s["student"] for s in screen] and len(names) == 3
        flat = " ".join(str(c) for row in cells for c in row)
        assert DESCRIPTION not in flat
        trail = AuditLog.objects.get(action="export", object_repr="behavior.daily_xlsx:built")
        assert trail.changes["rows"] == 3 and trail.changes["full_national_id"] is False
        assert DESCRIPTION not in str(trail.changes) and DESCRIPTION not in trail.object_repr

    def test_pdf_is_built_with_the_same_row_count(self, school, several, principal):  # noqa: F811
        job = _run(school, principal, "behavior.daily_pdf", "")

        assert bytes(job.content).startswith(b"%PDF")
        trail = AuditLog.objects.get(action="export", object_repr="behavior.daily_pdf:built")
        assert trail.changes["rows"] == 3

    def test_the_buttons_go_through_the_export_centre(
        self,
        school,
        several,
        principal,
        client_as,  # noqa: F811
    ):
        resp = client_as(principal).get(
            reverse("behavior:daily_report_xlsx"), HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )

        assert resp.status_code == 202 and "status_url" in resp.json()


class TestTheQueryCount:
    def test_queries_do_not_grow_with_rows(
        self,
        school,
        seeded_calendar,
        klass,
        mine,
        staff,
        principal,  # noqa: F811
    ):
        def count():
            with CaptureQueriesContext(connection) as ctx:
                daily_report(school, principal, {})
            return len(ctx)

        _infraction(school, mine, by=staff)
        count()  # تسخينٌ: ما يُخزَّن على المستخدم في أوّل نداءٍ لا يُحسب على الصفوف
        few = count()
        for i in range(8):
            student = UserFactory(full_name=f"طالب {i}")
            MembershipFactory(
                user=student, school=school, role=RoleFactory(school=school, name="student")
            )
            StudentEnrollmentFactory(student=student, class_group=klass)
            _infraction(school, student, by=staff)

        assert count() == few
        assert len(daily_report(school, principal, {})["rows"]) == 9

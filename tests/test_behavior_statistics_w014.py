"""إحصاءُ السلوك (W-20261107-014، بلاغ SOS-20261018-CA7E ب2): العامُ يغيّر الأرقام، ومرشّحُ الشهر، والتوزيعات، والتصدير.

النافذةُ من التقويم الأكاديميّ في الصفحتين (اللوحة والإحصاء)؛ وكلُّ توزيعٍ مجموعُه الإجماليُّ فلا يختفي سطرُ «بلا تصنيف»؛
والشعبةُ قيدُ الطالب الجاريُّ فيُعدّ مرّةً واحدة؛ والمقيَّدُ بجناحه يرى نطاقَه في الشاشة والملفّين.
"""

import datetime as dt
from io import BytesIO

import openpyxl
import pytest
from django.urls import reverse

from behavior.models import BehaviorInfraction, ViolationCategory
from behavior.services import (
    NO_WING_LABEL,
    UNCATEGORIZED_LABEL,
    academic_year_dates,
    behavior_statistics_data,
)
from behavior.views import _behaviour_year_window
from core.exports.runner import run_job
from core.models import ExportJob
from tests.conftest import StudentEnrollmentFactory, UserFactory
from tests.test_period_register import klass, supervisor, year  # noqa: F401
from tests.test_supervisor_behavior_scope import (  # noqa: F401 — أجهزةُ الجناح والمشرف نفسُها
    far_klass,
    mine,
    principal,
    theirs,
)

pytestmark = pytest.mark.django_db


def _infraction(school, student, day, *, level=1, category=None, resolved=False):
    inf = BehaviorInfraction.objects.create(
        school=school,
        student=student,
        level=level,
        violation_category=category,
        description="وصفٌ",
        is_resolved=resolved,
    )
    # `date` هو `auto_now_add`؛ نضبطه على يومٍ داخل نافذة العام المقصود
    BehaviorInfraction.objects.filter(pk=inf.pk).update(date=day)
    return inf


@pytest.fixture
def category(db, school):
    return ViolationCategory.objects.create(code="T-1", name_ar="بندٌ للاختبار", degree=2)


@pytest.fixture
def start(school, seeded_calendar):
    return academic_year_dates(school, seeded_calendar)[0]


def _sums(data):
    return {
        key: sum(row["count"] for row in data[key])
        for key in ("degree_rows", "category_rows", "wing_rows", "class_rows")
    }


class TestYearAndMonth:
    def test_changing_the_year_changes_the_numbers(
        self,
        school,
        seeded_calendar,
        start,
        mine,
        principal,  # noqa: F811
    ):
        previous = f"{start.year - 1}-{start.year}"
        _infraction(school, mine, start + dt.timedelta(days=40))
        _infraction(school, mine, start + dt.timedelta(days=41))
        _infraction(school, mine, dt.date(start.year - 1, 10, 5))

        now = behavior_statistics_data(school, principal, {"year": seeded_calendar})
        before = behavior_statistics_data(school, principal, {"year": previous})

        assert (now["total"], before["total"]) == (2, 1)
        assert before["year"] == previous and before["window_start"].year == start.year - 1

    def test_a_month_narrows_the_numbers_and_the_months_add_up_to_the_year(
        self,
        school,
        seeded_calendar,
        start,
        mine,
        principal,  # noqa: F811
    ):
        first = dt.date(start.year, 10, 3)
        _infraction(school, mine, first)
        _infraction(school, mine, first + dt.timedelta(days=1), level=3)
        _infraction(school, mine, dt.date(start.year, 11, 9))

        whole = behavior_statistics_data(school, principal, {"year": seeded_calendar})
        october = behavior_statistics_data(
            school, principal, {"year": seeded_calendar, "month": f"{start.year}-10"}
        )

        assert (whole["total"], october["total"]) == (3, 2)
        assert october["by_level"][3] == 1
        assert sum(row["count"] for row in whole["monthly"]) == whole["total"]
        assert sum(row["count"] for row in october["monthly"]) == whole["total"]

    def test_a_month_outside_the_window_is_ignored(
        self,
        school,
        seeded_calendar,
        start,
        mine,
        principal,  # noqa: F811
    ):
        _infraction(school, mine, dt.date(start.year, 10, 3))

        data = behavior_statistics_data(school, principal, {"month": "1999-01"})

        assert data["month"] == "" and data["total"] == 1

    def test_the_window_comes_from_the_calendar_on_both_pages(self, school, seeded_calendar):
        from core.academic_calendar import academic_year_window

        assert academic_year_dates(school) == academic_year_window(school)
        assert _behaviour_year_window(school) == academic_year_dates(school)


class TestBreakdowns:
    def test_uncategorized_is_its_own_row_and_every_breakdown_adds_up(
        self,
        school,
        seeded_calendar,
        start,
        mine,
        theirs,
        category,
        principal,  # noqa: F811
    ):
        day = dt.date(start.year, 10, 3)
        _infraction(school, mine, day, category=category, level=2)
        _infraction(school, mine, day)
        _infraction(school, theirs, day)
        orphan = UserFactory(full_name="بلا قيد")
        _infraction(school, orphan, day)

        data = behavior_statistics_data(school, principal, {})

        rows = {row["label"]: row["count"] for row in data["category_rows"]}
        assert rows[UNCATEGORIZED_LABEL] == 3 and rows[category.name_ar] == 1
        assert data["category_rows"][-1]["label"] == UNCATEGORIZED_LABEL
        assert set(_sums(data).values()) == {data["total"]} == {4}
        assert {row["label"]: row["count"] for row in data["wing_rows"]}[NO_WING_LABEL] == 1

    def test_a_student_is_counted_once_in_the_current_enrollment(
        self,
        school,
        seeded_calendar,
        start,
        klass,
        far_klass,
        mine,
        principal,  # noqa: F811
    ):
        # قيدٌ ثانٍ نشطٌ للطالب نفسه في شعبةٍ أخرى من العام ذاته: كان الربطُ عبر كلّ القيود يضاعف العدّ
        StudentEnrollmentFactory(student=mine, class_group=far_klass)
        _infraction(school, mine, dt.date(start.year, 10, 3))

        data = behavior_statistics_data(school, principal, {})

        assert data["total"] == 1
        assert sum(row["count"] for row in data["top_classes"]) == 1
        assert sum(row["count"] for row in data["class_rows"]) == 1


class TestScope:
    def test_a_wing_supervisor_sees_only_the_wing_on_screen_and_in_files(
        self,
        school,
        seeded_calendar,
        start,
        mine,
        theirs,
        supervisor,  # noqa: F811
        client_as,
    ):
        day = dt.date(start.year, 10, 3)
        _infraction(school, mine, day)
        _infraction(school, theirs, day)
        _infraction(school, theirs, day)

        data = behavior_statistics_data(school, supervisor, {})
        assert data["total"] == 1 and data["is_scoped"] is True

        job = ExportJob.objects.create(
            school=school,
            requested_by=supervisor,
            kind="behavior.statistics_xlsx",
            query_string="",
        )
        # المشرفُ لا يملك قدرةَ الإحصاء (م5.7)؛ فيرفض المنفِّذُ الملفَّ ولا يُنتَج محتوىً من أي جناح
        assert run_job(str(job.id))["ok"] is False
        job.refresh_from_db()
        assert job.status != "done" and not job.content

        # الشاشةُ نفسُها مغلقةٌ على المشرف (م5.7: لا يرث إحصاءَ المدرسة)؛ فلا تسرّب شيئاً
        assert client_as(supervisor).get(reverse("behavior:statistics")).status_code == 403


class TestScreenAndExports:
    def test_the_screen_shows_the_filters_the_breakdowns_and_the_buttons(
        self,
        school,
        seeded_calendar,
        start,
        mine,
        category,
        principal,
        client_as,  # noqa: F811
    ):
        _infraction(school, mine, dt.date(start.year, 10, 3), category=category)

        resp = client_as(principal).get(
            reverse("behavior:statistics"), {"year": seeded_calendar, "month": f"{start.year}-10"}
        )

        html = resp.content.decode()
        assert resp.status_code == 200
        assert 'name="month"' in html and category.name_ar in html
        assert "?export=pdf&amp;" in html and "?export=xlsx&amp;" in html
        assert f"month={start.year}-10" in resp.context["export_query"]

    def test_the_files_are_built_and_audited_with_the_row_count(
        self,
        school,
        seeded_calendar,
        start,
        mine,
        category,
        principal,  # noqa: F811
    ):
        _infraction(school, mine, dt.date(start.year, 10, 3), category=category)
        _infraction(school, mine, dt.date(start.year, 10, 4))

        for kind, magic in (
            ("behavior.statistics_pdf", b"%PDF"),
            ("behavior.statistics_xlsx", b"PK"),
        ):
            job = ExportJob.objects.create(
                school=school, requested_by=principal, kind=kind, query_string=""
            )
            assert run_job(str(job.id))["ok"] is True
            job.refresh_from_db()
            assert bytes(job.content).startswith(magic)

        sheet = openpyxl.load_workbook(BytesIO(bytes(job.content))).active
        cells = [c for row in sheet.iter_rows(values_only=True) for c in row if c is not None]
        assert UNCATEGORIZED_LABEL in cells and category.name_ar in cells

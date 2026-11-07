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
    NO_ACTION_LABEL,
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
        for key in (
            "degree_rows",
            "category_rows",
            "action_rows",
            "step_rows",
            "wing_rows",
            "class_rows",
        )
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

        # الملفّان بنطاق الجناح نفسه: لا يدخل طالبُ الجناح الآخر في الجدول ولا في الأكثر مخالفةً
        for kind in ("behavior.statistics_xlsx", "behavior.statistics_pdf"):
            job = ExportJob.objects.create(
                school=school, requested_by=supervisor, kind=kind, query_string=""
            )
            assert run_job(str(job.id))["ok"] is True
            job.refresh_from_db()
            assert job.status == "done" and job.content
        sheet = openpyxl.load_workbook(
            BytesIO(bytes(ExportJob.objects.filter(kind="behavior.statistics_xlsx").get().content))
        ).active
        cells = [c for row in sheet.iter_rows(values_only=True) for c in row if c is not None]
        assert theirs.full_name not in cells

        # الشاشةُ تُفتح للمشرف وفيها طالبُه وحدَه
        resp = client_as(supervisor).get(reverse("behavior:statistics"))
        html = resp.content.decode()
        assert resp.status_code == 200
        assert mine.full_name in html and theirs.full_name not in html
        assert resp.context["total"] == 1
        assert [r["student__id"] for r in resp.context["top_students"]] == [mine.pk]

    def test_the_wing_supervisor_is_pinned_to_the_current_year(
        self,
        school,
        seeded_calendar,
        start,
        mine,
        supervisor,
        principal,  # noqa: F811
    ):
        previous = f"{start.year - 1}-{start.year}"
        _infraction(school, mine, start + dt.timedelta(days=40))
        _infraction(school, mine, dt.date(start.year - 1, 10, 5))

        pinned = behavior_statistics_data(school, supervisor, {"year": previous})
        wide = behavior_statistics_data(school, principal, {"year": previous})

        assert pinned["year"] == seeded_calendar and pinned["total"] == 1
        assert pinned["year_locked"] is True
        assert wide["year"] == previous and wide["total"] == 1 and wide["year_locked"] is False

    def test_a_teacher_scope_is_pinned_to_the_current_year(
        self,
        school,
        seeded_calendar,
        start,
        mine,
        theirs,
        principal,
        monkeypatch,  # noqa: F811
    ):
        teacher = UserFactory(full_name="معلّمٌ اصطناعي", national_id="29300000092")
        previous = f"{start.year - 1}-{start.year}"
        _infraction(school, mine, start + dt.timedelta(days=40))
        _infraction(school, mine, dt.date(start.year - 1, 10, 5))
        _infraction(school, theirs, start + dt.timedelta(days=40))
        # نطاقُ المعلّم طلبةُ شعبه الآن؛ والعامُ السابق لا يوسّعه
        monkeypatch.setattr("behavior.services.get_teacher_student_ids", lambda *a, **k: {mine.pk})

        data = behavior_statistics_data(school, teacher, {"year": previous})

        assert data["year"] == seeded_calendar and data["total"] == 1
        assert data["year_locked"] is True


class TestActions:
    def test_action_breakdowns_add_up_with_a_separate_none_row_and_no_free_text(
        self,
        school,
        seeded_calendar,
        start,
        mine,
        principal,  # noqa: F811
    ):
        day = dt.date(start.year, 10, 3)
        first = _infraction(school, mine, day)
        BehaviorInfraction.objects.filter(pk=first.pk).update(
            disciplinary_action_type="verbal_warning", escalation_step=1
        )
        _infraction(school, mine, day)
        third = _infraction(school, mine, day)
        BehaviorInfraction.objects.filter(pk=third.pk).update(action_taken="نصٌّ سرّيٌّ مشفّر")

        data = behavior_statistics_data(school, principal, {})

        for key in ("action_rows", "step_rows"):
            assert sum(row["count"] for row in data[key]) == data["total"] == 3
            assert data[key][-1] == {"label": NO_ACTION_LABEL, "count": 2}
        assert "نصٌّ سرّيٌّ مشفّر" not in repr(data["action_rows"] + data["step_rows"])

    def test_the_supervisor_sees_the_actions_of_his_wing_only(
        self,
        school,
        seeded_calendar,
        start,
        mine,
        theirs,
        supervisor,
        client_as,  # noqa: F811
    ):
        day = dt.date(start.year, 10, 3)
        _infraction(school, mine, day)
        BehaviorInfraction.objects.filter(student=theirs).delete()
        other = _infraction(school, theirs, day)
        BehaviorInfraction.objects.filter(pk=other.pk).update(
            disciplinary_action_type="written_pledge"
        )

        resp = client_as(supervisor).get(reverse("behavior:statistics"))

        assert resp.context["action_rows"] == [{"label": NO_ACTION_LABEL, "count": 1}]
        assert "التوزيع بالإجراء التأديبي" in resp.content.decode()


class TestMenuLink:
    @pytest.mark.parametrize(
        ("role", "shown"),
        [
            ("principal", True),
            ("vice_admin", True),
            ("student_affairs_coordinator", True),
            ("teacher", True),
            ("coordinator", True),
            ("admin_supervisor", True),
            ("teacher_assistant", False),
        ],
    )
    def test_the_link_shows_for_holders_and_not_for_the_assistant(
        self, school, role, shown, client_as
    ):
        from tests.test_behavior_committee_art_5_7 import _user_with

        resp = client_as(_user_with(school, role)).get(reverse("dashboard"), follow=True)
        html = resp.content.decode()

        assert (reverse("behavior:statistics") in html) is shown


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

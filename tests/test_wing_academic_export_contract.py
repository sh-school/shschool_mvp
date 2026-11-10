"""ترحيلُ التصدير للمعروض (W-20261109-007): سجلُّ الجناح وتقريرُ الوزارة وأذوناتُ الخروج والتقاريرُ الأكاديميّة وكشفُ الدرجات ونتائجُ الصفّ.

لكلّ جدولٍ ثلاثةُ أدوار (مدير ومشرفُ جناح ومعلّم): من لا تفتح له القدرةُ الشاشةَ لا يخرج له ملفّ، ومن يفتحها يخرج له
المعروضُ بنطاقه وحدَه، مرقَّماً ومفروزاً بالجناح ومحذوفَ الأعمدةِ المخفيّة.
"""

import datetime as dt
from io import BytesIO
from types import SimpleNamespace

import pytest
from django.core.exceptions import PermissionDenied
from django.http import QueryDict
from django.urls import reverse
from openpyxl import load_workbook

from academic_management import report_selectors
from academic_management.export_tables import ACADEMIC_TABLES
from assessments.export_tables import GRADEBOOK_TABLE
from assessments.models import SubjectClassSetup
from core.capabilities import has_capability
from core.exports import contract, registry
from core.models.academic import Wing
from operations.models import ExitPermit, Subject
from reports.export_tables import CLASS_RESULTS_TABLE
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)
from wings import ministry_selectors
from wings.exit_permit_services import request_permit
from wings.export_tables import EXIT_PERMITS_TABLE, MINISTRY_TABLE, REGISTER_TABLE

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

ROLES = ["principal", "wing_supervisor", "teacher"]


def _staff(school, role, name, national_id):
    user = UserFactory(full_name=name, national_id=national_id)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


def _pupil(school, name, national_id, klass):
    user = UserFactory(full_name=name, national_id=national_id)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="student"))
    # القيدُ ساري قبل اليوم المثبَّت (7 أكتوبر)، وإلّا لا يُحسب الطالب في الكشف (`on_roll`).
    StudentEnrollmentFactory(student=user, class_group=klass, enrolled_at=dt.date(2026, 9, 1))
    return user


@pytest.fixture
def world(school, seeded_calendar):
    """جناحان: الأوّلُ (ترتيب 1) بمشرفنا وطالبَين، والثاني (ترتيب 2) بمشرفٍ آخر وطالبٍ واحد؛ والأسماءُ أبجديّاً تخالف الجناح."""
    year = seeded_calendar
    mine = _staff(school, "admin_supervisor", "مشرفُ الجناح الأوّل", "29000000031")
    other = _staff(school, "admin_supervisor", "مشرفُ الجناح الثاني", "29000000032")
    wing1 = Wing.objects.create(
        school=school, code="w1", name="جناح 1", academic_year=year, supervisor=mine, order=1
    )
    wing2 = Wing.objects.create(
        school=school, code="w2", name="جناح 2", academic_year=year, supervisor=other, order=2
    )
    klass1 = ClassGroupFactory(
        school=school, grade="G7", section="1", academic_year=year, level_type="prep", wing=wing1
    )
    klass2 = ClassGroupFactory(
        school=school, grade="G8", section="2", academic_year=year, level_type="prep", wing=wing2
    )
    pupils = {
        "ahmad": _pupil(school, "أحمد سالم", "29000000041", klass1),
        "badr": _pupil(school, "بدر خالد", "29000000042", klass2),
        "layla": _pupil(school, "ليلى حمد", "29000000043", klass1),
    }
    return {"supervisor": mine, "other": other, "pupils": pupils, "klass1": klass1}


@pytest.fixture
def roles(world, principal_user, teacher_user):
    return {
        "principal": principal_user,
        "wing_supervisor": world["supervisor"],
        "teacher": teacher_user,
    }


def _file_rows(spec, user, school, query=""):
    """صفوفُ الملفّ كما يخرج Excel (بلا الترويسة والتذييل): كلُّ صفٍّ رقمُه في عموده الأوّل."""
    result = registry.get(spec.kind).build(school, user, QueryDict(query))
    sheet = load_workbook(BytesIO(result.content)).active
    rows = [
        [cell.value for cell in row]
        for row in sheet.iter_rows()
        if isinstance(row[0].value, int) and row[0].value >= 1
    ]
    return result, rows


def _gate(client_as, user, spec, url_name, **kwargs):
    """الدرسُ المشترك: من لا يحمل قدرةَ الجدول يُمنع (403)، ومن يحملها يُقبل طلبُه (مهمّةٌ خلفيّة)."""
    status = client_as(user).get(reverse(url_name, kwargs=kwargs or None)).status_code
    if has_capability(user, spec.capability):
        assert status != 403
    else:
        assert status == 403


class TestWingRegisterTable:
    def test_principal_gets_every_wing_sorted_by_wing_and_numbered(self, school, world, roles):
        result, rows = _file_rows(REGISTER_TABLE, roles["principal"], school)

        assert result.rows == len(rows) == 3
        assert [r[0] for r in rows] == [1, 2, 3]
        assert [r[2] for r in rows] == ["أحمد سالم", "ليلى حمد", "بدر خالد"]

    def test_wing_supervisor_gets_only_his_wing(self, school, world, roles):
        _result, rows = _file_rows(REGISTER_TABLE, roles["wing_supervisor"], school)

        assert sorted(r[2] for r in rows) == ["أحمد سالم", "ليلى حمد"]

    def test_the_wing_code_narrows_and_a_foreign_code_is_refused(self, school, world, roles):
        _result, rows = _file_rows(REGISTER_TABLE, roles["principal"], school, "wing=w2")
        assert [r[2] for r in rows] == ["بدر خالد"]

        with pytest.raises(Exception, match="ليس من أجنحتك"):
            _file_rows(REGISTER_TABLE, roles["wing_supervisor"], school, "wing=w2")

    def test_the_teacher_has_no_wing_so_the_file_is_empty(self, school, world, roles):
        _result, rows = _file_rows(REGISTER_TABLE, roles["teacher"], school)

        assert rows == []

    @pytest.mark.parametrize("who", ROLES)
    def test_the_capability_gate(self, client_as, roles, who):
        _gate(client_as, roles[who], REGISTER_TABLE, "wings:register_xlsx")

    def test_a_hidden_column_is_hidden_in_the_file(self, school, world, roles):
        result = registry.get(REGISTER_TABLE.kind).build(
            school, roles["principal"], QueryDict("hide=marks")
        )
        sheet = load_workbook(BytesIO(result.content)).active
        labels = [c.value for row in sheet.iter_rows() for c in row if c.value]

        assert not any(str(v).startswith("الحصص") for v in labels)


class TestExitPermitsTable:
    @pytest.fixture
    def permits(self, school, world):
        reason = ExitPermit.REASONS[0][0]
        pupils = world["pupils"]
        for key, by in (("ahmad", world["supervisor"]), ("badr", world["other"])):
            request_permit(by, school, pupils[key], reason=reason)

    def test_the_file_rows_equal_the_page_rows_for_every_role(
        self, client_as, school, world, roles, permits
    ):
        for who in ROLES:
            user = roles[who]
            response = client_as(user).get(reverse("wings:exit_permit_list"))
            _result, rows = _file_rows(EXIT_PERMITS_TABLE, user, school)
            if response.status_code != 200:
                assert not has_capability(user, EXIT_PERMITS_TABLE.capability)
                continue
            assert sorted(r[2] for r in rows) == sorted(
                p.student.full_name for p in response.context["permits"]
            ), who

    def test_the_principal_sees_both_wings_and_the_supervisor_only_his(
        self, school, world, roles, permits
    ):
        _r, all_rows = _file_rows(EXIT_PERMITS_TABLE, roles["principal"], school)
        _r, mine = _file_rows(EXIT_PERMITS_TABLE, roles["wing_supervisor"], school)

        assert [r[2] for r in all_rows] == ["أحمد سالم", "بدر خالد"] and [
            r[0] for r in all_rows
        ] == [1, 2]
        assert [r[2] for r in mine] == ["أحمد سالم"]

    def test_a_teacher_with_no_requests_gets_an_empty_file(self, school, world, roles, permits):
        _r, rows = _file_rows(EXIT_PERMITS_TABLE, roles["teacher"], school)

        assert rows == []

    @pytest.mark.parametrize("who", ROLES)
    def test_the_capability_gate(self, client_as, roles, who):
        _gate(client_as, roles[who], EXIT_PERMITS_TABLE, "wings:exit_permits_xlsx")


class TestMinistryTable:
    @pytest.fixture
    def fake_view(self, monkeypatch):
        """ملخّصٌ بغائبَين في جناحين: التصديرُ يفرزهما بالجناح لا بالاسم."""
        groups = [
            SimpleNamespace(short_code="8/2", wing=SimpleNamespace(order=2)),
            SimpleNamespace(short_code="7/1", wing=SimpleNamespace(order=1)),
        ]
        summary = SimpleNamespace(
            class_rows=[SimpleNamespace(group=g) for g in groups],
            ministered=[
                ministry_selectors.Ministered("أحمد", "8/2", False, "G8"),
                ministry_selectors.Ministered("بدر", "7/1", True, "G7", "جديد"),
            ],
        )
        view = ministry_selectors.MinistryView(
            summary, False, [("G7", "السابع"), ("G8", "الثامن")], "", [], "", ""
        )
        monkeypatch.setattr(ministry_selectors, "ministry_view", lambda *a, **k: view)

    def test_rows_are_sorted_by_wing_numbered_and_labelled(self, school, principal_user, fake_view):
        _result, rows = _file_rows(MINISTRY_TABLE, principal_user, school)

        assert [r[0] for r in rows] == [1, 2]
        assert [(r[1], r[3]) for r in rows] == [("السابع", "بدر"), ("الثامن", "أحمد")]
        assert rows[0][4:] == ["بعذر", "جديد"] and rows[1][4:] == ["بلا عذر", "—"]

    def test_the_filter_reaches_the_summary(self, school, principal_user, monkeypatch):
        seen = {}

        def fake(user, school_, params, today):
            seen.update(params.dict())
            return ministry_selectors.MinistryView(
                SimpleNamespace(class_rows=[], ministered=[]), False, [], "", [], "", ""
            )

        monkeypatch.setattr(ministry_selectors, "ministry_view", fake)
        _file_rows(MINISTRY_TABLE, principal_user, school, "date=2026-11-08&grade=G8&q=x")

        assert seen == {"date": "2026-11-08", "grade": "G8", "q": "x"}

    def test_the_real_summary_runs_for_a_wing_supervisor(self, school, world, roles):
        _result, rows = _file_rows(MINISTRY_TABLE, roles["wing_supervisor"], school)

        assert rows == []  # لا رصدَ في اليوم

    @pytest.mark.parametrize("who", ROLES)
    def test_the_capability_gate(self, client_as, roles, who):
        _gate(client_as, roles[who], MINISTRY_TABLE, "wings:ministry_xlsx")


class TestAcademicReports:
    DATA = {
        "quiz": {
            "rows": [
                {
                    "student_name": "أحمد",
                    "subject": "علوم",
                    "class_group": "7/1",
                    "title": "اختبار",
                    "date": dt.date(2026, 11, 2),
                    "raw_grade": 8.0,
                    "max_grade": 10.0,
                    "pct": 80.0,
                },
            ]
        },
        "exam_results": {
            "rows": [
                {
                    "package": "P1",
                    "semester": "S1",
                    "class_group": "7/1",
                    "subject": "علوم",
                    "students_count": 3,
                    "avg_score": 7.5,
                    "min_score": 5.0,
                    "max_score": 9.0,
                    "max_grade": 10.0,
                }
            ]
        },
        "progress": {
            "students": [
                {
                    "rank": 1,
                    "student_name": "أحمد",
                    "assessments_count": 2,
                    "avg_pct": 80.0,
                    "min_pct": 70.0,
                    "max_pct": 90.0,
                }
            ]
        },
        "monthly": {
            "rows": [
                {"student_name": "أحمد", "quiz_count": 2, "quiz_avg": 80.0, "behavior_count": 1},
            ]
        },
    }
    SELECTORS = {
        "quiz": "quiz_data",
        "exam-results": "exam_results_data",
        "progress": "progress_data",
        "monthly": "monthly_data",
    }
    KEYS = {
        "quiz": "quiz",
        "exam-results": "exam_results",
        "progress": "progress",
        "monthly": "monthly",
    }

    @pytest.mark.parametrize("slug", list(ACADEMIC_TABLES))
    def test_the_file_has_the_selector_rows_numbered(
        self, monkeypatch, school, principal_user, slug
    ):
        data = self.DATA[self.KEYS[slug]]
        monkeypatch.setattr(report_selectors, self.SELECTORS[slug], lambda *_a: data)

        result, rows = _file_rows(ACADEMIC_TABLES[slug], principal_user, school)

        assert result.rows == len(rows) == 1
        assert rows[0][0] == 1 and rows[0][1] in ("أحمد", "P1", 1)

    @pytest.mark.parametrize("slug", list(ACADEMIC_TABLES))
    @pytest.mark.parametrize("who", ROLES)
    def test_the_capability_gate(self, client_as, roles, slug, who):
        _gate(
            client_as,
            roles[who],
            ACADEMIC_TABLES[slug],
            "academic_management:report_xlsx",
            report=slug,
        )

    def test_the_page_and_the_file_read_the_same_selector(
        self, client_as, monkeypatch, principal_user, school
    ):
        monkeypatch.setattr(
            report_selectors,
            "quiz_data",
            lambda *_a: dict(
                self.DATA["quiz"],
                min_pct=None,
                max_pct=None,
                total_rows=1,
                avg_pct=80.0,
                range_label="",
            ),
        )
        page = client_as(principal_user).get(reverse("academic_management:quiz_reports"))
        _result, rows = _file_rows(ACADEMIC_TABLES["quiz"], principal_user, school)

        assert page.status_code == 200 and len(page.context["data"]["rows"]) == len(rows) == 1

    def test_an_unknown_report_is_404(self, client_as, principal_user):
        response = client_as(principal_user).get(
            reverse("academic_management:report_xlsx", kwargs={"report": "nope"})
        )

        assert response.status_code == 404

    def test_a_hidden_column_is_hidden_in_the_file(self, monkeypatch, school, principal_user):
        monkeypatch.setattr(report_selectors, "monthly_data", lambda *_a: self.DATA["monthly"])
        result = registry.get("academic.monthly_xlsx").build(
            school, principal_user, QueryDict("hide=behavior_count")
        )
        labels = [
            c.value
            for row in load_workbook(BytesIO(result.content)).active.iter_rows()
            for c in row
        ]

        assert "عدد المخالفات" not in labels and "عدد الاختبارات" in labels


class TestGradebookAndClassResults:
    @pytest.fixture
    def setup(self, school, class_group, teacher_user, enrolled_student):
        subject = Subject.objects.create(school=school, name_ar="العلوم", code="SCI")
        return SubjectClassSetup.objects.create(
            school=school,
            subject=subject,
            class_group=class_group,
            teacher=teacher_user,
            academic_year=class_group.academic_year,
        )

    @pytest.mark.parametrize(
        "spec,query",
        [
            (GRADEBOOK_TABLE, "setup_id={setup}&semester=S1"),
            (CLASS_RESULTS_TABLE, "class_id={klass}&year={year}"),
        ],
    )
    def test_principal_and_the_owning_teacher_get_the_class_without_a_national_id(
        self, school, setup, principal_user, teacher_user, enrolled_student, spec, query
    ):
        params = query.format(setup=setup.pk, klass=setup.class_group_id, year=setup.academic_year)
        for user in (principal_user, teacher_user):
            result, rows = _file_rows(spec, user, school, params)

            assert result.rows == len(rows) == 1 and result.full_national_id is False
            assert rows[0][0] == 1
            assert enrolled_student.student.national_id not in {str(c) for c in rows[0]}

    @pytest.mark.parametrize(
        "spec,query",
        [
            (GRADEBOOK_TABLE, "setup_id={setup}&semester=S1"),
            (CLASS_RESULTS_TABLE, "class_id={klass}&year={year}"),
        ],
    )
    def test_a_wing_supervisor_and_a_foreign_teacher_are_refused(
        self, school, setup, world, enrolled_student, spec, query
    ):
        params = query.format(setup=setup.pk, klass=setup.class_group_id, year=setup.academic_year)
        stranger = _staff(school, "teacher", "معلّمٌ غريب", "29000000051")

        for user in (world["supervisor"], stranger):
            with pytest.raises(PermissionDenied):
                _file_rows(spec, user, school, params)

    @pytest.mark.parametrize("who", ROLES)
    def test_the_capability_gate_of_the_gradebook(self, client_as, roles, setup, who):
        _gate(client_as, roles[who], GRADEBOOK_TABLE, "export_gradebook", setup_id=setup.pk)

    def test_the_gradebook_pdf_kind_shares_the_table(self):
        assert registry.get("assessments.gradebook_pdf") is not None
        assert GRADEBOOK_TABLE.kind in contract.tables()

"""عقدُ التصدير المركزيّ (W-20261109-012): الملفُّ يحمل المعروضَ بعد الفلتر وبنطاق الدور — لا «الكلَّ».

رفض المالكُ المعاينةَ السابقة (الطلب 1413): «صدر الكل ولم يصدر المعروض بعد الفلترة». فهنا:
* بحثُ `q` يطابق طالباً واحداً ← ملفٌّ بصفٍّ واحد، وبلا فلترٍ ← كلُّ الصفوف.
* صفوفُ التصدير = صفوفُ الصفحة بالمعاملات نفسِها لمدير ومشرفِ جناحٍ ومعلّم.
* الترقيمُ يُحسب عند الإخراج، والفرزُ بالجناح، والأعمدةُ المخفيّة تُخفى في الملف.
"""

from io import BytesIO

import pytest
from django.http import QueryDict
from django.urls import reverse
from openpyxl import load_workbook

from core.academic_calendar import academic_year_for_school
from core.exports import registry
from core.exports.contract import (
    NUMBER_HEADER,
    Column,
    hidden_columns,
    numbered,
    sort_by_wing,
    visible_columns,
    wing_rank,
)
from core.models import Wing
from student_affairs.export_builders import build_student_list_xlsx
from student_affairs.student_list_rows import rows_for
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

KIND = "student_affairs.students_xlsx"


def _staff(school, role, national_id, name):
    user = UserFactory(full_name=name, national_id=national_id)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


def _pupil(school, klass, name, national_id):
    user = UserFactory(full_name=name, national_id=national_id)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="student"))
    StudentEnrollmentFactory(student=user, class_group=klass)
    return user


@pytest.fixture
def world(school, seeded_calendar):
    """جناحان: الأوّل (ترتيب 2) بمشرفٍ وفيه سالم وماجد، والثاني (ترتيب 1) فيه نايف."""
    year = academic_year_for_school(school)
    supervisor = _staff(school, "admin_supervisor", "29000000011", "مشرف الجناح")
    wing_a = Wing.objects.create(
        school=school, code="wa", name="جناح أ", academic_year=year, supervisor=supervisor, order=2
    )
    wing_b = Wing.objects.create(
        school=school, code="wb", name="جناح ب", academic_year=year, order=1
    )
    class_a = ClassGroupFactory(school=school, academic_year=year, grade="G7", section="1")
    class_b = ClassGroupFactory(school=school, academic_year=year, grade="G8", section="1")
    class_a.wing, class_b.wing = wing_a, wing_b
    class_a.save(update_fields=["wing"])
    class_b.save(update_fields=["wing"])
    _pupil(school, class_a, "سالم الأحمدي", "29000000001")
    _pupil(school, class_a, "ماجد الكعبي", "29000000002")
    _pupil(school, class_b, "نايف المهندي", "29000000003")
    return {"supervisor": supervisor}


def _sheet(result):
    ws = load_workbook(BytesIO(result.content)).active
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    start = next(i for i, r in enumerate(rows) if r and r[0] == NUMBER_HEADER)
    return rows[start], [r for r in rows[start + 1 :] if isinstance(r[0], int)]


def _names(rows):
    return [r["full_name"] for r in rows]


class TestTheExportCarriesWhatIsDisplayed:
    def test_a_search_matching_one_student_gives_one_row(self, school, principal_user, world):
        params = QueryDict("q=سالم")
        _header, body = _sheet(build_student_list_xlsx(school, principal_user, params))

        assert len(body) == 1
        assert "سالم الأحمدي" in body[0]

    def test_without_a_filter_all_the_rows_come_out(self, school, principal_user, world):
        _header, body = _sheet(build_student_list_xlsx(school, principal_user, QueryDict("")))

        assert len(body) == 3

    def test_every_filter_of_the_page_url_reaches_the_selector(self, school, principal_user, world):
        assert _names(rows_for(principal_user, QueryDict("grade=G8"), school)) == ["نايف المهندي"]
        assert _names(rows_for(principal_user, QueryDict("section=1&q=ماجد"), school)) == [
            "ماجد الكعبي"
        ]
        assert rows_for(principal_user, QueryDict("parent_status=linked"), school) == []

    def test_the_page_link_carries_all_the_filters(self, client_as, principal_user, world):
        page = client_as(principal_user).get(
            reverse("student_affairs:student_list"), {"q": "سالم", "status": "all"}
        )

        html = page.content.decode()
        assert "q=%D8%B3%D8%A7%D9%84%D9%85" in html
        assert "status=all" in html

    def test_the_kind_is_registered_in_the_central_registry(self):
        assert registry.get(KIND) is not None


class TestExportRowsEqualPageRows:
    """الصفحةُ والتصديرُ يقرآن بالمحدِّد نفسِه: لثلاثة أدوار وبالمعاملات نفسِها."""

    @pytest.mark.parametrize("query", ["", "q=سالم", "grade=G7", "sort=name&dir=desc"])
    def test_for_the_principal_the_supervisor_and_the_teacher(
        self, client_as, school, principal_user, teacher_user, world, query
    ):
        for user in (principal_user, world["supervisor"], teacher_user):
            exported = rows_for(user, QueryDict(query), school)
            client = client_as(user)
            response = client.get(reverse("student_affairs:student_list") + f"?{query}")
            if response.status_code != 200:
                # المعلّمُ لا يفتح الشاشة: لا يُصدِّر أيضاً — العقدُ نفسُه (قدرةٌ واحدة).
                export = client.get(reverse("student_affairs:student_export") + f"?{query}")
                assert export.status_code in (302, 403)
                continue
            shown = [r["full_name"] for r in response.context["students"]]
            assert sorted(_names(exported)) == sorted(shown)

    def test_the_supervisor_gets_only_the_wing_students(self, school, world):
        assert sorted(_names(rows_for(world["supervisor"], QueryDict(""), school))) == [
            "سالم الأحمدي",
            "ماجد الكعبي",
        ]

    def test_the_supervisor_cannot_widen_the_scope_by_a_url(self, school, world):
        rows = rows_for(world["supervisor"], QueryDict("status=all&grade=G8"), school)

        assert rows == []

    def test_the_whole_filtered_set_not_the_current_page(self, school, principal_user, world):
        from student_affairs.views import STUDENT_PAGE_SIZE

        assert STUDENT_PAGE_SIZE >= 3  # الصفحةُ تتّسع للثلاثة، والعقدُ يخرج بالمجموعة كلِّها لا بالصفحة
        assert len(rows_for(principal_user, QueryDict("page=2"), school)) == 3


class TestContractHelpers:
    def test_the_number_is_computed_at_output_and_not_stored(self, school, principal_user, world):
        rows = rows_for(principal_user, QueryDict(""), school)

        assert all(NUMBER_HEADER not in row and "num" not in row for row in rows)
        assert [n for n, _ in numbered(rows)] == [1, 2, 3]
        _header, body = _sheet(build_student_list_xlsx(school, principal_user, QueryDict("")))
        assert [r[0] for r in body] == [1, 2, 3]

    def test_the_default_sort_is_by_the_wing_order_then_the_name(
        self, school, principal_user, world
    ):
        # جناحُ «ب» ترتيبُه 1 فيسبق جناحَ «أ» ترتيبُه 2 ولو تأخّر اسمُه.
        assert _names(rows_for(principal_user, QueryDict(""), school)) == [
            "نايف المهندي",
            "سالم الأحمدي",
            "ماجد الكعبي",
        ]

    def test_an_explicit_sort_wins_over_the_wing_sort(self, school, principal_user, world):
        asc = _names(rows_for(principal_user, QueryDict("sort=name&dir=asc"), school))
        desc = _names(rows_for(principal_user, QueryDict("sort=name&dir=desc"), school))

        assert desc == asc[::-1]
        assert asc != _names(rows_for(principal_user, QueryDict(""), school))

    def test_the_wing_rank_follows_the_central_order_and_unknown_goes_last(self):
        assert [wing_rank(n) for n in (1, 2, 5)] == [0, 1, 4]
        assert wing_rank(None) == wing_rank(9) == wing_rank("x") == 6
        rows = [{"wing_order": 5}, {"wing_order": None}, {"wing_order": 1}]
        assert [r["wing_order"] for r in sort_by_wing(rows)] == [1, 5, None]

    def test_the_hidden_screen_columns_are_hidden_in_the_file(self, school, principal_user, world):
        params = QueryDict("hide=national_id,guardian_phone")
        header, _body = _sheet(build_student_list_xlsx(school, principal_user, params))

        assert "الرقم الشخصي" not in header
        assert "جوال ولي الأمر" not in header
        assert "الاسم الكامل" in header

    def test_hidden_columns_parsing(self):
        cols = (Column("a", "أ"), Column("b", "ب"), Column("c", "ج"))

        assert hidden_columns(QueryDict("hide=a, c")) == {"a", "c"}
        assert [c.key for c in visible_columns(cols, QueryDict("hide=b"))] == ["a", "c"]
        assert [c.key for c in visible_columns(cols, QueryDict(""))] == ["a", "b", "c"]

    def test_the_national_id_in_the_file_is_masked(self, school, principal_user, world):
        _header, body = _sheet(build_student_list_xlsx(school, principal_user, QueryDict("")))

        assert not any("29000000001" in str(cell) for row in body for cell in row)

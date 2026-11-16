"""عقدُ التصدير المركزيّ للجداول (W-20261109-013): الملفُّ المعروضُ بعد الفلترة وبنطاق الدور، لا السجلُّ كلُّه.

رفض المالكُ المعاينةَ السابقةَ (الطلب 1413): «صدر الكل ولم يصدر المعروض بعد الفلترة». فهنا: المعاملاتُ كلُّها تصل المحدِّدَ،
وصفوفُ الملفّ تساوي صفوفَ الصفحة بالمعاملات نفسِها لثلاثة أدوار، والمشرفُ لا يخرج في ملفّه طالبٌ من غير جناحه.
"""

from io import BytesIO

import pytest
from django.http import QueryDict
from django.urls import reverse
from openpyxl import load_workbook

from core.exports import contract, registry
from core.models.academic import Wing
from student_affairs.export_builders import STUDENT_LIST_TABLE
from student_affairs.list_selectors import rows_for
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

KIND = STUDENT_LIST_TABLE.kind


def _staff(school, role, name, national_id):
    user = UserFactory(full_name=name, national_id=national_id)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


def _pupil(school, name, national_id, klass):
    user = UserFactory(full_name=name, national_id=national_id)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="student"))
    StudentEnrollmentFactory(student=user, class_group=klass)
    return user


@pytest.fixture
def world(school, seeded_calendar):
    """جناحان: الأوّلُ (ترتيب 1) بمشرفنا وطالبَين، والثاني (ترتيب 2) بمشرفٍ آخر وطالبٍ واحد."""
    year = seeded_calendar
    mine = _staff(school, "admin_supervisor", "مشرفُ الجناح الأوّل", "29000000011")
    other = _staff(school, "admin_supervisor", "مشرفُ الجناح الثاني", "29000000012")
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
    # الأسماءُ مرتَّبةً أبجديّاً: «أحمد» ثمّ «بدر» ثمّ «ليلى» — فيظهر فرزُ الجناح لا فرزُ الاسم.
    pupils = {
        "ahmad": _pupil(school, "أحمد سالم", "29000000021", klass1),
        "badr": _pupil(school, "بدر خالد", "29000000022", klass2),
        "layla": _pupil(school, "ليلى حمد", "29000000023", klass1),
    }
    return {"supervisor": mine, "pupils": pupils}


@pytest.fixture
def roles(world, school, principal_user, teacher_user):
    return {
        "principal": principal_user,
        "wing_supervisor": world["supervisor"],
        "teacher": teacher_user,
    }


def _xlsx_rows(user, school, query=""):
    """صفوفُ البيانات في الملفّ كما يخرج (بلا الترويسة والتذييل): كلُّ صفٍّ رقمُه في عموده الأوّل."""
    result = registry.get(KIND).build(school, user, QueryDict(query))
    sheet = load_workbook(BytesIO(result.content)).active
    rows = [
        [cell.value for cell in row]
        for row in sheet.iter_rows()
        if isinstance(row[0].value, int) and row[0].value >= 1
    ]
    return result, rows


def _page_names(client_as, user, params):
    response = client_as(user).get(reverse("student_affairs:student_list"), params)
    if response.status_code != 200:
        return None
    return sorted(row["full_name"] for row in response.context["students"])


class TestTheContractMatchesThePage:
    @pytest.mark.parametrize("who", ["principal", "wing_supervisor", "teacher"])
    @pytest.mark.parametrize(
        "params", [{}, {"q": "أحمد"}, {"grade": "G8"}, {"q": "حمد", "section": "1"}]
    )
    def test_export_rows_equal_page_rows_for_the_same_params(
        self, client_as, school, roles, who, params
    ):
        user = roles[who]
        page = _page_names(client_as, user, params)
        exported = sorted(r["full_name"] for r in rows_for(user, QueryDict(urlencode(params))))

        if page is None:
            # من لا يفتح الشاشةَ لا يصدّر منها: القدرةُ نفسُها حارسُ الاثنين.
            assert not user_may_open(user)
            return
        assert exported == page


def urlencode(params):
    q = QueryDict(mutable=True)
    q.update(params)
    return q.urlencode()


def user_may_open(user):
    from core.capabilities import has_capability

    return has_capability(user, STUDENT_LIST_TABLE.capability)


class TestTheFilterReachesTheFile:
    """رفضُ الطلب 1413: الفلترُ كلُّه يصل المحدِّدَ فيخرج المطابقون فقط."""

    def test_a_search_matching_one_pupil_gives_a_file_of_one_row(
        self, school, principal_user, world
    ):
        result, rows = _xlsx_rows(principal_user, school, "q=" + "أحمد")

        assert result.rows == 1 and len(rows) == 1
        assert rows[0][1] == "أحمد سالم"

    def test_without_a_filter_the_file_has_every_pupil(self, school, principal_user, world):
        result, rows = _xlsx_rows(principal_user, school)

        assert result.rows == len(rows) == 3

    def test_the_file_row_count_equals_the_page_total(
        self, client_as, school, principal_user, world
    ):
        response = client_as(principal_user).get(
            reverse("student_affairs:student_list"), {"q": "حمد"}
        )
        _result, rows = _xlsx_rows(principal_user, school, "q=" + "حمد")

        assert len(rows) == response.context["total"] == 2

    def test_the_grade_filter_reaches_the_file(self, school, principal_user, world):
        _result, rows = _xlsx_rows(principal_user, school, "grade=G8")

        assert [r[1] for r in rows] == ["بدر خالد"]


class TestTheRoleScope:
    def test_a_wing_supervisor_exports_only_his_wing(self, school, world):
        _result, rows = _xlsx_rows(world["supervisor"], school)

        assert sorted(r[1] for r in rows) == ["أحمد سالم", "ليلى حمد"]

    def test_a_wing_supervisor_cannot_widen_his_scope_by_the_link(self, school, world):
        _result, rows = _xlsx_rows(world["supervisor"], school, "grade=G8&status=all")

        assert rows == []


class TestNumberingSortingAndHiding:
    def test_numbering_is_computed_at_output_and_the_file_is_sorted_by_wing(
        self, school, principal_user, world
    ):
        """«م» تسلسلٌ في الملفّ لا في القاعدة؛ والجناحُ الأوّلُ يسبق الثاني ولو كان اسمُه بعده أبجديّاً."""
        _result, rows = _xlsx_rows(principal_user, school)

        assert [r[0] for r in rows] == [1, 2, 3]
        assert [r[1] for r in rows] == ["أحمد سالم", "ليلى حمد", "بدر خالد"]

    def test_wing_sorted_is_stable_and_puts_the_wingless_last(self):
        rows = [
            {"n": "a", "wing_order": None},
            {"n": "b", "wing_order": 2},
            {"n": "c", "wing_order": 1},
            {"n": "d", "wing_order": 2},
        ]

        assert [r["n"] for r in contract.wing_sorted(rows)] == ["c", "b", "d", "a"]

    def test_hidden_columns_are_hidden_in_the_file(self, school, principal_user, world):
        result = registry.get(KIND).build(school, principal_user, QueryDict("hide=guardian_phone"))
        sheet = load_workbook(BytesIO(result.content)).active
        headers = [c.value for row in sheet.iter_rows() for c in row if c.value == "جوال ولي الأمر"]

        assert headers == []

    def test_hiding_every_column_keeps_them_all(self):
        params = QueryDict("hide=" + ",".join(c.key for c in STUDENT_LIST_TABLE.columns))

        assert len(contract.visible_columns(STUDENT_LIST_TABLE, params)) == len(
            STUDENT_LIST_TABLE.columns
        )

    def test_the_national_number_is_masked_and_arabic_survives(self, school, principal_user, world):
        _result, rows = _xlsx_rows(principal_user, school, "q=أحمد")

        assert rows[0][2].startswith("*") and "29000000021" not in rows[0][2]
        assert rows[0][1] == "أحمد سالم"


class TestTheRegistration:
    def test_the_pilot_kind_is_in_the_central_registry_with_the_page_capability(self):
        spec = registry.get(KIND)

        assert spec is not None and spec.capability == "student_affairs.view"
        assert KIND in contract.tables()

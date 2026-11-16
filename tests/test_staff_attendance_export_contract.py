"""ترحيلُ التصدير للمعروض (W-20261110-004): جدولا حضور الموظفين (تقريرُ الشهر وكشفُ اليوم) على عقد core/exports.

لثلاثة أدوار — مدير ومشرفُ جناح ومعلّم: الصفحةُ وExcel يقرؤون المحدِّدَ نفسَه؛ من لا تفتح له القدرةُ الشاشةَ لا يخرج له
ملفٌّ، ومن يفتحها يخرج له المعروضُ مرقَّماً ومحذوفَ الأعمدةِ المخفيّة، بالرقم الوظيفيّ وحدَه ولا نصَّ عذر (م-7).
"""

import io

import pytest
from django.core.exceptions import PermissionDenied
from django.http import QueryDict
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from core.capabilities import has_capability
from core.exports import contract, registry
from staff_affairs.export_tables import DAILY_TABLE, MONTHLY_TABLE, daily_rows, monthly_rows
from staff_affairs.models import StaffAttendance
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

SECRET_EXCUSE = "تقرير طبي سرّي"
TABLES = [MONTHLY_TABLE, DAILY_TABLE]


def _person(school, number, role="teacher", name=None):
    user = UserFactory(
        full_name=name or f"موظف اصطناعي {number}", employee_number=f"T-{number:04d}"
    )
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


def _query(**extra):
    query = QueryDict(mutable=True)
    query.update({"date": f"{timezone.localdate():%Y-%m-%d}", **extra})
    return query


@pytest.fixture
def roles(school, principal_user, teacher_user):
    return {
        "principal": principal_user,
        "wing_supervisor": _person(school, 90, "admin_supervisor", "مشرفُ جناحٍ اصطناعيّ"),
        "teacher": teacher_user,
    }


@pytest.fixture
def staff(school):
    first, second = _person(school, 1), _person(school, 2)
    StaffAttendance.objects.create(
        school=school,
        staff=first,
        date=timezone.localdate(),
        status="absent",
        absence_type="sick",
        accepted_excuse=SECRET_EXCUSE,
    )
    return first, second


def _sheet_rows(content):
    """صفوفُ البيانات في الملفّ كما يخرج: ما رقمُه في عموده الأوّل «م» عددٌ."""
    sheet = load_workbook(io.BytesIO(content)).active
    return [
        [cell.value for cell in row]
        for row in sheet.iter_rows()
        if isinstance(row[0].value, int) and row[0].value >= 1
    ]


class TestTheManagerGetsTheShownTable:
    @pytest.mark.parametrize("spec", TABLES, ids=lambda s: s.kind)
    def test_every_member_is_numbered_in_the_file(self, spec, school, roles, staff):
        result = registry.get(spec.kind).build(school, roles["principal"], _query())
        rows = _sheet_rows(result.content)

        assert result.rows == len(rows) >= 2
        assert [row[0] for row in rows] == list(range(1, len(rows) + 1))
        assert result.full_national_id is False

    def test_the_file_carries_the_employee_number_never_the_excuse(self, school, roles, staff):
        result = registry.get(DAILY_TABLE.kind).build(school, roles["principal"], _query())
        cells = {c for row in _sheet_rows(result.content) for c in row}

        assert "T-0001" in cells and "T-0002" in cells
        assert SECRET_EXCUSE not in cells
        assert SECRET_EXCUSE.encode() not in result.content

    def test_the_monthly_rows_are_the_page_rows(self, school, roles, staff):
        month = f"{timezone.localdate():%Y-%m}"
        rows = monthly_rows(roles["principal"], _query(month=month))

        assert {"T-0001", "T-0002"} <= {row["employee_number"] for row in rows}

    def test_a_status_filter_reaches_every_result_not_a_page(self, roles, staff):
        absent = daily_rows(roles["principal"], _query(status="absent"))
        unmarked = daily_rows(roles["principal"], _query(status="unmarked"))

        assert [row["employee_number"] for row in absent] == ["T-0001"]
        assert "T-0002" in {row["employee_number"] for row in unmarked}
        assert "T-0001" not in {row["employee_number"] for row in unmarked}

    def test_a_name_search_narrows_the_file(self, roles, staff):
        rows = daily_rows(roles["principal"], _query(q="T-0002"))

        assert [row["employee_number"] for row in rows] == ["T-0002"]

    @pytest.mark.parametrize("spec", TABLES, ids=lambda s: s.kind)
    def test_a_hidden_column_leaves_the_file_and_the_number_stays(self, spec, roles, staff):
        shown, rows = contract.table_rows(spec, roles["principal"], _query())
        hidden, hidden_rows = contract.table_rows(
            spec, roles["principal"], _query(hide="employee_number")
        )

        assert "الرقم الوظيفي" in [c.label for c in shown]
        assert "الرقم الوظيفي" not in [c.label for c in hidden]
        assert [r[0] for r in hidden_rows] == [r[0] for r in rows]
        assert all(len(r) == len(hidden) + 1 for r in hidden_rows)

    @pytest.mark.parametrize("spec", TABLES, ids=lambda s: s.kind)
    def test_staff_have_no_wing_so_the_file_is_not_wing_sorted(self, spec):
        assert spec.wing_key is None


class TestTheOtherRolesGetOnlyWhatTheirCapabilityOpens:
    @pytest.mark.parametrize("role", ["wing_supervisor", "teacher"])
    @pytest.mark.parametrize(
        ("spec", "url_name"),
        [
            (MONTHLY_TABLE, "staff_affairs:attendance_report_xlsx"),
            (DAILY_TABLE, "staff_affairs:attendance_daily_xlsx"),
        ],
        ids=lambda v: getattr(v, "kind", v),
    )
    def test_the_file_follows_the_capability_of_the_page(
        self, role, spec, url_name, roles, staff, client_as
    ):
        user = roles[role]
        status = client_as(user).get(reverse(url_name), {"date": _query()["date"]}).status_code

        if not has_capability(user, spec.capability):
            assert status == 403
        elif spec is MONTHLY_TABLE:
            # كشفُ اليوم يزيد على القدرة أن تُفتح للقارئ لوحةُ الرصد، فلا يُجزم بقبوله هنا.
            assert status != 403

    def test_a_teacher_cannot_read_the_daily_rows_directly(self, roles, staff):
        with pytest.raises(PermissionDenied):
            daily_rows(roles["teacher"], _query())


class TestTheRegistration:
    @pytest.mark.parametrize("spec", TABLES, ids=lambda s: s.kind)
    def test_each_table_is_registered_with_its_capability(self, spec):
        assert spec.kind in contract.tables()
        assert registry.get(spec.kind).capability == spec.capability

    def test_the_board_link_carries_the_search_and_the_status(self, client_as, roles, staff):
        html = (
            client_as(roles["principal"])
            .get(reverse("staff_affairs:attendance_board"), {"status": "absent", "q": "T-0001"})
            .content.decode()
        )

        assert reverse("staff_affairs:attendance_daily_xlsx") in html
        assert "status=absent" in html

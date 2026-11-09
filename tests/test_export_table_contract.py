"""عقدُ التصدير الجدوليّ المركزيّ (W-20261109-001): المُصدَّر = المعروض، بنطاق الدور، مرقَّماً ومفروزاً بالجناح.

النوعُ التجريبيُّ كشفُ الطلاب (`student_affairs.export_tables`). المحدِّدُ `roster_rows` هو مصدرُ الصفحة والتصدير معاً،
فيُقرأ ملفُّ Excel المُنتَج ويقارَن بصفوف المحدِّد بالمعاملات نفسِها لثلاثة أدوار: مدير ومشرف جناح ومعلّم.
"""

import datetime as dt
from io import BytesIO

import openpyxl
import pytest
from django.http import QueryDict

from core.exports import registry, table
from core.exports.table import Column, TableSpec
from core.models import Wing
from operations.models import ScheduleSlot
from student_affairs import export_tables
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]


def _user(school, role, name, national_id):
    user = UserFactory(full_name=name, national_id=national_id)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


def _pupil(school, klass, name, national_id):
    student = _user(school, "student", name, national_id)
    StudentEnrollmentFactory(student=student, class_group=klass)
    return student


@pytest.fixture
def world(school, seeded_calendar):
    """جناحان (ترتيب 2 ثمّ 1) وطالبان في كلٍّ، وشعبةٌ بلا جناح؛ المعلّمُ يُدرّس شعبةَ الجناح الأوّل وحدَها."""
    year = seeded_calendar
    supervisor = _user(school, "admin_supervisor", "مشرف الجناح الأول", "29000000001")
    other_supervisor = _user(school, "admin_supervisor", "مشرف الجناح الثاني", "29000000002")
    wing_a = Wing.objects.create(
        school=school, code="a", name="جناح أ", academic_year=year, supervisor=supervisor, order=2
    )
    wing_b = Wing.objects.create(
        school=school,
        code="b",
        name="جناح ب",
        academic_year=year,
        supervisor=other_supervisor,
        order=1,
    )
    klass_a = ClassGroupFactory(
        school=school, academic_year=year, grade="G7", section="1", wing=wing_a
    )
    klass_b = ClassGroupFactory(
        school=school, academic_year=year, grade="G8", section="2", wing=wing_b
    )
    klass_none = ClassGroupFactory(
        school=school, academic_year=year, grade="G9", section="3", wing=None
    )
    pupils = {
        "a1": _pupil(school, klass_a, "باسم الأول", "29000000011"),
        "a2": _pupil(school, klass_a, "أحمد الأول", "29000000012"),
        "b1": _pupil(school, klass_b, "سالم الثاني", "29000000013"),
        "n1": _pupil(school, klass_none, "خالد بلا جناح", "29000000014"),
    }
    teacher = _user(school, "teacher", "معلّم الشعبة", "29000000003")
    ScheduleSlot.objects.create(
        school=school,
        teacher=teacher,
        class_group=klass_a,
        day_of_week=0,
        period_number=1,
        start_time=dt.time(7, 10),
        end_time=dt.time(7, 55),
        academic_year=year,
    )
    principal = _user(school, "principal", "مدير المدرسة", "29000000004")
    return {
        "principal": principal,
        "supervisor": supervisor,
        "teacher": teacher,
        "pupils": pupils,
        "wing_a": wing_a,
    }


def _names(rows):
    return [row["full_name"] for row in rows]


def _xlsx_rows(content: bytes) -> list[list]:
    """صفوفُ البيانات في الملفّ: من ما بعد سطر الترويسة («م») إلى ما قبل الذيل."""
    ws = openpyxl.load_workbook(BytesIO(content)).active
    grid = [[c.value for c in row] for row in ws.iter_rows()]
    head = next(i for i, row in enumerate(grid) if row and row[0] == table.NUMBER_LABEL)
    body = []
    for row in grid[head + 1 :]:
        if not isinstance(row[0], int):
            break
        body.append(row)
    return [grid[head], *body]


def _export(school, user, params):
    return table.build_xlsx(export_tables.ROSTER, school, user, params)


@pytest.mark.parametrize("role", ["principal", "supervisor", "teacher"])
def test_export_rows_equal_page_rows_for_each_role(school, world, role):
    user = world[role]
    params = QueryDict("")
    page_rows = table.sort_by_wing(export_tables.roster_rows(user, params))

    result = _export(school, user, params)
    head, *body = _xlsx_rows(result.content)

    assert head[1:] == [c.label for c in export_tables.COLUMNS]
    assert [r[1] for r in body] == _names(page_rows)
    assert [r[2:] for r in body] == [
        [row["grade"], row["section"], row["wing"]] for row in page_rows
    ]
    assert result.rows == len(page_rows)


def test_scope_by_role(school, world):
    params = QueryDict("")
    everyone = _names(export_tables.roster_rows(world["principal"], params))
    assert len(everyone) == 4
    # مشرفُ الجناح لا يرى إلّا طلبةَ جناحه — لا المدرسةَ ولا الجناحَ الآخر ولا من بلا جناح.
    assert sorted(_names(export_tables.roster_rows(world["supervisor"], params))) == [
        "أحمد الأول",
        "باسم الأول",
    ]
    # المعلّمُ يرى من يُدرّسهم فقط.
    assert sorted(_names(export_tables.roster_rows(world["teacher"], params))) == [
        "أحمد الأول",
        "باسم الأول",
    ]


def test_role_outside_the_module_sees_nobody(school, world):
    stranger = _user(school, "bus_driver", "سائق", "29000000005")
    assert export_tables.roster_rows(stranger, QueryDict("")) == []


def test_filter_applies_to_whole_result_not_the_current_page(school, world):
    params = QueryDict("grade=G8")
    rows = export_tables.roster_rows(world["principal"], params)
    assert _names(rows) == ["سالم الثاني"]
    _head, *body = _xlsx_rows(_export(school, world["principal"], params).content)
    assert [r[1] for r in body] == ["سالم الثاني"]
    # مشرفُ الجناح الأوّل بفلتر جناحٍ ليس له: لا شيء، لا تسريبَ بالفلتر.
    assert export_tables.roster_rows(world["supervisor"], params) == []


def test_numbering_is_computed_at_output_and_follows_wing_order(school, world):
    _head, *body = _xlsx_rows(_export(school, world["principal"], QueryDict("")).content)
    assert [r[0] for r in body] == [1, 2, 3, 4]
    # الجناحُ ذو الترتيب 1 (ب) أولاً، ثمّ الترتيب 2 (أ) بترتيب الاسم داخله، وما بلا جناحٍ آخراً.
    assert [r[1] for r in body] == ["سالم الثاني", "أحمد الأول", "باسم الأول", "خالد بلا جناح"]
    stored = export_tables.roster_rows(world["principal"], QueryDict(""))
    assert all("م" not in row and "num" not in row for row in stored)


def test_wing_sort_is_stable_and_puts_unknown_wings_last():
    rows = [
        {"k": "x", "wing_order": None},
        {"k": "a", "wing_order": 3},
        {"k": "b", "wing_order": 1},
        {"k": "c", "wing_order": 3},
        {"k": "z", "wing_order": 9},
    ]
    assert [r["k"] for r in table.sort_by_wing(rows)] == ["b", "a", "c", "x", "z"]


def test_hidden_columns_are_hidden_in_the_file(school, world):
    params = QueryDict("hide=wing,section")
    head, *body = _xlsx_rows(_export(school, world["principal"], params).content)
    assert head[1:] == ["الاسم الكامل", "الصف"]
    assert all(len(r) == 3 for r in body)


def test_hiding_every_column_is_ignored():
    spec = TableSpec("k", "t", (Column("a", "أ"), Column("b", "ب")), lambda u, p: [])
    assert table.visible_columns(spec, QueryDict("hide=a,b")) == spec.columns
    assert [c.key for c in table.visible_columns(spec, QueryDict("hide=a&hide=zzz"))] == ["b"]


def test_both_formats_are_registered_with_the_central_registry():
    assert registry.get("student_affairs.roster_xlsx") is not None
    assert registry.get("student_affairs.roster_pdf") is not None


def test_pdf_has_arabic_headers_numbering_and_no_national_id(school, world, monkeypatch):
    seen: list[str] = []

    def fake(html, paper_size="A4"):
        seen.append(html)
        return b"%PDF-fake"

    monkeypatch.setattr("core.pdf_utils.render_pdf_bytes", fake)
    result = table.build_pdf(export_tables.ROSTER, school, world["supervisor"], QueryDict(""))
    html = seen[0]
    assert result.rows == 2
    assert "الاسم الكامل" in html and "باسم الأول" in html and "أحمد الأول" in html
    assert "سالم الثاني" not in html  # خارج جناح المشرف
    assert "<th>م</th>" in html
    assert "29000000011" not in html and "29000000012" not in html

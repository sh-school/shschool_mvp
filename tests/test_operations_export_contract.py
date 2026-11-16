"""ترحيلُ التصدير للمعروض (W-20261110-004): جدولا متابعة الغياب (التواصلُ والإجراءات) على عقد core/exports.

لثلاثة أدوار — مدير ومشرفُ جناح ومعلّم: الصفحةُ وExcel وPDF يقرؤون `shown_rows` نفسَه؛ من لا تفتح له القدرةُ الشاشةَ لا يخرج
له ملفٌّ (المعلّم)، ومن يفتحها يخرج له المعروضُ بنطاقه وحدَه، مرقَّماً ومفروزاً بالجناح ومحذوفَ الأعمدةِ المخفيّة.
"""

import io

import pytest
from django.http import QueryDict
from django.urls import reverse
from openpyxl import load_workbook

from core.capabilities import has_capability
from core.exports import contract, registry
from operations import export_tables
from operations.absence_followup_print import build_followup_pdf, build_followup_xlsx
from operations.export_tables import ACTIONS_TABLE, CONTACT_FEEDBACK_TABLE, CONTACT_TABLE
from tests.operations.test_absence_followup import (  # noqa: F401
    DAY,
    _calendar_first,
    _get,
    absent_both,
    second_wing,
    staff,
)
from tests.test_period_register import (  # noqa: F401
    kids,
    klass,
    other_teacher,
    subjects,
    supervisor,
    teacher,
    year,
)

pytestmark = pytest.mark.django_db

TABLES = [CONTACT_TABLE, ACTIONS_TABLE]


def _query(**extra):
    query = QueryDict(mutable=True)
    query.update({"date": DAY, **extra})
    return query


def _rows(spec, user, **extra):
    columns, rows = contract.table_rows(spec, user, _query(**extra))
    return [c.label for c in columns], rows


def _sheet_numbers(content):
    """عمودُ «م» في الملف كما يخرج: كلُّ صفِّ بياناتٍ رقمُه في عموده الأوّل."""
    sheet = load_workbook(io.BytesIO(content)).active
    return [row[0].value for row in sheet.iter_rows() if isinstance(row[0].value, int)]


@pytest.mark.parametrize("spec", TABLES, ids=lambda s: s.kind)
class TestTheTwoFollowupTablesForThreeRoles:
    def test_the_manager_gets_both_wings_numbered(self, spec, staff, absent_both):
        _, rows = _rows(spec, staff["principal"])

        assert len(rows) == 2
        assert [row[0] for row in rows] == [1, 2]

    def test_the_wing_supervisor_gets_his_wing_alone(self, spec, supervisor, absent_both):
        _, rows = _rows(spec, supervisor)

        assert len(rows) == 1
        assert rows[0][0] == 1

    def test_the_teacher_is_refused_the_table_and_the_file(
        self, spec, teacher, client_as, school, absent_both
    ):
        assert not has_capability(teacher, spec.capability)
        assert _get(client_as, teacher, "absence_followup_xlsx").status_code == 403

    def test_a_search_filter_reaches_every_result_not_the_page(self, spec, staff, absent_both):
        everyone = _rows(spec, staff["principal"])[1]
        one = _rows(spec, staff["principal"], q="الجناح الثاني")[1]

        assert len(everyone) == 2 and len(one) == 1

    def test_a_hidden_column_leaves_the_file_and_the_number_stays(self, spec, staff, absent_both):
        labels, _ = _rows(spec, staff["principal"])
        hidden, rows = _rows(spec, staff["principal"], hide="wing")

        assert "الجناح" in labels and "الجناح" not in hidden
        assert [row[0] for row in rows] == [1, 2]
        assert all(len(row) == len(hidden) + 1 for row in rows)


class TestThePageAndTheFilesShareTheSelector:
    def test_the_excel_carries_the_rows_the_selector_returns(self, staff, school, absent_both):
        result = build_followup_xlsx(school, staff["principal"], _query(page="actions"))

        assert result.rows == len(export_tables.shown_rows(staff["principal"], _query())) == 2
        assert _sheet_numbers(result.content) == [1, 2]

    def test_the_pdf_counts_the_same_rows_as_the_excel(
        self, staff, supervisor, school, absent_both
    ):
        for user in (staff["principal"], supervisor):
            if not has_capability(user, export_tables.PRINT):
                continue
            pdf = build_followup_pdf(school, user, _query(page="contact"))
            xlsx = build_followup_xlsx(school, user, _query(page="contact"))
            assert pdf.rows == xlsx.rows

    def test_the_rows_are_ordered_by_wing_order(self, staff, absent_both):
        orders = [
            getattr(getattr(r["class_group"], "wing", None), "order", None) or 98
            for r in export_tables.shown_rows(staff["principal"], _query())
        ]

        assert orders == sorted(orders)

    def test_the_actions_page_still_opens_for_the_manager(self, client_as, staff, absent_both):
        assert _get(client_as, staff["principal"], "absence_actions").status_code == 200


class TestTheFeedbackColumnFollowsTheCapability:
    def test_the_variant_is_picked_by_the_feedback_capability(self, staff, supervisor):
        for user in (staff["principal"], supervisor):
            chosen = export_tables.table_for(user, "contact")
            expected = (
                CONTACT_FEEDBACK_TABLE
                if has_capability(user, export_tables.FEEDBACK)
                else CONTACT_TABLE
            )
            assert chosen is expected

    def test_the_actions_page_never_takes_the_contact_variants(self, staff):
        assert export_tables.table_for(staff["principal"], "actions") is ACTIONS_TABLE

    def test_the_feedback_label_is_only_in_its_own_variant(self):
        label = "التغذية الراجعة من ولي الأمر"

        assert label in [c.label for c in CONTACT_FEEDBACK_TABLE.columns]
        assert label not in [c.label for c in CONTACT_TABLE.columns]


class TestTheRegistration:
    @pytest.mark.parametrize("spec", export_tables.OPERATIONS_TABLES, ids=lambda s: s.kind)
    def test_each_table_is_registered_with_its_capability(self, spec):
        assert spec.kind in contract.tables()
        assert registry.get(spec.kind).capability == spec.capability

    def test_the_follow_up_button_points_at_a_registered_table(self, client_as, staff, absent_both):
        body = _get(client_as, staff["principal"], "daily_report").content.decode()

        assert reverse("absence_followup_xlsx") in body

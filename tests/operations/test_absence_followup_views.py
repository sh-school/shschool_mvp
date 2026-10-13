"""واجهةُ «متابعة الغياب» (W-20261013-016) — الفلاترُ وأنواعُ الإجراء وحفظُ التصفية عند العودة وتسميةُ القائمة.

العقدُ والنطاقُ والخصوصيّةُ مختبَرةٌ في `test_absence_followup.py` (011)؛ وهنا ما تضيفه الواجهة فوق الخدمة.
"""

import pytest
from django.urls import reverse

from tests.operations.test_absence_followup import (  # noqa: F401
    DAY,
    _calendar_first,
    _get,
    _post_action,
    _post_contact,
    absent_both,
    second_wing,
    staff,
)
from tests.test_absence_excuses import MONDAY, _absent_day  # noqa: F401
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


class TestFilters:
    def test_the_wing_filter_narrows_the_principal_to_one_wing(
        self, client_as, staff, second_wing, absent_both
    ):
        wing_id = second_wing["klass"].wing_id
        body = _get(client_as, staff["principal"], wing=str(wing_id)).content.decode()
        assert "طالب الجناح الثاني" in body and "طالب 0" not in body

    def test_the_grade_filter_keeps_only_that_grade(
        self, client_as, staff, second_wing, absent_both
    ):
        body = _get(client_as, staff["principal"], grade="G8").content.decode()
        assert "طالب الجناح الثاني" in body and "طالب 0" not in body

    def test_an_unmatched_filter_shows_a_clear_empty_state(self, client_as, staff, absent_both):
        body = _get(client_as, staff["principal"], grade="G12").content.decode()
        assert "لا غائبَ يطابق التصفية" in body

    def test_the_follow_up_filter_hides_whoever_was_contacted(
        self, client_as, staff, second_wing, absent_both
    ):
        _post_contact(client_as, staff["principal"], absent_both[0])
        body = _get(client_as, staff["principal"], followup="no_contact").content.decode()
        assert "طالب 0" not in body and "طالب الجناح الثاني" in body

    def test_the_supervisor_gets_no_wing_filter_and_no_outside_student(
        self, client_as, supervisor, second_wing, absent_both
    ):
        body = _get(client_as, supervisor).content.decode()
        assert '<select name="wing"' not in body and "طالب الجناح الثاني" not in body

    def test_a_forged_filter_never_widens_the_supervisor_scope(
        self, client_as, supervisor, second_wing, absent_both
    ):
        wing_id = second_wing["klass"].wing_id
        body = _get(client_as, supervisor, wing=str(wing_id)).content.decode()
        assert "طالب الجناح الثاني" not in body


class TestForms:
    def test_the_action_kind_is_a_fixed_list_not_free_text(self, client_as, staff, absent_both):
        body = _get(client_as, staff["principal"]).content.decode()
        assert '<select name="action_kind"' in body
        assert 'type="text" name="action_kind"' not in body

    def test_saving_returns_to_the_same_filters(self, client_as, staff, absent_both):
        resp = _post_contact(
            client_as, staff["principal"], absent_both[0], grade="G7", followup="no_action"
        )
        assert resp.status_code == 302
        assert "grade=G7" in resp["Location"] and "followup=no_action" in resp["Location"]
        assert f"date={DAY}" in resp["Location"]

    def test_the_menu_calls_the_screen_follow_up(self, client_as, staff, absent_both):
        body = _get(client_as, staff["principal"]).content.decode()
        assert "متابعة الغياب" in body and ">غياب اليوم<" not in body
        assert reverse("daily_report") in body


class TestContactSheetRoute:
    def test_the_route_returns_a_pdf_for_who_may_print(self, client_as, staff, absent_both):
        resp = _get(client_as, staff["principal"], "absence_followup_contact_sheet_pdf")
        assert resp.status_code == 200 and resp["Content-Type"] == "application/pdf"
        assert resp.content[:4] == b"%PDF"

    def test_a_teacher_is_denied(self, client_as, teacher, absent_both):
        assert _get(client_as, teacher, "absence_followup_contact_sheet_pdf").status_code == 403

    def test_the_screen_offers_the_sheet_link(self, client_as, staff, absent_both):
        body = _get(client_as, staff["principal"]).content.decode()
        assert reverse("absence_followup_contact_sheet_pdf") in body


class TestLayout:
    def test_the_two_cards_sit_in_one_two_column_grid(self, client_as, staff, absent_both):
        body = _get(client_as, staff["principal"]).content.decode()
        grid = body.index('class="ui-grid-2"')
        assert (
            grid < body.index("التواصلُ مع أولياء الأمور") < body.index("متابعةُ الإجراءات الإدارية")
        )
        assert body.count('class="ui-grid-2"') == 1


class TestPrintInsidePlatform:
    def test_preview_is_framed_in_the_platform_and_embed_is_bare(
        self, client_as, staff, absent_both
    ):
        framed = _get(client_as, staff["principal"], "absence_followup_print").content.decode()
        assert "report-viewer__frame" in framed and "embed=1" in framed and "site-nav" in framed
        bare = _get(
            client_as, staff["principal"], "absence_followup_print", embed="1"
        ).content.decode()
        assert "report-viewer__frame" not in bare and "site-nav" not in bare


class TestStickyHeader:
    def test_both_tables_scroll_vertically_under_a_fixed_head(self, client_as, staff, absent_both):
        body = _get(client_as, staff["principal"]).content.decode()
        assert body.count("table-wrap table-wrap-scroll") == 2


class TestFrameable:
    def test_the_embedded_sheet_is_not_blocked_from_the_viewer_frame(
        self, client_as, staff, absent_both
    ):
        resp = _get(client_as, staff["principal"], "absence_followup_print", embed="1")
        assert resp.status_code == 200
        assert resp["X-Frame-Options"].upper() == "SAMEORIGIN"


class TestSerialColumn:
    def test_each_table_starts_with_a_serial_number_column(self, client_as, staff, absent_both):
        body = _get(client_as, staff["principal"]).content.decode()
        assert body.count('<th scope="col" class="num">#</th>') == 2
        assert body.count('<td class="num">1</td>') >= 2

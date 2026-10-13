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
        assert 'name="action_type"' in body and "استدعاء وليّ أمر" in body
        assert 'type="text" name="action_type"' not in body

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

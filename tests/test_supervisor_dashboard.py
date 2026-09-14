"""لوحةُ مشرف الجناح — النسخةُ الأولى (قرارُ 2026-09-13).

فوق شُعبه المتبقّية: من غاب أمس ولم يُخطَر وليُّ أمره، ومن عند عتبات الغياب بلا
عذر أو تجاوزها. كلٌّ في جناحه، وبرابطٍ إلى صفحة الطالب.
"""

import datetime as dt

import pytest
from django.urls import reverse

from operations.guardian_contact import log_contact
from tests.test_period_register import (  # noqa: F401 — التجهيزاتُ نفسُها
    SUNDAY,
    _confirm,
    _periods,
    kids,
    klass,
    subjects,
    supervisor,
    teacher,
    year,
)
from wings.services import supervisor_watchlist

pytestmark = pytest.mark.django_db

MONDAY = SUNDAY + dt.timedelta(days=1)


def _absent_days(school, klass, teacher, supervisor, days_of: dict):
    """أيّامُ غيابٍ كاملةٍ متتاليةٍ من الأحد لكلّ طالبٍ بعدد أيّامه — أربعُ خاناتٍ في
    اليوم تكفي ليُحسب اليوم. الحصصُ تُنشأ مرّةً واحدة: قيدُ `no_teacher_time_overlap`."""
    for i in range(max(days_of.values())):
        on = SUNDAY + dt.timedelta(days=i)
        marks = {kid: "absent" for kid, n in days_of.items() if n > i}
        for session in _periods(school, klass, teacher, 4, day=on):
            _confirm(klass, session, marks, supervisor, day=on)


class TestTheWatchlist:
    def test_who_was_absent_yesterday_and_not_called_is_listed_until_the_call(
        self, school, seeded_calendar, year, klass, kids, teacher, supervisor
    ):
        _absent_days(school, klass, teacher, supervisor, {kids[0]: 1})

        rows = supervisor_watchlist(supervisor, school, year, MONDAY)["awaiting_contact"]
        assert [(r.student, r.needs_contact) for r in rows] == [(kids[0], SUNDAY)]

        log_contact(
            student=kids[0], school=school, absence_date=SUNDAY, outcome="no_answer", by=supervisor
        )

        assert supervisor_watchlist(supervisor, school, year, MONDAY)["awaiting_contact"] == []

    def test_one_day_before_a_gate_is_at_the_gate_and_past_it_is_flagged(
        self, school, seeded_calendar, year, klass, kids, teacher, supervisor
    ):
        """الصفّ السابع عتبتُه الأولى خمسة: أربعةُ أيّامٍ «عند العتبة»، وستّةٌ «تجاوز»."""
        _absent_days(school, klass, teacher, supervisor, {kids[0]: 4, kids[1]: 6, kids[2]: 1})
        on = SUNDAY + dt.timedelta(days=7)

        rows = supervisor_watchlist(supervisor, school, year, on)["at_gates"]

        assert [(r.student, r.days) for r in rows] == [(kids[1], 6), (kids[0], 4)]
        assert rows[0].passed and "تجاوز" in rows[0].says
        assert not rows[1].passed and "بعد 1 يوم" in rows[1].says


class TestTheDashboard:
    def test_the_supervisor_sees_both_lists_on_his_home_page(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor, monkeypatch
    ):
        _absent_days(school, klass, teacher, supervisor, {kids[0]: 4})
        # اليومُ الأحدُ التالي: آخرُ يومٍ دراسيٍّ قبله الأربعاءُ (غاب فيه ولم يُخطَر أهلُه)،
        # وأيّامُه الأربعةُ كلُّها قبل اليوم فتُعدّ — «عند العتبة» (الخامسة).
        monkeypatch.setattr(
            "django.utils.timezone.localdate", lambda *a, **k: SUNDAY + dt.timedelta(days=7)
        )

        body = client_as(supervisor).get(reverse("dashboard")).content.decode()

        assert "ينتظرون إخطارَ وليّ الأمر" in body
        assert "عند عتبات الغياب بلا عذر" in body
        assert reverse("wings:absence_file", args=[kids[0].id]) in body

    def test_a_quiet_wing_shows_neither_list(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _periods(school, klass, teacher, 7)

        body = client_as(supervisor).get(reverse("dashboard")).content.decode()

        assert "ينتظرون إخطارَ وليّ الأمر" not in body
        assert "عند عتبات الغياب" not in body

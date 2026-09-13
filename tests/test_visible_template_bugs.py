"""أعطالٌ كانت تظهر للمستخدم في القوالب — لكلٍّ منها حارسٌ هنا حتى لا يعود.

وُجدت في مراجعة تنظيم البطاقات (2026-09-13): عدٌّ يُطبع آحاداً متلاصقة،
وإشعارٌ عاجلٌ يُعرض مرّتين، وشريطُ نسبةٍ بعرضٍ صفريّ، وصنفُ شبكةٍ بلا تعريف،
وصفةُ `class` مكرّرةٌ يُهمَل ثانيها، وتنسيقٌ داخل القالب يغلب قاعدةَ الهاتف.
"""

import datetime as dt
import re
from pathlib import Path
from unittest import mock

import pytest
from django.conf import settings
from django.urls import reverse

from core.academic_calendar import academic_year_for_school
from notifications.models import InAppNotification
from operations.models import ScheduleSlot, Subject, SubstituteAssignment, TeacherAbsence
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

TEMPLATES = Path(settings.BASE_DIR) / "templates"
CSS = Path(settings.BASE_DIR) / "static" / "css" / "custom.css"
SUNDAY = dt.date(2026, 9, 13)


@pytest.mark.django_db
class TestCoveredSlotsAreCounted:
    def test_three_covered_slots_read_three_not_111(
        self, client_as, school, principal_user, teacher_user, class_group
    ):
        substitute = UserFactory(full_name="البديل")
        MembershipFactory(
            user=substitute, school=school, role=RoleFactory(school=school, name="teacher")
        )
        subject = Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")
        year = academic_year_for_school(school)
        absence = TeacherAbsence.objects.create(school=school, teacher=teacher_user, date=SUNDAY)
        for period in (1, 2, 3):
            slot = ScheduleSlot.objects.create(
                school=school,
                teacher=teacher_user,
                class_group=class_group,
                subject=subject,
                day_of_week=0,
                period_number=period,
                start_time=dt.time(7, period * 10),
                end_time=dt.time(8, period * 10),
                academic_year=year,
            )
            SubstituteAssignment.objects.create(
                absence=absence, slot=slot, substitute=substitute, school=school
            )

        with mock.patch(
            "operations.views_schedule.SubstituteService.get_available_teachers", return_value=[]
        ):
            resp = client_as(principal_user).get(reverse("absence_detail", args=[absence.id]))

        assert resp.status_code == 200
        assert resp.context["covered_count"] == 3
        assert ">111<" not in resp.content.decode()


@pytest.mark.django_db
class TestUrgentNotificationsShowOnce:
    def test_an_urgent_item_is_pinned_once_even_when_it_is_not_first(
        self, client_as, school, teacher_user
    ):
        urgent = InAppNotification.objects.create(
            user=teacher_user, school=school, title="عاجل", event_type="general", priority="urgent"
        )
        # الأحدثُ عاديٌّ، فالعاجلُ ليس أوّلَ القائمة — وهي الحالُ التي كان قسمُه لا يُفتح فيها.
        InAppNotification.objects.create(
            user=teacher_user, school=school, title="عادي", event_type="general", priority="medium"
        )

        body = client_as(teacher_user).get(reverse("notification_inbox")).content.decode()

        assert body.count(f'id="notif-{urgent.id}"') == 1
        assert 'id="urgent-section"' in body


class TestTemplatesAgreeWithTheStylesheet:
    def test_no_tag_carries_two_class_attributes(self):
        """المتصفّحُ يأخذ الأولى ويُهمل الثانية بصمت — فلا خطأ يُرى ولا لون."""
        twice = re.compile(r'<[a-zA-Z][^<>]*?\sclass="[^"]*"[^<>]*?\sclass="', re.S)
        offenders = [
            f"{path.relative_to(TEMPLATES)}:{text[: m.start()].count(chr(10)) + 1}"
            for path in TEMPLATES.rglob("*.html")
            for text in [path.read_text(encoding="utf-8")]
            for m in twice.finditer(text)
        ]
        assert offenders == []

    @pytest.mark.parametrize("name", ["charts-grid-3", "quick-links--few"])
    def test_the_grid_classes_the_dashboards_use_are_defined(self, name):
        assert re.search(rf"\.{re.escape(name)}\s*\{{", CSS.read_text(encoding="utf-8"))

    @pytest.mark.parametrize("page", ["clinic/dashboard.html", "library/dashboard.html"])
    def test_no_inline_column_count_beats_the_phone_rule(self, page):
        text = (TEMPLATES / page).read_text(encoding="utf-8")
        assert "grid-template-columns:repeat(4,1fr)" not in text
        assert "grid-template-columns:repeat(3,1fr)" not in text

    def test_the_clinic_statistics_link_opens_statistics(self):
        text = (TEMPLATES / "clinic/dashboard.html").read_text(encoding="utf-8")
        link = re.search(
            r'href="\{% url \'([^\']+)\' %\}"[^>]*>(?:(?!</a>).)*الإحصائيات', text, re.S
        )
        assert link and link.group(1) == "clinic:statistics"

"""تفريغُ «لتوليد الجدول» — موسومٌ للمولّد، ولا يمنع البديلَ ولا التبديل.

كان البديلُ والتبديلُ يتجاهلان التفريغَ كلَّه: يُقترح معلّمٌ أخرجته الوزارةُ من
الحصّة. والآن يحترمان التفريغَ الملزم (وزارة/إدارة/قسم/أخرى) ويعبران «لتوليد
الجدول» وحدَه — فهو أداةُ تشكيلٍ للجدول لا منعٌ لصاحبه (قرار 2026-09-11).
"""

from datetime import date, time, timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.models.audit import AuditLog
from core.querysets import year_or_current
from operations.exemption_grid import build_grid
from operations.models import ScheduleSlot, Subject, TeacherExemption
from operations.services import SubstituteService, SwapService
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

DAY, PERIOD = 1, 3


def _teacher(school, name):
    role = RoleFactory(school=school, name="teacher")
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=role)
    return user


def _exempt(school, teacher, *, source, day=DAY, period=PERIOD, full_day=False):
    return TeacherExemption.objects.create(
        school=school,
        teacher=teacher,
        academic_year=year_or_current(school),
        exemption_type="full_day" if full_day else "specific_period",
        day_of_week=day,
        period_number=None if full_day else period,
        reason="اختبار",
        source=source,
    )


class TestModel:
    def test_the_fifth_source_exists_and_is_the_only_soft_one(self):
        sources = dict(TeacherExemption._meta.get_field("source").choices)
        assert sources["generation"] == "لتوليد الجدول"
        assert TeacherExemption.SOFT_SOURCES == frozenset({"generation"})

    @pytest.mark.parametrize("source", ["ministry", "school", "department", "other"])
    def test_every_authority_binds_people(self, school, source):
        row = _exempt(school, _teacher(school, f"معلّم {source}"), source=source)
        assert row.binds_people is True

    def test_generation_does_not_bind_people(self, school):
        row = _exempt(school, _teacher(school, "معلّم التوليد"), source="generation")
        assert row.binds_people is False


class TestSubstitutes:
    def _available(self, school):
        return set(
            SubstituteService.get_available_teachers(school, date.today(), DAY, PERIOD).values_list(
                "full_name", flat=True
            )
        )

    def test_a_binding_exemption_removes_the_teacher_from_the_substitutes(self, school):
        """كان يُقترح — وهو مُخرَجٌ من الحصّة بقرار الوزارة."""
        teacher = _teacher(school, "مفرَّغٌ بقرار")
        _exempt(school, teacher, source="ministry")
        assert "مفرَّغٌ بقرار" not in self._available(school)

    def test_a_full_day_exemption_removes_the_whole_day(self, school):
        teacher = _teacher(school, "مفرَّغٌ يوماً")
        _exempt(school, teacher, source="school", full_day=True)
        assert "مفرَّغٌ يوماً" not in self._available(school)

    def test_a_generation_exemption_keeps_the_teacher_available(self, school):
        """موسومٌ لا ممنوع: رُتّب له جدولُه، ولم يُمنَع من الحصّة."""
        teacher = _teacher(school, "مفرَّغٌ للتوليد")
        _exempt(school, teacher, source="generation")
        assert "مفرَّغٌ للتوليد" in self._available(school)

    def test_another_period_of_the_same_day_is_untouched(self, school):
        teacher = _teacher(school, "مفرَّغٌ في غيرها")
        _exempt(school, teacher, source="ministry", period=PERIOD + 1)
        assert "مفرَّغٌ في غيرها" in self._available(school)


class TestSwaps:
    def _slots(self, school, a, b):
        subject = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
        group = ClassGroupFactory(school=school, grade="G8", section="1")
        year = year_or_current(school)

        def slot(teacher, day, period):
            return ScheduleSlot.objects.create(
                school=school,
                class_group=group,
                teacher=teacher,
                subject=subject,
                day_of_week=day,
                period_number=period,
                start_time=time(7 + period, 0),
                end_time=time(7 + period, 45),
                academic_year=year,
                is_active=True,
            )

        return slot(a, DAY, PERIOD), slot(b, DAY + 1, PERIOD + 1)

    def _errors(self, school, a, slot_a, slot_b):
        return SwapService.validate_swap_request(
            a, slot_a, slot_b, date.today() + timedelta(days=3), school
        )

    def test_swapping_into_a_binding_exemption_is_refused(self, school):
        """المعلّمُ ب يأخذ خانةَ أ — وهو مفرَّغٌ فيها بقرار الإدارة."""
        a, b = _teacher(school, "المعلّم أ"), _teacher(school, "المعلّم ب")
        slot_a, slot_b = self._slots(school, a, b)
        _exempt(school, b, source="school", day=slot_a.day_of_week, period=slot_a.period_number)

        errors = self._errors(school, a, slot_a, slot_b)
        assert any("المعلّم ب" in e and "ملزم" in e for e in errors)

    def test_the_requester_is_checked_against_the_other_slot_too(self, school):
        a, b = _teacher(school, "الطالبُ أ"), _teacher(school, "المستهدفُ ب")
        slot_a, slot_b = self._slots(school, a, b)
        _exempt(school, a, source="department", day=slot_b.day_of_week, period=slot_b.period_number)

        errors = self._errors(school, a, slot_a, slot_b)
        assert any("الطالبُ أ" in e and "ملزم" in e for e in errors)

    def test_a_generation_exemption_does_not_block_the_swap(self, school):
        a, b = _teacher(school, "أ للتوليد"), _teacher(school, "ب للتوليد")
        slot_a, slot_b = self._slots(school, a, b)
        _exempt(school, b, source="generation", day=slot_a.day_of_week, period=slot_a.period_number)

        errors = self._errors(school, a, slot_a, slot_b)
        assert not any("ملزم" in e for e in errors)


class TestGrid:
    def test_the_grid_marks_soft_cells_and_only_them(self, school):
        teacher = _teacher(school, "صاحبُ الشبكة")
        _exempt(school, teacher, source="generation", day=0, period=1)
        _exempt(school, teacher, source="school", day=0, period=2)

        grid = build_grid(school, teacher, year_or_current(school))
        cells = {c.period: c for c in grid.rows[0].cells}
        assert cells[1].exemption_id and cells[1].soft is True
        assert cells[2].exemption_id and cells[2].soft is False
        assert cells[3].soft is False


class TestRelabel:
    def test_dry_run_changes_nothing(self, school, capsys):
        teacher = _teacher(school, "يُعاد وسمُه")
        row = _exempt(school, teacher, source="school")

        # `--teacher` قائمةٌ (`action="append"`) — ونصٌّ مفردٌ يُقطَّع حروفاً.
        call_command("relabel_exemptions", teacher=["يُعاد وسمُه"], to="generation")

        row.refresh_from_db()
        assert row.source == "school"
        assert "عرضٌ فقط" in capsys.readouterr().out

    def test_apply_relabels_and_leaves_an_audit_row(self, school):
        teacher = _teacher(school, "يُعاد وسمُه فعلاً")
        row = _exempt(school, teacher, source="school")
        other = _exempt(school, _teacher(school, "لا يُمسّ"), source="school", period=PERIOD + 2)

        call_command("relabel_exemptions", teacher=["يُعاد وسمُه فعلاً"], to="generation", apply=True)

        row.refresh_from_db()
        other.refresh_from_db()
        assert row.source == "generation"
        assert other.source == "school"
        entry = AuditLog.objects.filter(object_id=str(row.pk)).latest("timestamp")
        assert entry.changes["source"] == ["school", "generation"]

    def test_an_ambiguous_name_is_refused(self, school):
        _teacher(school, "اسمٌ مكرّر")
        _teacher(school, "اسمٌ مكرّر")
        with pytest.raises(CommandError, match="حساباً"):
            call_command("relabel_exemptions", teacher=["اسمٌ مكرّر"], to="generation")

    def test_an_unknown_source_is_refused(self, school):
        _teacher(school, "أيُّ معلّم")
        with pytest.raises(CommandError, match="غيرُ معروفة"):
            call_command("relabel_exemptions", teacher=["أيُّ معلّم"], to="whatever")

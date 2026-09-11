"""إغلاقُ القيود المتقادمة — قيدُ عامٍ مضى، ومن لم يعد في سجلّ القيد."""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.models.academic import StudentEnrollment
from core.models.audit import AuditLog
from core.querysets import year_or_current
from tests.conftest import ClassGroupFactory, StudentEnrollmentFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def year(school):
    return year_or_current(school)


@pytest.fixture
def past(year):
    """عامٌ قبل الجاري — يُشتقّ منه ولا يُثبَّت.

    مدرسةُ الاختبار بلا تقويم، فالعامُ الجاري يرتدّ إلى الثابت المجمَّد. وتثبيتُ
    «2025-2026» ماضياً يجعله هو الجاريَ نفسَه، فلا يبقى قيدٌ متقادمٌ أصلاً.
    """
    start = int(year.split("-")[0]) - 1
    return f"{start}-{start + 1}"


def _enrol(school, student, academic_year, section="1", grade="G8"):
    group = ClassGroupFactory(
        school=school, grade=grade, section=section, academic_year=academic_year
    )
    return StudentEnrollmentFactory(student=student, class_group=group)


def _register(tmp_path, national_ids):
    """سجلُّ قيدٍ مسطَّحٌ كتصدير 2026-2027."""
    import openpyxl

    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "الجميع"
    sheet.append(["الرقم الشخصي", "الاسم", "الصف ", "الصف/الشعبة"])
    for index, national_id in enumerate(national_ids, 1):
        sheet.append([national_id, f"طالب {index}", "8", "08/1"])
    path = tmp_path / "سجل.xlsx"
    book.save(path)
    return str(path)


class TestPastYears:
    def test_a_past_year_enrollment_is_closed_and_the_current_one_survives(
        self, school, year, past
    ):
        student = UserFactory(full_name="مزدوجُ القيد", national_id="31400000001")
        old = _enrol(school, student, past, section="1")
        new = _enrol(school, student, year, section="2")

        call_command("close_stale_enrollments", apply=True)

        old.refresh_from_db()
        new.refresh_from_db()
        assert old.is_active is False
        assert new.is_active is True

    def test_nothing_is_written_without_apply(self, school, year, past, capsys):
        student = UserFactory(full_name="لا يُمسّ", national_id="31400000002")
        old = _enrol(school, student, past)

        call_command("close_stale_enrollments")

        old.refresh_from_db()
        assert old.is_active is True
        assert "عرضٌ فقط" in capsys.readouterr().out

    def test_whoever_is_left_without_any_enrollment_is_named_first(
        self, school, year, past, capsys
    ):
        """إغلاقُ قيدِ من لا قيدَ له غيرُه يتركه بلا صفّ — يُعرض قبل الكتابة."""
        student = UserFactory(full_name="خرّيجُ العام الماضي", national_id="31400000003")
        _enrol(school, student, past)

        call_command("close_stale_enrollments")

        out = capsys.readouterr().out
        assert "يبقون بلا قيدٍ نشط: 1 طالباً" in out
        assert "خرّيجُ العام الماضي" in out

    def test_a_clean_database_says_so(self, school, year, capsys):
        student = UserFactory(full_name="قيدُه سليم", national_id="31400000004")
        _enrol(school, student, year)

        call_command("close_stale_enrollments")

        assert "لا قيدَ متقادماً" in capsys.readouterr().out


class TestNotInRegister:
    def test_a_current_student_absent_from_the_register_is_closed(self, school, year, tmp_path):
        staying = UserFactory(full_name="في السجلّ", national_id="31400000010")
        leaving = UserFactory(full_name="ليس في السجلّ", national_id="31400000011")
        kept = _enrol(school, staying, year, section="1")
        dropped = _enrol(school, leaving, year, section="2")

        call_command(
            "close_stale_enrollments",
            not_in_register=_register(tmp_path, ["31400000010"]),
            keep_past_years=True,
            apply=True,
        )

        kept.refresh_from_db()
        dropped.refresh_from_db()
        assert kept.is_active is True
        assert dropped.is_active is False

    def test_past_years_are_untouched_when_asked(self, school, year, past, tmp_path):
        student = UserFactory(full_name="قيدُه قديمٌ فقط", national_id="31400000012")
        old = _enrol(school, student, past)

        call_command(
            "close_stale_enrollments",
            not_in_register=_register(tmp_path, ["31400000012"]),
            keep_past_years=True,
            apply=True,
        )

        old.refresh_from_db()
        assert old.is_active is True

    def test_both_modes_together_close_both_kinds(self, school, year, past, tmp_path):
        student = UserFactory(full_name="قديمٌ وغائب", national_id="31400000013")
        old = _enrol(school, student, past, section="1")
        current = _enrol(school, student, year, section="2")

        call_command(
            "close_stale_enrollments",
            not_in_register=_register(tmp_path, ["31499999999"]),
            apply=True,
        )

        old.refresh_from_db()
        current.refresh_from_db()
        assert old.is_active is False
        assert current.is_active is False

    def test_keeping_past_years_without_a_register_leaves_no_work(self, school, year):
        with pytest.raises(CommandError, match="لا يُبقي عملاً"):
            call_command("close_stale_enrollments", keep_past_years=True)


class TestAudit:
    def test_the_operation_leaves_one_row_naming_who_lost_an_enrollment(self, school, year, past):
        """سطرٌ واحدٌ لا خمسمئة — ومعه الأسماءُ لتتبّع من فقد قيدَه."""
        student = UserFactory(full_name="مذكورٌ في التدقيق", national_id="31400000020")
        _enrol(school, student, past)

        call_command("close_stale_enrollments", apply=True)

        entry = AuditLog.objects.filter(object_repr__contains="قيداً متقادماً").latest("timestamp")
        assert entry.changes["event"] == "stale_enrollments_closed"
        assert entry.changes["closed"] == 1
        assert entry.changes["year"] == year
        assert entry.changes["modes"]["past_years"] is True
        assert "مذكورٌ في التدقيق" in entry.changes["students"]

    def test_running_twice_closes_nothing_the_second_time(self, school, year, past, capsys):
        student = UserFactory(full_name="مرّتان", national_id="31400000021")
        _enrol(school, student, past)

        call_command("close_stale_enrollments", apply=True)
        capsys.readouterr()
        call_command("close_stale_enrollments", apply=True)

        assert "لا قيدَ متقادماً" in capsys.readouterr().out
        assert StudentEnrollment.objects.filter(student=student, is_active=True).count() == 0

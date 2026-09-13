"""الدرجةُ منسوبةً إلى الأساس المعتمَد — ومئةٌ تعني «بمستوى ما اعتمدناه»."""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.utils import IntegrityError

from operations.models import ScheduleBaseline
from operations.schedule_lab import RELATIVE_CAP, latest_baseline, relative_score

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"


def _metrics(**values):
    """مؤشّراتٌ مصغَّرةٌ بصيغة المختبر."""
    return {key: {"value": v, "detail": {}} for key, v in values.items()}


class TestRelativeScore:
    def test_a_schedule_measured_against_itself_reads_one_hundred(self):
        m = _metrics(**{"validity.completeness": 100.0, "teacher.run_breaches": 15.8})
        assert relative_score(m, m) == 100.0

    def test_without_a_baseline_there_is_no_relative_reading(self):
        """لا رقمَ يُخترع بلا مرجع — والشاشةُ تعرض المطلقةَ موسومة."""
        assert relative_score(_metrics(**{"validity.completeness": 90.0}), None) is None
        assert relative_score(_metrics(**{"validity.completeness": 90.0}), {}) is None

    def test_falling_short_of_the_baseline_reads_below_one_hundred(self):
        base = _metrics(**{"validity.completeness": 100.0})
        worse = _metrics(**{"validity.completeness": 80.0})
        assert relative_score(worse, base) == 80.0

    def test_beating_the_baseline_reads_above_one_hundred(self):
        base = _metrics(**{"validity.completeness": 80.0})
        better = _metrics(**{"validity.completeness": 100.0})
        assert relative_score(better, base) == min(RELATIVE_CAP, 125.0)

    def test_one_soaring_metric_cannot_hide_three_falling_ones(self):
        """السقفُ يُبقي التحسّنَ مرئيّاً ويمنعه من الستر."""
        base = _metrics(
            **{
                "validity.completeness": 10.0,
                "teacher.run_breaches": 10.0,
                "class.maths_late": 10.0,
            }
        )
        mixed = _metrics(
            **{
                "validity.completeness": 100.0,  # عشرةُ أضعاف — يُقصّ عند السقف
                "teacher.run_breaches": 50.0,  # وهذان تراجعٌ
                "class.maths_late": 50.0,
            }
        )
        # بلا سقفٍ لكان المتوسّطُ 400؛ وبالسقف يظهر التراجعُ في الرقم.
        assert relative_score(mixed, base) < RELATIVE_CAP

    def test_a_metric_missing_from_the_baseline_is_skipped(self):
        """مؤشّرٌ أُضيف بعد تثبيت الأساس لا أساسَ له — يُقصى حتّى يُحدَّث."""
        base = _metrics(**{"validity.completeness": 100.0})
        now = _metrics(**{"validity.completeness": 100.0, "teacher.run_breaches": 99.0})
        assert relative_score(now, base) == 100.0


class TestPinning:
    def _baseline(self, school, label, *, pinned):
        return ScheduleBaseline.objects.create(
            school=school, academic_year=YEAR, label=label, metrics={}, is_pinned=pinned
        )

    def test_the_pinned_one_wins_over_a_newer_save(self, school):
        """زرُّ «حفظ أساس» في المختبر للاستكشاف — ولا يُزيح المرجعَ المعروض."""
        pinned = self._baseline(school, "المعتمَد", pinned=True)
        self._baseline(school, "تجربة أحدث", pinned=False)

        assert latest_baseline(school, YEAR) == pinned

    def test_without_a_pin_the_newest_is_used_as_before(self, school):
        self._baseline(school, "قديم", pinned=False)
        newest = self._baseline(school, "أحدث", pinned=False)

        assert latest_baseline(school, YEAR) == newest

    def test_two_pinned_baselines_in_one_year_are_refused_by_the_database(self, school):
        """مرجعان معتمَدان يجعلان الدرجةَ تابعةً لترتيب الصفوف."""
        self._baseline(school, "الأوّل", pinned=True)
        with pytest.raises(IntegrityError):
            self._baseline(school, "الثاني", pinned=True)


class TestCommand:
    def test_pinning_needs_a_name(self, school):
        with pytest.raises(CommandError, match="اسمٌ يُعرف به"):
            call_command("schedule_lab", "--live", "--pin", year=YEAR)

"""درجةُ المختبر لا تتبع حجمَ المدرسة — والعدّادُ المطلقُ لا يدخل حكماً.

ثلاثةُ عدّاداتٍ كانت تُغذَّى في منحنى الدرجة `100 − v` وهو منحنًى كُتب للنسب
المئويّة، فقُرئ «55 يوماً فيها تلاصق» على أنّه 55٪ فأعطى 45 درجة — بينما هي
خمسةَ عشرَ في المئة من ثلاثمئةٍ وثمانيةٍ وأربعين يومَ معلّم. ومؤشّرا «الأقصى»
كانا يقيسان أتعسَ معلّمٍ في أتعسِ يومٍ ويأخذان جزأين من ثلاثةٍ وعشرين من درجة
المدرسة كلِّها.
"""

import pytest

from operations.schedule_lab import CATALOG, _rate, metric_score

#: المؤشّراتُ التي درجتُها متمّمُ قيمتها — فيجب أن تكون نسباً مئويّةً لا عدداً.
COMPLEMENT_SCORED = (
    "teacher.run_breaches",
    "teacher.pattern_breaches",
    "resources.saturated_slots",
    "class.heavy_streak_days",
    "class.maths_late",
)

#: ما يقيس أسوأَ حالةٍ فردية — يُعرض ولا يُحكم به.
WORST_CASE = ("teacher.gap_weighted_max", "teacher.transitions_max")


class TestRate:
    @pytest.mark.parametrize(
        ("part", "whole", "expected"),
        [(55, 348, 15.8), (8, 72, 11.1), (0, 100, 0.0), (100, 100, 100.0)],
    )
    def test_the_rate_is_a_percentage_of_its_population(self, part, whole, expected):
        assert _rate(part, whole) == expected

    def test_an_empty_population_has_no_rate(self):
        """مدرسةٌ بلا معلّمين لا نسبةَ لها — و`None` تُقصى من الدرجة ولا تُقرأ صفراً."""
        assert _rate(3, 0) is None

    def test_the_same_rate_scores_the_same_at_any_size(self):
        """جوهرُ الإصلاح: مدرسةٌ ضعفَ الأخرى بنفس النسبة تأخذ الدرجةَ نفسَها."""
        small = metric_score("teacher.run_breaches", _rate(10, 100))
        large = metric_score("teacher.run_breaches", _rate(100, 1000))
        assert small == large == 90.0


class TestCatalog:
    @pytest.mark.parametrize("key", COMPLEMENT_SCORED)
    def test_whatever_is_scored_by_its_complement_is_a_percentage(self, key):
        """`100 − v` على عدّادٍ مطلقٍ يجعل الدرجةَ تابعةً لحجم المدرسة."""
        _label, unit, better = CATALOG[key]
        assert unit == "%", f"{key} يُقاس بمتمّمه فيجب أن يكون نسبة"
        assert better == "low"

    @pytest.mark.parametrize("key", WORST_CASE)
    def test_worst_case_metrics_are_shown_not_judged(self, key):
        """أسوأُ معلّمٍ في أسوأِ يومٍ لا يمثّل المدرسة — ولا يتحسّن بتحسّنها."""
        assert CATALOG[key][2] == "info"
        assert metric_score(key, 4.5) is None

    def test_the_average_counterparts_still_carry_the_signal(self):
        """إخراجُ «الأقصى» لا يُعمي الدرجة: المتوسّطُ يبقى محكوماً به."""
        for key in ("teacher.gap_weighted_avg", "teacher.transitions_avg"):
            assert CATALOG[key][2] == "low"
            assert metric_score(key, 0.5) is not None

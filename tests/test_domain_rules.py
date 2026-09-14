"""قواعدُ المجال الصافية (`core/domain/`) تُخرج ما كانت المواضعُ القديمة تُخرجه.

كانت نسبةُ الحضور وشرائحُ الدرجات ولونُ الرقم تُكتب في كلّ موضعٍ بعتباته.
وجُمعت في `core/domain/` — والشرطُ: **لا تغييرَ في الأرقام المعروضة**. فهنا
النسخُ القديمةُ حرفيّاً (كما كانت في الملفّات قبل الترحيل) مرجعاً، وتُقارَن
بالجديد على عيّنةٍ كثيفة: كلُّ نصفِ درجةٍ من صفر إلى مئة، والأطرافُ، و`None`،
و`Decimal`.

الاستثناءُ الواحدُ موثَّقٌ في `test_attendance_rate_matches_exact_half_rounding`:
صيغةُ `p / t * 100` القديمةُ تُخطئ عند الأنصاف بخطأ الفاصلة العائمة؛ والجديدةُ
`p * 100 / t` تطابق التقريبَ الدقيق (`Fraction`) في كلّ الأزواج حتّى 400.
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

import pytest

from core.domain.attendance import attendance_rate, percent
from core.domain.grades import GRADE_BANDS, band_of, letter_of
from core.domain.tones import (
    ATTENDANCE_KPI,
    ATTENDANCE_SUMMARY,
    AVERAGE_KPI,
    GRADE_CELL,
    SHARE_KPI,
    tone_for,
)

#: كلُّ نصفِ درجةٍ من 0 إلى 100، والأطرافُ التي تكسر العتبات.
SCORES = [x / 2 for x in range(0, 201)] + [-1, 100.5, 49.999, 89.999, 94.999, 0.01]
SCORES_WITH_DECIMAL = SCORES + [Decimal("74.99"), Decimal("75"), Decimal("90.00")]


# ══════════════════════════════════════════════════════════════════════
#  النسخُ القديمة — حرفيّاً كما كانت قبل 2026-09-14
# ══════════════════════════════════════════════════════════════════════


def old_letter_grade(annual_total):
    """`assessments/models.py:518-539` قبل الترحيل."""
    if annual_total is None:
        return "—"
    t = float(annual_total)
    if t >= 95:
        return "A+"
    if t >= 90:
        return "A"
    if t >= 85:
        return "B+"
    if t >= 80:
        return "B"
    if t >= 75:
        return "C+"
    if t >= 70:
        return "C"
    if t >= 65:
        return "D+"
    if t >= 50:
        return "D"
    return "F"


def old_analytics_buckets(grades):
    """`analytics/views.py:234-250` قبل الترحيل."""
    buckets = {"90-100": 0, "80-89": 0, "70-79": 0, "60-69": 0, "50-59": 0, "أقل من 50": 0}
    for g in grades:
        if g is None:
            continue
        g = float(g)
        if g >= 90:
            buckets["90-100"] += 1
        elif g >= 80:
            buckets["80-89"] += 1
        elif g >= 70:
            buckets["70-79"] += 1
        elif g >= 60:
            buckets["60-69"] += 1
        elif g >= 50:
            buckets["50-59"] += 1
        else:
            buckets["أقل من 50"] += 1
    return buckets


def old_assessment_bands(results_values):
    """`assessments/services.py:611-627` قبل الترحيل."""
    bands = [0] * 6  # <50, 50-59, 60-69, 70-79, 80-89, 90-100
    for r in results_values:
        if r is None:
            continue
        t = float(r)
        if t >= 90:
            bands[5] += 1
        elif t >= 80:
            bands[4] += 1
        elif t >= 70:
            bands[3] += 1
        elif t >= 60:
            bands[2] += 1
        elif t >= 50:
            bands[1] += 1
        else:
            bands[0] += 1
    return bands


def old_parent_att_tone(pct):
    """`parents/views.py:269` قبل الترحيل."""
    return "green" if pct >= 90 else "amber" if pct >= 75 else "red"


def old_parent_kpi_att_tone(pct):
    """`parents/services.py:304-312` قبل الترحيل."""
    return "blue" if pct is None else "green" if pct >= 90 else "amber" if pct >= 75 else "red"


def old_parent_avg_tone(avg):
    """`parents/views.py:214` قبل الترحيل."""
    return "green" if avg >= 80 else "amber" if avg >= 60 else "red"


def old_share_tone(pct, green=90, amber=75):
    """`student_affairs/views.py:157-163` قبل الترحيل."""
    if pct >= green:
        return "green", "status-success"
    if pct >= amber:
        return "orange", "status-warning"
    return "red", "status-danger"


def old_grade_cell_tone(total):
    """`parents/services.py:388-401` قبل الترحيل (وكذا `assessments/views.py:40-55` بعد النسبة)."""
    if total is None:
        return "muted"
    total = float(total)
    return (
        "success"
        if total >= 80
        else "info"
        if total >= 65
        else "warning"
        if total >= 50
        else "danger"
    )


def old_behavior_share_tone(pct):
    """`behavior/views.py:716` و`:1017` قبل الترحيل."""
    return "green" if pct >= 80 else ("amber" if pct >= 50 else "red")


def old_net_score_rating(net_score):
    """`behavior/services.py:137-144` قبل الترحيل."""
    if net_score >= 90:
        return "ممتاز", "green"
    if net_score >= 75:
        return "جيد جداً", "blue"
    if net_score >= 60:
        return "جيد", "amber"
    return "يحتاج تطوير", "red"


def old_net_score_status(net_score):
    """`behavior/services.py:193-197` قبل الترحيل."""
    return "green" if net_score >= 80 else ("yellow" if net_score >= 60 else "red")


def old_report_grade_tone(total):
    """`reports/views.py:146-156` قبل الترحيل."""
    if not total:
        return "muted"
    if total >= 90:
        return "green"
    if total >= 75:
        return "blue"
    if total >= 50:
        return "orange"
    return "red"


def old_annual_grade(total):
    """`reports/views.py:206-221` قبل الترحيل."""
    if not total:
        return "na"
    if total >= 90:
        return "a"
    if total >= 75:
        return "b"
    if total >= 60:
        return "c"
    return "f"


def old_attendance_report(pct):
    """`reports/views.py:239-244` قبل الترحيل."""
    if pct >= 95:
        return "ممتاز", "green"
    if pct >= 80:
        return "مقبول", "orange"
    return "منخفض", "red"


def old_combined_tone(score):
    """`academic_management/views.py:124-132` قبل الترحيل."""
    if score is None:
        return "is-muted"
    if score >= 75:
        return "is-success"
    if score >= 50:
        return "is-warning"
    return "is-danger"


def old_bar_tone(pct, green_at=70, amber_at=40):
    """`quality/presentation.py:84-90` قبل الترحيل."""
    if pct >= green_at:
        return "green"
    if pct >= amber_at:
        return "amber"
    return "red"


def old_observation_score_tone(score):
    """`quality/presentation.py:102-110` قبل الترحيل."""
    if score is None:
        return "muted"
    if score >= 75:
        return "success"
    if score >= 50:
        return "warning"
    return "danger"


def old_lab_tone(relative):
    """`operations/views_schedule.py:916-925` قبل الترحيل."""
    return (
        ""
        if relative is None
        else "success"
        if relative >= 98
        else "warning"
        if relative >= 90
        else "danger"
    )


def old_infraction_tones(infraction_pct, today_infractions, unresolved):
    """`student_affairs/views.py:1393-1396` قبل الترحيل."""
    pct_tone = "green" if infraction_pct < 10 else "orange" if infraction_pct < 25 else "red"
    today_tone = "green" if not today_infractions else "orange" if today_infractions < 5 else "red"
    unresolved_tone = "green" if not unresolved else "orange" if unresolved < 10 else "red"
    return pct_tone, today_tone, unresolved_tone


def old_absence_days_tone(absent):
    """`parents/services.py:322` قبل الترحيل."""
    return "red" if absent >= 5 else "amber" if absent else "green"


def old_half_tone(score, out_of):
    """`assessments/views.py:58-62` قبل الترحيل."""
    if score is None:
        return "muted"
    return "success" if float(score) >= float(out_of) * 0.5 else "danger"


# ══════════════════════════════════════════════════════════════════════
#  نسبةُ الحضور
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("total", range(0, 121))
def test_attendance_rate_matches_exact_half_rounding(total):
    """`p * 100 / t` تطابق التقريبَ الدقيق لكلّ حاضرٍ من صفر إلى المجموع."""
    for present in range(total + 1):
        exact = round(Fraction(present * 100, total)) if total else 0
        assert attendance_rate(present, total) == exact
        assert attendance_rate(present, total) == (round(present * 100 / total) if total else 0)


def test_attendance_rate_old_formula_differs_only_at_float_halves():
    """توثيقُ الاستثناء الوحيد: الصيغةُ القديمة `p / t * 100` تُخطئ عند الأنصاف.

    ليست هذه انحرافاً في العتبات بل خطأُ فاصلةٍ عائمة كان في نصف المواضع دون
    نصفها الآخر — فالموضعان كانا يعرضان رقمين مختلفين للحضور نفسه.
    """
    mismatches = [
        (p, t)
        for t in range(1, 401)
        for p in range(t + 1)
        if round(p / t * 100) != attendance_rate(p, t)
    ]
    assert mismatches, "لو زال الفرقُ فليُحذف هذا التوثيق"
    for p, t in mismatches:
        assert Fraction(p * 100, t).denominator == 2, f"فرقٌ في غير نصفٍ دقيق: {p}/{t}"


def test_attendance_rate_empty_and_digits():
    assert attendance_rate(0, 0) == 0
    assert attendance_rate(0, 0, empty=100) == 100
    assert attendance_rate(0, 0, empty=None) is None
    assert attendance_rate(None, 0) == 0
    assert attendance_rate(1, 3, digits=1) == round(1 / 3 * 100, 1)
    assert attendance_rate(2, 3, digits=1) == round(2 * 100 / 3, 1)
    assert isinstance(attendance_rate(1, 2), int)
    assert isinstance(attendance_rate(1, 2, digits=1), float)
    assert attendance_rate(Decimal("3"), Decimal("4")) == 75


def test_percent_is_the_generic_form():
    for total in range(0, 60):
        for part in range(total + 1):
            assert percent(part, total) == attendance_rate(part, total)
    assert percent(7.0, 9.0) == round(7 * 100 / 9)


# ══════════════════════════════════════════════════════════════════════
#  شرائحُ الدرجات
# ══════════════════════════════════════════════════════════════════════


def test_letter_grade_unchanged():
    for score in SCORES_WITH_DECIMAL + [None]:
        assert letter_of(score) == old_letter_grade(score), score


def test_analytics_buckets_unchanged():
    grades = SCORES_WITH_DECIMAL + [None, None]
    buckets = {band.label: 0 for band in GRADE_BANDS}
    for g in grades:
        band = band_of(g)
        if band is not None:
            buckets[band.label] += 1
    assert buckets == old_analytics_buckets(grades)
    assert list(buckets) == list(old_analytics_buckets([]))


def test_assessment_bands_unchanged():
    values = SCORES_WITH_DECIMAL + [None]
    bands = [0] * len(GRADE_BANDS)
    for r in values:
        band = band_of(r)
        if band is not None:
            bands[band.rank] += 1
    assert bands == old_assessment_bands(values)


def test_grade_bands_are_descending_and_contiguous():
    lows = [b.low for b in GRADE_BANDS]
    assert lows == sorted(lows, reverse=True)
    assert lows[-1] == 0
    assert [b.rank for b in GRADE_BANDS] == list(range(len(GRADE_BANDS) - 1, -1, -1))


# ══════════════════════════════════════════════════════════════════════
#  لونُ الرقم
# ══════════════════════════════════════════════════════════════════════


def test_attendance_tones_unchanged():
    for pct in SCORES:
        assert tone_for(pct, ATTENDANCE_KPI) == old_parent_att_tone(pct), pct
        assert tone_for(pct, ATTENDANCE_SUMMARY, empty=("", "")) == old_share_tone(pct), pct
        assert tone_for(pct, ATTENDANCE_KPI, empty="blue") == old_parent_kpi_att_tone(pct), pct
    assert tone_for(None, ATTENDANCE_KPI, empty="blue") == old_parent_kpi_att_tone(None)


def test_average_and_share_tones_unchanged():
    for value in SCORES:
        assert tone_for(value, AVERAGE_KPI) == old_parent_avg_tone(value), value
        assert tone_for(value, SHARE_KPI) == old_behavior_share_tone(value), value


def test_grade_cell_tone_unchanged():
    for total in SCORES_WITH_DECIMAL + [None]:
        assert tone_for(total, GRADE_CELL) == old_grade_cell_tone(total), total


def test_behavior_service_scales_unchanged():
    from behavior.services import NET_SCORE_RATING, NET_SCORE_STATUS

    for score in SCORES:
        assert tone_for(score, NET_SCORE_RATING) == old_net_score_rating(score), score
        assert tone_for(score, NET_SCORE_STATUS) == old_net_score_status(score), score


def test_reports_scales_unchanged():
    from reports.views import (
        ANNUAL_GRADE_CLASSES,
        ANNUAL_TOTAL_TONES,
        ATTENDANCE_REPORT_LABELS,
        _annual_grade,
        _grade_tone,
    )

    for total in SCORES_WITH_DECIMAL + [None]:
        assert _grade_tone(total) == old_report_grade_tone(total), total
        assert _annual_grade(total) == old_annual_grade(total), total
        if total:  # الصفرُ و`None` يحرسهما الشرطُ الأوّل في الدالّتين
            assert tone_for(total, ANNUAL_TOTAL_TONES) == old_report_grade_tone(total)
            assert tone_for(total, ANNUAL_GRADE_CLASSES) == old_annual_grade(total)
    for pct in SCORES:
        assert tone_for(pct, ATTENDANCE_REPORT_LABELS) == old_attendance_report(pct), pct


def test_academic_and_quality_scales_unchanged():
    from academic_management.views import _combined_tone
    from quality.presentation import bar_tone, observation_score_tone

    for score in SCORES + [None]:
        assert _combined_tone(score) == old_combined_tone(score), score
        assert observation_score_tone(score) == old_observation_score_tone(score), score
    for pct in SCORES:
        assert bar_tone(pct) == old_bar_tone(pct), pct
        assert bar_tone(pct, green_at=80, amber_at=50) == old_bar_tone(pct, 80, 50), pct


def test_schedule_lab_tone_unchanged():
    from operations.views_schedule import LAB_RELATIVE_TONES

    for relative in SCORES + [None]:
        assert tone_for(relative, LAB_RELATIVE_TONES, empty="") == old_lab_tone(relative), relative


def test_student_affairs_kpi_scales_unchanged():
    from student_affairs.views import (
        INFRACTION_SHARE_KPI,
        TODAY_INFRACTIONS_KPI,
        UNRESOLVED_KPI,
        _share_tone,
    )

    for pct in SCORES:
        assert _share_tone(pct) == old_share_tone(pct), pct
    for pct in SCORES:
        for today in range(0, 12):
            for unresolved in range(0, 15):
                assert (
                    tone_for(pct, INFRACTION_SHARE_KPI),
                    tone_for(today, TODAY_INFRACTIONS_KPI),
                    tone_for(unresolved, UNRESOLVED_KPI),
                ) == old_infraction_tones(pct, today, unresolved)


def test_parent_absence_days_scale_unchanged():
    from parents.services import ABSENCE_DAYS_KPI

    for absent in range(0, 20):
        assert tone_for(absent, ABSENCE_DAYS_KPI) == old_absence_days_tone(absent), absent


def test_assessment_half_tone_unchanged():
    from assessments.views import _grade_tone, _half_tone

    for out_of in (Decimal("20"), Decimal("40"), Decimal("60"), 100):
        for score in SCORES_WITH_DECIMAL + [None]:
            assert _half_tone(score, out_of) == old_half_tone(score, out_of), (score, out_of)
            if score is None or float(score) < 0:
                continue
            expected = old_grade_cell_tone(float(score) / float(out_of) * 100)
            assert _grade_tone(score, out_of) == expected, (score, out_of)


def test_tone_for_requires_a_fallback():
    with pytest.raises(ValueError):
        tone_for(5, ((10, "green"),))

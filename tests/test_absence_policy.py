"""[LEGAL] عتباتُ الغياب والتأخّر هي أرقامُ الوزارة — لا نسبةٌ من عندنا.

## ثلاثةُ مصادرَ تعاقبت

كانت المنصّةُ تحسب «10٪ من أيام الدراسة (≈19 يوماً من 190)» وتنسبها إلى
المادة 7 من قانون التعليم الإلزامي 25/2001. وراجعتُ نصّ القانون: مادّتُه
السابعة توجب إخطارَ المسؤول عن الطفل بكتابٍ مسجَّل، ولا تذكر نسبةً ولا عددَ
أيّام — لا هي ولا سائرُ مواده الثلاث عشرة.

ثمّ صُحّحت إلى «سياسة تقييم الطلبة 2018» (القرار 22/2015): 7·10·13·15 للصفوف
4–11، و10·15 للثاني عشر.

**والنافذُ اليوم** «الدليل التنظيمي لسياسة إدارة سلوك الطلبة **2026**» — قسم
حماية ورعاية الطلبة، والملفُّ في `data/2026-2027/`:

    1–11          5 · 8 · 11 · 15     م 3.4.1.3 (ص29)
    الثاني عشر    8 · 15              (عتبتا المنتصف مقصورتان على 1–11)
    ذوو الإعاقة   8 · 15              م 3.7.3.3 (ص139–140)

تراكميّاً من بداية العام، متصلةً أو غيرَ متصلة، وأثرُها الحرمانُ من دخول
الاختبار بقرارِ **فريق إدارة سلوك الطلبة** — لا إشعارُ وليّ الأمر.

## ولمَ ملفٌّ واحد

كُتبت أرقامُ 2026 أوّلاً في ملفٍّ ثانٍ إلى جانب هذا، فصار للوحدة حارسان
بأرقامٍ متعارضة: أحدُهما يُثبّت السبعةَ والآخرُ الخمسة. وحارسان يتناقضان أسوأُ
من حارسٍ واحدٍ يُخفق — فمن يقرأ لا يدري أيُّهما الحقّ. فدُمجا هنا.

## وهذه الحرّاسُ تُثبّت الأرقامَ بأعيانها

فرقمٌ يتغيّر بلا مراجعةٍ للنصّ يحرم طالباً من حقّه، أو يترك آخرَ يدخل وهو
محروم — وكلاهما **لا يُخفق في أيّ شاشة**.
"""

import pytest

from operations import absence_policy as policy
from operations.absence_policy import (
    ACCEPTED_EXCUSES,
    BAND_1_11,
    BAND_12,
    BAND_ESE,
    BAND_UNKNOWN,
    GATES_1_11,
    GATES_12,
    GATES_ESE,
    GUARDIAN_REPLY_DAYS,
    MEDICAL_PROOF_DAYS_AFTER_RETURN,
    MIN_PERIODS_FOR_PRESENCE,
    SUMMON_DAYS,
    TARDIES_PER_ABSENCE_DAY,
    TARDY_AFTER_MINUTES,
    TARDY_LADDER,
    absence_days_from_tardies,
    band_for,
    breached,
    gates_for,
    next_gate,
    tardy_step,
)


class TestTheNumbersAreTheGuides:
    def test_grades_one_to_eleven_have_four_gates(self):
        """م 3.4.1.3: خمسةٌ · ثمانيةٌ · إحدى عشرةَ · خمسةَ عشر."""
        assert [g.max_days for g in GATES_1_11] == [5, 8, 11, 15]

    def test_grade_twelve_has_two(self):
        """عتبتا المنتصف مقصورتان على «الأول إلى الحادي عشر» بنصّ الدليل."""
        assert [g.max_days for g in GATES_12] == [8, 15]

    def test_the_disability_band_has_two(self):
        """م 3.7.3.3: «تجاوز ثمانية أيام» ثمّ «16 يوماً»."""
        assert [g.max_days for g in GATES_ESE] == [8, 15]

    def test_no_gate_carries_a_2018_number(self):
        """7 و10 و13 أرقامُ سياسة 2018 — لا وجودَ لها في دليل 2026."""
        every = {g.max_days for g in GATES_1_11 + GATES_12 + GATES_ESE}

        assert not every & {7, 10, 13}, "رقمٌ من سياسة 2018 عاد"

    def test_the_gates_rise(self):
        for gates in (GATES_1_11, GATES_12, GATES_ESE):
            days = [g.max_days for g in gates]
            assert days == sorted(days)

    def test_every_gate_names_its_exam_and_semester(self):
        for gate in GATES_1_11 + GATES_12 + GATES_ESE:
            assert gate.key and gate.label
            assert gate.event_type in ("midterm_exam", "final_exam")
            assert gate.semester in ("S1", "S2")


class TestExceedingNotReaching:
    """نصُّ الدليل: «في حال **تجاوز** غيابه المدة المسموح بها»."""

    def test_matching_the_allowance_does_not_bar(self):
        assert breached("G8", 5) == ()

    def test_one_day_past_it_bars(self):
        assert [g.key for g in breached("G8", 6)] == ["s1_midterm"]

    def test_the_count_rises_with_the_days(self):
        assert len(breached("G8", 9)) == 2
        assert len(breached("G8", 12)) == 3
        assert len(breached("G8", 16)) == 4

    def test_the_upcoming_gate_is_the_first_not_passed(self):
        assert next_gate("G8", 0).max_days == 5
        assert next_gate("G8", 5).max_days == 5
        assert next_gate("G8", 6).max_days == 8

    def test_when_all_are_passed_there_is_no_next(self):
        assert next_gate("G8", 99) is None

    def test_a_twelfth_grader_is_not_barred_at_six(self):
        """عتبةُ الخمسة لا تخصّه — فمن غاب ستّاً في الثاني عشر لم يُحرم."""
        assert breached("G12", 6) == ()
        assert [g.key for g in breached("G12", 9)] == ["s1_final"]


class TestTheBands:
    @pytest.mark.parametrize("grade", ["G1", "G7", "G8", "G11", 7, "11"])
    def test_one_to_eleven(self, grade):
        assert band_for(grade) == BAND_1_11

    def test_twelve_stands_alone(self):
        assert band_for("G12") == BAND_12

    def test_the_disability_band_is_a_flag_not_a_grade(self):
        """طالبُ التربية الخاصّة في الثامن صفُّه ثامنٌ وسلّمُه سلّمُه."""
        assert band_for("G8", ese=True) == BAND_ESE
        assert band_for("G12", ese=True) == BAND_ESE
        assert gates_for("G8", ese=True) == GATES_ESE

    def test_a_grade_with_no_table_returns_unknown(self):
        assert band_for("") == BAND_UNKNOWN
        assert band_for("G13") == BAND_UNKNOWN
        assert gates_for("G13") == ()

    def test_an_unknown_band_bars_nobody(self):
        """جدولٌ لا يخصّ الصفَّ لا يُطبَّق عليه — ولا يُحرم أحدٌ بالقياس."""
        assert breached("G13", 99) == ()
        assert next_gate("G13", 99) is None


class TestTheSeventhTardyIsADay:
    """م 3.4.2.2 الدرجة السابعة: «يتم احتساب الطالب غيابًا يومًا كاملًا بدون
    عذر رسمي مع إبلاغ وليّ الأمر»."""

    def test_the_limit_is_seven(self):
        assert TARDIES_PER_ABSENCE_DAY == 7

    @pytest.mark.parametrize(
        ("tardies", "days"), [(0, 0), (1, 0), (6, 0), (7, 1), (13, 1), (14, 2), (21, 3)]
    )
    def test_every_seven_makes_one_day(self, tardies, days):
        assert absence_days_from_tardies(tardies) == days

    def test_a_negative_count_makes_nothing(self):
        assert absence_days_from_tardies(-3) == 0

    def test_the_tardy_days_feed_the_gates(self):
        """وهذا سببُ بنائهما معاً: من تأخّر أربعةَ عشرَ يُضاف يومان إلى عدّه،
        فيقفز من تحت العتبة إلى فوقها."""
        own_absences = 4
        total = own_absences + absence_days_from_tardies(14)

        assert breached("G8", own_absences) == ()
        assert [g.key for g in breached("G8", total)] == ["s1_midterm"]

    def test_the_ladder_is_seven_steps(self):
        assert [step for step, _ in TARDY_LADDER] == [1, 2, 3, 4, 5, 6, 7]

    def test_the_fourth_step_warns_and_the_seventh_counts(self):
        assert "التكرار يُحسب غيابًا" in tardy_step(4)
        assert "يوم غياب كامل" in tardy_step(7)

    def test_beyond_the_seventh_the_last_step_holds(self):
        assert tardy_step(9) == tardy_step(7)

    def test_no_step_before_the_first(self):
        assert tardy_step(0) == ""

    def test_tardiness_begins_after_the_assembly(self):
        """م 3.4.2.1: «بعد 15 دقيقة من بدء الدوام»."""
        assert TARDY_AFTER_MINUTES == 15


class TestTheExcusesAreAClosedFive:
    def test_there_are_five(self):
        assert len(ACCEPTED_EXCUSES) == 5

    @pytest.mark.parametrize(
        "word", ["المرض", "الوفاة", "الظروف العائلية", "تمثيل الدولة", "المحكمة"]
    )
    def test_each_of_the_five_is_named(self, word):
        assert any(word in excuse for excuse in ACCEPTED_EXCUSES)

    def test_the_school_activity_is_not_among_them(self):
        """نشاطٌ تنظّمه المدرسة ليس من الخمسة، والقائمةُ مغلقة.

        فالطالبُ في مسابقةٍ مدرسيّةٍ **حاضرٌ في عهدة المدرسة** لا غائبٌ بعذر —
        كفترة العيادة. ومن سجّله عذراً خالف نصّاً صريحاً.
        """
        assert not any("نشاط مدرسي" in excuse for excuse in ACCEPTED_EXCUSES)

    def test_the_medical_deadline_runs_from_the_return(self):
        """«في غضون يومين من العودة إلى المدرسة» — لا من يوم الغياب."""
        assert MEDICAL_PROOF_DAYS_AFTER_RETURN == 2

    def test_the_guardian_has_two_days_to_answer(self):
        """م 3.4.1.5: إن لم يردّ خلال يومين حُسب الغيابُ بلا عذر."""
        assert GUARDIAN_REPLY_DAYS == 2


class TestFourPeriodsMakeADay:
    def test_the_minimum_is_four(self):
        """م 3.4.3: «يجب استكمال 4 حصص على الأقل ليُحسب حضور الطالب»."""
        assert MIN_PERIODS_FOR_PRESENCE == 4


class TestTheSummonLadders:
    def test_each_band_has_one(self):
        assert set(SUMMON_DAYS) == {BAND_1_11, BAND_12, BAND_ESE}

    def test_the_disability_ladder_is_the_tightest(self):
        """م 3.7.3.3 يُشعر من اليوم الأوّل ويُعهِّد من الثاني — لا من الخامس."""
        assert SUMMON_DAYS[BAND_ESE][0] == 1
        assert SUMMON_DAYS[BAND_1_11][0] == 5

    def test_every_ladder_rises(self):
        for days in SUMMON_DAYS.values():
            assert list(days) == sorted(days)

    def test_no_summon_day_exceeds_its_last_gate(self):
        """سلّمٌ يستدعي بعد آخر عتبةٍ يستدعي لطالبٍ حُرم أصلاً."""
        for band, gates in ((BAND_1_11, GATES_1_11), (BAND_12, GATES_12), (BAND_ESE, GATES_ESE)):
            assert max(SUMMON_DAYS[band]) <= gates[-1].max_days + 1


# ── ما لم يعد يُدّعى ──────────────────────────────────────────────────


def test_no_module_claims_the_compulsory_education_law_sets_a_threshold():
    """المادة 7 لا تذكر نسبةً ولا عدد أيام — والادّعاء بها كان الخطأ الأصل."""
    import pathlib
    import re

    claim = re.compile(r"(25/2001|التعليم الإلزامي)")
    threshold = re.compile(r"(10\s*%|10٪|19 ?يوم|العتبة القانونية)")

    offenders = []
    for f in sorted(pathlib.Path(".").rglob("*.py")):
        path = "/" + f.as_posix()
        if any(x in path for x in ("/.venv/", "/node_modules/", "/.claude/", "/tests/")):
            continue
        src = f.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(src.splitlines(), 1):
            if claim.search(line) and threshold.search(line):
                offenders.append(f"{f.as_posix()}:{i}")

    assert not offenders, f"عتبةٌ منسوبةٌ إلى القانون في: {offenders}"


def test_the_policy_cites_where_its_numbers_come_from():
    """رقمٌ بلا مصدرٍ في نصّه يُغيَّر بعد أشهرٍ بلا مراجعة.

    وقد وقع ذلك فعلاً: أرقامُ 2018 بقيت سنةً بعد أن نسخها دليلُ 2026، ولم
    يُمسكها إلّا التحفّظُ المكتوبُ في صدر الملفّ.
    """
    doc = policy.__doc__ or ""

    assert "2026" in doc, "سنةُ الدليل النافذ"
    assert "3.4.1.3" in doc, "مادّةُ العتبات"
    assert "حماية ورعاية الطلبة" in doc, "الجهةُ المُصدِرة"
    assert "2018" in doc, "ما نُسخ يُذكر كي لا يُعاد"

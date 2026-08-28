"""[LEGAL] عتبات الغياب هي أرقام الوزارة — لا نسبةٌ من عندنا.

كانت المنصّة تحسب «10٪ من أيام الدراسة (≈19 يوماً من 190)» وتنسبها إلى
المادة 7 من قانون التعليم الإلزامي 25/2001. وراجعتُ نصّ القانون: مادّته
السابعة توجب إخطار المسؤول عن الطفل بكتابٍ مسجَّل، ولا تذكر نسبةً ولا عدد
أيام — لا هي ولا سائر مواده الثلاث عشرة.

والأرقام الحقيقية في «الدليل التعريفي لسياسة تقييم الطلبة» (القرار الوزاري
22/2015)، ص 27 و37:

    الصفوف ٤–١١     7 · 10 · 13 · 15
    الصف ١٢            10 · 15

تراكميّاً من بداية العام، متصلةً أو غير متصلة، وأثرها الحرمان من دخول
الاختبار — لا إشعار وليّ الأمر.

وهذه الحرّاس تُثبّت الأرقام بأعيانها. فرقمٌ يتغيّر بلا مراجعةٍ للنصّ يحرم
طالباً من حقّه أو يترك آخر يدخل وهو محروم — وكلاهما لا يُخفق في أيّ شاشة.
"""

import pytest

from operations import absence_policy as policy

# ── الأرقام نفسها ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "key,days",
    [("s1_midterm", 7), ("s1_final", 10), ("s2_midterm", 13), ("first_round", 15)],
)
def test_the_four_gates_for_grades_four_to_eleven(key, days):
    """الدليل ص 27."""
    gate = next(g for g in policy.GATES_4_11 if g.key == key)

    assert gate.max_days == days


@pytest.mark.parametrize("key,days", [("s1_final", 10), ("s2_final", 15)])
def test_the_two_gates_for_grade_twelve(key, days):
    """الدليل ص 37 — عتبتان لا أربع."""
    gate = next(g for g in policy.GATES_12 if g.key == key)

    assert gate.max_days == days


def test_grade_twelve_has_no_midterm_gate():
    """الفارق البنيويّ بين الجدولين، لا مجرّد فارقٍ في الأرقام."""
    assert not [g for g in policy.GATES_12 if "midterm" in g.event_type]
    assert [g for g in policy.GATES_4_11 if "midterm" in g.event_type]


def test_the_gates_rise_in_order():
    """عتبةٌ أدنى بعد أعلى تجعل `next_gate` تتخطّى ما لم يُتجاوز."""
    for gates in (policy.GATES_4_11, policy.GATES_12):
        days = [g.max_days for g in gates]
        assert days == sorted(days), gates


# ── إلى أيّ جدولٍ ينتمي الصفّ ──────────────────────────────────────────


@pytest.mark.parametrize("grade", ["G4", "7", "G11", 11])
def test_grades_four_to_eleven_take_the_four_gate_table(grade):
    assert policy.gates_for(grade) is policy.GATES_4_11


@pytest.mark.parametrize("grade", ["G12", 12])
def test_grade_twelve_takes_its_own_table(grade):
    assert policy.gates_for(grade) is policy.GATES_12


@pytest.mark.parametrize("grade", ["G1", "G3", 2, "", None])
def test_the_early_grades_get_no_table_rather_than_the_wrong_one(grade):
    """الصفوف ١–٣ لها قسمٌ مستقلّ في الدليل لم يُشفَّر.

    وإرجاع جدولٍ لا يخصّها أسوأ من إرجاع لا شيء: يُنتج رقماً يبدو صحيحاً.
    """
    assert policy.gates_for(grade) == ()
    assert policy.next_gate(grade, 99) is None
    assert policy.breached(grade, 99) == ()


# ── حدُّ العتبة ───────────────────────────────────────────────────────


def test_the_limit_itself_does_not_deprive():
    """النصّ يقول «إذا تجاوزت» — فالمساواة بالعدد لا تحرم."""
    assert policy.breached("G7", 7) == ()
    assert policy.breached("G7", 8)[0].key == "s1_midterm"


def test_the_next_gate_is_the_first_not_yet_passed():
    assert policy.next_gate("G7", 0).key == "s1_midterm"
    assert policy.next_gate("G7", 7).key == "s1_midterm"
    assert policy.next_gate("G7", 8).key == "s1_final"
    assert policy.next_gate("G7", 15).key == "first_round"
    assert policy.next_gate("G7", 16) is None


def test_breaching_a_later_gate_implies_the_earlier_ones():
    """من تجاوز الخامسة عشرة فقد تجاوز ما قبلها — والعرض يجب أن يقولها كلّها."""
    keys = [g.key for g in policy.breached("G7", 20)]

    assert keys == ["s1_midterm", "s1_final", "s2_midterm", "first_round"]


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
    """رقمٌ بلا مصدرٍ في نصّه يُغيَّر بعد أشهرٍ بلا مراجعة."""
    doc = policy.__doc__ or ""

    assert "22" in doc and "2015" in doc, "القرار الوزاري"
    assert "27" in doc and "37" in doc, "صفحتا الدليل"

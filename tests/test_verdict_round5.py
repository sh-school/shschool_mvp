"""[COMPLIANCE 0.1 · 2.2 · جولة إصلاح 5] الحكمُ الواحد — ما أثبتته المراجعةُ العدائيّة.

الأصل (صفحاتٌ مصوَّرة، `data/2026-2027/03- الأكاديمي/`):

  «ملغي»  قرار 30/2018 ص1 م1 (المادّة 45 مكرر، 4–11) وص2 م2 (33 مكرر، الثاني عشر):
          «يُلغى اختبار الطالب في جميع المواد، ويُعتبر راسباً في صفه، ويُرصد له كلمة
          (ملغي)». و«لا يحق له دخول اختبارات الدور الثاني» ليست في القرار — هي في الدليل
          التعريفيّ ص30 (`04b_academic_deep_part1.md:1975`) لحالاتٍ أخرى.
  البنية  قرار 14/2018 م3 ص4–5: 15/5/20 و15/5/40، والثاني عشر «(40 درجة) … لاختبار
          نهاية الفصل» و«(60 درجة) … لاختبار نهاية الفصل»؛ وم5 ص6: توزيعُ الدرجات لقطاع
          شؤون التقييم لا للمدرسة (`04b_academic_deep_part1.md:2176-2188`).
  م17 ص20 المعذورُ عن المنتصف «يختبر في نهاية الفصل بواقع 100% من الدرجة المخصصة
          للفصل»؛ وم24 ص21 جزءُ المنتصف بواقع النهاية، وجزءُ نهاية الأول يؤجَّل للملحق.
  م25 ص22 المعذورُ عن نهاية الثاني وحدَها يُختبر في منهاجها — قصواه درجةُ P4 (40).
  م50 ص33 «ويوضح في الشهادة أنه قد تم ترفيع الطالب»؛ وم30 ص23 كلمةُ «معذور»/«محروم».

كلُّ اختبارٍ هنا سقط على الإيداع d1c75c0c قبل الإصلاح.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from fractions import Fraction
from io import StringIO

import pytest

from assessments.models import (
    AnnualSubjectResult,
    Assessment,
    AssessmentPackage,
    StudentSubjectResult,
)
from assessments.services import GradeService
from core.domain.grades import (
    ExamFacts,
    MakeupFacts,
    SecondRoundFacts,
    SubjectFacts,
    judge_student,
)
from tests.test_assessment_verdict import (
    T30,
    T48_5,
    T80,
    _annual,
    _class,
    _exams,
    _fill,
    _mark,
    _student,
)

F = Fraction


def _full_s2():
    return {
        "P3": ExamFacts(F(15), F(15)),
        "P4": ExamFacts(F(40), F(40)),
        "AW": ExamFacts(F(5), F(5)),
    }


def _s1(p1=12, p2=16, aw=4):
    return {
        "P1": ExamFacts(F(p1), F(15)),
        "P2": ExamFacts(F(p2), F(20)),
        "AW": ExamFacts(F(aw), F(5)),
    }


def _others(n=5):
    return [SubjectFacts(f"o{i}", _s1(), _full_s2()) for i in range(n)]


# ═══ 1 — «ملغي»: كلمةٌ تُرصد في كلّ مادّة، ولا مجموعَ ولا «ناجح» ═══════════════════


@pytest.mark.parametrize("grade,article", [(10, "م45 مكرر"), (12, "م33 مكرر")])
def test_cancelled_records_the_word_in_every_subject_not_pass(grade, article):
    from core.domain.grades import MARK_LABELS, RESULT_STATUS_LABELS, status_bucket

    if grade == 12:
        subjects = [
            SubjectFacts(f"s{i}", {"P2": ExamFacts(F(24), F(40))}, {"P4": ExamFacts(F(36), F(60))})
            for i in range(6)
        ]
    else:
        subjects = _others(6)
    verdict = judge_student(grade, subjects, cancelled=True)
    assert (verdict.standing, verdict.article) == ("failed", article)
    for s in verdict.subjects:
        assert (s.status, s.mark, s.annual_total) == ("cancelled", "cancelled", None)
        assert (s.s1_total, s.s2_total, s.second_round_max) == (None, None, None)
    assert MARK_LABELS["cancelled"] == RESULT_STATUS_LABELS["cancelled"] == "ملغي"
    assert status_bucket("cancelled") == "failed"


def test_cancelled_citation_is_the_decision_text():
    import inspect

    from core.domain import grades

    source = inspect.getsource(grades)
    assert "م45 مكرر (قرار 30/2018): «ولا يحق له دخول اختبارات الدور الثاني»" not in source
    assert "ويُرصد له كلمة (ملغي)" in source


# ═══ 2 — البنيةُ من القرار: لا باقةَ خارجها تُجمع، ولا وزنَ مدرسةٍ يُحسب ═════════════


def test_grade12_package_outside_the_structure_is_not_summed():
    subject = SubjectFacts(
        "x",
        {"P2": ExamFacts(F(16), F(40)), "P1": ExamFacts(F(10), F(10))},
        {"P4": ExamFacts(F(30), F(60)), "AW": ExamFacts(F(5), F(5))},
    )
    (v,) = judge_student(12, [subject]).subjects
    assert (v.s1_total, v.s2_total, v.annual_total) == (Decimal("16"), Decimal("30"), Decimal("46"))
    assert "P1" in v.review and "AW" in v.review


def test_standard_package_outside_the_structure_is_not_summed():
    s1 = {**_s1(), "P4": ExamFacts(F(20), F(20))}
    v = judge_student(10, [SubjectFacts("x", s1, _full_s2())] + _others()).by_key()["x"]
    assert v.s1_total == Decimal("32")


def test_stored_weight_does_not_override_the_decision(school, teacher_user):
    """وزنٌ غيّرته مدرسةٌ (P2 = 60% بدل 50%) لا يُحسب: الدرجةُ الكاملة 20 من القرار لا 24."""
    from core.domain.grades import exact_package_weight

    assert exact_package_weight(10, "S2", "P4") == F(200, 3)
    assert exact_package_weight(12, "S1", "P1") is None
    cg, (setup,) = _class(school, teacher_user, n=1, code="H")
    exams = _exams(setup)
    student = _student(cg)
    p2 = exams[("S1", "P2")].package
    AssessmentPackage.objects.filter(pk=p2.pk).update(weight=Decimal("60"))
    p2.refresh_from_db()
    _mark(exams[("S1", "P2")], student, 20)
    assert GradeService.calc_package_score(student, p2, raw=True) == 20


def test_grade12_blocked_setup_counts_the_final_at_the_decision_weight(school, teacher_user):
    """P1 (وزن 25) عليه تقييم، وP2 بوزنٍ قديم (50): 100% في P1 و40% في P2 ← 16 من 40 لا 18."""
    cg, (setup,) = _class(school, teacher_user, grade="G12", n=1, code="Z")
    exams = _exams(setup)
    student = _student(cg)
    p2 = exams[("S1", "P2")].package
    AssessmentPackage.objects.filter(pk=p2.pk).update(weight=Decimal("50"))
    p1 = AssessmentPackage.objects.create(
        setup=setup,
        school=school,
        package_type="P1",
        semester="S1",
        weight=Decimal("25"),
        semester_max_grade=Decimal("40"),
    )
    p1_exam = Assessment.objects.create(
        package=p1, school=school, title="P1", max_grade=Decimal("10"), status="published"
    )
    _mark(p1_exam, student, 10)
    _mark(exams[("S1", "P2")], student, 16)  # 40% من 40
    _mark(exams[("S2", "P4")], student, 60)
    GradeService.recalculate_full_class(setup)
    s1 = StudentSubjectResult.objects.get(student=student, setup=setup, semester="S1")
    assert s1.total == Decimal("16")
    assert s1.p1_score is None  # باقةٌ خارج البنية: لا «0» ولا درجة
    annual = _annual(student, setup)
    assert annual.annual_total == Decimal("76")
    assert "P1" in annual.review


# ═══ 3 — درجةُ دورٍ ثانٍ فوق قصوى اختبارها: تنبيهٌ لا انهيار ═══════════════════════


def _m25_subject(second):
    return SubjectFacts(
        "m",
        _s1(15, 20, 5),
        {
            "P3": ExamFacts(F(10), F(15)),
            "P4": ExamFacts(None, F(40), excused_share=F(1)),
            "AW": ExamFacts(F(4), F(5)),
        },
        second_round=SecondRoundFacts(F(second)),
    )


def test_second_round_score_above_its_exam_max_is_flagged_not_raised():
    verdict = judge_student(10, [_m25_subject(80)] + _others())
    v = verdict.by_key()["m"]
    assert v.status == "excused" and v.second_round_max == Decimal("40")
    assert "80" in v.review and "40" in v.review
    assert verdict.standing == "second_round"


def test_second_round_within_its_max_is_credited_with_the_carried():
    v = judge_student(10, [_m25_subject(30)] + _others()).by_key()["m"]
    assert (v.status, v.annual_total) == ("pass", Decimal("84"))


def _excused_final_student(school, teacher_user, code):
    cg, (setup, other) = _class(school, teacher_user, n=2, code=code)
    student = _student(cg)
    _fill(_exams(setup), student, (15, 20, 5, 10, "excused", 4))
    _fill(_exams(other), student, T80)
    GradeService.recalculate_full_class(setup)
    return setup, student


def test_class_recalculation_survives_an_over_max_second_round_entry(school, teacher_user):
    setup, student = _excused_final_student(school, teacher_user, "Q")
    row = _annual(student, setup)
    assert row.status == "excused"
    # رصدٌ من مئة لاختبارٍ من أربعين (م25) — لا يظهر للراصد أنّ القصوى 40.
    AnnualSubjectResult.objects.filter(pk=row.pk).update(second_round_score=Decimal("80"))
    GradeService.recalculate_full_class(setup)  # كان: ValueError فتسقط الشعبةُ كلُّها
    row = _annual(student, setup)
    assert row.status == "excused" and "80" in row.review and "40" in row.review
    assert row.second_round_max == Decimal("40")


def test_admin_form_refuses_a_score_above_the_stored_max(school, teacher_user):
    from assessments.admin import AnnualSubjectResultForm

    setup, student = _excused_final_student(school, teacher_user, "W")
    row = _annual(student, setup)
    bound = AnnualSubjectResultForm(
        data={"second_round_score": "80", "second_round_absent": ""}, instance=row
    )
    assert not bound.is_valid()
    assert "second_round_score" in bound.errors
    ok = AnnualSubjectResultForm(
        data={"second_round_score": "30", "second_round_absent": ""}, instance=row
    )
    assert ok.is_valid(), ok.errors


# ═══ 4 — الأمرُ يقارن الحكمَ كلَّه: الموضعُ والتنبيه ═══════════════════════════════


def test_command_writes_a_review_that_alone_changed(school, teacher_user, principal_user):
    """راسبٌ في أربعٍ إحداها 48.5 (م12-أ): الحالةُ والمجاميعُ لا تتغيّر، والتنبيهُ وحدَه يُكتب."""
    from django.core.management import call_command

    cg, setups = _class(school, teacher_user, n=6, code="C")
    student = _student(cg)
    for i, setup in enumerate(setups):
        _fill(_exams(setup), student, T48_5 if i == 0 else (T30 if i < 4 else T80))
    GradeService.recalculate_full_class(setups[0])
    row = _annual(student, setups[0])
    assert (row.status, row.standing) == ("fail", "failed") and "القاعدة الأولى" in row.review
    AnnualSubjectResult.objects.filter(student=student).update(review="")
    out = StringIO()
    call_command("recalculate_grade_results", "--school", school.code, stdout=out)
    assert "review" in out.getvalue() and "status" not in out.getvalue()
    call_command(
        "recalculate_grade_results",
        "--apply",
        "--actor",
        principal_user.national_id,
        "--school",
        school.code,
        stdout=StringIO(),
    )
    assert "القاعدة الأولى" in _annual(student, setups[0]).review


# ═══ 5 — م17/م24 في مسار الملحق: الجزءُ المعذورُ من المنتصف لا يسقط ═════════════════


@pytest.mark.parametrize(
    "p1",
    [
        ExamFacts(F(15, 2), F(15), excused_share=F(1, 2)),  # نصفُ المنتصف (م24)
        ExamFacts(F(0), F(15), excused_share=F(1)),  # المنتصفُ كلُّه (م17)
    ],
)
def test_makeup_path_keeps_the_excused_midterm_part(p1):
    subject = SubjectFacts(
        "k",
        {
            "P1": p1,
            "P2": ExamFacts(F(10), F(20), excused_share=F(1, 2)),
            "AW": ExamFacts(F(5), F(5)),
        },
        _full_s2(),
        makeup=MakeupFacts("present", F(1)),
    )
    v = judge_student(10, [subject] + _others()).by_key()["k"]
    assert v.s1_total == Decimal("40")


# ═══ 6/7/8 — كلُّ مستهلكٍ يقرأ الحالةَ المخزَّنة: الكشفُ الرسميّ وملفُّ الطالب والشهادات ═══


def test_official_sheet_profile_and_certificates_agree_with_the_stored_verdict(
    client_as, school, principal_user, teacher_user, monkeypatch
):
    import re

    from django.http import HttpResponse

    from assessments.models import ExamDeprivation
    from tests.conftest import MembershipFactory, RoleFactory

    cg, setups = _class(school, teacher_user, n=3, code="K")
    promoted, retaker, deprived, excused = (
        _student(cg, name) for name in ("أحمد", "خالد", "سالم", "راشد")
    )
    exams = [_exams(setup) for setup in setups]
    for student, first in (
        (promoted, T48_5),
        (retaker, T30),
        (deprived, T80),
        (excused, (12, 16, 4, 12, "excused", 4)),
    ):
        for i, subject_exams in enumerate(exams):
            _fill(subject_exams, student, first if i == 0 else T80)
    ExamDeprivation.objects.create(
        school=school,
        student=deprived,
        academic_year=setups[0].academic_year,
        gate="s2_final",
        decided_on=date.today(),
    )
    GradeService.recalculate_full_class(setups[0])
    role = RoleFactory(school=school, name="student")
    for student in (promoted, retaker, deprived, excused):
        MembershipFactory(user=student, school=school, role=role)
    client = client_as(principal_user)
    # ملفُّ الطالب PDF: يُقرأ الـHTML الذي يُعطى للمحرّك.
    monkeypatch.setattr(
        "student_affairs.views.render_pdf", lambda html, *a, **k: HttpResponse(html)
    )

    words = {
        promoted.id: ("مُرفَّع", None, 3),
        retaker.id: ("راسب — دور ثانٍ", None, 2),
        deprived.id: ("محروم — دور ثانٍ", "محروم", 0),
        excused.id: ("معذور — دور ثانٍ", "معذور", 2),
    }
    for student in (promoted, retaker, deprived, excused):
        label, mark, passed = words[student.id]
        sheet = client.get(f"/reports/student/{student.id}/annual-result/?preview=1")
        assert sheet.status_code == 200
        body = sheet.content.decode()
        assert label in body, student.full_name
        assert "غير مكتمل" not in body, student.full_name
        if mark:
            assert re.search(rf">\s*{mark}\s*<", body), student.full_name  # م30

        profile = client.get(f"/student-affairs/profile/{student.id}/")
        assert profile.status_code == 200
        text = profile.content.decode()
        assert label in text, student.full_name
        assert f"ناجح {passed}" in text, student.full_name

        pdf = client.get(f"/student-affairs/profile/{student.id}/pdf/").content.decode()
        assert label in pdf, student.full_name
        if mark:
            assert re.search(rf">\s*{mark}\s*<", pdf), student.full_name

    certs = client.get(f"/reports/class/{cg.id}/certificates/?preview=1")
    assert certs.status_code == 200
    text = certs.content.decode()
    assert "مُرفَّع" in text and "محروم — دور ثانٍ" in text and "رياضيات" in text


# ═══ 9 — لا إعادةَ حسابٍ صامتة: كلُّ مسارٍ يكتب قبلَه وبعدَه ════════════════════════


def _last_verdict_log():
    from core.models import AuditLog

    return AuditLog.objects.filter(changes__op="verdict_recalculated").order_by("-timestamp")


def test_saving_one_grade_audits_every_verdict_it_rewrites(school, teacher_user):
    cg, (setup, other) = _class(school, teacher_user, n=2, code="U")
    student = _student(cg)
    exams = _exams(setup)
    _fill(exams, student, T80)
    _fill(_exams(other), student, T80)
    GradeService.recalculate_full_class(setup)
    AnnualSubjectResult.objects.filter(student=student, setup=other).update(
        annual_total=Decimal("79.40")
    )
    before = _last_verdict_log().count()
    GradeService.save_grade(exams[("S1", "P2")], student, Decimal("18"), entered_by=teacher_user)
    assert _last_verdict_log().count() == before + 1
    log = _last_verdict_log()[0]
    assert log.user == teacher_user
    rows = {(r["setup"], r["row"]): r for r in log.changes["rows"]}
    other_row = rows[(str(other.id), "annual")]
    assert (other_row["before"]["annual_total"], other_row["after"]["annual_total"]) == (
        "79.40",
        "80.00",
    )
    assert (str(setup.id), "S1") in rows


def test_recalculate_button_is_audited_with_its_actor(client_as, school, teacher_user):
    cg, (setup,) = _class(school, teacher_user, n=1, code="B")
    student = _student(cg)
    _fill(_exams(setup), student, T80)
    GradeService.recalculate_full_class(setup)
    AnnualSubjectResult.objects.filter(student=student).update(status="fail")
    client_as(teacher_user).post(f"/assessments/setup/{setup.id}/recalculate/")
    log = _last_verdict_log()[0]
    assert log.user == teacher_user
    (row,) = (r for r in log.changes["rows"] if r["row"] == "annual")
    assert (row["before"]["status"], row["after"]["status"]) == ("fail", "pass")


def test_unchanged_recalculation_writes_no_audit_row(school, teacher_user):
    cg, (setup,) = _class(school, teacher_user, n=1, code="N")
    student = _student(cg)
    _fill(_exams(setup), student, T80)
    GradeService.recalculate_full_class(setup)
    before = _last_verdict_log().count()
    GradeService.recalculate_full_class(setup)
    assert _last_verdict_log().count() == before

"""[COMPLIANCE 0.1 · 2.2 · جولة إصلاح 7] الحكمُ الواحد — ما أثبتته المراجعةُ العدائيّة.

الأصل (صفحاتٌ مصوَّرة، `data/2026-2027/03- الأكاديمي/`، بالأرقام المطبوعة):

  4–11  م8 ص9        «عند حساب درجات أية مادة … في منتصف الفصل أو نهايته أو الدور الثاني»
                     — موضعُ الجبر قراءةٌ لا نصّ
        م24 ص21، م25 ص22  الجزءُ المعذورُ من المنتصف «بواقع» النهاية، والنهايةُ دورٌ ثانٍ
        م50 ص33       «في مادتين» — القاعدةُ الثانية
        ملحق ص60–63   الإثرائيّةُ «تظهر الدرجة في شهادة نهاية العام فقط»، والفنيةُ للسابع–التاسع
                     «لاترصد و لاتظهر بالشهادة»
  12    ملحق 7 ص47–48 البدنيةُ «لا تظهر بالشهادة»، والإثرائيّةُ «ولا تظهر في شهادة الطالب»
  قرار 14/2018 م3 ص4–5  الفصلُ الأول: منتصفٌ 15، أعمالٌ 5، نهايةٌ 20؛ والثاني عشر نهايةٌ وحدَها
  08_conduct_policy_2026.md:171  «يُحال إلى فريق سلوك الطلبة إذا تجاوز المدة المسموح بها للغياب»

كلُّ اختبارٍ يستورد الجديدَ داخلَه، فيُجمع على شيفرة الجولة 6 ويسقط فيها بعينه.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest

from assessments.models import AnnualSubjectResult, Assessment
from assessments.services import GradeService
from core.domain.grades import ExamFacts, SecondRoundFacts, SubjectFacts, judge_student
from tests.test_assessment_verdict import (
    T30,
    T80,
    _annual,
    _class,
    _exams,
    _fill,
    _mark,
    _student,
)
from tests.test_verdict_round6 import _setup

F = Fraction


def _s1(p1, aw, p2):
    return {
        "P1": ExamFacts(F(p1), F(15)),
        "AW": ExamFacts(F(aw), F(5)),
        "P2": ExamFacts(F(p2), F(20)),
    }


def _s2(p3, aw, p4):
    return {
        "P3": ExamFacts(F(p3), F(15)),
        "AW": ExamFacts(F(aw), F(5)),
        "P4": ExamFacts(F(p4), F(40)),
    }


def _others(n=4):
    return [SubjectFacts(f"o{i}", _s1(12, 4, 16), _s2(12, 4, 32)) for i in range(n)]


# ═══ 1 — موضعُ الجبر قراءةٌ: حيث يتغيّر بها الموقفُ يُعرض ولا يُطوى ═══════════════════


def test_jabr_reading_that_changes_the_standing_is_flagged():
    """(أ) 7.1+2.1+9.1 ← 19 بجبر المنتصف، و18.5 بجبر المجموع وحدَه؛ (ب) 47.

    المعتمدة: مادّةٌ راسبةٌ نقصُها 3 — دورٌ ثانٍ. وبجبر المجموع وحدَه: مادّتان نقصُهما 0.5 و3
    — القاعدةُ الثانية (م50) ترفّعه. فالقراءةُ ليست في صالح الطالب دائماً.
    """
    from core.domain.grades import JABR_READING, JABR_READINGS

    a = SubjectFacts("a", _s1(F("7.1"), F("2.1"), F("9.1")), _s2(7, 2, 22))
    b = SubjectFacts("b", _s1(7, 2, 8), _s2(7, 2, 21))
    verdict = judge_student(10, [a, b] + _others())
    assert JABR_READING in JABR_READINGS and len(JABR_READINGS) == 3
    by = verdict.by_key()
    assert (verdict.standing, by["a"].annual_total, by["b"].status) == (
        "second_round",
        Decimal("50"),
        "second_round",
    )
    assert "م8 موضعُ الجبر قراءة" in by["a"].review and "ناجح بالترفيع" in by["a"].review
    assert "م8" in by["b"].review
    assert all("م8" not in by[f"o{i}"].review for i in range(4))


def test_jabr_reading_without_effect_on_the_standing_is_silent():
    a = SubjectFacts("a", _s1(F("7.1"), F("2.1"), F("9.1")), _s2(12, 4, 32))
    verdict = judge_student(10, [a] + _others())
    assert verdict.standing == "passed"
    assert all(v.review == "" for v in verdict.subjects)


# ═══ 2 — ما لا يظهر في الشهادة لا يظهر ولو رُصدت له درجة ══════════════════════════


@pytest.mark.parametrize(
    "grade,name,shown",
    [
        ("G8", "التربية الفنية", False),
        ("G12", "التربية البدنية", False),
        ("G12", "مهارات ما قبل الجامعة", False),
        ("G10", "برنامج القراءة للغة العربية", True),
    ],
)
def test_certificate_follows_the_appendix_column(school, teacher_user, grade, name, shown):
    from reports.services import ReportDataService
    from reports.views import _certificate_rows
    from tests.test_assessment_verdict import MARKS, MARKS_12

    cg, (base,) = _class(school, teacher_user, grade=grade, n=1, code=f"C{grade}")
    exempt = _setup(school, teacher_user, cg, name, f"X{grade}")
    student = _student(cg)
    for setup in (base, exempt):
        exams = _exams(setup)
        table = MARKS_12 if grade == "G12" else MARKS
        for key, exam in exams.items():
            _mark(exam, student, table[key] * 8 // 10)
    GradeService.recalculate_full_class(base)
    row = _annual(student, exempt)
    assert (row.status, row.annual_total is not None) == ("no_pass_mark", True)
    assert row.on_certificate is shown

    ctx = ReportDataService.get_student_report(student, school)
    _certificate_rows(ctx)
    assert (name in {r["subject"] for r in ctx["rows"]}) is shown


# ═══ 3 — الكشفُ الرسميّ: كلُّ باقةٍ تحت عمودها ═══════════════════════════════════════


def _sheet_cells(client, student):
    body = client.get(f"/reports/student/{student.id}/annual-result/?preview=1").content.decode()
    return [c.strip() for c in re.findall(r'<td class="pkg-scores">([^<]*)</td>', body)]


def test_official_sheet_puts_each_package_under_its_column(client_as, school, principal_user):
    from tests.conftest import MembershipFactory, RoleFactory

    cg, (setup,) = _class(school, principal_user, n=1, code="Q")
    g12, (setup12,) = _class(school, principal_user, grade="G12", n=1, code="Q12")
    student, senior = _student(cg), _student(g12)
    role = RoleFactory(school=school, name="student")
    for s in (student, senior):
        MembershipFactory(user=s, school=school, role=role)
    _fill(_exams(setup), student, (12, 18, 4, 9, 30, 3))
    exams12 = _exams(setup12)
    _mark(exams12[("S1", "P2")], senior, 32)
    _mark(exams12[("S2", "P4")], senior, 48)
    GradeService.recalculate_full_class(setup)
    GradeService.recalculate_full_class(setup12)

    client = client_as(principal_user)
    # منتصف·أعمال·نهاية لكلّ فصل.
    assert _sheet_cells(client, student) == ["12,00", "4,00", "18,00", "9,00", "3,00", "30,00"]
    assert _sheet_cells(client, senior) == ["×", "×", "32,00", "×", "×", "48,00"]

    text = client.get(f"/reports/student/{student.id}/result/?preview=1").content.decode()
    assert "نهاية:30,00" in text and "منتصف:12,00" in text


# ═══ 4 — باقةٌ إلزاميّةٌ لم تُرصد: «غير مكتمل» لا «دور ثانٍ» ═════════════════════════


def test_unrecorded_midterms_leave_the_subject_incomplete():
    x = SubjectFacts(
        "x",
        {"P2": ExamFacts(F(10), F(20)), "AW": ExamFacts(F(3), F(5))},
        {"P4": ExamFacts(F(20), F(40)), "AW": ExamFacts(F(3), F(5))},
    )
    verdict = judge_student(10, [x] + _others())
    v = verdict.by_key()["x"]
    assert (verdict.standing, v.status, v.annual_total) == ("incomplete", "incomplete", None)


def test_draft_midterm_leaves_the_stored_verdict_incomplete(school, teacher_user):
    cg, (setup, other) = _class(school, teacher_user, n=2, code="D")
    student = _student(cg)
    exams = _exams(setup)
    _fill(exams, student, (None, 10, 3, None, 20, 3))
    _fill(_exams(other), student, T80)
    Assessment.objects.filter(pk=exams[("S2", "P3")].pk).update(status="draft")
    GradeService.recalculate_full_class(setup)
    row = _annual(student, setup)
    assert (row.status, row.standing, row.annual_total) == ("incomplete", "incomplete", None)
    assert not GradeService.get_failing_students(school).filter(student=student).exists()


def test_unrecorded_final_is_not_a_semester_of_midterm_and_work():
    x = SubjectFacts(
        "x", _s1(12, 4, 16), {"P3": ExamFacts(F(12), F(15)), "AW": ExamFacts(F(4), F(5))}
    )
    v = judge_student(10, [x] + _others()).by_key()["x"]
    assert (v.status, v.s2_total) == ("incomplete", None)


# ═══ 5 — م25 مع عذرٍ عن جزءٍ من P3: الجزءُ المعذورُ بواقع اختبار الدور الثاني ══════════


def _m25_partial(second=None):
    return SubjectFacts(
        "m",
        _s1(15, 5, 20),
        {
            "P3": ExamFacts(F(15, 2), F(15), excused_share=F(1, 2)),
            "P4": ExamFacts(None, F(40), excused_share=F(1)),
            "AW": ExamFacts(F(5), F(5)),
        },
        second_round=None if second is None else SecondRoundFacts(F(second)),
    )


def test_m25_with_a_partly_excused_midterm_can_reach_one_hundred():
    first = judge_student(10, [_m25_partial()] + _others()).by_key()["m"]
    assert (first.status, first.second_round_max) == ("excused", Decimal("47.5"))
    full = judge_student(10, [_m25_partial("47.5")] + _others()).by_key()["m"]
    assert (full.status, full.annual_total) == ("pass", Decimal("100"))
    half = judge_student(10, [_m25_partial("23.75")] + _others()).by_key()["m"]
    assert half.annual_total == Decimal("76.5")  # 40 + 7.5 + 5 + 23.75 = 76.25 ← 76.5 (م8)


# ═══ 6 — نتائجُ القواعد الأقدم لا تُرجئ الرصد: «حفظ الكلّ» يظهر أثرُه ═══════════════


def test_save_all_after_deploy_updates_the_class_it_touches(client_as, school, teacher_user):
    cg, (setup, other) = _class(school, teacher_user, n=2, code="W")
    a, b = _student(cg, "أ"), _student(cg, "ب")
    exams = _exams(setup)
    for student in (a, b):
        _fill(exams, student, T80)
        _fill(_exams(other), student, T80)
    GradeService.recalculate_full_class(setup)
    AnnualSubjectResult.objects.update(ruleset=0)  # كلُّ الصفوف بعد الهجرة 0015

    p4 = exams[("S2", "P4")]
    resp = client_as(teacher_user).post(
        f"/assessments/assessment/{p4.id}/save-all/",
        {f"grade_{a.id}": "40", f"grade_{b.id}": "32"},
    )
    assert resp.status_code == 302
    assert _annual(a, setup).annual_total == Decimal("88")
    assert set(AnnualSubjectResult.objects.values_list("ruleset", flat=True)) == {1}


# ═══ 7 — تنبيهُ العتبة يظهر لمن يدخل الدور الثاني ═══════════════════════════════════


def test_second_round_screen_shows_the_threshold_warning_for_sitting_students(
    client_as, school, principal_user, teacher_user, monkeypatch
):
    cg, setups = _class(school, teacher_user, n=2, code="T")
    student = _student(cg, "طالبُ العتبة")
    for i, setup in enumerate(setups):
        exams = _exams(setup)
        _fill(exams, student, T30 if i == 0 else T80)
        for key, day in ((("S1", "P2"), date(2027, 1, 5)), (("S2", "P4"), date(2027, 5, 20))):
            exams[key].date = day
            exams[key].save(update_fields=["date"])
    GradeService.recalculate_full_class(setups[0])
    monkeypatch.setattr(
        "operations.absence_standing.unexcused_days_for_class",
        lambda class_group, school_, on=None: {student.id: 16},
    )
    body = (
        client_as(principal_user)
        .get(f"/assessments/second-round/?class_group={cg.id}")
        .content.decode()
    )
    assert "طالبُ العتبة" in body and "م12-أ" in body
    sitting = body.split("بقيّةُ الشعبة")[0]
    assert "لم يُسجَّل قرارُ فريق السلوك" in sitting


# ═══ 8 — رصدُ الدور الثاني من لوحة الإدارة مسجَّلٌ بقيمتيه ════════════════════════════


def _admin_save(obj, user):
    from django.contrib import admin
    from django.test import RequestFactory

    from assessments.admin import AnnualSubjectResultAdmin

    request = RequestFactory().post("/")
    request.user = user
    AnnualSubjectResultAdmin(AnnualSubjectResult, admin.site).save_model(request, obj, None, True)


def test_admin_second_round_entry_is_audited_even_when_the_verdict_stays(
    school, teacher_user, principal_user
):
    from core.models import AuditLog

    cg, (setup, other) = _class(school, teacher_user, n=2, code="A")
    student = _student(cg)
    _fill(_exams(setup), student, T30)
    _fill(_exams(other), student, T80)
    GradeService.recalculate_full_class(setup)
    row = _annual(student, setup)
    assert row.status == "second_round"

    for score in ("60", "70"):
        row.second_round_score = Decimal(score)
        _admin_save(row, principal_user)
    logs = AuditLog.objects.filter(changes__op="second_round_entry").order_by("timestamp")
    assert [
        (g.changes["before"]["second_round_score"], g.changes["after"]["second_round_score"])
        for g in logs
    ] == [
        ("", "60.00"),
        ("60.00", "70.00"),
    ]
    assert all(g.user == principal_user for g in logs)
    assert _annual(student, setup).annual_total == Decimal("50")  # م16: النهايةُ الصغرى

    # نتائجُ بقواعد أقدم: يُكتب السجلّ ويُعاد الحكم على الشعبة.
    AnnualSubjectResult.objects.update(ruleset=0)
    row = _annual(student, setup)
    row.second_round_score = None
    row.second_round_absent = True
    _admin_save(row, principal_user)
    assert AuditLog.objects.filter(changes__op="second_round_entry").count() == 3
    stored = _annual(student, setup)
    assert (stored.status, stored.mark, stored.ruleset) == ("fail", "absent", 1)


# ═══ 9 — مركزُ معلومات الطلبة يعدّ بما تعدّ به البوّابة ═══════════════════════════════


def test_student_info_average_and_bands_skip_subjects_without_a_pass_mark(school, teacher_user):
    from parents.services import ParentService
    from student_info import services

    cg, (base,) = _class(school, teacher_user, grade="G8", n=1, code="I")
    enrich = _setup(school, teacher_user, cg, "برنامج القراءة للغة العربية", "IR")
    student = _student(cg)
    _fill(_exams(base), student, T80)
    _fill(_exams(enrich), student, T30)
    GradeService.recalculate_full_class(base)
    year = base.academic_year
    assert _annual(student, enrich).status == "no_pass_mark"

    assert services.student_average(student, year)["value"] == 80.0
    overview = services.achievement_overview(school, year)
    assert (overview["total"], overview["overall"]["below"]) == (1, 0)
    rows = {r["subject"]: r for r in services.student_results(student, year)}
    assert rows["برنامج القراءة للغة العربية"]["band"] is None

    portal = ParentService.get_student_grades(student, school, year)
    assert portal["avg"] == services.student_average(student, year)["value"]

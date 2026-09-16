"""[COMPLIANCE 0.1 · 2.2 · جولة إصلاح 6] الحكمُ الواحد — ما أثبتته المراجعةُ العدائيّة.

الأصل (صفحاتٌ مصوَّرة، `data/2026-2027/03- الأكاديمي/`، بالأرقام المطبوعة):

  4–11  م11 ص16، م50 ص33   الشروطُ «في المواد التي لها نهاية صغرى»
        ملحق ص60–61        «التربية الفنية» للسابع–التاسع «ليست مادة نجاح و رسوب»
        م42–م45 ص30–31      «غش» في المنتصف/النهاية/الملحق، و«ملغي» «ولا يحق له دخول
                            اختبارات الدور الثاني»
        م24 ص21، م8 ص9      جزءُ المنتصف المعذورُ بنسبة النهاية، والجبرُ على الدرجة
        م27 ص22             «"غائب" أي لا يحتسب له درجات الفصل الأول»
  12    ملحق 7 ص47–48       «التربية البدنية» «لا تظهر بالشهادة وليس لها اختبار»
        م17، م19 ص11        «ولا تحسب له درجات الفصل الأول»، «(تلغى درجات الطالب في الفصل الأول)»
        م30–م33 ص17–18      «غش» في نهاية الفصلين والدور الثاني، و«ملغي»

كلُّ اختبارٍ يستورد الجديدَ داخلَه، فيُجمع على شيفرة الجولة 5 ويسقط فيها بعينه.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from fractions import Fraction
from io import StringIO

import pytest

from assessments.models import AnnualSubjectResult, SubjectClassSetup
from assessments.services import GradeService
from core.domain.grades import ExamFacts, SecondRoundFacts, SubjectFacts, judge_student
from operations.models import Subject
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

F = Fraction


def _s1(p1=12, p2=16, aw=4):
    return {
        "P1": ExamFacts(F(p1), F(15)),
        "P2": ExamFacts(F(p2), F(20)),
        "AW": ExamFacts(F(aw), F(5)),
    }


def _s2(p3=12, p4=32, aw=4):
    return {
        "P3": ExamFacts(F(p3), F(15)),
        "P4": ExamFacts(F(p4), F(40)),
        "AW": ExamFacts(F(aw), F(5)),
    }


def _others(n=5):
    return [SubjectFacts(f"o{i}", _s1(), _s2()) for i in range(n)]


def _g12(key, p2=32, p4=48, **kw):
    return SubjectFacts(key, {"P2": ExamFacts(F(p2), F(40))}, {"P4": ExamFacts(F(p4), F(60))}, **kw)


def _setup(school, teacher, cg, name, code):
    return SubjectClassSetup.objects.create(
        school=school,
        subject=Subject.objects.create(school=school, name_ar=name, code=code),
        class_group=cg,
        teacher=teacher,
        academic_year=cg.academic_year,
    )


# ═══ 1 — المادّةُ التي لا نجاحَ فيها ولا رسوب لا تُعلِّق الطالبَ ولا تُرسبه ═══════════


def test_pass_mark_table_is_the_policy_appendix():
    from core.domain.grades import default_has_pass_mark

    assert not default_has_pass_mark(12, "التربية البدنية")
    assert default_has_pass_mark(11, "التربية البدنية")
    assert not default_has_pass_mark(8, "الفنون البصرية")
    assert not default_has_pass_mark(7, "التربية الفنية")
    assert default_has_pass_mark(12, "الفنون البصرية")  # مادّةٌ اختياريّة لها نهايةٌ صغرى
    assert not default_has_pass_mark(10, "برنامج القراءة للغة العربية")
    assert not default_has_pass_mark(11, "مهارات ما قبل الجامعة")
    assert default_has_pass_mark(9, "الرياضيات")


def test_grade12_physical_education_without_exam_does_not_hold_the_student():
    pe = SubjectFacts("pe", has_pass_mark=False)
    verdict = judge_student(12, [_g12(f"s{i}") for i in range(5)] + [pe])
    assert verdict.standing == "passed"
    v = verdict.by_key()["pe"]
    assert (v.status, v.annual_total) == ("no_pass_mark", None)


def test_art_below_fifty_is_not_a_failed_subject():
    art = SubjectFacts("art", _s1(3, 4, 1), _s2(3, 8, 1), has_pass_mark=False)
    verdict = judge_student(8, _others(3) + [art])
    assert verdict.standing == "passed"
    v = verdict.by_key()["art"]
    assert (v.status, v.annual_total) == ("no_pass_mark", Decimal("20"))


def test_exempt_subject_is_stored_counted_by_no_consumer_and_off_the_certificate(
    school, teacher_user
):
    from core.domain.grades import status_bucket
    from core.views_dashboard import _get_director_ctx
    from parents.services import ParentService
    from reports.services import ReportDataService
    from reports.views import _certificate_rows

    cg, setups = _class(school, teacher_user, grade="G12", n=2, code="P")
    pe = _setup(school, teacher_user, cg, "التربية البدنية", "PE6")
    GradeService.ensure_packages(pe, "S1")
    GradeService.ensure_packages(pe, "S2")
    student = _student(cg)
    for setup in setups:
        exams = _exams(setup)
        _mark(exams[("S1", "P2")], student, 30)
        _mark(exams[("S2", "P4")], student, 45)
    GradeService.recalculate_full_class(setups[0])

    row = _annual(student, pe)
    assert (row.status, row.standing) == ("no_pass_mark", "passed")
    assert status_bucket(row.status) == "exempt" and not row.on_certificate
    ctx = ReportDataService.get_student_report(student, school)
    assert (ctx["total"], ctx["passed"], ctx["failed"]) == (2, 2, 0)
    _certificate_rows(ctx)
    assert {r["annual"].setup_id for r in ctx["rows"]} == {s.id for s in setups}
    assert ParentService.get_student_grades(student, school)["total"] == 2
    director = _get_director_ctx(school, date.today())
    assert director["failing_count"] == 0


def test_setup_can_declare_a_subject_the_appendix_does_not_name(school, teacher_user):
    cg, (setup, other) = _class(school, teacher_user, n=2, code="Q")
    setup.has_pass_mark = False
    setup.save(update_fields=["has_pass_mark"])
    student = _student(cg)
    _fill(_exams(setup), student, T30)
    _fill(_exams(other), student, T80)
    GradeService.recalculate_full_class(setup)
    assert (_annual(student, setup).status, _annual(student, other).standing) == (
        "no_pass_mark",
        "passed",
    )


# ═══ 2 — «ملغي» واقعةٌ مسجَّلة تصل الحكم، بلا دورٍ ثانٍ ═══════════════════════════


def test_cancelled_is_recorded_and_reaches_the_stored_verdict(school, teacher_user, principal_user):
    from assessments.models import ExamMisconduct
    from assessments.services import ExamDecisionService, SecondRoundService

    cg, setups = _class(school, teacher_user, n=2, code="C")
    student = _student(cg)
    for setup in setups:
        _fill(_exams(setup), student, T30)  # كان دوراً ثانياً
    GradeService.recalculate_full_class(setups[0])
    assert _annual(student, setups[0]).standing == "second_round"

    ExamDecisionService.save(
        ExamMisconduct(
            school=school,
            student=student,
            academic_year=cg.academic_year,
            kind="cancelled",
            basis="policy",
            decided_on=date.today(),
        ),
        principal_user,
    )
    for setup in setups:
        row = _annual(student, setup)
        assert (row.status, row.mark, row.standing, row.article) == (
            "cancelled",
            "cancelled",
            "failed",
            "م45",
        )
        assert row.annual_total is None and row.second_round_max is None
    rows, _ = SecondRoundService.roster(cg)
    assert not rows[0].sits_second_round and rows[0].retake == []


def test_cancelled_second_round_bar_is_cited_to_the_policies_themselves():
    import inspect

    from core.domain import grades

    source = inspect.getsource(grades)
    assert "4–11 م45 ص31، و12 م32 ص17" in source
    assert "ولا يحق له دخول اختبارات الدور الثاني»؛" in source
    assert "نصُّ الدليل التعريفيّ ص30 لحالاتٍ أخرى" not in source
    assert judge_student(12, [_g12("a")], cancelled="decree30_1").article == "م33 مكرر 1"


# ═══ 3 — «غش» وآثارُه بنصّ السياستين ═════════════════════════════════════════════


def test_cheating_in_second_semester_final_voids_the_first_semester_4_11():
    x = SubjectFacts("x", _s1(), _s2(), cheated=frozenset({"s2_final"}))
    v = judge_student(9, [x] + _others()).by_key()["x"]
    assert (v.status, v.mark, v.article) == ("second_round", "cheating", "م44")
    assert (v.s1_total, v.s2_total, v.annual_total) == (None, None, None)


def test_cheating_in_a_midterm_zeroes_it_and_keeps_final_and_works():
    x = SubjectFacts("x", _s1(12, 16, 4), _s2(), cheated=frozenset({"s1_midterm"}))
    v = judge_student(9, [x] + _others()).by_key()["x"]
    assert v.s1_total == Decimal("20")  # 0 + 16 + 4
    assert v.article == "م42"


def test_cheating_in_first_final_cancels_the_final_only_for_those_with_mid_and_works():
    with_marks = SubjectFacts("x", _s1(12, 16, 4), _s2(), cheated=frozenset({"s1_final"}))
    v = judge_student(9, [with_marks] + _others()).by_key()["x"]
    assert (v.s1_total, v.article) == (Decimal("16"), "م43")

    no_mid = SubjectFacts(
        "x",
        {**_s1(), "P1": ExamFacts(F(0), F(15), excused_share=F(1))},
        _s2(),
        cheated=frozenset({"s1_final"}),
    )
    v = judge_student(9, [no_mid] + _others()).by_key()["x"]
    assert (v.status, v.mark, v.article, v.s2_total) == ("second_round", "cheating", "م43", None)


def test_grade12_cheating_in_finals_and_second_round():
    v = judge_student(12, [_g12("x", cheated=frozenset({"s1_final"}))] + [_g12("o")]).by_key()["x"]
    assert (v.status, v.mark, v.article, v.s2_total) == ("second_round", "cheating", "م30", None)

    v = judge_student(12, [_g12("x", cheated=frozenset({"s2_final"}))] + [_g12("o")]).by_key()["x"]
    assert (v.mark, v.article, v.s1_total) == ("cheating", "م31", None)

    low = [_g12("a", 10, 20), _g12("b", 10, 20)]
    first = judge_student(12, low)
    assert first.standing == "second_round"
    sat = [
        _g12(
            "a", 10, 20, second_round=SecondRoundFacts(F(90)), cheated=frozenset({"second_round"})
        ),
        _g12("b", 10, 20),
    ]
    verdict = judge_student(12, sat)
    assert (verdict.standing, verdict.article) == ("failed", "م33")
    a, b = verdict.by_key()["a"], verdict.by_key()["b"]
    assert (a.status, a.mark) == ("fail", "cheating")
    assert (b.status, b.article) == ("fail", "م33")


def test_cheating_is_recorded_per_subject_and_exam(school, teacher_user, principal_user):
    from assessments.models import ExamMisconduct
    from assessments.services import ExamDecisionService

    cg, (setup, other) = _class(school, teacher_user, n=2, code="G")
    student = _student(cg)
    _fill(_exams(setup), student, T80)
    _fill(_exams(other), student, T80)
    ExamDecisionService.save(
        ExamMisconduct(
            school=school,
            student=student,
            academic_year=cg.academic_year,
            kind="cheating",
            setup=setup,
            exam="s2_final",
            report_ref="محضر 7",
            decided_on=date.today(),
        ),
        principal_user,
    )
    row = _annual(student, setup)
    assert (row.status, row.mark, row.s1_total, row.total_display) == (
        "second_round",
        "cheating",
        None,
        "غش",
    )
    assert _annual(student, other).status == "pass"


# ═══ 4 — الجبرُ بعد ضمّ الجزء المستعار: لا فصلَ فوق قصواه ═══════════════════════


def test_midterm_is_rounded_after_the_borrowed_part_not_before():
    # P1: تقييمٌ وزنُه 35 بالدرجة الكاملة، وآخرُ وزنُه 65 معذورٌ عنه — والنهايةُ كاملة.
    p1 = ExamFacts(F(35, 100) * 15, F(15), excused_share=F(65, 100))
    p3 = ExamFacts(F(35, 100) * 15, F(15), excused_share=F(65, 100))
    x = SubjectFacts(
        "x",
        {"P1": p1, "P2": ExamFacts(F(20), F(20)), "AW": ExamFacts(F(5), F(5))},
        {"P3": p3, "P4": ExamFacts(F(40), F(40)), "AW": ExamFacts(F(5), F(5))},
    )
    v = judge_student(10, [x] + _others()).by_key()["x"]
    assert (v.s1_total, v.s2_total, v.annual_total) == (
        Decimal("40"),
        Decimal("60"),
        Decimal("100"),
    )


def test_partial_midterm_gets_one_rounding_not_two():
    # الحاضرُ 5.2 (يُجبر وحدَه 5.5) والمستعارُ 0.8 × 7.625 = 6.1 — المنتصفُ يُجبر مرّةً.
    p1 = ExamFacts(F(52, 10), F(15), excused_share=F(61, 120))
    x = SubjectFacts(
        "x",
        {"P1": p1, "P2": ExamFacts(F(16), F(20)), "AW": ExamFacts(F(4), F(5))},
        _s2(),
    )
    v = judge_student(10, [x] + _others()).by_key()["x"]
    # المنتصف = 5.2 + 6.1 = 11.3 → 11.5؛ الفصل = 11.5 + 16 + 4 = 31.5 (لا 5.5 + 6.1 + 20 → 32)
    assert v.s1_total == Decimal("31.5")


# ═══ 5 — «لا تحسب له درجات الفصل الأول» لا تُخزَّن ولا تُطبع ════════════════════


def test_voided_first_semester_is_not_stored():
    deprived = judge_student(12, [_g12("a"), _g12("b")], frozenset({"s2_final"}))
    assert {v.s1_total for v in deprived.subjects} == {None}

    absent = SubjectFacts("x", _s1(), {**_s2(), "P4": ExamFacts(F(0), F(40), absent_share=F(1))})
    v = judge_student(9, [absent] + _others()).by_key()["x"]
    assert (v.article, v.s1_total) == ("م27", None)

    g12_absent = _g12("x")
    g12_absent = SubjectFacts("x", g12_absent.s1, {"P4": ExamFacts(F(0), F(60), absent_share=F(1))})
    v = judge_student(12, [g12_absent, _g12("o")]).by_key()["x"]
    assert (v.article, v.s1_total) == ("م17", None)

    g12_excused = SubjectFacts(
        "x", _g12("x").s1, {"P4": ExamFacts(F(0), F(60), excused_share=F(1))}
    )
    v = judge_student(12, [g12_excused, _g12("o")]).by_key()["x"]
    assert (v.article, v.s1_total) == ("م16", None)

    # 4–11 م29-4: النصُّ لا يُلغي الفصلَ الأول — يبقى.
    kept = judge_student(9, _others(2), frozenset({"s2_final"}))
    assert {v.s1_total for v in kept.subjects} == {Decimal("32")}


# ═══ 6 — لا إعادةَ حسابٍ جزئيّة لنتائج كُتبت بقواعد أقدم ═════════════════════════


def test_results_written_by_older_rules_wait_for_the_command(school, teacher_user, principal_user):
    from django.core.management import call_command

    from core.models import AuditLog

    cg, (setup, other) = _class(school, teacher_user, n=2, code="R")
    a, b = _student(cg, "أ"), _student(cg, "ب")
    exams, other_exams = _exams(setup), _exams(other)
    for student in (a, b):
        _fill(exams, student, T80)
        _fill(other_exams, student, T80)
    GradeService.recalculate_full_class(setup)
    # ما كتبته الشيفرةُ قبل النشر: مجموعٌ خامٌ بلا جبر، وإصدارُ القواعد 0.
    AnnualSubjectResult.objects.filter(setup=other).update(annual_total=Decimal("79.40"), ruleset=0)

    GradeService.save_grade(exams[("S1", "AW")], a, Decimal("5"), entered_by=teacher_user)
    assert _annual(a, other).annual_total == Decimal("79.40")  # لم يُعَد حسابُه وحدَه
    assert _annual(a, setup).annual_total == _annual(b, setup).annual_total == Decimal("80")
    assert GradeService.recalculate_full_class(setup, actor=teacher_user) == 0
    assert _annual(b, other).annual_total == Decimal("79.40")

    call_command(
        "recalculate_grade_results",
        "--apply",
        "--actor",
        principal_user.national_id,
        "--school",
        school.code,
        stdout=StringIO(),
    )
    assert _annual(a, setup).annual_total == Decimal("81")
    assert _annual(a, other).annual_total == _annual(b, other).annual_total == Decimal("80")
    assert set(AnnualSubjectResult.objects.values_list("ruleset", flat=True)) == {1}
    assert GradeService.recalculate_full_class(setup, actor=teacher_user) == 2
    log = AuditLog.objects.filter(changes__op="verdict_recalculated").first()
    assert log is None or log.changes["trigger"]


def test_a_departed_students_old_row_does_not_hold_the_class(school, teacher_user):
    from core.models import StudentEnrollment

    cg, (setup,) = _class(school, teacher_user, n=1, code="L")
    stay, gone = _student(cg, "باقٍ"), _student(cg, "غادر")
    exams = _exams(setup)
    for student in (stay, gone):
        _fill(exams, student, T80)
    GradeService.recalculate_full_class(setup)
    StudentEnrollment.objects.filter(student=gone).update(is_active=False)
    AnnualSubjectResult.objects.filter(student=gone).update(ruleset=0)
    assert not GradeService.is_deferred(cg, cg.academic_year)
    assert GradeService.recalculate_full_class(setup) == 1


def test_command_stamps_unchanged_old_rows(school, teacher_user, principal_user):
    from django.core.management import call_command

    cg, (setup,) = _class(school, teacher_user, n=1, code="S")
    student = _student(cg)
    _fill(_exams(setup), student, T80)
    GradeService.recalculate_full_class(setup)
    AnnualSubjectResult.objects.update(ruleset=0)
    out = StringIO()
    call_command(
        "recalculate_grade_results",
        "--apply",
        "--actor",
        principal_user.national_id,
        "--school",
        school.code,
        stdout=out,
    )
    assert _annual(student, setup).ruleset == 1
    assert "1 صفّاً بقواعد أقدم" in out.getvalue()


# ═══ 7 — البنيةُ المخالفة لا تُحسم بالناقص ضدّ الطالب ════════════════════════════


def test_structure_outside_the_decision_is_incomplete_not_failed():
    s1 = {"P1": ExamFacts(F(9), F(15)), "P4": ExamFacts(F(0), F(0))}  # بذرٌ قديم: P4 في الأول
    x = SubjectFacts("x", s1, _s2(9, 24, 3))
    verdict = judge_student(10, [x] + _others())
    v = verdict.by_key()["x"]
    assert (verdict.standing, v.status, v.annual_total) == ("incomplete", "incomplete", None)
    assert "S1/P4" in v.review


def test_missing_structural_package_holds_the_subject(school, teacher_user):
    from assessments.models import Assessment, AssessmentPackage

    cg, (setup, other) = _class(school, teacher_user, n=2, code="T")
    student = _student(cg)
    exams = _exams(setup)
    _fill(exams, student, T80)
    _fill(_exams(other), student, T80)
    # البذرُ القديم: لا P2 في الفصل الأول.
    Assessment.objects.filter(package__setup=setup, package__package_type="P2").delete()
    AssessmentPackage.objects.filter(setup=setup, package_type="P2").delete()
    GradeService.recalculate_full_class(setup)
    row = _annual(student, setup)
    assert (row.status, row.standing) == ("incomplete", "incomplete")
    assert "S1/P2" in row.review


# ═══ 8–9 — قرارُ فريق السلوك: إعادةُ حكمٍ فوريّة، وسجلُّ مراجعةٍ بقيمتيه ═══════════


def _admin_request(user):
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.test import RequestFactory

    request = RequestFactory().post("/")
    request.user = user
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


def test_admin_decision_rejudges_now_and_on_delete(school, teacher_user, principal_user):
    from django.contrib import admin

    from assessments.models import ExamDeprivation

    cg, setups = _class(school, teacher_user, n=2, code="D")
    student = _student(cg)
    for setup in setups:
        _fill(_exams(setup), student, T80)
    GradeService.recalculate_full_class(setups[0])
    assert _annual(student, setups[0]).status == "pass"

    model_admin = admin.site._registry[ExamDeprivation]
    obj = ExamDeprivation(
        school=school,
        student=student,
        academic_year=cg.academic_year,
        gate="s2_final",
        decided_on=date.today(),
        decided_by=teacher_user,  # يدٌ حرّة — تُستبدل بالفاعل
    )
    model_admin.save_model(_admin_request(principal_user), obj, None, False)
    row = _annual(student, setups[0])
    assert (row.status, row.mark, row.standing) == ("deprived", "deprived", "second_round")
    obj.refresh_from_db()
    assert obj.decided_by == principal_user
    assert "decided_by" in model_admin.get_readonly_fields(_admin_request(principal_user), obj)

    obj.deprived = False
    model_admin.save_model(_admin_request(principal_user), obj, None, True)
    assert _annual(student, setups[0]).status == "pass"

    obj.deprived = True
    model_admin.save_model(_admin_request(principal_user), obj, None, True)
    model_admin.delete_model(_admin_request(principal_user), obj)
    assert _annual(student, setups[0]).status == "pass"


def test_decision_writes_are_audited_with_before_after_and_actor(
    school, teacher_user, principal_user
):
    from assessments.models import ExamDeprivation
    from assessments.services import ExamDecisionService
    from core.models import AuditLog

    cg, (setup,) = _class(school, teacher_user, n=1, code="U")
    student = _student(cg)
    obj = ExamDeprivation(
        school=school,
        student=student,
        academic_year=cg.academic_year,
        gate="s1_final",
        decided_on=date.today(),
    )
    ExamDecisionService.save(obj, principal_user)
    obj.deprived = False
    ExamDecisionService.save(obj, teacher_user)
    ExamDecisionService.delete(obj, principal_user)

    logs = list(
        AuditLog.objects.filter(changes__op="exam_decision", object_id=str(obj.pk)).order_by(
            "timestamp"
        )
    )
    assert [log.action for log in logs] == ["create", "update", "delete"]
    assert [log.user for log in logs] == [principal_user, teacher_user, principal_user]
    update = logs[1].changes
    assert (update["before"]["deprived"], update["after"]["deprived"]) == ("True", "False")
    assert update["before"]["decided_by_id"] == str(principal_user.pk)
    assert update["after"]["decided_by_id"] == str(teacher_user.pk)
    assert logs[2].changes["after"] is None


def test_decision_for_a_closed_year_is_refused(school, teacher_user, principal_user):
    from assessments.models import ExamDeprivation
    from assessments.services import ClosedYearError, ExamDecisionService

    cg, _ = _class(school, teacher_user, n=1, code="W")
    with pytest.raises(ClosedYearError):
        ExamDecisionService.save(
            ExamDeprivation(
                school=school,
                student=_student(cg),
                academic_year="2019-2020",
                gate="s1_final",
                decided_on=date.today(),
            ),
            principal_user,
        )
    assert not ExamDeprivation.objects.exists()

"""[COMPLIANCE 0.1 · 2.2 · جولة إصلاح 9] الحكمُ الواحد — ما أثبتته المراجعةُ العدائيّة
ومواصفةُ المالك لأربعة أحكامٍ متنازَعٍ عليها أو صامتٍ عنها.

الأصل (صفحاتٌ مصوَّرة، `data/2026-2027/03- الأكاديمي/`، بالأرقام المطبوعة):

  4–11  م8 ص9         الجبرُ في ثلاث لحظاتٍ فقط — لا رابعة (مواصفةُ الجولة 9، §1)
        م25 ص22        «تجمع درجات هذا الاختبار مع … وتضاف إلى درجات الطالب في الفصل
                       الدراسي الأول» — فصلٌ أوّلُ لم يُرصد ليس صفراً
        ملحق ص59–63    المواد الإضافيّة: «لا توجد … تقييمات دورية، ولا تُكتب في تقرير
                       الطالب ولا في شهادة نهاية العام إطلاقاً» (مواصفةُ الجولة 9، §2)
        م50 ص33        القاعدةُ الثالثة: «يوضح في الشهادة أنه قد تم ترفيع الطالب … بناء
                       على القاعدة الثالثة» (مواصفةُ الجولة 9، §3.4)

كلُّ اختبارٍ يستورد الجديدَ داخلَه، فيُجمع على شيفرة الجولة 8 ويسقط فيها بعينه.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest

from assessments.models import AnnualSubjectResult, Assessment, AssessmentPackage, ExamDeprivation
from assessments.services import ExamDecisionService, GradeService, package_facts
from core.domain.grades import ExamFacts, SubjectFacts, judge_student
from tests.test_assessment_verdict import _class, _mark, _student

F = Fraction


def _s1(p1=12, aw=4, p2=16):
    return {
        "P1": ExamFacts(F(p1), F(15)),
        "AW": ExamFacts(F(aw), F(5)),
        "P2": ExamFacts(F(p2), F(20)),
    }


def _s2(p3=12, aw=4, p4=32):
    return {
        "P3": ExamFacts(F(p3), F(15)),
        "AW": ExamFacts(F(aw), F(5)),
        "P4": ExamFacts(F(p4), F(40)),
    }


def _others(n=4):
    return [SubjectFacts(f"o{i}", _s1(), _s2()) for i in range(n)]


# ═══ 1 — الفصلُ الأوّل غيرُ المرصود لا يُحمل صفراً في الدور الثاني (م25/م26) ══════════


def test_unrecorded_first_semester_stays_incomplete_not_zeroed_into_excused():
    """أعمالُ الفصل الأول لم تُرصد، وعُذر عن منتصف الفصل الثاني ونهايته: «غير مكتمل» —
    لا «معذور — دور ثانٍ» بمحمولٍ صفر (كان `s1 or Fraction(0)` يحمل صفراً)."""
    x = SubjectFacts(
        "x",
        {"P1": ExamFacts(F(12), F(15)), "P2": ExamFacts(F(16), F(20))},  # AW لم تُرصد إطلاقاً
        {
            "P3": ExamFacts(None, F(15), excused_share=F(1)),
            "P4": ExamFacts(None, F(40), excused_share=F(1)),
            "AW": ExamFacts(F(4), F(5)),
        },
    )
    v = judge_student(10, [x] + _others())
    sub = v.by_key()["x"]
    assert sub.status == "incomplete"
    assert sub.annual_total is None
    assert v.standing == "incomplete"


def test_unrecorded_first_semester_still_incomplete_when_second_semester_complete():
    """نفسُ العلّة حين يكتمل الفصلُ الثاني عاديّاً (لا عذرَ فيه) — أيضاً «غير مكتمل»."""
    x = SubjectFacts(
        "x",
        {"P2": ExamFacts(F(16), F(20)), "AW": ExamFacts(F(4), F(5))},  # P1 لم يُرصد
        _s2(),
    )
    v = judge_student(9, [x] + _others())
    assert v.by_key()["x"].status == "incomplete"


# ═══ 2 — قصوى الدور الثاني قد لا تكون مضاعفَ نصفٍ — لا AssertionError ═══════════════


def test_second_round_max_with_partial_midterm_excuse_does_not_crash():
    """م25: عذرٌ عن ربع منتصف الفصل الثاني (تقييمٌ مقسومٌ 25/75) وعن نهايته كاملةً —
    قصوى الدور الثاني 43.75 (= 40 + ربع الخمسة عشر)؛ كانت `_to_decimal` تُسقط
    `AssertionError` لأنّها ليست مضاعفَ نصف."""
    x = SubjectFacts(
        "x",
        _s1(),
        {
            "P3": ExamFacts(F(9), F(15), excused_share=F(1, 4)),
            "P4": ExamFacts(None, F(40), excused_share=F(1)),
            "AW": ExamFacts(F(4), F(5)),
        },
    )
    v = judge_student(10, [x] + _others())
    sub = v.by_key()["x"]
    assert sub.status == "excused"
    assert sub.second_round_max == Decimal("43.75")


# ═══ 3 — موضعُ الجبر مستقرٌّ: لا قراءةٌ بديلة، ولا تنبيهُ مقارنة ════════════════════


def test_no_alternate_jabr_reading_functions_remain():
    import core.domain.grades as g

    assert not hasattr(g, "JABR_TOTAL_ONLY")
    assert not hasattr(g, "JABR_EACH_EXAM")
    assert not hasattr(g, "JABR_READINGS")
    assert not hasattr(g, "_jabr_reading_reviews")


# ═══ 4 — الموادّ الإضافيّة: لا سجلّاتٍ لها إطلاقاً ═══════════════════════════════════


def test_additional_subject_predicate_matches_the_appendix():
    from core.domain.grades import is_additional_subject

    assert is_additional_subject(8, "اللغة الفرنسية")
    assert is_additional_subject(6, "مسرح ودراما")
    assert is_additional_subject(10, "الفنون")  # سادسُ خيارٍ في العاشر وحدَه
    assert not is_additional_subject(9, "الفنون")  # لا وجودَ لها فيما دون العاشر
    assert not is_additional_subject(11, "الفنون")  # اختياريّةٌ أساسيّةٌ هناك — لا إضافية
    assert not is_additional_subject(4, "الروبوت")  # الرابعُ صمتٌ تامّ
    assert not is_additional_subject(12, "الروبوت")
    assert not is_additional_subject(8, "الرياضيات")


@pytest.mark.django_db
def test_additional_subject_gets_no_packages_and_no_annual_result(school, teacher_user):
    """`ensure_packages` لا تُنشئ شيئاً لمادّةٍ إضافيّة، و`plan_students` لا يكتب لها صفّاً."""
    from operations.models import Subject

    cg, (setup,) = _class(school, teacher_user, grade="G8", n=1, code="ADD")
    setup.subject = Subject.objects.create(school=school, name_ar="اللغة الفرنسية", code="ADD-FR")
    setup.save(update_fields=["subject"])
    student = _student(cg)

    assert GradeService.ensure_packages(setup, "S1") == []
    assert not AssessmentPackage.objects.filter(setup=setup).exists()

    GradeService.recalculate_full_class(setup)
    assert not AnnualSubjectResult.objects.filter(student=student, setup=setup).exists()


# ═══ 5 — باقةٌ لم يكتمل رصدُها لا تُحسب نسبةً جزئيّة كأنّ الباقي صفر ═════════════════


@pytest.mark.django_db
def test_ungraded_item_makes_the_whole_package_unrecorded_not_partial(school, teacher_user):
    """بندٌ واحدٌ في الأعمال بلا صفٍّ إطلاقاً يجعل الباقةَ كلَّها «غير مرصودة» لا نسبةً محسوبةً
    من نصفها وحدَه — وكذلك صفٌّ محفوظٌ بلا درجةٍ ولا غياب (خانةٌ فارغةٌ من «حفظ الكلّ»)."""
    cg, (setup,) = _class(school, teacher_user, n=1)
    student = _student(cg)
    GradeService.ensure_packages(setup, "S1")
    pkg = AssessmentPackage.objects.get(setup=setup, semester="S1", package_type="AW")
    item1 = Assessment.objects.create(
        package=pkg,
        school=school,
        title="و1",
        max_grade=Decimal("10"),
        weight_in_package=Decimal("50"),
        status="published",
    )
    item2 = Assessment.objects.create(
        package=pkg,
        school=school,
        title="و2",
        max_grade=Decimal("10"),
        weight_in_package=Decimal("50"),
        status="published",
    )
    _mark(item1, student, 10)  # كاملةٌ في البند الأول
    # البندُ الثاني بلا صفٍّ إطلاقاً — لم يُرصد بعد.
    exams, _ = package_facts([pkg], [student.id])
    assert (student.id, pkg.id) not in exams

    # وصفٌ صريحٌ بلا درجةٍ ولا غياب (خانةٌ فارغة) لهذا البند — الأثرُ نفسُه.
    _mark(item2, student, None)
    exams, _ = package_facts([pkg], [student.id])
    assert (student.id, pkg.id) not in exams

    # فإذا رُصد البندُ الثاني اكتملت الباقةُ وحُسبت.
    _mark(item2, student, 8)
    exams, _ = package_facts([pkg], [student.id])
    facts = exams[(student.id, pkg.id)]
    assert facts.score == F(9, 10) * F(5)  # (10+8)/20 × 5


# ═══ 6 — قرارُ الحرمان/الانضباط لا يُنسخ اسمُ الطالب ولا نصُّ ملاحظته إلى سجلٍّ لا يُمحى ═


@pytest.mark.django_db
def test_decision_audit_log_has_no_student_name_or_free_text(school, teacher_user, principal_user):
    from core.models import AuditLog

    cg, _ = _class(school, teacher_user, n=1)
    student = _student(cg, "اسمٌ حسّاس للاختبار")
    year = cg.academic_year
    obj = ExamDeprivation(
        school=school,
        student=student,
        academic_year=year,
        gate="s1_midterm",
        deprived=False,
        decided_on=date.today(),
        note="قُبل العذر: تقرير طبي حسّاس",
    )
    ExamDecisionService.save(obj, principal_user)
    log = AuditLog.objects.filter(changes__op="exam_decision").latest("timestamp")
    blob = str(log.changes)
    assert student.full_name not in log.object_repr
    assert student.full_name not in blob
    assert "تقرير طبي" not in blob
    assert str(student.id) in blob  # يبقى المعرّفُ لا الاسم


# ═══ 7 — الشهادةُ توضح الترفيعَ بالقاعدة الثالثة ودرجةَ الدور الثاني (م50) ══════════


def test_certificate_row_shows_rule_three_promotion_note_only_for_rule_three():
    from core.domain.grades import PROMOTION_RULE_3_ARTICLE, STATUS_PROMOTED
    from reports.views import _subject_rows_presentation

    rule3 = AnnualSubjectResult(
        academic_year="2026-2027",
        status=STATUS_PROMOTED,
        article=PROMOTION_RULE_3_ARTICLE,
        second_round_score=Decimal("62.00"),
        annual_total=Decimal("50"),
    )
    rule1 = AnnualSubjectResult(
        academic_year="2026-2027",
        status=STATUS_PROMOTED,
        article="م50 القاعدة الأولى",
        annual_total=Decimal("48"),
    )
    rows = [{"annual": rule3}, {"annual": rule1}]
    _subject_rows_presentation(rows)
    assert "القاعدة الثالثة" in rows[0]["promotion_note"]
    assert "62.00" in rows[0]["promotion_note"]
    assert rows[1]["promotion_note"] == ""


# ═══ 8 — كشفُ الشعبة لا يعدّ المعذورَ بلا رسوبٍ فعليّ ضمن «الراسبين» ═══════════════


@pytest.mark.django_db
def test_class_sheet_does_not_count_purely_excused_students_as_failed(school, teacher_user):
    """طالبٌ معذورٌ عن الفصل الثاني كلِّه في مادّةٍ واحدة (م26) بلا رسوبٍ فعليّ في أيّ مادّة —
    موقفُه العامّ «دور ثانٍ» (`FAILING_STANDINGS`)، لكنّ «الراسبين» في كشف الشعبة عدٌّ على
    المادّة (`row['failed']`، ومثلُه `get_failing_students`/`failing_by_class`) — فلا يظهر
    فيه، ولا يناقض السطرَ نفسَه الذي يُظهر له صفر موادّ راسبة."""
    from reports.services import ReportDataService
    from tests.test_assessment_verdict import T80, _exams, _fill

    cg, (setup, other) = _class(school, teacher_user, n=2, code="EXC")
    student = _student(cg)
    exams, other_exams = _exams(setup), _exams(other)
    _fill(exams, student, (12, 16, 4, "excused", "excused", 4))
    _fill(other_exams, student, T80)
    GradeService.recalculate_full_class(setup)
    GradeService.recalculate_full_class(other)

    data = ReportDataService.get_class_results(cg, school)
    row = next(r for r in data["student_rows"] if r["student"] == student)
    assert row["standing"] == "second_round"
    assert row["failed"] == 0
    assert data["total_failed"] == 0

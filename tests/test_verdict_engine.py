"""محرّكُ الحكم الواحد (`assessments/verdict_engine.py`) — خلف راية `VERDICT_ENGINE_ENABLED`.

يثبت هذا الملفّ:
1. **الراية المطفأة لا تغيّر شيئاً**: `save_grade` يحسب بالمسار القديم ولا يكتب موقفاً ولا إصداراً.
2. **الراية المرفوعة تحكم وتخزّن**: الموقفُ والحالةُ والإصدارُ وسجلُّ المراجعة، والترفيعُ م50،
   والغيابُ م27، والباقةُ غيرُ المكتملة، والإرجاءُ إلى الإصدار الجاري، والعامُ المغلق.
3. **الأمرُ**: العرضُ متاحٌ دائماً، والتطبيقُ يشترط الراية والفاعل.

الوقائعُ اصطناعيّةٌ بحتة: لا طلابَ حقيقيّين ولا أرقامَ شخصيّةً.
"""

from __future__ import annotations

from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from assessments.models import (
    AnnualSubjectResult,
    Assessment,
    AssessmentPackage,
    StudentSubjectResult,
    SubjectClassSetup,
)
from assessments.services import GradeService
from assessments.verdict_engine import ClosedYearError, VerdictEngine
from core.domain.grades import VERDICT_RULESET
from core.models import AuditLog
from operations.models import Subject
from tests.conftest import ClassGroupFactory, StudentEnrollmentFactory, UserFactory

pytestmark = pytest.mark.django_db

#: الباقاتُ وأنصبتُها كما في القرار 14/2018 م3: (الفصل، النوع، الوزنُ داخل الفصل، أقصى الفصل).
PACKAGES = (
    ("S1", "P1", "37.50", "40"),
    ("S1", "AW", "12.50", "40"),
    ("S1", "P2", "50.00", "40"),
    ("S2", "P3", "25.00", "60"),
    ("S2", "AW", "8.33", "60"),
    ("S2", "P4", "66.67", "60"),
)


@pytest.fixture
def engine_on(settings):
    settings.VERDICT_ENGINE_ENABLED = True


@pytest.fixture
def klass(school, seeded_calendar):
    """شعبةٌ من الصفّ الثامن بثماني موادّ وطالبٍ واحد."""
    teacher = UserFactory()
    group = ClassGroupFactory(school=school, grade="G8", academic_year=seeded_calendar)
    student = UserFactory()
    StudentEnrollmentFactory(student=student, class_group=group)
    setups, exams = [], {}
    for i in range(8):
        subject = Subject.objects.create(school=school, name_ar=f"مادة {i}", code=f"V{i}")
        setup = SubjectClassSetup.objects.create(
            school=school,
            subject=subject,
            class_group=group,
            teacher=teacher,
            academic_year=seeded_calendar,
        )
        setups.append(setup)
        for sem, ptype, weight, sem_max in PACKAGES:
            pkg = AssessmentPackage.objects.create(
                setup=setup,
                school=school,
                package_type=ptype,
                semester=sem,
                weight=Decimal(weight),
                semester_max_grade=Decimal(sem_max),
            )
            exams[(setup.id, sem, ptype)] = Assessment.objects.create(
                package=pkg,
                school=school,
                title="اختبار",
                max_grade=Decimal("100"),
                weight_in_package=Decimal("100"),
                status="published",
            )
    return {"school": school, "group": group, "student": student, "setups": setups, "exams": exams}


def _fill(k, setup, s1_pct, s2_pct, *, skip=(), absent=()):
    """يرصد للطالب نسبةً في كلّ باقات المادّة — `skip` بلا رصد، و`absent` غيابٌ بلا عذر."""
    for sem, ptype, _w, _m in PACKAGES:
        if (sem, ptype) in skip:
            continue
        exam = k["exams"][(setup.id, sem, ptype)]
        pct = Decimal(str(s1_pct if sem == "S1" else s2_pct))
        GradeService.save_grade(
            exam,
            k["student"],
            grade=None if (sem, ptype) in absent else pct,
            is_absent=(sem, ptype) in absent,
        )


def _all_pass(k, except_setup=None):
    for setup in k["setups"]:
        if setup is not except_setup:
            _fill(k, setup, 80, 80)


def _annual(k, setup):
    return AnnualSubjectResult.objects.get(student=k["student"], setup=setup)


# ── 1. الراية المطفأة ────────────────────────────────────────────────────


def test_flag_off_keeps_the_old_calculation(klass):
    setup = klass["setups"][0]
    _fill(klass, setup, 80, 80)
    row = _annual(klass, setup)
    assert row.status == "pass"
    assert row.standing == "incomplete"  # لم يُكتب موقفٌ
    assert row.ruleset == 0
    assert not AuditLog.objects.filter(changes__op="verdict_recalculated").exists()


# ── 2. الراية المرفوعة ───────────────────────────────────────────────────


def test_flag_on_passes_and_stamps_the_ruleset(klass, engine_on):
    _all_pass(klass)
    row = _annual(klass, klass["setups"][0])
    assert (row.status, row.standing, row.ruleset) == ("pass", "passed", VERDICT_RULESET)
    assert row.annual_total == Decimal("80")
    assert StudentSubjectResult.objects.filter(student=klass["student"]).count() == 16


def test_flag_on_promotes_a_subject_short_by_up_to_two(klass, engine_on):
    weak = klass["setups"][0]
    _all_pass(klass, except_setup=weak)
    _fill(klass, weak, 47, 47)  # 48.5 بعد الجبر → ينقصه 1.5 → م50 القاعدة الأولى
    row = _annual(klass, weak)
    assert row.status == "promoted"
    assert row.standing == "promoted"
    assert row.article == "م50 القاعدة الأولى"
    other = _annual(klass, klass["setups"][1])
    assert (other.status, other.standing) == ("pass", "promoted")


def test_flag_on_absent_from_s2_final_sits_second_round(klass, engine_on):
    weak = klass["setups"][0]
    _all_pass(klass, except_setup=weak)
    _fill(klass, weak, 80, 80, absent=(("S2", "P4"),))
    row = _annual(klass, weak)
    assert row.status == "second_round"
    assert row.mark == "absent"
    assert row.standing == "second_round"
    assert row.annual_total is None


def test_flag_on_unrecorded_package_is_incomplete_not_summed(klass, engine_on):
    weak = klass["setups"][0]
    _all_pass(klass, except_setup=weak)
    _fill(klass, weak, 80, 80, skip=(("S1", "AW"),))
    row = _annual(klass, weak)
    assert row.status == "incomplete"
    assert row.standing == "incomplete"


def test_flag_on_writes_an_audit_row_with_before_and_after(klass, engine_on):
    setup = klass["setups"][0]
    _fill(klass, setup, 80, 80)
    logs = AuditLog.objects.filter(changes__op="verdict_recalculated")
    assert logs.exists()
    changed = [r for log in logs for r in log.changes["rows"] if r["row"] == "annual"]
    assert changed and changed[-1]["after"]["status"] in {"pass", "incomplete"}


def test_flag_on_restamps_a_class_written_by_an_older_ruleset(klass, engine_on):
    """صفٌّ قديمٌ (إصدار 0) في الشعبة → أوّلُ حسابٍ يُعيد الحكمَ عليها كلِّها بالإصدار الجاري."""
    _all_pass(klass)
    AnnualSubjectResult.objects.filter(student=klass["student"]).update(ruleset=0)
    exam = klass["exams"][(klass["setups"][0].id, "S1", "P1")]
    GradeService.save_grade(exam, klass["student"], grade=Decimal("90"))
    assert not AnnualSubjectResult.objects.filter(
        student=klass["student"], ruleset__lt=VERDICT_RULESET
    ).exists()


def test_flag_on_refuses_writes_to_a_closed_year(klass, engine_on):
    setup = klass["setups"][0]
    SubjectClassSetup.objects.filter(pk=setup.pk).update(academic_year="2001-2002")
    exam = klass["exams"][(setup.id, "S1", "P1")]
    with pytest.raises(ClosedYearError):
        GradeService.save_grade(exam, klass["student"], grade=Decimal("50"))


def test_flag_off_still_accepts_writes_to_any_year(klass):
    setup = klass["setups"][0]
    SubjectClassSetup.objects.filter(pk=setup.pk).update(academic_year="2001-2002")
    exam = klass["exams"][(setup.id, "S1", "P1")]
    GradeService.save_grade(exam, klass["student"], grade=Decimal("50"))


def test_plan_students_computes_without_writing(klass, engine_on):
    _all_pass(klass)
    before = _annual(klass, klass["setups"][0]).updated_at
    plan = VerdictEngine.plan_students(
        klass["group"], klass["setups"][0].academic_year, [klass["student"]]
    )
    assert plan.students == 1
    assert _annual(klass, klass["setups"][0]).updated_at == before


# ── 3. الأمر ─────────────────────────────────────────────────────────────


def _run(*args, **kw):
    out = StringIO()
    call_command("recalculate_grade_results", *args, stdout=out, **kw)
    return out.getvalue()


def test_command_dry_run_works_with_the_flag_off(klass):
    _fill(klass, klass["setups"][0], 80, 80)
    text = _run(school=klass["school"].code)
    assert "عرضٌ فقط" in text
    assert AnnualSubjectResult.objects.filter(ruleset=VERDICT_RULESET).count() == 0


def test_command_apply_is_refused_while_the_flag_is_off(klass):
    with pytest.raises(CommandError, match="VERDICT_ENGINE_ENABLED"):
        _run("--apply", "--actor", "x", school=klass["school"].code)


def test_command_apply_requires_an_actor(klass, engine_on):
    with pytest.raises(CommandError, match="--actor"):
        _run("--apply", school=klass["school"].code)


def test_command_apply_rewrites_and_logs(klass, engine_on):
    _all_pass(klass)
    AnnualSubjectResult.objects.filter(student=klass["student"]).update(ruleset=0)
    actor = UserFactory()
    text = _run("--apply", "--actor", actor.national_id, school=klass["school"].code)
    assert "طُبّق" in text
    assert not AnnualSubjectResult.objects.filter(ruleset__lt=VERDICT_RULESET).exists()
    assert AuditLog.objects.filter(changes__op="recalculate_grade_results", user=actor).exists()

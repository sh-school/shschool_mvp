"""[RECONCILE] نقلُ عملٍ من 8500 إلى قاعدةٍ أخرى بالمفتاح الطبيعيّ — بلا PII وبلا كتابةٍ خارج خدمات المنصّة.

الثوابتُ المحروسة هنا:

    NaturalKey = (school.code, teacher.hmac|employee_number, subject.code, grade/section, year)   لا UUID
    Dump ≠ Apply                القراءةُ نقيّةٌ، والكتابةُ عبر assignment_services/workload_workflow وحدَهما
    FrozenPlan → لا تُعدَّل آليّاً أبداً حتى لو اختلفت عمّا دُمق

القاعدةُ هنا واحدةٌ (المصدر=الهدف)؛ فالمطابقةُ بالمفتاح الطبيعيّ داخل قاعدةٍ واحدةٍ تُثبت المنطقَ نفسَه الذي
يعمل بين قاعدتين مختلفتين، لأنّ الحلَّ لا يقرأ شيئاً غيرَ الحقول الطبيعيّة.
"""

import io
import json

import pytest
from django.core.management import call_command

from academic_management import preview_reconciliation as recon
from academic_management.models import APPROVED, DRAFT, FROM_MANUAL, TeacherWorkloadPlan
from academic_management.preview_reconciliation import ReconciliationError

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"


@pytest.fixture
def school(db):
    from core.models import School

    return School.objects.create(name="مدرسة الاختبار", code="TST-1")


@pytest.fixture
def subject(db, school):
    from operations.models import Subject

    return Subject.objects.create(school=school, name_ar="الكيمياء", code="CHM")


@pytest.fixture
def klass(db, school):
    from core.models import ClassGroup

    return ClassGroup.objects.create(
        school=school,
        grade="G12",
        section="1",
        level_type="sec",
        track="science",
        academic_year=YEAR,
    )


def _teacher(school, *, employee_number=""):
    from tests.conftest import MembershipFactory, RoleFactory, UserFactory

    role = RoleFactory(school=school, name="teacher")
    user = UserFactory(full_name="عطيه محمود", employee_number=employee_number)
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def teacher(db, school):
    return _teacher(school)


@pytest.fixture
def actor(db, school):
    """مطوّرُ منصّةٍ — يحرّر ويراجع (بديلاً عن --actor-employee-number)."""
    from tests.conftest import UserFactory

    return UserFactory(full_name="مطوّر المنصّة", is_superuser=True, is_staff=True)


@pytest.fixture
def approver(db, school):
    """معتمِدٌ مختلفٌ عن المراجع — الاعتمادُ توقيعٌ مستقلٌّ لا يجوز أن يوقّعه من راجع."""
    from tests.conftest import UserFactory

    return UserFactory(
        full_name="مدير المدرسة", is_superuser=True, is_staff=True, employee_number="22222"
    )


# ══════════════════════════════════════════════════════════════════════
#  الحلّ بالمفتاح الطبيعيّ
# ══════════════════════════════════════════════════════════════════════


def test_resolve_school_by_code(school):
    assert recon.resolve_school("TST-1").pk == school.pk


def test_resolve_school_fails_loudly_for_an_unknown_code(school):
    with pytest.raises(ReconciliationError, match="لا مدرسةَ"):
        recon.resolve_school("NOPE")


def test_resolve_teacher_by_hmac(teacher):
    found = recon.resolve_teacher(national_id_hmac=teacher.national_id_hmac)
    assert found.pk == teacher.pk


def test_resolve_teacher_by_employee_number_when_hmac_is_absent(school):
    t = _teacher(school, employee_number="99887")
    found = recon.resolve_teacher(employee_number="99887")
    assert found.pk == t.pk


def test_resolve_teacher_fails_loudly_with_neither_key():
    with pytest.raises(ReconciliationError, match="لا معلّمَ"):
        recon.resolve_teacher()


def test_resolve_class_group_by_grade_section_year(school, klass):
    found = recon.resolve_class_group(school, grade="G12", section="1", academic_year=YEAR)
    assert found.pk == klass.pk


def test_resolve_subject_by_code_within_the_school(school, subject):
    found = recon.resolve_subject(school, "CHM")
    assert found.pk == subject.pk


def test_resolve_subject_fails_loudly_when_the_code_is_unknown(school):
    with pytest.raises(ReconciliationError, match="لا مادّةَ"):
        recon.resolve_subject(school, "XXX")


# ══════════════════════════════════════════════════════════════════════
#  الدمقُ — بلا بياناتٍ شخصيّة
# ══════════════════════════════════════════════════════════════════════


def test_dump_assignment_never_carries_the_national_id(school, klass, subject, teacher):
    from operations.models import SubjectClassAssignment

    row = SubjectClassAssignment.objects.create(
        school=school,
        class_group=klass,
        subject=subject,
        teacher=teacher,
        weekly_periods=6,
        academic_year=YEAR,
    )
    data = recon.dump_assignment(row)

    assert "national_id" not in json.dumps(data)
    assert data["teacher_hmac"] == teacher.national_id_hmac
    assert data["school_code"] == "TST-1" and data["subject_code"] == "CHM"
    assert data["grade"] == "G12" and data["section"] == "1"


def test_dump_workload_plan_never_carries_the_national_id(school, teacher, actor):
    from academic_management import workload_workflow as wf

    plan = wf.open_draft(
        school,
        teacher,
        YEAR,
        by=actor,
        required_weekly_periods=18,
        required_source_kind=FROM_MANUAL,
        required_source_reference="محضرُ اجتماعٍ 12",
    )
    data = recon.dump_workload_plan(plan)

    assert "national_id" not in json.dumps(data)
    assert data["teacher_hmac"] == teacher.national_id_hmac
    assert data["status"] == DRAFT


# ══════════════════════════════════════════════════════════════════════
#  التطبيقُ عبر الأمر — تقريرٌ فقط، ثمّ كتابةٌ فعليّة
# ══════════════════════════════════════════════════════════════════════


def _run_apply(path, actor, apply=False, approver=None):
    out = io.StringIO()
    args = ["--in", path]
    if apply:
        args += ["--apply", "--actor-employee-number", actor.employee_number]
        if approver is not None:
            args += ["--approver-employee-number", approver.employee_number]
    call_command("apply_preview_workload_changes", *args, stdout=out)
    return out.getvalue()


def test_apply_reads_a_file_windows_tools_saved_with_a_utf8_bom(
    tmp_path, school, klass, subject, teacher, actor
):
    """PowerShell يكتب UTF-8 بعلامة BOM افتراضيّاً — وjson.load على utf-8 العاديّ يرفضها بخطأ فكِّ ترميز."""
    payload = {
        "assignments": [
            {
                "school_code": "TST-1",
                "academic_year": YEAR,
                "grade": "G12",
                "section": "1",
                "subject_code": "CHM",
                "teacher_hmac": teacher.national_id_hmac,
                "weekly_periods": 6,
                "requires_lab": False,
                "parallel_group": "",
                "periods_override_reason": "",
                "is_active": True,
            }
        ],
        "workload_plans": [],
    }
    path = tmp_path / "changes.json"
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(payload).encode("utf-8"))

    out = _run_apply(str(path), actor, apply=False)

    assert "تقريرٌ فقط" in out
    assert "خطأ" not in out


def test_dry_run_writes_nothing(tmp_path, school, klass, subject, teacher, actor):
    actor.employee_number = "11111"
    actor.save(update_fields=["employee_number"])
    payload = {
        "assignments": [
            {
                "school_code": "TST-1",
                "academic_year": YEAR,
                "grade": "G12",
                "section": "1",
                "subject_code": "CHM",
                "teacher_hmac": teacher.national_id_hmac,
                "weekly_periods": 6,
                "requires_lab": False,
                "parallel_group": "",
                "periods_override_reason": "",
                "is_active": True,
            }
        ],
        "workload_plans": [],
    }
    path = tmp_path / "changes.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    out = _run_apply(str(path), actor, apply=False)

    from operations.models import SubjectClassAssignment

    assert "تقريرٌ فقط" in out
    assert not SubjectClassAssignment.objects.exists()


def test_apply_creates_the_assignment_then_reports_no_change_on_a_second_run(
    tmp_path, school, klass, subject, teacher, actor
):
    actor.employee_number = "11111"
    actor.save(update_fields=["employee_number"])
    payload = {
        "assignments": [
            {
                "school_code": "TST-1",
                "academic_year": YEAR,
                "grade": "G12",
                "section": "1",
                "subject_code": "CHM",
                "teacher_hmac": teacher.national_id_hmac,
                "weekly_periods": 6,
                "requires_lab": False,
                "parallel_group": "",
                "periods_override_reason": "",
                "is_active": True,
            }
        ],
        "workload_plans": [],
    }
    path = tmp_path / "changes.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    from operations.models import SubjectClassAssignment

    out1 = _run_apply(str(path), actor, apply=True)
    assert "✓ كُتب" in out1
    row = SubjectClassAssignment.objects.get(school=school, class_group=klass, subject=subject)
    assert row.weekly_periods == 6 and row.teacher_id == teacher.id

    out2 = _run_apply(str(path), actor, apply=True)
    assert "لا تغيير" in out2
    assert (
        SubjectClassAssignment.objects.filter(
            school=school, class_group=klass, subject=subject
        ).count()
        == 1
    )


def test_apply_creates_a_new_workload_plan_and_advances_it_to_the_dumped_status(
    tmp_path, school, klass, subject, teacher, actor, approver
):
    """الإسنادُ أوّلاً ثمّ الخطّة: الاعتمادُ يتحقّق من أنّ المُسنَدَ يساوي الهدفَ التدريسيّ."""
    actor.employee_number = "11111"
    actor.save(update_fields=["employee_number"])
    payload = {
        "assignments": [
            {
                "school_code": "TST-1",
                "academic_year": YEAR,
                "grade": "G12",
                "section": "1",
                "subject_code": "CHM",
                "teacher_hmac": teacher.national_id_hmac,
                "weekly_periods": 6,
                "requires_lab": False,
                "parallel_group": "",
                "periods_override_reason": "",
                "is_active": True,
            }
        ],
        "workload_plans": [
            {
                "school_code": "TST-1",
                "academic_year": YEAR,
                "plan_version": 1,
                "teacher_hmac": teacher.national_id_hmac,
                "required_weekly_periods": 6,
                "required_source_kind": FROM_MANUAL,
                "required_source_reference": "محضرُ اجتماعٍ 12",
                "required_policy_key": "",
                "reduction_periods": 0,
                "reduction_reason": "",
                "reduction_source": "",
                "reduction_source_reference": "",
                "status": APPROVED,
            }
        ],
    }
    path = tmp_path / "changes.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    out = _run_apply(str(path), actor, apply=True, approver=approver)

    assert "✓ كُتبت" in out
    plan = TeacherWorkloadPlan.objects.get(school=school, teacher=teacher, academic_year=YEAR)
    assert plan.status == APPROVED and plan.required_weekly_periods == 6


def test_apply_never_touches_an_approved_plan_that_differs_it_only_warns(
    tmp_path, school, klass, subject, teacher, actor, approver
):
    from academic_management import workload_workflow as wf

    existing = wf.open_draft(
        school,
        teacher,
        YEAR,
        by=actor,
        required_weekly_periods=18,
        required_source_kind=FROM_MANUAL,
        required_source_reference="القرارُ الأصليّ",
    )
    from operations.models import SubjectClassAssignment

    SubjectClassAssignment.objects.create(
        school=school,
        class_group=klass,
        subject=subject,
        teacher=teacher,
        weekly_periods=18,
        academic_year=YEAR,
    )
    wf.submit_for_review(existing, by=actor)
    wf.record_review(existing, by=actor)
    wf.approve(existing, by=approver)

    actor.employee_number = "11111"
    actor.save(update_fields=["employee_number"])
    payload = {
        "assignments": [],
        "workload_plans": [
            {
                "school_code": "TST-1",
                "academic_year": YEAR,
                "plan_version": 1,
                "teacher_hmac": teacher.national_id_hmac,
                "required_weekly_periods": 22,
                "required_source_kind": FROM_MANUAL,
                "required_source_reference": "8500",
                "required_policy_key": "",
                "reduction_periods": 0,
                "reduction_reason": "",
                "reduction_source": "",
                "reduction_source_reference": "",
                "status": APPROVED,
            }
        ],
    }
    path = tmp_path / "changes.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    out = _run_apply(str(path), actor, apply=True)

    assert "لا تُعدَّل آليّاً" in out
    existing.refresh_from_db()
    assert existing.required_weekly_periods == 18


# ══════════════════════════════════════════════════════════════════════
#  احترامُ is_active — لا يُنشئ صفّاً غيرَ نشطٍ، ولا يُفعِّل ما أُطفئ (F-10)
# ══════════════════════════════════════════════════════════════════════


def _assignment_row(school, academic_year, grade, section, subject_code, teacher_hmac, **extra):
    row = {
        "school_code": school,
        "academic_year": academic_year,
        "grade": grade,
        "section": section,
        "subject_code": subject_code,
        "teacher_hmac": teacher_hmac,
        "weekly_periods": 6,
        "requires_lab": False,
        "parallel_group": "",
        "periods_override_reason": "",
        "is_active": True,
    }
    row.update(extra)
    return row


def test_apply_never_creates_a_row_for_an_inactive_dumped_assignment(
    tmp_path, school, klass, subject, teacher, actor
):
    row = _assignment_row(
        "TST-1", YEAR, "G12", "1", "CHM", teacher.national_id_hmac, is_active=False
    )
    path = tmp_path / "changes.json"
    path.write_text(json.dumps({"assignments": [row], "workload_plans": []}), encoding="utf-8")

    out = _run_apply(str(path), actor, apply=True)

    from operations.models import SubjectClassAssignment

    assert "لا تغيير" in out
    assert not SubjectClassAssignment.objects.exists()


def test_apply_deactivates_a_currently_active_row_when_the_dump_says_inactive(
    tmp_path, school, klass, subject, teacher, actor
):
    from operations.models import SubjectClassAssignment

    live = SubjectClassAssignment.objects.create(
        school=school,
        class_group=klass,
        subject=subject,
        teacher=teacher,
        weekly_periods=6,
        academic_year=YEAR,
    )
    row = _assignment_row(
        "TST-1", YEAR, "G12", "1", "CHM", teacher.national_id_hmac, is_active=False
    )
    path = tmp_path / "changes.json"
    path.write_text(json.dumps({"assignments": [row], "workload_plans": []}), encoding="utf-8")

    out = _run_apply(str(path), actor, apply=True)

    assert "✓ أُطفئ" in out
    live.refresh_from_db()
    assert live.is_active is False


def test_dry_run_reports_the_deactivation_without_writing_it(
    tmp_path, school, klass, subject, teacher, actor
):
    from operations.models import SubjectClassAssignment

    live = SubjectClassAssignment.objects.create(
        school=school,
        class_group=klass,
        subject=subject,
        teacher=teacher,
        weekly_periods=6,
        academic_year=YEAR,
    )
    row = _assignment_row(
        "TST-1", YEAR, "G12", "1", "CHM", teacher.national_id_hmac, is_active=False
    )
    path = tmp_path / "changes.json"
    path.write_text(json.dumps({"assignments": [row], "workload_plans": []}), encoding="utf-8")

    out = _run_apply(str(path), actor, apply=False)

    assert "إطفاءٌ" in out
    live.refresh_from_db()
    assert live.is_active is True
    assert SubjectClassAssignment.objects.filter(pk=live.pk, is_active=True).exists()


def test_apply_never_reactivates_a_row_that_the_dump_still_marks_inactive(
    tmp_path, school, klass, subject, teacher, actor
):
    """حتّى لو اختلفت حصصُه — لا تُفعَّل مادّةٌ غيرُ نشطةٍ في 8500 أبداً (`apply_assignment` يُفعِّل دائماً)."""
    from operations.models import SubjectClassAssignment

    dormant = SubjectClassAssignment.objects.create(
        school=school,
        class_group=klass,
        subject=subject,
        teacher=teacher,
        weekly_periods=4,
        academic_year=YEAR,
        is_active=False,
        deletion_reason="حُذفت سابقاً",
    )
    row = _assignment_row(
        "TST-1",
        YEAR,
        "G12",
        "1",
        "CHM",
        teacher.national_id_hmac,
        weekly_periods=6,
        is_active=False,
    )
    path = tmp_path / "changes.json"
    path.write_text(json.dumps({"assignments": [row], "workload_plans": []}), encoding="utf-8")

    out = _run_apply(str(path), actor, apply=True)

    assert "لا تغيير" in out
    dormant.refresh_from_db()
    assert dormant.is_active is False and dormant.weekly_periods == 4


def test_deactivations_apply_before_activations_so_a_transfer_lands_correctly(
    tmp_path, school, klass, subject, teacher, actor
):
    """نقلُ مادّةٍ من معلّمٍ إلى آخر في الدمق نفسِه: الإطفاءُ يُطبَّق قبل التفعيل مهما كان ترتيبُ السطور."""
    from operations.models import SubjectClassAssignment

    new_teacher = _teacher(school, employee_number="55555")
    SubjectClassAssignment.objects.create(
        school=school,
        class_group=klass,
        subject=subject,
        teacher=teacher,
        weekly_periods=6,
        academic_year=YEAR,
    )
    # التفعيلُ يسبق الإطفاءَ في الملفّ نفسِه عمداً — ليثبت أنّ الأمرَ لا يعتمد على ترتيب السطور.
    payload = {
        "assignments": [
            _assignment_row(
                "TST-1", YEAR, "G12", "1", "CHM", new_teacher.national_id_hmac, is_active=True
            ),
            _assignment_row(
                "TST-1", YEAR, "G12", "1", "CHM", teacher.national_id_hmac, is_active=False
            ),
        ],
        "workload_plans": [],
    }
    path = tmp_path / "changes.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    _run_apply(str(path), actor, apply=True)

    live = SubjectClassAssignment.objects.filter(
        school=school, class_group=klass, subject=subject, is_active=True
    )
    assert live.count() == 1 and live.first().teacher_id == new_teacher.id
    old = SubjectClassAssignment.objects.get(
        school=school, class_group=klass, subject=subject, teacher=teacher
    )
    assert old.is_active is False

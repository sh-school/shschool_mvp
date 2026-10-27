"""[ASSIGNMENT] نجاحُ الكتابة لا أثرُها الجانبيّ (W-20260928-006).

الجردُ (مسارات الكتابة العامّة في `assignment_services`): سبعةٌ — `apply_assignment` و`remove_assignment` و`set_parallel`
و`set_double` و`apply_preparation` و`remove_preparation` و`set_coordinator_entry_paused`. كان لـ`set_double` و`remove_preparation`
والمفتاحِ **لا اختبارَ مباشراً**، وكان الباقي يقرأ الكائنَ المُعاد من الدالّة لا السجلَّ المخزَّن؛ وعيبٌ يُعيد كائناً سليماً دون أن يحفظه يمرّ.
هنا يُعاد جلبُ السجلّ من القاعدة بعد كلّ استدعاء ويُفحص ما كُتب فيه بقيمه، ثمّ أثرُه في التدقيق.
"""

import pytest

from academic_management import assignment_services as svc
from academic_management.models import CoursePreparation, WorkloadGovernance
from core.models import AuditLog
from operations.models import SubjectClassAssignment
from tests.test_assignment_service import (  # noqa: F401  — تجهيزاتٌ وأدواتٌ مشتركة
    YEAR,
    a_teacher,
    actor,
    apply,
    plan_row,
    prepare,
    school,
    seventh,
    subjects,
    teacher,
)

pytestmark = pytest.mark.django_db


def stored(row):
    """السجلُّ كما هو في القاعدة لا كما أعادته الدالّة."""
    return SubjectClassAssignment.objects.get(pk=row.pk)


def written(school, subjects, seventh, teacher, actor):
    plan_row(school, subjects["MAT"], periods=5)
    row, _ = apply(school, seventh, subjects["MAT"], teacher, actor)
    return row


def test_apply_assignment_persists_the_row_with_its_values(
    school, subjects, seventh, teacher, actor
):
    row = written(school, subjects, seventh, teacher, actor)

    db = stored(row)
    assert db.is_active and db.weekly_periods == 5
    assert db.teacher_id == teacher.id and db.class_group_id == seventh.id
    assert db.subject_id == subjects["MAT"].id and db.academic_year == YEAR
    assert db.created_by_id == actor.id


def test_set_double_writes_the_flag_and_audits_it(school, subjects, seventh, teacher, actor):
    row = written(school, subjects, seventh, teacher, actor)

    svc.set_double(row, True, by=actor)
    assert stored(row).double_period is True and stored(row).updated_by_id == actor.id
    svc.set_double(stored(row), False, by=actor)
    assert stored(row).double_period is False, "صريحٌ: False لا None"

    entry = (
        AuditLog.objects.filter(model_name="SubjectClassAssignment", action="update")
        .order_by("-timestamp")
        .first()
    )
    assert entry.changes["after"]["double_period"] is False


def test_remove_assignment_soft_deletes_with_its_trace(school, subjects, seventh, teacher, actor):
    row = written(school, subjects, seventh, teacher, actor)

    svc.remove_assignment(assignment=row, by=actor, reason="نُقل المعلّم")

    db = stored(row)
    assert db.is_active is False and db.deleted_by_id == actor.id and db.deleted_at is not None
    assert db.deletion_reason == "نُقل المعلّم"
    assert AuditLog.objects.filter(model_name="SubjectClassAssignment", action="delete").exists()


def test_set_parallel_writes_one_shared_tag_to_both_rows_and_unlinking_clears_it(
    school, subjects, seventh, teacher, actor
):
    plan_row(school, subjects["SCI"], periods=5)
    first = written(school, subjects, seventh, teacher, actor)
    other = a_teacher(school, "معلّم العلوم")
    second, _ = apply(school, seventh, subjects["SCI"], other, actor)

    svc.set_parallel(first, second, by=actor)
    a, b = stored(first), stored(second)
    assert a.parallel_group and a.parallel_group == b.parallel_group

    svc.set_parallel(stored(first), None, by=actor)
    assert not (stored(first).parallel_group or "").strip()
    assert not (stored(second).parallel_group or "").strip(), "فكُّ الربط يشمل الشريك"


def test_apply_preparation_persists_the_preparer_and_audits(
    school, subjects, seventh, teacher, actor
):
    written(school, subjects, seventh, teacher, actor)

    row, _ = prepare(school, subjects["MAT"], teacher, actor)

    db = CoursePreparation.objects.get(pk=row.pk)
    assert db.teacher_id == teacher.id and db.is_active and db.updated_by_id == actor.id
    assert db.grade == "G7" and db.academic_year == YEAR
    assert AuditLog.objects.filter(model_name="CoursePreparation", action="create").exists()


def test_remove_preparation_deactivates_it_and_requires_a_reason(
    school, subjects, seventh, teacher, actor
):
    from django.core.exceptions import ValidationError

    written(school, subjects, seventh, teacher, actor)
    row, _ = prepare(school, subjects["MAT"], teacher, actor)

    with pytest.raises(ValidationError):
        svc.remove_preparation(preparation=row, by=actor, reason="  ")
    assert CoursePreparation.objects.get(pk=row.pk).is_active, "السببُ الفارغ لا يكتب شيئاً"

    svc.remove_preparation(preparation=row, by=actor, reason="تبدّل المقرّر")

    assert CoursePreparation.objects.get(pk=row.pk).is_active is False
    entry = AuditLog.objects.filter(model_name="CoursePreparation", action="delete").get()
    assert entry.changes["reason"] == "تبدّل المقرّر"


def test_pausing_coordinator_entry_persists_and_records_who_and_when(school, actor):
    svc.set_coordinator_entry_paused(school, True, actor)

    gov = WorkloadGovernance.objects.get(school=school)
    assert gov.coordinator_entry_paused is True
    assert gov.entry_changed_by_id == actor.id and gov.entry_changed_at is not None
    entry = AuditLog.objects.filter(model_name="WorkloadGovernance", action="update").get()
    assert entry.changes["coordinator_entry_paused"] == {"before": False, "after": True}

    svc.set_coordinator_entry_paused(school, True, actor)  # صريحٌ لا قلب: تكرارُه لا يكتب
    assert AuditLog.objects.filter(model_name="WorkloadGovernance", action="update").count() == 1
    svc.set_coordinator_entry_paused(school, False, actor)
    assert WorkloadGovernance.objects.get(school=school).coordinator_entry_paused is False


def test_pausing_is_refused_for_a_role_without_the_toggle(school, teacher):
    from django.core.exceptions import PermissionDenied

    with pytest.raises(PermissionDenied):
        svc.set_coordinator_entry_paused(school, True, teacher)
    assert not WorkloadGovernance.objects.filter(
        school=school, coordinator_entry_paused=True
    ).exists()

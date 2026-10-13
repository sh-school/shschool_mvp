"""خدمةُ «متابعة الغياب» — التسجيلُ والتصحيحُ والقراءةُ لسجلّي الاتّصال والإجراء (W-20261013-011).

العقدُ الثابتُ (مواصفة 0301): `followup_rows(user, date)` و`guardian_phone(student)` و`record_contact` و`record_action`
و`correct_contact` و`correct_action`. والخدمةُ **تتحقّق من القدرة وتحصر النطاق بنفسها** — فلا تتّكل على عرضٍ:

- القدرةُ ناقصةٌ = `PermissionDenied`؛ وطالبٌ خارج جناح المشرف = `Http404` (كالعروض).
- **الإضافةُ فقط:** التصحيحُ سجلٌّ جديدٌ يشير إلى السابق (`corrects`)، وما صُحِّح لا يُصحَّح ثانيةً.
- **تغذيةُ الأهل** لا تُكتب ولا تُقرأ إلّا لحامل `operations.absence_followup_feedback`؛ وتُحجب من الصفوف عن غيره.
- **لا اسمَ وليٍّ ولا أمٍّ** في أيّ مخرج (D-431م): `guardian_phone` ترجع أرقاماً وحدَها، ولا يُخزَّن رقمٌ.
- **التدقيق:** كلُّ إنشاءٍ أو تصحيحٍ سطرٌ في `AuditLog` بلا نصٍّ ولا رقمٍ ولا اسم.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Any

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.utils import timezone

from core.capabilities import has_capability
from core.models import AuditLog, CustomUser, ParentStudentLink
from operations.models import (
    AbsenceActionLog,
    AbsenceContactLog,
    AbsenceExcuse,
    StudentAttendance,
)

VIEW = "operations.absence_followup_view"
RECORD = "operations.absence_followup_record"
FEEDBACK = "operations.absence_followup_feedback"
PRINT = "operations.absence_followup_print"


class FollowupError(ValueError):
    """رُفض التسجيلُ لسببٍ في المدخلات — والرسالةُ للمستخدم."""


def _need(user: Any, key: str) -> None:
    if not has_capability(user, key):
        raise PermissionDenied("لا صلاحيةَ لهذا الإجراء في متابعة الغياب.")


def _scope(user: Any) -> Any:
    from wings.scope import student_scope

    return student_scope(user, user.get_school())


def _student(user: Any, student_id: Any) -> CustomUser:
    """الطالبُ ضمن نطاق صاحب الطلب — خارج جناح المشرف = 404."""
    scope = _scope(user)
    if not scope.covers_student(student_id):
        raise Http404("ليس من طلبة جناحك")
    try:
        return CustomUser.objects.get(pk=student_id)
    except (CustomUser.DoesNotExist, ValueError, TypeError) as exc:
        raise Http404("طالبٌ غيرُ موجود") from exc


def _require_absent(school: Any, student: CustomUser, day: dt.date) -> None:
    if not StudentAttendance.objects.filter(
        school=school, student=student, session__date=day, status="absent"
    ).exists():
        raise FollowupError("لا غيابَ مرصوداً لهذا الطالب في هذا اليوم.")


def _audit(user: Any, action: str, what: str, log: Any) -> None:
    """سطرُ تدقيقٍ بالنوع والدور فقط — لا نصَّ ولا رقمَ ولا اسم."""
    AuditLog.log(
        user=user,
        action=action,
        model_name="other",
        object_id=log.pk,
        object_repr=what,
        changes={"role": user.get_role()},
        school=log.school,
    )


def _check_unrevised(model: Any, prior: Any) -> None:
    if model.objects.filter(corrects=prior).exists():
        raise FollowupError("صُحِّح هذا السجلُّ من قبلُ — صحّح آخرَ السلسلة.")


def record_contact(
    user: Any, student_id: Any, absence_date: dt.date, outcome: str, feedback: str = ""
) -> AbsenceContactLog:
    _need(user, RECORD)
    if feedback:
        _need(user, FEEDBACK)
    student = _student(user, student_id)
    school = user.get_school()
    if outcome not in dict(AbsenceContactLog.OUTCOMES):
        raise FollowupError("نتيجةُ الاتّصال غيرُ معروفة.")
    _require_absent(school, student, absence_date)
    log = AbsenceContactLog.objects.create(
        school=school,
        student=student,
        absence_date=absence_date,
        outcome=outcome,
        feedback=(feedback or "").strip()[:2000],
        contacted_by=user,
        contacted_at=timezone.now(),
    )
    _audit(user, "create", "اتّصالٌ بوليّ أمر عن غياب", log)
    return log


def correct_contact(user: Any, log_id: Any, **fields: Any) -> AbsenceContactLog:
    """تصحيحٌ = سجلٌّ جديدٌ يرث السابقَ ويبدّل ما في `fields` (outcome وfeedback)."""
    _need(user, RECORD)
    prior = AbsenceContactLog.objects.filter(pk=log_id, school=user.get_school()).first()
    if prior is None:
        raise Http404("السجلُّ غيرُ موجود")
    student = _student(user, prior.student_id)
    _check_unrevised(AbsenceContactLog, prior)
    outcome = fields.get("outcome", prior.outcome)
    if outcome not in dict(AbsenceContactLog.OUTCOMES):
        raise FollowupError("نتيجةُ الاتّصال غيرُ معروفة.")
    if "feedback" in fields:
        _need(user, FEEDBACK)
        feedback = (fields["feedback"] or "").strip()[:2000]
    else:
        # من لا يملك القدرة لا يمسّ نصَّها ولا ينسخه إلى سجلّه: يبقى في السابق وحدَه.
        feedback = prior.feedback if has_capability(user, FEEDBACK) else ""
    log = AbsenceContactLog.objects.create(
        school=prior.school,
        student=student,
        absence_date=prior.absence_date,
        outcome=outcome,
        feedback=feedback,
        contacted_by=user,
        contacted_at=timezone.now(),
        corrects=prior,
    )
    _audit(user, "update", "تصحيحُ اتّصالٍ بوليّ أمر عن غياب", log)
    return log


def _sick_leave_excuse(school: Any, student: CustomUser, day: dt.date) -> Any:
    return (
        AbsenceExcuse.objects.filter(
            school=school,
            student=student,
            kind="medical",
            date_from__lte=day,
            date_to__gte=day,
            status="accepted",
        )
        .order_by("-granted_at")
        .first()
    )


def record_action(
    user: Any,
    student_id: Any,
    absence_date: dt.date,
    action_kind: str,
    status: str,
    note: str = "",
    excuse: Any = None,
) -> AbsenceActionLog:
    _need(user, RECORD)
    student = _student(user, student_id)
    school = user.get_school()
    if status not in dict(AbsenceActionLog.STATUSES):
        raise FollowupError("حالةُ الإجراء غيرُ معروفة.")
    action_kind = action_kind or "other"
    if action_kind not in dict(AbsenceActionLog.KINDS):
        raise FollowupError("نوعُ الإجراء غيرُ معروف.")
    _require_absent(school, student, absence_date)
    if status == "sick_leave_received" and excuse is None:
        # استلامُ الإجازة يرتبط بالعذر القائم المقبول لليوم إن وُجد — لا نسخةً منه.
        excuse = _sick_leave_excuse(school, student, absence_date)
    log = AbsenceActionLog.objects.create(
        school=school,
        student=student,
        absence_date=absence_date,
        action_kind=action_kind,
        status=status,
        note=(note or "").strip()[:200],
        excuse=excuse,
        acted_by=user,
        acted_at=timezone.now(),
    )
    _audit(user, "create", "إجراءٌ إداريٌّ عن غياب", log)
    return log


def correct_action(user: Any, log_id: Any, **fields: Any) -> AbsenceActionLog:
    """تصحيحٌ = سجلٌّ جديدٌ يرث السابقَ ويبدّل ما في `fields` (action_kind وstatus وnote وexcuse)."""
    _need(user, RECORD)
    prior = AbsenceActionLog.objects.filter(pk=log_id, school=user.get_school()).first()
    if prior is None:
        raise Http404("السجلُّ غيرُ موجود")
    student = _student(user, prior.student_id)
    _check_unrevised(AbsenceActionLog, prior)
    status = fields.get("status", prior.status)
    if status not in dict(AbsenceActionLog.STATUSES):
        raise FollowupError("حالةُ الإجراء غيرُ معروفة.")
    if fields.get("action_kind", prior.action_kind) not in dict(AbsenceActionLog.KINDS):
        raise FollowupError("نوعُ الإجراء غيرُ معروف.")
    excuse = fields.get("excuse", prior.excuse)
    if status == "sick_leave_received" and excuse is None:
        excuse = _sick_leave_excuse(prior.school, student, prior.absence_date)
    log = AbsenceActionLog.objects.create(
        school=prior.school,
        student=student,
        absence_date=prior.absence_date,
        action_kind=fields.get("action_kind", prior.action_kind),
        status=status,
        note=(fields.get("note", prior.note) or "").strip()[:200],
        excuse=excuse,
        acted_by=user,
        acted_at=timezone.now(),
        corrects=prior,
    )
    _audit(user, "update", "تصحيحُ إجراءٍ إداريٍّ عن غياب", log)
    return log


def _heads(model: Any, school: Any, day: dt.date, student_ids: Any, by_field: str) -> dict:
    """آخرُ سجلٍّ لكلّ طالبٍ في اليوم — الذي لم يُستبدَل بلاحق."""
    rows = (
        model.objects.filter(school=school, absence_date=day, student_id__in=student_ids)
        .filter(corrected_by__isnull=True)
        .select_related(by_field)
        .order_by("-pk")
    )
    heads: dict = {}
    for row in rows:
        heads.setdefault(row.student_id, row)
    return heads


def guardian_phones_for(school: Any, student_ids: Any) -> dict[Any, list[str]]:
    """{معرّفُ الطالب: [أرقامُ أولياء أمره]} — أرقامٌ وحدَها بلا اسمٍ ولا صلة (D-431م)."""
    links = list(
        ParentStudentLink.objects.filter(school=school, student_id__in=student_ids).values_list(
            "student_id", "parent_id"
        )
    )
    parent_ids = {pid for _, pid in links}
    users = CustomUser.objects.filter(pk__in=parent_ids).only("pk", "phone", "phone_encrypted")
    phone_of = {u.pk: u.get_phone_decrypted() for u in users}
    out: dict[Any, list[str]] = defaultdict(list)
    for sid, pid in links:
        number = phone_of.get(pid, "")
        if number and number not in out[sid]:
            out[sid].append(number)
    return dict(out)


def guardian_phone(student: CustomUser) -> list[str]:
    """أرقامُ أولياء أمر طالبٍ — تُقرأ وقتَ العرض من `ParentStudentLink` ولا تُخزَّن، بلا اسمٍ ولا صلة."""
    school = student.get_school()
    return guardian_phones_for(school, [student.pk]).get(student.pk, [])


def followup_rows(user: Any, date: dt.date) -> list[dict]:
    """غائبو اليوم ضمن نطاق صاحب الطلب: لكلٍّ آخرُ اتّصالٍ وآخرُ إجراءٍ وأرقامُ الأولياء.

    مصدرُ الغائبين `daily_absence.daily_report`. ونصُّ التغذية الراجعة يُحجب (`feedback == ""`) عمّن
    لا يملك قدرتها. ومنسّقُ القسم يُحصر بمعلّمي قسمه؛ ومنسّقُ شؤون الطلبة والقيادةُ على المدرسة.
    """
    from core.permissions import get_department_teacher_ids
    from operations.daily_absence import daily_report

    _need(user, VIEW)
    school = user.get_school()
    scope = _scope(user)
    report = daily_report(
        school,
        date,
        teacher_ids=get_department_teacher_ids(user) if user.get_role() == "coordinator" else None,
        student_ids=scope.student_ids() if scope.is_wing_bound else None,
    )
    absent = [r for r in report.rows if r.absent_periods]
    ids = [r.student.id for r in absent]
    phones = guardian_phones_for(school, ids)
    contacts = _heads(AbsenceContactLog, school, date, ids, "contacted_by")
    actions = _heads(AbsenceActionLog, school, date, ids, "acted_by")
    may_feedback = has_capability(user, FEEDBACK)
    return [
        {
            "student": r.student,
            "class_group": r.class_group,
            "absent_periods": r.absent_periods,
            "ministry_flag": r.ministry_flag,
            "phones": phones.get(r.student.id, []),
            "contact": contacts.get(r.student.id),
            "feedback": (
                contacts[r.student.id].feedback if may_feedback and r.student.id in contacts else ""
            ),
            "action": actions.get(r.student.id),
        }
        for r in absent
    ]

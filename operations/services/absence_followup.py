"""خدمةُ «متابعة الغياب» — التسجيلُ والتصحيحُ والقراءةُ لسجلّي الاتّصال والإجراء (W-20261013-011).

العقدُ الثابتُ (مواصفة 0301): `followup_rows(user, date)` و`guardian_phone(student)` و`record_contact` و`record_action`
و`correct_contact` و`correct_action`. والخدمةُ **تتحقّق من القدرة وتحصر النطاق بنفسها** — فلا تتّكل على عرضٍ:

- القدرةُ ناقصةٌ = `PermissionDenied`؛ وطالبٌ خارج جناح المشرف = `Http404` (كالعروض).
- **الإضافةُ فقط:** التصحيحُ سجلٌّ جديدٌ يشير إلى السابق (`corrects`)، وما صُحِّح لا يُصحَّح ثانيةً.
- **التغذية الراجعة من وليّ الأمر** لا تُكتب ولا تُقرأ إلّا لحامل `operations.absence_followup_feedback`؛ وتُحجب من الصفوف عن غيره.
- **لا اسمَ وليٍّ ولا أمٍّ** في أيّ مخرج (D-431م): `guardian_phone` ترجع أرقاماً وحدَها، ولا يُخزَّن رقمٌ.
- **التدقيق:** كلُّ إنشاءٍ أو تصحيحٍ سطرٌ في `AuditLog` بلا نصٍّ ولا رقمٍ ولا اسم.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Any
from urllib.parse import urlencode

from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models.functions import TruncDay
from django.http import Http404
from django.utils import timezone

from core.capabilities import has_capability
from core.models import AuditLog, CustomUser, ParentStudentLink, Wing
from operations.models import (
    AbsenceActionLog,
    AbsenceContactLog,
    AbsenceExcuse,
    StudentAttendance,
)
from operations.models.absence_followup import FOLLOWUP_STATUSES

VIEW = "operations.absence_followup_view"
RECORD = "operations.absence_followup_record"
FEEDBACK = "operations.absence_followup_feedback"
PRINT = "operations.absence_followup_print"
FOLLOW = "operations.absence_followup_followup"

#: قيمُ «حالة الإجراء» التي لا يضعها إلّا حاملُ قدرة المتابعة (القيمُ السابقةُ مفتوحةٌ لكلّ كاتب).
_FOLLOW_ONLY_ACTION_STATUSES = frozenset({"partial", "not_followed"})


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


def _contact_status(user: Any, status: str) -> str:
    """حالةُ التواصل: لغير حاملِ قدرة المتابعة لا تُقبل (تُهمَل)، ولحاملها من القائمة المعروفة وحدَها."""
    if not status:
        return ""
    _need(user, FOLLOW)
    if status not in dict(FOLLOWUP_STATUSES):
        raise FollowupError("حالةُ التواصل غيرُ معروفة.")
    return status


def record_contact(
    user: Any,
    student_id: Any,
    absence_date: dt.date,
    outcome: str,
    feedback: str = "",
    status: str = "",
) -> AbsenceContactLog:
    _need(user, RECORD)
    if feedback:
        _need(user, FEEDBACK)
    status = _contact_status(user, status)
    student = _student(user, student_id)
    school = user.get_school()
    if outcome not in dict(AbsenceContactLog.OFFERED_OUTCOMES):
        raise FollowupError("نتيجةُ الاتّصال غيرُ معروفة.")
    if outcome == "other" and not (feedback or "").strip():
        raise FollowupError("«أخرى» تُكتب نصّاً: اكتب ما جرى في خانة التغذية الراجعة.")
    _require_absent(school, student, absence_date)
    log = AbsenceContactLog.objects.create(
        school=school,
        student=student,
        absence_date=absence_date,
        outcome=outcome,
        status=status,
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
    # القيمُ السابقةُ تبقى مقبولةً لمن لا يغيّرها؛ والتغييرُ يكون إلى الستّة المعروضة وحدَها.
    if outcome != prior.outcome and outcome not in dict(AbsenceContactLog.OFFERED_OUTCOMES):
        raise FollowupError("نتيجةُ الاتّصال غيرُ معروفة.")
    if outcome not in dict(AbsenceContactLog.OUTCOMES):
        raise FollowupError("نتيجةُ الاتّصال غيرُ معروفة.")
    # من لا يملك قدرةَ المتابعة لا يمسّ الحالةَ ولا ينسخها: تبقى في السابق (وهو لا يراها).
    if "status" in fields:
        status = _contact_status(user, fields["status"])
    else:
        status = prior.status if has_capability(user, FOLLOW) else ""
    if "feedback" in fields:
        _need(user, FEEDBACK)
        feedback = (fields["feedback"] or "").strip()[:2000]
    else:
        # من لا يملك القدرة لا يمسّ نصَّها ولا ينسخه إلى سجلّه: يبقى في السابق وحدَه.
        feedback = prior.feedback if has_capability(user, FEEDBACK) else ""
    if outcome == "other" and not feedback.strip():
        raise FollowupError("«أخرى» تُكتب نصّاً: اكتب ما جرى في خانة التغذية الراجعة.")
    log = AbsenceContactLog.objects.create(
        school=prior.school,
        student=student,
        absence_date=prior.absence_date,
        outcome=outcome,
        status=status,
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


def _action_status(user: Any, status: str, prior: str = "") -> str:
    """حالةُ الإجراء: غيرُ المسمّاة تُرفض، و«تمّ جزئياً/لم تتمّ المتابعة» لحاملِ قدرة المتابعة وحدَه.

    وكاتبٌ بلا القدرة لا يرى عمودَ الحالة فلا يرسل قيمةً: يُعدّ تسجيلُه إجراءً أنّه «تمّ». وإن صحّح سجلاً
    حالتُه من القيم المحجوبة فهي تبقى كما كانت (ولا يمسّها).
    """
    allowed_all = has_capability(user, FOLLOW)
    if not status:
        status = prior or "done"
    if status not in dict(AbsenceActionLog.STATUSES):
        raise FollowupError("حالةُ الإجراء غيرُ معروفة.")
    if status in _FOLLOW_ONLY_ACTION_STATUSES and not allowed_all and status != prior:
        raise PermissionDenied("لا صلاحيةَ لهذه الحالة في متابعة الغياب.")
    return status


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
    status = _action_status(user, status)
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
    status = _action_status(user, fields.get("status", prior.status), prior=prior.status)
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
    school = student.get_school()  # type: ignore[no-untyped-call]
    return guardian_phones_for(school, [student.pk]).get(student.pk, [])


def followup_rows(user: Any, date: dt.date) -> list[dict]:
    """غائبو اليوم ضمن نطاق صاحب الطلب: لكلٍّ آخرُ اتّصالٍ وآخرُ إجراءٍ وأرقامُ الأولياء.

    مصدرُ الغائبين `daily_absence.daily_report`، ولا يُحتسب منهم إلّا من غاب الحصّتين الأولى والثانية. ونصُّ التغذية الراجعة يُحجب (`feedback == ""`) عمّن
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
    # يُحتسب الطالبُ في المتابعة إن غاب الحصّتين الأولى والثانية معاً (قولُ المالك 2026-10-14، بلاغ FFED) — وهو
    # بالضبط «الرفعُ الوزاريّ» (`ministry_flag`): فالعدّادُ والجدولُ وزرُّ الملخّص من مصدرٍ واحد. وغيابُ حصّةٍ واحدة لا يظهر.
    absent = [r for r in report.rows if r.ministry_flag]
    ids = [r.student.id for r in absent]
    phones = guardian_phones_for(school, ids)
    contacts = _heads(AbsenceContactLog, school, date, ids, "contacted_by")
    actions = _heads(AbsenceActionLog, school, date, ids, "acted_by")
    may_feedback = has_capability(user, FEEDBACK)
    may_follow = has_capability(user, FOLLOW)
    rows = [
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
            # عمودا «المتابعة»: يُحجبان هنا في الخدمة عمّن لا قدرةَ له، فلا يصل قالبَ الشاشة ولا الكشفَ ولا PDF.
            "contact_status": _status_label(contacts.get(r.student.id), may_follow),
            "action_status": _status_label(actions.get(r.student.id), may_follow),
        }
        for r in absent
    ]
    rows.sort(key=_class_order)
    return rows


#: حالاتُ المتابعة للتصفية: كلُّ الغائبين، من لم يُتّصل بوليّه، من لا إجراءَ له، ومن اكتملت متابعتُه.
FOLLOWUP_FILTERS = [
    ("", "كلُّ الغائبين"),
    ("no_contact", "لم يُتّصل بوليّهم"),
    ("no_action", "بلا إجراءٍ مسجَّل"),
    ("complete", "اكتملت متابعتُهم"),
]

#: مفاتيحُ الفرز المسموحة — قائمةٌ بيضاءُ يتحقّق منها الخادم لا نصٌّ حرٌّ (الافتراضيُّ: الشعبةُ ثمّ الاسم).
SORTS = [
    ("class", "الشعبةُ ثمّ الاسم"),
    ("name", "الاسم"),
    ("periods", "الأكثرُ حصصَ غياب"),
]


def apply_view(
    rows: list[dict], *, grade: str = "", wing: str = "", followup: str = "", sort: str = ""
) -> list[dict]:
    """يصفّي صفوفَ الخدمة بالصفّ والجناح وحالة المتابعة ويفرزها — بعد أن ضيّقت الخدمةُ النطاقَ، فلا يتّسع به.

    الشاشةُ والكشفُ المطبوع وورقةُ الاتّصال تمرّ بهذه الدالّة نفسِها فيتطابق المطبوعُ مع المعروض. وكلُّ مفتاحٍ
    خارج القائمة البيضاء يُهمَل فيرجع الافتراضيَّ؛ والصفُّ والجناحُ يُقارَنان بالصفوف في الذاكرة فقط (لا استعلامَ منهما).
    """
    followup = followup if followup in dict(FOLLOWUP_FILTERS) else ""
    out = []
    for row in rows:
        group = row["class_group"]
        if grade and getattr(group, "grade", None) != grade:
            continue
        if wing and str(getattr(group, "wing_id", "")) != wing:
            continue
        if followup == "no_contact" and row["contact"]:
            continue
        if followup == "no_action" and row["action"]:
            continue
        if followup == "complete" and not (row["contact"] and row["action"]):
            continue
        out.append(row)
    if sort == "name":
        out.sort(key=lambda r: r["student"].full_name)
    elif sort == "periods":
        out.sort(key=lambda r: (-r["absent_periods"], r["student"].full_name))
    return out


def _status_label(log: Any, allowed: bool) -> str:
    """الاسمُ المعروض لحالة المتابعة، أو فارغٌ لمن لا قدرةَ له أو لا سجلَّ/حالةَ."""
    if not allowed or log is None or not log.status:
        return ""
    return str(log.get_status_display())


def _class_order(row: dict) -> tuple[int, int, str]:
    """ترتيبٌ تصاعديٌّ بالصفّ ثمّ الشعبة عدداً (7/1 … 12/4) ثمّ الاسم — لا أبجديّاً فيسبق 10 السابعَ."""
    group = row["class_group"]
    grade = (getattr(group, "grade", "") or "").removeprefix("G")
    section = str(getattr(group, "section", "") or "")
    return (
        int(grade) if grade.isdigit() else 99,
        int(section) if section.isdigit() else 99,
        row["student"].full_name,
    )


#: `TruncDay` يقبل اسمَ الحقل نصّاً وقتَ التشغيل، وstubs الإصدار المثبَّت تطلب `Expression` — نوعٌ فقط.
_trunc_day: Any = TruncDay


def _anonymise(model: Any, student: CustomUser, **blank: Any) -> list[Any]:
    """يُجهِّل صفوفَ الطالب في `model` ويرجع مفاتيحَها: يُنزَع الربطُ بالطالب وما في `blank` من محتوًى حرٍّ.

    السجلّان مضافان فقط فيرفض `update` على مديرهما؛ والتجهيلُ هو الاستثناءُ الوحيد، فيمرّ بـ`QuerySet` عاديٍّ
    على النموذج نفسِه (لا يمسّ أيَّ مسارٍ آخر). RLS تقيّده بمدرسة دور القاعدة كباقي الاستعلامات.
    """
    plain: Any = models.QuerySet(model, using=model.objects.db).filter(student=student)
    ids = list(plain.values_list("pk", flat=True))
    if ids:
        plain.update(student=None, **blank)
    return ids


def erase_followup_logs(
    student: CustomUser, *, actor: CustomUser | None = None, school: Any = None
) -> dict[str, int]:
    """يُجهِّل سجلَّي المتابعة لطالبٍ — حقُّ المحو (PDPPL م.18) بـ«أثرٍ مجهَّلٍ» (قرارُ المالك). **من `ErasureService` وحدَه.**

    لا حذفَ: يبقى الصفُّ بمدرسته وتاريخ غيابه ونتيجته/حالته ونوعه (للإحصاء)، ويُنزَع منه كلُّ ما يدلّ على الطالب:
    الربطُ به (`student` ← NULL)، وتغذيةُ الأهل المشفَّرة والملاحظةُ الحرّةُ والعذرُ المرتبطُ بطالبٍ (`excuse`)،
    وسلسلةُ التصحيح (`corrects` ← NULL: تربط صفوفَ الطالب الواحد فتُعيد تعريفَ الصفّ)، والموظّفُ الكاتب
    (`contacted_by`/`acted_by` ← NULL: يتذكّر الموظّفُ صفَّه)، ووقتُ الكتابة يُقصّ إلى اليوم (`TruncDay`).

    **لا يفشل صامتاً تحت RLS** كمحوِ سجلّ رصد المعلّم (حكمُ 0104): هويّةُ المستأجِر من دور القاعدة، فدورُ
    مدرسةٍ أخرى يرى صفراً فيُجهَّل 0 ويُقال «تمّ» والصفوفُ باقية. فيُرفض ابتداءً (`erasure_wrong_tenant`)، ويُتحقَّق
    بعد التجهيل ألّا يبقى ربطٌ بالطالب ولا نصٌّ في صفوفه (`erasure_incomplete`) — وكلاهما يُلغي المعاملةَ كلَّها.
    ويُكتب `AuditLog` بالأعداد وحدَها: لا نصَّ ولا رقمَ ولا اسم.
    """
    from operations.attendance_entries import EntryError, _role_tenant

    tenant = _role_tenant()
    if tenant is not None and school is not None and str(tenant) != str(school.pk):
        raise EntryError(
            "erasure_wrong_tenant",
            f"دورُ القاعدة الحاليّ لمدرسةٍ غيرِ مدرسة «{school.name}» التي قُدّم فيها طلبُ المحو — يُنفَّذ بدور مدرستها",
        )
    contact_ids = _anonymise(
        AbsenceContactLog,
        student,
        feedback="",
        corrects=None,
        contacted_by=None,
        contacted_at=_trunc_day("contacted_at"),
    )
    action_ids = _anonymise(
        AbsenceActionLog,
        student,
        note="",
        excuse=None,
        corrects=None,
        acted_by=None,
        acted_at=_trunc_day("acted_at"),
    )
    if (
        AbsenceContactLog.objects.filter(student=student).exists()
        or AbsenceActionLog.objects.filter(student=student).exists()
        or AbsenceContactLog.objects.filter(pk__in=contact_ids).exclude(feedback="").exists()
        or AbsenceContactLog.objects.filter(pk__in=contact_ids)
        .filter(models.Q(corrects__isnull=False) | models.Q(contacted_by__isnull=False))
        .exists()
        or AbsenceActionLog.objects.filter(pk__in=action_ids).exclude(note="").exists()
        or AbsenceActionLog.objects.filter(pk__in=action_ids)
        .filter(
            models.Q(excuse__isnull=False)
            | models.Q(corrects__isnull=False)
            | models.Q(acted_by__isnull=False)
        )
        .exists()
    ):
        raise EntryError(
            "erasure_incomplete", "بقيت بياناتٌ شخصيّةٌ في سجلّات المتابعة — أُلغيت المعاملة."
        )
    counts = {"contacts": len(contact_ids), "actions": len(action_ids)}
    if contact_ids or action_ids:
        AuditLog.log(
            user=actor,
            action="update",
            model_name="other",
            object_id=student.pk,
            object_repr="متابعةُ الغياب — تجهيلُ سجلّ طالبٍ بالمحو (PDPPL م.18)",
            changes=counts,
            school=school,
        )
    return counts


def wing_choices(school: Any) -> list[tuple[Any, str]]:
    """أجنحةُ المدرسة (المعرّف والاسم) لقائمة التصفية."""
    return list(Wing.objects.filter(school=school).order_by("code").values_list("id", "name"))


def view_query(grade: str, wing: str, followup: str, sort: str) -> str:
    """سلسلةُ الاستعلام التي تحمل تصفيةَ الشاشة وفرزَها إلى الطباعة والعودة."""
    pairs = (("grade", grade), ("wing", wing), ("followup", followup), ("sort", sort))
    return urlencode({k: v for k, v in pairs if v})

"""نقلُ عملٍ من قاعدة المعاينة (8500) إلى الإنتاج بالمفتاح الطبيعيّ — لا بمعرّفٍ يختلف بين القاعدتين.

    Preview(Django default DB) → dump → JSON → apply → Production(Django default DB)

عملٌ أنجزه المالكُ على 8500 ظنّاً منه أنّه الإنتاج (طلبُ «مايسترو إدارة الجلسات»، 2026-09-27):
`SubjectClassAssignment` (الإسنادُ) و`TeacherWorkloadPlan` (خطّةُ النصاب). القاعدتان مستقلّتان، وUUID
كلٍّ منهما محليٌّ لا يعبر — فالمطابقةُ بالمفتاح الطبيعيّ: المعلّمُ بـ`national_id_hmac` أو `employee_number`
(لا بالرقم الشخصيّ الصريح قطّ — PDPPL)، والمدرسةُ برمزها، والشعبةُ بـ(صفّ، شعبة، عام) داخل مدرستها،
والمادّةُ برمزها داخل مدرستها.

هذه الوحدةُ قراءةٌ وتحويلٌ فقط. الكتابةُ الفعليّةُ في `apply_preview_workload_changes` عبر خدمتَي المنصّة
القائمتين (`assignment_services.apply_assignment`، `workload_workflow`) — لا عبر `save()` مباشرةً، فتبقى
الحراسةُ والتدقيقُ كما لكلّ تعديلٍ آخر.

**ما لا يعبر (D-167م، W-20261003-023):** حساباتُ المعاينة الدائمةُ (`core/preview_accounts.py`: بادئةُ الاسم «[وهميّ» **و**الرقم `PV-`)
تبقى على 8500: `dump` يُسقط صفوفَ معلّمٍ موسومٍ (`exclude_preview_teachers`)، و`apply` يرفض ملفّاً يحمل مفتاحاً خارج قائمة السماح
(`INJECTABLE_KEYS`: إسنادٌ وخطّةُ نصابٍ لا غير) أو صفّاً معلّمُه موسوم برقمه الوظيفيّ `PV-…` (`injection_violations`) قبل أيّ كتابة. وعلى هذا فتعليقُ «لا
بياناتٍ شخصيّةً في الملفّ» يعني: الـHMAC والرقمُ الوظيفيّ للمطابقة وحدَها، **ولا حسابَ وهميّاً** مهما بلغ الدمقُ.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.models import ClassGroup, CustomUser, School
from core.preview_accounts import ID_PREFIX, ROLES, preview_accounts_q
from operations.models import Subject, SubjectClassAssignment

from .models import TeacherWorkloadPlan

#: قائمةُ سماحٍ بما يعبر 8500 → الإنتاج (حكمُ 0105 ب-٢): مفاتيحُ الملفّ هذه وحدَها — نموذجان معرَّفان لا غير. مفتاحٌ آخرُ يرفضه
#: `injection_violations` فلا يُقبل ملفٌّ يحمل مستخدمين أو عضويّاتٍ أو أيَّ صنفٍ لم يُسمَّ هنا.
INJECTABLE_KEYS = frozenset({"since", "assignments", "workload_plans"})


class ReconciliationError(Exception):
    """تعذّرت المطابقةُ أو الحلّ — يُذكر بلا تخمين."""


def exclude_preview_teachers(queryset):
    """يُسقط من الدمق كلَّ صفٍّ معلّمُه حسابُ معاينةٍ وهميّ (الوسمُ المركَّب) — «الحساباتُ كلُّها على المحلّيّ ولا تُحقن في الإنتاج»."""
    return queryset.exclude(preview_accounts_q("teacher__"))


def _preview_hmacs() -> set[str]:
    """بصماتُ أرقام الدخول الاصطناعيّة `PV-…` — محسوبةٌ بسرّ هذه البيئة نفسِه (الحتميُّ في كلّ البيئات)."""
    from core.models.crypto import hmac_field  # لا يُستورد في الرأس: يتبع إعداداتِ التشفير

    return {hmac_field(national_id) for national_id in ROLES.values()}


def injection_violations(payload: dict[str, Any]) -> list[str]:
    """ما يمنع قبولَ ملفّ حقنٍ على هذه القاعدة (الإنتاجُ عادةً): مفتاحٌ خارج `INJECTABLE_KEYS`، أو صفٌّ معلّمُه حسابُ معاينة.

    يُفحص قبل أيّ كتابةٍ في `apply_preview_workload_changes` ولو بلا `--apply`. **الساقُ الفاعلةُ هي الرقمُ الوظيفيّ بالبادئة `PV-`**
    (`preview_accounts` يضبط `employee_number=PV-<الدور>` لكلّ حساب، ولا يحمل الملفُّ الاسمَ). أمّا مطابقةُ البصمة فلا تصحّ إلّا إن اتّحد
    مفتاحُ HMAC بين البيئتين — وهو يختلف بين 8500 والإنتاج عادةً، فهي طبقةٌ إضافيّةٌ عند اتّحاده لا ضمانٌ؛ والحاجزُ الأوّلُ دائماً أنّ
    `dump` لا يُدمق الموسومين، ثمّ فشلُ `resolve_teacher` المغلق في الإنتاج لمعلّمٍ لا وجودَ له.
    """
    problems = [
        f"مفتاحٌ غيرُ مسموحٍ في ملفّ الحقن: «{key}»" for key in payload if key not in INJECTABLE_KEYS
    ]
    fake_hmacs = _preview_hmacs()
    for section in ("assignments", "workload_plans"):
        for index, row in enumerate(payload.get(section, []) or []):
            identity = (row.get("teacher_hmac") or "", row.get("teacher_employee_number") or "")
            if identity[0] in fake_hmacs or identity[1].startswith(ID_PREFIX):
                problems.append(f"{section}[{index}]: معلّمُه حسابُ معاينةٍ وهميّ — لا يُحقن في الإنتاج")
    return problems


def resolve_school(code: str) -> School:
    school = School.objects.filter(code=code).first()
    if school is None:
        raise ReconciliationError(f"لا مدرسةَ برمز «{code}».")
    return school


def resolve_teacher(*, national_id_hmac: str = "", employee_number: str = "") -> CustomUser:
    """لا يُستعمل `national_id` الصريحُ قطّ هنا — الـHMAC حتميٌّ بالسرّ نفسِه في كلّ البيئات."""
    if national_id_hmac:
        rows = list(CustomUser.objects.filter(national_id_hmac=national_id_hmac)[:2])
        if rows:
            if len(rows) > 1:
                raise ReconciliationError("أكثرُ من معلّمٍ بالبصمة نفسها — تصادمٌ لا يُحسَم آليّاً.")
            return rows[0]
    if employee_number:
        rows = list(CustomUser.objects.filter(employee_number=employee_number)[:2])
        if rows:
            if len(rows) > 1:
                raise ReconciliationError("أكثرُ من معلّمٍ بالرقم الوظيفيّ نفسه — تصادمٌ لا يُحسَم آليّاً.")
            return rows[0]
    raise ReconciliationError("لا معلّمَ يطابق بصمةَ الرقم الشخصيّ ولا الرقمَ الوظيفيّ في هذه القاعدة.")


def resolve_class_group(
    school: School, *, grade: str, section: str, academic_year: str
) -> ClassGroup:
    group = ClassGroup.objects.filter(
        school=school, grade=grade, section=section, academic_year=academic_year
    ).first()
    if group is None:
        raise ReconciliationError(
            f"لا شعبةَ {grade}/{section} في {school.code} للعام {academic_year}."
        )
    return group


def resolve_subject(school: School, code: str) -> Subject:
    rows = list(Subject.objects.filter(school=school, code=code)[:2])
    if not rows:
        raise ReconciliationError(f"لا مادّةَ برمز «{code}» في {school.code}.")
    if len(rows) > 1:
        raise ReconciliationError(f"أكثرُ من مادّةٍ برمز «{code}» في {school.code} — الرمزُ غيرُ فريد.")
    return rows[0]


def _teacher_identity(user: CustomUser | None) -> dict[str, str]:
    if user is None:
        return {"teacher_hmac": "", "teacher_employee_number": ""}
    return {
        "teacher_hmac": user.national_id_hmac or "",
        "teacher_employee_number": user.employee_number or "",
    }


# ══════════════════════════════════════════════════════════════════════
#  التسليسل (الدَّمْقُ) — من كائنات القاعدة إلى قواميسَ قابلةٍ لِـJSON
# ══════════════════════════════════════════════════════════════════════


def dump_assignment(row: SubjectClassAssignment) -> dict[str, Any]:
    return {
        "school_code": row.school.code,
        "academic_year": row.academic_year,
        "grade": row.class_group.grade,
        "section": row.class_group.section,
        "subject_code": row.subject.code,
        **_teacher_identity(row.teacher),
        "weekly_periods": row.weekly_periods,
        "requires_lab": row.requires_lab,
        "parallel_group": row.parallel_group,
        "periods_override_reason": row.periods_override_reason,
        "is_active": row.is_active,
        "updated_at": row.updated_at.isoformat(),
    }


def dump_workload_plan(row: TeacherWorkloadPlan) -> dict[str, Any]:
    return {
        "school_code": row.school.code,
        "academic_year": row.academic_year,
        "plan_version": row.plan_version,
        **_teacher_identity(row.teacher),
        "required_weekly_periods": row.required_weekly_periods,
        "required_source_kind": row.required_source_kind,
        "required_source_reference": row.required_source_reference,
        "required_policy_key": row.required_policy_key,
        "reduction_periods": row.reduction_periods,
        "reduction_reason": row.reduction_reason,
        "reduction_source": row.reduction_source,
        "reduction_source_reference": row.reduction_source_reference,
        "status": row.status,
        "updated_at": row.updated_at.isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════
#  الحلّ — من قاموسٍ مُستوردٍ إلى كائنات القاعدة الحاليّة (الإنتاج عادةً)
# ══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ResolvedAssignment:
    school: School
    class_group: ClassGroup
    subject: Subject
    teacher: CustomUser | None
    data: dict[str, Any]


def resolve_assignment(data: dict[str, Any]) -> ResolvedAssignment:
    school = resolve_school(data["school_code"])
    group = resolve_class_group(
        school,
        grade=data["grade"],
        section=data["section"],
        academic_year=data["academic_year"],
    )
    subject = resolve_subject(school, data["subject_code"])
    teacher = (
        resolve_teacher(
            national_id_hmac=data.get("teacher_hmac", ""),
            employee_number=data.get("teacher_employee_number", ""),
        )
        if data.get("teacher_hmac") or data.get("teacher_employee_number")
        else None
    )
    return ResolvedAssignment(school, group, subject, teacher, data)


@dataclass(frozen=True)
class ResolvedPlan:
    school: School
    teacher: CustomUser
    data: dict[str, Any]


def resolve_plan(data: dict[str, Any]) -> ResolvedPlan:
    school = resolve_school(data["school_code"])
    teacher = resolve_teacher(
        national_id_hmac=data.get("teacher_hmac", ""),
        employee_number=data.get("teacher_employee_number", ""),
    )
    return ResolvedPlan(school, teacher, data)

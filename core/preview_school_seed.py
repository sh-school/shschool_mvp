"""بذرُ المدرسة الوهميّة الثانية — متساوي الأثر، على قاعدة المعاينة وحدَها (W-20261004-006).

يُستدعى من الأمر `seed_preview_school` الذي يتحقّق من بيئة المعاينة قبل أيّ لمس. يبذر: المدرسةَ (`PVS`)، والأدوارَ الاثنى عشر
حساباً بعضويّةٍ واحدةٍ نشطةٍ بلا superuser ولا is_staff، وجناحين وشُعباً وطلبةً.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from core.academic_calendar import academic_year_for_school
from core.models import (
    AuditLog,
    ClassGroup,
    CustomUser,
    Membership,
    Role,
    School,
    StudentEnrollment,
    Wing,
)
from core.preview_accounts import EMAIL_PREFIX, FULL_NAME_PREFIX
from core.preview_school import (
    EMPLOYEE_NUMBERS,
    FORBIDDEN_ROLES,
    GRADES,
    ROLES,
    SCHOOL_CODE,
    SCHOOL_NAME,
    SECTIONS,
    STUDENTS_PER_CLASS,
    WINGS,
)


@dataclass
class SeedResult:
    accounts_created: int = 0
    accounts_fixed: int = 0
    classes: int = 0
    students: int = 0


def seed(password: str) -> SeedResult:
    """يبذر المدرسةَ الثانيةَ كاملةً؛ إعادةُ التشغيل لا تُضيف شيئاً."""
    known = {name for name, _ in Role.ROLES}
    for role_name in ROLES:
        if role_name in FORBIDDEN_ROLES or role_name not in known:
            raise ValueError(f"دورٌ غيرُ مسموحٍ في قائمة المدرسة الثانية: {role_name}")
    result = SeedResult()
    with transaction.atomic():
        school, _ = School.objects.get_or_create(
            code=SCHOOL_CODE, defaults={"name": SCHOOL_NAME, "is_active": True}
        )
        if school.name != SCHOOL_NAME or not school.is_active:
            school.name, school.is_active = SCHOOL_NAME, True
            school.save()
        _seed_accounts(school, password, result)
        _seed_structure(school, result)
    return result


def _seed_accounts(school: School, password: str, result: SeedResult) -> None:
    for role_name, nid in ROLES.items():
        holder = (
            CustomUser.objects.filter(employee_number=EMPLOYEE_NUMBERS[role_name])
            .exclude(national_id=nid)
            .first()
        )
        if holder is not None:
            raise ValueError("رقمٌ وظيفيٌّ من نطاق المدرسة الثانية ممسوكٌ لحسابٍ آخر")
        existing = CustomUser.objects.filter(national_id=nid).first()
        is_new = existing is None
        user = existing if existing is not None else CustomUser(national_id=nid)
        wanted = {
            "full_name": f"{FULL_NAME_PREFIX}{role_name} (مدرسة 2)",
            "employee_number": EMPLOYEE_NUMBERS[role_name],
            "email": f"{EMAIL_PREFIX}s2_{role_name}@preview.invalid",
            "is_active": True,
            "is_staff": False,
            "is_superuser": False,
            "must_change_password": False,
        }
        drift = [k for k, v in wanted.items() if getattr(user, k) != v]
        for key, value in wanted.items():
            setattr(user, key, value)
        user.set_password(password)
        user.save()
        role, _ = Role.objects.get_or_create(school=school, name=role_name)
        Membership.objects.get_or_create(
            user=user, school=school, role=role, defaults={"is_active": True}
        )
        Membership.objects.filter(user=user, school=school, role=role).update(is_active=True)
        stray = (
            Membership.objects.filter(user=user)
            .exclude(school=school, role=role)
            .update(is_active=False)
        )
        if is_new:
            result.accounts_created += 1
        elif drift or stray:
            result.accounts_fixed += 1
        if is_new or drift or stray:
            AuditLog.log(
                user=None,
                action="create" if is_new else "update",
                model_name="other",
                object_id=user.pk,
                object_repr="حسابُ مدرسة المعاينة الثانية",
                changes={"role": role_name, "drift": drift, "stray_memberships": stray},
                school=school,
            )


def _seed_structure(school: School, result: SeedResult) -> None:
    year = academic_year_for_school(school)
    supervisor = CustomUser.objects.get(national_id=ROLES["admin_supervisor"])
    student_role, _ = Role.objects.get_or_create(school=school, name="student")
    wings = []
    for index, (code, name) in enumerate(WINGS):
        wing, _ = Wing.objects.get_or_create(
            school=school,
            code=code,
            academic_year=year,
            defaults={
                "name": f"{FULL_NAME_PREFIX}{name}",
                "supervisor": supervisor if index == 0 else None,
            },
        )
        wings.append(wing)
    for gi, grade in enumerate(GRADES):
        for si, section in enumerate(SECTIONS):
            cg, created = ClassGroup.objects.get_or_create(
                school=school,
                grade=grade,
                section=section,
                track="general",
                defaults={"academic_year": year, "wing": wings[si % len(wings)]},
            )
            result.classes += int(created)
            for i in range(1, STUDENTS_PER_CLASS + 1):
                student, s_new = CustomUser.objects.get_or_create(
                    national_id=f"PV-s2-st-{gi}{si}{i:02d}",
                    defaults={"full_name": f"{FULL_NAME_PREFIX}طالب {grade}-{section}-{i}"},
                )
                result.students += int(s_new)
                Membership.objects.get_or_create(
                    user=student, school=school, role=student_role, defaults={"is_active": True}
                )
                StudentEnrollment.objects.get_or_create(student=student, class_group=cg)

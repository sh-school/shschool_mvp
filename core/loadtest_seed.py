"""بذرُ مدرسةٍ لاختبار الحمل — طلبةٌ بحجمٍ وحساباتٌ متعدّدة (W-20261027-036، سواط 017 توصية 13).

يُستدعى من الأمر `seed_loadtest` الذي يتحقّق من البيئة قبل أيّ لمس. يبذر مدرسةً مستقلّةً (`LDT`) فيها جناحٌ وشُعبٌ وطلبةٌ
بعضويّةٍ وتسجيل، وحساباتِ موظّفين بأدوارٍ متعدّدة لقياس Locust بحسابٍ لكلّ مستخدمٍ افتراضيّ بدل حسابٍ مشترك.

متساوي الأثر: إعادةُ التشغيل لا تُضيف شيئاً. بلا رقمٍ وظيفيّ للحسابات فلا تصطدم بنطاق المعاينة المحجوز.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction

from core.academic_calendar import academic_year_for_school
from core.models import ClassGroup, CustomUser, Membership, Role, School, StudentEnrollment, Wing
from core.preview_accounts import PRODUCTION_SETTINGS_MODULES

SCHOOL_CODE = "LDT"
SCHOOL_NAME = "[حمل] مدرسة اختبار الحمل"
#: رقمُ الدخول (حدُّ الحقل 20 خانة): طلبةٌ `LT-st-00001` وموظّفون `LT-u-001`.
STUDENT_PREFIX = "LT-st-"
STAFF_PREFIX = "LT-u-"
#: دورُ الحسابات: المديرُ وحدَه يقرأ واجهات الحضور والدرجات كلَّها (نائبا المدير يُرفضان 403 على بعضها فيُقاس الدورُ لا السعة).
STAFF_ROLES = ("principal",)
GRADES = ("G7", "G8", "G9")
STUDENTS_PER_CLASS = 30
DEFAULT_STUDENTS = 1000
DEFAULT_ACCOUNTS = 20
MAX_STUDENTS = 20000
MAX_ACCOUNTS = 500


@dataclass
class SeedResult:
    students: int = 0
    classes: int = 0
    accounts: int = 0


def environment_problems() -> list[str]:
    """أسبابُ رفض البذر قبل لمس القاعدة: إنتاجٌ أو قاعدةُ المعاينة."""
    problems = []
    if str(getattr(settings, "SETTINGS_MODULE", "")) in PRODUCTION_SETTINGS_MODULES:
        problems.append("إعدادُ إنتاجٍ أو staging")
    preview_db = os.environ.get("PREVIEW_DB_NAME", "")
    if preview_db and str(settings.DATABASES["default"].get("NAME", "")) == preview_db:
        problems.append("قاعدةُ المعاينة (8500) لا تُبذر بطلبة الحمل")
    return problems


def seed(
    password: str, students: int = DEFAULT_STUDENTS, accounts: int = DEFAULT_ACCOUNTS
) -> SeedResult:
    """يبذر مدرسة الحمل؛ يرمي ValueError عند عددٍ خارج الحدّ."""
    if not 1 <= students <= MAX_STUDENTS:
        raise ValueError(f"عددُ الطلبة بين 1 و{MAX_STUDENTS}")
    if not 1 <= accounts <= MAX_ACCOUNTS:
        raise ValueError(f"عددُ الحسابات بين 1 و{MAX_ACCOUNTS}")
    result = SeedResult()
    with transaction.atomic():
        school, _ = School.objects.get_or_create(
            code=SCHOOL_CODE, defaults={"name": SCHOOL_NAME, "is_active": True}
        )
        year = academic_year_for_school(school)
        wing, _ = Wing.objects.get_or_create(
            school=school, code="ldt", academic_year=year, defaults={"name": "[حمل] جناح"}
        )
        _seed_students(school, wing, year, students, result)
        _seed_accounts(school, password, accounts, result)
    return result


def _seed_students(school: School, wing: Wing, year, count: int, result: SeedResult) -> None:
    student_role, _ = Role.objects.get_or_create(school=school, name="student")
    class_count = math.ceil(count / STUDENTS_PER_CLASS)
    groups = []
    for index in range(class_count):
        grade = GRADES[index % len(GRADES)]
        section = str(index // len(GRADES) + 1)
        group, created = ClassGroup.objects.get_or_create(
            school=school,
            grade=grade,
            section=section,
            track="general",
            defaults={"academic_year": year, "wing": wing},
        )
        result.classes += int(created)
        groups.append(group)
    for number in range(1, count + 1):
        student, created = CustomUser.objects.get_or_create(
            national_id=f"{STUDENT_PREFIX}{number:05d}",
            defaults={"full_name": f"[حمل] طالب {number}"},
        )
        if created:
            student.set_unusable_password()
            student.save(update_fields=["password"])
            result.students += 1
        Membership.objects.get_or_create(
            user=student, school=school, role=student_role, defaults={"is_active": True}
        )
        StudentEnrollment.objects.get_or_create(
            student=student, class_group=groups[(number - 1) // STUDENTS_PER_CLASS]
        )


def _seed_accounts(school: School, password: str, count: int, result: SeedResult) -> None:
    known = {name for name, _ in Role.ROLES}
    roles = {}
    for name in STAFF_ROLES:
        if name not in known:
            raise ValueError(f"دورٌ غيرُ معروف: {name}")
        roles[name], _ = Role.objects.get_or_create(school=school, name=name)
    for number in range(1, count + 1):
        role = roles[STAFF_ROLES[(number - 1) % len(STAFF_ROLES)]]
        user, created = CustomUser.objects.get_or_create(
            national_id=f"{STAFF_PREFIX}{number:03d}",
            defaults={"full_name": f"[حمل] موظّف {number}", "must_change_password": False},
        )
        if created:
            user.set_password(password)
            user.save()
            result.accounts += 1
        Membership.objects.get_or_create(
            user=user, school=school, role=role, defaults={"is_active": True}
        )
        Membership.objects.filter(user=user, school=school, role=role).update(is_active=True)
        Membership.objects.filter(user=user, school=school).exclude(role=role).update(
            is_active=False
        )

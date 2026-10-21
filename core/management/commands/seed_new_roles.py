"""
seed_new_roles.py
══════════════════════════════════════════════════════════════════════
ينشئ الأدوار الجديدة لكل مدرسة موجودة، ثم **كلَّ اسمٍ في ``Role.ROLES``** (W-20261019-008):
دورٌ جديدٌ في القائمة بلا صفٍّ للمدرسة يُسقط تعيينَه على دورٍ قريبٍ فتفرغ صفحاتُ صاحبه.
يُشغَّل مرة واحدة بعد تطبيق الـ migration.

Usage:
    python manage.py seed_new_roles --settings=shschool.settings.development
══════════════════════════════════════════════════════════════════════
"""

from django.core.management.base import BaseCommand

from core.models import Role, School

NEW_ROLES = [
    "admin_supervisor",
    "social_worker",
    "psychologist",
    "academic_advisor",
    "ese_teacher",
    "it_technician",
    "secretary",
    "e_projects_coordinator",  # 2026-09 — المسمّى الوزاريّ منسّق المشاريع الإلكترونية
]


def all_role_names() -> list[str]:
    """الأدوارُ الجديدة ثمّ كلُّ اسمٍ في ``Role.ROLES`` بلا تكرار وبترتيبٍ ثابت."""
    return list(dict.fromkeys([*NEW_ROLES, *(name for name, _label in Role.ROLES)]))


class Command(BaseCommand):
    help = "ينشئ الأدوار الوظيفية الجديدة (كلّ أسماء Role.ROLES) لكل مدرسة"

    def handle(self, *args, **options):
        schools = School.objects.all()
        if not schools.exists():
            self.stdout.write(self.style.WARNING("لا توجد مدارس — تخطّي"))
            return

        created_count = 0
        for school in schools:
            for role_name in all_role_names():
                _, created = Role.objects.get_or_create(
                    school=school,
                    name=role_name,
                )
                if created:
                    created_count += 1
                    self.stdout.write(self.style.SUCCESS(f"  [OK] {role_name} -> {school.code}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"\n[DONE] Created {created_count} new roles for {schools.count()} school(s)"
            )
        )

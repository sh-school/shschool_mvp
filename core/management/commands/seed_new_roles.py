"""
seed_new_roles.py
══════════════════════════════════════════════════════════════════════
ينشئ الأدوار الجديدة (5+2) لكل مدرسة موجودة.
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
]


class Command(BaseCommand):
    help = "ينشئ الأدوار الوظيفية الجديدة (7 أدوار) لكل مدرسة"

    def handle(self, *args, **options):
        schools = School.objects.all()
        if not schools.exists():
            self.stdout.write(self.style.WARNING("لا توجد مدارس — تخطّي"))
            return

        created_count = 0
        for school in schools:
            for role_name in NEW_ROLES:
                _, created = Role.objects.get_or_create(
                    school=school, name=role_name,
                )
                if created:
                    created_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"  [OK] {role_name} -> {school.code}")
                    )

        self.stdout.write(
            self.style.SUCCESS(f"\n[DONE] Created {created_count} new roles for {schools.count()} school(s)")
        )

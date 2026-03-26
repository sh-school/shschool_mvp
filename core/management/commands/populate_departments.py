"""
Management command: Create 13 Department records + link Memberships.
Usage: python manage.py populate_departments
"""

import io

from django.core.management.base import BaseCommand

from core.models import CustomUser, Department, Membership, School


class Command(BaseCommand):
    help = "Create 13 academic departments and link existing Memberships to FK"

    def handle(self, *args, **options):
        out = io.open(
            r"D:\shschool_mvp\_dept_migration_log.txt", "w", encoding="utf-8"
        )

        def log(msg):
            out.write(msg + "\n")
            out.flush()
            self.stdout.write(msg)

        # ══════════════════════════════════════════════════════════
        # 1. Department definitions
        # ══════════════════════════════════════════════════════════

        DEPARTMENTS = [
            ("math", "الرياضيات", 1),
            ("arabic", "اللغة العربية", 2),
            ("english", "اللغة الإنجليزية", 3),
            ("social", "الدراسات الاجتماعية", 4),
            ("islamic", "التربية الإسلامية", 5),
            ("pe", "التربية البدنية", 6),
            ("science", "العلوم", 7),
            ("biology", "الأحياء", 8),
            ("tech", "التكنولوجيا", 9),
            ("art", "الفنون البصرية", 10),
            ("chemistry", "الكيمياء", 11),
            ("physics", "الفيزياء", 12),
            ("life_skills", "المهارات الحياتية والمهنية", 13),
        ]

        # ══════════════════════════════════════════════════════════
        # 2. Get the school
        # ══════════════════════════════════════════════════════════

        school = School.objects.first()
        if not school:
            log("ERROR: No school found!")
            out.close()
            return

        log(f"School: {school.name} ({school.code})")
        log("=" * 60)

        # ══════════════════════════════════════════════════════════
        # 3. Create Department records + find coordinators
        # ══════════════════════════════════════════════════════════

        created_count = 0
        existing_count = 0
        dept_map = {}  # name_ar -> Department object

        for code, name_ar, sort_order in DEPARTMENTS:
            # Find coordinator from Membership
            coord_membership = (
                Membership.objects.filter(
                    school=school,
                    is_active=True,
                    department=name_ar,
                    role__name="coordinator",
                )
                .select_related("user")
                .first()
            )
            head = coord_membership.user if coord_membership else None

            dept, created = Department.objects.get_or_create(
                school=school,
                code=code,
                defaults={
                    "name": name_ar,
                    "head": head,
                    "sort_order": sort_order,
                    "is_active": True,
                },
            )
            # Update head if dept already exists but head changed
            if not created and head and dept.head != head:
                dept.head = head
                dept.save(update_fields=["head"])

            dept_map[name_ar] = dept

            if created:
                created_count += 1
                head_name = head.full_name if head else "-- no coordinator --"
                log(f"  CREATED: {name_ar} ({code}) -> head: {head_name}")
            else:
                existing_count += 1
                log(f"  EXISTS:  {name_ar} ({code})")

        log(f"\nDepartments: {created_count} created, {existing_count} existed")
        log("=" * 60)

        # ══════════════════════════════════════════════════════════
        # 4. Link Memberships to Department FK
        # ══════════════════════════════════════════════════════════

        linked_count = 0
        skipped_count = 0
        not_found_count = 0

        memberships_with_dept = Membership.objects.filter(
            school=school, is_active=True
        ).exclude(department="")

        for m in memberships_with_dept:
            if m.department_obj_id:
                skipped_count += 1
                continue

            dept = dept_map.get(m.department)
            if dept:
                m.department_obj = dept
                m.save(update_fields=["department_obj"])
                linked_count += 1
            else:
                not_found_count += 1
                log(
                    f"  WARNING: No department for '{m.department}' "
                    f"-> {m.user.full_name}"
                )

        log(f"\nMemberships linked: {linked_count}")
        log(f"Already linked (skipped): {skipped_count}")
        log(f"Not found: {not_found_count}")
        log("=" * 60)

        # ══════════════════════════════════════════════════════════
        # 5. Verify
        # ══════════════════════════════════════════════════════════

        log("\n--- VERIFICATION ---")
        for dept in Department.objects.filter(school=school).order_by("sort_order"):
            member_count = dept.memberships.filter(is_active=True).count()
            head_name = dept.head.full_name if dept.head else "-- no coordinator --"
            log(f"  {dept.name} ({dept.code}): {member_count} members -> {head_name}")

        total_linked = Membership.objects.filter(
            school=school, is_active=True, department_obj__isnull=False
        ).count()
        total_with_dept = (
            Membership.objects.filter(school=school, is_active=True)
            .exclude(department="")
            .count()
        )

        log(f"\nTotal linked to FK: {total_linked} / {total_with_dept}")
        log("DONE!")
        out.close()
        self.stdout.write(self.style.SUCCESS("Migration complete!"))

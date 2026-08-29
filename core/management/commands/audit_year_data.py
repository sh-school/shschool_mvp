"""
تدقيقٌ للقراءة فقط على بيانات عامٍ دراسيّ — قبل الترفيع لا بعده.

يُشغَّل قبل إنشاء شُعب العام الجديد، ليُعرف **ما الذي يُرفَّع منه**: كم شعبة،
وكم طالباً في كلٍّ منها، ومَن بلا تسجيل، ومَن سُجِّل مرّتين، وأيّ شعبةٍ خالية.

ولا يكتب شيئاً. `--year` اختياريّ، وبدونه يُشتقّ العام الجاري من التقويم.
"""

from collections import Counter, defaultdict

from django.core.management.base import BaseCommand

from core.academic_calendar import academic_year_for_school
from core.models import ClassGroup, Membership, School, StudentEnrollment


class Command(BaseCommand):
    help = "تدقيق قراءةٍ على شُعب عامٍ دراسيّ وتسجيلات طلابه"

    def add_arguments(self, parser):
        parser.add_argument("--year", default=None, help="مثال: 2025-2026")
        parser.add_argument("--school", default=None, help="كود المدرسة")

    def handle(self, *args, **options):
        school = self._school(options["school"])
        if school is None:
            self.stderr.write("لا مدرسة بهذا الكود.")
            return

        year = options["year"] or academic_year_for_school(school)
        self.stdout.write(f"\n{school.name} · العام {year}")
        self.stdout.write("═" * 60)

        groups = list(
            ClassGroup.objects.filter(school=school, academic_year=year).order_by(
                "grade", "section"
            )
        )
        if not groups:
            self.stdout.write("لا شُعب لهذا العام.")
            return

        self._sections(groups)
        self._students(school, year, groups)
        self._anomalies(school, year, groups)

    # ── الأقسام ──────────────────────────────────────────────────────

    def _school(self, code):
        if code:
            return School.objects.filter(code=code).first()
        return School.objects.first()

    def _sections(self, groups):
        self.stdout.write(f"\nالشُّعب — {len(groups)}")
        by_grade = defaultdict(list)
        for g in groups:
            by_grade[g.grade].append(g)

        for grade in sorted(by_grade, key=lambda x: int("".join(c for c in x if c.isdigit()))):
            items = by_grade[grade]
            num = "".join(c for c in grade if c.isdigit())
            names = ", ".join(
                f"{num}/{g.section}" + (f" ({g.get_track_display()})" if g.track else "")
                for g in items
            )
            inactive = sum(1 for g in items if not g.is_active)
            note = f"  [{inactive} غير نشطة]" if inactive else ""
            self.stdout.write(f"  {grade:4} ({len(items):2}) {names}{note}")

    def _students(self, school, year, groups):
        counts = Counter(
            StudentEnrollment.objects.filter(class_group__in=groups, is_active=True).values_list(
                "class_group_id", flat=True
            )
        )
        total = sum(counts.values())
        self.stdout.write(f"\nالتسجيلات النشطة — {total}")
        for g in groups:
            num = "".join(c for c in g.grade if c.isdigit())
            n = counts.get(g.id, 0)
            flag = "  ← خالية" if n == 0 else ""
            self.stdout.write(f"  {num}/{g.section:4} {n:4}{flag}")

    def _anomalies(self, school, year, groups):
        self.stdout.write("\nما يستحقّ النظر")

        student_role_ids = set(
            Membership.objects.filter(
                school=school, is_active=True, role__name="student"
            ).values_list("user_id", flat=True)
        )
        enrolled = set(
            StudentEnrollment.objects.filter(class_group__in=groups, is_active=True).values_list(
                "student_id", flat=True
            )
        )

        unenrolled = student_role_ids - enrolled
        self.stdout.write(f"  طلاب بلا تسجيل في هذا العام : {len(unenrolled)}")

        # تسجيلٌ نشطٌ مزدوج — القيد يمنعه، ووجوده يعني خللاً في البيانات
        dupes = [
            sid
            for sid, n in Counter(
                StudentEnrollment.objects.filter(is_active=True).values_list(
                    "student_id", flat=True
                )
            ).items()
            if n > 1
        ]
        self.stdout.write(f"  طلاب بتسجيلين نشطين أو أكثر  : {len(dupes)}")

        empty = sum(
            1
            for g in groups
            if not StudentEnrollment.objects.filter(class_group=g, is_active=True).exists()
        )
        self.stdout.write(f"  شُعب خالية                   : {empty}")

        tracked = [g for g in groups if g.grade in ClassGroup.TRACKED_GRADES]
        without = [g for g in tracked if not g.track]
        self.stdout.write(f"  شُعب ١١/١٢ بلا مسار          : {len(without)} من {len(tracked)}")

        other_years = ClassGroup.objects.filter(school=school).exclude(academic_year=year)
        if other_years.exists():
            years = sorted(set(other_years.values_list("academic_year", flat=True)))
            self.stdout.write(f"\n  أعوامٌ أخرى في القاعدة: {', '.join(years)}")
            self.stdout.write("  (استعلامٌ لا يُقيَّد بالعام يخلطها بهذا العام — راجع #89)")
        self.stdout.write("")

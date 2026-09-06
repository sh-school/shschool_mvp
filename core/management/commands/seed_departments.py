"""تسجيلُ الأقسام في القاعدة، وربطُ كلّ معلّمٍ بقسمه.

    DerivedDepartment → RegisteredDepartment      (مرّةً واحدة)

كان جدولُ الأقسام فارغاً، فكانت الشاشاتُ تشتقّ قسمَ المعلّم من الغالب على
حصصه في كلّ طلب. والاشتقاقُ حلٌّ لا مصدر: يتبدّل بتبدّل الجدول، ولا يحمل
قراراً إداريّاً كإلحاق معلّم إدارة الأعمال بقسم الكيمياء. فيُكتب مرّةً
ويصير السجلُّ هو المرجع.

## قراران إداريّان مثبَّتان

  ١. معلّمُ إدارة الأعمال يتبع **قسم الكيمياء** إداريّاً (قرارُ مدير المدرسة
     2026-09-06) — فلا يُنشأ له قسمٌ برجلٍ واحد.
  ٢. العلومُ قسمان بالمرحلة: «العلوم — إعدادي» و«العلوم — ثانوي» (يضمّ الأحياءَ
     والعلومَ العامّة)، والكيمياءُ والفيزياءُ قسمان مستقلّان.

## متعادلٌ ولا يكتب إلّا بأمر

يُطبع التقريرُ أوّلاً ولا تُمسّ القاعدةُ إلّا بـ`--apply`، فبذرةٌ خاطئةٌ تصير
مرجعاً تُقاس عليه السنةُ كلُّها. وتشغيلُه مرّتين لا يُنشئ قسماً ثانياً ولا
يُبدّل رابطاً صحيحاً.

    python manage.py seed_departments --year 2026-2027
    python manage.py seed_departments --year 2026-2027 --apply
"""

from collections import Counter, defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.academic_calendar import academic_year_for_school
from core.models import Department, Membership, School
from operations import departments as dept_map
from operations.models import SubjectClassAssignment

#: من يُنسب إلى قسم — الأدوارُ التي تُدرّس.
TEACHING_ROLES = ("teacher", "ese_teacher", "coordinator", "e_projects_coordinator")

#: قراراتُ الإلحاق الإداريّ: قسمٌ مشتقٌّ ← القسمُ الذي يتبعه فعلاً.
#: إدارةُ الأعمال معلّمٌ واحدٌ يتبع الكيمياءَ إداريّاً (قرارُ المدير 2026-09-06).
ATTACHED_TO = {"business": "chemistry"}


class Command(BaseCommand):
    help = "يسجّل الأقسام الأكاديميّة ويربط كلَّ معلّمٍ بقسمه — بلا كتابةٍ إلّا بـ--apply"

    def add_arguments(self, parser):
        parser.add_argument("--school", default="", help="رمزُ المدرسة — والافتراضُ الأولى")
        parser.add_argument("--year", default="", help="العامُ الدراسيّ — والافتراضُ الجاري")
        parser.add_argument("--apply", action="store_true", help="اكتب التغييرات")

    def handle(self, *args, **options):
        school = self._school(options["school"])
        year = options["year"] or academic_year_for_school(school)
        apply = options["apply"]

        placements = self._placements(school, year)
        if not placements:
            raise CommandError("لا معلّمين نشطين في هذه المدرسة — لا شيءَ يُسجَّل.")

        needed = sorted({code for code, _ in placements.values()}, key=_order)
        self.stdout.write(f"المدرسة: {school.name} · العام: {year}")
        self.stdout.write(f"الأقسامُ المطلوبة: {len(needed)} · المعلّمون: {len(placements)}")

        per_department = defaultdict(list)
        for user, (code, why) in placements.items():
            per_department[code].append((user, why))

        for code in needed:
            members = per_department[code]
            self.stdout.write(f"\n  {dept_map.DEPARTMENT_NAMES[code]} ({code}) — {len(members)}")
            for user, why in sorted(members, key=lambda m: m[0].full_name):
                self.stdout.write(f"      {user.full_name} — {why}")

        if not apply:
            self.stdout.write("\nتقريرٌ فقط — أضِف --apply للكتابة.")
            return

        created, linked, cleared = self._write(school, needed, placements)
        self.stdout.write(f"\nأُنشئ {created} قسماً، ورُبط {linked} معلّماً.")
        if cleared:
            self.stdout.write(
                f"وأُزيل القسمُ من {cleared} عضويّةٍ غيرِ تدريسيّة — القسمُ لعضويّة التدريس."
            )

    # ── القراءة ──────────────────────────────────────────────────────

    def _school(self, code):
        qs = School.objects.filter(code=code) if code else School.objects.all()
        school = qs.first()
        if school is None:
            raise CommandError(f"لا مدرسةَ بالرمز «{code}»." if code else "لا مدارسَ في القاعدة.")
        return school

    def _placements(self, school, year):
        """لكلّ معلّمٍ: رمزُ قسمه وسببُ نسبته إليه."""
        lessons = defaultdict(list)
        rows = (
            SubjectClassAssignment.objects.live(school, year=year)
            .filter(teacher__isnull=False)
            .select_related("subject", "class_group")
        )
        for row in rows:
            lessons[row.teacher_id].append(
                (row.subject.name_ar, row.class_group.grade, row.weekly_periods)
            )

        out = {}
        memberships = (
            Membership.objects.filter(school=school, is_active=True, role__name__in=TEACHING_ROLES)
            .select_related("user", "department_obj")
            .order_by("user__full_name")
        )
        for m in memberships:
            if m.user_id in out:
                continue
            mine = lessons.get(m.user_id, [])
            derived = dept_map.resolve_from_lessons(mine)
            attached = ATTACHED_TO.get(derived)
            if attached:
                why = f"{dept_map.DEPARTMENT_NAMES[derived]} — ملحقٌ إداريّاً بقرار المدير"
                derived = attached
            elif mine:
                counted = Counter()
                for name, grade, weight in mine:
                    if dept_map.department_of_subject(name, grade) == derived:
                        counted[derived] += weight
                total = sum(w for _n, _g, w in mine)
                why = f"{counted[derived]} من {total} حصّة"
            else:
                why = "لا حصصَ له — يُنسب إلى «غير محدَّد» حتّى يُسنَد"
            out[m.user] = (derived, why)
        return out

    # ── الكتابة ──────────────────────────────────────────────────────

    @transaction.atomic
    def _write(self, school, needed, placements):
        registry, created = {}, 0
        for code in needed:
            department, made = Department.objects.get_or_create(
                school=school,
                code=code,
                defaults={
                    "name": dept_map.DEPARTMENT_NAMES[code],
                    "sort_order": _order(code),
                },
            )
            registry[code] = department
            created += int(made)

        # القسمُ يخصّ عضويّةَ التدريس وحدَها. ومن له عضويّةٌ ثانيةٌ بدورٍ إداريّ
        # كان يُنسب مرّتين، فيصير عددُ القسم أكبرَ من عدد معلّميه.
        linked, cleared = 0, 0
        for user, (code, _why) in placements.items():
            mine = Membership.objects.filter(user=user, school=school, is_active=True)
            linked += int(
                bool(
                    mine.filter(role__name__in=TEACHING_ROLES)
                    .exclude(department_obj=registry[code])
                    .update(department_obj=registry[code])
                )
            )
            cleared += mine.exclude(role__name__in=TEACHING_ROLES).exclude(
                department_obj__isnull=True
            ).update(department_obj=None)

        # المنسّقُ رأسُ قسمه — يُقرأ من دوره لا يُكتب باليد.
        for code, department in registry.items():
            head = next(
                (
                    user
                    for user, (placed, _why) in placements.items()
                    if placed == code and user.get_role() == "coordinator"
                ),
                None,
            )
            if head is not None and department.head_id != head.id:
                department.head = head
                department.save(update_fields=["head"])
        return created, linked, cleared


def _order(code: str) -> int:
    return dept_map.DEPARTMENT_ORDER.get(code, len(dept_map.DEPARTMENTS))

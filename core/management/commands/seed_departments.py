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
from operations.departments import (
    TEACHING_ROLES,
    ExistingDepartments,
    free_conflicting_names,
)
from operations.models import SubjectClassAssignment

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

        plan = self._plan(school, needed)
        self._report_plan(plan)

        if not apply:
            self.stdout.write("\nتقريرٌ فقط — أضِف --apply للكتابة.")
            return

        created, linked, cleared = self._write(school, plan, placements)
        self.stdout.write(f"\nأُنشئ {created} قسماً، ورُبط {linked} معلّماً.")
        if cleared:
            self.stdout.write(f"وأُزيل القسمُ من {cleared} عضويّةٍ غيرِ تدريسيّة — القسمُ لعضويّة التدريس.")

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

    # ── التوفيق بين المطلوب والقائم ──────────────────────────────────

    def _plan(self, school, needed):
        """لكلّ قسمٍ مطلوب: أيُّ صفٍّ قائمٍ يتبنّاه، وما الذي يتبدّل فيه.

        ثلاثُ محاولاتٍ قبل الإنشاء — الرمزُ المعتمَد، فرمزُ الجيل الأوّل،
        فالاسمُ نفسُه. وما لم يُوجد بواحدةٍ منها فهو جديدٌ حقّاً.
        """
        existing = ExistingDepartments(Department.objects.filter(school=school))

        plan = []
        for code in needed:
            name, order = dept_map.DEPARTMENT_NAMES[code], _order(code)
            found = existing.adopt(code, name)
            changes = []
            if found is not None:
                if found.code != code:
                    changes.append(("الرمز", found.code, code))
                if found.name != name:
                    changes.append(("الاسم", found.name, name))
                if found.sort_order != order:
                    changes.append(("الترتيب", found.sort_order, order))
            plan.append(
                {
                    "code": code,
                    "name": name,
                    "order": order,
                    "department": found,
                    "changes": changes,
                }
            )
        return plan

    def _report_plan(self, plan):
        """ما يُنشأ وما يُبدَّل — يُقرأ قبل الكتابة لا بعدها."""
        fresh = [entry for entry in plan if entry["department"] is None]
        touched = [entry for entry in plan if entry["changes"]]
        kept = len(plan) - len(fresh) - len(touched)

        self.stdout.write("\nسجلُّ الأقسام:")
        self.stdout.write(f"  قائمٌ كما هو: {kept} · يُبدَّل: {len(touched)} · يُنشأ: {len(fresh)}")
        for entry in touched:
            was = entry["department"]
            self.stdout.write(f"    {was.name} ({was.code}):")
            for field, before, after in entry["changes"]:
                self.stdout.write(f"        {field}: {before} ← {after}")
        for entry in fresh:
            self.stdout.write(
                f"    جديد: {entry['name']} ({entry['code']}) — ترتيب {entry['order']}"
            )

    # ── الكتابة ──────────────────────────────────────────────────────

    @transaction.atomic
    def _write(self, school, plan, placements):
        registry, created = {}, 0
        free_conflicting_names(school, {e["name"]: e["department"] for e in plan})

        for entry in plan:
            department = entry["department"]
            if department is None:
                department = Department.objects.create(
                    school=school,
                    code=entry["code"],
                    name=entry["name"],
                    sort_order=entry["order"],
                )
                created += 1
            elif entry["changes"]:
                department.code = entry["code"]
                department.name = entry["name"]
                department.sort_order = entry["order"]
                department.save(update_fields=["code", "name", "sort_order"])
            registry[entry["code"]] = department

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
            cleared += (
                mine.exclude(role__name__in=TEACHING_ROLES)
                .exclude(department_obj__isnull=True)
                .update(department_obj=None)
            )

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

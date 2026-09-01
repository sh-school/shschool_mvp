"""وسمُ الإسنادات المتوازية — يُقرأ من الجدول القائم لا يُخترع.

أربعُ شعبٍ يتفرّق طلابها بين مادّتين في التوقيت نفسه. والجدولُ المستورَد يسجّل
ذلك في `ScheduleSlot.elective_group`، أمّا الإسنادُ فلا يعرفه — فيُنذر تحذيرُ
الطاقة كاذباً، ويعجز المولّدُ عن إنتاج الحصّتين معاً.

فيُقرأ الواقعُ من الجدول: أيُّ (شعبة · يوم · حصّة) تحمل أكثرَ من صفٍّ فموادُّها
متوازية، وتُوسَم إسناداتُها بوسمٍ واحد.

    python manage.py mark_parallel_groups --school SHH --year 2026-2027 --dry-run
"""

from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError

from core.models import School
from operations.models import ScheduleSlot, SubjectClassAssignment


class Command(BaseCommand):
    help = "يسِمُ الإسنادات المتوازية من واقع الجدول القائم."

    def add_arguments(self, parser):
        parser.add_argument("--school", default="SHH")
        parser.add_argument("--year", default="")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        school = School.objects.filter(code=opts["school"]).first()
        if school is None:
            raise CommandError(f"لا مدرسةَ بالكود {opts['school']}")
        year = opts["year"] or self._year(school)

        slots = defaultdict(list)
        for row in ScheduleSlot.objects.filter(
            school=school, academic_year=year, is_active=True
        ).select_related("class_group", "subject"):
            slots[(row.class_group_id, row.day_of_week, row.period_number)].append(row)

        #: لكلّ شعبةٍ مجموعةُ الموادّ التي وُجدت تتشارك خانةً.
        parallel = defaultdict(set)
        for (class_id, _, _), rows in slots.items():
            if len(rows) > 1:
                parallel[class_id] |= {r.subject_id for r in rows}

        if not parallel:
            self.stdout.write("لا شعبةَ منقسمةً في هذا الجدول.")
            return

        marked = 0
        for class_id, subject_ids in parallel.items():
            rows = SubjectClassAssignment.objects.filter(
                school=school,
                academic_year=year,
                class_group_id=class_id,
                subject_id__in=subject_ids,
                is_active=True,
            ).select_related("class_group", "subject")
            label = "متوازي-1"
            names = "، ".join(sorted(r.subject.name_ar for r in rows))
            self.stdout.write(f"{rows[0].class_group if rows else class_id}: {names} → {label}")
            if opts["dry_run"]:
                continue
            marked += rows.update(parallel_group=label)

        if opts["dry_run"]:
            self.stdout.write(self.style.WARNING("عرضٌ فقط — لم يُكتب شيء."))
        else:
            self.stdout.write(self.style.SUCCESS(f"وُسِم {marked} إسناداً في {len(parallel)} شعبة."))

    def _year(self, school):
        from core.academic_calendar import academic_year_for_school

        return academic_year_for_school(school)

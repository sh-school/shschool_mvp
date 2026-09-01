"""موارِدُ الجدولة المحدودة — الملاعبُ والمعملان.

القيدُ على **المكان** لا على المعلّم ولا على الشعبة: في المدرسة معملا حاسبٍ
اثنان، فلا تقع أكثرُ من حصّتَي حاسبٍ في التوقيت الواحد مهما كثر المعلّمون
الفارغون. والمعملانِ تتقاسمهما «التكنولوجيا» و«علوم الحاسب» و«تكنولوجيا
المعلومات» معاً، فالسقفُ عليها مجتمعةً لا على كلّ مادّةٍ بمفردها — ولهذا كان
المورد كياناً مستقلّاً لا حقلاً في المادّة.

    TeacherFree ∧ ClassFree ⇏ Schedulable

والبنيةُ قائمةٌ سلفاً: `SchedulingResource` و`HC9 check_resource_capacity`.
والناقصُ كان سطرَ البيانات — فمَن لم يُسجَّل مورده لم يُقيَّد.

والأمرُ مُعلِنٌ لا مُراكِم: يُثبت الوصفَ المكتوبَ هنا ويُظهر ما غيّره، ويُعيد
عرضَ ما في الجدول القائم من مخالفات — فالقيدُ يمنع ما يُولَّد بعده ولا يُصلح
ما وُلِّد قبله.

    python manage.py seed_scheduling_resources --school SHH --dry-run
"""

from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from core.academic_calendar import academic_year_for_school
from core.models import School
from operations.models import ScheduleSlot, SchedulingResource, Subject

#: الموارد المحدودة في المدرسة: (الاسم، السعة، الموادّ، الملاحظة).
#: والسعةُ عددُ الحصص التي تقع معاً في التوقيت الواحد.
RESOURCES = (
    (
        "معملا الحاسب",
        2,
        ("التكنولوجيا", "علوم الحاسب", "تكنولوجيا المعلومات"),
        "معملان اثنان تتقاسمهما موادُّ الحاسب",
    ),
    (
        "الملاعب",
        2,
        ("التربية البدنية",),
        "ملعبان اثنان",
    ),
)

DAYS = ("الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس")


class Command(BaseCommand):
    help = "يُثبت موارد الجدولة المحدودة (المعملان والملعبان) ويكشف مخالفات الجدول القائم."

    def add_arguments(self, parser):
        parser.add_argument("--school", default="SHH")
        parser.add_argument("--year", default="")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        school = School.objects.filter(code=opts["school"]).first()
        if school is None:
            raise CommandError(f"لا مدرسةَ بالكود {opts['school']}")
        year = opts["year"] or academic_year_for_school(school)
        dry_run = opts["dry_run"]

        for name, capacity, subject_names, note in RESOURCES:
            subjects = list(Subject.objects.filter(school=school, name_ar__in=subject_names))
            missing = set(subject_names) - {s.name_ar for s in subjects}
            if missing:
                # مادّةٌ غير مسجّلةٍ في المدرسة لا تُسقط الموردَ كلَّه، لكنّها
                # ثغرةٌ في القيد فتُقال بصوتٍ مسموع.
                self.stdout.write(self.style.WARNING(f"{name}: لا مادّةَ باسم {'، '.join(missing)}"))

            resource = SchedulingResource.objects.filter(school=school, name=name).first()
            changes = []
            if resource is None:
                changes.append("جديد")
            else:
                if resource.capacity != capacity:
                    changes.append(f"السعة {resource.capacity} → {capacity}")
                if not resource.is_active:
                    changes.append("تفعيل")
                current = {s.id for s in resource.subjects.all()}
                if current != {s.id for s in subjects}:
                    changes.append("الموادّ")

            names = "، ".join(s.name_ar for s in subjects)
            state = "، ".join(changes) if changes else "دون تغيير"
            self.stdout.write(f"{name} (سعة {capacity}): {names} — {state}")

            if dry_run or not changes:
                continue

            if resource is None:
                resource = SchedulingResource.objects.create(
                    school=school, name=name, capacity=capacity, note=note
                )
            else:
                resource.capacity = capacity
                resource.is_active = True
                resource.save(update_fields=["capacity", "is_active"])
            resource.subjects.set(subjects)

        self._report_violations(school, year)

        if dry_run:
            self.stdout.write(self.style.WARNING("عرضٌ فقط — لم يُكتب شيء."))
        else:
            self.stdout.write(self.style.SUCCESS("ثُبِّتت الموارد."))

    def _report_violations(self, school, year):
        """ما في الجدول القائم من تجاوزٍ للسعة — والقيدُ لا يُصلحه بأثرٍ رجعيّ."""
        for name, capacity, subject_names, _ in RESOURCES:
            load = Counter(
                (row.day_of_week, row.period_number)
                for row in ScheduleSlot.objects.filter(
                    school=school,
                    academic_year=year,
                    is_active=True,
                    subject__name_ar__in=subject_names,
                ).only("day_of_week", "period_number")
            )
            over = {slot: count for slot, count in load.items() if count > capacity}
            if not over:
                continue
            self.stdout.write(
                self.style.ERROR(f"{name}: {len(over)} خانةً فوق السعة في جدول {year}")
            )
            for (day, period), count in sorted(over.items()):
                self.stdout.write(f"   {DAYS[day]} ح{period}: {count} حصص معاً")
            self.stdout.write("   القيدُ يمنع ما يُولَّد بعده — وهذه تحتاج إعادةَ توليد.")

"""نصابُ موادّ المعمل: أربعُ حصصٍ في مزدوجتين، لا حصّتان.

جدولُ المدرسة الحقيقيُّ (aSc, 28/08/2026) يُظهر في الحادي عشر/4 والثاني عشر/4:

    علوم الحاسب          مزدوجتان في الأسبوع  →  أربعُ حصص
    تكنولوجيا المعلومات   مزدوجتان في الأسبوع  →  أربعُ حصص

وكان في بياناتنا حصّتان لكلٍّ — فنقصت أربعُ حصصٍ في كلّ شعبة، وثمانٍ في
الشعبتين. وهي الثمانيةُ التي ظهرت فراغاً في الجدول المولَّد.

## ولماذا لم يكشفه العدُّ الآليّ

استُخرج الجدولُ العامُّ من ملفّ aSc آليّاً فأعطى الشعبتين ثلاثاً وثلاثين حصّةً
— مطابقاً لبياناتنا الناقصة. والسببُ أنّ **الحصّةَ المزدوجةَ خليّةٌ واحدةٌ
عريضةٌ في الملفّ**، فيعدّها المستخرِجُ حصّةً لا حصّتين. فنقصُ القراءة ساوى
نقصَ البيانات فبدا الأمرُ سليماً — ولم ينكشف إلّا بمراجعة جدولَي الشعبتين
بأعينهما.

    مطابقةُ رقمين لا تعني صحّتَهما: قد يكونان خاطئين بالمقدار نفسه.

    python manage.py fix_lab_subject_periods --school SHH --dry-run
"""

from django.core.management.base import BaseCommand, CommandError

from core.academic_calendar import academic_year_for_school
from core.models import School
from operations.models import SubjectClassAssignment

#: المادّةُ ونصابُها الصحيح — من جدول المدرسة لا من اجتهاد.
LAB_SUBJECTS = {
    "علوم الحاسب": 4,
    "تكنولوجيا المعلومات": 4,
}


class Command(BaseCommand):
    help = "يُصحّح نصابَ موادّ المعمل إلى أربع حصصٍ (مزدوجتان) كما في جدول المدرسة."

    def add_arguments(self, parser):
        parser.add_argument("--school", default="SHH")
        parser.add_argument("--year", default="")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        school = School.objects.filter(code=opts["school"]).first()
        if school is None:
            raise CommandError(f"لا مدرسةَ بالكود {opts['school']}")
        year = opts["year"] or academic_year_for_school(school)

        changed = 0
        for name, periods in LAB_SUBJECTS.items():
            rows = SubjectClassAssignment.objects.filter(
                school=school, academic_year=year, is_active=True, subject__name_ar=name
            ).select_related("class_group", "subject")
            if not rows:
                self.stdout.write(self.style.WARNING(f"{name}: لا إسنادَ في {year}"))
                continue
            if not rows[0].subject.requires_double_period:
                self.stdout.write(
                    self.style.WARNING(f"تنبيه: «{name}» غيرُ مُعلَّمةٍ «مزدوجة» — تُوزَّع مفردةً.")
                )
            for row in rows:
                label = str(row.class_group).split(" (")[0]
                if row.weekly_periods == periods:
                    self.stdout.write(f"{name} · {label}: {periods} — دون تغيير")
                    continue
                self.stdout.write(
                    self.style.SUCCESS(f"{name} · {label}: {row.weekly_periods} → {periods}")
                )
                if opts["dry_run"]:
                    continue
                row.weekly_periods = periods
                row.save(update_fields=["weekly_periods"])
                changed += 1
        if opts["dry_run"]:
            self.stdout.write(self.style.WARNING("عرضٌ فقط — لم يُكتب شيء."))
        else:
            self.stdout.write(self.style.SUCCESS(f"صُحّح {changed} إسناداً."))

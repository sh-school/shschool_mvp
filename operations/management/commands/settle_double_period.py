"""حسمُ الازدواج حيث سكتت عنه البيانات — والصمتُ فخٌّ لا قيمةٌ محايدة.

    python manage.py settle_double_period
    python manage.py settle_double_period --apply

## العلّة

`SubjectClassAssignment.double_period` ثلاثيُّ القيمة: نعم، ولا، و**لا شيء**.
واللاشيءُ يرث `Subject.requires_double_period` — فيصير قرارُ مادّةٍ كاملةٍ
قرارَ إسنادٍ بعينه بلا أن يكتبه أحد.

وقد أضرّ ذلك فعلاً: الفنّيّةُ مزدوجةٌ في الإعداديّ ومتباعدةٌ في الثانويّ. وكان
حقلُ «أيّامٌ مختلفة» (HC18) يستر الأثرَ — يُبطل الازدواجَ حيث سرى التباعد. فلمّا
سقط HC18 (التباعدُ نتيجةُ قسمةٍ في HC6 لا وسمٌ يُكتب) ظهر الموروثُ على وجهه:
الفنّيّةُ في الحادي عشر/1 تُجدول مزدوجةً لأنّ حقلَها ساكت.

## العلاج — والصفةُ صفةُ إسنادٍ لا صفةُ مادّة

1. `Subject.requires_double_period = False` للفنون البصريّة: الازدواجُ صفةُ
   إسناد، وهو مكتوبٌ صريحاً على اثنَي عشرَ إسناداً إعداديّاً سلفاً.
2. كلُّ إسنادٍ نشطٍ لمادّةٍ مزدوجةٍ يوماً وساكتٍ عن نفسه يُكتب له `False`
   صريحاً — فلا يُقرأ قرارُه من مكانٍ آخر.

وهو idempotent: تشغيلُه مرّتين يكتب في الأولى ولا يجد في الثانية شيئاً.
ولا يكتب بلا `--apply`، وللعمليّة سطرٌ في سجلّ التدقيق.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import School
from core.models.audit import AuditLog
from operations.models import Subject, SubjectClassAssignment

#: الموادُّ التي يُنزَع عنها وسمُ الازدواج: الصفةُ صفةُ إسنادٍ لا مادّة.
SUBJECT_CODES = ("ART",)


class Command(BaseCommand):
    help = "يحسم الازدواجَ حيث سكتت عنه البيانات — بلا كتابةٍ إلّا بـ--apply"

    def add_arguments(self, parser):
        parser.add_argument("--school", default="", help="رمزُ المدرسة — والافتراضُ الأولى")
        parser.add_argument("--year", default="", help="العامُ الدراسيّ — والافتراضُ كلُّها")
        parser.add_argument("--apply", action="store_true", help="اكتب — والافتراضُ عرضٌ فقط")

    def handle(self, *args, **options):
        school = self._school(options["school"])

        subjects = list(
            Subject.objects.filter(
                school=school, code__in=SUBJECT_CODES, requires_double_period=True
            ).order_by("code")
        )

        silent = SubjectClassAssignment.objects.filter(
            school=school, is_active=True, double_period__isnull=True
        ).select_related("class_group", "subject")
        if options["year"]:
            silent = silent.filter(academic_year=options["year"])
        # السكوتُ لا يضرّ إلّا حين يرث «نعم» — ومادّةٌ غيرُ مزدوجةٍ سكوتُ
        # إسنادها سكوتٌ عن «لا»، فلا يُلمَس ولا يُحشى السجلُّ به.
        doubled_now = set(
            Subject.objects.filter(school=school, requires_double_period=True).values_list(
                "id", flat=True
            )
        )
        silent = [a for a in silent if a.subject_id in doubled_now]

        if not subjects and not silent:
            self.stdout.write(self.style.SUCCESS("لا سكوتَ يُحسم — البيانات صريحةٌ سلفاً."))
            return

        self.stdout.write(f"المدرسة: {school.name}")
        for subject in subjects:
            explicit = SubjectClassAssignment.objects.filter(
                school=school, subject=subject, is_active=True, double_period=True
            ).count()
            self.stdout.write(
                f"  • {subject.name_ar} [{subject.code}]: تُنزَع صفةُ الازدواج عن المادّة"
                f" — وهي مكتوبةٌ صريحاً على {explicit} إسناداً"
            )
        for assignment in sorted(silent, key=lambda a: str(a.class_group)):
            self.stdout.write(
                f"  • {assignment.class_group} · {assignment.subject.name_ar}:"
                f" ساكتٌ يرث «مزدوجة» ← يُكتب له «لا» صريحاً"
            )

        if not options["apply"]:
            self.stdout.write(self.style.WARNING("\nعرضٌ فقط — أضف --apply للكتابة"))
            return

        with transaction.atomic():
            for subject in subjects:
                subject.requires_double_period = False
                subject.save(update_fields=["requires_double_period"])
            for assignment in silent:
                assignment.double_period = False
                assignment.save(update_fields=["double_period"])

            AuditLog.objects.create(
                school=school,
                user=None,
                action="update",
                model_name="other",
                object_id="",
                object_repr=f"حسمُ الازدواج: {len(subjects)} مادّةً و{len(silent)} إسناداً"[:300],
                changes={
                    "event": "double_period_settled",
                    "subjects": [s.code for s in subjects],
                    "assignments": [f"{a.class_group} · {a.subject.name_ar}" for a in silent],
                },
            )

        self.stdout.write(self.style.SUCCESS(f"\nحُسم {len(subjects)} مادّةً و{len(silent)} إسناداً"))

    def _school(self, code: str) -> School:
        school = (
            (School.objects.filter(code=code) if code else School.objects.all())
            .order_by("id")
            .first()
        )
        if school is None:
            raise CommandError(f"لا مدرسةَ برمز {code}" if code else "لا مدرسةَ في القاعدة")
        return school

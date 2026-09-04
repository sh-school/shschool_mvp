"""اجتماعُ منسّقي المواد: الأحدُ الحصّةُ الأولى — تفريغٌ للجميع.

منسّقو المواد يجتمعون بالنائب الأكاديميّ كلَّ أحدٍ في الحصّة الأولى، فلا
يُجدَّل لأحدهم فيها درس. والقيدُ على **الدور** لا على الأشخاص: من صار منسّقاً
دخل فيه، ومن تركه خرج منه — فيُعاد تشغيلُ الأمر بعد كلّ تغييرٍ في المنسّقين.

    python manage.py exempt_coordinators_meeting --school SHH --dry-run

ويُلغى التفريغُ بـ`--undo` إن انتقل الاجتماعُ إلى موعدٍ آخر.
"""

from django.core.management.base import BaseCommand, CommandError

from core.academic_calendar import academic_year_for_school
from core.models import Membership, School
from operations.models import TeacherExemption

SUNDAY = 0
FIRST_PERIOD = 1
REASON = "اجتماعُ منسّقي المواد بالنائب الأكاديميّ"


class Command(BaseCommand):
    help = "يُفرّغ منسّقي المواد يومَ الأحد الحصّةَ الأولى لاجتماعهم بالنائب الأكاديميّ."

    def add_arguments(self, parser):
        parser.add_argument("--school", default="SHH")
        parser.add_argument("--year", default="")
        parser.add_argument("--undo", action="store_true", help="إلغاءُ التفريغ")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        school = School.objects.filter(code=opts["school"]).first()
        if school is None:
            raise CommandError(f"لا مدرسةَ بالكود {opts['school']}")
        year = opts["year"] or academic_year_for_school(school)

        coordinators = (
            Membership.objects.filter(school=school, role__name="coordinator", is_active=True)
            .select_related("user")
            .order_by("user__full_name")
        )
        if not coordinators:
            self.stdout.write(self.style.WARNING("لا منسّقين في هذه المدرسة."))
            return

        if opts["undo"]:
            rows = TeacherExemption.objects.filter(
                school=school,
                academic_year=year,
                day_of_week=SUNDAY,
                period_number=FIRST_PERIOD,
                reason=REASON,
            )
            self.stdout.write(f"سيُلغى {rows.count()} تفريغاً.")
            if not opts["dry_run"]:
                rows.delete()
                self.stdout.write(self.style.SUCCESS("أُلغي التفريغ."))
            return

        created = 0
        for membership in coordinators:
            existing = TeacherExemption.objects.filter(
                school=school,
                teacher=membership.user,
                academic_year=year,
                day_of_week=SUNDAY,
                period_number=FIRST_PERIOD,
                is_active=True,
            ).first()
            if existing:
                self.stdout.write(f"{membership.user.full_name}: مفرَّغٌ سلفاً")
                continue
            self.stdout.write(self.style.SUCCESS(f"{membership.user.full_name}: الأحد ح1"))
            if opts["dry_run"]:
                continue
            row = TeacherExemption(
                school=school,
                teacher=membership.user,
                academic_year=year,
                exemption_type="specific_period",
                day_of_week=SUNDAY,
                period_number=FIRST_PERIOD,
                reason=REASON,
                source="school",
                is_active=True,
            )
            row.full_clean(exclude=["created_by"])
            row.save()
            created += 1

        if opts["dry_run"]:
            self.stdout.write(self.style.WARNING("عرضٌ فقط — لم يُكتب شيء."))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"فُرّغ {created} منسّقاً — والاجتماعُ محفوظٌ في الجدول.")
            )

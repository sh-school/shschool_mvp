"""
إعادةُ حساب نتائج العام الجاري كلِّها بقاعدة الحساب الحاليّة — مرّةً وصراحةً.

لماذا: تغيّر موضعُ جبر الكسور (م8: منتصفُ الفصل ثمّ مجموعُه، لا كلُّ باقة)، وصارت
الحالةُ السنويّة تقرأ الغيابَ عن الاختبارات (م22، م27، م12-ب). والنتيجةُ المخزَّنة لا
تتغيّر إلّا حين يُحفظ درجةٌ أو يُضغط زرُّ الإعادة — فتختلط في الشعبة الواحدة قاعدتان.
هذا الأمرُ يوحّدها للعام الجاري وحدَه، ولا يمسّ عاماً مُغلقاً.

    python manage.py recalculate_grade_results                                # عرضٌ فقط
    python manage.py recalculate_grade_results --apply --actor <الرقم الشخصي>
"""

from django.core.management.base import BaseCommand, CommandError

from assessments.models import AnnualSubjectResult, SubjectClassSetup
from assessments.services import GradeService
from core.academic_calendar import academic_year_for_school
from core.models import AuditLog, CustomUser, School


class Command(BaseCommand):
    help = "إعادةُ حساب نتائج العام الجاري بقاعدة الحساب الحاليّة — عرضٌ ما لم يُطلب --apply"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="تطبيقُ إعادة الحساب")
        parser.add_argument("--actor", help="الرقمُ الشخصيّ لمن ينفّذ — إلزاميٌّ مع --apply")
        parser.add_argument("--school", help="رمزُ مدرسةٍ واحدة (الافتراض: كلُّ المدارس)")

    def handle(self, *args, **options):
        schools = School.objects.all()
        if options["school"]:
            schools = schools.filter(code=options["school"])
            if not schools.exists():
                raise CommandError(f"--school: لا مدرسةَ برمز {options['school']}.")
        actor = None
        if options["apply"]:
            if not options["actor"]:
                raise CommandError("--actor إلزاميٌّ للتطبيق: من ينفّذ يُكتب في سجلّ المراجعة.")
            actor = CustomUser.objects.filter(national_id=options["actor"]).first()
            if actor is None:
                raise CommandError("--actor: لا مستخدمَ بهذا الرقم الشخصيّ.")

        for school in schools:
            year = academic_year_for_school(school)
            setups = list(
                SubjectClassSetup.objects.filter(school=school, academic_year=year).select_related(
                    "class_group"
                )
            )
            self.stdout.write(f"{school.code} · {year}: {len(setups)} إعداداً")
            if not options["apply"] or not setups:
                continue
            before = dict(
                AnnualSubjectResult.objects.filter(
                    setup__in=setups, academic_year=year
                ).values_list("id", "status")
            )
            students = sum(GradeService.recalculate_full_class(s) for s in setups)
            after = dict(
                AnnualSubjectResult.objects.filter(
                    setup__in=setups, academic_year=year
                ).values_list("id", "status")
            )
            changed = sum(1 for k, v in after.items() if before.get(k) != v)
            AuditLog.objects.create(
                school=school,
                user=actor,
                action="update",
                model_name="other",
                object_id=year,
                object_repr=f"إعادةُ حساب نتائج العام {year}"[:300],
                changes={
                    "op": "recalculate_grade_results",
                    "setups": len(setups),
                    "students": students,
                    "status_changed": changed,
                },
            )
            self.stdout.write(
                self.style.SUCCESS(f"  أُعيد حسابُ {students} نتيجةَ طالب · تغيّرت حالةُ {changed}")
            )
        if not options["apply"]:
            self.stdout.write("عرضٌ فقط — أعِد بـ--apply --actor للتطبيق.")

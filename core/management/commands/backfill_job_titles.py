"""تعميرُ المسمّى الوظيفيّ الناقص من عنوان الدور.

    python manage.py backfill_job_titles
    python manage.py backfill_job_titles --apply

## العلّة

كان سجلُّ الكادر يعرض عمودَين متقاربَين: «المسمّى الوظيفيّ» و«دور المنصّة».
وهما شيئان مختلفان: المسمّى نصٌّ وزاريٌّ حرٌّ فيه المادّة («معلم رياضيات»،
«منسق كيمياء»)، والدورُ مفتاحُ الصلاحيّات من قائمةٍ مغلقة («معلم»، «منسق
أكاديمي»). فالدورُ لا يصير نسخةً من المسمّى: لا دورَ اسمُه «منسق كيمياء»،
ولو جُعل المسمّى نسخةً من الدور ضاعت المادّة.

فالقرار: المسمّى هو المعروضُ وحدَه، والدورُ مفتاحٌ خفيٌّ يحرس الصلاحيّات.

ويبقى نقصٌ واحد: عضويّةٌ بلا مسمّى مسجَّل. وكانت الشاشةُ تستره بارتدادٍ إلى
عنوان الدور عند العرض، فيختلف المعروضُ عن المخزَّن — ويفترق الفرزُ والتصدير
وكلُّ قارئٍ آخرَ عن الشاشة. فيُكتب الارتدادُ في القاعدة مرّةً واحدة.

ولا يكتب شيئاً بلا `--apply`، وللعمليّة سطرٌ في سجلّ التدقيق.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import School
from core.models.access import Membership, Role
from core.models.audit import AuditLog

#: أدوارُ الطلاب وأولياء الأمور ليست وظائف — ولا مسمّى وظيفيّاً لها.
NOT_STAFF = ("student", "parent")


class Command(BaseCommand):
    help = "يملأ المسمّى الوظيفيّ الناقصَ من عنوان الدور — بلا كتابةٍ إلّا بـ--apply"

    def add_arguments(self, parser):
        parser.add_argument("--school", default="", help="رمزُ المدرسة — والافتراضُ الأولى")
        parser.add_argument("--apply", action="store_true", help="اكتب — والافتراضُ عرضٌ فقط")

    def handle(self, *args, **options):
        school = self._school(options["school"])
        labels = dict(Role.ROLES)

        gaps = []
        for membership in (
            Membership.objects.filter(school=school, is_active=True)
            .exclude(role__name__in=NOT_STAFF)
            .select_related("role", "user")
            .order_by("user__full_name")
        ):
            if (membership.job_title or "").strip():
                continue
            label = labels.get(membership.role.name, membership.role.name)
            gaps.append((membership, label))

        if not gaps:
            self.stdout.write(self.style.SUCCESS("لا عضويّةَ بلا مسمّى — لا شيءَ يُكتب"))
            return

        self.stdout.write(f"{len(gaps)} عضويّةً بلا مسمّى في {school.name}:")
        for membership, label in gaps:
            self.stdout.write(f"  {membership.user.full_name} — يُكتب له: {label}")

        if not options["apply"]:
            self.stdout.write(self.style.WARNING("\nعرضٌ فقط — أضف --apply للكتابة"))
            return

        with transaction.atomic():
            for membership, label in gaps:
                membership.job_title = label
                membership.save(update_fields=["job_title"])

            AuditLog.objects.create(
                school=school,
                user=None,
                action="update",
                model_name="other",
                object_id="",
                object_repr=f"تعميرُ {len(gaps)} مسمّى وظيفيّاً من عنوان الدور"[:300],
                changes={
                    "event": "job_titles_backfilled",
                    "filled": len(gaps),
                    "people": [m.user.full_name for m, _ in gaps],
                    "titles": [label for _, label in gaps],
                },
            )

        self.stdout.write(self.style.SUCCESS(f"\nكُتب {len(gaps)} مسمّى وظيفيّاً"))

    def _school(self, code: str) -> School:
        if code:
            school = School.objects.filter(code=code).first()
            if not school:
                raise CommandError(f"لا مدرسةَ برمز {code}")
            return school
        school = School.objects.order_by("id").first()
        if not school:
            raise CommandError("لا مدرسةَ في القاعدة")
        return school

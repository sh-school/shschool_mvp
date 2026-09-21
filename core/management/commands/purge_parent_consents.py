"""مسحُ كلّ سجلّات موافقة أولياء الأمور (ConsentRecord).

قرار المالك 2026-09-21: ما في النظام من موافقاتٍ كان تجريبيّاً (المفاتيحُ كانت
مُفعَّلةً مسبقاً فسُجّل «موافقٌ» بلا اختيارٍ فعليّ)، والموافقةُ صارت صريحةً
(PDPPL): لا سجلَّ ⇒ لم يوافق. فتُمسح كلُّها ويُطلب من كلّ وليٍّ أن يختار.

الأصلُ عرضٌ فقط (dry-run) بأعدادٍ لكلّ نوع؛ ولا يُحذف شيءٌ إلّا بـ ``--apply``،
ويُكتب عندئذٍ سطرُ تدقيقٍ لكلّ مدرسة. وبـ ``--reset-gate`` يُصفَّر
``consent_given_at`` لأولياء الأمور المربوطين فتعود بوّابةُ الموافقة تعرض
الصفحةَ عليهم عند دخولهم التالي (وإلّا بقوا يرون البوّابةَ بلا سجلّاتٍ ولا مطالبة).

    python manage.py purge_parent_consents                       # عرضٌ فقط
    python manage.py purge_parent_consents --apply --reset-gate  # تنفيذ
"""

from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import AuditLog, ConsentRecord, CustomUser, ParentStudentLink


class Command(BaseCommand):
    help = "يحذف كلَّ سجلّات ConsentRecord — عرضٌ فقط ما لم يُمرَّر --apply"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="ينفّذ الحذفَ فعلاً")
        parser.add_argument(
            "--reset-gate",
            action="store_true",
            help="يصفّر consent_given_at لأولياء الأمور المربوطين ليُطلب منهم الاختيار من جديد",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        reset_gate = options["reset_gate"]

        by_type = Counter(ConsentRecord.objects.values_list("data_type", flat=True))
        by_school = Counter(ConsentRecord.objects.values_list("school_id", flat=True))
        total = sum(by_type.values())
        gated = (
            CustomUser.objects.filter(
                pk__in=ParentStudentLink.objects.values("parent_id"),
                consent_given_at__isnull=False,
            ).count()
            if reset_gate
            else 0
        )

        for data_type, count in sorted(by_type.items()):
            self.stdout.write(f"{data_type}: {count}")
        self.stdout.write(f"المجموع: {total} سجلّاً في {len(by_school)} مدرسة")
        if reset_gate:
            self.stdout.write(f"أولياءُ أمورٍ سيُصفَّر consent_given_at لهم: {gated}")

        if not apply:
            self.stdout.write(self.style.WARNING("عرضٌ فقط — لم يُحذف شيء. أضِف --apply للتنفيذ."))
            return

        with transaction.atomic():
            ConsentRecord.objects.all().delete()
            # حارسٌ: لو أخفت سياسةُ RLS صفوفاً عن هذا الدور لبقي منها شيءٌ فنتراجع.
            remaining = ConsentRecord.objects.count()
            if remaining:
                raise CommandError(f"بقي {remaining} سجلّاً بعد الحذف — تُراجَع المعاملة")

            if reset_gate:
                CustomUser.objects.filter(
                    pk__in=ParentStudentLink.objects.values("parent_id"),
                    consent_given_at__isnull=False,
                ).update(consent_given_at=None)

            for school_id, count in by_school.items():
                AuditLog.log(
                    user=None,
                    action="delete",
                    model_name="ConsentRecord",
                    object_id="*",
                    object_repr=f"purge_parent_consents: {count} سجلّاً",
                    changes={
                        "command": "purge_parent_consents",
                        "reason": "بياناتٌ تجريبيّة — الموافقةُ صريحةٌ (قرار المالك 2026-09-21)",
                        "deleted": count,
                        "by_type": dict(by_type) if len(by_school) == 1 else None,
                        "gate_reset": reset_gate,
                    },
                    school=None if school_id is None else _school(school_id),
                )

        self.stdout.write(self.style.SUCCESS(f"حُذف {total} سجلّاً."))


def _school(school_id):
    from core.models import School

    return School.objects.filter(pk=school_id).first()

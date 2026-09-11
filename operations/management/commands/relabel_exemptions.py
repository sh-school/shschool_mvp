"""إعادةُ وسم تفريغات معلّمٍ إلى جهةٍ أخرى — بالجملة، وبعرضٍ قبل الكتابة.

    python manage.py relabel_exemptions --teacher "اسم كامل" --to generation
    python manage.py relabel_exemptions --teacher "اسم" --teacher "اسم آخر" --to generation --apply

## لماذا

على الإنتاج تسعون تفريغاً نشطاً موسومةً «إدارة/قسم/أخرى»، اثنان وستّون منها على
أربعة معلّمين. وليست قراراتِ جهات: هي خاناتٌ أُغلقت ليقع جدولُ المعلّم حيث
يُراد — أدواتُ تشكيلٍ للجدول. وحين صار البديلُ والتبديلُ يحترمان التفريغَ
الملزم (قرار 2026-09-11)، صار بقاءُ هذه على وسمها القديم يجعل البديلَ أصعبَ من
اليوم لا أسهل. فتُنقل إلى «لتوليد الجدول»: المولّدُ يحترمها كما كان، والناسُ لا
تُمنَع بها.

## الضوابط

- المعلّمُ يُسمّى، ويُطابَق **اسمُه الكامل فريداً** — واسمٌ يقابله اثنان يُرفض.
- الجهةُ الهدفُ من قائمة النموذج لا نصٌّ حرّ.
- تُعرض السطورُ قبل الكتابة، ولا يُكتب شيءٌ بلا `--apply`.
- لكلّ تفريغٍ مُعادِ الوسم سطرٌ في سجلّ التدقيق يحمل الجهةَ القديمةَ والجديدة.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import CustomUser, School
from core.models.audit import AuditLog
from operations.models import TeacherExemption


class Command(BaseCommand):
    help = "يُعيد وسمَ تفريغات معلّمين بعينهم إلى جهةِ قرارٍ أخرى — بلا كتابةٍ إلّا بـ--apply"

    def add_arguments(self, parser):
        parser.add_argument(
            "--teacher",
            action="append",
            default=[],
            help="الاسمُ الكامل كما في القاعدة — يُكرَّر لأكثر من معلّم",
        )
        parser.add_argument("--to", required=True, help="الجهةُ الجديدة، مثل generation")
        parser.add_argument("--school", default="", help="رمزُ المدرسة — والافتراضُ الأولى")
        parser.add_argument("--year", default="", help="العامُ الدراسيّ — والافتراضُ الجاري")
        parser.add_argument("--apply", action="store_true", help="بدونه يعرض ولا يكتب")

    def handle(self, *args, **options):
        school = self._school(options["school"])
        target = options["to"]
        labels = dict(TeacherExemption._meta.get_field("source").choices)
        if target not in labels:
            raise CommandError(f"جهةٌ غيرُ معروفة «{target}» — الجهات: {'، '.join(labels)}")
        if not options["teacher"]:
            raise CommandError("سمِّ معلّماً واحداً على الأقلّ بـ--teacher.")

        from core.querysets import year_or_current

        year = options["year"] or year_or_current(school)
        teachers = [self._teacher(name) for name in options["teacher"]]

        rows = TeacherExemption.objects.filter(
            school=school, academic_year=year, is_active=True, teacher__in=teachers
        ).exclude(source=target)
        self.stdout.write(f"المدرسة: {school.name} · العام {year} · الهدف «{labels[target]}»")
        if not rows.exists():
            self.stdout.write(self.style.SUCCESS("لا تفريغَ يحتاج إعادةَ وسم."))
            return

        by_teacher: dict[str, list] = {}
        for row in rows.select_related("teacher").order_by("teacher__full_name", "day_of_week"):
            by_teacher.setdefault(row.teacher.full_name, []).append(row)
        for name, items in by_teacher.items():
            sources = sorted({labels[r.source] for r in items})
            self.stdout.write(f"  • {name}: {len(items)} تفريغاً — من {'، '.join(sources)}")

        if not options["apply"]:
            self.stdout.write(f"\nعرضٌ فقط — {rows.count()} سطراً. أضِف --apply للكتابة.")
            return

        written = self._write(school, rows, target, labels)
        self.stdout.write(self.style.SUCCESS(f"\nأُعيد وسمُ {written} تفريغاً."))

    @transaction.atomic
    def _write(self, school, rows, target, labels):
        written = 0
        for row in rows.select_related("teacher"):
            before = row.source
            row.source = target
            row.save(update_fields=["source"])
            AuditLog.objects.create(
                school=school,
                user=None,
                action="update",
                model_name="other",
                object_id=str(row.pk),
                object_repr=f"تفريغ {row.teacher.full_name} — {row}"[:300],
                changes={
                    "event": "exemption_relabelled",
                    "source": [before, target],
                    "reason": "أداةُ تشكيلٍ للجدول لا قرارُ جهة — البديلُ والتبديلُ يجوزان فيها",
                },
            )
            written += 1
        return written

    def _teacher(self, name):
        key = " ".join(name.split())
        matches = list(CustomUser.objects.filter(full_name=key))
        if not matches:
            raise CommandError(f"لا معلّمَ بهذا الاسم: «{key}»")
        if len(matches) > 1:
            raise CommandError(f"الاسمُ «{key}» يقابله {len(matches)} حساباً — حدّده بأدقّ.")
        return matches[0]

    def _school(self, code):
        school = School.objects.filter(code=code).first() if code else School.objects.first()
        if school is None:
            raise CommandError("لا مدرسةَ بهذا الرمز.")
        return school

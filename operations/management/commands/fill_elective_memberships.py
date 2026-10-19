"""يملأ عضويّةَ الطلبة في المجموعات الاختياريّة من ملفّ CSV (W-20261002-021) — idempotent، يعمل بعد الدوام.

الأعمدة: national_id، grade، section، group_label. الافتراضيُّ عرضٌ بلا كتابة؛ والكتابةُ بـ`--apply`.
لا تُنشأ عضويّةٌ لطالبٍ بلا قيدٍ نشطٍ في الشعبة المذكورة (تُعدّ وتُبلَّغ)، وتكرارُ التشغيل لا يُضاعف شيئاً.
"""

import csv

from django.core.management.base import BaseCommand, CommandError

from core.models import ElectiveGroupMembership, StudentEnrollment


class Command(BaseCommand):
    help = "ملءُ عضويّة المجموعات الاختياريّة من CSV (عرضٌ افتراضيّ، --apply للكتابة)"

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **opts):
        try:
            handle = open(opts["csv_path"], encoding="utf-8-sig", newline="")  # noqa: SIM115
        except OSError as exc:
            raise CommandError(f"تعذّرت قراءة الملف: {exc}") from exc
        created = existing = missing = 0
        with handle:
            for row in csv.DictReader(handle):
                enrollment = (
                    StudentEnrollment.objects.filter(
                        student__national_id=row["national_id"].strip(),
                        class_group__grade=row["grade"].strip(),
                        class_group__section=row["section"].strip(),
                        is_active=True,
                    )
                    .order_by("-enrolled_at")
                    .first()
                )
                if enrollment is None:
                    missing += 1
                    continue
                label = row["group_label"].strip()
                if ElectiveGroupMembership.objects.filter(
                    enrollment=enrollment, group_label=label
                ).exists():
                    existing += 1
                    continue
                created += 1
                if opts["apply"]:
                    ElectiveGroupMembership.objects.create(enrollment=enrollment, group_label=label)
        mode = "كُتب" if opts["apply"] else "عرضٌ فقط (لم يُكتب شيء)"
        self.stdout.write(f"{mode}: جديد={created} قائم={existing} بلا قيدٍ نشط={missing}")

"""
يُصنّف حالةَ التشفير في حقول السجلّ الصحّيّ الطبّيّة — ولا يكتب شيئاً أبداً.

    python manage.py classify_health_record_encryption [--out تقرير.json]

هذا الأمرُ لا يملك مسارَ كتابةٍ ولا رايةَ `--apply`: التصنيفُ يسبق الترحيل،
ولا يجوز أن يُصلح ما يُصنّفه في المرور نفسه. ومخرجُه أثرٌ يُراجَع ويُقرَّر على
أساسه، لا قرارُ إصلاح.

وما بقي `UNKNOWN` يُمنع ترحيلُه آلياً — هو وحده، لا الجدولُ كلُّه.

ولا يُطبع نصٌّ طبّيٌّ واحد: المعرّفُ واسمُ الحقل والتصنيفُ وسببُه فقط.
"""

import json

from django.core.management.base import BaseCommand

from clinic.encryption_audit import (
    CLASSIFICATIONS,
    UNKNOWN,
    classify_records,
    summarise,
)
from clinic.models import HealthRecord


class Command(BaseCommand):
    help = "يُصنّف تشفيرَ حقول السجلّ الصحّيّ (قراءةً فقط — لا يكتب)"

    def add_arguments(self, parser):
        parser.add_argument("--out", default="", help="يحفظ التقرير المفصَّل بصيغة JSON")
        parser.add_argument(
            "--show-all",
            action="store_true",
            help="يعرض كلَّ القيم لا الشاذّة وحدها",
        )

    def handle(self, *args, **options):
        from core.models._crypto import _get_fernet

        fernet = _get_fernet()
        records = list(HealthRecord.objects.all().only("id", *self._fields()))
        rows = classify_records(records, fernet)
        counts = summarise(rows)

        self.stdout.write("")
        if fernet is None:
            self.stdout.write(
                self.style.WARNING(
                    "لا مفتاحَ تشفيرٍ في هذه البيئة — لا يُميَّز العاري من المشفَّر، "
                    "فكلُّ ما ليس فارغاً UNKNOWN. شغّله حيث المفتاحُ مضبوط."
                )
            )
            self.stdout.write("")

        self.stdout.write(f"total_records={len(records)}")
        self.stdout.write(f"total_values={len(rows)}")
        self.stdout.write("")
        for name in CLASSIFICATIONS:
            self.stdout.write(f"{name}={counts[name]}")

        shown = [r for r in rows if options["show_all"] or self._notable(r)]
        if shown:
            self.stdout.write("")
            self.stdout.write("── القيم ──")
            for pk, field, verdict in shown:
                depth = f" عمق={verdict.depth}" if verdict.depth else ""
                self.stdout.write(
                    f"  {pk}  {field:<18} {verdict.verdict}{depth}  ({verdict.reason})"
                )

        if counts[UNKNOWN]:
            self.stdout.write("")
            self.stdout.write(
                self.style.ERROR(
                    f"{counts[UNKNOWN]} قيمةً لم يثبت تصنيفُها — تُمنع من الترحيل الآليّ "
                    "حتى تُفهَم. ولا «أفضل تخمين»."
                )
            )

        if options["out"]:
            self._write_report(options["out"], records, rows, counts, fernet)
            self.stdout.write(self.style.SUCCESS(f"\nحُفظ التقرير: {options['out']}"))

        self.stdout.write(self.style.SUCCESS("\nقراءةٌ فقط — لم يُكتب شيء.\n"))

    # ── مساعدات ──────────────────────────────────────────────────────

    def _fields(self):
        from clinic.encryption_audit import MEDICAL_FIELDS

        return MEDICAL_FIELDS

    def _notable(self, row):
        """ما يستحقّ العرضَ افتراضاً: الشاذُّ وما يحتاج قراراً."""
        from clinic.encryption_audit import EMPTY, ENCRYPTED_ONCE

        return row[2].verdict not in (EMPTY, ENCRYPTED_ONCE)

    def _write_report(self, path, records, rows, counts, fernet):
        """أثرٌ يُراجَع — وفيه المعرّفاتُ والتصنيفاتُ دون أيّ نصٍّ طبّيّ."""
        from django.utils import timezone

        payload = {
            "generated_at": timezone.now().isoformat(),
            "key_present": fernet is not None,
            "total_records": len(records),
            "total_values": len(rows),
            "counts": counts,
            "values": [
                {
                    "record_id": str(pk),
                    "field": field,
                    "classification": verdict.verdict,
                    "reason": verdict.reason,
                    "depth": verdict.depth,
                }
                for pk, field, verdict in rows
            ],
        }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=1)

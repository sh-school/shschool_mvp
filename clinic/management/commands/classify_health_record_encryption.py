"""
يُصنّف حالةَ التشفير في كلّ حقلٍ مشفَّرٍ بالسجلّ الصحّيّ وزيارات العيادة — ولا يكتب شيئاً أبداً.

    python manage.py classify_health_record_encryption [--out تقرير.json] [--detail]

هذا الأمرُ لا يملك مسارَ كتابةٍ ولا رايةَ `--apply`: التصنيفُ يسبق الترحيل،
ولا يجوز أن يُصلح ما يُصنّفه في المرور نفسه. ومخرجُه أثرٌ يُراجَع ويُقرَّر على
أساسه، لا قرارُ إصلاح.

وما بقي `UNKNOWN` يُمنع ترحيلُه آلياً — هو وحده، لا الجدولُ كلُّه.

**أعدادٌ فقط افتراضياً:** لكلّ حقلٍ عددُ كلّ تصنيف، بلا نصٍّ طبّيٍّ ولا معرّفٍ مقترنٍ بنتيجة. وتفصيلُ
المعرّفات (معرّفُ الصفّ لا الطالب) خلف `--detail` للتحقيق في شاذٍّ بعينه.

والقراءةُ من الأعمدة **الخام** (SQL) لا من النموذج: الحقلُ الشفّاف يفكّ الطبقةَ عند القراءة فيُرى كلُّ شيءٍ نصّاً
عارياً (W-20261020-028). والحقولُ تُستقرأ بالانعكاس فلا يفوت حقلٌ مشفَّرٌ أُضيف لاحقاً.
"""

import json

from django.core.management.base import BaseCommand

from clinic.encryption_audit import (
    CLASSIFICATIONS,
    UNKNOWN,
    classify_raw,
    summarise,
    summarise_by_field,
)
from clinic.models import ClinicVisit, HealthRecord
from core.fields import encrypted_field_names

MODELS = (HealthRecord, ClinicVisit)


class Command(BaseCommand):
    help = "يُصنّف تشفيرَ حقول السجلّ الصحّيّ وزيارات العيادة من الأعمدة الخام (قراءةً فقط — لا يكتب)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--out", default="", help="يحفظ التقرير بصيغة JSON (أعداد، وتفصيلٌ مع --detail)"
        )
        parser.add_argument(
            "--detail",
            action="store_true",
            help="يضيف معرّفَ الصفّ وتصنيفَ كلّ قيمةٍ شاذّةٍ (بلا نصّ). الافتراضيُّ أعدادٌ فقط",
        )

    def handle(self, *args, **options):
        from core.models.crypto import _get_fernet

        fernet = _get_fernet()
        self.stdout.write("")
        if fernet is None:
            self.stdout.write(
                self.style.WARNING(
                    "لا مفتاحَ تشفيرٍ في هذه البيئة — لا يُميَّز العاري من المشفَّر، "
                    "فكلُّ ما ليس فارغاً UNKNOWN. شغّله حيث المفتاحُ مضبوط."
                )
            )
            self.stdout.write("")

        report: dict = {}
        all_rows = []
        for model in MODELS:
            fields = encrypted_field_names(model)
            rows = classify_raw(model, fields, fernet)
            all_rows.append((model, rows))
            per_field = summarise_by_field(rows)
            report[model.__name__] = {
                "fields": fields,
                "total_records": len({pk for pk, _f, _v in rows}),
                "per_field": per_field,
                "totals": summarise(rows),
            }
            self.stdout.write(
                f"── {model.__name__}: صفوف={report[model.__name__]['total_records']} ──"
            )
            for name in fields:
                counts = per_field.get(name) or dict.fromkeys(CLASSIFICATIONS, 0)
                line = " ".join(f"{c}={counts[c]}" for c in CLASSIFICATIONS)
                self.stdout.write(f"  {name:<24} {line}")
            self.stdout.write("")

        unknown = sum(r["totals"][UNKNOWN] for r in report.values())
        if unknown:
            self.stdout.write(
                self.style.ERROR(
                    f"{unknown} قيمةً لم يثبت تصنيفُها — تُمنع من الترحيل الآليّ "
                    "حتى تُفهَم. ولا «أفضل تخمين»."
                )
            )

        if options["detail"]:
            self.stdout.write("── التفصيل (معرّفُ الصفّ، بلا نصّ) ──")
            for model, rows in all_rows:
                for pk, field, verdict in rows:
                    if self._notable(verdict):
                        depth = f" عمق={verdict.depth}" if verdict.depth else ""
                        self.stdout.write(
                            f"  {model.__name__} {pk} {field:<20} {verdict.verdict}{depth}  ({verdict.reason})"
                        )

        if options["out"]:
            self._write_report(options["out"], report, all_rows, fernet, options["detail"])
            self.stdout.write(self.style.SUCCESS(f"\nحُفظ التقرير: {options['out']}"))

        self.stdout.write(self.style.SUCCESS("\nقراءةٌ فقط — لم يُكتب شيء.\n"))

    @staticmethod
    def _notable(verdict):
        """ما يستحقّ التفصيل: الشاذُّ وما يحتاج قراراً."""
        from clinic.encryption_audit import EMPTY, ENCRYPTED_ONCE

        return verdict.verdict not in (EMPTY, ENCRYPTED_ONCE)

    def _write_report(self, path, report, all_rows, fernet, detail):
        """أثرٌ يُراجَع: أعدادٌ لكلّ حقل، ومعرّفاتُ الصفوف الشاذّة فقط إن طُلب `--detail`، ولا نصَّ طبّيّاً."""
        from django.utils import timezone

        payload = {
            "generated_at": timezone.now().isoformat(),
            "key_present": fernet is not None,
            "models": report,
        }
        if detail:
            payload["notable"] = [
                {
                    "model": model.__name__,
                    "record_id": str(pk),
                    "field": field,
                    "classification": verdict.verdict,
                    "reason": verdict.reason,
                    "depth": verdict.depth,
                }
                for model, rows in all_rows
                for pk, field, verdict in rows
                if self._notable(verdict)
            ]
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=1)

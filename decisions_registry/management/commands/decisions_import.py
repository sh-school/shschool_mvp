from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from decisions_registry.services import DecisionsImportError, import_decisions


class Command(BaseCommand):
    help = "استيرادُ سجلّ قرارات المالك من ملفٍّ خارجَ git باتجاهٍ واحد (يشغّله 0601 بعد الدوام)"

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="decisions.md")
        parser.add_argument("--meta", help="decisions_meta.jsonl")
        parser.add_argument("--names-file", help="أسماءٌ تُحجب، اسمٌ بكلّ سطر (خارجَ git)")

    def handle(self, *args, **options):
        names: tuple[str, ...] = ()
        try:
            if options["names_file"]:
                names = tuple(Path(options["names_file"]).read_text(encoding="utf-8").splitlines())
            result = import_decisions(
                Path(options["file"]),
                Path(options["meta"]) if options["meta"] else None,
                names,
            )
        except (DecisionsImportError, OSError, UnicodeDecodeError) as exc:
            raise CommandError(str(exc)) from exc
        note = "" if names else " — تنبيه: لا قائمة أسماء للحجب (حُجبت الأرقام والبريد فقط)"
        self.stdout.write(
            f"قُرئ {result.total}، أُنشئ {result.created}، دون تغيير {result.unchanged}{note}"
        )

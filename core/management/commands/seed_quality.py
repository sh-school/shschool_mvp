from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "حقن الخطة التشغيلية ولجنة المراجعة الذاتية من ملفات CSV"

    def handle(self, *args, **kwargs):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "scripts"))
        from seed_quality import run
        run()

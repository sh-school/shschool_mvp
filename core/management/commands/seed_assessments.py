from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "حقن بيانات تجريبية للتقييمات والباقات الأربع"

    def handle(self, *args, **options):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "scripts"))
        from seed_assessments import run
        run()

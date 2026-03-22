from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "حقن كامل لجميع البيانات الحقيقية (موظفون + طلاب + خطة تشغيلية)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="تشغيل بدون طلب تأكيد",
        )

    def handle(self, *args, **options):
        import sys
        from pathlib import Path

        # تجاوز input() عند --no-input
        if options.get("no_input"):
            import builtins

            builtins.input = lambda _="": ""

        scripts_dir = str(Path(__file__).resolve().parent.parent.parent.parent / "scripts")
        sys.path.insert(0, scripts_dir)

        from real_seed import run as run_real_seed
        from seed_all import run_quality, run_real_seed
        from seed_quality import run as run_quality

        self.stdout.write("📥 الموظفون والطلاب...")
        run_real_seed()

        self.stdout.write("📋 الخطة التشغيلية...")
        run_quality()

        self.stdout.write(self.style.SUCCESS("✅ اكتمل الحقن الكامل!"))

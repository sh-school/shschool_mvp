from django.core.management.base import BaseCommand
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))


class Command(BaseCommand):
    help = "تهيئة البيانات التجريبية لمدرسة الشحانية"

    def handle(self, *args, **kwargs):
        from scripts.seed_data import run
        run()

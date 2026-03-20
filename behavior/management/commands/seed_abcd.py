"""
management command: python manage.py seed_abcd
يغذّي لائحة مخالفات ABCD الكاملة (20 مخالفة) من Ct.zip
"""
from django.core.management.base import BaseCommand
from behavior.models import ViolationCategory


class Command(BaseCommand):
    help = 'تغذية لائحة مخالفات ABCD (20 مخالفة) من Ct.zip'

    def handle(self, *args, **options):
        created = ViolationCategory.seed_abcd()
        total   = ViolationCategory.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f'✅ تم إضافة {created} مخالفة جديدة | الإجمالي: {total} مخالفة'
        ))

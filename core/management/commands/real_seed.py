"""
real_seed — يُعيد التوجيه لـ full_seed
احتفظ بهذا الملف للتوافق مع الإصدارات السابقة
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "مختصر لـ full_seed (للتوافق)"

    def handle(self, *args, **kwargs):
        call_command("full_seed")

from django.core.management.base import BaseCommand

from ux_survey.services import purge_old


class Command(BaseCommand):
    help = "يحذف إجاباتِ استبانة تجربة المستخدم الأقدمَ من 12 شهراً."

    def handle(self, *args, **options):
        self.stdout.write(f"حُذفت {purge_old()} إجابةً قديمة.")

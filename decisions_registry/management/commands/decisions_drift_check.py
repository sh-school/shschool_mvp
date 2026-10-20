from django.core.management.base import BaseCommand, CommandError

from decisions_registry.services import check_drift


class Command(BaseCommand):
    help = "يقارن بصماتِ جدول القرارات بالمخزَّنة؛ يفشل عند الانجراف"

    def handle(self, *args, **options):
        drifted = check_drift()
        if drifted:
            raise CommandError(f"انجرافُ {len(drifted)} قراراً (أوّلها {drifted[0]})")
        self.stdout.write("لا انجراف")

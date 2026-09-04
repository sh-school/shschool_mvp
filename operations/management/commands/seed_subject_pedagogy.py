"""بذرُ طبيعة الموادّ (ثقيلة / نشاط / عادية) من رمزها — idempotent.

    python manage.py seed_subject_pedagogy [--dry-run]

الحقلُ يقرؤه مختبرُ الجودة (التوقيت التربويّ)، ويُضبط بعد البذر من لوحة
الإدارة لمن أراد خلافَ القاعدة. ما ضُبط يدويّاً لا يُمَسّ: البذرُ يكتب فقط
حيث القيمةُ ما زالت الافتراضيّة «عادية».
"""

from django.core.management.base import BaseCommand

from operations.models import Subject

HEAVY = {"MAT", "SCI", "GSC", "PHY", "CHM", "BIO", "ARA", "ENG"}
ACTIVITY = {"PE", "ART", "TECH", "IT", "CS", "LFS"}


def pedagogy_for(code: str) -> str:
    code = (code or "").upper()
    if code in HEAVY:
        return "heavy"
    if code in ACTIVITY:
        return "activity"
    return "regular"


class Command(BaseCommand):
    help = "يضبط طبيعة كلّ مادّة من رمزها حيث ما زالت «عادية»"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        changed = 0
        for subject in Subject.objects.filter(pedagogy="regular").order_by("code"):
            wanted = pedagogy_for(subject.code)
            if wanted == "regular":
                continue
            self.stdout.write(f"  {subject.code:6} {subject.name_ar}: → {wanted}")
            if not opts["dry_run"]:
                subject.pedagogy = wanted
                subject.save(update_fields=["pedagogy"])
            changed += 1
        tag = "DRY-RUN" if opts["dry_run"] else "DONE"
        self.stdout.write(self.style.SUCCESS(f"{tag}: changed={changed}"))

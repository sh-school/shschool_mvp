"""
يستكمل سجلّاً مؤقّتاً ببيانات صاحبه الحقيقية.

    python manage.py complete_staff_record \\
        --placeholder "جمال صالح" \\
        --name "جمال صالح محمد ادم" \\
        --national-id 29273603822 \\
        --employee-number 197985 \\
        --apply

`create_placeholder_staff` يفتح سجلّاً بالاسم المختصر ورقمٍ مؤقّتٍ ظاهر
النقص، ليجد جدولُ الحصص معلّمَه. وهذا الأمر يُغلق تلك الحلقة.

ولا يمسّ إلّا سجلّاً مؤقّتاً: من كان رقمه الشخصيّ حقيقياً فبياناته جاءت من
شؤون الموظفين، ولا يُصحّح من سطر أوامر. والرقم الجديد يُرفض إن كان لغيره.

والحساب يُفعَّل — فصاحبه موظّفٌ حقيقيّ — ويبقى بلا كلمة مرورٍ صالحة: لا
يُدخَل به حتى تُصدَر له واحدة.

ولا يكتب شيئاً بلا `--apply`.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.management.commands.create_placeholder_staff import PLACEHOLDER_PREFIX
from core.models import CustomUser


class Command(BaseCommand):
    help = "يستكمل سجلّ معلّمٍ مؤقّت ببياناته الحقيقية"

    def add_arguments(self, parser):
        parser.add_argument("--placeholder", required=True, help="الاسم المختصر في السجلّ المؤقّت")
        parser.add_argument("--name", required=True, help="الاسم الكامل كما في الإقامة")
        parser.add_argument("--national-id", required=True, help="الرقم الشخصي")
        parser.add_argument("--employee-number", default="", help="الرقم الوظيفي لدى الوزارة")
        parser.add_argument("--nationality", default="", help="الجنسية")
        parser.add_argument("--apply", action="store_true", help="بدونه يعرض ولا يكتب")

    def handle(self, *args, **options):
        user = self._placeholder(options["placeholder"])
        national_id = options["national_id"].strip()
        employee_number = options["employee_number"].strip()

        self._reject_a_borrowed_identifier(CustomUser, "national_id", national_id, user)
        if employee_number:
            self._reject_a_borrowed_identifier(CustomUser, "employee_number", employee_number, user)

        self.stdout.write(f"\n{user.full_name}")
        self.stdout.write("═" * 52)
        self.stdout.write(f"  الاسم         {user.full_name}  ←  {options['name'].strip()}")
        self.stdout.write("  الرقم الشخصي   مؤقّت  ←  حقيقيّ")
        if employee_number:
            self.stdout.write(f"  الرقم الوظيفي  —  ←  {employee_number}")
        if options["nationality"]:
            self.stdout.write(f"  الجنسية        —  ←  {options['nationality'].strip()}")
        self.stdout.write("  الحساب         معطَّل  ←  مُفعَّل (بلا كلمة مرور بعد)")

        if not options["apply"]:
            self.stdout.write("\nعرضٌ فقط. أضف --apply للكتابة.\n")
            return

        with transaction.atomic():
            user.full_name = options["name"].strip()
            user.national_id = national_id
            user.employee_number = employee_number
            if options["nationality"]:
                user.nationality = options["nationality"].strip()
            user.is_active = True
            user.full_clean(exclude=["password"])
            user.save()

        self.stdout.write(self.style.SUCCESS("\nاكتمل السجلّ."))
        self.stdout.write(
            self.style.WARNING("ولا كلمة مرور له بعد — لا يُدخَل بالحساب حتى تُصدَر واحدة.")
        )

    # ── مساعدات ──────────────────────────────────────────────────────

    def _placeholder(self, name):
        """السجلّ المؤقّت وحده — ولا يُصحَّح سجلٌّ حقيقيّ من سطر أوامر."""
        user = CustomUser.objects.filter(full_name=name.strip()).first()
        if user is None:
            raise CommandError(f"لا سجلّ بهذا الاسم: {name}")
        if not user.national_id.startswith(PLACEHOLDER_PREFIX):
            raise CommandError(
                f"«{name}» سجلٌّ حقيقيٌّ لا مؤقّت — بياناته من شؤون الموظفين، " "ولا تُغيَّر من هنا."
            )
        return user

    def _reject_a_borrowed_identifier(self, model, field, value, user):
        """رقمٌ يحمله غيرُه ليس خطأ إدخالٍ وحده — قد يكون شخصاً آخر."""
        other = model.objects.filter(**{field: value}).exclude(pk=user.pk).first()
        if other is not None:
            raise CommandError(
                f"{model._meta.get_field(field).verbose_name} يحمله سجلٌّ آخر "
                f"({other.full_name}) — راجع البيانات."
            )

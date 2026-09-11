"""إصدارُ كلماتِ مرورٍ مؤقّتةٍ لمن يُعرَف في النظام ولا يدخل به.

    python manage.py issue_temporary_passwords
    python manage.py issue_temporary_passwords --apply

## العلّة

الحسابُ الذي يُنشئه استيرادُ كشف الكادر يُفتح **بلا كلمة مرورٍ صالحة** عمداً:
يُعرَف في النظام ولا يُدخَل به حتّى تُصدَر له واحدة. وهذا صوابٌ عند الإنشاء —
كلمةٌ تُولَّد لمن لا يعلم بها بعدُ خطرٌ لا خدمة. لكنّه يصير عطلاً حين يبقى:
موظّفٌ في السجلّ لا يبلغ المنصّةَ أبداً.

## والمؤقّتةُ مؤقّتةٌ بالبناء

`must_change_password` مرفوعٌ على كلّ من تُصدَر له — فأوّلُ دخولٍ يُلزمه
بتغييرها، ولا تبقى في يد من وزّعها. وهذا ما تقتضيه سياسةُ التدوير المعتمدة.

## والكلماتُ تُطبَع مرّةً واحدة

لا تُخزَّن في مكان، ولا تُكتب في سجلّ التدقيق — السجلُّ يقول **من** صدرت له
لا **ما** صدر. وهذا يعني أنّ المخرج نفسَه سرٌّ: يُقرأ ويُوزَّع ويُمسح، ولا
يُلصَق في تذكرةٍ ولا محادثة.

ومن نسي فلا استرجاع — تُصدَر له أخرى، وهو الصواب.

ولا يكتب شيئاً بلا `--apply`.
"""

import secrets

from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import School
from core.models.access import Membership
from core.models.audit import AuditLog
from core.models.user import CustomUser

#: أدوارٌ ليست كادراً — لا تُصدَر لها من هنا.
NOT_STAFF = ("student", "parent")

#: أبجديّةٌ بلا ملتبسٍ بصريّاً: لا O ولا 0 ولا l ولا 1 ولا I.
#: الكلمةُ تُقرأ من ورقةٍ وتُكتب بيدٍ، فحرفٌ يُخطئ فيه القارئُ بابٌ مغلق.
LETTERS_UPPER = "ABCDEFGHJKLMNPQRSTUVWXYZ"
LETTERS_LOWER = "abcdefghijkmnpqrstuvwxyz"
DIGITS = "23456789"
SYMBOLS = "!@#$%*-+=?"
LENGTH = 14


def make_password() -> str:
    """كلمةٌ تُرضي المدقّق بالبناء لا بالمحاولة: حرفٌ من كلّ صنفٍ ثمّ الباقي."""
    pools = (LETTERS_UPPER, LETTERS_LOWER, DIGITS, SYMBOLS)
    chars = [secrets.choice(pool) for pool in pools]
    everything = "".join(pools)
    chars += [secrets.choice(everything) for _ in range(LENGTH - len(pools))]
    # الخلطُ ضروريّ: بلا مزجٍ يقع الرمزُ رابعاً دائماً فيصير النمطُ معروفاً.
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


class Command(BaseCommand):
    help = "يُصدر كلماتِ مرورٍ مؤقّتةً لمن لا كلمةَ له — بلا كتابةٍ إلّا بـ--apply"

    def add_arguments(self, parser):
        parser.add_argument("--school", default="", help="رمزُ المدرسة — والافتراضُ الأولى")
        parser.add_argument(
            "--employee",
            default="",
            help="رقمٌ وظيفيٌّ بعينه — والافتراضُ كلُّ من لا كلمةَ له",
        )
        parser.add_argument("--apply", action="store_true", help="اكتب — والافتراضُ عرضٌ فقط")

    def handle(self, *args, **options):
        school = self._school(options["school"])

        staff = Membership.objects.filter(school=school, is_active=True).exclude(
            role__name__in=NOT_STAFF
        )
        people = CustomUser.objects.filter(id__in=staff.values("user_id"), is_active=True).order_by(
            "full_name"
        )
        if options["employee"]:
            people = people.filter(employee_number=options["employee"])

        needy = [user for user in people if not user.has_usable_password()]
        if not needy:
            self.stdout.write(self.style.SUCCESS("لا حسابَ بلا كلمة مرور — لا شيءَ يُصدَر."))
            return

        self.stdout.write(f"المدرسة: {school.name} · {len(needy)} حساباً بلا كلمة مرور:")
        for user in needy:
            self.stdout.write(f"  • {user.full_name} — الرقم الوظيفيّ {user.employee_number or '—'}")

        if not options["apply"]:
            self.stdout.write(self.style.WARNING("\nعرضٌ فقط — أضف --apply للإصدار"))
            return

        issued = []
        with transaction.atomic():
            for user in needy:
                password = make_password()
                validate_password(password, user)
                user.set_password(password)
                user.must_change_password = True
                user.save(update_fields=["password", "must_change_password"])
                issued.append((user, password))

            AuditLog.objects.create(
                school=school,
                user=None,
                action="update",
                model_name="other",
                object_id="",
                object_repr=f"إصدارُ {len(issued)} كلمةِ مرورٍ مؤقّتة"[:300],
                # السجلُّ يقول **من** صدرت له لا **ما** صدر: كلمةٌ في سجلّ
                # تدقيقٍ لا تُمحى كلمةٌ مكشوفةٌ إلى الأبد.
                changes={
                    "event": "temporary_passwords_issued",
                    "count": len(issued),
                    "people": [u.full_name for u, _ in issued],
                    "must_change_password": True,
                },
            )

        self.stdout.write(self.style.WARNING("\n" + "═" * 64))
        self.stdout.write(self.style.WARNING("  هذه الكلماتُ تُعرض مرّةً واحدة — ولا تُسترجَع"))
        self.stdout.write(self.style.WARNING("  وزّعها لأصحابها ثمّ امسح هذا المخرج"))
        self.stdout.write(self.style.WARNING("═" * 64 + "\n"))
        for user, password in issued:
            self.stdout.write(f"{user.employee_number or '—':>8}  {user.full_name:<34}  {password}")
        self.stdout.write(
            self.style.SUCCESS(f"\nصدرت {len(issued)} كلمة — وكلُّ صاحبٍ يُلزَم بتغييرها عند أوّل دخول.")
        )

    def _school(self, code: str) -> School:
        school = (
            (School.objects.filter(code=code) if code else School.objects.all())
            .order_by("id")
            .first()
        )
        if school is None:
            raise CommandError(f"لا مدرسةَ برمز {code}" if code else "لا مدرسةَ في القاعدة")
        return school

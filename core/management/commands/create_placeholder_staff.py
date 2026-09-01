"""
يُنشئ سجلّاً مؤقّتاً لموظّفٍ جديدٍ باسمه المختصر حتى تُستكمل بياناته.

    python manage.py create_placeholder_staff --name "جمال صالح" --apply
    python manage.py create_placeholder_staff --role nurse --name "أيمن" --apply

والدورُ الافتراضيّ `teacher`، فالمعلّم أكثرُ الحالات: يظهر في جدول الحصص
قبل أن يُدخل في المنصّة، فتسقط حصصه كلّها عند الاستيراد وتبقى شعبٌ بلا
مادّة. وسائرُ الأدوار مثله: اسمٌ يُعرَف في المدرسة قبل أن تكتمل أوراقه.
وهذا السجلّ يسدّ الفجوة حتى تُدخل شؤون الموظفين بياناته الكاملة.

وهو **ناقصٌ عمداً وظاهرُ النقص**:

    الرقم الشخصي   عشرون تسعةً وأصفاراً — لا يشبه رقماً قطرياً (أحدَ عشر
                   رقماً)، فلا يُقرأ يوماً على أنّه رقمٌ حقيقي
    الحساب         `is_active=False` وكلمةٌ غير صالحة — لا يُدخَل به
    الاسم          كما في الجدول، مختصراً

فلا يُختلق رقمٌ شخصيٌّ يشبه الحقيقيّ — واختلاقه في نظامٍ يخضع لقانون
حماية البيانات الشخصية أسوأ من نقصٍ معلَن.

ولا يكتب شيئاً بلا `--apply`، وهو مُعاوِد.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import CustomUser, School
from core.models.access import Membership, Role

#: بادئةٌ لا تشبه رقماً قطرياً: عشرون خانة تبدأ بتسعاتٍ تسع.
PLACEHOLDER_PREFIX = "999999999"
PLACEHOLDER_WIDTH = 20


class Command(BaseCommand):
    help = "يُنشئ سجلّاً مؤقّتاً لموظّفٍ جديد باسمه المختصر"

    def add_arguments(self, parser):
        parser.add_argument(
            "--name",
            action="append",
            required=True,
            metavar="اسم الموظّف",
            help='يُكرَّر لكل موظّف: --name "جمال صالح" --name "علي الطيطي"',
        )
        parser.add_argument(
            "--role",
            default="teacher",
            help="اسم الدور البرمجيّ — teacher افتراضاً، nurse للممرّض...",
        )
        parser.add_argument("--school", default=None, help="كود المدرسة")
        parser.add_argument("--apply", action="store_true", help="بدونه يعرض ولا يكتب")

    def handle(self, *args, **options):
        school = self._school(options["school"])
        names = [n.strip() for n in options["name"] if n.strip()]
        if not names:
            raise CommandError("لا اسم صالح في القائمة.")

        role_name = self._role_name(options["role"])
        role, _ = Role.objects.get_or_create(school=school, name=role_name)

        self.stdout.write(f"\n{school.name} — {dict(Role.ROLES)[role_name]}")
        self.stdout.write("═" * 52)

        existing = set(
            CustomUser.objects.filter(full_name__in=names).values_list("full_name", flat=True)
        )
        to_create = [n for n in names if n not in existing]

        for name in to_create:
            self.stdout.write(f"  + {name}   سجلّ مؤقّت، معطَّل حتى تُستكمل بياناته")
        for name in sorted(existing):
            self.stdout.write(f"  · {name}   قائمٌ أصلاً")

        self.stdout.write(f"\nستُنشأ {len(to_create)} · قائمة {len(existing)}")

        if not options["apply"]:
            self.stdout.write("عرضٌ فقط. أضف --apply للكتابة.\n")
            return

        with transaction.atomic():
            created = 0
            for name in to_create:
                user = CustomUser(
                    national_id=self._next_placeholder_id(),
                    full_name=name,
                    is_active=False,
                    must_change_password=True,
                )
                user.set_unusable_password()
                user.full_clean(exclude=["password"])
                user.save()
                Membership.objects.create(user=user, school=school, role=role)
                created += 1

        self.stdout.write(self.style.WARNING(f"\nأُنشئت {created} سجلّاً مؤقّتاً."))
        self.stdout.write(
            self.style.WARNING(
                "شؤون الموظفين تستكمل الاسم الرباعي والرقم الشخصي والبريد، ثمّ تُفعّل الحساب."
            )
        )

    # ── مساعدات ──────────────────────────────────────────────────────

    def _role_name(self, name):
        """يرفض دوراً لا وجود له في `Role.ROLES` بدل أن يخترع اسماً."""
        valid = dict(Role.ROLES)
        if name not in valid:
            raise CommandError(f"لا دور بالاسم «{name}». الأدوار: {'، '.join(sorted(valid))}")
        return name

    def _school(self, code):
        school = School.objects.filter(code=code).first() if code else School.objects.first()
        if school is None:
            raise CommandError("لا مدرسة بهذا الكود.")
        return school

    def _next_placeholder_id(self):
        """رقمٌ مؤقّتٌ تالٍ — يُقرأ من القاعدة فلا يصطدم بسابقٍ له."""
        used = CustomUser.objects.filter(national_id__startswith=PLACEHOLDER_PREFIX).values_list(
            "national_id", flat=True
        )
        taken = {int(n) for n in used if n.isdigit()}
        base = int(PLACEHOLDER_PREFIX.ljust(PLACEHOLDER_WIDTH, "0"))
        candidate = base + 1
        while candidate in taken:
            candidate += 1
        return str(candidate)

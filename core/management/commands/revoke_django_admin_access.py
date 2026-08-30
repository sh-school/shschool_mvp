"""
يُطفئ `is_staff` عمّن ليس من القيادة — فبابُ لوحة إدارة جانغو ليس للجميع.

    python manage.py revoke_django_admin_access --apply

`is_staff` محورٌ منفصلٌ عن أدوار المنصّة: لا يمنح صلاحيةً على بيانات، بل
يفتح `/admin/` — صفحةَ دخولٍ ثانية خارج تدفّق المنصّة. وقد وُجد على ١٢٩
حساباً في الإنتاج: اثنان وستّون معلّماً، وتسعةُ **أولياء أمور**، وأربعةٌ
فقط منهم قيادةٌ فعليّة.

ومصدرُه `full_seed` الذي يضع `is_staff=True` لكل من يُنشئه من الطاقم.

والضررُ اليوم محدود — ثلاثةُ حساباتٍ فقط تحمل صلاحياتٍ على النماذج،
والباقي يرى فهرساً فارغاً. لكنّ البابَ مفتوح: سطحُ هجومٍ بلا داعٍ، وأيُّ
صلاحيةٍ تُمنح لمجموعةٍ يوماً تسري عليهم جميعاً فوراً.

ولا يُمَسّ:
    superuser          مفاتيحُ النظام، وإطفاؤها يقفل الباب على أهله
    المدير والمطوّر    قرارُ المدرسة: الباب لهما

ولا يكتب شيئاً بلا `--apply`.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import CustomUser
from core.models.access import Membership

#: من يبقى له بابُ لوحة الإدارة: المدير والمطوّر، بقرار المدرسة.
#: ونوّابه لا يلزمهم: أدوارُهم في المنصّة تكفيهم، ولوحةُ جانغو تتجاوز
#: حرّاسها إلى الجداول نفسها.
ADMIN_SITE_ROLES = ("principal", "platform_developer")


class Command(BaseCommand):
    help = "يُطفئ is_staff عمّن ليس قيادةً — لوحة إدارة جانغو ليست للجميع"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="بدونه يعرض ولا يكتب")

    def handle(self, *args, **options):
        roles = {
            m.user_id: m.role.name
            for m in Membership.objects.filter(is_active=True).select_related("role")
        }
        staff = list(CustomUser.objects.filter(is_staff=True).order_by("full_name"))

        keep, revoke = [], []
        for user in staff:
            role = roles.get(user.id)
            if user.is_superuser or role in ADMIN_SITE_ROLES:
                keep.append((user, role))
            else:
                revoke.append((user, role))

        self.stdout.write(f"\nحسابات is_staff: {len(staff)}")
        self.stdout.write("═" * 52)

        self.stdout.write(f"\nيبقى لهم الباب ({len(keep)}):")
        for user, role in keep:
            mark = " · superuser" if user.is_superuser else ""
            self.stdout.write(f"  · {user.full_name} — {role or 'بلا عضوية'}{mark}")

        self.stdout.write(f"\nيُغلق عنهم ({len(revoke)}):")
        by_role: dict[str, int] = {}
        for _user, role in revoke:
            by_role[role or "بلا عضوية"] = by_role.get(role or "بلا عضوية", 0) + 1
        for role, count in sorted(by_role.items(), key=lambda kv: -kv[1]):
            self.stdout.write(f"  {role:22} {count}")

        if not options["apply"]:
            self.stdout.write("\nعرضٌ فقط. أضف --apply للكتابة.\n")
            return

        with transaction.atomic():
            CustomUser.objects.filter(id__in=[u.id for u, _ in revoke]).update(is_staff=False)

        self.stdout.write(self.style.SUCCESS(f"\nأُغلق الباب عن {len(revoke)} حساباً."))
        self.stdout.write("ولم تُمسّ أدوارُهم في المنصّة — `is_staff` محورٌ آخر.")

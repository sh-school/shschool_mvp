"""تسجيلُ مغادرة الكادر — نقلاً أو انتهاءَ خدمة.

من نُقل إلى مدرسةٍ أخرى يبقى في قوائم المدرسة بأصفارٍ في كلّ عمود، لأنّ
`Membership` كان يحمل تاريخَ التحاقٍ بلا نظير. وحذفُ العضويّة ليس جواباً:
أحدُ المنقولين له خمسٌ وعشرون حصّةً في جدول العام الماضي، فمحوُ عضويّته يقطع
تلك الحصص عن صاحبها.

فتُسجَّل المغادرةُ تاريخاً وسبباً ومرجعاً، وتُطفأ العضويّة معها.

    python manage.py record_staff_departure --school SHH --date 2026-08-01 \\
        --reference "قرار نقل 2026/44" --names names.txt --dry-run

وأسماءُ المغادرين تُقرأ من ملفٍّ سطراً سطراً، أو تُمرَّر بـ`--name` مكرّرةً.
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from core.models import CustomUser, Membership, School


class Command(BaseCommand):
    help = "يسجّل مغادرة موظّفين للكادر — بتاريخها وسببها ومرجعها."

    def add_arguments(self, parser):
        parser.add_argument("--school", default="SHH")
        parser.add_argument("--date", required=True, help="تاريخ المغادرة YYYY-MM-DD")
        parser.add_argument("--reference", required=True, help="مرجع القرار — إلزاميّ")
        parser.add_argument("--reason", default="transfer")
        parser.add_argument("--note", default="")
        parser.add_argument("--name", action="append", default=[], help="اسمٌ كاملٌ (يتكرّر)")
        parser.add_argument("--names", default="", help="ملفُّ أسماءٍ سطراً سطراً")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        school = School.objects.filter(code=opts["school"]).first()
        if school is None:
            raise CommandError(f"لا مدرسةَ بالكود {opts['school']}")
        try:
            on = date.fromisoformat(opts["date"])
        except ValueError as exc:
            raise CommandError(f"تاريخٌ غيرُ صالح: {opts['date']}") from exc

        names = list(opts["name"])
        if opts["names"]:
            with open(opts["names"], encoding="utf-8") as handle:
                names += [line.strip() for line in handle if line.strip()]
        if not names:
            raise CommandError("لا أسماء — مرّرها بـ--name أو --names")

        recorded = 0
        for name in names:
            user = CustomUser.objects.filter(full_name=name).first()
            if user is None:
                self.stdout.write(self.style.WARNING(f"لا موظّفَ بهذا الاسم: {name}"))
                continue
            rows = Membership.objects.filter(user=user, school=school, is_active=True)
            if not rows:
                self.stdout.write(f"{name}: لا عضويّةَ نشطةً — لا شيءَ يُسجَّل.")
                continue
            for membership in rows:
                self.stdout.write(f"{name} ({membership.role.name}) → غادر في {on}")
                if opts["dry_run"]:
                    continue
                membership.record_departure(
                    on=on,
                    reason=opts["reason"],
                    reference=opts["reference"],
                    note=opts["note"],
                )
                recorded += 1

        if opts["dry_run"]:
            self.stdout.write(self.style.WARNING("عرضٌ فقط — لم يُكتب شيء."))
        else:
            self.stdout.write(self.style.SUCCESS(f"سُجّلت {recorded} مغادرة."))

"""
مطابقةُ باقات شعب الثاني عشر القائمة بالقرار 14/2018 (المادّة 3 «ثالثاً»، 2018/06/06).

الثاني عشر: P2 = اختبارُ نهاية الفصل الأول (40)، وP4 = اختبارُ نهاية الفصل
الثاني (60) — لا P1 ولا P3 ولا AW. والباقاتُ المنشأةُ قبل التصحيح على بنية
الصفوف الأخرى تُحذف (إن كانت فارغة) ويُعاد وزنُ P2/P4 إلى 100٪.

    python manage.py fix_grade12_packages            # عرضٌ فقط (--dry-run)
    python manage.py fix_grade12_packages --apply    # تطبيق
    python manage.py fix_grade12_packages --revert --apply   # تراجع

ولِمَ أمرٌ لا هجرة: الهجرةُ تجري آليّاً في النشر، وهذا العملُ يجب أن **يقف** إن
وُجدت تقييماتٌ مرصودة على P1/P3/AW — فحذفُها قرارُ مالك. الإعدادُ المحجوب لا يُمسّ
أبداً، ويُعرض بعدد تقييماته ودرجاته، ويخرج الأمرُ برمزٍ غير صفريّ.
"""

from django.core.management.base import BaseCommand, CommandError

from assessments.services import Grade12PackageFix


class Command(BaseCommand):
    help = "مطابقةُ باقات الثاني عشر بالقرار 14/2018 (P2=40، P4=60 فقط) — عرضٌ ما لم يُطلب --apply"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="عرضُ ما سيتغيّر (الافتراض)")
        parser.add_argument("--apply", action="store_true", help="تطبيقُ التغيير")
        parser.add_argument("--revert", action="store_true", help="إعادةُ البنية العامّة (تراجع)")

    def handle(self, *args, **options):
        apply = options["apply"] and not options["dry_run"]
        if options["revert"]:
            return self._revert(apply)

        plans = Grade12PackageFix.plan()
        pending = [p for p in plans if p.changes]
        blocked = [p for p in pending if p.blocked]
        clean = [p for p in pending if not p.blocked]
        n_extra = sum(len(p.extra) for p in clean)
        n_reweight = sum(len(p.reweight) for p in clean)

        self.stdout.write(
            f"إعداداتُ الثاني عشر: {len(plans)} · تحتاج تصحيحاً: {len(pending)} "
            f"(نظيفة {len(clean)}، محجوبة {len(blocked)})"
        )
        self.stdout.write(f"باقاتٌ زائدة تُحذف: {n_extra} · باقاتٌ يُعاد وزنُها: {n_reweight}")
        for p in clean:
            extra = ", ".join(f"{x.semester}/{x.package_type}" for x in p.extra) or "—"
            rew = ", ".join(f"{x.semester}/{x.package_type} {x.weight}→{w}" for x, w in p.reweight)
            self.stdout.write(f"  • {p.setup}: حذف [{extra}] · وزن [{rew or '—'}]")
        for p in blocked:
            self.stdout.write(
                self.style.WARNING(
                    f"  ⛔ {p.setup}: {p.blocking_assessments} تقييماً و{p.blocking_grades} "
                    "درجةً على P1/P3/AW — لا يُمسّ (قرارُ مالك)"
                )
            )

        if not apply:
            self.stdout.write("عرضٌ فقط — لم يتغيّر شيء. أعِد بـ--apply للتطبيق.")
        else:
            for p in clean:
                Grade12PackageFix.apply(p)
            self.stdout.write(self.style.SUCCESS(f"طُبِّق على {len(clean)} إعداداً."))
        if blocked:
            raise CommandError(f"{len(blocked)} إعداداً محجوباً بدرجاتٍ مرصودة — راجع القائمة.")

    def _revert(self, apply):
        setups = list(Grade12PackageFix.setups())
        self.stdout.write(f"تراجع: {len(setups)} إعداداً من الثاني عشر يعود إلى البنية العامّة.")
        if not apply:
            self.stdout.write("عرضٌ فقط — أعِد بـ--revert --apply للتطبيق.")
            return
        for setup in setups:
            touched = Grade12PackageFix.revert(setup)
            self.stdout.write(f"  • {setup}: {', '.join(touched) or 'لا تغيير'}")

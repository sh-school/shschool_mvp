"""
مطابقةُ باقات شعب الثاني عشر القائمة بالقرار 14/2018 (المادّة 3 «ثالثاً»، 2018/06/06).

الثاني عشر: P2 = اختبارُ نهاية الفصل الأول (40)، وP4 = اختبارُ نهاية الفصل
الثاني (60) — لا P1 ولا P3 ولا AW. والباقاتُ المنشأةُ قبل التصحيح على بنية
الصفوف الأخرى تُحذف (إن كانت فارغة) ويُعاد وزنُ P2/P4 إلى 100٪.

    python manage.py fix_grade12_packages                                  # عرضٌ فقط
    python manage.py fix_grade12_packages --apply --actor <الرقم الشخصي>    # تطبيق
    python manage.py fix_grade12_packages --revert --apply --actor <…>     # تراجع

النطاقُ العامُ الجاري لكلّ مدرسة (و`--school` لمدرسةٍ واحدة) — لا يُمسّ عامٌ مُغلق.
والفاعلُ إلزاميٌّ للتطبيق والتراجع: يُكتب في سجلّ المراجعة.

ولِمَ أمرٌ لا هجرة: الهجرةُ تجري آليّاً في النشر، وهذا العملُ يجب أن **يقف** إن
وُجدت تقييماتٌ مرصودة على P1/P3/AW — فحذفُها قرارُ مالك. الإعدادُ المحجوب لا يُمسّ
أبداً — ويُعاد فحصُه تحت القفل لحظةَ التطبيق — ويخرج الأمرُ برمزٍ غير صفريّ.
والتراجعُ يستعيد ما سجّله التطبيقُ نفسُه، ويقف عند إعدادٍ رُصدت فيه درجاتٌ بعده.
"""

from django.core.management.base import BaseCommand, CommandError

from assessments.services import Grade12BlockedError, Grade12PackageFix


class Command(BaseCommand):
    help = "مطابقةُ باقات الثاني عشر بالقرار 14/2018 (P2=40، P4=60 فقط) — عرضٌ ما لم يُطلب --apply"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="عرضُ ما سيتغيّر (الافتراض)")
        parser.add_argument("--apply", action="store_true", help="تطبيقُ التغيير")
        parser.add_argument("--revert", action="store_true", help="التراجعُ عمّا طبّقه --apply")
        parser.add_argument("--actor", help="الرقمُ الشخصيّ لمن ينفّذ — إلزاميٌّ مع --apply")
        parser.add_argument("--school", help="رمزُ مدرسةٍ واحدة (الافتراض: كلُّ المدارس)")

    def handle(self, *args, **options):
        from core.models import CustomUser, School

        apply = options["apply"] and not options["dry_run"]
        actor = None
        if apply:
            if not options["actor"]:
                raise CommandError("--actor إلزاميٌّ للتطبيق: من ينفّذ يُكتب في سجلّ المراجعة.")
            actor = CustomUser.objects.filter(national_id=options["actor"]).first()
            if actor is None:
                raise CommandError("--actor: لا مستخدمَ بهذا الرقم الشخصيّ.")
        school = None
        if options["school"]:
            school = School.objects.filter(code=options["school"]).first()
            if school is None:
                raise CommandError(f"--school: لا مدرسةَ برمز {options['school']}.")
        setups = Grade12PackageFix.setups(school)
        if options["revert"]:
            return self._revert(setups, apply, actor)

        plans = Grade12PackageFix.plan(setups)
        pending = [p for p in plans if p.changes]
        blocked = [p for p in pending if p.blocked]
        clean = [p for p in pending if not p.blocked]
        n_extra = sum(len(p.extra) for p in clean)
        n_reweight = sum(len(p.reweight) for p in clean)

        self.stdout.write(
            f"إعداداتُ الثاني عشر (العامُ الجاري): {len(plans)} · تحتاج تصحيحاً: {len(pending)} "
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
            self.stdout.write("عرضٌ فقط — لم يتغيّر شيء. أعِد بـ--apply --actor للتطبيق.")
            if blocked:
                raise CommandError(f"{len(blocked)} إعداداً محجوباً بدرجاتٍ مرصودة — راجع القائمة.")
            return
        done = 0
        for p in clean:
            try:
                Grade12PackageFix.apply(p.setup, actor)
                done += 1
            except Grade12BlockedError as exc:
                blocked.append(p)
                self.stdout.write(self.style.WARNING(f"  ⛔ رُصد عليه بعد العرض: {exc}"))
        self.stdout.write(self.style.SUCCESS(f"طُبِّق على {done} إعداداً."))
        if blocked:
            raise CommandError(f"{len(blocked)} إعداداً محجوباً بدرجاتٍ مرصودة — راجع القائمة.")

    def _revert(self, setups, apply, actor):
        targets = [s for s in setups if Grade12PackageFix.pending_revert(s) is not None]
        self.stdout.write(f"تراجع: {len(targets)} إعداداً طبّق عليه --apply ولم يُتراجَع عنه.")
        if not apply:
            self.stdout.write("عرضٌ فقط — أعِد بـ--revert --apply --actor للتطبيق.")
            return
        blocked = 0
        for setup in targets:
            try:
                touched = Grade12PackageFix.revert(setup, actor)
                self.stdout.write(f"  • {setup}: {', '.join(touched) or 'لا تغيير'}")
            except Grade12BlockedError as exc:
                blocked += 1
                self.stdout.write(self.style.WARNING(f"  ⛔ {exc}"))
        if blocked:
            raise CommandError(f"{blocked} إعداداً لم يُتراجَع عنه: رُصدت فيه درجاتٌ بعد التطبيق.")

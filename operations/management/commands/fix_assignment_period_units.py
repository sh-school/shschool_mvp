"""
توحيدُ وحدة القياس في `SubjectClassAssignment.weekly_periods`.

    python manage.py fix_assignment_period_units --year 2026-2027 [--apply]

الحقلُ يعدّ **الحصص**، إلّا في سبعةَ عشرَ سجلّاً يعدّ فيها **الكتلَ المزدوجة**:
الفنونُ في الإعداديّ أُدخلت `1` وتُجدوَل حصّتين متلاصقتين، وعلومُ الحاسب
وتكنولوجيا المعلومات في 11/4 و12/4 أُدخلت `2` وتُجدوَل أربعاً في كتلتين.

    Single Semantic Source: حقلٌ واحدٌ ← وحدةُ قياسٍ واحدة

ولا يعمل هذا الأمرُ باستدلالٍ عامّ من نوع «كلُّ سجلٍّ مجدولُه ضعفُ مُسنَده
يُصحَّح». فقاعدةٌ كهذه تصلح غداً سجلّاً ليس فيه خللٌ أصلاً، وقد يكون ضِعفُه
قراراً إداريّاً. بل ثمّةَ **قائمةٌ مثبَّتةٌ مسبقاً** في `CANDIDATES`، وكلُّ ما
خرج عنها يُوقف `--apply` ولا يُصحَّح.

ولا يدخل في شرطه «هل يعبر الزوجُ فسحةً؟». فذلك سؤالُ **صلاحيةِ ترتيبِ
الجدول**، لا سؤالُ **وحدةِ عدِّ الحصص**؛ وهو موقوفٌ حتى يصير تقويمُ الحصص
مُدرِكاً للمرحلة (`TimeSlotConfig` اليومَ لا يحمل `level_type` أصلاً).

والأمرُ متعادِلٌ (idempotent): تشغيلُه بعد النجاح يجد صفرَ مرشَّحين.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

#: القائمةُ المثبَّتة: (كود المادّة، الصفوف، المُسنَدُ الآن، المُجدوَلُ المتوقَّع)
CANDIDATES = (
    ("ART", frozenset({"G7", "G8", "G9"}), 1, 2),
    ("CS", frozenset({"G11", "G12"}), 2, 4),
    ("IT", frozenset({"G11", "G12"}), 2, 4),
)

EXPECTED_TOTAL = 17


class Command(BaseCommand):
    help = "يوحّد وحدةَ القياس في weekly_periods للسجلّات السبعةَ عشرَ المثبَّتة"

    def add_arguments(self, parser):
        parser.add_argument("--year", required=True)
        parser.add_argument("--school", default=None)
        parser.add_argument("--apply", action="store_true", help="بدونها: قراءةٌ فقط")

    def handle(self, *args, **options):
        from operations.models import ScheduleSlot, SubjectClassAssignment

        school = self._school(options["school"])
        year = options["year"]
        w = self.stdout.write

        assignments = list(
            SubjectClassAssignment.objects.filter(
                school=school, academic_year=year, is_active=True
            ).select_related("class_group", "subject", "teacher")
        )
        if not assignments:
            raise CommandError(f"لا إسناداتٍ نشطةً في {year}.")

        scheduled = {}
        teachers_in_schedule = {}
        for slot in ScheduleSlot.objects.filter(
            school=school, academic_year=year, is_active=True
        ).select_related("teacher"):
            key = (slot.class_group_id, slot.subject_id)
            scheduled[key] = scheduled.get(key, 0) + 1
            teachers_in_schedule.setdefault(key, set()).add(slot.teacher_id)

        candidates, ambiguous, mismatches, settled = [], [], [], 0
        assigned_before = 0
        for a in assignments:
            assigned_before += a.weekly_periods
            key = (a.class_group_id, a.subject_id)
            found = scheduled.get(key, 0)
            rule = self._rule(a)

            if found == a.weekly_periods:
                # مستقرٌّ أصلاً — والتعادلُ يقتضي ألّا يُوصف بالالتباس بعد نجاحٍ سابق.
                settled += 1
                continue

            if rule is None:
                ambiguous.append((a, found, "خارج القائمة المثبَّتة"))
                continue

            _, _, expect_assigned, expect_scheduled = rule
            if a.weekly_periods != expect_assigned or found != expect_scheduled:
                ambiguous.append(
                    (
                        a,
                        found,
                        f"المتوقَّع {expect_assigned}←{expect_scheduled}, والواقع {a.weekly_periods}←{found}",
                    )
                )
                continue

            slot_teachers = teachers_in_schedule.get(key, set())
            if slot_teachers != {a.teacher_id}:
                mismatches.append((a, found, "معلّمُ الجدول يخالف معلّمَ الإسناد"))
                continue

            candidates.append((a, found))

        self._report(w, candidates, ambiguous, mismatches, assigned_before, scheduled, settled)

        blocked = bool(ambiguous or mismatches) or len(candidates) != EXPECTED_TOTAL
        if not candidates and not ambiguous and not mismatches:
            w(self.style.SUCCESS("\nلا شيءَ يُصحَّح — الحقلُ متّسقٌ في كلّ سجلّ.\n"))
            return
        if not options["apply"]:
            w(self.style.WARNING("\nقراءةٌ فقط — أعد التشغيل بـ --apply للكتابة.\n"))
            return
        if blocked:
            raise CommandError(
                "الكتابةُ ممنوعة: ظهر ما يخرج عن القائمة المثبَّتة أو عدمُ تطابق. لا يُصحَّح شيء."
            )

        with transaction.atomic():
            for a, found in candidates:
                a.weekly_periods = found
                a.save(update_fields=["weekly_periods"])
        w(self.style.SUCCESS(f"\nصُحِّح {len(candidates)} سجلّاً.\n"))

    # ── مساعدات ──────────────────────────────────────────────────────

    def _rule(self, assignment):
        code = assignment.subject.code or ""
        grade = assignment.class_group.grade or ""
        for rule in CANDIDATES:
            if rule[0] == code and grade in rule[1]:
                return rule
        return None

    def _report(self, w, candidates, ambiguous, mismatches, assigned_before, scheduled, settled):
        scheduled_total = sum(scheduled.values())
        delta = sum(found - a.weekly_periods for a, found in candidates)

        w("\n── وحدةُ القياس في weekly_periods ──")
        w(f"  {len(candidates)} candidates")
        w(f"  {settled} already consistent")
        w(f"  {len(ambiguous)} ambiguous")
        w(f"  {sum(1 for _ in mismatches)} teacher/subject/class mismatches")
        w(f"  assigned_total_before = {assigned_before}")
        w(f"  assigned_total_after  = {assigned_before + delta}")
        w(f"  scheduled_total       = {scheduled_total}")

        if candidates:
            w(f"\n  {'الشعبة':<9}{'المادّة':<8}{'مُسنَد':>7}{'مُجدوَل':>8}  المعلّم")
            for a, found in sorted(
                candidates, key=lambda p: (p[0].subject.code or "", str(p[0].class_group.grade))
            ):
                cg = a.class_group
                section = f"{(cg.grade or '').removeprefix('G')}/{cg.section}"
                w(
                    f"  {section:<9}{a.subject.code or '—':<8}{a.weekly_periods:>7}{found:>8}"
                    f"  {a.teacher.full_name if a.teacher else '—'}"
                )
        for group, label in ((ambiguous, "ملتبس"), (mismatches, "عدمُ تطابق")):
            for a, found, why in group:
                cg = a.class_group
                section = f"{(cg.grade or '').removeprefix('G')}/{cg.section}"
                w(
                    self.style.ERROR(
                        f"  [{label}] {section} {a.subject.name_ar} "
                        f"[{a.subject.code or 'بلا كود'}] مُسنَد {a.weekly_periods} مُجدوَل {found}: {why}"
                    )
                )

        if candidates and len(candidates) != EXPECTED_TOTAL:
            w(
                self.style.ERROR(
                    f"\n  العددُ المتوقَّع {EXPECTED_TOTAL} والموجود {len(candidates)} — لا كتابة."
                )
            )

    def _school(self, code):
        from core.models import School

        if code:
            try:
                return School.objects.get(code=code)
            except School.DoesNotExist as exc:
                raise CommandError(f"لا مدرسة بهذا الكود: {code}") from exc
        schools = list(School.objects.all()[:2])
        if len(schools) != 1:
            raise CommandError("أكثرُ من مدرسة — حدّد --school.")
        return schools[0]

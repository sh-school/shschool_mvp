"""بذرُ أجنحة المدرسة الخمسة ونسبةُ الشُّعب إليها — idempotent.

    python manage.py seed_wings [--dry-run]
    python manage.py seed_wings --assign [--dry-run]

المصدر: قرارُ الإدارة 2026-09-09 (وتصحيحُ 10/1 ← 10/4 في جناح 4)، الموثَّق في
`AAdocs/claude/roadmap/خارطة_طريق_المشرف_الإداري_2026-09.md` §1 القرار 2.

    الطابق الأرضيّ
      جناح 1   7/1 · 7/2 · 7/3 · 7/4 · 8/1
      جناح 2   8/2 · 8/3 · 8/4 · 9/1 · 9/2
    الطابق الأوّل
      جناح 3   9/3 · 9/4 · 10/1 · 10/2 · 10/3
      جناح 4   10/4 · 11/1 · 11/2 · 11/3 · 11/4
      جناح 5   11/5 · 12/1 · 12/2 · 12/3 · 12/4

خمسٌ وعشرون شعبةً بلا تكرارٍ ولا فراغ. وشُعبُ التربية الخاصّة الثلاث
(8/ESE · 9/ESE · 10/ESE) **خارجَ الأجنحة بقرارٍ صريح** — حضورُها بيد معلّمي
التربية الخاصّة. فتُترك بلا جناحٍ وتُسمّى في التقرير: الفارغُ المقصودُ يُكتب
ولا يُترك سكوتاً يظنّه القارئُ بعد سنةٍ خللاً في البيانات.

## المشرفون لا يُبذرون

الجدولُ هنا يقول **أيُّ شعبةٍ في أيّ جناح** — لا **من يشرف عليه**. أسماءُ
المشرفين الخمسة قرارٌ إداريٌّ لم يُسمَّ بعد، وبذرُ اسمٍ مخمَّنٍ أسوأُ من تركِ
الخانة فارغة: الفارغُ يُرى ويُسأل عنه، والمخمَّنُ يُصدَّق. تُعيَّن من لوحة
الإدارة، والنموذجُ يرفض من ليس مشرفاً إداريّاً ولا نائباً إداريّاً.

## ولا يكتب سطراً بلا `--assign`

`seed_wings` وحدَه يُنشئ الأجنحةَ الخمسة ويعرض ما ستؤول إليه نسبةُ الشُّعب.
و`--assign` ينسبها. و`--dry-run` يتراجع عن كلّ شيءٍ بعد عرضه.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from core.academic_calendar import academic_year_for_school
from core.models import ClassGroup, School, Wing

#: (الرمز، الاسم، الطابق، الترتيب، شُعبُه)
#: والشعبةُ زوجٌ (الصفّ، الشعبة) كما تُخزَّن: «G7» و«1».
WINGS = [
    (
        "w1",
        "جناح 1",
        "ground",
        1,
        [("G7", "1"), ("G7", "2"), ("G7", "3"), ("G7", "4"), ("G8", "1")],
    ),
    (
        "w2",
        "جناح 2",
        "ground",
        2,
        [("G8", "2"), ("G8", "3"), ("G8", "4"), ("G9", "1"), ("G9", "2")],
    ),
    (
        "w3",
        "جناح 3",
        "first",
        3,
        [("G9", "3"), ("G9", "4"), ("G10", "1"), ("G10", "2"), ("G10", "3")],
    ),
    (
        "w4",
        "جناح 4",
        "first",
        4,
        [("G10", "4"), ("G11", "1"), ("G11", "2"), ("G11", "3"), ("G11", "4")],
    ),
    (
        "w5",
        "جناح 5",
        "first",
        5,
        [("G11", "5"), ("G12", "1"), ("G12", "2"), ("G12", "3"), ("G12", "4")],
    ),
]

#: شُعبٌ خارجَ الأجنحة بقرارٍ لا بسهو — تُسمّى ولا تُنسب.
EXCLUDED_SECTION = "ESE"


def wing_of_section() -> dict:
    """(الصفّ، الشعبة) → رمزُ الجناح — مبنيٌّ من `WINGS` كي لا يُكتب الجدولُ مرّتين."""
    return {pair: code for code, _n, _f, _o, pairs in WINGS for pair in pairs}


class Command(BaseCommand):
    help = "بذرُ الأجنحة الخمسة ونسبةُ الشُّعب الخمس والعشرين إليها — idempotent"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="اعرضْ ولا تكتبْ")
        parser.add_argument(
            "--assign",
            action="store_true",
            help="انسبِ الشُّعبَ إلى أجنحتها أيضاً — والافتراضُ إنشاءُ الأجنحة وعرضُ الخطّة",
        )

    def handle(self, *args, **opts):
        created = updated = unchanged = 0
        for school in School.objects.all():
            with transaction.atomic():
                wings = {}
                for code, name, floor, order, _pairs in WINGS:
                    year = academic_year_for_school(school)
                    wing, was_created = Wing.objects.get_or_create(
                        school=school,
                        code=code,
                        academic_year=year,
                        defaults={"name": name, "floor": floor, "order": order},
                    )
                    wings[code] = wing
                    if was_created:
                        created += 1
                    elif (wing.name, wing.floor, wing.order) != (name, floor, order):
                        wing.name, wing.floor, wing.order = name, floor, order
                        wing.save(update_fields=["name", "floor", "order"])
                        updated += 1
                    else:
                        unchanged += 1

                self.stdout.write(f"== {school.name} · {academic_year_for_school(school)}")
                moved, kept, orphans, excluded = self._plan(school, wings, opts["assign"])
                for line in moved:
                    self.stdout.write(f"   → {line}")
                for line in excluded:
                    self.stdout.write(f"   · خارجَ الأجنحة بقرار: {line}")
                for line in orphans:
                    self.stdout.write(self.style.WARNING(f"   ! شعبةٌ بلا جناحٍ في الجدول: {line}"))
                verb = "نُسبت" if opts["assign"] and not opts["dry_run"] else "ستُنسب"
                self.stdout.write(
                    f"   {verb} {len(moved)} شعبة، وعلى حالها {len(kept)}، "
                    f"ومستثناةٌ {len(excluded)}، وبلا جناح {len(orphans)}."
                )
                if opts["dry_run"]:
                    transaction.set_rollback(True)

        tag = "DRY-RUN — لم يُكتب شيء" if opts["dry_run"] else "DONE"
        note = "" if opts["assign"] else " · أضِف --assign لنسبة الشُّعب"
        self.stdout.write(
            self.style.SUCCESS(
                f"{tag}: أجنحةٌ created={created} updated={updated} unchanged={unchanged}{note}"
            )
        )

    def _plan(self, school, wings, do_assign):
        """يُرجع (ما نُقل أو يُنقل، ما هو على حاله، بلا جناحٍ في الجدول، مستثنىً)."""
        year = academic_year_for_school(school)
        table = wing_of_section()
        moved, kept, orphans, excluded = [], [], [], []

        for klass in (
            ClassGroup.objects.filter(school=school, academic_year=year, is_active=True)
            .select_related("wing")
            .in_school_order()
        ):
            label = f"{klass.grade.removeprefix('G')}/{klass.section}"
            now = klass.wing.code if klass.wing_id else "—"
            code = table.get((klass.grade, klass.section))

            if klass.section == EXCLUDED_SECTION:
                excluded.append(label)
                continue
            if code is None:
                orphans.append(f"{label} (جناحُها الآن: {now})")
                continue
            if now == code:
                kept.append(label)
                continue

            moved.append(f"{label}: {now} ← {code}")
            if do_assign:
                ClassGroup.objects.filter(pk=klass.pk).update(wing=wings[code])

        return moved, kept, orphans, excluded

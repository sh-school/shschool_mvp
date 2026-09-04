"""مختبرُ جودة الجدول من سطر الأوامر: قياسٌ ومقارنةٌ وحفظُ أساس.

    python manage.py schedule_lab --live                       # الجدول الحيّ
    python manage.py schedule_lab --generation <id>            # مسودّةٌ أو توليد
    python manage.py schedule_lab --live --compare baseline    # مقابل آخر أساس
    python manage.py schedule_lab --generation <id> --compare live
    python manage.py schedule_lab --live --save-baseline "أساس 2026-09"
    python manage.py schedule_lab --generation <id> --store    # يحفظ المؤشرات في صفّ التوليد
    ... [--json تقرير.json] [--school SHH] [--year 2026-2027]

القراءةُ لا تكتب شيئاً إلّا بـ`--save-baseline` أو `--store`.
"""

import json

from django.core.management.base import BaseCommand, CommandError

from core.academic_calendar import academic_year_for_school
from core.models import School
from operations.models import ScheduleBaseline, ScheduleGeneration
from operations.schedule_lab import ScheduleLab, compare, latest_baseline


class Command(BaseCommand):
    help = "يقيس مؤشرات جودة جدولٍ (حيّ أو توليد) ويقارنه بأساسٍ أو بجدولٍ آخر"

    def add_arguments(self, parser):
        parser.add_argument("--school", default=None, help="كود المدرسة (وإلّا الأولى)")
        parser.add_argument("--year", default="", help="العام الدراسيّ")
        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument("--live", action="store_true", help="الجدول الحيّ")
        target.add_argument("--generation", default="", help="معرّف التوليد (أو أوّل حروفه)")
        parser.add_argument(
            "--compare", default="", help="live أو baseline أو baseline:<اسم> أو معرّف توليد"
        )
        parser.add_argument("--save-baseline", default="", help="يحفظ القياس أساساً بهذا الاسم")
        parser.add_argument("--store", action="store_true", help="يحفظ المؤشرات في صفّ التوليد")
        parser.add_argument("--json", default="", help="يكتب التقرير الكامل JSON")

    def handle(self, *args, **opts):
        school = (
            School.objects.filter(code=opts["school"]).first()
            if opts["school"]
            else School.objects.first()
        )
        if school is None:
            raise CommandError("لا مدرسة")
        year = opts["year"] or academic_year_for_school(school)

        generation = None
        if opts["generation"]:
            generation = self._generation(school, year, opts["generation"])
            lab = ScheduleLab.for_generation(generation)
            title = f"التوليد {str(generation.id)[:8]} ({generation.get_status_display()})"
        else:
            lab = ScheduleLab.for_live(school, year)
            title = "الجدول الحيّ"
        metrics = lab.compute()

        baseline_metrics, baseline_title = self._reference(school, year, opts["compare"])
        rows = compare(metrics, baseline_metrics)

        self.stdout.write(f"== {school.name} — {year} — {title}")
        if baseline_title:
            self.stdout.write(f"   مقابل: {baseline_title}")
        width = max(len(r["label"]) for r in rows) + 2
        for r in rows:
            value = "—" if r["value"] is None else r["value"]
            line = f"  {r['label']:<{width}} {value!s:>8} {r['unit']}"
            if baseline_metrics:
                base = "—" if r["baseline"] is None else r["baseline"]
                delta = "" if r["delta"] is None else f" ({r['delta']:+})"
                mark = {"better": "▲", "worse": "▼"}.get(r["verdict"], " ")
                line += f"   الأساس {base!s:>8}{delta} {mark}"
            self.stdout.write(line)
            if r["key"] in ("validity.hard_conflicts", "fairness.stress") and r["detail"]:
                self.stdout.write(f"      {json.dumps(r['detail'], ensure_ascii=False)}")

        if opts["store"]:
            if generation is None:
                raise CommandError("--store يحتاج --generation")
            generation.metrics = metrics
            generation.save(update_fields=["metrics"])
            self.stdout.write(self.style.SUCCESS("حُفظت المؤشرات في صفّ التوليد."))
        if opts["save_baseline"]:
            obj, created = ScheduleBaseline.objects.update_or_create(
                school=school,
                academic_year=year,
                label=opts["save_baseline"],
                defaults={"metrics": metrics},
            )
            self.stdout.write(
                self.style.SUCCESS(f"{'أُنشئ' if created else 'حُدّث'} الأساس «{obj.label}».")
            )
        if opts["json"]:
            with open(opts["json"], "w", encoding="utf-8") as fh:
                json.dump(
                    {"title": title, "metrics": metrics, "rows": rows},
                    fh,
                    ensure_ascii=False,
                    indent=2,
                )
            self.stdout.write(f"كُتب {opts['json']}")

    def _generation(self, school, year, ident):
        qs = ScheduleGeneration.objects.filter(school=school, academic_year=year)
        obj = (
            qs.filter(id__startswith=ident).first()
            if len(ident) < 32
            else qs.filter(id=ident).first()
        )
        if obj is None:
            raise CommandError(f"لا توليدَ يبدأ بـ{ident}")
        return obj

    def _reference(self, school, year, spec):
        if not spec:
            return None, ""
        if spec == "live":
            return ScheduleLab.for_live(school, year).compute(), "الجدول الحيّ"
        if spec.startswith("baseline"):
            label = spec.partition(":")[2]
            obj = (
                ScheduleBaseline.objects.filter(
                    school=school, academic_year=year, label=label
                ).first()
                if label
                else latest_baseline(school, year)
            )
            if obj is None:
                raise CommandError("لا أساسَ محفوظاً — احفظ واحداً بـ--save-baseline")
            return obj.metrics, f"الأساس «{obj.label}» ({obj.created_at:%Y-%m-%d})"
        gen = self._generation(school, year, spec)
        return ScheduleLab.for_generation(gen).compute(), f"التوليد {str(gen.id)[:8]}"

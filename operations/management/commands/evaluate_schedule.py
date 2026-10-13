"""المُقيِّمُ المستقلّ للجدول من سطر الأوامر (V2-S1، ADR-0008).

    python manage.py evaluate_schedule --live                    # الجدول الحيّ المعتمَد
    python manage.py evaluate_schedule --generation <id>         # مسودّةٌ أو توليد
    python manage.py evaluate_schedule --slots-json ناتج.json     # حلّالٌ خارجيّ بالمعرّفات
    ... [--school SHH] [--year 2026-2027] [--json تقرير.json]

القراءةُ لا تكتب شيئاً في القاعدة. والمخرجُ بمعرّفاتٍ مختصرةٍ لا أسماء. ويخرج بالرمز 1 إن لم يُقبَل الجدول
(حصّةٌ بلا موضع أو مخالفةٌ صلبة أو خانةٌ بلا إسناد) ليصلح خطوةً في بوّابة.
"""

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from core.academic_calendar import academic_year_for_school
from core.models import School
from operations.models import ScheduleGeneration
from operations.schedule_evaluator import (
    EvaluatorInputError,
    evaluate_slots,
    generation_slots,
    live_slots,
    relaxations_from_payload,
    slots_from_payload,
)


class Command(BaseCommand):
    help = "يقيّم جدولاً (حيّاً أو مسودّةً أو ناتجَ حلّالٍ خارجي) مستقلّاً عن الباني ولا يكتب شيئاً"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--school", default=None, help="كود المدرسة (وإلّا الأولى)")
        parser.add_argument("--year", default="", help="العام الدراسيّ")
        source = parser.add_mutually_exclusive_group(required=True)
        source.add_argument("--live", action="store_true", help="الجدول الحيّ")
        source.add_argument("--generation", default="", help="معرّف التوليد (أو أوّل حروفه)")
        source.add_argument("--slots-json", default="", help="ملفُّ ناتج حلّالٍ خارجيّ بالمعرّفات")
        parser.add_argument("--json", default="", help="يكتب التقرير الكامل JSON")

    def handle(self, *args: Any, **opts: Any) -> None:
        school = (
            School.objects.filter(code=opts["school"]).first()
            if opts["school"]
            else School.objects.first()
        )
        if school is None:
            raise CommandError("لا مدرسة")
        year = opts["year"] or academic_year_for_school(school)

        solver = None
        relaxations: dict[str, int] = {}
        if opts["live"]:
            label, slots = "الجدول الحيّ", live_slots(school, year)
        elif opts["generation"]:
            generation = self._generation(school, opts["generation"])
            year = generation.academic_year
            label, slots = f"التوليد {str(generation.pk)[:8]}", generation_slots(generation)
        else:
            try:
                with open(opts["slots_json"], encoding="utf-8") as handle:
                    payload = json.load(handle)
                slots, solver = slots_from_payload(payload)
                relaxations = relaxations_from_payload(payload)
            except (OSError, json.JSONDecodeError, EvaluatorInputError) as error:
                raise CommandError(f"ملفٌّ مرفوض: {error}") from error
            label = "ناتج حلّالٍ خارجيّ"

        result = evaluate_slots(school, year, slots, solver, relaxations)
        self._print(label, year, result)
        if opts["json"]:
            with open(opts["json"], "w", encoding="utf-8") as out:
                json.dump(result.as_dict(), out, ensure_ascii=False, indent=2)
        if not result.accepted:
            raise SystemExit(1)

    @staticmethod
    def _generation(school: School, prefix: str) -> ScheduleGeneration:
        found = [
            g
            for g in ScheduleGeneration.objects.filter(school=school)
            if str(g.pk).startswith(prefix)
        ]
        if len(found) != 1:
            raise CommandError(f"المعرّف «{prefix}» يطابق {len(found)} توليداً")
        return found[0]

    def _print(self, label: str, year: str, r: Any) -> None:
        out = self.stdout.write
        out(f"{label} — العام {year}")
        out(
            f"InfeasibilityValue = {r.infeasibility_value}  (المطلوب {r.required_periods} · الموضوع {r.placed_periods})"
        )
        for row in r.unplaced:
            out(f"   بلا موضع: شعبة {row[0]} · مادّة {row[1]} · معلّم {row[2]}")
        hard = ", ".join(f"{code}={n}" for code, n in sorted(r.hard_breaches.items())) or "لا شيء"
        out(f"المخالفات الصلبة = {r.hard_total}  ({hard})")
        out(f"ObjectiveValue = {r.objective_value}  (القيود المرنة وحدَها)")
        if r.soft_counts:
            out("   مرنة: " + ", ".join(f"{k}={v}" for k, v in sorted(r.soft_counts.items())))
        if r.orphan_cells:
            out(f"خاناتٌ بلا إسنادٍ مطابق = {r.orphan_cells}")
        if r.solver:
            s = r.solver
            out(f"الحلّال: {s['status']} — {r.verdict} · بذرة {s['seed']} · عمّال {s['workers']}")
        out(f"بصمة الجدول = {r.fingerprint}")
        for note in r.notes:
            out(f"ملاحظة: {note}")
        out("القبول: " + ("مقبول" if r.accepted else "غير مقبول"))

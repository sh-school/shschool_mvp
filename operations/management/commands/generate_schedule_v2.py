"""توليدُ الجدول V2 (CP-SAT) من سطر الأوامر.

    python manage.py generate_schedule_v2 --dry-run [--seed N] [--workers N] [--max-seconds S]   # حلٌّ وتقييمٌ بلا كتابة
    python manage.py generate_schedule_v2 [--sync]                                                  # مسودّةٌ: في العامل، أو هنا مع --sync

المخرجُ بمعرّفاتٍ لا أسماء. والمسودّةُ لا تُكتب إلّا بعد قبول المُقيِّم المستقلّ لها.
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from core.academic_calendar import academic_year_for_school
from core.models import School
from operations.models import ScheduleGeneration
from operations.scheduler_v2 import runner


class Command(BaseCommand):
    help = "يولّد جدولاً V2 بـCP-SAT: --dry-run حلٌّ وتقييمٌ بلا كتابة، وإلّا مسودّةٌ غيرُ منشورة"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--school", default=None)
        parser.add_argument("--year", default="")
        parser.add_argument("--seed", type=int, default=runner.DEFAULT_SEED)
        parser.add_argument("--workers", type=int, default=runner.DEFAULT_WORKERS)
        parser.add_argument("--max-seconds", type=float, default=runner.DEFAULT_MAX_SECONDS)
        parser.add_argument(
            "--max-minutes", type=float, default=None, help="بالدقائق (يغلب --max-seconds)"
        )
        parser.add_argument("--dry-run", action="store_true", help="لا يكتب شيئاً في القاعدة")
        parser.add_argument("--sync", action="store_true", help="ينفّذ هنا لا في العامل")

    def handle(self, *args: Any, **opts: Any) -> None:
        school = (
            School.objects.filter(code=opts["school"]).first()
            if opts["school"]
            else School.objects.first()
        )
        if school is None:
            raise CommandError("لا مدرسة")
        year = opts["year"] or academic_year_for_school(school)
        seconds = opts["max_minutes"] * 60 if opts["max_minutes"] else opts["max_seconds"]
        config = runner.SolverConfig(opts["seed"], opts["workers"], seconds)

        if opts["dry_run"]:
            try:
                result, _ = runner.run(school, year, config)
            except runner.RunnerError as error:
                raise CommandError(str(error)) from error
            self._print(result)
            if not result.ok:
                raise SystemExit(1)
            return

        generation = ScheduleGeneration.objects.create(
            school=school, academic_year=year, status="queued"
        )
        if opts["sync"]:
            ScheduleGeneration.objects.filter(pk=generation.pk).update(status="running")
            generation.status = "running"
            result = runner.run_generation(generation, config)
            self._print(result)
            if not result.ok:
                raise SystemExit(1)
        else:
            from operations.scheduler_v2.tasks import generate_schedule_v2_task

            generate_schedule_v2_task.delay(
                str(generation.pk), config.seed, config.workers, config.max_seconds
            )
            self.stdout.write(f"في الطابور: التوليد {str(generation.pk)[:8]}")

    def _print(self, result: runner.RunResult) -> None:
        out = self.stdout.write
        if result.report:
            r = result.report
            out(
                f"الحلّال: {r.status} — {r.verdict} · بذرة {r.seed} · عمّال {r.workers} · {r.seconds:.1f}ث"
            )
        if result.evaluation:
            e = result.evaluation
            out(
                f"InfeasibilityValue={e.infeasibility_value} · صلبة={e.hard_total} · "
                f"ObjectiveValue={e.objective_value} · بصمة {e.fingerprint}"
            )
        verdict = "مسودّةٌ مقبولة" if result.ok else f"مرفوض ({result.reason}) — {result.message}"
        out("النتيجة: " + verdict)

"""غلافُ الرجوع بالجدول بأمرٍ واحد: استعادةُ لقطةٍ ثمّ مصالحةُ جلسات المدى.

    python manage.py rollback_schedule --snapshot backups/schedule/<لقطة>.json \
        --from 2026-10-11 --to 2026-10-15 [--dry-run] [--yes]

الخطوات (مدرسةُ اللقطة بمعرّفها لا باسمها):
  1. عدُّ الحصص المفعَّلة قبل الرجوع وبعده (ما في اللقطة).
  2. **الرفض** إن وُجدت جلساتٌ ممسوسةٌ (رصدٌ أو خروجٌ أو مخالفةٌ أو تبديلٌ أو تعويضٌ…) في المدى
     — فالرجوعُ بعد أوّل رصدٍ صباح الأحد يفقد أدلّتَه أو يتركها بلا حصّة. ويُطبع عددُها.
  3. تجربةٌ جافّة دائماً: استعادةُ اللقطة (`schedule_snapshot --restore`) ثمّ مصالحةُ كلّ يومٍ
     (`resync_sessions_for_date`) داخل معاملةٍ تُلغى — فيُعرض ما سيُحذف وما سيُنشأ فعلاً.
  4. `--dry-run` يقف هنا. وإلّا يُطلب تأكيدٌ («نعم»، أو `--yes`) ثمّ يُنفَّذ كلُّه في معاملةٍ واحدة.

ثابتُ التكرار: جدولٌ حيٌّ يطابق اللقطةَ لا يُستعاد ثانيةً (الاستعادةُ تُطفئ النشطَ وتنشئ صفوفاً جديدة)،
والمصالحةُ على جدولٍ مصالَحٍ لا تجد ما تحذفه ولا ما تنشئه.
"""

import datetime as dt
import json
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import School
from operations.models import ScheduleSlot, Session
from operations.school_days import SchoolDays
from operations.services import ScheduleService

_SLOT_KEY = ("teacher_id", "class_group_id", "subject_id", "day_of_week", "period_number")


def _key(row) -> tuple:
    return (*(str(row[k]) for k in _SLOT_KEY), row["elective_group"] or "")


class Command(BaseCommand):
    help = "الرجوع بالجدول: استعادة لقطة ثمّ مصالحة جلسات المدى (مع رفض ما مُسّ)"

    def add_arguments(self, parser):
        parser.add_argument("--snapshot", required=True, help="مسار لقطة schedule_snapshot")
        parser.add_argument("--from", dest="start", required=True, help="YYYY-MM-DD")
        parser.add_argument("--to", dest="end", required=True, help="YYYY-MM-DD")
        parser.add_argument("--dry-run", action="store_true", help="تجربةٌ بلا كتابة")
        parser.add_argument("--yes", action="store_true", help="تنفيذٌ بلا سؤال (للسكربتات)")

    def handle(self, *args, **opts):
        path = Path(opts["snapshot"])
        if not path.exists():
            raise CommandError(f"لا ملفَّ في {path}")
        try:
            start, end = dt.date.fromisoformat(opts["start"]), dt.date.fromisoformat(opts["end"])
        except ValueError as exc:
            raise CommandError(f"تاريخ غير صالح: {exc}") from exc
        if end < start:
            raise CommandError("--to قبل --from")
        data = json.loads(path.read_text(encoding="utf-8"))
        school = School.objects.filter(id=data["school_id"]).first()
        if school is None:
            raise CommandError("مدرسةُ اللقطة غيرُ موجودةٍ في هذه القاعدة.")
        year = data["academic_year"]

        live = ScheduleSlot.objects.filter(school=school, academic_year=year, is_active=True)
        before, after = live.count(), len(data["slots"])
        self.stdout.write(f"الحصص المفعَّلة: قبل={before} بعد={after}")

        touched = self._touched(school, start, end)
        if touched:
            raise CommandError(
                f"رُفض الرجوع: {touched} جلسةً ممسوسةً (رصدٌ أو ما في حكمه) في المدى {start} → {end}."
            )

        already = {_key(r) for r in live.values(*_SLOT_KEY, "elective_group")} == {
            _key(r) for r in data["slots"]
        }
        self.stdout.write(
            "الجدولُ الحيّ يطابق اللقطة — لا استعادة." if already else "ستُستعاد اللقطة."
        )

        trial = self._apply(school, path, start, end, already, year)
        self._print(trial, "تجربة")
        if opts["dry_run"]:
            self.stdout.write(self.style.SUCCESS("DRY-RUN — لم يُكتب شيء"))
            return
        if not opts["yes"] and input("اكتب «نعم» للتنفيذ: ").strip() not in ("نعم", "yes"):
            self.stdout.write("أُلغي.")
            return
        result = self._apply(school, path, start, end, already, year, commit=True)
        self._print(result, "نُفِّذ")
        self.stdout.write(self.style.SUCCESS(f"DONE: حصصٌ مفعَّلة الآن {live.count()}"))

    @staticmethod
    def _touched(school, start, end) -> int:
        """جلساتُ المدى الحقيقيّةُ التي مسّها أحدٌ — عكسُ `_untouched`."""
        rows = Session.objects.filter(school=school, date__range=(start, end), provisional=False)
        untouched = ScheduleService._untouched(rows).values("pk")
        return rows.exclude(pk__in=untouched).count()

    def _apply(self, school, path, start, end, already, year, commit=False) -> dict:
        totals = {"deleted": 0, "created": 0, "kept": 0}
        with transaction.atomic():
            if not already:
                call_command("schedule_snapshot", restore=str(path), yes=True, stdout=self.stdout)
            days = SchoolDays(school, start, end)
            day = start
            while day <= end:
                result = ScheduleService.resync_sessions_for_date(
                    school, day, academic_year=year, school_days=days
                )
                for k in totals:
                    totals[k] += result[k]
                day += dt.timedelta(days=1)
            if not commit:
                transaction.set_rollback(True)
        return totals

    def _print(self, totals: dict, label: str) -> None:
        self.stdout.write(
            f"{label}: حُذفت {totals['deleted']} | أُنشئت {totals['created']} | أُبقيت {totals['kept']}"
        )

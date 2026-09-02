"""لقطةُ الجدول قبل التوليد، واسترجاعُها بعده.

زرُّ التوليد يُعطّل كلَّ حصّةٍ نشطةٍ للعام ثمّ يكتب مكانها — **لحظةَ الضغط، لا
عند الاعتماد**. فالجدولُ القائمُ الذي أُدخل يدويّاً على مدى أسابيعَ يختفي في
معاملةٍ واحدة. والإخفاءُ ناعمٌ (`is_active=False`) فالاسترجاعُ ممكنٌ نظريّاً،
لكنّ «ممكنٌ نظريّاً» ليس خطّةَ تراجع: من يُعيد الرايةَ إلى 870 صفّاً وهو
مذعورٌ يُخطئ.

    التقاط:   python manage.py schedule_snapshot --school SHH --year 2026-2027
    عرض:      python manage.py schedule_snapshot --list
    استرجاع:  python manage.py schedule_snapshot --restore <ملفّ>

واللقطةُ ملفُّ JSON بالمعرّفات لا بالأسماء: الأسماءُ تتغيّر، والمعرّفاتُ تُعيد
بناءَ الصفّ كما كان. وتُكتب في `backups/schedule/` وهو خارجُ المستودع.

والاسترجاعُ لا يحذف الحاضرَ حذفاً: يُطفئ ما هو نشطٌ الآن ثمّ يُنشئ صفوفَ
اللقطة. فإن أخطأتَ في اختيار اللقطة التقطتَ لقطةً جديدةً ثمّ رجعت.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import School
from operations.models import ScheduleSlot

#: خارجُ المستودع — `*.backup` و`backups/` لا تُودَع.
BACKUP_DIR = Path("backups") / "schedule"

#: ما يُعاد بناءُ الصفّ منه. لا `id` — الصفُّ المسترجَعُ صفٌّ جديدٌ بحقائقَ
#: قديمة، ولا فائدةَ في تثبيت مفتاحٍ قد يكون مستعمَلاً.
FIELDS = (
    "teacher_id",
    "class_group_id",
    "subject_id",
    "day_of_week",
    "period_number",
    "start_time",
    "end_time",
    "academic_year",
    "elective_group",
    "notes",
)


class Command(BaseCommand):
    help = "لقطةٌ احتياطيّةٌ لجدول الحصص واسترجاعُها — قبل التوليد وبعده."

    def add_arguments(self, parser):
        parser.add_argument("--school", default="SHH", help="كود المدرسة")
        parser.add_argument("--year", default="", help="العام الدراسي (افتراضه عامُ المدرسة)")
        parser.add_argument("--label", default="", help="وسمٌ يُضاف إلى اسم الملفّ")
        parser.add_argument("--list", action="store_true", help="عرضُ اللقطات المحفوظة")
        parser.add_argument("--restore", default="", help="مسارُ لقطةٍ تُسترجَع")
        parser.add_argument(
            "--yes", action="store_true", help="تنفيذُ الاسترجاع بلا سؤال (للسكربتات)"
        )

    def handle(self, *args, **opts):
        if opts["list"]:
            return self._list()
        if opts["restore"]:
            return self._restore(opts["restore"], confirmed=opts["yes"])
        return self._capture(opts)

    # ── العرض ────────────────────────────────────────────────────

    def _list(self):
        if not BACKUP_DIR.exists():
            self.stdout.write("لا لقطاتٍ بعد.")
            return
        rows = sorted(BACKUP_DIR.glob("*.json"))
        if not rows:
            self.stdout.write("لا لقطاتٍ بعد.")
            return
        for path in rows:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.stdout.write(
                f"{path}  ·  {data['school_code']} {data['academic_year']}  ·  "
                f"{len(data['slots'])} حصّة  ·  {data['taken_at']}"
            )

    # ── الالتقاط ─────────────────────────────────────────────────

    def _capture(self, opts):
        school = self._school(opts["school"])
        year = opts["year"] or self._year(school)
        rows = ScheduleSlot.objects.filter(
            school=school, academic_year=year, is_active=True
        ).values(*FIELDS)

        slots = [{k: self._plain(v) for k, v in row.items()} for row in rows]
        if not slots:
            self.stdout.write(self.style.WARNING(f"لا حصصَ نشطةً في {year} — لا لقطةَ تُلتقط."))
            return

        stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
        label = f"-{opts['label']}" if opts["label"] else ""
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        path = BACKUP_DIR / f"{school.code}-{year}-{stamp}{label}.json"
        path.write_text(
            json.dumps(
                {
                    "school_id": str(school.id),
                    "school_code": school.code,
                    "academic_year": year,
                    "taken_at": timezone.localtime().isoformat(timespec="seconds"),
                    "slots": slots,
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        self.stdout.write(self.style.SUCCESS(f"التُقطت {len(slots)} حصّة → {path}"))
        self.stdout.write("وللرجوع: python manage.py schedule_snapshot --restore " + str(path))

    # ── الاسترجاع ────────────────────────────────────────────────

    def _restore(self, raw_path, *, confirmed):
        path = Path(raw_path)
        if not path.exists():
            raise CommandError(f"لا ملفَّ في {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        school = School.objects.filter(id=data["school_id"]).first()
        if school is None:
            raise CommandError(f"مدرسةُ اللقطة {data['school_code']} غيرُ موجودةٍ في هذه القاعدة.")

        year = data["academic_year"]
        live = ScheduleSlot.objects.filter(school=school, academic_year=year, is_active=True)
        self.stdout.write(
            f"سيُطفأ {live.count()} حصّةً نشطةً، ويُستعاد {len(data['slots'])} من لقطة "
            f"{data['taken_at']}."
        )
        if not confirmed and input("اكتب «نعم» للمتابعة: ").strip() not in ("نعم", "yes"):
            self.stdout.write("أُلغي.")
            return

        with transaction.atomic():
            live.update(is_active=False)
            ScheduleSlot.objects.bulk_create(
                [ScheduleSlot(school=school, is_active=True, **row) for row in data["slots"]]
            )
        self.stdout.write(self.style.SUCCESS(f"استُعيدت {len(data['slots'])} حصّة."))

    # ── أدوات ────────────────────────────────────────────────────

    def _school(self, code):
        school = School.objects.filter(code=code).first()
        if school is None:
            raise CommandError(f"لا مدرسةَ بالكود {code}")
        return school

    def _year(self, school):
        from core.academic_calendar import academic_year_for_school

        return academic_year_for_school(school)

    @staticmethod
    def _plain(value):
        """الأوقاتُ والمعرّفاتُ نصّاً — و`json` لا يعرف `time` ولا `UUID`."""
        return value if isinstance(value, str | int | type(None)) else str(value)

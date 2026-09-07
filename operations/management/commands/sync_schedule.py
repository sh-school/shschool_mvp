"""نقلُ الجدول الحيّ بين قاعدتين — بالأسماء، ثمّ اعتمادٌ كما من الشاشة.

    export → حصصُ الجدول الحيّ بأسماء الشعبةِ والمادّةِ والمعلّم، ومعها مقاييسُ توليدها
    import → مطابقةٌ بالأسماء، ومسودّةُ توليدٍ جديدة، ثمّ الاعتمادُ عبر الخدمة نفسِها

لمَ لا يُعاد التوليدُ على الهدف؟ لأنّ الجدولَ المحلّيَّ توليدٌ معتمَدٌ رُوجع
بعينٍ بشريّة، والمولّدُ لا يُخرج الجدولَ نفسَه مرّتين — فإعادتُه تُنتج جدولاً
آخرَ يُراجَع من جديد. والنقلُ يُثبّت ما رُوجع فعلاً.

## الجدولُ لا يُنقل إلّا فوق إسنادٍ يطابقه

كلُّ حصّةٍ في الملفّ يجب أن يكون لها إسنادٌ حيٌّ في الهدف بالشعبةِ والمادّةِ
والمعلّمِ نفسِها — وإلّا فهي تعذُّرٌ يُسمّى. فجدولٌ يقول «أحمدُ يدرّس رياضياتِ
9/2» وإسنادٌ يقول غيرَ ذلك تناقضٌ يراه المعلّمُ قبل أن يراه أحد. لذا يُنقل
الإسنادُ أوّلاً (`sync_assignments`) ثمّ الجدول.

## والاعتمادُ من الباب نفسِه

الحصصُ تُدرَج مسودّةً مُطفأةً على توليدٍ جديد، ثمّ يُستدعى
`ScheduleService.approve_generation` — الذي يستدعيه زرُّ الاعتماد في الشاشة:
يُطفئ الجدولَ القديم، ويُفعّل الجديد، ويؤرشف ويقيس ويُشعر ويصالح جلساتِ
الأسبوع. لا مسارَ ثانياً يُقلّد الأوّلَ ثمّ يتخلّف عنه.
"""

import base64
import gzip
import json
import sys

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.academic_calendar import default_academic_year
from core.models import School
from operations.management.commands.sync_assignments import Resolver
from operations.models import ScheduleGeneration, ScheduleSlot, SubjectClassAssignment
from operations.services import ScheduleService

DAYS = dict(ScheduleSlot.DAYS)


def _payload(slot):
    return {
        "grade": slot.class_group.grade,
        "section": slot.class_group.section,
        "track": slot.class_group.track or "",
        "subject": slot.subject.name_ar if slot.subject else "",
        "teacher": slot.teacher.full_name,
        "day": slot.day_of_week,
        "period": slot.period_number,
        "start": slot.start_time.strftime("%H:%M"),
        "end": slot.end_time.strftime("%H:%M"),
        "elective_group": slot.elective_group or "",
        "notes": slot.notes or "",
    }


def _generation_meta(gen):
    """ما يُحمل من التوليد المصدر: مقاييسُه وإعداداتُه، لا هويّتُه."""
    if gen is None:
        return {}
    return {
        "source_generation": str(gen.id),
        "quality_score": gen.quality_score,
        "hard_violations": gen.hard_violations,
        "soft_violations": gen.soft_violations,
        "metrics": gen.metrics,
        "config_snapshot": gen.config_snapshot,
        "generation_time_ms": gen.generation_time_ms,
    }


class Command(BaseCommand):
    help = "تصديرُ الجدول الحيّ أو استيرادُه بالمطابقة بالأسماء ثمّ اعتمادُه"

    def add_arguments(self, parser):
        parser.add_argument("mode", choices=["export", "import"])
        parser.add_argument("--file", default="-", help="مسارُ الملفّ، و«-» للقياسيّ (الافتراض)")
        parser.add_argument("--b64", default="", help="الحمولةُ gzip+base64 بدل الملفّ / أخرِجها كذلك")
        parser.add_argument("--year", default="", help="العامُ الدراسيّ (الافتراض: الجاري)")
        parser.add_argument("--apply", action="store_true", help="نفِّذ فعلاً — وبدونه عرضٌ فقط")
        parser.add_argument("--no-notify", action="store_true", help="اعتمِد بلا إشعار المعلّمين")

    def handle(self, *args, **options):
        school = School.objects.first()
        if school is None:
            raise CommandError("لا مدرسةَ في هذه القاعدة.")
        year = options["year"] or default_academic_year()
        if options["mode"] == "export":
            return self._export(school, year, options)
        return self._import(school, year, options)

    # ── تصدير ────────────────────────────────────────────────────

    def _export(self, school, year, options):
        slots = ScheduleSlot.objects.live(school, year=year).select_related(
            "class_group", "subject", "teacher"
        )
        rows = sorted(
            (_payload(s) for s in slots),
            key=lambda r: (r["grade"], r["section"], r["day"], r["period"], r["elective_group"]),
        )
        gens = {s.generation_id for s in slots if s.generation_id}
        gen = ScheduleGeneration.objects.filter(id__in=gens).first() if len(gens) == 1 else None
        text = json.dumps(
            {"year": year, "generation": _generation_meta(gen), "rows": rows},
            ensure_ascii=False,
            indent=1,
        )
        if options["b64"]:
            text = base64.b64encode(gzip.compress(text.encode("utf-8"), 9)).decode("ascii")
        if options["file"] == "-":
            self.stdout.write(text)
        else:
            with open(options["file"], "w", encoding="utf-8") as handle:
                handle.write(text)
        self.stderr.write(
            f"صُدِّرت {len(rows)} حصّةً"
            + (f" من توليدٍ واحدٍ {str(gen.id)[:8]}" if gen else " (بلا توليدٍ واحدٍ يجمعها)")
        )

    # ── استيراد ──────────────────────────────────────────────────

    def _read(self, options):
        if options["b64"]:
            try:
                raw = gzip.decompress(base64.b64decode(options["b64"])).decode("utf-8")
            except (ValueError, OSError) as exc:
                raise CommandError(f"حمولةُ --b64 ليست gzip+base64 صالحة: {exc}") from exc
        else:
            path = options["file"]
            raw = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CommandError(f"الملفُّ ليس JSON صالحاً: {exc}") from exc
        if not isinstance(data.get("rows"), list):
            raise CommandError("الملفُّ بلا حقل `rows`.")
        return data

    def _plan(self, rows, resolver, school, year):
        """يُسمّي كلَّ حصّةٍ بكائناتها، ويقف عند ما لا اسمَ له أو لا إسنادَ يسنده."""
        assigned = set(
            SubjectClassAssignment.objects.live(school, year=year).values_list(
                "class_group_id", "subject_id", "teacher_id"
            )
        )
        resolved, failed = [], []
        for row in rows:
            try:
                klass, subject, teacher = resolver.resolve(row)
                if teacher is None:
                    raise LookupError("حصّةٌ بلا معلّم")
                if (klass.id, subject.id, teacher.id) not in assigned:
                    raise LookupError(
                        f"لا إسنادَ حيّاً يسند «{subject.name_ar}» لـ{teacher.full_name} في هذه الشعبة"
                    )
            except LookupError as exc:
                failed.append((row, str(exc)))
                continue
            resolved.append((row, klass, subject, teacher))

        current = {
            (
                s.class_group_id,
                s.subject_id,
                s.teacher_id,
                s.day_of_week,
                s.period_number,
                s.elective_group or "",
            )
            for s in ScheduleSlot.objects.live(school, year=year)
        }
        incoming = {
            (k.id, s.id, t.id, r["day"], r["period"], r["elective_group"])
            for r, k, s, t in resolved
        }
        return (
            resolved,
            failed,
            len(incoming & current),
            len(incoming - current),
            len(current - incoming),
        )

    def _import(self, school, year, options):
        data = self._read(options)
        rows = data["rows"]
        resolver = Resolver(school, year)
        resolved, failed, same, added, removed = self._plan(rows, resolver, school, year)

        self.stderr.write(
            f"الملفّ {len(rows)} حصّةً | مطابقة {same} | جديدة {added} | ستُطفأ {removed}"
            f" | تعذّر {len(failed)}"
        )
        for row, why in failed[:40]:
            self.stderr.write(
                f"  ✗ {row['grade']}/{row['section']} {DAYS.get(row['day'], row['day'])} ح{row['period']}"
                f" {row['subject']}: {why}"
            )
        if len(failed) > 40:
            self.stderr.write(f"  … و{len(failed) - 40} أخرى")

        if not options["apply"]:
            self.stderr.write("عرضٌ فقط — أضِف --apply للتنفيذ.")
            return
        if failed:
            raise CommandError("لن يُنفَّذ شيءٌ ما دامت حصّةٌ واحدةٌ متعذّرة.")

        meta = data.get("generation") or {}
        with transaction.atomic():
            gen = ScheduleGeneration.objects.create(
                school=school,
                academic_year=year,
                status="draft",
                quality_score=meta.get("quality_score", 0),
                hard_violations=meta.get("hard_violations", 0),
                soft_violations=meta.get("soft_violations") or {},
                metrics=meta.get("metrics") or {},
                total_slots_created=len(resolved),
                generation_time_ms=meta.get("generation_time_ms", 0),
                config_snapshot={
                    **(meta.get("config_snapshot") or {}),
                    "imported_from": meta.get("source_generation", ""),
                },
            )
            ScheduleSlot.objects.bulk_create(
                [
                    ScheduleSlot(
                        school=school,
                        teacher=t,
                        class_group=k,
                        subject=s,
                        day_of_week=r["day"],
                        period_number=r["period"],
                        start_time=r["start"],
                        end_time=r["end"],
                        academic_year=year,
                        elective_group=r["elective_group"],
                        notes=r["notes"],
                        generation=gen,
                        is_active=False,
                    )
                    for r, k, s, t in resolved
                ]
            )
            result = ScheduleService.approve_generation(gen, notify=not options["no_notify"])

        live = ScheduleSlot.objects.live(school, year=year).count()
        sync = result["sync"]
        self.stderr.write(
            f"اعتُمد التوليدُ {str(gen.id)[:8]}: {live} حصّةً حيّة | أُشعر {result['notified']} معلّماً"
            f" | جلساتُ الأسبوع: حُذف {sync['deleted']}، أُنشئ {sync['created']}، أُبقي {sync['kept']}"
        )

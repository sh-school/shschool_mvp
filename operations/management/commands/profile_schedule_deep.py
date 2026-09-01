"""
تشريحُ الجدول القائم — قراءةً محضة، ودراسةٌ لا ملخّص.

    python manage.py profile_schedule_deep --year 2026-2027 \\
        [--section adjacency|fingerprint|sections|gaps|splits|doubles|
                   availability|transitions|thursday|peers|variance|all]
        [--json تقرير.json] [--csv مجلَّد]

ولا رايةَ `--apply`: ليس له مسارُ كتابةٍ أصلاً.

وكلُّ ما يُخرجه **مرصودٌ** لا مُقرَّر: `ObservedLoad ≠ RequiredLoad`، فلا
يُسمّى تفاوتُ النصاب ظلماً ولا يومُ الفراغ إعفاءً حتى يُسنِدهما قرارٌ إداريّ.
"""

import csv
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from operations import schedule_deep_profile as deep
from operations import schedule_profile as base

SECTIONS = (
    "adjacency",
    "fingerprint",
    "variance",
    "sections",
    "gaps",
    "splits",
    "doubles",
    "availability",
    "transitions",
    "thursday",
    "peers",
)


class Command(BaseCommand):
    help = "تشريحٌ عميقٌ للجدول القائم (قراءةً فقط)"

    def add_arguments(self, parser):
        parser.add_argument("--year", required=True)
        parser.add_argument("--school", default=None)
        parser.add_argument("--section", default="adjacency", help="أو all")
        parser.add_argument("--top", type=int, default=12)
        parser.add_argument("--json", default="")
        parser.add_argument("--csv", default="", help="مجلَّدٌ تُكتب فيه الجداول التفصيليّة")

    def handle(self, *args, **options):
        school = self._school(options["school"])
        year = options["year"]
        lessons = base.load_lessons(school, year)
        if not lessons:
            raise CommandError(f"لا حصصَ نشطةً في {year}.")

        wanted = SECTIONS if options["section"] == "all" else (options["section"],)
        for name in wanted:
            if name not in SECTIONS:
                raise CommandError(f"قسمٌ غير معروف: {name} — المتاح: {', '.join(SECTIONS)}")

        w = self.stdout.write
        top = options["top"]
        w(f"\n{school.name} · {year} · {len(lessons)} حصّة")
        w("═" * 72)

        data = {}
        for name in wanted:
            data[name] = getattr(self, f"_{name}")(school, year, lessons, w, top)

        if options["json"]:
            Path(options["json"]).write_text(
                json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
            )
            w(self.style.SUCCESS(f"\nحُفظ: {options['json']}"))
        if options["csv"]:
            self._csv(Path(options["csv"]), data, w)

        w(self.style.SUCCESS("\nقراءةٌ فقط — لم يُكتب شيء في القاعدة.\n"))

    # ── الأقسام ──────────────────────────────────────────────────────

    def _adjacency(self, school, year, lessons, w, top):
        rows = deep.subject_adjacency(lessons)
        w("\n── مصفوفةُ التجاور: ما معنى «تكرارُ المادّة في اليوم» ──")
        w(
            f"  {'المادّة [كود]':<28}{'تكرار':>7}{'متلاصق':>9}"
            f"{'متباعد':>9}{'نسبة':>8}  {'أشهرُ زوج':<10}"
        )
        for name, row in list(rows.items())[:top]:
            w(
                f"  {name[:23]:<24}{row.daily_doubles:>7}{row.adjacent:>9}"
                f"{row.apart:>9}{row.adjacency_rate:>7}%  {row.commonest_pair:<10}"
            )
        for name, row in list(rows.items())[:4]:
            w(f"\n  · {name}")
            w(f"      الأزواج: {row.pairs}")
            w(f"      أطوالُ السلاسل: {row.run_lengths}")
            w(f"      بالصفّ: {row.by_grade}")
            w(f"      باليوم: {row.by_day}")
        return {
            f"{r.subject_code}·{r.subject}": {
                "subject_id": r.subject_id,
                "code": r.subject_code,
                "name": r.subject,
                "daily_doubles": r.daily_doubles,
                "adjacent": r.adjacent,
                "apart": r.apart,
                "adjacency_rate": r.adjacency_rate,
                "pairs": r.pairs,
                "run_lengths": r.run_lengths,
                "by_grade": r.by_grade,
                "by_section": r.by_section,
                "by_teacher": r.by_teacher,
                "by_day": r.by_day,
            }
            for r in rows.values()
        }

    def _fingerprint(self, school, year, lessons, w, top):
        rows = deep.subject_fingerprint(lessons)
        w("\n── بصمةُ المادّة × الصفّ ──")
        w(
            f"  {'مادّة · صفّ':<30}{'حصص':>6}{'شعب':>6}{'صباح%':>8}{'متأخّر%':>9}{'أيّام':>7}{'مسافة':>8}"
        )
        for name, d in list(rows.items())[:top]:
            w(
                f"  {name[:29]:<30}{d['total']:>6}{d['sections']:>6}"
                f"{d['morning_pct']:>8}{d['late_pct']:>9}{d['days_spread']:>7}{d['mean_gap_between']:>8}"
            )
        return rows

    def _variance(self, school, year, lessons, w, top):
        rows = deep.grade_section_variance(lessons)
        w("\n── شُعبُ الصفّ الواحد في المادّة الواحدة ──")
        w("  (النصابُ والصفُّ والمادّةُ مثبَّتة — فما بقي فارقٌ يقع على الطالب)")
        for title, d in list(rows.items())[:top]:
            flag = "" if d["equal_weekly"] else "   ⟨نصابٌ غيرُ متساوٍ⟩"
            w(f"\n  {title}   id={d['subject_id']}{flag}")
            w(
                f"  {'الشعبة':<9}{'نصاب':>6}{'ح١-٣%':>9}{'ح٦-٧%':>9}"
                f"{'متأخّرة':>9}{'أيّامُ تكرار':>13}{'مزدوجة':>9}"
            )
            for section, r in d["sections"].items():
                w(
                    f"  {section:<9}{r['weekly']:>6}{r['morning_pct']:>8}%"
                    f"{r['late_pct']:>8}%{r['late_count']:>9}"
                    f"{r['repeated_days']:>13}{r['adjacent_double']:>9}"
                )
            w(
                f"      فارقُ الحصص المتأخّرة {d['late_count_spread']}"
                f"  ·  تشتّتُ النسبة {d['late_spread']}%"
                f"  ·  أثقلُها {d['latest_section']} · أخفُّها {d['earliest_section']}"
            )
        return rows

    def _sections(self, school, year, lessons, w, top):
        core = self._core_names(school)
        rows = deep.section_burden(lessons, core)
        w("\n── ما يقع على الشُّعب ──")
        w(
            f"  {'الشعبة':<14}{'حصص':>6}{'أولى':>7}{'سابعة':>8}{'متأخّرة':>9}{'أثقل يوم':>10}{'أساسيّ متأخّر':>14}"
        )
        for name, d in list(rows.items())[:top]:
            w(
                f"  {name[:13]:<14}{d['lessons']:>6}{d['first_periods']:>7}{d['seventh_periods']:>8}"
                f"{d['late_periods']:>9}{d['heaviest_day']:>10}{d['core_in_late']:>14}"
            )
        return rows

    def _gaps(self, school, year, lessons, w, top):
        rows = deep.gap_anatomy(lessons)
        w("\n── تشريحُ الفراغ: أربعةُ أنواعٍ لا رقمٌ واحد ──")
        w(
            f"  {'المعلّم':<28}{'داخليّ':>8}{'مفردة':>8}{'مزدوجة+':>10}"
            f"{'أسوأ':>7}{'أيّام':>7}{'قبل الأولى':>12}{'بعد الأخيرة':>13}"
        )
        for name, d in list(rows.items())[:top]:
            w(
                f"  {name[:27]:<28}{d['internal_gap']:>8}{d['single_gap']:>8}"
                f"{d['multi_gap']:>10}{d['worst_gap']:>7}{d['days_with_gap']:>7}"
                f"{d['leading_free']:>12}{d['trailing_free']:>13}"
            )
        totals = {
            "internal_gap": sum(d["internal_gap"] for d in rows.values()),
            "multi_gap": sum(d["multi_gap"] for d in rows.values()),
            "leading_free": sum(d["leading_free"] for d in rows.values()),
            "trailing_free": sum(d["trailing_free"] for d in rows.values()),
        }
        w(f"\n  المجاميع: {totals}")
        w("  (قبل الأولى وبعد الأخيرة ليسا فراغاً تشغيليّاً — لا حضورَ مطلوبٌ فيهما)")
        return rows

    def _splits(self, school, year, lessons, w, top):
        data = deep.split_slots(lessons)
        w(f"\n── الحصصُ المنقسمة ({len(data['slots'])}) ──")
        for slot in data["slots"]:
            branches = " │ ".join(
                f"{b['group'] or '—'} → {b['subject']} → {b['teacher']}" for b in slot["branches"]
            )
            w(f"  {slot['section']:<10} {slot['day']:<9} حصّة {slot['period']}   {branches}")
        w(f"\n  الاقترانات: {data['pairings']}")
        w(f"  بالصفّ: {data['grades']}")
        return data

    def _doubles(self, school, year, lessons, w, top):
        rows = deep.declared_versus_observed_doubles(school, lessons)
        w("\n── المُعلَن مقابل الواقع: الحصّةُ المزدوجة ──")
        w(f"  {'المادّة [كود]':<30}{'النموذج':>9}{'حصص':>7}{'تكرار':>7}{'تلاصق%':>9}  أشهرُ زوج")
        for d in list(rows.values())[:top]:
            declared = (
                "نعم" if d["declared_double"] else ("لا" if d["declared_double"] is False else "؟")
            )
            label = f"{d['name']} [{d['code'] or '—'}]"
            w(
                f"  {label[:29]:<30}{declared:>9}{d['lessons']:>7}{d['daily_doubles']:>7}"
                f"{d['adjacency_rate']:>8}%  {d['commonest_pair']}"
            )
        return rows

    def _availability(self, school, year, lessons, w, top):
        rows = deep.availability_status(school, year, lessons)
        counts = {}
        for r in rows:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        w("\n── التوافر: المُعلَن مقابل المرصود ──")
        w(f"  {counts}")
        for r in rows[:top]:
            w(f"  {r['teacher'][:30]:<32}{r['day']:<10}{r['status']}")
        w("  (OBSERVED_ONLY لا يصير قيداً — قد يكون أثرَ الجدول لا قراراً)")
        return {"counts": counts, "rows": rows}

    def _transitions(self, school, year, lessons, w, top):
        rows = deep.subject_transitions(lessons)
        w("\n── ما يأتي بعد ماذا ──")
        for name, count in list(rows.items())[:top]:
            w(f"  {name[:52]:<54}{count:>5}")
        return rows

    def _thursday(self, school, year, lessons, w, top):
        data = deep.thursday_apart(lessons)
        w("\n── الخميس مفصولاً ──")
        w(f"  الأيّامُ العاديّة: {data['ordinary_days']}")
        w(f"  الخميس:          {data['thursday']}")
        for level, shape in data["by_level"].items():
            w(f"    {level}: {shape}")
        return data

    def _peers(self, school, year, lessons, w, top):
        profiles = base.profile_teachers(lessons)
        data = deep.peer_outliers(profiles, lessons)
        w("\n── مقارنةُ النظراء: داخل شرائح النصاب لا عبر المدرسة ──")
        for band, d in data["bands"].items():
            w(
                f"\n  شريحة {band}  ·  {d['teachers']} معلّماً  ·  الفراغُ الداخليّ"
                f" أدنى {d['min_gaps']} · وسيط {d['median_gaps']} · أعلى {d['max_gaps']}"
                f"  ·  وسيطُ المزدوجة {d['median_multi']}"
            )
            for tag, group in (("أثقلُ", d["heaviest"]), ("أخفُّ", d["lightest"])):
                for r in group:
                    w(
                        f"      {tag:<6}{r['name'][:26]:<28}نصاب {r['weekly']:>3}"
                        f"  داخليّ {r['internal_gap']:>3}  مزدوجة {r['multi_gap']:>2}"
                        f"  أسوأ {r['worst_gap']:>2}  أيّام {r['days_used']}"
                    )
        if data["too_small"]:
            w("\n  شرائحُ أصغرُ من أن تُقارَن — تُذكر ولا تُطوى:")
            for band, rows in data["too_small"].items():
                names = "، ".join(f"{r['name'][:20]} ({r['weekly']})" for r in rows)
                w(f"      {band}: {names}")
        w("\n  (النصابُ المطلوب ليس في الجدول — فلا يُسمّى أحدٌ شاذّاً هنا)")
        return data

    # ── مساعدات ──────────────────────────────────────────────────────

    def _core_names(self, school):
        from operations.models import Subject
        from operations.scheduler_constraints import CORE_CODES

        return {
            s.name_ar
            for s in Subject.objects.filter(school=school, code__in=CORE_CODES).only("name_ar")
        }

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

    #: الأقسامُ التي بنيتُها جدولٌ مسطَّح — وما عداها متداخلٌ لا يُسطَّح بلا تشويه.
    TABULAR = ("adjacency", "fingerprint", "sections", "gaps", "doubles")

    def _csv(self, folder, data, w):
        folder.mkdir(parents=True, exist_ok=True)
        skipped = [n for n in data if n not in self.TABULAR]
        if skipped:
            w(f"  (لا CSV لـ {'، '.join(skipped)} — بنيتُها متداخلة، والـJSON يحفظها كاملةً)")
        for name, payload in data.items():
            if name not in self.TABULAR:
                continue
            if not isinstance(payload, dict) or not payload:
                continue
            first = next(iter(payload.values()))
            if not isinstance(first, dict):
                continue
            path = folder / f"{name}.csv"
            columns = ["key", *first.keys()]
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(columns)
                for key, row in payload.items():
                    writer.writerow([key, *[row.get(c, "") for c in columns[1:]]])
            w(self.style.SUCCESS(f"  CSV: {path}"))

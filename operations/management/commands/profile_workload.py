"""
أساسُ النصاب المرصود 2026-2027 — قراءةً محضة.

    python manage.py profile_workload --year 2026-2027 \\
        [--section teachers|cells|demand|summary|all] [--json تقرير.json]

ولا رايةَ `--apply`: ليس له مسارُ كتابةٍ أصلاً.

وكلُّ رقمٍ هنا **`observed scheduled workload`** لا `approved workload`.
فلا يُقال «فلانٌ ناقصُ أربعِ حصص» — قد يكون له تخفيضٌ معتمَد، والجدولُ لا
يحمل هذه الحقيقة. وسبيلُ ذلك كيانٌ إداريٌّ مستقلٌّ لم يُبنَ بعد.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.models.academic import grade_number
from operations import schedule_profile as base
from operations import workload_profile as wl

SECTIONS = ("summary", "teachers", "cells", "demand")


class Command(BaseCommand):
    help = "أساسُ النصاب المرصود من الجدول القائم، ومطابقتُه بالإسنادات (قراءةً فقط)"

    def add_arguments(self, parser):
        parser.add_argument("--year", required=True)
        parser.add_argument("--school", default=None)
        parser.add_argument("--section", default="all")
        parser.add_argument("--top", type=int, default=15)
        parser.add_argument("--json", default="")

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

        observed = wl.observed_workload(lessons)
        rows = wl.assignment_rows(school, year)
        cells = wl.reconcile_cells(lessons, rows)
        teachers = wl.reconcile_teachers(observed, rows)

        w = self.stdout.write
        top = options["top"]
        w(f"\n{school.name} · {year} · {len(lessons)} حصّة · {len(observed)} معلّماً")
        w("═" * 74)
        w("  كلُّ رقمٍ هنا observed scheduled workload — لا approved workload.")

        data = {}
        for name in wanted:
            data[name] = getattr(self, f"_{name}")(lessons, observed, rows, cells, teachers, w, top)

        if options["json"]:
            Path(options["json"]).write_text(
                json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
            )
            w(self.style.SUCCESS(f"\nحُفظ: {options['json']}"))
        w(self.style.SUCCESS("\nقراءةٌ فقط — لم يُكتب شيء في القاعدة.\n"))

    # ── الأقسام ──────────────────────────────────────────────────────

    def _summary(self, lessons, observed, rows, cells, teachers, w, top):
        data = wl.summary(cells, teachers)
        w("\n── المطابقة إجمالاً ──")
        w(f"  حصصُ الجدول {data['scheduled_total']}  ·  حصصُ الإسناد {data['assigned_total']}")
        w(f"  الخلايا (شعبة × مادّة): {data['cells']}")
        w(f"  المعلّمون:              {data['teachers']}")
        unstaffed = [r for r in rows if not r["teacher_id"]]
        w(f"  إسناداتٌ بلا معلّم: {len(unstaffed)}")
        multi = sum(1 for t in observed.values() if t.multi_subject)
        levels = sum(1 for t in observed.values() if t.multi_level)
        splits = sum(1 for t in observed.values() if t.split_periods)
        w(f"  يُدرّسون أكثرَ من مادّة: {multi}  ·  أكثرَ من مرحلة: {levels}")
        w(f"  لهم حصصٌ في شعبةٍ منقسمة: {splits}")
        w("  (المؤهّلُ — CanTeach — غيرُ معلومٍ في القاعدة، ولا يُستنتج من الظهور)")
        return {**data, "unstaffed_assignments": len(unstaffed)}

    def _teachers(self, lessons, observed, rows, cells, teachers, w, top):
        w("\n── النصابُ المرصود لكلّ معلّم ──")
        w(
            f"  {'المعلّم':<28}{'جدول':>6}{'إسناد':>7}{'فرق':>6}{'موادّ':>7}{'شعب':>6}{'صفوف':>7}  الحالة"
        )
        for tid, t in list(teachers.items())[:top]:
            obs = observed.get(tid)
            w(
                f"  {t['name'][:27]:<28}{t['scheduled']:>6}{t['assigned']:>7}{t['delta']:>+6}"
                f"{len(obs.subjects) if obs else 0:>7}{len(obs.sections) if obs else 0:>6}"
                f"{len(obs.grades) if obs else 0:>7}  {t['status']}"
            )
        w("\n  تفصيلُ الأثقل نصاباً:")
        for t in list(observed.values())[:3]:
            subjects = "، ".join(
                f"{s['name']} [{s['code']}] {s['periods']}" for s in t.subjects.values()
            )
            w(f"\n  · {t.name}  ({t.observed_weekly} حصّة)   id={t.teacher_id}")
            w(f"      الموادّ: {subjects}")
            w(f"      الصفوف: {t.grades}")
            w(f"      شعبٌ لكلّ مادّة: {t.sections_per_subject}")
            w(f"      الحصص لكلّ مادّة×شعبة: {t.per_subject_class}")
            w(f"      اليوميّ: {t.per_day}   منقسمة: {t.split_periods}")
        return {
            tid: {
                **t,
                "subjects": [dict(s) for s in observed[tid].subjects.values()]
                if tid in observed
                else [],
                "sections": sorted(observed[tid].sections) if tid in observed else [],
                "grades": (
                    sorted(observed[tid].grades, key=grade_number) if tid in observed else []
                ),
                "per_subject_class": observed[tid].per_subject_class if tid in observed else {},
                "per_day": observed[tid].per_day if tid in observed else {},
                "split_periods": observed[tid].split_periods if tid in observed else 0,
            }
            for tid, t in teachers.items()
        }

    def _cells(self, lessons, observed, rows, cells, teachers, w, top):
        bad = [c for c in cells if c["status"] != wl.MATCH]
        w(f"\n── الخلايا المختلفة ({len(bad)} من {len(cells)}) ──")
        w(
            f"  {'الشعبة':<9}{'المادّة':<26}{'جدول':>6}{'إسناد':>7}{'فرق':>6}  {'الحالة':<18}معلّمُ الجدول"
        )
        for c in bad[:top]:
            label = f"{c['name']} [{c['code'] or '—'}]"
            w(
                f"  {c['section']:<9}{label[:25]:<26}{c['scheduled']:>6}{c['assigned']:>7}"
                f"{c['delta']:>+6}  {c['status']:<18}{c['scheduled_teacher'][:22]}"
            )
        if len(bad) > top:
            w(f"  … و{len(bad) - top} خليّةً أخرى في الـJSON")
        return cells

    def _demand(self, lessons, observed, rows, cells, teachers, w, top):
        data = wl.demand_coverage(lessons, rows)
        gaps = [r for r in data if r["delta"] or r["unstaffed"]]
        w(f"\n── ميزانيّةُ الحصص لكلّ (صفّ × مادّة) — المختلُّ {len(gaps)} من {len(data)} ──")
        w(f"  {'الصفّ':<6}{'المادّة':<26}{'شعب':>5}{'جدول':>6}{'إسناد':>7}{'فرق':>6}{'بلا معلّم':>10}")
        for r in gaps[:top]:
            label = f"{r['name']} [{r['code'] or '—'}]"
            w(
                f"  {r['grade']:<6}{label[:25]:<26}{r['sections']:>5}{r['scheduled']:>6}"
                f"{r['assigned']:>7}{r['delta']:>+6}{r['unstaffed']:>10}"
            )
        w("  (فارقٌ موجبٌ: الجدولُ يحمل أكثرَ ممّا أُسنِد. وسالبٌ: إسنادٌ لم يُجدوَل)")
        return data

    # ── مساعدات ──────────────────────────────────────────────────────

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

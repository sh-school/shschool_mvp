"""
بذرُ قوالب تقييم الأداء من الاستمارات الوزاريّة السبع.

المرجع: AAdocs/ministry_data/2026_2027/06_attendance_performance_review.md §2.3–2.9
البيانات: quality/ministry_appraisal_forms.json — والمنطق: quality/appraisal_seed.py

    python manage.py seed_quality_templates                 # يعرض الفرق ولا يكتب
    python manage.py seed_quality_templates --apply         # يكتب
    python manage.py seed_quality_templates --apply --prune-orphans
    python manage.py seed_quality_templates --school SHH --year 2026-2027
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from core.academic_calendar import academic_year_for_school
from core.models import School
from quality.appraisal_seed import SchoolPlan, apply_plan, build_plan

_STATUS_LABEL = {
    "new": "جديد",
    "same": "مطابق",
    "changed": "يختلف",
    "locked": "يختلف — مقفل (عليه تقييمات، لا يُغيَّر)",
}


class Command(BaseCommand):
    help = "بذرُ قوالب التقييم الوزاريّة لكلّ دور. بلا --apply يعرض الفرقَ عن القائم ولا يكتب."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--apply", action="store_true", help="اكتب التغييرات")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="اعرض الفرق فقط (الافتراضيّ؛ للصراحة في الأوامر المكتوبة)",
        )
        parser.add_argument("--school", help="رمز المدرسة (الافتراضيّ: كلّ المدارس)")
        parser.add_argument("--year", help="العام الأكاديميّ (الافتراضيّ: عامُ كلّ مدرسة)")
        parser.add_argument(
            "--prune-orphans",
            action="store_true",
            help="مع --apply: احذف قوالبَ لأدوارٍ غيرِ موجودة ولا تقييمَ عليها",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if options["apply"] and options["dry_run"]:
            raise CommandError("--apply و--dry-run لا يجتمعان")
        schools = School.objects.order_by("code")
        if options["school"]:
            schools = schools.filter(code=options["school"])
        if not schools.exists():
            raise CommandError("لا مدرسةَ مطابقة")

        for school in schools:
            year = options["year"] or academic_year_for_school(school)
            plan = build_plan(school, year)
            self._show(plan)
            if options["apply"]:
                counts = apply_plan(plan, prune_orphans=options["prune_orphans"])
                self.stdout.write(self.style.SUCCESS(f"  كُتب: {counts}"))
        if not options["apply"]:
            self.stdout.write(self.style.WARNING("عرضٌ فقط — لم يُكتب شيء. أعد التشغيل بـ --apply."))

    def _show(self, plan: SchoolPlan) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING(f"{plan.school.code} — {plan.year}"))
        for tp in plan.templates:
            self.stdout.write(
                f"  [{_STATUS_LABEL[tp.status]}] {tp.role_name} ← {tp.form.title} "
                f"(§{tp.form.section}، المحاور {len(tp.form.axes)}، المجموع {tp.form.total_weight})"
            )
            for change in tp.changes:
                self.stdout.write(f"      {change}")
        for orphan in plan.orphans:
            self.stdout.write(
                self.style.WARNING(
                    f"  [يتيم] {orphan.role_name}: لا دورَ بهذا الاسم في Role.ROLES — لا تقرؤه شاشة"
                )
            )

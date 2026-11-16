"""استيرادُ مواضع حصص جدول aSc من PDF — مسودّةُ جدولٍ بلا تفعيل.

    Position ≠ Assignment      الموضعُ من الـPDF، والإسنادُ من المنصّة

المدرسةُ تعمل على جدول aSc والجدولُ الحيُّ في المنصّة من المولِّد، فالتبديلُ والإشغالُ يُحسبان
على مواضعَ غيرِ حقيقيّة. وهذا الأمرُ يستورد **موضعَ كلّ حصّةٍ فقط** (اليومُ ورقمُ الحصّة).
الإسناداتُ المعتمَدة `SubjectClassAssignment` هي المرجعُ ولا تُعدَّل، والتوقيتُ من جرس المنصّة.

ملفُّ الشعب مدقِّقٌ فقط: مجموعةُ خاناته (شعبة، يوم، حصّة) يجب أن تساوي مجموعةَ ملفّ المعلّمين.

## لا يكتب إلّا بأمر

يُطبع التقريرُ دائماً: ما لم يُطابَق، والتعارضات، وكلُّ إسنادٍ عددُ خاناته المستوردةِ لا يساوي
`weekly_periods`. و`--apply` يرفض إن بقي بندٌ فيه، إلّا أزواج (معلّم، شعبة) المذكورةَ في
`asc_ignore` بملفّ القواعد الخاصّ (راجع `import_assignments_from_timetable`). وما يكتبه
مسودّةٌ `ScheduleGeneration` حصصُها `is_active=False` — لا اعتمادَ ولا تفعيل.

    python manage.py import_schedule_from_asc_pdf --teachers t.pdf --classes c.pdf
    python manage.py import_schedule_from_asc_pdf --teachers t.pdf --classes c.pdf --apply

المنطقُ كلُّه في `academic_management.asc_import` (تناديه صفحةُ الرفع أيضاً)؛ وهنا الخياراتُ والطباعةُ فقط.
"""

from __future__ import annotations

import hashlib
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from academic_management import asc_import
from academic_management.management.commands.import_assignments_from_timetable import (
    Command as TimetableImport,
)
from academic_management.management.commands.import_assignments_from_timetable import (
    load_name_rules,
)
from core.academic_calendar import academic_year_for_school


def _sha256(path: str) -> str:
    try:
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except OSError as exc:
        raise CommandError(f"تعذّر فتحُ الملفّ: {path}") from exc


class Command(BaseCommand):
    help = "يستورد مواضع الحصص من PDF جدول aSc مسودّةً غيرَ مفعَّلة — بلا كتابةٍ إلّا بـ--apply"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--teachers", required=True, help="PDF «جدول المعلمين — مفرد»")
        parser.add_argument("--classes", required=True, help="PDF جدول الشعب — للتدقيق فقط")
        parser.add_argument("--school", default="", help="رمزُ المدرسة")
        parser.add_argument("--year", default="", help="العامُ الدراسيّ")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument(
            "--replace",
            action="store_true",
            help="يستبدل مسودّةَ الملفّين نفسيهما إن كانت draft وغيرَ مفعَّلة",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        school = TimetableImport()._school(options["school"])
        year = options["year"] or academic_year_for_school(school)
        rules = load_name_rules()
        sha_teachers, sha_classes = _sha256(options["teachers"]), _sha256(options["classes"])

        analysis = asc_import.analyze(school, year, options["teachers"], options["classes"], rules)
        self.stdout.write(f"المدرسة: {school.name} · العام: {year}")
        self.stdout.write(
            f"الملفّان: {analysis.lessons} حصّةً في ملفّ المعلّمين · {analysis.class_slots} خانةً في ملفّ الشعب"
        )
        self.stdout.write(
            f"بنودُ التقرير: {len(analysis.items)} · مانعةٌ لـ--apply: {len(analysis.blocking)}"
        )
        for item in analysis.items:
            mark = "  (متجاهَل)" if item not in analysis.blocking else ""
            self.stdout.write(f"   - {item.text}{mark}")

        if not options["apply"]:
            self.stdout.write("\nتقريرٌ فقط — أضِف --apply للكتابة.")
            return
        try:
            written = asc_import.write_draft(
                school, year, analysis, sha_teachers, sha_classes, options["replace"]
            )
        except asc_import.AscImportRefusedError as refusal:
            raise CommandError(f"{refusal.option} مرفوض: {refusal.reason}") from refusal
        self.stdout.write(
            f"\nكُتبت مسودّةٌ بـ{written} حصّةً غيرِ مفعَّلة."
            if written
            else "\nمسودّةُ هذين الملفّين موجودةٌ — لا شيءَ كُتب (أضِف --replace لاستبدالها)."
        )

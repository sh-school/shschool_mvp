"""
إعادةُ الحكم على نتائج العام الجاري بالحكم الواحد (`judge_student`) — عرضاً ثمّ صراحةً.

لماذا: تغيّر الحكمُ (الجبرُ على الكسر الدقيق، وأحكامُ الغياب م17–م27، والملحق، والحرمانُ
بقرار، والترفيعُ م50)، والنتيجةُ المخزَّنة لا تتغيّر إلّا حين تُحفظ درجةٌ أو يُضغط زرّ.

    python manage.py recalculate_grade_results                                # عرضٌ: من يتغيّر وكيف
    python manage.py recalculate_grade_results --apply --actor <الرقم الشخصي>

- **العرضُ افتراض**: يُحسب داخل معاملةٍ تُلغى، ويُطبع كلُّ من يتغيّر حكمُه بقيمتيه.
- **لكلّ مدرسةٍ معاملةٌ واحدة**: تُكتب قائمةُ التغييرات (قبل/بعد) في `AuditLog` **أوّلاً**،
  ثمّ تُعاد كتابةُ النتائج؛ فإن سقط إعدادٌ في منتصفها أُلغيت المدرسةُ كلُّها وسجلُّها معها —
  لا مدرسةَ على قاعدتين، ولا تغييرَ بلا أثر.
- **العامُ الجاري وحدَه**: الأعوامُ المغلقة مجمَّدة.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from assessments.models import AnnualSubjectResult, SubjectClassSetup
from assessments.services import GradeService
from core.academic_calendar import academic_year_for_school
from core.models import AuditLog, ClassGroup, CustomUser, School, StudentEnrollment

#: ما يُقارن قبل/بعد — الحكمُ كلُّه لا الحالةُ وحدَها.
FIELDS = ("status", "standing", "annual_total", "s1_total", "s2_total", "mark")

OP = "recalculate_grade_results"


class _RollbackError(Exception):
    pass


def _snapshot(school: School, year: str) -> dict[tuple[str, str], dict[str, str]]:
    rows = AnnualSubjectResult.objects.filter(school=school, academic_year=year).values_list(
        "student_id", "setup_id", *FIELDS
    )
    return {
        (str(r[0]), str(r[1])): {
            f: ("" if v is None else str(v)) for f, v in zip(FIELDS, r[2:], strict=False)
        }
        for r in rows
    }


def _recalculate(school: School, year: str) -> int:
    classes = ClassGroup.objects.filter(
        id__in=SubjectClassSetup.objects.filter(school=school, academic_year=year).values(
            "class_group_id"
        )
    )
    students = 0
    for class_group in classes:
        enrolled = [
            e.student
            for e in StudentEnrollment.objects.filter(
                class_group=class_group, is_active=True
            ).select_related("student")
        ]
        students += GradeService.recalculate_students(class_group, year, enrolled)
    return students


def _diff(
    before: dict[tuple[str, str], dict[str, str]], after: dict[tuple[str, str], dict[str, str]]
) -> list[dict[str, Any]]:
    changes = []
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        if old != new:
            changes.append({"student": key[0], "setup": key[1], "before": old, "after": new})
    return changes


class Command(BaseCommand):
    help = "إعادةُ الحكم على نتائج العام الجاري — عرضٌ بمن يتغيّر ما لم يُطلب --apply"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--apply", action="store_true", help="تطبيقُ إعادة الحساب")
        parser.add_argument("--actor", help="الرقمُ الشخصيّ لمن ينفّذ — إلزاميٌّ مع --apply")
        parser.add_argument("--school", help="رمزُ مدرسةٍ واحدة (الافتراض: كلُّ المدارس)")

    def handle(self, *args: Any, **options: Any) -> None:
        schools = School.objects.all()
        if options["school"]:
            schools = schools.filter(code=options["school"])
            if not schools.exists():
                raise CommandError(f"--school: لا مدرسةَ برمز {options['school']}.")
        actor = None
        if options["apply"]:
            if not options["actor"]:
                raise CommandError("--actor إلزاميٌّ للتطبيق: من ينفّذ يُكتب في سجلّ المراجعة.")
            actor = CustomUser.objects.filter(national_id=options["actor"]).first()
            if actor is None:
                raise CommandError("--actor: لا مستخدمَ بهذا الرقم الشخصيّ.")

        for school in schools:
            year = academic_year_for_school(school)
            before = _snapshot(school, year)
            # العرضُ أوّلاً — في كلّ حال: الحسابُ داخل معاملةٍ تُلغى، فتُعرف القائمةُ قبل الكتابة.
            planned: list[dict[str, Any]] = []
            try:
                with transaction.atomic():
                    students = _recalculate(school, year)
                    planned = _diff(before, _snapshot(school, year))
                    raise _RollbackError
            except _RollbackError:
                pass
            self._report(school, year, students, planned)
            if not options["apply"] or not planned:
                continue
            with transaction.atomic():
                # داخل معاملة المدرسة: يُعاد الحسابُ في نقطة حفظٍ تُلغى فتُعرف القائمة، ثمّ يُكتب
                # السجلُّ بها، ثمّ النتائج — وإن خالف المكتوبُ المسجَّلَ أُلغي كلُّ شيء.
                savepoint = transaction.savepoint()
                _recalculate(school, year)
                planned = _diff(before, _snapshot(school, year))
                transaction.savepoint_rollback(savepoint)
                log = AuditLog.objects.create(
                    school=school,
                    user=actor,
                    action="update",
                    model_name="other",
                    object_id=year,
                    object_repr=f"إعادةُ الحكم على نتائج العام {year}"[:300],
                    changes={
                        "op": OP,
                        "academic_year": year,
                        "students": students,
                        "changed": len(planned),
                        "rows": planned,
                    },
                )
                _recalculate(school, year)
                done = _diff(before, _snapshot(school, year))
                if done != planned:
                    # سجلُّ التدقيق لا يُعدَّل — فإن خالف المكتوبُ ما سُجِّل أُلغيت المدرسةُ كلُّها.
                    raise CommandError(
                        f"{school.code}: تغيّرت النتائجُ بين التسجيل والكتابة — أُلغي التطبيق، أعِد التشغيل."
                    )
            self.stdout.write(self.style.SUCCESS(f"  طُبّق · سجلّ المراجعة {log.pk}"))
        if not options["apply"]:
            self.stdout.write("عرضٌ فقط — أعِد بـ--apply --actor للتطبيق.")

    def _report(
        self, school: School, year: str, students: int, planned: list[dict[str, Any]]
    ) -> None:
        self.stdout.write(
            f"{school.code} · {year}: {students} طالباً · يتغيّر حكمُ {len(planned)} نتيجة"
        )
        for row in planned:
            old, new = row["before"] or {}, row["after"] or {}
            parts = [
                f"{f}: {old.get(f, '∅') or '—'} → {new.get(f, '∅') or '—'}"
                for f in FIELDS
                if old.get(f) != new.get(f)
            ]
            self.stdout.write(f"  {row['student']} · {row['setup']} · " + " · ".join(parts))

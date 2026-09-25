"""
إعادةُ الحكم على نتائج العام الجاري بالحكم الواحد (`judge_student`) — عرضاً ثمّ صراحةً.

لماذا: تغيّر الحكمُ (الجبرُ على الكسر الدقيق، وأحكامُ الغياب م17–م27، والملحق، والحرمانُ
بقرار، والترفيعُ م50، و«ملغي»، والبنيةُ من القرار 14/2018)، والنتيجةُ المخزَّنة لا تتغيّر
إلّا حين تُحفظ درجةٌ أو يُضغط زرّ.

    python manage.py recalculate_grade_results                                # عرضٌ: من يتغيّر وكيف
    python manage.py recalculate_grade_results --apply --actor <الرقم الشخصي>

- **العرضُ افتراض**: يُحسب الحكمُ (`VerdictEngine.plan_students`) ولا يُكتب شيء، ويُطبع كلُّ
  من يتغيّر حكمُه بقيمتيه.
- **لكلّ مدرسةٍ معاملةٌ واحدة**: تُحسب خططُ شُعبها كلِّها، ثمّ تُكتب قائمةُ التغييرات (قبل/بعد)
  في `AuditLog` **أوّلاً**، ثمّ تُكتب النتائج؛ فإن سقطت كتابةٌ في منتصفها أُلغيت المدرسةُ
  كلُّها وسجلُّها معها — لا مدرسةَ على قاعدتين، ولا تغييرَ بلا أثر.
- **المقارنةُ بالحكم كلِّه**: الحالةُ والموقفُ والمجاميعُ والكلمةُ والموضعُ والتنبيهُ وقصوى
  الدور الثاني، ودرجاتُ الباقات ومجموعُ كلّ فصل (`ANNUAL_AUDIT_FIELDS`، `SEMESTER_AUDIT_FIELDS`)
  — فصفٌّ لم يتغيّر فيه إلّا تنبيهٌ يُكتب.
- **التطبيقُ يشترط الراية**: `settings.VERDICT_ENGINE_ENABLED` (مطفأةٌ افتراضاً) — العرضُ متاحٌ دائماً
  ليُعرف الأثرُ قبل رفعها، والتطبيقُ لا يجري إلّا بعد أن تقرأ الشاشاتُ الحكمَ المخزَّن.
- **العامُ الجاري وحدَه**: الأعوامُ المغلقة مجمَّدة.
- **إصدارُ القواعد** (`AnnualSubjectResult.ruleset`): ما كُتب بقواعد أقدم لا يُعاد حسابُه جزئيّاً —
  أوّلُ حسابٍ في شعبته (حفظُ درجة، زرّ، قرار) يُعيد الحكمَ على الشعبة كلِّها؛ وهذا الأمرُ على
  المدرسة كلِّها. ويُكتب كلُّ صفٍّ بالإصدار الجاري ولو لم يتغيّر فيه حقل.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from assessments.models import SubjectClassSetup
from assessments.verdict_engine import VerdictEngine, VerdictPlan
from core.academic_calendar import academic_year_for_school
from core.models import AuditLog, ClassGroup, CustomUser, School, StudentEnrollment
from core.verdict_read import verdict_engine_enabled

OP = "recalculate_grade_results"


def _plans(school: School, year: str) -> list[VerdictPlan]:
    classes = ClassGroup.objects.filter(
        id__in=SubjectClassSetup.objects.filter(school=school, academic_year=year).values(
            "class_group_id"
        )
    )
    plans = []
    for class_group in classes:
        enrolled = [
            e.student
            for e in StudentEnrollment.objects.filter(
                class_group=class_group, is_active=True
            ).select_related("student")
        ]
        plans.append(VerdictEngine.plan_students(class_group, year, enrolled, restamp=True))
    return plans


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
        if options["apply"] and not verdict_engine_enabled():
            raise CommandError(
                "--apply مرفوضٌ والراية VERDICT_ENGINE_ENABLED مطفأة: الشاشاتُ ما زالت تقرأ الحالاتِ "
                "القديمة (fail/pass) فتعدّ «مُرفَّع» و«دور ثانٍ» خطأً. العرضُ (بلا --apply) متاح."
            )
        if options["apply"]:
            if not options["actor"]:
                raise CommandError("--actor إلزاميٌّ للتطبيق: من ينفّذ يُكتب في سجلّ المراجعة.")
            actor = CustomUser.objects.filter(national_id=options["actor"]).first()
            if actor is None:
                raise CommandError("--actor: لا مستخدمَ بهذا الرقم الشخصيّ.")

        for school in schools:
            year = academic_year_for_school(school)
            with transaction.atomic():
                plans = _plans(school, year)
                students = sum(p.students for p in plans)
                changes = [c for p in plans for c in p.changes]
                stale = sum(p.stale for p in plans)
                self._report(school, year, students, changes, stale)
                if not options["apply"] or not (changes or stale):
                    continue
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
                        "stale": stale,
                        "changed": len(changes),
                        "rows": changes,
                    },
                )
                for plan in plans:
                    plan.write(actor=actor, audit=False)
                self.stdout.write(self.style.SUCCESS(f"  طُبّق · سجلّ المراجعة {log.pk}"))
        if not options["apply"]:
            self.stdout.write("عرضٌ فقط — أعِد بـ--apply --actor للتطبيق.")

    def _report(
        self,
        school: School,
        year: str,
        students: int,
        changes: list[dict[str, Any]],
        stale: int = 0,
    ) -> None:
        self.stdout.write(
            f"{school.code} · {year}: {students} طالباً · يتغيّر {len(changes)} صفّاً من الحكم"
            f" · {stale} صفّاً بقواعد أقدم"
        )
        for row in changes:
            old, new = row["before"] or {}, row["after"] or {}
            parts = [
                f"{f}: {old.get(f, '∅') or '—'} → {new.get(f, '∅') or '—'}"
                for f in new
                if old.get(f) != new.get(f)
            ]
            self.stdout.write(
                f"  {row['student']} · {row['setup']} · {row['row']} · " + " · ".join(parts)
            )

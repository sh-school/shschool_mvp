"""نقلُ إسنادات المواد بين قاعدتين — بالأسماء لا بالمعرّفات.

    export → ملفٌ بأسماء الشعبة والمادّة والمعلّم
    import → مطابقةٌ بالأسماء على القاعدة الهدف، ثمّ كتابةٌ عبر خدمة الإسناد

ولمَ بالأسماء؟ لأنّ `UUID` الشعبةِ والمادّةِ والمعلّمِ يختلف بين قاعدةٍ وأخرى:
هما قاعدتان بُذرتا على حدة، فالمعرّفُ الذي يعني «التاسع/1» هنا يعني شيئاً آخر
هناك أو لا يعني شيئاً. والنقلُ بالمعرّف إمّا يسقط بخطأِ مفتاحٍ أجنبيّ — وهذا
أرحمُ — وإمّا ينجح خطأً فيُسند موادَّ لغير أصحابها بلا صوت.

## لا يكتب سطراً بلا `--apply`

التشغيلُ الافتراضيّ يعرض ما سيفعل ولا يفعله: كم سيُنشئ، وكم سيُعدّل، وكم لا
يحتاج شيئاً، وأيُّ سطرٍ تعذّر لأنّ اسمَه غيرُ موجودٍ في القاعدة الهدف. فمن
ينقل مئتين وخمسين إسناداً إلى الإنتاج يستحقّ أن يرى الخطّةَ قبل أن تقع.

## والكتابةُ عبر الخدمة لا حولها

`assignment_service.apply_assignment` هو المسارُ الوحيد: يفحص، ويسجّل في
التدقيق ما كان وما صار، ويحرس النقلَ من زميلٍ إلى آخر. والكتابةُ المباشرةُ
هنا كانت ستلتفّ على ذلك كلِّه — فتنقل البياناتِ وتترك السجلَّ أعمى.
"""

import json
import sys

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from academic_management import assignment_service as service
from core.academic_calendar import default_academic_year
from core.models import ClassGroup, CustomUser, Membership, School
from core.models.access import TEACHING_ROLES
from operations.models import Subject, SubjectClassAssignment


def _payload(assignment):
    """صورةُ الإسناد بالأسماء — ما يكفي لإعادة بنائه في قاعدةٍ أخرى."""
    return {
        "grade": assignment.class_group.grade,
        "section": assignment.class_group.section,
        "track": assignment.class_group.track or "",
        "subject": assignment.subject.name_ar,
        "teacher": assignment.teacher.full_name if assignment.teacher else "",
        "weekly_periods": assignment.weekly_periods,
        "parallel_group": assignment.parallel_group or "",
        "requires_lab": assignment.requires_lab,
        "override_reason": assignment.periods_override_reason or "",
    }


class Resolver:
    """يترجم أسماءَ الملفّ إلى كائنات القاعدة الهدف — ويسمّي ما لم يجده."""

    def __init__(self, school, year):
        self.school = school
        self.year = year
        self.classes = {
            (c.grade, c.section): c
            for c in ClassGroup.objects.filter(school=school, academic_year=year, is_active=True)
        }
        self.subjects = {s.name_ar.strip(): s for s in Subject.objects.filter(school=school)}
        # الاسمُ الكامل مفتاحاً — بين من يحمل عضويّةَ تدريسٍ حيّةً في هذه المدرسة
        # وحدَهم. فالاسمُ الواحد قد يكون لمعلّمٍ ولمطوّرِ المنصّة وهما شخصٌ واحدٌ
        # بحسابين، أو لمعلّمٍ وطالبٍ من أسرةٍ واحدة؛ ولا يُسنَد إلّا لمن يدرّس.
        # وما بقي مكرَّراً بعد ذلك يُسقَط من الجدول كي لا يُختار أحدُهما بالقرعة:
        # نقلٌ يقف ويسمّي خيرٌ من نقلٍ يُصيب نصفَ الوقت.
        teaching_ids = Membership.objects.filter(
            school=school, is_active=True, role__name__in=TEACHING_ROLES
        ).values_list("user_id", flat=True)
        names = {}
        for user in CustomUser.objects.filter(is_active=True, id__in=teaching_ids).only(
            "id", "full_name"
        ):
            key = user.full_name.strip()
            names[key] = None if key in names else user
        self.teachers = {k: v for k, v in names.items() if v is not None}
        self.ambiguous = {k for k, v in names.items() if v is None}

    def resolve(self, row):
        """يُرجع (الشعبة، المادّة، المعلّم) أو يرفع سببَ التعذّر نصّاً."""
        klass = self.classes.get((row["grade"], row["section"]))
        if klass is None:
            raise LookupError(f"لا شعبةَ {row['grade']}/{row['section']} في {self.year}")

        subject = self.subjects.get(row["subject"].strip())
        if subject is None:
            raise LookupError(f"لا مادّةَ باسم «{row['subject']}»")

        name = (row.get("teacher") or "").strip()
        if not name:
            return klass, subject, None
        if name in self.ambiguous:
            raise LookupError(f"اسمٌ مكرَّر: «{name}» — لأكثرَ من مستخدم")
        teacher = self.teachers.get(name)
        if teacher is None:
            raise LookupError(f"لا معلّمَ باسم «{name}»")
        return klass, subject, teacher


class Command(BaseCommand):
    help = "تصديرُ إسنادات المواد أو استيرادُها بالمطابقة بالأسماء"

    def add_arguments(self, parser):
        parser.add_argument("mode", choices=["export", "import"])
        parser.add_argument(
            "--file",
            default="-",
            help="مسارُ الملفّ، و«-» للمُدخَل/المُخرَج القياسيّ (الافتراض)",
        )
        parser.add_argument("--year", default="", help="العامُ الدراسيّ (الافتراض: الجاري)")
        parser.add_argument(
            "--apply",
            action="store_true",
            help="نفِّذ فعلاً — وبدونه يُعرض ما سيقع ولا يقع",
        )
        parser.add_argument(
            "--deactivate-missing",
            action="store_true",
            help="أبطِل إسناداتِ الهدف التي ليست في الملفّ (شعبةٌ أُغلقت مثلاً)",
        )
        parser.add_argument(
            "--by",
            default="",
            help="الاسمُ الكاملُ لمن يُنسب إليه التغييرُ في سجلّ التدقيق",
        )

    def handle(self, *args, **options):
        school = School.objects.first()
        if school is None:
            raise CommandError("لا مدرسةَ في هذه القاعدة.")
        year = options["year"] or default_academic_year()

        if options["mode"] == "export":
            return self._export(school, year, options["file"])
        return self._import(school, year, options)

    # ── تصدير ────────────────────────────────────────────────────

    def _export(self, school, year, path):
        rows = [
            _payload(a)
            for a in SubjectClassAssignment.objects.filter(
                school=school, academic_year=year, is_active=True
            ).select_related("class_group", "subject", "teacher")
        ]
        rows.sort(key=lambda r: (r["grade"], r["section"], r["subject"], r["teacher"]))
        text = json.dumps({"year": year, "rows": rows}, ensure_ascii=False, indent=1)
        if path == "-":
            self.stdout.write(text)
        else:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
            self.stderr.write(f"صُدِّر {len(rows)} إسناداً إلى {path}")

    # ── استيراد ──────────────────────────────────────────────────

    def _read(self, path):
        raw = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CommandError(f"الملفُّ ليس JSON صالحاً: {exc}") from exc
        if not isinstance(data.get("rows"), list):
            raise CommandError("الملفُّ بلا حقل `rows`.")
        return data["rows"]

    def _plan(self, rows, resolver, school, year):
        """يُصنّف كلَّ سطر: إنشاءٌ أم تعديلٌ أم لا شيء أم تعذُّر."""
        existing = {
            (a.class_group_id, a.subject_id, a.teacher_id): a
            for a in SubjectClassAssignment.objects.filter(
                school=school, academic_year=year, is_active=True
            )
        }
        seen, plan, failed = set(), [], []
        for row in rows:
            try:
                klass, subject, teacher = resolver.resolve(row)
            except LookupError as exc:
                failed.append((row, str(exc)))
                continue
            key = (klass.id, subject.id, teacher.id if teacher else None)
            seen.add(key)
            found = existing.get(key)
            if found and (
                found.weekly_periods == row["weekly_periods"]
                and (found.parallel_group or "") == row["parallel_group"]
                and found.requires_lab == row["requires_lab"]
            ):
                plan.append(("same", row, klass, subject, teacher))
            else:
                plan.append(("update" if found else "create", row, klass, subject, teacher))
        stale = [a for key, a in existing.items() if key not in seen]
        return plan, failed, stale

    def _import(self, school, year, options):
        rows = self._read(options["file"])
        resolver = Resolver(school, year)
        plan, failed, stale = self._plan(rows, resolver, school, year)

        counts = {kind: 0 for kind in ("create", "update", "same")}
        for kind, *_ in plan:
            counts[kind] += 1
        self.stderr.write(
            f"الملفّ {len(rows)} سطراً | إنشاء {counts['create']} | تعديل {counts['update']}"
            f" | بلا تغيير {counts['same']} | تعذّر {len(failed)} | زائدٌ في الهدف {len(stale)}"
        )
        for row, why in failed:
            self.stderr.write(f"  ✗ {row['grade']}/{row['section']} {row['subject']}: {why}")
        for assignment in stale:
            self.stderr.write(f"  ⌫ زائد: {assignment.class_group} | {assignment.subject}")

        if not options["apply"]:
            self.stderr.write("عرضٌ فقط — أضِف --apply للتنفيذ.")
            return
        if failed:
            raise CommandError("لن يُنفَّذ شيءٌ ما دام سطرٌ واحدٌ متعذّراً — صحّح الأسماءَ أوّلاً.")

        by = None
        if options["by"]:
            by = CustomUser.objects.filter(full_name=options["by"].strip()).first()

        written, refused = 0, []
        with transaction.atomic():
            for kind, row, klass, subject, teacher in plan:
                if kind == "same":
                    continue
                try:
                    service.apply_assignment(
                        school=school,
                        academic_year=year,
                        class_group=klass,
                        subject=subject,
                        teacher=teacher,
                        weekly_periods=row["weekly_periods"],
                        by=by,
                        override_reason=row["override_reason"],
                        parallel_group=row["parallel_group"],
                        requires_lab=row["requires_lab"],
                        confirm_transfer=True,
                    )
                    written += 1
                except service.AssignmentError as exc:
                    refused.append((row, "؛ ".join(f.message for f in exc.findings if f.blocks)))

            if options["deactivate_missing"]:
                for assignment in stale:
                    service.remove_assignment(
                        assignment=assignment,
                        by=by,
                        reason="أُبطل بمزامنة الإسنادات — ليس في المصدر",
                    )

            if refused:
                for row, why in refused:
                    self.stderr.write(
                        f"  ✗ رُفض {row['grade']}/{row['section']} {row['subject']}: {why}"
                    )
                raise CommandError(f"رُفض {len(refused)} إسناداً — أُلغيت المعاملةُ كلُّها.")

        self.stderr.write(
            f"كُتب {written} إسناداً"
            + (f"، وأُبطل {len(stale)}" if options["deactivate_missing"] else "")
        )

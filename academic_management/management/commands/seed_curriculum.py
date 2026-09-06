"""بذرُ الخطّة الدراسيّة من دليل الوزارة — ومن تجربةِ العاشر بوسمها.

    HistoricalAssignment → DepartmentHint        (وليس → Demand)

فالأرقامُ من الدليل المنشور لا من الإسناد القائم: لو استُنسخ الطلبُ من الواقع
لصار كلُّ خطأٍ في الواقع قاعدةً تُقاس عليها الأعوامُ القادمة، وهو عينُ ما
كلّفنا سبعةَ عشرَ سجلّاً حين كان عددُ الحصص يُكتب يدويّاً بلا مرجع.

والإسنادُ القائمُ يُستشار في شيءٍ واحدٍ فقط: **قسمُ المادّة في الصفّ**. فقسمُ
«العلوم» في السابع غيرُ قسمها في العاشر، وليس في الدليل ما يقوله — إنّما
يقوله واقعُ المدرسة: من يدرّسها اليومَ، وفي أيّ قسمٍ عضويّتُه.

## الاستثناءان الصريحان

علومُ العاشر يدرّسها معلّمو الفيزياء والكيمياء والأحياء (قرارُ الإدارة)، فلو
استُنتج قسمُها من معلّميها لخرج «مختلطاً». وهي بقرار الإدارة تتبع **قسم العلوم
الثانويّ** — أي قسمَ من يدرّس الأحياءَ في الحادي عشر.

والمهاراتُ الحياتيّةُ والمهنيّةُ يدرّسها معلّمو بدنيّةٍ وإدارةِ أعمالٍ وأحياء،
فلا قسمَ لها — وجولتُها عامّةٌ بيد النائب الأكاديميّ.

## ولا يكتب إلّا بأمر

بلا `--apply` يطبع التقريرَ ولا يمسّ القاعدة. وبها يكتب متعادلاً: تشغيلُه
مرّتين لا يُنتج سجلّاً مكرّراً ولا يغيّر ما لم يتغيّر.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from academic_management.models import (
    FROM_MINISTRY_GUIDE,
    FROM_PILOT,
    FROM_SCHOOL,
    CurriculumPlan,
)
from core.models import ClassGroup, Membership, School

GUIDE = "دليل الخطط الدراسية 2025-2026"
PILOT_REFERENCE = ""  # تعميمُ التجربة لم يصل بعد — يُملأ من لوحة الإدارة.

#: الإعداديّ: المستويات السابع إلى التاسع — الدليل ص14، المجموع 34.
PREP = {
    "ISL": 4,
    "ARA": 5,
    "ENG": 5,
    "MAT": 5,
    "SCI": 4,
    "SOC": 3,
    "TECH": 2,
    "PE": 2,
    "ART": 2,
    "LFS": 2,
}

#: العاشر — **تجربةٌ وزاريّة** تطبّقها مدارسُ مختارة منها هذه المدرسة: دمجُ
#: الكيمياء والفيزياء والأحياء في «علوم» بستّ حصص، والعربيّةُ والرياضياتُ ستٌّ
#: بدل خمس. والمجموعُ 35 كما في الدليل، والتوزيعُ يخالفه (ص17).
G10_PILOT = {
    "ISL": 3,
    "ARA": 6,
    "ENG": 5,
    "MAT": 6,
    "SCI": 6,
    "SOC": 3,
    "TECH": 2,
    "PE": 2,
    "LFS": 2,
}

#: الثانويّ بمساراته — الدليل ص18 و19 و20، المجموع 35 لكلّ مستوى.
#: والبدنيّةُ حصّتان في الحادي عشر وواحدةٌ في الثاني عشر، والإنجليزيّةُ خمسٌ
#: ثمّ ستّ. والاختياريّةُ حصّتان لا تُذكر هنا: بدائلُها تُبذر ممّا تعرضه
#: المدرسةُ فعلاً، فالدليلُ يعطي القائمةَ والمدرسةُ تختار منها.
SECONDARY = {
    ("G11", "science"): {
        "ISL": 3,
        "ARA": 3,
        "ENG": 5,
        "MAT": 6,
        "CHM": 4,
        "PHY": 4,
        "BIO": 4,
        "PE": 2,
        "LFS": 2,
    },
    ("G12", "science"): {
        "ISL": 3,
        "ARA": 3,
        "ENG": 6,
        "MAT": 6,
        "CHM": 4,
        "PHY": 4,
        "BIO": 4,
        "PE": 1,
        "LFS": 2,
    },
    ("G11", "humanities"): {
        "ISL": 3,
        "ARA": 6,
        "ENG": 5,
        "MAT": 3,
        "GSC": 4,
        "GEO": 4,
        "HIS": 4,
        "PE": 2,
        "LFS": 2,
    },
    ("G12", "humanities"): {
        "ISL": 3,
        "ARA": 6,
        "ENG": 6,
        "MAT": 3,
        "GSC": 4,
        "GEO": 4,
        "HIS": 4,
        "PE": 1,
        "LFS": 2,
    },
    ("G11", "technology"): {
        "ISL": 3,
        "ARA": 3,
        "ENG": 5,
        "MAT": 6,
        "PHY": 4,
        "IT": 4,
        "CS": 4,
        "PE": 2,
        "LFS": 2,
    },
    ("G12", "technology"): {
        "ISL": 3,
        "ARA": 3,
        "ENG": 6,
        "MAT": 6,
        "PHY": 4,
        "IT": 4,
        "CS": 4,
        "PE": 1,
        "LFS": 2,
    },
}

#: صفحةُ الدليل لكلّ نطاق — فمرجعٌ بلا صفحةٍ ادّعاءُ مصدر.
PAGES = {
    ("G7", ""): "ص14",
    ("G8", ""): "ص14",
    ("G9", ""): "ص14",
    ("G11", "humanities"): "ص18",
    ("G12", "humanities"): "ص18",
    ("G11", "science"): "ص19",
    ("G12", "science"): "ص19",
    ("G11", "technology"): "ص20",
    ("G12", "technology"): "ص20",
}

ELECTIVE_GROUP = "elective"
ELECTIVE_PERIODS = 2

#: قسمُ هذا النطاق يُنسخ عن نطاقٍ آخر بدل استنتاجه من معلّميه.
DEPARTMENT_FROM = {
    ("G10", "", "SCI"): ("G11", "science", "BIO"),
}

#: بلا قسم — جولتُها عامّةٌ بيد النائب الأكاديميّ.
NO_DEPARTMENT = {"LFS"}


def _scopes():
    """كلُّ (صفّ، مسار) في الخطّة مع حصصه ومنبعه ومرجعه."""
    out = {}
    for grade in ("G7", "G8", "G9"):
        out[(grade, "")] = (PREP, FROM_MINISTRY_GUIDE, f"{GUIDE} {PAGES[(grade, '')]}")
    out[("G10", "")] = (G10_PILOT, FROM_PILOT, PILOT_REFERENCE)
    for scope, periods in SECONDARY.items():
        out[scope] = (periods, FROM_MINISTRY_GUIDE, f"{GUIDE} {PAGES[scope]}")
    return out


class Command(BaseCommand):
    help = "يبذر الخطّة الدراسيّة من الدليل الوزاريّ ومن تجربة العاشر — بلا --apply لا يكتب."

    def add_arguments(self, parser):
        parser.add_argument("--year", required=True, help="العام الدراسي، مثال 2026-2027")
        parser.add_argument("--school", default="", help="رمزُ المدرسة أو اسمُها — يُلزَم عند تعدّدها")
        parser.add_argument("--apply", action="store_true", help="اكتب فعلاً؛ وبدونها تقريرٌ فقط")

    # ── الأدوات ──────────────────────────────────────────────────

    def _school(self, name):
        schools = School.objects.all()
        if name:
            school = schools.filter(name__icontains=name).first()
            if school is None:
                raise CommandError(f"لا مدرسةَ باسم «{name}».")
            return school
        if schools.count() != 1:
            raise CommandError("أكثرُ من مدرسة — حدّدها بـ--school.")
        return schools.first()

    def _subjects(self, school):
        from operations.models import Subject

        by_code = {}
        for subject in Subject.objects.filter(school=school):
            if subject.code:
                by_code[subject.code.upper()] = subject
        return by_code

    def _teacher_departments(self, school):
        """قسمُ كلّ معلّمٍ من عضويّته — ومن لا عضويّةَ قسمٍ له لا يدلّ على شيء."""
        out = {}
        rows = Membership.objects.filter(
            school=school, is_active=True, department_obj__isnull=False
        ).select_related("department_obj")
        for m in rows:
            out.setdefault(m.user_id, m.department_obj)
        return out

    def _observed_departments(self, school, year, teacher_departments):
        """(صفّ، مسار، رمزُ المادّة) → مجموعةُ الأقسام التي يدرّسها معلّموها اليوم."""
        from operations.models import SubjectClassAssignment

        seen = {}
        rows = SubjectClassAssignment.objects.live(school, year=year).select_related(
            "class_group", "subject"
        )
        for a in rows:
            if a.class_group.has_own_timetable or a.teacher_id is None or not a.subject.code:
                continue
            key = (a.class_group.grade, a.class_group.track, a.subject.code.upper())
            department = teacher_departments.get(a.teacher_id)
            if department is not None:
                seen.setdefault(key, set()).add(department)
        return seen

    def _observed_electives(self, school, year, planned_codes):
        """البدائلُ التي تعرضها المدرسةُ فعلاً في كلّ (صفّ، مسار).

        فالدليلُ يعطي القائمةَ — الفنونُ وإدارةُ الأعمال والحوسبةُ واللغاتُ
        وعلومُ الأرض — والمدرسةُ تختار منها. وبذرُ القائمة كلِّها يُنشئ طلباً
        لموادَّ لا تُدرَّس هنا.
        """
        from operations.models import SubjectClassAssignment

        offered = {}
        rows = SubjectClassAssignment.objects.live(school, year=year).select_related(
            "class_group", "subject"
        )
        for a in rows:
            cg = a.class_group
            if cg.has_own_timetable or not a.subject.code:
                continue
            scope = (cg.grade, cg.track)
            code = a.subject.code.upper()
            if code in planned_codes.get(scope, ()):
                continue
            offered.setdefault(scope, {}).setdefault(code, set()).add(cg.id)
        return offered

    # ── التنفيذ ──────────────────────────────────────────────────

    def handle(self, *args, **options):
        year = options["year"]
        school = self._school(options["school"])
        subjects = self._subjects(school)
        teacher_departments = self._teacher_departments(school)
        observed = self._observed_departments(school, year, teacher_departments)

        known = bool(teacher_departments)
        if not known:
            self.stdout.write(
                self.style.WARNING(
                    "لا عضويّةَ قسمٍ في هذه المدرسة — تُبذر الخطّةُ بأقسامٍ فارغة، وتُملأ لاحقاً."
                )
            )

        scopes = _scopes()
        planned_codes = {scope: set(periods) for scope, (periods, _, _) in scopes.items()}
        electives = self._observed_electives(school, year, planned_codes)

        live_scopes = {
            (c.grade, c.track)
            for c in ClassGroup.objects.filter(
                school=school, academic_year=year, is_active=True, has_own_timetable=False
            )
        }

        rows, problems, notes = [], [], []

        for scope, (periods, source_kind, reference) in scopes.items():
            grade, track = scope
            if scope not in live_scopes:
                notes.append(
                    f"{grade}{'/' + track if track else ''}: لا شعبةَ لها هذا العام — تُتجاوز."
                )
                continue

            for code, weekly in periods.items():
                subject = subjects.get(code)
                if subject is None:
                    problems.append(f"{grade}{track}: لا مادّةَ برمز «{code}» في هذه المدرسة.")
                    continue
                department, note = self._resolve_department(grade, track, code, observed, known)
                if note:
                    (problems if note.startswith("!") else notes).append(note.lstrip("! "))
                rows.append(
                    {
                        "grade": grade,
                        "track": track,
                        "subject": subject,
                        "weekly_periods": weekly,
                        "source_kind": source_kind,
                        "source_reference": reference,
                        "is_pilot": source_kind == FROM_PILOT,
                        "department": department,
                        "elective_group": "",
                    }
                )

            for code in sorted(electives.get(scope, {})):
                subject = subjects.get(code)
                if subject is None:
                    continue
                department, note = self._resolve_department(grade, track, code, observed, known)
                if note:
                    (problems if note.startswith("!") else notes).append(note.lstrip("! "))
                rows.append(
                    {
                        "grade": grade,
                        "track": track,
                        "subject": subject,
                        "weekly_periods": ELECTIVE_PERIODS,
                        "source_kind": FROM_SCHOOL,
                        "source_reference": f"بديلٌ من قائمة {GUIDE} ص18–20 — اختيارُ المدرسة",
                        "is_pilot": False,
                        "department": department,
                        "elective_group": ELECTIVE_GROUP,
                    }
                )

        self._report(rows, problems, notes, scopes, live_scopes)

        if problems:
            raise CommandError(
                f"{len(problems)} مسألةً تمنع الكتابة — حُلّها أوّلاً، فالخطّةُ تُبذر مرّةً وتُقاس عليها السنة."
            )
        if not options["apply"]:
            self.stdout.write(self.style.WARNING("\nتقريرٌ فقط — أضف --apply لتُكتب."))
            return
        self._write(school, year, rows)

    def _resolve_department(self, grade, track, code, observed, known):
        """قسمُ هذه المادّة في هذا الصفّ — استنتاجاً أو باستثناءٍ صريح.

        و`known` تقول إن كانت المدرسةُ سجّلت أقسامَها أصلاً. فمدرسةٌ بلا أقسامٍ
        تُبذر خطّتُها بأقسامٍ فارغةٍ وتُملأ لاحقاً — أمّا مدرسةٌ لها أقسامٌ
        وعجز صفٌّ واحدٌ عن الانتساب إليها فذاك خللٌ يُوقف الكتابة.
        """
        if code in NO_DEPARTMENT or not known:
            return None, None

        source = DEPARTMENT_FROM.get((grade, track, code))
        if source:
            found = observed.get(source)
            if not found:
                return None, f"! {grade} {code}: قسمُه يُنسخ عن {source} ولا إسنادَ هناك."
            if len(found) > 1:
                return None, f"! {grade} {code}: مصدرُ قسمه {source} مختلطٌ بين {len(found)} قسماً."
            department = next(iter(found))
            return department, f"{grade} {code}: قسمُه «{department.name}» بالاستثناء المعتمَد."

        found = observed.get((grade, track, code))
        if not found:
            return None, f"{grade}{track} {code}: لا إسنادَ يدلّ على قسمه — يُترك فارغاً."
        if len(found) > 1:
            names = "، ".join(sorted(d.name for d in found))
            return None, f"! {grade}{track} {code}: معلّموه من أقسامٍ مختلفة ({names})."
        return next(iter(found)), None

    # ── العرضُ والكتابة ──────────────────────────────────────────

    def _report(self, rows, problems, notes, scopes, live_scopes):
        from academic_management.curriculum_service import expected_total

        self.stdout.write(self.style.MIGRATE_HEADING("\nالخطّة الدراسيّة المقترَحة"))
        by_scope = {}
        for r in rows:
            by_scope.setdefault((r["grade"], r["track"]), []).append(r)

        for scope in sorted(by_scope, key=lambda s: (len(s[0]), s[0], s[1])):
            grade, track = scope
            scope_rows = by_scope[scope]
            fake = [
                type(
                    "Row",
                    (),
                    {"weekly_periods": r["weekly_periods"], "elective_group": r["elective_group"]},
                )()
                for r in scope_rows
            ]
            total = expected_total(fake)
            expected = 34 if grade in ("G7", "G8", "G9") else 35
            mark = "✓" if total == expected else "✗"
            label = f"{grade}{'/' + track if track else ''}"
            self.stdout.write(f"\n  {label} — {len(scope_rows)} مادّةً، المجموع {total} {mark}")
            if total != expected:
                problems.append(f"{label}: المجموع {total} والمتوقَّع {expected}.")
            for r in sorted(scope_rows, key=lambda x: -x["weekly_periods"]):
                dept = r["department"].name if r["department"] else "— بلا قسم —"
                elective = " (اختياريّة)" if r["elective_group"] else ""
                pilot = " ★تجريبيّة" if r["is_pilot"] else ""
                self.stdout.write(
                    f"      {r['weekly_periods']:>2}  {r['subject'].name_ar}{elective}{pilot}  ·  {dept}"
                )

        for scope in sorted(live_scopes - set(scopes)):
            self.stdout.write(
                self.style.WARNING(
                    f"\n  شعبةٌ بلا خطّة: {scope[0]}{'/' + scope[1] if scope[1] else ''}"
                )
            )

        if notes:
            self.stdout.write(self.style.MIGRATE_HEADING("\nملاحظات"))
            for n in dict.fromkeys(notes):
                self.stdout.write(f"  · {n}")
        if problems:
            self.stdout.write(self.style.ERROR("\nمسائلُ تمنع الكتابة"))
            for p in dict.fromkeys(problems):
                self.stdout.write(self.style.ERROR(f"  ✗ {p}"))

    @transaction.atomic
    def _write(self, school, year, rows):
        created = updated = 0
        for r in rows:
            row, was_created = CurriculumPlan.objects.update_or_create(
                school=school,
                academic_year=year,
                grade=r["grade"],
                track=r["track"],
                subject=r["subject"],
                defaults={
                    "weekly_periods": r["weekly_periods"],
                    "source_kind": r["source_kind"],
                    "source_reference": r["source_reference"],
                    "is_pilot": r["is_pilot"],
                    "department": r["department"],
                    "elective_group": r["elective_group"],
                    "is_active": True,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1
        self.stdout.write(
            self.style.SUCCESS(f"\nكُتبت الخطّة: {created} صفّاً جديداً · {updated} صفّاً موجوداً حُدّث.")
        )

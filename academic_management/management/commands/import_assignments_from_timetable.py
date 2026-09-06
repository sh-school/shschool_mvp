"""إسنادُ الأنصبة من جدولٍ خارجيّ — الأرقامُ منه، والجدولةُ من المنصّة.

    Timetable → Assignments        ولا يُستورَد الجدولُ نفسُه

المدرسةُ تبني جدولَها في aSc وتُصدّره «جدول المعلمين — مفرد»: صفحةٌ لكلّ معلّم.
وهذا الأمرُ يقرأ منه **من يدرّس ماذا لأيّ شعبةٍ وكم حصّة** فحسب، ويكتبه إسناداً
في المنصّة. أمّا التوقيتُ وتوزيعُ الأيّام فمن المنصّة (قرارُ المستخدم
2026-09-06): مولّدُها يبني الجدولَ من هذه الأنصبة.

## المطابقة

الأسماءُ في الملفّ مختصرةٌ («أحمد أغلو») وفي المنصّة كاملة («احمد محمد أوغلو»)،
فتُوحَّد الحروفُ (ألفٌ وهمزةٌ وتاءٌ مربوطةٌ وياءٌ وتطويل) ثمّ يُطابَق بالتضمّن:
كلُّ كلمةٍ في الملفّ موجودةٌ في اسم المنصّة، ومطابقةٌ واحدةٌ لا أكثر. وما التبس
يُذكر ولا يُخمَّن.

## لا يكتب إلّا بأمر

يُطبع التقريرُ أوّلاً: كم إسناداً يُضاف ويُعدَّل ويُحذف، وما لم يُطابَق، وأين
تتعارض البيانات. ولا تُمسّ القاعدةُ إلّا بـ`--apply`.

    python manage.py import_assignments_from_timetable --file data/lessons.tsv
    python manage.py import_assignments_from_timetable --file data/lessons.tsv --apply
"""

import csv
import re
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from academic_management import assignment_service as svc
from core.academic_calendar import academic_year_for_school
from core.models import ClassGroup, CustomUser, Membership, School
from operations.models import Subject, SubjectClassAssignment

TEACHING_ROLES = ("teacher", "ese_teacher", "coordinator", "e_projects_coordinator")

#: أرقامُ الصفوف في الملفّ ← رموزُها في المنصّة.
GRADES = {str(n): f"G{n}" for n in range(7, 13)}

_ALEF = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ـ": ""})

#: أسماءٌ مركّبةٌ تُكتب موصولةً ومفصولة: «عبد الله» و«عبدالله». تُوصَل هنا
#: بجزأيها معاً لا بالبادئة وحدَها — وإلّا التصق «عماد» بـ«العبسي» فصار اسماً
#: لا وجودَ له.
JOINED_PREFIXES = ("عبد", "عماد")
JOINED_SECONDS = (
    "الله",
    "الرحمن",
    "الرحيم",
    "العزيز",
    "الكريم",
    "اللطيف",
    "الحميد",
    "المجيد",
    "الوهاب",
    "الرزاق",
    "القادر",
    "الفتاح",
    "السلام",
    "الهادي",
    "الغني",
    "الدين",
)

#: أسماءُ معلّمين في الجدول لا تُطابق أسماءَ المنصّة بحروفها — تُربط صراحةً.
#: «علي ضيف» اسمان في المدرسة، ففُصل بمادّته: الاجتماعيّاتُ لحمد عليّ، والأحياءُ
#: لخريسات. و«يوسف عثامنه» اسمُ شهرةٍ لا يشبه المسجَّل — والفنّيّةُ تدلّ عليه.
TEACHER_ALIASES = {
    "علي ضيف": "على ضيف الله حمد على",
    "يوسف عثامنه": "يوسف جميل سليمان العبدالله",
    "عبدالرحمن رجا": "عبدالرحمن فيصل اسماعيل راجه",
    "وليد جمعه عبد اللطيف": "وليد عبد اللطيف",
}

#: خانةٌ ظهرت في صفحتَي معلّمَين وليست مقسومةً بينهما — أحياءُ 12/1 أربعُ
#: حصصٍ لمعلّمٍ واحدٍ لا نصفان. ومنسّقُ الأحياء أحمد محمد إبراهيم مُجازٌ وعليّ
#: خريسات يقوم بجدوله (2026-09-07)، فالحصصُ باسم القائم بها كما أثبتها
#: المستخدمُ في الشاشة — والمنصّةُ تسجّل من يُدرّس لا من يُنسَب إليه.
SOLE_HOLDERS = {("12.1", "احياء"): "علي خريسات"}

#: نصفُ شعبةٍ سمّاه aSc باسم نصفها الآخر. فالخانةُ المقسومةُ في تصديره
#: تُطبع بمادّةٍ واحدةٍ على صفحتَي المعلّمَين، وهي في الحقيقة مادّتان: نصفٌ
#: إلى معمل الحاسب ونصفٌ إلى غرفة الفنون — وهو ما تقوله الخطّةُ الدراسيّة
#: نفسُها (مجموعةُ اختيارٍ في 11/1 و11/2 و12/1 و12/2). فيُصحَّح باسم قسم
#: المعلّم لا بالتخمين: مدرّسُ الفنون يُدرّس الفنون، ومدرّسُ التكنولوجيا
#: يُدرّس التكنولوجيا (قرارُ المستخدم 2026-09-07).
SPLIT_SUBJECTS = {
    ("11.1", "عبد الله الرمضان"): "الفنون البصرية",
    ("11.2", "احمد رمضان حامد"): "ادارة اعمال",
    ("12.1", "محمد اسماعيل السيد"): "التكنولوجيا",
    ("12.2", "يوسف يعقوب عوض"): "الفنون البصرية",
}

#: بادئةُ وسم الشعبة المقسومة. والوسمُ **واحدٌ لنصفَي الشعبة** لا وسمان:
#: المولّدُ يجمع في خانةٍ واحدةٍ كلَّ ما تشارك الوسمَ، فلو اختلف الوسمان
#: لجُدولا في خانتين وشغلت الشعبةُ ضِعفَ زمنها.
SPLIT_TAG = "نصفان"

#: أسماءٌ في الجدول لا تُطابق تسميةَ المنصّة بالحروف — تُربط صراحةً لا بالتخمين.
SUBJECT_ALIASES = {
    "علوم اجتماعيه": "الدراسات الاجتماعية",
    "علوم عامه": "العلوم العامة",
    "تربيه بدنيه 1trops": "التربية البدنية",
    "تربيه بدنيه 2trops": "التربية البدنية",
    "مهارات حياتيه": "المهارات الحياتية والمهنية",
    "الحياتيه": "المهارات الحياتية والمهنية",
}


def normal(text: str) -> str:
    """توحيدُ الاسم: تطويلٌ يسقط، وأل التعريفُ تسقط، و«عبد الله» تُوصَل.

    فالاسمُ الواحدُ يُكتب بوجهين: «عبد الله» و«عبدالله»، «عماد الدين»
    و«عمادالدين». وفصلُهما يجعل الكلمتين ثلاثاً فتسقط المطابقة.
    """
    text = (text or "").translate(_ALEF).lower()
    words = [w for w in re.split(r"\s+", text) if w]

    joined = []
    for word in words:
        if joined and joined[-1] in JOINED_PREFIXES and word in JOINED_SECONDS:
            joined[-1] += word
        else:
            joined.append(word)

    return " ".join(w[2:] if w.startswith("ال") and len(w) > 3 else w for w in joined)


def tokens(name: str) -> set:
    return {t for t in normal(name).split() if len(t) > 1}


def closeness(a: str, b: str) -> float:
    """قربُ اسمين — لمطابقة «أحمد أغلو» بـ«احمد محمد أوغلو»."""
    from difflib import SequenceMatcher

    first, second = tokens(a), tokens(b)
    if not first or not second:
        return 0.0
    hits = 0.0
    for word in first:
        best = max((SequenceMatcher(None, word, other).ratio() for other in second), default=0.0)
        hits += 1.0 if best >= 0.82 else 0.0
    return hits / len(first)


class Command(BaseCommand):
    help = "يستورد الأنصبة من جدول aSc المُصدَّر — بلا كتابةٍ إلّا بـ--apply"

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="ملفُّ الحصص (TSV) المستخرَج من الـPDF")
        parser.add_argument("--school", default="", help="رمزُ المدرسة")
        parser.add_argument("--year", default="", help="العامُ الدراسيّ")
        parser.add_argument(
            "--prune",
            action="store_true",
            help="احذف الإسنادات التي ليست في الملفّ — والافتراضُ إبقاؤها",
        )
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        school = self._school(options["school"])
        year = options["year"] or academic_year_for_school(school)
        lessons = self._read(options["file"])

        wanted, splits, groups = self._aggregate(lessons)
        teachers, missing_teachers = self._match_teachers(school, wanted)
        classes, missing_classes = self._match_classes(school, year, wanted)
        subjects, missing_subjects = self._match_subjects(school, wanted)

        self.stdout.write(f"المدرسة: {school.name} · العام: {year}")
        self.stdout.write(
            f"الملفّ: {len(lessons)} حصّة · {len(wanted)} إسناداً · "
            f"{len({k[0] for k in wanted})} معلّماً"
        )

        for label, rows in (
            ("معلّمون لم يُطابَقوا", missing_teachers),
            ("شُعبٌ لم تُطابَق", missing_classes),
            ("موادُّ لم تُطابَق", missing_subjects),
        ):
            if rows:
                self.stdout.write(self.style.WARNING(f"\n{label}: {len(rows)}"))
                for row in sorted(rows):
                    self.stdout.write(f"   {row}")

        if splits:
            self.stdout.write(
                self.style.WARNING(f"\nشُعبٌ مقسومةٌ بين معلّمَين للمادّة نفسها: {len(splits)}")
            )
            for (class_code, subject), names in sorted(splits.items()):
                self.stdout.write(f"   {class_code} · {subject} → {' + '.join(sorted(names))}")
            self.stdout.write("   لكلٍّ سجلُّه، ولهما وسمُ مجموعةٍ واحد — خانةٌ واحدةٌ ونصابان.")

        plan = self._plan(
            school, year, wanted, teachers, classes, subjects, groups, options["prune"]
        )
        self.stdout.write(
            f"\nجديد: {len(plan['create'])} · تعديل: {len(plan['update'])} · "
            f"بلا تغيير: {plan['same']} · للحذف: {len(plan['delete'])}"
        )
        for row in plan["create"][:80]:
            self.stdout.write(f"   + {row[0]} · {row[1]} · {row[2]} حصص → {row[3]}")
        for row in plan["update"][:80]:
            self.stdout.write(f"   ~ {row[0]} · {row[1]} · {row[2]} → {row[3]}")
        for row in plan["delete"][:80]:
            self.stdout.write(f"   - {row}")

        if not options["apply"]:
            self.stdout.write("\nتقريرٌ فقط — أضِف --apply للكتابة.")
            return

        written, removed = self._write(school, year, plan)
        self.stdout.write(f"\nكُتب {written} إسناداً، وحُذف {removed}.")

    # ── القراءة والمطابقة ────────────────────────────────────────────

    def _school(self, code):
        school = (School.objects.filter(code=code) if code else School.objects.all()).first()
        if school is None:
            raise CommandError("لا مدرسةَ بهذا الرمز.")
        return school

    def _read(self, path):
        try:
            with open(path, encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle, delimiter="\t"))
        except OSError as exc:
            raise CommandError(f"تعذّر فتحُ الملفّ: {path}") from exc
        if not rows or "teacher" not in rows[0]:
            raise CommandError("الملفُّ ليس بالشكل المتوقَّع (teacher/day/period/class/subject).")
        return rows

    def _aggregate(self, lessons):
        """(معلّم، شعبة، مادّة) → حصص، ومعها وسمُ المجموعة عند القسمة.

        الشعبةُ المقسومةُ نصفين يُدرَّسان معاً بمعلّمَين: لكلٍّ سجلُّه فيصحّ
        نصابُ الاثنين، ويحمل السجلّان **وسمَ مجموعةٍ واحداً** فيعرف المولّدُ
        أنّهما خانةٌ واحدةٌ لا خانتان.

        والقسمةُ تُعرَف من الخانة لا من المادّة: معلّمان في (شعبةٍ · يومٍ ·
        حصّة) واحدةٍ نصفان، اتّفقت مادّتاهما أو اختلفتا. وكانت تُعرَف بتساوي
        المادّة، فلمّا صُحِّحت أسماءُ الأنصاف بـ`SPLIT_SUBJECTS` اختلفت
        المادّتان فانفكّت القسمةُ وصارت الشعبةُ تشغل خانتين.
        """
        counts = Counter()
        cells = defaultdict(list)
        for row in lessons:
            teacher, class_code, subject = (
                row["teacher"].strip(),
                row["class"].strip(),
                row["subject"].strip(),
            )
            sole = SOLE_HOLDERS.get((class_code, normal(subject)))
            if sole and teacher != sole:
                continue  # تكرارُ تصديرٍ لا شراكةُ تدريس
            subject = SPLIT_SUBJECTS.get((class_code, teacher), subject)
            counts[(teacher, class_code, subject)] += 1
            cells[(class_code, row["day"], row["period"])].append((teacher, subject))

        splits, groups = {}, {}
        for (class_code, _, _), members in cells.items():
            if len(members) < 2:
                continue
            names = sorted({subject for _, subject in members})
            tag = f"{SPLIT_TAG}-{class_code}-{'+'.join(normal(n)[:9] for n in names)}"[:40]
            splits.setdefault((class_code, " / ".join(names)), set()).update(
                teacher for teacher, _ in members
            )
            for teacher, subject in members:
                groups[(teacher, class_code, subject)] = tag
        return counts, splits, groups

    def _match_teachers(self, school, wanted):
        people = {
            m.user
            for m in Membership.objects.filter(
                school=school, is_active=True, role__name__in=TEACHING_ROLES
            ).select_related("user")
        }
        by_name = {normal(p.full_name): p for p in people}
        found, missing = {}, []
        for name in sorted({k[0] for k in wanted}):
            alias = TEACHER_ALIASES.get(name)
            if alias and normal(alias) in by_name:
                found[name] = by_name[normal(alias)]
                continue
            scored = sorted(
                ((closeness(name, p.full_name), p) for p in people), key=lambda x: -x[0]
            )
            best, runner = scored[0], (scored[1] if len(scored) > 1 else (0.0, None))
            if best[0] >= 0.99 and best[0] > runner[0]:
                found[name] = best[1]
            elif best[0] >= 0.99:
                # تعادلٌ بين اسمين — يُفصل بأطولهما اشتراكاً في الكلمات.
                tie = [p for score, p in scored if score >= 0.99]
                tie.sort(key=lambda p: -len(tokens(name) & tokens(p.full_name)))
                if len(tie) == 1 or len(tokens(name) & tokens(tie[0].full_name)) > len(
                    tokens(name) & tokens(tie[1].full_name)
                ):
                    found[name] = tie[0]
                else:
                    missing.append(
                        f"{name} — التبس على {len(tie)}: " + "، ".join(p.full_name for p in tie[:3])
                    )
            else:
                near = "، ".join(f"{p.full_name} ({score:.0%})" for score, p in scored[:2])
                missing.append(f"{name} — لا مطابق. الأقربُ: {near}")
        return found, missing

    def _match_classes(self, school, year, wanted):
        groups = {
            (g.grade, g.section): g
            for g in ClassGroup.objects.filter(school=school, academic_year=year, is_active=True)
        }
        found, missing = {}, []
        for code in sorted({k[1] for k in wanted}):
            grade, _, section = code.partition(".")
            key = (GRADES.get(grade, ""), section)
            if key in groups:
                found[code] = groups[key]
            else:
                missing.append(code)
        return found, missing

    def _match_subjects(self, school, wanted):
        catalogue = {normal(s.name_ar): s for s in Subject.objects.filter(school=school)}
        found, missing = {}, []
        for name in sorted({k[2] for k in wanted}):
            key = normal(name)
            key = normal(SUBJECT_ALIASES.get(key, key))
            hit = catalogue.get(key)
            if hit is None:
                hit = next((s for k, s in catalogue.items() if key in k or k in key), None)
            if hit is not None:
                found[name] = hit
            else:
                missing.append(name)
        return found, missing

    def _plan(self, school, year, wanted, teachers, classes, subjects, groups, prune):
        current = {
            (a.class_group_id, a.subject_id, a.teacher_id): a
            for a in SubjectClassAssignment.objects.live(school, year=year).select_related(
                "class_group", "subject", "teacher"
            )
        }
        create, update, same, seen = [], [], 0, set()
        for (teacher_name, class_code, subject_name), periods in sorted(wanted.items()):
            teacher = teachers.get(teacher_name)
            group = classes.get(class_code)
            subject = subjects.get(subject_name)
            if not (teacher and group and subject):
                continue
            tag = groups.get((teacher_name, class_code, subject_name), "")
            key = (group.id, subject.id, teacher.id)
            seen.add(key)
            row = current.get(key)
            label = f"{subject.name_ar}{' · نصفُ شعبة' if tag else ''}"
            if row is None:
                create.append((str(group), label, periods, teacher.full_name, key))
            elif (
                row.teacher_id != teacher.id
                or row.weekly_periods != periods
                or (row.parallel_group or "") != tag
            ):
                update.append(
                    (
                        str(group),
                        label,
                        f"{row.teacher.full_name if row.teacher else '—'} {row.weekly_periods}ح"
                        + (f" [{row.parallel_group}]" if row.parallel_group else ""),
                        f"{teacher.full_name} {periods}ح" + (" [نصفُ شعبة]" if tag else ""),
                        key,
                    )
                )
            else:
                same += 1

        delete = []
        if prune:
            for key, row in current.items():
                if key not in seen:
                    delete.append(f"{row.class_group} · {row.subject.name_ar} · {row.teacher}")
        return {
            "create": create,
            "update": update,
            "same": same,
            "delete": delete,
            "wanted": wanted,
            "teachers": teachers,
            "classes": classes,
            "subjects": subjects,
            "seen": seen,
            "groups": groups,
            "current": current,
            "prune": prune,
        }

    # ── الكتابة ──────────────────────────────────────────────────────

    @transaction.atomic
    def _write(self, school, year, plan):
        actor = CustomUser.objects.filter(is_superuser=True).first()
        written = 0
        seen = set()
        for (teacher_name, class_code, subject_name), periods in sorted(plan["wanted"].items()):
            teacher = plan["teachers"].get(teacher_name)
            group = plan["classes"].get(class_code)
            subject = plan["subjects"].get(subject_name)
            if not (teacher and group and subject):
                continue
            tag = plan["groups"].get((teacher_name, class_code, subject_name), "")
            key = (group.id, subject.id, teacher.id)
            seen.add(key)
            svc.apply_assignment(
                school=school,
                academic_year=year,
                class_group=group,
                subject=subject,
                teacher=teacher,
                weekly_periods=periods,
                by=actor,
                parallel_group=tag,
                override_reason="من جدول المدرسة المعتمَد (aSc)",
                confirm_transfer=True,
            )
            written += 1

        removed = 0
        if plan["prune"]:
            for key, row in plan["current"].items():
                if key not in seen:
                    svc.remove_assignment(
                        assignment=row, by=actor, reason="ليس في جدول المدرسة المعتمَد"
                    )
                    removed += 1
        return written, removed

"""خدمةُ استيراد مواضع حصص جدول aSc — يناديها الأمرُ `import_schedule_from_asc_pdf` وصفحةُ الرفع.

    Position ≠ Assignment      الموضعُ من الـPDF، والإسنادُ من المنصّة

منطقُ التحليل والكتابة هنا مرّةً واحدة: `analyze` تقرأ الملفّين وتبني التقرير بلا كتابة،
و`write_draft` تكتب مسودّةً `ScheduleGeneration` حصصُها `is_active=False` — لا اعتمادَ ولا تفعيل.
المصدرُ مسارٌ أو كائنٌ في الذاكرة (بايتاتُ الصفحة لا تلمس القرص).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import IO, Any, NamedTuple

from django.db import transaction

from academic_management import asc_pdf
from academic_management.management.commands.import_assignments_from_timetable import (
    Command as TimetableImport,
)
from academic_management.management.commands.import_assignments_from_timetable import (
    NameRules,
    closeness,
)
from operations.models import ScheduleGeneration, ScheduleSlot, SubjectClassAssignment
from operations.scheduler_persist import distinct_labels
from operations.scheduling_inputs import bell_lookup

Pair = tuple[str, str]  # (اسمُ المعلّم، رمزُ الشعبة)
Source = str | IO[bytes]


class AscImportRefusedError(Exception):
    """رفضٌ بشرطٍ من شروط الكتابة؛ `option` هو الخيارُ الذي رُفض (`--apply` أو `--replace`)."""

    def __init__(self, reason: str, option: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.option = option


class Item(NamedTuple):
    """بندُ تقرير. وأزواجُه (معلّم، شعبة) تُحدّد هل تُعفيه قائمةُ التجاهل."""

    text: str
    pairs: tuple[Pair, ...] = ()


class Lesson(NamedTuple):
    teacher: str
    class_code: str
    subject: str
    day: int
    period: int


class Analysis(NamedTuple):
    """ناتجُ القراءة: التقريرُ، وما تحتاجه الكتابةُ لو لم يبقَ بندٌ مانع."""

    lessons: int
    class_slots: int
    items: list[Item]
    blocking: list[Item]
    placed: list[Lesson]
    labels: list[str]
    assignments: dict[tuple[str, str, str], SubjectClassAssignment]


def _code(group: Any) -> str:
    """رمزُ الشعبة بنمط الجدول: «7.1» من (G7، 1)."""
    return f"{str(group.grade)[1:]}.{group.section}"


def _read_lessons(source: Source, title_words: tuple[str, ...]) -> tuple[list[Lesson], list[Item]]:
    pages, errors = asc_pdf.parse_pdf(source, lambda p: asc_pdf.parse_teacher_page(p, title_words))
    lessons = [
        Lesson(page.name, code, subject, day, period)
        for page in pages
        for day, period, code, subject in page.lessons
    ]
    return lessons, [Item(f"ملفُّ المعلّمين — {e}") for e in errors]


def _name_unlabeled(
    pages: list[asc_pdf.ClassPage], lessons: list[Lesson]
) -> tuple[list[asc_pdf.ClassPage], list[Item]]:
    """صفحةٌ بلا رمزٍ تُنسب إلى الشعبة الوحيدة في ملفّ المعلّمين التي تطابق خاناتها ولم تُنسب إليها صفحة."""
    by_code: dict[str, set[tuple[int, int]]] = defaultdict(set)
    for x in lessons:
        by_code[x.class_code].add((x.day, x.period))
    taken = {p.class_code for p in pages if p.class_code}
    unlabeled = [p for p in pages if not p.class_code]
    guess = {
        id(p): [c for c, s in by_code.items() if c not in taken and s == p.slots] for p in unlabeled
    }
    votes = Counter(c for found in guess.values() for c in found)
    named = [p for p in pages if p.class_code]
    items = []
    for page in unlabeled:
        found = guess[id(page)]
        if len(found) == 1 and votes[found[0]] == 1:
            named.append(page._replace(class_code=found[0]))
        else:
            items.append(
                Item(f"ملفُّ الشعب — صفحةٌ بلا رمزِ شعبةٍ ولا مطابقةٍ وحيدة لخاناتها: {page.title}")
            )
    return named, items


def _read_class_slots(
    source: Source, lessons: list[Lesson]
) -> tuple[set[tuple[str, int, int]], list[Item]]:
    pages, errors = asc_pdf.parse_pdf(source, asc_pdf.parse_class_page)
    items = [Item(f"ملفُّ الشعب — {e}") for e in errors]
    pages, unnamed = _name_unlabeled(pages, lessons)
    slots = {(page.class_code, d, p) for page in pages for d, p in page.slots}
    if not slots:
        # بندٌ واحد: سببُ الصفحات غير المنسوبة إن وُجد، وإلا أنّ الملفّ فارغ
        return slots, items + (unnamed[:1] or [Item("ملفُّ الشعب — لم تُقرأ منه أيُّ خانة")])
    return slots, items + unnamed


def _cross_check(lessons: list[Lesson], class_slots: set[tuple[str, int, int]]) -> list[Item]:
    """ملفُّ الشعب يدقّق ملفَّ المعلّمين: المجموعتان متساويتان أو تعارضٌ لكلّ فرق."""
    teacher_slots = {(x.class_code, x.day, x.period) for x in lessons}
    items = []
    for label, rows in (
        ("في ملفّ المعلّمين ولا في ملفّ الشعب", teacher_slots - class_slots),
        ("في ملفّ الشعب ولا في ملفّ المعلّمين", class_slots - teacher_slots),
    ):
        items.extend(
            Item(f"تعارض: {label}: {c} · يوم {d + 1} · حصّة {p}") for c, d, p in sorted(rows)
        )
    return items


def _teacher_clashes(lessons: list[Lesson]) -> list[Item]:
    """معلّمٌ واحدٌ في شعبتين في الخانة نفسها."""
    seen: dict[tuple[str, int, int], set[str]] = defaultdict(set)
    for x in lessons:
        seen[(x.teacher, x.day, x.period)].add(x.class_code)
    return [
        Item(
            f"تعارض: {t} في شعبتين معاً ({'، '.join(sorted(cs))}) · يوم {d + 1} · حصّة {p}",
            tuple((t, c) for c in sorted(cs)),
        )
        for (t, d, p), cs in sorted(seen.items())
        if len(cs) > 1
    ]


class _Linked(NamedTuple):
    #: (معلّم aSc، شعبة، مادّة) → الإسناد المعتمَد
    assignments: dict[tuple[str, str, str], SubjectClassAssignment]
    items: list[Item]


def _link(school: Any, year: str, lessons: list[Lesson], legacy: TimetableImport) -> _Linked:
    """ربطُ (معلّم، شعبة، مادّة) بإسنادٍ معتمَد — بالمادّة أوّلاً، ثمّ بالإسناد الوحيد للمعلّم في الشعبة."""
    wanted = Counter((x.teacher, x.class_code, x.subject) for x in lessons)
    teachers, missing_teachers = legacy._match_teachers(school, wanted)
    classes, missing_classes = legacy._match_classes(school, year, wanted)
    subjects, _ = legacy._match_subjects(school, wanted)

    by_pair: dict[tuple[Any, Any], list[SubjectClassAssignment]] = defaultdict(list)
    for a in SubjectClassAssignment.objects.live(school, year=year).select_related(
        "subject", "teacher", "class_group"
    ):
        by_pair[(a.teacher_id, a.class_group_id)].append(a)

    items = [
        Item(f"معلّمٌ لم يُطابَق: {row}", tuple((n, c) for n, c, _ in wanted if row.startswith(n)))
        for row in missing_teachers
    ]
    items += [
        Item(f"شعبةٌ لم تُطابَق: {code}", tuple((n, c) for n, c, _ in wanted if c == code))
        for code in missing_classes
    ]
    found: dict[tuple[str, str, str], SubjectClassAssignment] = {}
    for key in sorted(wanted):
        name, code, subject = key
        teacher, group = teachers.get(name), classes.get(code)
        if teacher is None or group is None:
            continue
        options = by_pair.get((teacher.id, group.id), [])
        hit = subjects.get(subject)
        exact = [a for a in options if hit is not None and a.subject_id == hit.id]
        pick = exact[0] if exact else (options[0] if len(options) == 1 else None)
        if pick is None:
            items.append(
                Item(f"إسنادٌ غيرُ موجودٍ أو ملتبس: {name} · {code} · {subject}", ((name, code),))
            )
        else:
            found[key] = pick
    return _Linked(found, items)


def _parallel_tags(
    lessons: list[Lesson], linked: dict[tuple[str, str, str], SubjectClassAssignment]
) -> tuple[dict[tuple[str, int, int], str], list[Item]]:
    """خانةٌ بمعلّمَين تُقبل إن حمل إسناداهما `parallel_group` نفسَه — وهو ما يُكتب في `elective_group`."""
    cells: dict[tuple[str, int, int], list[Lesson]] = defaultdict(list)
    for x in lessons:
        cells[(x.class_code, x.day, x.period)].append(x)
    tags: dict[tuple[str, int, int], str] = {}
    items = []
    for cell, members in sorted(cells.items()):
        if len({m.teacher for m in members} - {""}) < 2:
            continue
        rows = [linked.get((m.teacher, m.class_code, m.subject)) for m in members]
        groups = {(a.parallel_group or "").strip() if a else None for a in rows}
        if len(groups) == 1 and None not in groups and "" not in groups:
            tags[cell] = groups.pop() or ""
        elif None not in groups:
            who = "، ".join(sorted({m.teacher for m in members}))
            items.append(
                Item(
                    f"تعارض: معلّمان في خانةٍ واحدةٍ بلا وسمِ توازٍ مشترك: {cell[0]} · يوم {cell[1] + 1} · حصّة {cell[2]} ({who})",
                    tuple((m.teacher, m.class_code) for m in members),
                )
            )
    return tags, items


def _cell_labels(
    placed: list[Lesson],
    linked: dict[tuple[str, str, str], SubjectClassAssignment],
    tags: dict[tuple[str, int, int], str],
) -> list[str]:
    """`elective_group` لكلّ حصّةٍ مكتوبة: فارغٌ لغير المشتركة، ومميَّزٌ لكلّ طرفٍ في المشتركة.

    القيدُ `no_class_period_overlap` يشمل `elective_group`، فوسمُ التوازي المشتركُ نفسُه
    يُسقط الاعتماد؛ والقاعدةُ هي قاعدةُ المولِّد (`distinct_labels`) بترتيبٍ ثابتٍ للأطراف.
    """
    members: dict[tuple[str, int, int], list[int]] = defaultdict(list)
    for index, x in enumerate(placed):
        cell = (x.class_code, x.day, x.period)
        if cell in tags:
            members[cell].append(index)
    labels = [""] * len(placed)
    for indexes in members.values():
        indexes.sort(key=lambda i: (placed[i].teacher, placed[i].subject, i))
        names = [
            linked[(placed[i].teacher, placed[i].class_code, placed[i].subject)] for i in indexes
        ]
        for i, label in zip(
            indexes, distinct_labels([a.subject.name_ar for a in names]), strict=True
        ):
            labels[i] = label
    return labels


def _constraint_items(
    placed: list[Lesson],
    linked: dict[tuple[str, str, str], SubjectClassAssignment],
    labels: list[str],
) -> list[Item]:
    """حصصُ المسودّة لو فُعّلت: هل تخالف `no_teacher_period_overlap` أو `no_class_period_overlap`؟"""
    teacher_rows: Counter[tuple[int | None, int, int]] = Counter()
    class_rows: Counter[tuple[int, int, int, str]] = Counter()
    for x, label in zip(placed, labels, strict=True):
        a = linked[(x.teacher, x.class_code, x.subject)]
        teacher_rows[(a.teacher_id, x.day, x.period)] += 1
        class_rows[(a.class_group_id, x.day, x.period, label)] += 1
    items = [
        Item(
            f"قيد: معلّمٌ بحصّتين مفعَّلتين معاً (no_teacher_period_overlap): معلّم {t} · يوم {d + 1} · حصّة {p}"
        )
        for (t, d, p), n in sorted(teacher_rows.items(), key=str)
        if n > 1 and t is not None
    ]
    items += [
        Item(
            f"قيد: حصّتان لشعبةٍ بوسمٍ واحد (no_class_period_overlap): شعبة {g} · يوم {d + 1} · حصّة {p}"
        )
        for (g, d, p, _), n in sorted(class_rows.items(), key=str)
        if n > 1
    ]
    return items


def _count_items(
    school: Any,
    year: str,
    lessons: list[Lesson],
    linked: dict[tuple[str, str, str], SubjectClassAssignment],
) -> list[Item]:
    """كلُّ إسنادٍ معتمَدٍ عددُ خاناته المستوردةِ لا يساوي `weekly_periods`."""
    counts: Counter[Any] = Counter()
    for x in lessons:
        pick = linked.get((x.teacher, x.class_code, x.subject))
        if pick is not None:
            counts[pick.id] += 1
    items = []
    for a in SubjectClassAssignment.objects.live(school, year=year).select_related(
        "subject", "teacher", "class_group"
    ):
        if counts[a.id] != a.weekly_periods:
            who = a.teacher.full_name if a.teacher else "—"
            code = _code(a.class_group)
            items.append(
                Item(
                    f"عددٌ مخالف: {who} · {code} · {a.subject.name_ar}: استُورد {counts[a.id]} والإسناد {a.weekly_periods}",
                    ((who, code),),
                )
            )
    return items


def _ignored(item: Item, ignore: frozenset[Pair]) -> bool:
    """يُعفى البندُ إن كان كلُّ أزواجه في قائمة التجاهل — الاسمُ بالتضمّن (اسمُ aSc مختصرٌ، واسمُ المنصّة كامل)."""
    return bool(item.pairs) and all(
        any(c == code and closeness(name, n) >= 0.99 for name, code in ignore)
        for n, c in item.pairs
    )


def analyze(
    school: Any, year: str, teachers: Source, classes: Source, rules: NameRules
) -> Analysis:
    """يقرأ الملفّين ويبني التقرير — لا يكتب شيئاً."""
    legacy = TimetableImport()
    lessons, items = _read_lessons(teachers, rules.asc_title_words)
    class_slots, class_errors = _read_class_slots(classes, lessons)
    linked = _link(school, year, lessons, legacy)
    tags, tag_items = _parallel_tags(lessons, linked.assignments)
    # بلا خانةٍ واحدة من ملفّ الشعب يكفي بندُ القراءة، لا بندٌ زائفٌ لكلّ خانة
    crossed = _cross_check(lessons, class_slots) if class_slots else []
    items += class_errors + crossed + _teacher_clashes(lessons)
    items += linked.items + tag_items + _count_items(school, year, lessons, linked.assignments)
    # ما عُفي بندُه من الإسنادات غيرِ المربوطة لا يُكتب له موضع.
    placed = [x for x in lessons if (x.teacher, x.class_code, x.subject) in linked.assignments]
    labels = _cell_labels(placed, linked.assignments, tags)
    items += _constraint_items(placed, linked.assignments, labels)
    blocking = [i for i in items if not _ignored(i, rules.asc_ignore)]
    return Analysis(
        len(lessons), len(class_slots), items, blocking, placed, labels, linked.assignments
    )


def write_draft(
    school: Any,
    year: str,
    analysis: Analysis,
    sha_teachers: str,
    sha_classes: str,
    replace: bool,
) -> int:
    """يكتب المسودّةَ بشرط `--apply`: يُرفض إن بقي بندٌ مانع. يُرجع عددَ الحصص المكتوبة (0 = موجودةٌ مسبقاً)."""
    if analysis.blocking:
        raise AscImportRefusedError(f"بقي {len(analysis.blocking)} بند في التقرير.", "--apply")
    snapshot = {"mode": "import", "sha256_teachers": sha_teachers, "sha256_classes": sha_classes}
    return _write(
        school,
        year,
        analysis.placed,
        analysis.labels,
        analysis.assignments,
        snapshot,
        replace,
    )


@transaction.atomic
def _write(
    school: Any,
    year: str,
    placed: list[Lesson],
    labels: list[str],
    linked: dict[tuple[str, str, str], SubjectClassAssignment],
    snapshot: dict[str, str],
    replace: bool,
) -> int:
    """مسودّةٌ واحدةٌ بحصصها غيرِ المفعَّلة؛ ومن أعاد التشغيلَ بالملفّين نفسيهما لا يزيد شيئاً.

    و`--replace` يستبدل المسودّةَ القائمةَ إن كانت draft وحصصُها كلُّها غيرُ مفعَّلة، في المعاملة نفسها.
    """
    same = ScheduleGeneration.objects.filter(
        school=school,
        academic_year=year,
        config_snapshot__mode="import",
        config_snapshot__sha256_teachers=snapshot["sha256_teachers"],
        config_snapshot__sha256_classes=snapshot["sha256_classes"],
    )
    if same.exists():
        if not replace:
            return 0
        old = list(same)
        stale = [
            g
            for g in old
            if g.status != "draft"
            or ScheduleSlot.objects.filter(generation=g, is_active=True).exists()
        ]
        if stale:
            raise AscImportRefusedError("المسودّةُ القائمة معتمَدةٌ أو فيها حصّةٌ مفعَّلة.", "--replace")
        ScheduleSlot.objects.filter(generation__in=old).delete()
        ScheduleGeneration.objects.filter(id__in=[g.id for g in old]).delete()
    generation = ScheduleGeneration.objects.create(
        school=school,
        academic_year=year,
        status="draft",
        config_snapshot=snapshot,
        total_slots_created=len(placed),
    )
    times = bell_lookup(school)
    slots = []
    for x, label in zip(placed, labels, strict=True):
        a = linked[(x.teacher, x.class_code, x.subject)]
        start, end = times(x.day, x.period, a.class_group.time_band_id)
        slots.append(
            ScheduleSlot(
                school=school,
                teacher_id=a.teacher_id,
                class_group_id=a.class_group_id,
                subject_id=a.subject_id,
                day_of_week=x.day,
                period_number=x.period,
                start_time=start,
                end_time=end,
                academic_year=year,
                elective_group=label,
                is_active=False,
                generation=generation,
            )
        )
    ScheduleSlot.objects.bulk_create(slots)
    return len(slots)

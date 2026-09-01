"""
قياسُ الجدول القائم — قراءةً محضة، ولا استنتاجَ سياسةٍ من الكود.

الجدولُ المستورد (٨٧٠ حصّة) هو أصدقُ ما نملك عن قواعد المدرسة الفعليّة: هو
مخرجُ قراراتٍ إداريّةٍ اتُّخذت، لا فرضيّاتٌ عنها. وهذا الملفُّ يستخرج منه
الأرقام، **ولا يُحوّلها إلى قواعد**.

والتمييزُ الذي تقوم عليه الوحدة كلُّها:

    FACT              رقمٌ مقيسٌ من الجدول — لا يُنازَع.
    OBSERVED PATTERN  انتظامٌ يُرى في المقيس — قد يكون قراراً وقد يكون صدفة.
    CANDIDATE POLICY  قاعدةٌ **مقترحة** تُشتقّ من النمط — لا تسري حتى تُعتمد.

فلو وجدنا أنّ أحداً لا يتجاوز خمسَ حصصٍ في اليوم، فهذا نمطٌ مرصود؛ وقد يكون
قرارَ إدارةٍ وقد يكون أثراً عرضيّاً لجدولٍ بُني هكذا. وأن نكتب
`MAX_TEACHER_DAILY = 5` من هذا وحده اختراعُ سياسةٍ باسم المدرسة.

ولا يكتب هذا الملفُّ شيئاً في القاعدة.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from statistics import median

#: أيّامُ الأسبوع الدراسيّ القطريّ.
DAY_NAMES = {0: "الأحد", 1: "الاثنين", 2: "الثلاثاء", 3: "الأربعاء", 4: "الخميس"}

#: حصّةٌ «متأخّرة» — تُعرَّف هنا للقياس لا للحكم.
LATE_PERIOD = 6


@dataclass(frozen=True)
class Lesson:
    """حصّةٌ واحدةٌ مجرّدةٌ من النموذج — كي يُقاس بلا قاعدة بيانات."""

    teacher_id: str
    teacher_name: str
    class_id: str
    class_name: str
    subject_id: str
    subject_name: str
    day: int
    period: int
    level_type: str = ""
    grade: str = ""
    elective_group: str = ""
    subject_code: str = ""
    class_label: str = ""  # «10/1» — مختصرٌ صالحٌ للجداول


def _class_label(class_group):
    """«الصف العاشر / 2 — علمي» ← «10/2»: الجداولُ لا تتّسع للاسم الكامل.

    والاسمُ المبتورُ أسوأ من المختصر: «الصف الثا» لا يميّز الثامنَ من الثاني
    عشر، فيصير التقريرُ غيرَ قابلٍ للقراءة أصلاً.
    """
    grade = (class_group.grade or "").removeprefix("G")
    section = class_group.section or ""
    return f"{grade}/{section}" if grade and section else str(class_group)


def load_lessons(school, academic_year):
    """يقرأ الحصص النشطة — ولا يكتب."""
    from operations.models import ScheduleSlot

    rows = (
        ScheduleSlot.objects.filter(school=school, academic_year=academic_year, is_active=True)
        .select_related("teacher", "class_group", "subject")
        .order_by("day_of_week", "period_number")
    )
    return [
        Lesson(
            teacher_id=str(r.teacher_id),
            teacher_name=r.teacher.full_name if r.teacher else "—",
            class_id=str(r.class_group_id),
            class_name=str(r.class_group),
            subject_id=str(r.subject_id) if r.subject_id else "",
            subject_name=r.subject.name_ar if r.subject else "—",
            subject_code=(r.subject.code or "") if r.subject else "",
            class_label=_class_label(r.class_group),
            day=r.day_of_week,
            period=r.period_number,
            level_type=r.class_group.level_type or "",
            grade=r.class_group.grade or "",
            elective_group=getattr(r, "elective_group", "") or "",
        )
        for r in rows
    ]


# ── أدواتٌ صغيرة ─────────────────────────────────────────────────────


def _runs(periods):
    """أطولُ سلسلةِ حصصٍ متتابعة في يوم."""
    if not periods:
        return 0
    ordered = sorted(periods)
    longest = run = 1
    for previous, current in zip(ordered, ordered[1:], strict=False):
        run = run + 1 if current == previous + 1 else 1
        longest = max(longest, run)
    return longest


def _gaps(periods):
    """الفراغاتُ بين أوّل حصّةٍ وآخرها في اليوم."""
    if len(periods) < 2:
        return 0
    ordered = sorted(periods)
    return (ordered[-1] - ordered[0] + 1) - len(ordered)


def _spread(values):
    """أدنى ووسيطٌ وأعلى — الوسيطُ لا المتوسّط، فحالةٌ شاذّةٌ لا تُشوّهه."""
    if not values:
        return {"min": 0, "median": 0, "max": 0}
    return {"min": min(values), "median": median(values), "max": max(values)}


# ── عبءُ المعلّمين ───────────────────────────────────────────────────


@dataclass
class TeacherProfile:
    teacher_id: str
    name: str
    weekly: int = 0
    days_used: int = 0
    max_daily: int = 0
    min_daily: int = 0
    first_period: int = 0
    late_periods: int = 0
    gaps: int = 0
    longest_run: int = 0
    per_day: dict = field(default_factory=dict)


def profile_teachers(lessons):
    by_teacher = defaultdict(lambda: defaultdict(list))
    names = {}
    for lesson in lessons:
        by_teacher[lesson.teacher_id][lesson.day].append(lesson.period)
        names[lesson.teacher_id] = lesson.teacher_name

    profiles = []
    for teacher_id, days in by_teacher.items():
        daily = {day: sorted(periods) for day, periods in days.items()}
        counts = [len(p) for p in daily.values()]
        profiles.append(
            TeacherProfile(
                teacher_id=teacher_id,
                name=names[teacher_id],
                weekly=sum(counts),
                days_used=len(daily),
                max_daily=max(counts),
                min_daily=min(counts),
                first_period=sum(1 for p in daily.values() if 1 in p),
                late_periods=sum(1 for p in daily.values() for x in p if x >= LATE_PERIOD),
                gaps=sum(_gaps(p) for p in daily.values()),
                longest_run=max(_runs(p) for p in daily.values()),
                per_day=daily,
            )
        )
    return sorted(profiles, key=lambda p: (-p.weekly, p.name))


# ── عبءُ الشُّعب ─────────────────────────────────────────────────────


@dataclass
class SectionProfile:
    """ملفُّ شعبةٍ واحدة.

    و`weekly` عددُ **الحصص** لا الخانات، وبينهما فرقٌ حقيقيّ: أربعُ شعبٍ
    ينقسم طلابُها في الخانة الواحدة بين مادّتين (التكنولوجيا مقابل الفنون،
    والكيمياء مقابل الفنون). فتحمل الخانةُ حصّتين، ويظهر اليومُ ثمانيَ حصصٍ
    في سبع خانات. و`split_periods` يعدّ ذلك صراحةً كي لا يُقرأ تجاوزاً للسقف.
    """

    class_id: str
    name: str
    level_type: str
    weekly: int = 0
    per_day: dict = field(default_factory=dict)
    periods_per_day: dict = field(default_factory=dict)
    split_periods: int = 0
    subjects: dict = field(default_factory=dict)
    twice_in_a_day: int = 0
    adjacent_pairs: int = 0


def profile_sections(lessons):
    by_class = defaultdict(list)
    for lesson in lessons:
        by_class[lesson.class_id].append(lesson)

    profiles = []
    for class_id, items in by_class.items():
        per_day = defaultdict(list)
        for lesson in items:
            per_day[lesson.day].append(lesson.period)

        subject_day = Counter((x.subject_name, x.day) for x in items)
        adjacent = 0
        for (subject, day), count in subject_day.items():
            if count < 2:
                continue
            periods = sorted(x.period for x in items if x.subject_name == subject and x.day == day)
            adjacent += sum(1 for a, b in zip(periods, periods[1:], strict=False) if b == a + 1)

        slot_counts = Counter((x.day, x.period) for x in items)
        profiles.append(
            SectionProfile(
                class_id=class_id,
                name=items[0].class_name,
                level_type=items[0].level_type,
                weekly=len(items),
                per_day={d: len(p) for d, p in sorted(per_day.items())},
                periods_per_day={d: len(set(p)) for d, p in sorted(per_day.items())},
                split_periods=sum(1 for count in slot_counts.values() if count > 1),
                subjects=dict(Counter(x.subject_name for x in items).most_common()),
                twice_in_a_day=sum(1 for count in subject_day.values() if count >= 2),
                adjacent_pairs=adjacent,
            )
        )
    return sorted(profiles, key=lambda p: p.name)


# ── توزيعُ المواد ────────────────────────────────────────────────────


def profile_subjects(lessons):
    by_subject = defaultdict(list)
    for lesson in lessons:
        by_subject[lesson.subject_name].append(lesson)

    result = {}
    for name, items in by_subject.items():
        periods = [x.period for x in items]
        result[name] = {
            "total": len(items),
            "per_period": dict(sorted(Counter(periods).items())),
            "per_day": dict(sorted(Counter(x.day for x in items).items())),
            "in_last_period": sum(1 for p in periods if p == 7),
            "morning_share": round(sum(1 for p in periods if p <= 3) * 100 / len(periods), 1),
        }
    return dict(sorted(result.items(), key=lambda kv: -kv[1]["total"]))


# ── التوافر: متى لا يُدرّس معلّم ─────────────────────────────────────


def profile_availability(lessons):
    """الأيّامُ والخاناتُ التي لا يظهر فيها المعلّم أبداً.

    ولا يُسمّى هذا «إعفاءً»: قد يكون قراراً رسميّاً وقد يكون أثرَ الجدول.
    """
    by_teacher = defaultdict(set)
    names = {}
    for lesson in lessons:
        by_teacher[lesson.teacher_id].add((lesson.day, lesson.period))
        names[lesson.teacher_id] = lesson.teacher_name

    free_days = {}
    for teacher_id, slots in by_teacher.items():
        used_days = {day for day, _ in slots}
        empty = [DAY_NAMES[d] for d in sorted(set(DAY_NAMES) - used_days)]
        if empty:
            free_days[names[teacher_id]] = empty
    return free_days


# ── العدالة ──────────────────────────────────────────────────────────


def fairness(profiles):
    """توزيعُ الأعباء بين المعلّمين — لا متوسّطاً واحداً يُخفي الفروق."""
    return {
        "teachers": len(profiles),
        "weekly": _spread([p.weekly for p in profiles]),
        "max_daily": _spread([p.max_daily for p in profiles]),
        "gaps": _spread([p.gaps for p in profiles]),
        "first_period": _spread([p.first_period for p in profiles]),
        "late_periods": _spread([p.late_periods for p in profiles]),
        "days_used": _spread([p.days_used for p in profiles]),
        "longest_run": _spread([p.longest_run for p in profiles]),
    }


# ── الأنماطُ المرصودةُ والسياساتُ المرشَّحة ─────────────────────────


@dataclass(frozen=True)
class Observation:
    """رقمٌ مقيسٌ، ونمطٌ يُرى فيه، وقاعدةٌ **مقترحة** لا تسري حتى تُعتمد."""

    fact: str
    pattern: str
    candidate: str
    needs_approval: bool = True


def observations(lessons, teachers, sections, fair):
    """يُخرج ما يستحقّ قراراً — ولا يتّخذه."""
    found = []
    if not lessons:
        return found

    found.append(
        Observation(
            fact=f"أعلى عبءٍ يوميٍّ لمعلّمٍ في الجدول: {fair['max_daily']['max']} حصص.",
            pattern=f"لا معلّمَ يتجاوز {fair['max_daily']['max']} حصصٍ في يوم.",
            candidate=f"سقفٌ يوميٌّ للمعلّم = {fair['max_daily']['max']}.",
        )
    )
    found.append(
        Observation(
            fact=(
                f"النصابُ الأسبوعيّ: أدنى {fair['weekly']['min']} · "
                f"وسيط {fair['weekly']['median']} · أعلى {fair['weekly']['max']}."
            ),
            pattern=f"الفارقُ بين أثقل معلّمٍ وأخفّهم {fair['weekly']['max'] - fair['weekly']['min']} حصّة.",
            candidate="حدُّ تفاوتٍ مقبولٌ في النصاب الأسبوعيّ.",
        )
    )
    found.append(
        Observation(
            fact=(
                f"الفراغاتُ الأسبوعيّة: أدنى {fair['gaps']['min']} · "
                f"وسيط {fair['gaps']['median']} · أعلى {fair['gaps']['max']}."
            ),
            pattern="تفاوتُ الفراغات بين المعلّمين هو أظهرُ وجوه العدالة في الجدول.",
            candidate="سقفٌ للفراغات الأسبوعيّة للمعلّم الواحد.",
        )
    )

    longest = max(p.longest_run for p in teachers)
    found.append(
        Observation(
            fact=f"أطولُ سلسلةِ حصصٍ متتابعةٍ لمعلّم: {longest}.",
            pattern=f"لا سلسلةَ تتجاوز {longest} حصصٍ متتابعة.",
            candidate=f"حدُّ التتابع = {longest}.",
        )
    )

    # الخانةُ لا الحصّة: الشعبةُ المنقسمةُ تحمل حصّتين في خانةٍ واحدة.
    by_stage = defaultdict(set)
    for section in sections:
        for day, count in section.periods_per_day.items():
            by_stage[section.level_type or "غير محدّد"].add((day, count))
    thursday = {
        stage: max((count for day, count in pairs if day == 4), default=0)
        for stage, pairs in by_stage.items()
    }
    if thursday:
        found.append(
            Observation(
                fact="أقصى خاناتٍ يوم الخميس: "
                + " · ".join(f"{stage}={count}" for stage, count in sorted(thursday.items())),
                pattern="الخميسُ أقصرُ من سائر الأيّام، ويختلف باختلاف المرحلة.",
                candidate="سقفُ الخميس لكلّ مرحلةٍ على حدة.",
            )
        )

    split = sum(s.split_periods for s in sections)
    if split:
        found.append(
            Observation(
                fact=f"خاناتٌ تحمل أكثرَ من حصّة: {split} — في "
                + "، ".join(s.name.split(" (")[0] for s in sections if s.split_periods),
                pattern="شعبةٌ ينقسم طلابُها بين مادّتين في التوقيت نفسه — اختيارٌ لا تعارض.",
                candidate=(
                    "تمثيلُ الحصّة المنقسمة قيداً مستقلّاً: خانةٌ واحدة، مادّتان، "
                    "معلّمان، وقاعتان — ولا تُعدّ تجاوزاً للسقف."
                ),
            )
        )

    twice = sum(s.twice_in_a_day for s in sections)
    adjacent = sum(s.adjacent_pairs for s in sections)
    found.append(
        Observation(
            fact=f"تكرارُ المادّة في اليوم الواحد للشعبة: {twice} حالة، منها {adjacent} متجاورة.",
            pattern=(
                "التكرارُ قائمٌ فعلاً، وجزءٌ منه متجاورٌ — أي حصصٌ مزدوجةٌ مقصودة."
                if adjacent
                else "التكرارُ قائمٌ ولا تجاورَ فيه."
            ),
            candidate="تحديدُ أيّ المواد يجوز تكرارُها في اليوم، وأيّها يجب أن تتجاور.",
        )
    )
    return found

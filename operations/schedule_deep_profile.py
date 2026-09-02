"""
تشريحُ الجدول القائم — دراسةٌ لا ملخّص.

الجدولُ ثمانمئةٍ وسبعون ملاحظة، ومتوسّطاتُه تُخفي أكثرَ ممّا تُظهر. فـ«تسعٌ
وأربعون حالةَ تكرارٍ منها ثلاثٌ وعشرون متجاورة» رقمٌ لا يُجاب عنه سؤال: أيُّ
المواد؟ وفي أيّ صفّ؟ وأيُّ زوجٍ من الحصص؟ وهل هو قاعدةٌ أم عارض؟

وقاعدةُ هذه الوحدة كلِّها: **ما يُقاس يُسمّى بما هو، لا بما نظنّه.**

    ObservedLoad ≠ RequiredLoad

فمعلّمٌ بثلاث حصصٍ ليس مظلوماً ولا محظوظاً — قد يكون منسّقاً أو مكلَّفاً أو
مخفَّضَ النصاب. ولا تُقاس العدالةُ حتى يُعرف النصابُ المطلوب لكلّ واحد، وهو
ليس في الجدول. فما هنا `observed` وحده، ومقارنةُ النظراء تُضيّق المجال ولا
تُلغي القيد.

ولا تكتب هذه الوحدةُ شيئاً في القاعدة.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from statistics import mean, median

from operations.schedule_profile import DAY_NAMES  # noqa: F401  (يُعاد تصديرُه للأوامر)

#: الحصصُ الصباحيّةُ والمتأخّرة — حدودٌ للوصف لا للحكم.
MORNING = (1, 2, 3)
LATE = (6, 7)


def subject_ref(lesson):
    """هويّةُ المادّة: المعرّفُ أوّلاً، والكودُ والاسمُ للقراءة.

    و«تكنولوجيا المعلومات» و«التكنولوجيا» مادّتان مستقلّتان بكودين `IT`
    و`TECH`. ولو صُنّفتا بالاسم وحده لالتبستا في تقريرٍ تُبنى عليه سياسة.
    فالاسمُ عرضةٌ للتشابه، والمعرّفُ لا.
    """
    return (lesson.subject_id, lesson.subject_code, lesson.subject_name)


def subject_label(code, name):
    return f"{name} [{code or '—'}]"


# ══════════════════════════════════════════════════════════════════════
#  ١. مصفوفةُ التجاور — ما معنى «تكرارُ المادّة في اليوم»؟
# ══════════════════════════════════════════════════════════════════════


@dataclass
class AdjacencyRow:
    """تشريحُ تكرار مادّةٍ في اليوم الواحد لشعبةٍ واحدة."""

    subject: str  # الاسمُ للقراءة
    subject_id: str = ""
    subject_code: str = ""
    daily_doubles: int = 0  # مرّاتُ ظهورها مرّتين فأكثر في يومٍ لشعبة
    adjacent: int = 0  # منها ما كان متلاصقاً
    apart: int = 0  # منها ما كان متباعداً
    pairs: dict = field(default_factory=dict)  # «٢-٣» ← كم مرّة
    run_lengths: dict = field(default_factory=dict)  # طولُ السلسلة ← كم مرّة
    by_grade: dict = field(default_factory=dict)
    by_section: dict = field(default_factory=dict)
    by_teacher: dict = field(default_factory=dict)
    by_day: dict = field(default_factory=dict)

    @property
    def adjacency_rate(self):
        """نسبةُ التلاصق من مرّات التكرار — صفرٌ إن لم تتكرّر أصلاً."""
        return round(self.adjacent * 100 / self.daily_doubles, 1) if self.daily_doubles else 0.0

    @property
    def commonest_pair(self):
        return max(self.pairs, key=self.pairs.get) if self.pairs else "—"

    @property
    def label(self):
        return subject_label(self.subject_code, self.subject)


def _runs_of(periods):
    """سلاسلُ الأرقام المتّصلة — [1,2,4] ← [[1,2],[4]]."""
    ordered = sorted(set(periods))
    if not ordered:
        return []
    runs, current = [], [ordered[0]]
    for value in ordered[1:]:
        if value == current[-1] + 1:
            current.append(value)
        else:
            runs.append(current)
            current = [value]
    runs.append(current)
    return runs


def subject_adjacency(lessons):
    """لكلّ مادّة: كم مرّةً تكرّرت في يومٍ لشعبة، وكم منها كان متلاصقاً.

    والوحدةُ (شعبة × مادّة × يوم): هي ما يعيشه الطالب فعلاً. ولو عددنا على
    مستوى المادّة وحدها لاختلط صفٌّ بصفّ ومعلّمٌ بمعلّم.
    """
    grouped = defaultdict(list)
    for lesson in lessons:
        grouped[(lesson.class_id, subject_ref(lesson), lesson.day)].append(lesson)

    rows = {}
    for (_class_id, ref, day), items in grouped.items():
        periods = sorted({x.period for x in items})
        if len(periods) < 2:
            continue

        subject_id, code, name = ref
        row = rows.setdefault(
            subject_id,
            AdjacencyRow(subject=name, subject_id=subject_id, subject_code=code),
        )
        row.daily_doubles += 1

        runs = _runs_of(periods)
        touching = [run for run in runs if len(run) >= 2]
        if touching:
            row.adjacent += 1
        else:
            row.apart += 1

        for run in runs:
            row.run_lengths[len(run)] = row.run_lengths.get(len(run), 0) + 1
            for a, b in zip(run, run[1:], strict=False):
                label = f"{a}-{b}"
                row.pairs[label] = row.pairs.get(label, 0) + 1

        first = items[0]
        for bucket, key in (
            (row.by_grade, first.grade or "—"),
            (row.by_section, first.class_label or first.class_name),
            (row.by_teacher, first.teacher_name),
            (row.by_day, DAY_NAMES.get(day, str(day))),
        ):
            bucket[key] = bucket.get(key, 0) + 1

    return dict(sorted(rows.items(), key=lambda kv: -kv[1].daily_doubles))


# ══════════════════════════════════════════════════════════════════════
#  ٢. بصمةُ المادّة عبر الأسبوع (مادّة × صفّ)
# ══════════════════════════════════════════════════════════════════════


def subject_fingerprint(lessons):
    """لكلّ (مادّة، صفّ): انتشارُها على الأيّام والحصص ومسافةُ ما بينها."""
    grouped = defaultdict(list)
    for lesson in lessons:
        grouped[(lesson.subject_name, lesson.grade or "—")].append(lesson)

    result = {}
    for (subject, grade), items in grouped.items():
        sections = {x.class_id for x in items}
        per_day = Counter(x.day for x in items)
        per_period = Counter(x.period for x in items)
        total = len(items)

        distances = []
        by_class_day = defaultdict(list)
        for x in items:
            by_class_day[(x.class_id, x.day)].append(x.period)
        for periods in by_class_day.values():
            ordered = sorted(set(periods))
            distances += [b - a for a, b in zip(ordered, ordered[1:], strict=False)]

        result[f"{subject} · {grade}"] = {
            "total": total,
            "sections": len(sections),
            "per_day_avg": {
                DAY_NAMES[d]: round(per_day.get(d, 0) / len(sections), 1) for d in sorted(DAY_NAMES)
            },
            "per_period_pct": {
                p: round(per_period.get(p, 0) * 100 / total, 1) for p in range(1, 8)
            },
            "morning_pct": round(sum(per_period.get(p, 0) for p in MORNING) * 100 / total, 1),
            "late_pct": round(sum(per_period.get(p, 0) for p in LATE) * 100 / total, 1),
            "days_spread": len(per_day),
            "max_in_a_day": max(
                (len(set(v)) for v in by_class_day.values()),
                default=0,
            ),
            "mean_gap_between": round(mean(distances), 2) if distances else 0,
        }
    return dict(sorted(result.items(), key=lambda kv: -kv[1]["total"]))


# ══════════════════════════════════════════════════════════════════════
#  ٣. نمطُ الأسبوع لكلّ شعبة × مادّة، والتباينُ بين شُعب الصفّ
# ══════════════════════════════════════════════════════════════════════


def class_subject_patterns(lessons):
    """«9/1 رياضيات = الأحد٢، الاثنين٤…» — ثمّ يُقارَن بين شُعب الصفّ."""
    grouped = defaultdict(lambda: defaultdict(list))
    meta = {}
    for lesson in lessons:
        grouped[(lesson.class_id, lesson.subject_name)][lesson.day].append(lesson.period)
        meta[lesson.class_id] = (lesson.class_label or lesson.class_name, lesson.grade or "—")

    patterns = {}
    for (class_id, subject), days in grouped.items():
        name, grade = meta[class_id]
        patterns[(grade, name, subject)] = {
            DAY_NAMES[d]: sorted(set(p)) for d, p in sorted(days.items())
        }
    return patterns


def grade_section_variance(lessons):
    """هل تُعامَل شُعبُ الصفّ الواحد في المادّة الواحدة معاملةً متقاربة؟

    هذا أقربُ ما وصلنا إليه من **عدالةٍ طلّابيّة**: النصابُ واحدٌ والصفُّ
    واحدٌ والمادّةُ واحدة، فإن أخذت شعبةٌ نصفَ حصصها متأخّرةً وأخرى لا شيء،
    فالفارقُ لا يفسّره اختلافُ التكليف — بخلاف نصاب المعلّمين.

    والترتيبُ بفارق **العدد** لا النسبة: مادّةٌ نصابُها حصّتان تبلغ «مئةً
    بالمئة تأخّراً» بحصّتين اثنتين، فتتصدّر قائمةً هي فيها ضجيج. والفارقُ
    المعدود يقيس ما يقع على الطالب فعلاً.

    ويبقى مرشَّحاً لا حكماً: قد يكون أثراً لازماً لقيدٍ آخر (معملٌ واحد،
    معلّمٌ مشترك). لكنّه أقوى المرشّحات لأنّ المتغيّرات الأخرى مثبَّتة.
    """
    grouped = defaultdict(lambda: defaultdict(list))
    for lesson in lessons:
        key = (lesson.grade or "—", subject_ref(lesson))
        grouped[key][lesson.class_label or lesson.class_name].append(lesson)

    result = {}
    for (grade, ref), sections in grouped.items():
        if len(sections) < 2:
            continue
        subject_id, code, name = ref

        rows = {}
        for section, items in sections.items():
            per_day = defaultdict(set)
            for x in items:
                per_day[x.day].add(x.period)
            repeated = adjacent = 0
            for periods in per_day.values():
                if len(periods) < 2:
                    continue
                repeated += 1
                if any(len(run) >= 2 for run in _runs_of(periods)):
                    adjacent += 1
            weekly = sum(len(v) for v in per_day.values())
            rows[section] = {
                "weekly": weekly,
                "morning_pct": round(
                    sum(1 for x in items if x.period in MORNING) * 100 / len(items), 1
                ),
                "late_count": sum(1 for x in items if x.period in LATE),
                "late_pct": round(sum(1 for x in items if x.period in LATE) * 100 / len(items), 1),
                "repeated_days": repeated,
                "adjacent_double": adjacent,
                "mean_period": round(mean(x.period for x in items), 2),
            }

        rows = dict(sorted(rows.items()))
        weeklies = [r["weekly"] for r in rows.values()]
        lates = [r["late_pct"] for r in rows.values()]
        late_counts = [r["late_count"] for r in rows.values()]
        mornings = [r["morning_pct"] for r in rows.values()]
        means = [r["mean_period"] for r in rows.values()]
        result[f"{grade} · {subject_label(code, name)}"] = {
            "grade": grade,
            "subject_id": subject_id,
            "code": code,
            "name": name,
            "sections": rows,
            "equal_weekly": len(set(weeklies)) == 1,
            "weekly_spread": max(weeklies) - min(weeklies),
            "late_spread": round(max(lates) - min(lates), 1),
            "late_count_spread": max(late_counts) - min(late_counts),
            "weekly": max(weeklies),
            "morning_spread": round(max(mornings) - min(mornings), 1),
            "mean_period_spread": round(max(means) - min(means), 2),
            "latest_section": max(rows, key=lambda k: rows[k]["late_pct"]),
            "earliest_section": min(rows, key=lambda k: rows[k]["late_pct"]),
        }

    # الأشدُّ تبايناً أوّلاً، والنصابُ المتساوي مقدَّمٌ لأنّه يعزل السبب.
    return dict(
        sorted(
            result.items(),
            key=lambda kv: (
                kv[1]["equal_weekly"],
                kv[1]["late_count_spread"],
                kv[1]["weekly"],
                kv[1]["late_spread"],
            ),
            reverse=True,
        )
    )


# ══════════════════════════════════════════════════════════════════════
#  ٤. عدالةُ الشُّعب — ما يقع على الطلاب
# ══════════════════════════════════════════════════════════════════════


def section_burden(lessons, core_subjects=()):
    """الحصّةُ الأولى والسابعة والأيّامُ الثقيلة — لكلّ شعبة."""
    grouped = defaultdict(list)
    for lesson in lessons:
        grouped[lesson.class_id].append(lesson)

    rows = {}
    for _class_id, items in grouped.items():
        per_day = defaultdict(set)
        for x in items:
            per_day[x.day].add(x.period)
        counts = [len(v) for v in per_day.values()]
        name = items[0].class_label or items[0].class_name
        core_late = sum(1 for x in items if x.subject_name in core_subjects and x.period in LATE)
        rows[name] = {
            "grade": items[0].grade or "—",
            "level": items[0].level_type or "—",
            "lessons": len(items),
            "first_periods": sum(1 for v in per_day.values() if 1 in v),
            "seventh_periods": sum(1 for x in items if x.period == 7),
            "late_periods": sum(1 for x in items if x.period in LATE),
            "heaviest_day": max(counts) if counts else 0,
            "lightest_day": min(counts) if counts else 0,
            "core_in_late": core_late,
        }
    return dict(sorted(rows.items(), key=lambda kv: -kv[1]["seventh_periods"]))


# ══════════════════════════════════════════════════════════════════════
#  ٦. تشريحُ الفراغ — ليست كلُّ فجوةٍ مشكلةً تشغيليّة
# ══════════════════════════════════════════════════════════════════════


def gap_anatomy(lessons):
    """أربعةُ أنواعٍ لا رقمٌ واحد — لأنّ عبأها التشغيليَّ مختلف.

    * `internal_gap`   حصّةٌ خاليةٌ بين أوّل حصصه وآخرها — حضورٌ بلا عمل.
    * `leading_free`   ما قبل أوّل حصّة — ليس مطالَباً بالحضور فيه أصلاً.
    * `trailing_free`  ما بعد آخر حصّة — كذلك.
    * `multi_gap`      فجوةٌ داخليّةٌ طولُها حصّتان فأكثر — أثقلُ من مفردتين.

    فمن يعمل P1,P2,P6 له فراغٌ داخليٌّ ثقيل، ومن يعمل P3,P4 فقط ليس له
    فراغٌ داخليٌّ البتّة وإن بدا يومُه قصيراً.
    """
    grouped = defaultdict(lambda: defaultdict(set))
    names = {}
    for lesson in lessons:
        grouped[lesson.teacher_id][lesson.day].add(lesson.period)
        names[lesson.teacher_id] = lesson.teacher_name

    rows = {}
    for teacher_id, days in grouped.items():
        internal = single = multi = leading = trailing = 0
        worst = 0
        days_with_gap = 0
        for periods in days.values():
            ordered = sorted(periods)
            leading += ordered[0] - 1
            trailing += 7 - ordered[-1]
            holes = _runs_of([p for p in range(ordered[0], ordered[-1] + 1) if p not in periods])
            if holes:
                days_with_gap += 1
            for hole in holes:
                internal += len(hole)
                worst = max(worst, len(hole))
                if len(hole) == 1:
                    single += 1
                else:
                    multi += 1
        rows[names[teacher_id]] = {
            "teacher_id": teacher_id,
            "internal_gap": internal,
            "single_gap": single,
            "multi_gap": multi,
            "worst_gap": worst,
            "days_with_gap": days_with_gap,
            "leading_free": leading,
            "trailing_free": trailing,
            "days_used": len(days),
        }
    return dict(sorted(rows.items(), key=lambda kv: (-kv[1]["internal_gap"], -kv[1]["worst_gap"])))


# ══════════════════════════════════════════════════════════════════════
#  ٧. الحصصُ المنقسمة — كيانٌ مستقلٌّ لا تكرارٌ عارض
# ══════════════════════════════════════════════════════════════════════


def split_slots(lessons):
    """كلُّ خانةٍ تحمل أكثرَ من حصّةٍ لشعبةٍ واحدة، ومع من تنقسم."""
    grouped = defaultdict(list)
    for lesson in lessons:
        grouped[(lesson.class_id, lesson.day, lesson.period)].append(lesson)

    slots, pairings, grades = [], Counter(), Counter()
    for (_class_id, day, period), items in sorted(
        grouped.items(), key=lambda kv: (kv[0][1], kv[0][2])
    ):
        if len(items) < 2:
            continue
        entry = {
            "section": items[0].class_label or items[0].class_name,
            "grade": items[0].grade or "—",
            "day": DAY_NAMES.get(day, str(day)),
            "period": period,
            "branches": [
                {
                    "group": x.elective_group or "—",
                    "subject": x.subject_name,
                    "teacher": x.teacher_name,
                }
                for x in sorted(items, key=lambda x: x.subject_name)
            ],
        }
        slots.append(entry)
        pairings[" ⟷ ".join(sorted({x.subject_name for x in items}))] += 1
        grades[entry["grade"]] += 1
    return {"slots": slots, "pairings": dict(pairings), "grades": dict(grades)}


# ══════════════════════════════════════════════════════════════════════
#  ٨. المُعلَن مقابل الواقع: الحصّةُ المزدوجة
# ══════════════════════════════════════════════════════════════════════


def declared_versus_observed_doubles(school, lessons):
    """`Subject.requires_double_period` يقول «مزدوجة» — فماذا يقول الجدول؟

    وإن قال النموذجُ نعم وقال الواقعُ أربعين بالمئة، فإمّا الإعدادُ خاطئٌ
    وإمّا الجدولُ يخالف السياسة. وكلاهما يستحقّ أن يُعرَف.
    """
    from operations.models import Subject

    declared = {
        str(s.id): (s.code or "", s.name_ar, bool(s.requires_double_period))
        for s in Subject.objects.filter(school=school).only(
            "id", "code", "name_ar", "requires_double_period"
        )
    }
    observed = subject_adjacency(lessons)
    totals = Counter(subject_ref(x) for x in lessons)

    rows = {}
    for (subject_id, code, name), total in totals.most_common():
        row = observed.get(subject_id)
        model = declared.get(subject_id)
        rows[subject_id] = {
            "subject_id": subject_id,
            "code": code,
            "name": name,
            "declared_double": model[2] if model else None,
            "lessons": total,
            "daily_doubles": row.daily_doubles if row else 0,
            "adjacency_rate": row.adjacency_rate if row else 0.0,
            "commonest_pair": row.commonest_pair if row else "—",
        }
    return rows


# ══════════════════════════════════════════════════════════════════════
#  ٩. التوافرُ المُعلَن مقابل المرصود
# ══════════════════════════════════════════════════════════════════════

DECLARED_AND_OBSERVED = "DECLARED_AND_OBSERVED"
DECLARED_BUT_VIOLATED = "DECLARED_BUT_VIOLATED"
OBSERVED_ONLY = "OBSERVED_ONLY"


def availability_status(school, academic_year, lessons):
    """يقارن يومَ الفراغ المرصود بما هو مُعلَنٌ في `TeacherExemption`.

    و`OBSERVED_ONLY` لا يصير قيداً: خلوُّ يومٍ من الحصص قد يكون أثرَ الجدول
    لا قراراً إداريّاً — والفرقُ لا يُشتقّ من الأرقام.
    """
    from operations.models import TeacherExemption

    taught = defaultdict(set)
    names = {}
    for lesson in lessons:
        taught[lesson.teacher_id].add((lesson.day, lesson.period))
        names[lesson.teacher_id] = lesson.teacher_name

    declared = defaultdict(set)
    for ex in TeacherExemption.objects.filter(
        school=school, academic_year=academic_year, is_active=True
    ):
        tid = str(ex.teacher_id)
        if ex.exemption_type == "full_day":
            declared[tid] |= {(ex.day_of_week, p) for p in range(1, 8)}
        elif ex.period_number:
            declared[tid].add((ex.day_of_week, ex.period_number))

    rows = []
    for teacher_id, slots in taught.items():
        used_days = {d for d, _ in slots}
        declared_days = {d for d, _ in declared.get(teacher_id, set())}
        for day in sorted(set(DAY_NAMES) - used_days):
            rows.append(
                {
                    "teacher": names[teacher_id],
                    "day": DAY_NAMES[day],
                    "status": DECLARED_AND_OBSERVED if day in declared_days else OBSERVED_ONLY,
                }
            )
        for day in sorted(declared_days & used_days):
            clash = sorted(p for d, p in slots if d == day and (d, p) in declared[teacher_id])
            if clash:
                rows.append(
                    {
                        "teacher": names[teacher_id],
                        "day": DAY_NAMES[day],
                        "status": DECLARED_BUT_VIOLATED,
                        "periods": clash,
                    }
                )
    return rows


# ══════════════════════════════════════════════════════════════════════
#  ١٠ و ١١. ما يأتي بعد ماذا، وتسلسلُ اليوم
# ══════════════════════════════════════════════════════════════════════


def subject_transitions(lessons):
    """«رياضيات ← علوم ٤٢ مرّة» — قواعدُ لا تظهر من تحليل الازدواج."""
    grouped = defaultdict(dict)
    for lesson in lessons:
        grouped[(lesson.class_id, lesson.day)][lesson.period] = lesson.subject_name

    pairs = Counter()
    for periods in grouped.values():
        for period, subject in periods.items():
            following = periods.get(period + 1)
            if following:
                pairs[f"{subject} ← {following}"] += 1
    return dict(pairs.most_common())


def day_sequences(lessons):
    """تسلسلُ مواد اليوم لكلّ شعبة — لتُصنَّف أنماطُه إداريّاً لاحقاً."""
    grouped = defaultdict(dict)
    meta = {}
    for lesson in lessons:
        grouped[(lesson.class_id, lesson.day)][lesson.period] = lesson.subject_name
        meta[lesson.class_id] = lesson.class_label or lesson.class_name

    sequences = {}
    for (class_id, day), periods in sorted(
        grouped.items(), key=lambda kv: (meta[kv[0][0]], kv[0][1])
    ):
        ordered = [periods[p] for p in sorted(periods)]
        sequences[f"{meta[class_id]} · {DAY_NAMES.get(day, day)}"] = ordered
    return sequences


# ══════════════════════════════════════════════════════════════════════
#  ١٢. الخميس مفصولٌ تماماً
# ══════════════════════════════════════════════════════════════════════


def thursday_apart(lessons):
    """الخميسُ ليس يوماً عاديّاً — فلا يُدخَل في متوسّط الأربعة."""
    ordinary = [x for x in lessons if x.day != 4]
    thursday = [x for x in lessons if x.day == 4]

    def shape(items):
        if not items:
            return {"lessons": 0}
        per_class_day = defaultdict(set)
        for x in items:
            per_class_day[(x.class_id, x.day)].add(x.period)
        counts = [len(v) for v in per_class_day.values()]
        return {
            "lessons": len(items),
            "max_slots_per_section_day": max(counts),
            "median_slots_per_section_day": median(counts),
            "late_share_pct": round(
                sum(1 for x in items if x.period in LATE) * 100 / len(items), 1
            ),
        }

    by_level = {}
    for level in {x.level_type or "—" for x in thursday}:
        by_level[level] = shape([x for x in thursday if (x.level_type or "—") == level])
    return {"ordinary_days": shape(ordinary), "thursday": shape(thursday), "by_level": by_level}


# ══════════════════════════════════════════════════════════════════════
#  مقارنةُ النظراء — لا يُقارَن صاحبُ الثلاث بصاحب الثمانيةَ عشر
# ══════════════════════════════════════════════════════════════════════


def peer_outliers(teacher_profiles, lessons, band=2):
    """يجمع المعلّمين في شرائحِ نصابٍ متقاربة ثمّ يصف التوزّعَ داخلها.

    ومقارنةُ المدرسة كلِّها دفعةً واحدةً تُنتج «ظلماً» موهوماً: من نصابُه ثلاثٌ
    ليس كمن نصابُه ثمانيةَ عشر، وقد يكون منسّقاً أو مخفَّضَ النصاب. والنصابُ
    المطلوب ليس في الجدول أصلاً — فالمقارنةُ داخل الشريحة أقربُ ما نملك.

    ولا يُسمّى أحدٌ «شاذّاً» بعتبةٍ مخترعة: تُذكر أطرافُ الشريحة ووسيطُها،
    ويُترك الحكمُ لمن يعرف التكليف. والشرائحُ التي يقلّ عددُها عن ثلاثةٍ
    تُذكر باسمها في `too_small` ولا تُطوى صامتةً — فمن سقط من القياس يُسمّى.
    """
    anatomy = gap_anatomy(lessons)
    bands = defaultdict(list)
    for profile in teacher_profiles:
        bands[profile.weekly // band * band].append(profile)

    result, too_small = {}, {}
    for floor, members in sorted(bands.items()):
        label = f"{floor}–{floor + band - 1}"
        rows = []
        for m in members:
            a = anatomy.get(m.name, {})
            rows.append(
                {
                    "name": m.name,
                    "weekly": m.weekly,
                    "internal_gap": a.get("internal_gap", 0),
                    "multi_gap": a.get("multi_gap", 0),
                    "worst_gap": a.get("worst_gap", 0),
                    "days_used": m.days_used,
                }
            )
        rows.sort(key=lambda r: -r["internal_gap"])
        if len(members) < 3:
            too_small[label] = rows
            continue
        internal = [r["internal_gap"] for r in rows]
        result[label] = {
            "teachers": len(members),
            "median_gaps": median(internal),
            "min_gaps": min(internal),
            "max_gaps": max(internal),
            "median_multi": median([r["multi_gap"] for r in rows]),
            "heaviest": rows[:2],
            "lightest": rows[-2:],
        }
    return {"bands": result, "too_small": too_small}

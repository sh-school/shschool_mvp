"""schedule_feasibility.py — أيمكن أن يُبنى هذا الجدولُ أصلاً؟

    الحسابُ بالعدّ يسبق البحثَ بالساعات.

المولّدُ يبحث، والبحثُ لا يعرف الفرقَ بين «لم أجد» و«لا يوجد». فحين يكون
الطلبُ أكبرَ من الخانات، يدور المولّدُ حتى ينفد وقتُه ثمّ يخرج بحصصٍ متعذّرةٍ
بلا أن يقول لماذا. وقد وقع ذلك على الإنتاج: سبعمئةٌ وخمسٌ وثلاثون ثانيةً ثمّ
سقوطٌ على Railway (2026-09-03).

وهذه الفحوصُ لا تبحث: تعدّ. تقارن ما تطلبه التوزيعاتُ بما تسعه الخانات —
للشعبة، وللمعلّم، وللمورد، ولمادّةٍ يجب أن تتفرّق أيّامُها. فما ظهر عجزُه
هنا لن يجده بحثٌ مهما طال، وعلاجُه في المُدخلات لا في الخوارزميّة.

والفحصُ يُعلم ولا يمنع: قرارُ «ولّد على أيّ حال» قرارُ النائب الأكاديميّ، لكن
لا يصحّ أن يتّخذه وهو لا يرى الثمن.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import time

from core.models import School

from .models import SchedulingResource, SubjectClassAssignment, TeacherExemption, TeacherPreference
from .scheduler_bell import HC5_JOINABLE_GAP_MINUTES
from .scheduler_constraints import THURSDAY, get_max_periods_for_day

#: أيّامُ الأسبوع الدراسيّ — الأحدُ إلى الخميس، كما في `scheduler.DAYS`.
DAYS = (0, 1, 2, 3, 4)

OK, WARN, FAIL = "ok", "warn", "fail"

#: هامشٌ وقائيٌّ أسفل السقف الصلب (AS-4/AS-5) — توصيةُ 0104، **غيرُ موصَّفٍ
#: رسمياً في المنصّة** (استعملت 2..3 في توليدها التجريبيّ بلا تثبيت رقم).
#: من بلغ السقفَ بهامشٍ أقلَّ من هذا يُحذَّر لا يُرفَض — فالرفضُ لمن تجاوز
#: السقفَ قطعاً (`load > cap`)، والتحذيرُ لمن وقف عليه بلا مَتَّسع.
DAILY_LOAD_MARGIN = 2


@dataclass(frozen=True)
class Shortfall:
    """عجزُ طرفٍ واحد: ما طُلب منه، وما يسعه، والفرق."""

    name: str
    demand: int
    capacity: int
    note: str = ""

    @property
    def gap(self) -> int:
        return max(0, self.demand - self.capacity)


@dataclass(frozen=True)
class Finding:
    """نتيجةُ فحصٍ واحد — عنوانُه وحكمُه وتفصيلُه."""

    code: str
    title: str
    status: str
    summary: str
    rows: tuple[Shortfall, ...] = ()

    @property
    def gap(self) -> int:
        """أقلُّ ما يتعذّر وضعُه بسبب هذا الفحص — مجموعُ عجز أطرافه."""
        return sum(r.gap for r in self.rows)

    @property
    def is_blocking(self) -> bool:
        return self.status == FAIL


@dataclass(frozen=True)
class FeasibilityReport:
    findings: tuple[Finding, ...] = field(default_factory=tuple)

    @property
    def blocking(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.is_blocking)

    @property
    def warnings(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.status == WARN)

    @property
    def feasible(self) -> bool:
        return not self.blocking

    @property
    def minimum_unplaceable(self) -> int:
        """حدٌّ أدنى لعدد الحصص التي لن تجد موضعاً مهما طال البحث.

        وهو **أدنى** لا مجموع: الفحوصُ تتقاطع — معلّمٌ ضاق وقتُه قد يكون هو
        صاحبَ المادّة التي ضاقت أيّامُها — فيُؤخذ أكبرُ عجزٍ لا حاصلُ الجمع،
        كي لا يُوعَد المستخدمُ برقمٍ أسوأَ من الحقيقة.
        """
        return max((f.gap for f in self.blocking), default=0)

    def as_dict(self) -> dict:
        """صورةٌ تُحفظ مع عمليّة التوليد — فالحكمُ يُقرأ بعد أشهر."""
        return {
            "feasible": self.feasible,
            "minimum_unplaceable": self.minimum_unplaceable,
            "findings": [
                {
                    "code": f.code,
                    "status": f.status,
                    "summary": f.summary,
                    "gap": f.gap,
                    "rows": [
                        {
                            "name": r.name,
                            "demand": r.demand,
                            "capacity": r.capacity,
                            "note": r.note,
                        }
                        for r in f.rows
                    ],
                }
                for f in self.findings
            ],
        }


# ── ما تسعه الخانات ──────────────────────────────────────────────────


def weekly_capacity(level_type: str) -> int:
    """خاناتُ الأسبوع لشعبةٍ في مرحلتها — والخميسُ وحدَه يختلف (HC4)."""
    return sum(get_max_periods_for_day(day, level_type) for day in DAYS)


def _exempt_map(school: School, year: str) -> tuple[dict, dict]:
    """لكلّ معلّم: أيّامُه المفرَّغةُ كاملةً، وعددُ حصصه المفرَّغة في كلّ يوم.

    والقيودُ الشخصيّةُ الدائمةُ («لا أولى ولا سابعة») تُحسب معها: المولّدُ
    يقرؤها من الجدول نفسِه، فهي خاناتٌ خارجةٌ عن وقته حقّاً.
    """
    full_days: dict[str, set] = defaultdict(set)
    blocked: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    for ex in TeacherExemption.objects.filter(
        school=school, academic_year=year, is_active=True
    ).only("teacher_id", "exemption_type", "day_of_week", "period_number"):
        tid = str(ex.teacher_id)
        if ex.exemption_type == "full_day":
            full_days[tid].add(ex.day_of_week)
        else:
            blocked[tid][ex.day_of_week] += 1
    return full_days, blocked


# ── الفحوص ───────────────────────────────────────────────────────────


def _check_unassigned(assignments) -> Finding:
    """إسنادٌ بلا معلّمٍ لا يدخل الجدولَ أصلاً — `build_tasks` يتخطّاه صامتاً."""
    orphans = [a for a in assignments if not a.teacher_id]
    lost = sum(a.weekly_periods for a in orphans)
    if not orphans:
        return Finding(
            "assignment.unassigned",
            "إسنادٌ بلا معلّم",
            OK,
            "كلُّ إسنادٍ له معلّم.",
        )
    return Finding(
        "assignment.unassigned",
        "إسنادٌ بلا معلّم",
        WARN,
        f"{len(orphans)} إسناداً بلا معلّم — {lost} حصّةً لن تدخل الجدولَ ولن تُعَدّ متعذّرة.",
        tuple(
            Shortfall(f"{a.class_group} · {a.subject}", a.weekly_periods, 0, "بلا معلّم")
            for a in orphans[:20]
        ),
    )


def _check_classes(assignments) -> Finding:
    """طاقةُ الشعبة — الحسابُ في `CapacityCheckService` ولا يُعاد هنا."""
    from .services import CapacityCheckService

    over = CapacityCheckService.get_overcapacity_classes(assignments)
    if not over:
        return Finding(
            "capacity.class",
            "طاقةُ الشُّعب",
            OK,
            "لا شعبةَ طلبُها فوقَ خاناتِ أسبوعها.",
        )
    rows = tuple(
        Shortfall(
            o["class_name"],
            o["demand"],
            o["capacity"],
            #: السببُ المرجَّحُ يُقال لا يُترك للتخمين: وسمُ توازٍ بلا شريكٍ في
            #: الشعبة لا يُخصَم من الطلب، فيظهر فائضٌ سببُه وسمٌ ناقصٌ لا نصابٌ
            #: زائد. وعلاجُه إشعالُ «متوازية» على شريكة المادّة في شاشة الإسناد.
            note=(
                "توازٍ ناقصٌ شريكَه: " + "، ".join(o["orphan_parallels"])
                if o.get("orphan_parallels")
                else ""
            ),
        )
        for o in sorted(over, key=_by_over)
    )
    return Finding(
        "capacity.class",
        "طاقةُ الشُّعب",
        FAIL,
        f"{len(rows)} شعبةً طلبُها فوقَ خاناتِ أسبوعها — بمجموع {sum(r.gap for r in rows)} حصّة.",
        rows,
    )


def _by_over(row: dict) -> int:
    return -row["overflow"]


def _check_teachers(assignments, full_days: dict, blocked: dict) -> Finding:
    """طاقةُ المعلّم: نصابُه مقابلَ خاناتِه بعد تفريغاته.

    وسقفُ يومه أوسعُ سقوفِ شُعبه: من يُدرّس الثانويَّ له سابعةٌ يومَ الخميس،
    ومن لا يدرّسه فلا. والتوازي لا يُدمج هنا — الشعبةُ تُقسَم فيأخذ كلُّ
    معلّمٍ نصفَها، وكلاهما مشغولٌ في التوقيت نفسه.
    """
    demand: dict[str, int] = defaultdict(int)
    levels: dict[str, set] = defaultdict(set)
    names: dict[str, str] = {}
    for a in assignments:
        if not a.teacher_id:
            continue
        tid = str(a.teacher_id)
        demand[tid] += a.weekly_periods
        levels[tid].add(a.class_group.level_type or "")
        names[tid] = a.teacher.full_name

    rows = []
    for tid, need in demand.items():
        capacity = 0
        for day in DAYS:
            if day in full_days.get(tid, ()):
                continue
            widest = max(get_max_periods_for_day(day, lv) for lv in levels[tid])
            capacity += max(0, widest - blocked.get(tid, {}).get(day, 0))
        if need > capacity:
            free = len(full_days.get(tid, ()))
            note = f"{free} يومَ تفريغٍ كامل" if free else ""
            rows.append(Shortfall(names[tid], need, capacity, note))

    if not rows:
        return Finding(
            "capacity.teacher",
            "طاقةُ المعلّمين",
            OK,
            "لا معلّمَ نصابُه فوقَ خاناته بعد التفريغات.",
        )
    rows.sort(key=lambda r: -r.gap)
    return Finding(
        "capacity.teacher",
        "طاقةُ المعلّمين",
        FAIL,
        f"{len(rows)} معلّماً نصابُه فوقَ خاناته — بمجموع {sum(r.gap for r in rows)} حصّة.",
        tuple(rows),
    )


def _check_resources(school: School, assignments) -> Finding:
    """المورد المحدود: الطلبُ عليه مقابلَ سعتِه في توقيتات الأسبوع (HC9)."""
    by_subject: dict[str, list] = defaultdict(list)
    for resource in SchedulingResource.objects.filter(
        school=school, is_active=True
    ).prefetch_related("subjects"):
        for subject in resource.subjects.all():
            by_subject[str(subject.id)].append(resource)

    if not by_subject:
        return Finding("capacity.resource", "الموارد", OK, "لا موردَ محدودٌ مسجَّل.")

    demand: dict[str, int] = defaultdict(int)
    names: dict[str, str] = {}
    caps: dict[str, int] = {}
    for a in assignments:
        for resource in by_subject.get(str(a.subject_id), ()):
            rid = str(resource.id)
            demand[rid] += a.weekly_periods
            names[rid] = resource.name
            caps[rid] = resource.capacity

    #: أوسعُ تقديرٍ للطاقة: السعةُ في كلّ توقيتٍ من الأسبوع بأطول سقفٍ يوميّ.
    #: فما عجز هنا عاجزٌ يقيناً، ولا يُنذَر أحدٌ بالشكّ.
    slots = weekly_capacity("sec")
    rows = [
        Shortfall(names[rid], need, caps[rid] * slots, f"سعةُ التوقيت {caps[rid]}")
        for rid, need in demand.items()
        if need > caps[rid] * slots
    ]
    if not rows:
        return Finding(
            "capacity.resource",
            "الموارد",
            OK,
            "لا موردَ طلبُه فوقَ سعتِه.",
        )
    rows.sort(key=lambda r: -r.gap)
    return Finding(
        "capacity.resource",
        "الموارد",
        FAIL,
        f"{len(rows)} مورداً طلبُه فوقَ سعتِه — بمجموع {sum(r.gap for r in rows)} حصّة.",
        tuple(rows),
    )


# ── AS-1/AS-2/AS-4/AS-5: قيودُ الإسناد الضمنيّة (W-20261001-046) ───────
#
# كشفتها جلسةُ «عصفٌ ذهنيّ: معايير التوليد» عبر توليد CP-SAT تجريبيّ لم
# يُنمذج القيودَ التالية صراحةً، فأثبتَ `INFEASIBLE` إسناداً يخالفها قبل أن
# يبدأ التوليدُ — وهذا سببُ وجودها هنا: ليست قيوداً على الجدولة بل على
# الإسناد نفسِه، فلا تحتاج محرّكاً للكشف عنها، والعدُّ يكفي كما في بقية هذا
# الملفّ. AS-3 (صفٌّ نصابُه خمسٌ يلزمه خمسةُ أيّامٍ) وAS-6 (مطابقةُ
# التوزيعات لا تضمن الجدوى) لا تُرمَّزان: الأولى أثرُ نموذجٍ معزولٍ لا قيدَ
# منصّةٍ (المنصّةُ تحسب سقفَ اليوم بـ`available_days` الفعليّ لا بخمسةٍ
# محفورة)، والثانيةُ حكمٌ منهجيٌّ على الرسائل لا شرطٌ على صفّ.


def _minutes(moment: time) -> int:
    return moment.hour * 60 + moment.minute


def _band_day_cap(school: School, band_ids: frozenset[str], day_type: str) -> int:
    """AS-1/AS-5: أقصى خاناتٍ غيرِ متلاصقةٍ في يومٍ، من اتّحاد خانات نطاقاته.

    معلّمٌ يخدم نطاقين قد تتلاصق خانتاهما بالساعة وإن اختلف رقمُ الحصّة —
    فجرسُ النطاقات متداخلٌ بالساعة. فالحسابُ هنا على الأوقات الفعليّة
    (`TimeSlotConfig`) لا على عدد الحصص، واتّحادُ الخانات **لا يزيد** السقفَ
    بل قد يُنقصه؛ وهذا بعينه الفارقُ عن `get_max_periods_for_day` الذي يعدّ
    الحصصَ بلا نظرٍ إلى تلاصقها (`_check_teachers` أعلاه).
    """
    from .models import TimeSlotConfig

    rows = TimeSlotConfig.objects.filter(school=school, day_type=day_type, is_break=False)
    intervals: set[tuple[time, time]] = set()
    for band_id in band_ids or {""}:
        scoped = rows.filter(band_id=band_id) if band_id else rows.filter(band__isnull=True)
        for row in scoped.only("start_time", "end_time"):
            intervals.add((row.start_time, row.end_time))
    if not intervals:
        #: لا جرسَ معروفاً لهذا النطاق — الصمتُ لا يُقرأ منعاً (كـ`are_joined`).
        return get_max_periods_for_day(THURSDAY if day_type == "thursday" else 0, "")

    count, end = 0, None
    for start, finish in sorted(intervals):
        if end is None or _minutes(start) - _minutes(end) > HC5_JOINABLE_GAP_MINUTES:
            count += 1
            end = finish
        elif finish > end:
            end = finish
    return count


def _check_daily_band_load(
    school: School, year: str, assignments, full_days: dict, blocked: dict
) -> Finding:
    """AS-1 + AS-4/AS-5: نصابُ المعلّم مقابلَ سقفَين، والسَّاري أضيقُهما.

    AS-5 بنيويٌّ عامٌّ: سقفُ الجرس بالأوقات الفعليّة عبر نطاقات المعلّم كلِّها
    (AS-1 هو سببُ ضيقه حين يخدم نطاقَين). وAS-4 شخصيٌّ: `max_daily_periods`
    الذي كتبته الإدارةُ في حقّ معلّمٍ بعينه (`TeacherPreference`) — ولا يسري
    إلّا لمن له سجلٌّ فعليّ؛ غيابُ السجلّ غيابُ قيدٍ لا الافتراضُ ٥. والقيدُ
    الساري أضيقُهما — فمن رُفض إسنادُه يُقال له أيُّهما حكم، لا «نصابٌ زائد»
    غامضة.
    """
    demand: dict[str, int] = defaultdict(int)
    bands: dict[str, set] = defaultdict(set)
    names: dict[str, str] = {}
    for a in assignments:
        if not a.teacher_id:
            continue
        tid = str(a.teacher_id)
        demand[tid] += a.weekly_periods
        bands[tid].add(str(a.class_group.time_band_id or ""))
        names[tid] = a.teacher.full_name

    personal = {
        str(k): v
        for k, v in TeacherPreference.objects.filter(school=school, academic_year=year).values_list(
            "teacher_id", "max_daily_periods"
        )
    }

    rows = []
    for tid, need in demand.items():
        days = [d for d in DAYS if d not in full_days.get(tid, ())]
        if not days:
            continue
        structural = sum(
            max(
                0,
                _band_day_cap(
                    school, frozenset(bands[tid]), "thursday" if d == THURSDAY else "regular"
                )
                - blocked.get(tid, {}).get(d, 0),
            )
            for d in days
        )
        #: لا تفضيلَ مسجَّلٌ يعني لا قيدَ شخصيّاً — لا الافتراضَ ٥ من حقل
        #: النموذج. فذاك افتراضُ عرضِ الاستمارة لمن يملأها، وليس قراراً
        #: إداريّاً صدر في حقّ من لم يُفتح له سجلٌّ أصلاً (AS-4 "لمن كُتب له").
        personal_cap = personal[tid] * len(days) if tid in personal else None
        if personal_cap is None or structural <= personal_cap:
            binding, source = structural, "سقفُ الجرس"
        else:
            binding, source = personal_cap, "تفضيلُه الشخصيّ"
        gap = max(0, need - binding)
        slack = binding - need
        if gap > 0:
            rows.append((FAIL, Shortfall(names[tid], need, binding, f"يضيّقه {source}")))
        elif slack < DAILY_LOAD_MARGIN:
            rows.append(
                (
                    WARN,
                    Shortfall(names[tid], need, binding, f"على حدّ {source} بلا هامش ({slack})"),
                )
            )

    if not rows:
        return Finding(
            "assignment.daily_band",
            "النصابُ مقابلَ سقف الجرس الفعليّ (AS-1/AS-4/AS-5)",
            OK,
            "لا معلّمَ نصابُه يبلغ سقفَ جرسه أو تفضيلَه الشخصيّ بلا هامش.",
        )
    failing = [r for s, r in rows if s == FAIL]
    warning = [r for s, r in rows if s == WARN]
    failing.sort(key=lambda r: -r.gap)
    status = FAIL if failing else WARN
    summary = []
    if failing:
        summary.append(
            f"{len(failing)} معلّماً تجاوز نصابُه سقفَه — بمجموع {sum(r.gap for r in failing)} حصّة"
        )
    if warning:
        summary.append(f"{len(warning)} معلّماً على الحدّ بلا هامش")
    return Finding(
        "assignment.daily_band",
        "النصابُ مقابلَ سقف الجرس الفعليّ (AS-1/AS-4/AS-5)",
        status,
        "، ".join(summary) + ".",
        tuple(failing + warning),
    )


def _check_parallel_same_teacher(assignments) -> Finding:
    """AS-2: المجموعةُ المتوازيةُ تلزمها معلّمون مختلفون — خرقٌ صامتٌ عن HC1.

    `_to_tasks` يدمج أعضاءَ المجموعة المتوازية (الشعبة نفسُها + الوسمُ نفسُه)
    في مهمّةٍ واحدة. فإسنادُ المعلّم نفسِه لعضوَين فيها يضعه في خانةٍ واحدةٍ
    مرّتين — وHC1 يفحص التضاربَ بين مهمّتين لا داخلَ المهمّة، فلا يراه. ولا
    يكفي أن يُسنَد معلّمٌ مؤهَّلٌ للمجموعة؛ يلزم أن يكون **معلّماً مختلفاً**
    عن كلّ عضوٍ آخر فيها — أربعُ شُعبٍ نصابُها 37 وخاناتُها 35 لا تُسع إلّا
    بهذا (قياسٌ على تصدير الإنتاج 2026-10-01).
    """
    groups: dict[tuple[str, str], list] = defaultdict(list)
    for a in assignments:
        label = (a.parallel_group or "").strip()
        if label:
            groups[(str(a.class_group_id), label)].append(a)

    rows = []
    for (cid, label), members in groups.items():
        teacher_ids = [str(m.teacher_id) for m in members if m.teacher_id]
        if len(set(teacher_ids)) < len(teacher_ids):
            dup_counts: dict[str, int] = defaultdict(int)
            for tid in teacher_ids:
                dup_counts[tid] += 1
            dup_name = next(
                m.teacher.full_name
                for m in members
                if str(m.teacher_id) in {t for t, n in dup_counts.items() if n > 1}
            )
            class_name = str(members[0].class_group)
            rows.append(
                Shortfall(
                    f"{class_name} · {label}",
                    len(teacher_ids),
                    len(set(teacher_ids)),
                    f"المعلّمُ {dup_name} مُسنَدٌ لعضوَين في المجموعة — يقع في خانةٍ واحدةٍ مرّتين ولا يراه HC1",
                )
            )

    if not rows:
        return Finding(
            "assignment.parallel_same_teacher",
            "تمايزُ معلّمي المجموعة المتوازية (AS-2)",
            OK,
            "كلُّ مجموعةٍ متوازيةٍ معلّموها مختلفون.",
        )
    rows.sort(key=lambda r: -r.gap)
    return Finding(
        "assignment.parallel_same_teacher",
        "تمايزُ معلّمي المجموعة المتوازية (AS-2)",
        FAIL,
        f"{len(rows)} مجموعةً متوازيةً فيها معلّمٌ مكرّر — خرقٌ صامتٌ لا يظهر في عدّ المخالفات.",
        tuple(rows),
    )


def check(school: School, year: str) -> FeasibilityReport:
    """يعدّ ولا يبحث — تقريرٌ يُقرأ قبل أن يُضغط زرُّ التوليد."""
    assignments = list(
        SubjectClassAssignment.objects.filter(
            school=school, academic_year=year, is_active=True
        ).select_related("class_group", "class_group__time_band", "subject", "teacher")
    )
    full_days, blocked = _exempt_map(school, year)
    return FeasibilityReport(
        (
            _check_classes(assignments),
            _check_teachers(assignments, full_days, blocked),
            _check_resources(school, assignments),
            _check_unassigned(assignments),
            _check_daily_band_load(school, year, assignments, full_days, blocked),
            _check_parallel_same_teacher(assignments),
        )
    )

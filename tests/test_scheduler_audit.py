"""[SCHEDULE] أثرُ القيود والمدقّقُ المستقلّ (SCH-01، SCH-02).

جاء الجدولُ المعتمد في 2026-09-24 باثنتي عشرةَ مخالفةً للقسمة (HC6) لم يرها أحد:
الباني يعدّ رخصَه ولا يحفظ مواضعها. فصار له شاهدان:

    slot_violations   أيُّ قيدٍ صلبٍ يرفض الخانةَ باسمه — كلُّها لا أوّلُها
    grid_breaches     الجدولُ المنتهي يُفحص حصّةً حصّةً بلا رخصة

والشاهدُ لا يُصدَّق إلّا بثلاث: أن يوافق حكمَ التوليد في كلّ خانة (فلا نسختان من
القيود تفترقان يوماً)، وأن يعدّ المخالفةَ بموضوعها لا بحصصها، وأن يترك الشبكةَ
كما وجدها. وفي آخر الملفّ ثغراتٌ معروفةٌ موسومةٌ `xfail` صارماً: كلٌّ منها يصف
ما ينبغي، فإن أُصلحت الثغرةُ سقط الوسمُ وطالب بحذفه.

والاختباراتُ كلُّها في الذاكرة: لا قاعدةَ بيانات ولا توليد.
"""

import datetime as dt
import json

import pytest

from operations.constraint_registry import RELAXED, ConstraintPolicy, default_policy
from operations.scheduler import DAYS, Member, ScheduleGrid, Task, _day_coverage
from operations.scheduler_audit import EXEMPTION, grid_breaches, summary, task_breaches
from operations.scheduler_constraints import is_slot_valid, slot_violations

PERIODS = range(1, 8)
#: (allow_adjacent, allow_dense) — الجولةُ الصارمة ثمّ الرخصتان منفردتين ومجتمعتين.
LICENCES = [(False, False), (True, False), (False, True), (True, True)]


def lesson(
    klass="c-1",
    subject="s-mat",
    teacher="t-1",
    *,
    weekly=5,
    span=1,
    double=False,
    level="prep",
    grade="G7",
    band="",
    resources=(),
    members=(),
    cap=0,
    gap=None,
    subject_name="رياضيات",
    teacher_name="",
):
    return Task(
        class_id=klass,
        class_name=klass,
        subject_id=subject,
        subject_name=subject_name,
        subject_code=subject.upper(),
        teacher_id=teacher,
        teacher_name=teacher_name or teacher,
        weekly_periods=weekly,
        prefers_double=double,
        level_type=level,
        grade=grade,
        consecutive_cap=cap,
        gap_cap=gap,
        band_id=band,
        resources=tuple(resources),
        span=span,
        members=list(members),
    )


def split(klass, first, second, *, weekly=2):
    """شعبةٌ منقسمة: مادّتان ومعلّمان في الخانة نفسها — والأوّلُ هو «رأسُ» المهمّة."""
    members = [Member(t, t, s, s, s.upper()) for t, s in (first, second)]
    return lesson(klass, first[1], first[0], weekly=weekly, members=members)


def snapshot(grid, tasks):
    """ما يراه كلُّ قيدٍ من الشبكة — بواجهتها العامّة لا بفهارسها الداخليّة."""
    classes = {t.class_id for t in tasks}
    teachers = {m.teacher_id for t in tasks for m in t.members}
    cells = {
        (c, d, p): id(grid.get_task_at(c, d, p)) for c in classes for d in DAYS for p in PERIODS
    }
    busy = {
        (t, d, p): id(grid.teacher_task_at(t, d, p))
        for t in teachers
        for d in DAYS
        for p in PERIODS
    }
    per_day = {
        (t.class_id, t.subject_id, d): grid.subject_on_day(t.class_id, t.subject_id, d)
        for t in tasks
        for d in DAYS
    }
    loads = {(t, d): grid.teacher_periods_on_day(t, d) for t in teachers for d in DAYS}
    homes = {id(t): grid.home_of(t) for t in tasks}
    entries = sorted((id(e["task"]), e["day"], e["period"]) for e in grid.all_entries())
    return cells, busy, per_day, loads, homes, entries


# ══════════════════════════════════════════════════════════════
#  المشاهد — شبكاتٌ تُسأل عنها كلُّ خانة
# ══════════════════════════════════════════════════════════════

#: جرسان: الأرضيّ (بلا نطاق) والعلويّ («up») — ثانيةُ الأرضيّ تتداخل مع ثالثة
#: العلويّ خمسَ دقائق، وثالثتُه تنتهي حيث تبدأ رابعةُ العلويّ.
GROUND = {
    1: (dt.time(7, 10), dt.time(8, 0)),
    2: (dt.time(8, 0), dt.time(8, 50)),
    3: (dt.time(8, 50), dt.time(9, 35)),
    4: (dt.time(9, 55), dt.time(10, 40)),
    5: (dt.time(10, 40), dt.time(11, 25)),
    6: (dt.time(11, 25), dt.time(12, 10)),
    7: (dt.time(12, 30), dt.time(13, 15)),
}
UPPER = {
    1: (dt.time(7, 10), dt.time(7, 55)),
    2: (dt.time(7, 55), dt.time(8, 45)),
    3: (dt.time(8, 45), dt.time(9, 35)),
    4: (dt.time(9, 35), dt.time(10, 25)),
    5: (dt.time(10, 45), dt.time(11, 35)),
    6: (dt.time(11, 35), dt.time(12, 25)),
    7: (dt.time(12, 25), dt.time(13, 15)),
}
BANDS = {("", "regular"): GROUND, ("up", "regular"): UPPER}
BREAKS = {
    ("", "regular"): [
        (dt.time(9, 35), dt.time(9, 55), "فسحة"),
        (dt.time(12, 10), dt.time(12, 30), "صلاة"),
    ],
    ("up", "regular"): [(dt.time(10, 25), dt.time(10, 45), "فسحة")],
}


def scene_empty():
    """شبكةٌ فارغة: لا يرفض خانةً إلّا سقفُ اليوم (سابعةُ الخميس للإعداديّ)."""
    candidates = [
        lesson("c-1"),
        lesson("c-11", "s-phy", "t-2", level="sec", grade="G11"),
        lesson("c-2", "s-art", "t-3", weekly=2, span=2, double=True),
        split("c-3", ("t-4", "s-chem"), ("t-5", "s-bio")),
    ]
    return ScheduleGrid(), candidates, {"HC4"}


def scene_partial():
    """شبكةٌ نصفُ ممتلئة فيها لكلّ قيدٍ من قيود الشعبة والمعلّم والمورد خانةٌ ترفض."""
    grid = ScheduleGrid()
    maths = [lesson("c-1") for _ in range(5)]
    grid.place(0, 1, maths[0])
    grid.place(1, 2, maths[1])
    grid.place(2, 2, maths[2])
    grid.place(0, 7, lesson("c-2", "s-sci", "t-1", weekly=4))
    grid.place(1, 7, lesson("c-3", "s-sci", "t-1", weekly=4))
    grid.place(0, 4, lesson("c-1", "s-eng", "t-2"))
    grid.place(4, 1, lesson("c-11", "s-phy", "t-3", weekly=6, level="sec", grade="G11"))
    gym, yard = ("r-gym", 1, False), ("r-yard", 2, True)
    grid.place(2, 3, lesson("c-5", "s-pe", "t-6", weekly=2, resources=[gym]))
    grid.place(
        2, 5, lesson("c-7", "s-pe", "t-7", weekly=2, level="sec", grade="G10", resources=[yard])
    )
    candidates = [
        maths[3],  # الأحدُ: HC6 وHC20 وHC5 — والثانيةُ للمرّة الثالثة: HC7
        lesson("c-4", "s-sci", "t-1", weekly=4),  # معلّمٌ مشغول HC1، وسابعةٌ ثالثة HC8
        lesson("c-11", "s-phy", "t-3", weekly=6, level="sec", grade="G11"),  # الخميس HC17
        lesson("c-6", "s-pe", "t-8", weekly=2, resources=[gym]),  # ملعبٌ ممتلئ HC9
        lesson("c-8", "s-pe", "t-9", weekly=2, resources=[yard]),  # مرحلتان HC11
        lesson("c-1", "s-art", "t-10"),  # شعبةٌ مشغولة HC2
    ]
    must = {"HC1", "HC2", "HC5", "HC6", "HC7", "HC8", "HC9", "HC11", "HC17", "HC20"}
    return grid, candidates, must


def scene_doubles_and_split():
    """المزدوجةُ خانتان، والمادّةُ المزاوَجةُ تُعفى من التلاصق، والمنقسمةُ بمعلّمَين."""
    grid = ScheduleGrid()
    art = [lesson("c-1", "s-art", "t-1", weekly=4, span=2, double=True) for _ in range(2)]
    grid.place(0, 2, art[0])
    grid.place(1, 5, lesson("c-1", "s-tech", "t-2", weekly=3, double=True))
    grid.place(0, 4, split("c-2", ("t-3", "s-chem"), ("t-4", "s-bio")))
    grid.place(0, 5, lesson("c-3", "s-mat", "t-4"))
    candidates = [
        art[1],
        lesson("c-1", "s-tech", "t-2", weekly=3, span=2, double=True),
        split("c-2", ("t-3", "s-chem"), ("t-4", "s-bio")),
        lesson("c-4", "s-mat", "t-3"),
    ]
    return grid, candidates, {"HC1", "HC2", "HC5", "HC6", "HC20"}


def scene_bells_and_coverage():
    """جرسان واستراحتان وتغطيةُ أيّامٍ وسقفُ فراغٍ شخصيّ — قيودُ الساعة والأسبوع."""
    ground_art = lesson("g-1", "s-art", "t-1", weekly=2, span=2, double=True)
    ground = [lesson(f"g-{k}", "s-mat", "t-2") for k in (2, 3)]
    upper = [lesson(f"u-{k}", "s-mat", "t-2", band="up", level="sec", grade="G10") for k in (1, 2)]
    strict = [lesson(f"g-{k}", "s-eng", "t-3", gap=0) for k in (4, 5)]
    full = [lesson(f"g-{k}", "s-geo", "t-5", weekly=1) for k in range(6, 11)]
    tasks = [ground_art, *ground, *upper, *strict, *full]
    grid = ScheduleGrid(band_times=BANDS, break_times=BREAKS, coverage=_day_coverage(tasks, set()))
    grid.place(0, 2, ground[0])  # الأرضيّ 8:00–8:50
    grid.place(1, 3, ground[1])  # الأرضيّ 8:50–9:35
    grid.place(2, 1, strict[0])
    grid.place(3, 1, full[0])
    candidates = [ground_art, upper[0], strict[1], full[1]]
    must = {"HC5", "HC10", "HC12", "HC13", "HC14", "HC16", "HC16B", "HC19"}
    return grid, candidates, must


SCENES = [scene_empty, scene_partial, scene_doubles_and_split, scene_bells_and_coverage]

#: كلُّ ما يقبل الرتبةَ يُكسَر في الرخصة الأولى — ليمرّ الاختبارُ بفرع `waived` أيضاً:
#: HC7 وHC8 وHC11 وHC16 وHC17 لا تلين بنفسها، فكسرُها تخطّيها.
LENIENT = ConstraintPolicy(
    breaks={
        code: RELAXED
        for code in ("HC5", "HC6", "HC7", "HC8", "HC11", "HC14", "HC16", "HC16B", "HC17", "HC20")
    },
    weights=default_policy().weights,
)
WAIVED = {"HC7", "HC8", "HC11", "HC16", "HC17"}


# ══════════════════════════════════════════════════════════════
#  SCH-01 — الحكمُ وتفسيرُه من مصدرٍ واحد
# ══════════════════════════════════════════════════════════════


@pytest.mark.parametrize("policy", [None, LENIENT], ids=["default", "lenient"])
@pytest.mark.parametrize("scene", SCENES, ids=lambda s: s.__name__)
def test_the_verdict_and_its_reasons_never_disagree(scene, policy):
    """في كلّ خانةٍ ولكلّ مهمّةٍ وتحت كلّ رخصة: صالحةٌ ⇔ لا رمزَ يرفضها.

    والسؤالُ لا يغيّر الشبكة: `slot_violations` يبلغ قيوداً لا يبلغها `is_slot_valid`
    (يقف عند أوّل رفض)، فلو عدّلت إحداها شيئاً لظهر هنا.
    """
    grid, candidates, must = scene()
    if policy is not None:
        grid.policy = policy
    before = snapshot(grid, candidates)
    seen: dict[tuple, set] = {licence: set() for licence in LICENCES}
    for task in candidates:
        for day in DAYS:
            for period in PERIODS:
                for adjacent, dense in LICENCES:
                    codes = slot_violations(grid, day, period, task, adjacent, dense)
                    verdict = is_slot_valid(grid, day, period, task, adjacent, dense)
                    where = (task.class_id, task.subject_id, day, period, adjacent, dense, codes)
                    assert verdict is (codes == []), where
                    assert len(codes) == len(set(codes)), where
                    seen[(adjacent, dense)].update(codes)
    assert snapshot(grid, candidates) == before
    # والمشهدُ ليس فارغاً من المعنى: كلُّ قيدٍ قُصد به رُفضت به خانةٌ فعلاً.
    assert must <= seen[(False, False)], must - seen[(False, False)]
    if scene is scene_empty:
        assert seen[(False, False)] == {"HC4"}
    if policy is LENIENT:
        assert not WAIVED & (seen[(True, False)] | seen[(False, True)])


def test_the_default_policy_waives_nothing_that_cannot_ease():
    """بالسياسة الافتراضيّة لا تُسقط الرخصتان إلّا ما يلين: السابعةُ الثالثة تبقى مرفوضة."""
    grid, _, _ = scene_partial()
    third_seventh = lesson("c-4", "s-sci", "t-1", weekly=4)
    for adjacent, dense in LICENCES:
        assert "HC8" in slot_violations(grid, 3, 7, third_seventh, adjacent, dense)


def test_every_refusal_is_named_not_only_the_first():
    """خانةٌ يرفضها قيدان — معلّمٌ مشغولٌ وحصّةٌ ثانيةٌ للمادّة في يومها — تُقال بهما."""
    grid = ScheduleGrid()
    maths = [lesson("c-1") for _ in range(5)]
    grid.place(0, 1, maths[0])
    grid.place(0, 3, lesson("c-2", "s-sci", "t-1", weekly=4))

    assert slot_violations(grid, 0, 3, maths[1]) == ["HC1", "HC6"]
    assert is_slot_valid(grid, 0, 3, maths[1]) is False
    # الرخصةُ لا تُسقط القسمةَ ولا النواةَ: توزيعُ المادّة لا يُكسَر البتّة (قرارُ المالك D-17).
    assert slot_violations(grid, 0, 3, maths[1], allow_dense=True) == ["HC1", "HC6"]
    assert slot_violations(grid, 0, 5, maths[1], allow_dense=True) == ["HC6"]


# ══════════════════════════════════════════════════════════════
#  SCH-02 — المدقّق
# ══════════════════════════════════════════════════════════════

#: رياضياتُ 9/1 كما وُجدت في الجدول المعتمد: حصّتان يومَ الأحد ولا شيءَ يومَ الخميس.
#: والخاناتُ متباعدةٌ عمداً ليبقى الحكمُ للقسمة وحدَها (لا تلاصق ولا تكرار موضع).
SUNDAY_TWICE = [(0, 2), (0, 5), (1, 3), (2, 4), (3, 6)]


def maths_week(cells=SUNDAY_TWICE):
    grid = ScheduleGrid()
    tasks = [
        lesson("9/1", "s-mat", "t-1", subject_name="الرياضيات", teacher_name="معلّم الرياضيات")
        for _ in cells
    ]
    for task, (day, period) in zip(tasks, cells, strict=True):
        grid.place(day, period, task)
    return grid, tasks


def test_two_lessons_on_one_day_are_one_breach_not_two():
    """الحصّتان كلتاهما ترفضهما الخانة، والمخالفةُ واحدة: (الشعبة · المادّة · اليوم)."""
    grid, tasks = maths_week()

    assert [b.code for b in task_breaches(grid, tasks[0])] == ["HC6"]
    assert [b.code for b in task_breaches(grid, tasks[1])] == ["HC6"]
    assert [b.code for b in task_breaches(grid, tasks[2])] == []

    breaches = grid_breaches(grid, tasks)
    assert [b.key for b in breaches] == [("HC6", "9/1", "s-mat", 0)]
    assert (breaches[0].day, breaches[0].period) == (0, 2)


def test_moving_one_lesson_to_the_empty_day_clears_the_week():
    """النقلةُ التي يُفترض أن يجدها السداد: حصّةُ الأحد الثانية إلى الخميس."""
    grid, tasks = maths_week()
    grid.remove("9/1", 0, 5)
    grid.place(4, 5, tasks[1])

    assert grid_breaches(grid, tasks) == []


def test_a_clean_week_with_doubles_and_split_lessons_has_no_breach():
    grid, tasks = maths_week([(0, 2), (1, 3), (2, 4), (3, 5), (4, 1)])
    art = lesson("9/1", "s-art", "t-2", weekly=2, span=2, double=True)
    pairs = [split("9/2", ("t-3", "s-chem"), ("t-4", "s-bio")) for _ in range(2)]
    grid.place(1, 5, art)
    grid.place(0, 1, pairs[0])
    grid.place(2, 3, pairs[1])

    assert grid_breaches(grid, [*tasks, art, *pairs]) == []


def test_the_audit_leaves_the_grid_exactly_as_it_found_it():
    """كلُّ حصّةٍ تُرفع وتُسأل ثمّ تُعاد — والشبكةُ بعد التدقيق هي هي قبله."""
    grid, tasks = maths_week()
    art = lesson("9/1", "s-art", "t-2", weekly=2, span=2, double=True)
    pair = split("9/2", ("t-3", "s-chem"), ("t-4", "s-bio"))
    grid.place(1, 5, art)
    grid.place(0, 4, pair)
    everything = [*tasks, art, pair]
    before = snapshot(grid, everything)

    assert grid_breaches(grid, everything, {("t-4", 0, 4)})
    assert snapshot(grid, everything) == before
    # والإطارُ يُغلق: لا سجلَّ تراجعٍ مفتوحاً يبتلع حركةً لاحقة.
    assert grid.touched() == []


def test_the_audit_grants_no_licence_whatever_the_policy():
    """المدقّقُ صارمٌ ولو كانت سياسةُ العام تكسر القسمةَ في الرخصة الأولى."""
    grid, tasks = maths_week()
    grid.policy = LENIENT

    assert [b.key for b in grid_breaches(grid, tasks)] == [("HC6", "9/1", "s-mat", 0)]


def test_a_lesson_in_an_exempt_cell_is_named_ex():
    """التفريغُ قرارٌ إداريّ لا قيدٌ في المحرّك — فيُقال `EX`، والمزدوجةُ بخانتيها."""
    grid = ScheduleGrid()
    single = lesson("c-1", "s-mat", "t-1")
    double = lesson("c-2", "s-art", "t-2", weekly=2, span=2, double=True)
    grid.place(1, 2, single)
    grid.place(2, 3, double)  # الخانتان 3 و4
    blocked = {("t-1", 1, 2), ("t-2", 2, 4), ("t-2", 3, 3)}

    found = [
        (b.code, b.class_name, b.day, b.period)
        for b in grid_breaches(grid, [single, double], blocked)
    ]
    assert found == [(EXEMPTION, "c-1", 1, 2), (EXEMPTION, "c-2", 2, 3)]
    assert grid_breaches(grid, [single, double]) == []


def test_an_unplaced_task_has_nothing_to_audit():
    grid, _ = maths_week()
    assert task_breaches(grid, lesson("9/1")) == []


def test_the_summary_is_what_the_generation_snapshot_stores():
    grid, tasks = maths_week()
    data = summary(grid_breaches(grid, tasks, {("t-1", 1, 3)}))

    assert data["count"] == 2
    assert data["by_code"] == {EXEMPTION: 1, "HC6": 1}
    assert [item["code"] for item in data["items"]] == [EXEMPTION, "HC6"]
    for item in data["items"]:
        assert set(item) == {"code", "class", "subject", "teacher", "day", "period"}
    assert data["items"][1] == {
        "code": "HC6",
        "class": "9/1",
        "subject": "الرياضيات",
        "teacher": "معلّم الرياضيات",
        "day": 0,
        "period": 2,
    }
    # يُحفظ في `config_snapshot` (JSON) — فلا يحمل ما لا يُسلسَل.
    assert json.loads(json.dumps(data, ensure_ascii=False)) == data
    assert summary([]) == {"count": 0, "by_code": {}, "items": []}


# ══════════════════════════════════════════════════════════════
#  HC14 وHC16B بعد اكتمال الجدول
# ══════════════════════════════════════════════════════════════
#
#  كلاهما احتياطٌ وقتَ البناء: يُعدّ ما سيبقى للمعلّم فيُرفض ما يستهلك حصّةً كان يومٌ
#  فارغٌ أو يومٌ دون الحدّ أولى بها. وفي شبكةٍ كاملةٍ «الباقي» صفرٌ بعد رفع الحصّة
#  المسؤول عنها، فيصير الاحتياطُ حكماً على الحال نفسِها:
#
#      HC14   ⇔ للمعلّم يومٌ متاحٌ فارغٌ غيرُ يوم هذه الحصّة   (ومن مواضعُه دون أيّامه معفى)
#      HC16B  ⇔ للمعلّم يومٌ متاحٌ دون ⌊النصاب ÷ الأيّام⌋      (ولا إعفاء)
#
#  والأوّلُ دقيق. والثاني بلا إعفاء الأوّل: من مواضعُه دون أيّامه لا يبلغ الحدَّ في أيّ
#  جدول، فيُبلَّغ عنه في كلّ جدولٍ صحيح — انظر الثغرتين الموسومتين أدناه.


def test_an_empty_day_is_one_breach_for_the_teacher_not_one_per_lesson():
    tasks = [lesson(f"c-{k}", "s-geo", "t-1", weekly=1) for k in range(8)]
    grid = ScheduleGrid(coverage=_day_coverage(tasks, set()))
    cells = [(0, 1), (0, 3), (1, 1), (1, 3), (2, 1), (2, 3), (3, 1), (3, 3)]
    for task, (day, period) in zip(tasks, cells, strict=True):
        grid.place(day, period, task)

    assert [b.key for b in grid_breaches(grid, tasks)] == [
        ("HC14", ("t-1",)),
        ("HC16B", ("t-1",)),
    ]

    grid.remove("c-7", 3, 3)
    grid.place(4, 2, tasks[7])
    assert grid_breaches(grid, tasks) == []


def test_a_teacher_with_fewer_lessons_than_days_may_keep_a_day_free():
    """منسّقٌ بأربع حصص: يومٌ فارغٌ ضرورةٌ لا مخالفة، والحدُّ الأدنى صفر."""
    tasks = [lesson(f"c-{k}", "s-geo", "t-1", weekly=1) for k in range(4)]
    grid = ScheduleGrid(coverage=_day_coverage(tasks, set()))
    for task, day in zip(tasks, range(4), strict=True):
        grid.place(day, 2, task)

    assert grid_breaches(grid, tasks) == []


def three_doubles():
    """معلّمُ فنونٍ بثلاث شُعبٍ مزدوجة: ستُّ حصصٍ في ثلاثة مواضع — لا تغطّي خمسة أيّام."""
    doubles = [lesson(f"c-{k}", "s-art", "t-art", weekly=2, span=2, double=True) for k in range(3)]
    grid = ScheduleGrid(coverage=_day_coverage(doubles, set()))
    return grid, doubles


def test_three_doubles_on_three_days_are_not_a_breach():
    grid, doubles = three_doubles()
    for task, day in zip(doubles, range(3), strict=True):
        grid.place(day, 2, task)
    # التغطيةُ تعفيه صراحةً (ثلاثةُ مواضع < خمسة أيّام) — والحدُّ الأدنى يعفيه كذلك.
    assert grid.coverage["t-art"] == (3, 6, frozenset(DAYS))

    assert grid_breaches(grid, doubles) == []


def test_the_second_double_needs_no_last_resort():
    grid, doubles = three_doubles()
    grid.place(0, 2, doubles[0])

    assert any(is_slot_valid(grid, d, p, doubles[1]) for d in (1, 2, 3, 4) for p in (1, 2, 4, 5))


# ══════════════════════════════════════════════════════════════
#  ثغراتٌ معروفة — كلٌّ يصف ما ينبغي، ويسقط وسمُه حين تُصلَح
# ══════════════════════════════════════════════════════════════


@pytest.mark.xfail(
    strict=True,
    reason="`_key` يأخذ `task.teacher_id` (رأس المنقسمة) لا العضوَ الذي كسر القيد",
)
def test_a_teacher_breach_names_the_member_who_breaks_it():
    """معلّمُ الأحياء يتلاصق بين نصف شعبةٍ منقسمةٍ وشعبةٍ أخرى — المخالفةُ له وحدَه.

    واليوم تُعَدّ مرّتين: مرّةً باسمه من حصّته هو، ومرّةً باسم معلّم الكيمياء
    (رأس المنقسمة) الذي لا تلاصقَ له.
    """
    pair = split("c-1", ("t-a", "s-chem"), ("t-b", "s-bio"), weekly=1)
    own = lesson("c-2", "s-bio", "t-b", weekly=1)
    grid = ScheduleGrid()
    grid.place(0, 2, pair)
    grid.place(0, 3, own)

    assert [b.key for b in grid_breaches(grid, [pair, own])] == [("HC5", "t-b", 0)]


@pytest.mark.xfail(
    strict=True,
    reason="الشبكةُ تحفظ ساكناً واحداً لكلّ (معلّم·يوم·حصّة)، فرفعُ أحد الحجزين يمحو الآخر",
)
def test_a_teacher_booked_twice_in_one_cell_is_reported():
    """`load_grid` يضع ما في القاعدة بلا تحقّق — فحجزٌ مزدوجٌ هناك يجب أن يُرى هنا."""
    first = lesson("c-1", "s-mat", "t-1", weekly=1)
    second = lesson("c-2", "s-mat", "t-1", weekly=1)
    grid = ScheduleGrid()
    grid.place(0, 3, first)
    grid.place(0, 3, second)

    assert "HC1" in {b.code for b in grid_breaches(grid, [first, second])}


@pytest.mark.xfail(
    strict=True,
    reason="HC1 في `_refusals` يسأل عن `task.teacher_id` وحدَه لا عن أعضاء المنقسمة",
)
def test_hc1_asks_every_member_of_a_split_lesson():
    """المولّدُ يحرس العضوَ الثاني بفحصٍ منفصل — و`slot_violations` وحدَه لا يراه."""
    grid = ScheduleGrid()
    grid.place(0, 3, lesson("c-9", "s-mat", "t-b"))
    pair = split("c-2", ("t-a", "s-chem"), ("t-b", "s-bio"))

    assert "HC1" in slot_violations(grid, 0, 3, pair)


@pytest.mark.xfail(
    strict=True,
    reason="مفتاحُ HC9 الحصّةُ (شعبة·يوم·حصّة) لا المورد — فالحجزُ الزائد يُعدّ بعدد ساكنيه",
)
def test_an_overbooked_resource_is_one_breach():
    gym = ("r-gym", 1, False)
    first = lesson("c-1", "s-pe", "t-1", weekly=2, resources=[gym])
    second = lesson("c-2", "s-pe", "t-2", weekly=2, resources=[gym])
    grid = ScheduleGrid()
    grid.place(1, 4, first)
    grid.place(1, 4, second)

    assert [b.code for b in grid_breaches(grid, [first, second])] == ["HC9"]

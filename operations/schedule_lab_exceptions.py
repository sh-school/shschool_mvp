"""تركّزُ الاستثناءات في الجدول (SCH-10) — أكثرُ ما يقع منها على جهةٍ واحدة.

الاستثناءُ هنا ما بقي للمولّد أن يكسره بعد قرار المالك 2026-09-24 (D-17): مهمّتان متّصلتان
لمعلّمٍ فوق سقفه في يومه، وحصّتان متّصلتان لمادّةٍ في شعبةٍ في يوم. وكلاهما يُعَدّ بموضوعه: يومٌ
للمعلّم، ويومٌ للمادّة في الشعبة. أمّا توزيعُ المادّة على الأيّام (HC6) فلا رخصةَ له، فلا يدخل.

**المهمّةُ لا الحصّة:** الحصّةُ المزدوجةُ المطلوبةُ (التربية الفنّية والمختبرات) حصّتان متّصلتان
عمداً، ومهمّةٌ واحدة — كما يحكم `HC5` في المولّد. فمعلّمُ فنّيةٍ كلُّ أيّامه مزدوجةٌ لا يحمل
استثناءً. وكان `teacher.run_breaches` يعدّ حصصَ اليوم فيرى المزدوجةَ تتابعاً (SCH-19) — فصار
يقيس بـ`longest_task_run` من هنا: المؤشّران يتّفقان على ما هو استثناء.

وعلّةُ المؤشّر أنّ **العددَ الكلّيّ يخفي التركّز**: سبعُ مخالفاتٍ موزّعةٌ على سبعةِ معلّمين غيرُ
سبعٍ على معلّمٍ واحد. وقد كانت اثنتا عشرةَ مخالفةً في الجدول المعتمد في 2026-09-24 أربعٌ منها
على شعبةٍ واحدة (9/1) فلم يُرَ ذلك حتى طُبعت ورقةُ معلّمٍ فيها حصّتا رياضيات في يومٍ واحد.

عرضٌ لا حكم (`info`): لا يدخل الدرجةَ التي تقود المولّدَ ولا يُحسب في `grid_lab_score`، فلا
يغيّر جدولاً ولا يكلّف محاولة. وتُقرَّر ترقيتُه حكماً بعد أن يُقاس على أساسٍ معتمَد.

وحدةٌ منفصلةٌ عن `schedule_lab` لأنّ ملفَّ المختبر بلغ حدَّ الحجم (1000 سطر)؛ وهو لا يستورد
منها شيئاً غيرَ الدالّة، وهي لا تستورد منه إلّا الأنواع.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from .scheduler_bell import are_joined

if TYPE_CHECKING:
    from .schedule_lab import ScheduleLab

#: عناوينُ تفصيلٍ تُقرأ في شاشة المختبر والأمر.
TEACHER_DAYS = "أيّامُ معلّمين فيها استثناء"
CLASS_DAYS = "أيّامُ موادَّ في شعبٍ فيها استثناء"


def _worst(counts: dict[str, int], names: dict[str, str]) -> dict[str, int]:
    """أثقلُ ثلاثةٍ تحمّلاً — بترتيبٍ ثابتٍ عند التساوي (بالاسم) فلا يتبدّل بين قياسَين."""
    top = sorted(counts.items(), key=lambda kv: (-kv[1], names.get(kv[0], kv[0])))[:3]
    return {names.get(key, key): n for key, n in top if n}


def second_halves(lab: ScheduleLab) -> dict[tuple[str, int], set[int]]:
    """(معلّم، يوم) ← الحصصُ التي هي النصفُ الثاني من مزدوجةٍ مطلوبة — لا تُعدّ مهمّةً ثانية.

    النصفُ الثاني هو الحصّةُ التي تلي مباشرةً حصّةً من المزدوجة نفسِها (المعلّم والشعبة والمادّة)
    لا مجرّدَ ثاني ما وُجد: مزدوجةٌ مفكوكةٌ إلى حصّتين متباعدتين لا نصفَ ثانيَ فيها. وتُحفظ على
    المختبر فتُحسب مرّةً لكلّ قياس — فالدالّةُ تُنادى لكلّ نقلةٍ يجرّبها المحسِّن.
    """
    if lab.halves is not None:
        return lab.halves
    periods: dict[tuple[str, int, str, str], set[int]] = defaultdict(set)
    for s in lab.slots:
        if s.requires_double:
            periods[(s.teacher_id, s.day, s.class_id, s.subject_id)].add(s.period)
    halves: dict[tuple[str, int], set[int]] = defaultdict(set)
    for (tid, day, _class, _subject), found in periods.items():
        seconds = halves[(tid, day)]
        before = 0
        for period in sorted(found):
            if period == before + 1 and before not in seconds:
                seconds.add(period)
            before = period
    lab.halves = halves
    return halves


def longest_task_run(lab: ScheduleLab, tid: str, day: int) -> int:
    """أطولُ تتابعٍ متّصلٍ بالساعة لمهامّ معلّمٍ في يومه — المزدوجةُ مهمّةٌ واحدة (SCH-19)."""
    halves = second_halves(lab).get((tid, day), set())
    best = run = 0
    before: tuple[int, str] | None = None
    for period, band in sorted(set(lab.by_teacher_day_bands[tid][day])):
        joined = (
            before is not None
            and period == before[0] + 1
            and are_joined(lab.interval(before[1], day, before[0]), lab.interval(band, day, period))
        )
        unit = 0 if period in halves else 1
        run = run + unit if joined else unit
        best = max(best, run)
        before = (period, band)
    return best


def exception_load(lab: ScheduleLab) -> dict:
    """`{"value": الأكبرُ من الجهتين، "detail": مجموعاتُ الأيّام وأثقلُ المتحمّلين}`."""
    teacher_days: dict[str, int] = defaultdict(int)
    for tid, days in lab.by_teacher_day.items():
        cap = lab.run_cap(tid)
        teacher_days[tid] = sum(1 for day in days if longest_task_run(lab, tid, day) > cap)

    # المزدوجةُ المطلوبةُ حصّتان متّصلتان عمداً، والمنقسمةُ معلّمان في الحصّة نفسِها لا تجاور.
    cells: dict[tuple[str, str, int], list[tuple[int, str]]] = defaultdict(list)
    class_names: dict[str, str] = {}
    for s in lab.slots:
        if s.requires_double or s.elective_group:
            continue
        cells[(s.class_id, s.subject_id, s.day)].append((s.period, s.band_id))
        class_names[s.class_id] = s.class_name
    class_days: dict[str, int] = defaultdict(int)
    for (class_id, _subject, day), items in cells.items():
        if lab.clock_run(items, day) > 1:
            class_days[class_id] += 1

    return {
        "value": max(max(teacher_days.values(), default=0), max(class_days.values(), default=0)),
        "detail": {
            TEACHER_DAYS: sum(teacher_days.values()),
            CLASS_DAYS: sum(class_days.values()),
            **{f"معلّم — {name}": n for name, n in _worst(teacher_days, lab.names).items()},
            **{f"شعبة — {name}": n for name, n in _worst(class_days, class_names).items()},
        },
    }

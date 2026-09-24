"""operations/services/schedule_read.py — قراءةُ الجدول: مصفوفاتُ المعلّمين والصفوف والصفحات والتعارضات.

مقطعٌ من `ScheduleService` (البند 8، الخطوة 2): يُركَّب في `schedule.py`.
"""

from __future__ import annotations

import logging
from collections import Counter
from itertools import groupby
from typing import TYPE_CHECKING

from django.db.models import Count

from core.academic_calendar import (
    academic_year_for_school,
)
from core.models.academic import grade_order
from operations.departments import (
    attached_specialty,
    derived_department,
    registered_departments,
    school_department_codes,
)
from operations.models import (
    ScheduleSlot,
    SubjectClassAssignment,
    TimeSlotConfig,
)
from operations.schedule_paper import colored_exemptions_by_teacher

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.models import ClassGroup, CustomUser, School


# ─────────────────────────────────────────────
# المرحلة 2 — الجداول الذكية + نظام البديل
# ─────────────────────────────────────────────


def parallel_labels(school, academic_year, generation=None) -> dict:
    """(شعبة · يوم · حصّة) → اسمُ ما يُدرَّس في الخانة المشتركة.

    الشعبةُ المقسومةُ نصفين لها صفّان في الخانة الواحدة، وجدولُ المعلّم
    يُصفّى على حصصه وحدَه فيرى نصفَه ولا يعلم أنّ الخانة مشتركة. فيُكتب في
    خانته ما يُدرَّس فيها كلُّه: «التكنولوجيا / الفنون البصرية» حين تختلف
    المادّتان، واسمُها مرّةً واحدة حين تتّحدان — قرارُ المستخدم 2026-09-07.

    واستعلامٌ واحدٌ صغير: الخاناتُ المشتركةُ في المدرسة كلِّها ستَّ عشرةَ
    صفّاً، فلا تُسأل القاعدةُ عن كلّ خانةٍ على حدة.
    """
    rows = ScheduleSlot.objects.filter(school=school, academic_year=academic_year).exclude(
        elective_group=""
    )
    rows = (
        rows.filter(generation=generation)
        if generation is not None
        else rows.filter(is_active=True)
    )
    cells: dict = {}
    for row in rows.select_related("subject").order_by("elective_group"):
        key = (row.class_group_id, row.day_of_week, row.period_number)
        name = row.subject.name_ar if row.subject else ""
        names = cells.setdefault(key, [])
        if name and name not in names:
            names.append(name)
    return {key: " / ".join(names) for key, names in cells.items() if names}


class ScheduleReadMixin:
    @staticmethod
    def period_times(
        school: School, academic_year: str | None = None, band=None, day_type: str = "regular"
    ) -> dict:
        """توقيت كل حصة — {رقم: (بداية، نهاية)} — لنطاقٍ ونوعِ يوم.

        المصدر الأوّل `TimeSlotConfig`، فهو ما تُعلنه المدرسة: جرسُ النطاق
        ليومه، ثمّ جرسُ المدرسة الافتراضيّ (بلا نطاق) ليومه، ثمّ جرسُ
        الأحد–الأربعاء. فإن لم تُعلن المدرسةُ جرساً اشتُقّ من الحصص نفسها
        بالأكثر شيوعاً لكلّ رقمٍ في أيّام ذلك النوع — لا من رقمٍ مكتوبٍ في
        الشيفرة يصير كذبةً يوم تُغيّر المدرسة توقيتها.
        """
        from collections import Counter

        academic_year = academic_year or academic_year_for_school(school)
        candidates = [(band, day_type), (None, day_type)]
        if day_type != "regular":
            candidates += [(band, "regular"), (None, "regular")]
        seen: set = set()
        for wanted_band, kind in candidates:
            if (wanted_band, kind) in seen:
                continue
            seen.add((wanted_band, kind))
            rows = TimeSlotConfig.objects.filter(school=school, day_type=kind, is_break=False)
            rows = rows.filter(band=wanted_band) if wanted_band else rows.filter(band__isnull=True)
            times = {r.period_number: (r.start_time, r.end_time) for r in rows}
            if times:
                return times

        tally: dict[int, Counter] = {}
        slots = ScheduleSlot.objects.filter(
            school=school, academic_year=academic_year, is_active=True
        )
        slots = (
            slots.filter(day_of_week=4) if day_type == "thursday" else slots.exclude(day_of_week=4)
        )
        for period, start, end in slots.values_list("period_number", "start_time", "end_time"):
            tally.setdefault(period, Counter())[(start, end)] += 1
        return {p: c.most_common(1)[0][0] for p, c in tally.items()}

    @staticmethod
    def get_weekly_schedule(
        school: School,
        teacher: CustomUser | None = None,
        class_group: ClassGroup | None = None,
        academic_year: str | None = None,
        generation=None,
    ) -> dict:
        """إرجاع الجدول الأسبوعي مرتّباً حسب اليوم والحصة.

        الشكل واحدٌ في كل الأحوال: `{يوم: {حصة: [slot, ...]}}`.

        و`generation` يُعاين مسودّةً بعينها بدل الجدول الحيّ: حصصُها مطفأةٌ
        حتّى تُعتمد فلا يجدها فلترُ `is_active` — ومن يعتمد جدولاً لم يرَه
        يعتمد رقماً لا جدولاً.

        وكان يُعيد حصّةً مفردة مع فلتر المعلّم أو الفصل، وقائمةً بلا فلتر.
        والشعبة **تكون** في حصّتين معاً حين يتفرّق طلابها بين مادّتين
        اختياريّتين في التوقيت نفسه، فكانت الثانية تُكتب فوق الأولى في
        القاموس وتختفي صامتة.

        ونوعُ الإرجاع المتبدّل فخٌّ في ذاته: قالبٌ يقرأ `slot.subject` من
        قائمةٍ لا يُخطئ — يطبع فراغاً. فوُحِّد الشكل.
        """
        academic_year = academic_year or academic_year_for_school(school)
        qs = ScheduleSlot.objects.filter(school=school, academic_year=academic_year)
        if generation is not None:
            qs = qs.filter(generation=generation)
        else:
            qs = qs.filter(is_active=True)
        # وداخلَ الخانة الواحدة ترتيبُ المدرسة: من 7/1 إلى 12/4. فخانةُ العرض
        # العامّ تحمل شعبَ المدرسة كلَّها، وبلا ترتيبٍ صريحٍ يُخرجها المحرّك
        # كيف اتّفق — فلا يجد القارئُ شعبتَه إلّا بمسحِ خمسٍ وعشرين بطاقة.
        qs = qs.select_related("teacher", "class_group", "subject").order_by(
            grade_order("class_group__grade"), "class_group__section"
        )
        if teacher:
            qs = qs.filter(teacher=teacher)
        if class_group:
            qs = qs.filter(class_group=class_group)

        grid: dict = {d: {} for d in range(5)}  # 0=أحد … 4=خميس
        # في جدول المعلّم تُكتب الخانةُ المشتركةُ بما فيها كلِّه؛ وفي جدول
        # الشعبة صفّاها حاضران أصلاً فلكلٍّ اسمُ مادّته ومعلّمه.
        labels = parallel_labels(school, academic_year, generation) if teacher else None
        for slot in qs:
            if labels is not None:
                slot.cell_subject = labels.get(
                    (slot.class_group_id, slot.day_of_week, slot.period_number), ""
                )
            grid[slot.day_of_week].setdefault(slot.period_number, []).append(slot)
        return grid

    @classmethod
    def get_teachers_matrix(
        cls, school: School, academic_year: str | None = None, generation=None
    ) -> list[dict]:
        """الجدول العام: صفٌّ لكل معلّم، وخمسةُ أيامٍ في كلٍّ منها سبعُ حصص.

        هذه صيغةُ ورقة «الجدول العام للمعلمين» التي تُعلَّق في المدرسة:
        المعلّمون سطوراً، والأسبوعُ كلُّه عرضاً، وفي الخانة رمزُ الشعبة
        وحده — لأنّ خانةً عرضُها سنتيمترٌ لا تحتمل اسم مادّةٍ ولا معلّم.

        والمعلّمُ بلا حصّةٍ لا سطر له: سطرٌ فارغٌ في ورقةٍ من ستّين سطراً
        يأكل مساحةً ولا يُفيد قارئه.

        والسطورُ مرتّبةٌ بالقسم الأكاديميّ ثمّ بالاسم — فالورقةُ تُقرأ قسماً
        قسماً، ومن أراد نصاب قسمٍ وجد معلّميه متجاورين. والقسمُ مشتقٌّ من
        الحصص نفسها، انظر `operations.departments`.

        الشكل: `[{"teacher": …, "days": [[خانة × ٧] × ٥], "total": عدد,
        "department": {رمز، اسم، ترتيب}, "dept_span": امتدادُ خانة القسم}]`
        والخانةُ قائمةٌ لا حصّةٌ مفردة — والقيدُ يمنع تعدُّدها اليوم، فإن
        رُفع غداً ظهر ما فيها بدل أن يُكتب أحدهما فوق الآخر.
        """
        academic_year = academic_year or academic_year_for_school(school)
        # و`generation` يُعاين مسودّةً بدل الجدول الحيّ — كالشبكة سواءً بسواء:
        # الصفحةُ الواحدةُ صارت تعرض الورقتين، فلا تُعاين المسودّةُ في إحداهما
        # ويُعرض الحيُّ في الأخرى باسمها.
        qs = ScheduleSlot.objects.filter(school=school, academic_year=academic_year)
        qs = (
            qs.filter(generation=generation)
            if generation is not None
            else qs.filter(is_active=True)
        )
        slots = qs.select_related("teacher", "class_group", "subject").order_by(
            "teacher__full_name", "day_of_week", "period_number"
        )
        return cls._matrix_rows(school, academic_year, slots, generation)

    @classmethod
    def _matrix_rows(cls, school: School, academic_year: str, slots, generation=None) -> list[dict]:
        """صفوفُ الجدول العام من حصصٍ بشكل الخانة، مرتّبةً بالمعلّم فاليوم فالحصّة.

        مشتركةٌ بين الخطّة (`ScheduleSlot`) والأسبوع الفعليّ (`Session`، `get_week_matrix`): الورقةُ
        واحدةٌ ومصدرُها يتبدّل — فلا يُكتب بناؤها مرّتين.
        """
        labels = parallel_labels(school, academic_year, generation)

        rows: dict = {}
        for slot in slots:
            row = rows.get(slot.teacher_id)
            if row is None:
                row = rows[slot.teacher_id] = {
                    "teacher": slot.teacher,
                    "days": [[[] for _ in range(7)] for _ in range(5)],
                    "total": 0,
                    "lessons": [],
                }

            subject_name = slot.subject.name_ar if slot.subject else ""
            slot.cell_subject = labels.get(
                (slot.class_group_id, slot.day_of_week, slot.period_number), ""
            )
            row["lessons"].append((subject_name, slot.class_group.grade, 1))
            # الحصص من ١ إلى ٧، والفهرسُ من صفر. وحصّةٌ خارج المدى بيانٌ
            # معطوب لا سببَ لإسقاط الورقة كلّها من أجله.
            if 1 <= slot.period_number <= 7 and 0 <= slot.day_of_week <= 4:
                row["days"][slot.day_of_week][slot.period_number - 1].append(slot)
                row["total"] += 1

        # السجلُّ أوّلاً — والاشتقاقُ احتياطُ من لا قسمَ مسجّلاً له.
        registry = registered_departments(school)
        # ومن أُلحق إدارياً بقسمٍ غيرِ تخصّصه يُذكر تخصّصُه بجانب اسمه، وإلّا
        # قُرئ من أهل القسم الذي أُلحق به. والرموزُ تُجلب مرّةً لا لكلّ معلّم.
        codes = school_department_codes(school)
        # نقطةُ لونٍ صغيرةٌ لا خلفيّةَ خليّة — السطرُ مُلوَّنٌ بقسمه أصلاً، فلا
        # تُضاف خلفيّةٌ ثانيةٌ تتصادم معها (قرارُ 2026-09-18). واستعلامٌ واحدٌ
        # للمدرسة كلِّها لا واحدٌ لكلّ معلّم.
        exemptions = colored_exemptions_by_teacher(school, academic_year)
        for teacher_id, row in rows.items():
            lessons = row.pop("lessons")
            registered = registry.get(str(teacher_id))
            row["department"] = registered or derived_department(lessons)
            row["specialty"] = attached_specialty(
                registered["code"] if registered else "", lessons, codes
            )
            row["exempt_map"] = exemptions.get(teacher_id, {})

        # الاسمُ في المفتاح لأنّ `sort_order` قد يتساوى بين قسمين، فلولاه
        # تشابكت صفوفُ القسمين وانكسر عمودُ القسم الممتدّ.
        ordered = sorted(
            rows.values(),
            key=lambda r: (
                r["department"]["order"],
                r["department"]["name"],
                r["teacher"].full_name or "",
            ),
        )

        # عمودُ القسم خانةٌ واحدةٌ ممتدّةٌ على سطور معلّميه: `dept_span` عددُ
        # السطور لأوّلِ معلّمي القسم وصفرٌ لمن بعده. والاسمُ يُكتب مرّةً لا في
        # كلِّ سطر — فتكرارُه ثلاثاً وسبعين مرّةً يأكل من عرض الورقة ولا يزيد
        # قارئها علماً. والسطورُ مرتّبةٌ بالقسم قبلَه، فالمجموعةُ متّصلة.
        for _, group in groupby(ordered, key=lambda r: r["department"]["code"]):
            members = list(group)
            members[0]["dept_span"] = len(members)
            for row in members[1:]:
                row["dept_span"] = 0

        return ordered

    @staticmethod
    def _by_day(days: list) -> list:
        """سطرٌ لكلّ يومٍ باسمه وخاناتِه السبع — شكلُ الورقة المفردة.

        السطرُ يومٌ والعمودُ حصّة (قرار 2026-09-08، وكان العكس). والسببُ ليس
        العادةَ بل التوقيت: `period_times` يختلف بالنطاق (الطابق) وبنوع اليوم —
        والخميسُ جرسٌ آخر. فحين كانت الأيّامُ أعمدةً وقع في سطر «الحصة ٣»
        توقيتُ الأحد وتوقيتُ الخميس جنباً إلى جنب. والآن ينتظم لكلّ يومٍ
        توقيتُه على امتداد سطره.

        والاسمُ يُقرن هنا لا في القالب: قوالبُ Django لا تُزاوج قائمتين.
        """
        return [
            {"day": name, "cells": list(cells)}
            for (_num, name), cells in zip(ScheduleSlot.DAYS, days, strict=False)
        ]

    @classmethod
    def teacher_pages(
        cls, school: School, academic_year: str | None = None, *, department=None, teacher_id=None
    ) -> list[dict]:
        """صفحاتُ جداول المعلّمين مرتّبةً بالأقسام — صفحةٌ لكلّ معلّمٍ له حصص.

        القسمُ من السجلّ الإداريّ لا من الموادّ (`registered_departments`)،
        فالورقةُ للمنسّق ورجلٌ ينتقل من قسمٍ إلى قسمٍ لأنّ جدوله تغيّر ورقةٌ لا
        تُصدَّق. ومن لا حصّةَ له لا صفحةَ له — ورقةٌ فارغةٌ لا تنفع أحداً.
        """
        rows = cls.get_teachers_matrix(school, academic_year)
        if teacher_id:
            rows = [r for r in rows if str(r["teacher"].id) == str(teacher_id)]
        elif department:
            rows = [r for r in rows if r["department"]["code"] == department]
        from operations.schedule_paper import (
            annotate_teacher_exemptions,
            bell_tables,
            teacher_bands_by_day,
            week_layout,
        )

        tables, band_codes = bell_tables(school), cls._band_codes(school)
        for row in rows:
            row["by_day"] = cls._by_day(row["days"])
            # الفسحةُ والصلاةُ بين الحصص — من أجراس شُعب المعلّم في كلّ يوم،
            # والجرسان كاملان لمن يدرّس في طابقين (قرار 2026-09-14).
            row["week"] = week_layout(
                row["days"], teacher_bands_by_day(row["days"], band_codes), tables
            )
            # `exempt_map` محسوبٌ أصلاً في `get_teachers_matrix` — لا استعلامَ ثانٍ.
            if row.get("exempt_map"):
                annotate_teacher_exemptions(row["week"], row["exempt_map"])
        return rows

    @staticmethod
    def _band_codes(school: School) -> dict:
        """معرّفُ الجرس → رمزُه: الحصّةُ تحمل `time_band_id` شعبتها، والأجراسُ برموزها."""
        from core.models.academic import TimeBand

        return dict(TimeBand.objects.filter(school=school).values_list("id", "code"))

    @classmethod
    def department_options(cls, school: School, academic_year: str | None = None) -> list[dict]:
        """الأقسامُ التي فيها معلّمون مجدولون — للقائمة المنسدلة، بترتيب الورقة.

        من الجدول نفسه لا من جدول الأقسام وحده: قسمٌ مسجّلٌ بلا معلّمٍ مجدولٍ
        خيارٌ يفتح ورقةً فارغة، وقسمٌ مشتقٌّ لمن لا سجلَّ له لا يظهر في السجلّ.
        """
        seen: dict[str, dict] = {}
        for row in cls.get_teachers_matrix(school, academic_year):
            info = row["department"]
            seen.setdefault(
                info["code"], {"code": info["code"], "name": info["name"], "order": info["order"]}
            )
        return sorted(seen.values(), key=lambda d: (d["order"], d["name"]))

    @classmethod
    def class_pages(cls, school: School, academic_year: str | None = None) -> list[dict]:
        """صفحةٌ لكلّ شعبة بترتيب المدرسة: من 7/1 إلى 12/4 — وفي الخانة المادّةُ والمعلّم."""
        academic_year = academic_year or academic_year_for_school(school)
        slots = (
            ScheduleSlot.objects.filter(school=school, academic_year=academic_year, is_active=True)
            .select_related("teacher", "class_group", "subject")
            .order_by(grade_order("class_group__grade"), "class_group__section")
        )
        rows: dict = {}
        for slot in slots:
            row = rows.get(slot.class_group_id)
            if row is None:
                row = rows[slot.class_group_id] = {
                    "class_group": slot.class_group,
                    "days": [[[] for _ in range(7)] for _ in range(5)],
                    "total": 0,
                }
            if 1 <= slot.period_number <= 7 and 0 <= slot.day_of_week <= 4:
                row["days"][slot.day_of_week][slot.period_number - 1].append(slot)
                row["total"] += 1
        pages = list(rows.values())
        from operations.schedule_paper import bell_tables, week_layout

        tables, band_codes = bell_tables(school), cls._band_codes(school)
        for row in pages:
            row["by_day"] = cls._by_day(row["days"])
            band = band_codes.get(row["class_group"].time_band_id)
            # جرسُ الشعبة واحدٌ كلَّ الأسبوع، وموضعُ استراحته يتبدّل يومَ الخميس.
            row["week"] = week_layout(row["days"], [[band] if band else []] * 5, tables)
        return pages

    @classmethod
    def matrix_totals(
        cls, rows: list[dict], school: School, academic_year: str | None = None
    ) -> dict:
        """مجموعُ الحصص أسفل الجدول العام، والمخطَّطُ الذي يُقاس إليه.

        في الخانة الواحدة (يومٌ وحصّة) يُعرض عددُ الحصص المنعقدة. وإلى جانبه
        يُقاس **تغطيةُ الشُّعب** لا عددُ الحصص: كم شعبةً في درسٍ حينها من
        الشُّعب التي تُسمح لها تلك الحصّة.

        والفرقُ بين المقياسين ليس تدقيقاً لفظياً: شعبةٌ ينقسم طلابها بين
        مادّتين اختياريّتين تشغل خانتين في العمود الواحد، فتستر بزيادتها
        شعبةً أخرى بلا درس — فيخرج العمودُ خمسةً وعشرين وفيه ثقب. فقياسُ
        الشُّعب يكشفه وقياسُ الحصص يخفيه.

        والمخطَّطُ في الأسبوع = الخاناتُ المسموحة لكلّ شعبة (`get_max_periods_
        for_day`: أربعٌ وثلاثون للإعدادي وخمسٌ وثلاثون للثانوي) + زيادةُ
        التوازي **من خطّة الإسناد** (`SubjectClassAssignment.parallel_group`)
        لا من الجدول المنفَّذ — وإلّا قِيس الشيءُ بنفسه فوافق دائماً.

        دالّةٌ على المصفوفة القائمة، واستعلامٌ واحدٌ للخطّة.
        """
        from operations.scheduler_constraints import get_max_periods_for_day

        counts = [[0] * 7 for _ in range(5)]
        covered: list[list[set]] = [[set() for _ in range(7)] for _ in range(5)]
        levels: dict = {}
        for row in rows:
            for day_index, day in enumerate(row["days"]):
                for period_index, cell in enumerate(day):
                    counts[day_index][period_index] += len(cell)
                    for slot in cell:
                        levels[slot.class_group_id] = slot.class_group.level_type or ""
                        covered[day_index][period_index].add(slot.class_group_id)

        days = []
        for day_index, day_counts in enumerate(counts):
            columns = []
            for period_index, count in enumerate(day_counts):
                expected = sum(
                    1
                    for level in levels.values()
                    if period_index + 1 <= get_max_periods_for_day(day_index, level)
                )
                sections = len(covered[day_index][period_index])
                columns.append(
                    {
                        "count": count,
                        "sections": sections,
                        "expected": expected,
                        "short": sections < expected,
                    }
                )
            days.append(columns)

        planned_cells = sum(
            sum(get_max_periods_for_day(day, level) for day in range(5))
            for level in levels.values()
        )
        parallel = cls.parallel_extra(school, academic_year, set(levels))
        planned = planned_cells + parallel
        total = sum(row["total"] for row in rows)

        return {
            "days": days,
            "total": total,
            "planned": planned,
            "parallel": parallel,
            "missing": max(planned - total, 0),
            "sections": len(levels),
        }

    @staticmethod
    def parallel_extra(
        school: School, academic_year: str | None = None, class_ids: set | None = None
    ) -> int:
        """الحصصُ الزائدةُ على الخانات بحكم التوازي — من الخطّة لا من الجدول.

        مادّتان في الشعبة الواحدة تحملان وسمَ التوازي نفسه تُدرَّسان في
        التوقيت ذاته لقسمَي الطلاب: الخانةُ واحدةٌ والحصصُ اثنتان. فالزيادةُ
        في المجموعة = مجموعُ حصصها ناقصَ أطولِها.
        """
        academic_year = academic_year or academic_year_for_school(school)
        qs = SubjectClassAssignment.objects.filter(
            school=school, academic_year=academic_year, is_active=True
        ).exclude(parallel_group="")
        if class_ids is not None:
            qs = qs.filter(class_group_id__in=class_ids)

        groups: dict = {}
        for class_id, group, periods in qs.values_list(
            "class_group_id", "parallel_group", "weekly_periods"
        ):
            groups.setdefault((class_id, group), []).append(periods)

        return sum(sum(periods) - max(periods) for periods in groups.values())

    @staticmethod
    def detect_conflicts(school: School, academic_year: str | None = None) -> list:
        """كشف التعارضات في الجدول"""
        academic_year = academic_year or academic_year_for_school(school)
        conflicts: list = []

        # تعارض المعلم: نفس المعلم في نفس اليوم والحصة
        teacher_dups = (
            ScheduleSlot.objects.filter(school=school, academic_year=academic_year, is_active=True)
            .values("teacher", "day_of_week", "period_number")
            .annotate(cnt=Count("id"))
            .filter(cnt__gt=1)
        )
        for dup in teacher_dups:
            slots = (
                ScheduleSlot.objects.live(school, year=academic_year)
                .filter(
                    teacher_id=dup["teacher"],
                    day_of_week=dup["day_of_week"],
                    period_number=dup["period_number"],
                )
                .select_related("teacher", "class_group")
            )
            conflicts.append(
                {
                    "type": "teacher",
                    "message": f"تعارض معلم: {slots[0].teacher.full_name} — {slots[0].day_name} ح{dup['period_number']}",
                    "slots": list(slots),
                }
            )

        # تعارض الفصل: نفس الفصل في نفس اليوم والحصة
        #
        # و`elective_group` جزءٌ من المفتاح: الشعبةُ المنقسمةُ تأخذ مادّتين في
        # التوقيت نفسه لقسمَي طلابها — كالفنون والتكنولوجيا في 11/1 — وذلك
        # توازٍ لا تعارض. وبدونه كان الكشفُ يُنذر بثمانية «تعارضات» كلُّها
        # حصصٌ مقصودةٌ يحرسها القيدُ الفريدُ في القاعدة نفسِها.
        class_dups = (
            ScheduleSlot.objects.filter(school=school, academic_year=academic_year, is_active=True)
            .values("class_group", "day_of_week", "period_number", "elective_group")
            .annotate(cnt=Count("id"))
            .filter(cnt__gt=1)
        )
        for dup in class_dups:
            slots = (
                ScheduleSlot.objects.live(school, year=academic_year)
                .filter(
                    class_group_id=dup["class_group"],
                    day_of_week=dup["day_of_week"],
                    period_number=dup["period_number"],
                    elective_group=dup["elective_group"],
                )
                .select_related("teacher", "class_group")
            )
            conflicts.append(
                {
                    "type": "class",
                    "message": f"تعارض فصل: {slots[0].class_group} — {slots[0].day_name} ح{dup['period_number']}",
                    "slots": list(slots),
                }
            )

        return conflicts

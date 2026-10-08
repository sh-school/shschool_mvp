"""operations/services/schedule_import.py — استيرادُ جدولٍ مولَّدٍ بالمعرّفات إلى مسودّة توليدٍ، ثمّ اعتمادُه من الباب نفسه.

مخرجُ أيّ مولّدٍ (V2 أو غيرُه) صفوفٌ بمعرّفات: (الشعبة، المادّة، المعلّم، اليوم، رقم الحصّة[، مجموعة الاختيار]).
وقتُ كلّ حصّةٍ **لا يأتي من المولّد**: يُشتقّ من جرس نطاق شعبتها ليومها (`scheduler.bell_lookup`) —
الترتيبُ نفسُه الذي يكتب به التوليدُ الحاليّ ويصالح به `resync_slot_times` — فلا يفترق جدولان في الساعة.

`sync_schedule` يطابق بالأسماء وينقل بين قاعدتين؛ وهذا يطابق بالمعرّفات داخل القاعدة نفسِها (D: المعرّفات لا الأسماء).
وكلاهما ينتهي بـ`ScheduleService.approve_generation` — لا مسارَ ثانياً يقلّد الاعتماد.

الفحصُ كلُّه قبل الكتابة: صفٌّ واحدٌ معيبٌ يمنع الباقي (كلُّ شيءٍ أو لا شيء)، والعيبُ يُسمّى بسطره.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from django.db import transaction

from core.models import ClassGroup, School
from operations.models import ScheduleGeneration, ScheduleSlot, SubjectClassAssignment

logger = logging.getLogger(__name__)

_DAYS = {d for d, _ in ScheduleSlot.DAYS}
_PERIODS = set(ScheduleSlot.PERIODS)


class ScheduleImportError(Exception):
    """الصفوفُ معيبة — الرسالةُ تسمّي كلَّ عيبٍ بسطره."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__(
            "؛ ".join(problems[:10])
            + (f" … و{len(problems) - 10} أخرى" if len(problems) > 10 else "")
        )


@dataclass
class ImportReport:
    generation: ScheduleGeneration | None
    rows: int
    problems: list[str] = field(default_factory=list)
    approval: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return not self.problems


def _key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        str(row.get("class_group_id")),
        int(row.get("day", -1)),
        int(row.get("period", -1)),
        row.get("elective_group") or "",
    )


def validate_rows(school: School, year: str, rows: Iterable[Mapping[str, Any]]) -> list[str]:
    """عيوبُ الصفوف بلا كتابة: معرّفٌ مجهول، إسنادٌ غيرُ حيّ، يومٌ/حصّةٌ خارج النطاق، وتضاربُ معلّمٍ أو شعبة."""
    rows = list(rows)
    problems: list[str] = []
    classes = {
        str(pk): band
        for pk, band in ClassGroup.objects.filter(school=school, academic_year=year).values_list(
            "id", "time_band_id"
        )
    }
    assigned = {
        (str(c), str(s), str(t))
        for c, s, t in SubjectClassAssignment.objects.live(school, year=year).values_list(
            "class_group_id", "subject_id", "teacher_id"
        )
    }
    seen_class: set[tuple[Any, ...]] = set()
    seen_teacher: set[tuple[Any, ...]] = set()
    for n, row in enumerate(rows, start=1):
        try:
            day, period = int(row["day"]), int(row["period"])
            cid, sid, tid = (str(row[k]) for k in ("class_group_id", "subject_id", "teacher_id"))
        except (KeyError, TypeError, ValueError):
            problems.append(f"السطر {n}: حقلٌ ناقصٌ أو غيرُ صالح")
            continue
        if day not in _DAYS or period not in _PERIODS:
            problems.append(f"السطر {n}: يومٌ أو حصّةٌ خارج النطاق ({day}/{period})")
        if cid not in classes:
            problems.append(f"السطر {n}: شعبةٌ مجهولةٌ في عام {year}")
        elif (cid, sid, tid) not in assigned:
            problems.append(f"السطر {n}: لا إسنادَ حيّاً يربط المعلّمَ والمادّةَ بالشعبة")
        ck = _key(row)
        if ck in seen_class:
            problems.append(f"السطر {n}: شعبةٌ بحصّتين في الخانة نفسِها")
        seen_class.add(ck)
        tk = (tid, day, period)
        if tk in seen_teacher:
            problems.append(f"السطر {n}: معلّمٌ بحصّتين في الخانة نفسِها")
        seen_teacher.add(tk)
    return problems


@transaction.atomic
def import_rows(
    school: School,
    year: str,
    rows: Iterable[Mapping[str, Any]],
    *,
    source: str = "",
    approve: bool = False,
    notify: bool = True,
    acknowledged: bool = False,
) -> ImportReport:
    """مسودّةُ توليدٍ من الصفوف؛ و`approve=True` يعتمدها كما يعتمدها زرُّ الشاشة.

    الأوقاتُ من الجرس لا من الصفوف. وترفض الدالّةُ (`ScheduleImportError`) قبل أيّ كتابة إن عابت الصفوف.
    """
    from operations.scheduler import bell_lookup
    from operations.services.schedule import ScheduleService

    rows = list(rows)
    problems = validate_rows(school, year, rows)
    if problems:
        raise ScheduleImportError(problems)

    bands = {
        str(pk): band_id
        for pk, band_id in ClassGroup.objects.filter(school=school, academic_year=year).values_list(
            "id", "time_band_id"
        )
    }
    bell = bell_lookup(school)
    gen = ScheduleGeneration.objects.create(
        school=school,
        academic_year=year,
        status="draft",
        total_slots_created=len(rows),
        config_snapshot={"imported_from": source, "importer": "schedule_import.import_rows"},
    )
    slots = []
    for row in rows:
        cid = row["class_group_id"]
        start, end = bell(int(row["day"]), int(row["period"]), bands.get(str(cid)))
        slots.append(
            ScheduleSlot(
                school=school,
                teacher_id=row["teacher_id"],
                class_group_id=cid,
                subject_id=row["subject_id"],
                day_of_week=int(row["day"]),
                period_number=int(row["period"]),
                start_time=start,
                end_time=end,
                academic_year=year,
                elective_group=row.get("elective_group") or "",
                generation=gen,
                is_active=False,
            )
        )
    ScheduleSlot.objects.bulk_create(slots)
    report = ImportReport(generation=gen, rows=len(slots))
    if approve:
        report.approval = ScheduleService.approve_generation(
            gen, notify=notify, acknowledged=acknowledged
        )
    logger.info("schedule_import: %d حصّةً من «%s» (اعتماد=%s)", len(slots), source, approve)
    return report

"""[CLINIC] W-20261119-003: قراءةُ شاشة «بطاقة الخروج» للممرّض والأخصائيّ — من خرج إلى العيادة الآن، ومن وُسم.

لا سببَ زيارةٍ هنا: القراءةُ من `ClassExit` (لحظاتٌ ووجهة) و`ExcusedExit` (وسمٌ بمدّة)، وسببُ الوسم لا يُقرأ إلا لواضعه.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError
from django.utils import timezone

from clinic.choices import OUTCOME_LEAVE
from clinic.models import ClinicVisit
from core.labels import class_label
from core.models import CustomUser
from operations.models import ClassExit, ExcusedExit


def clinic_exits(school: Any, day: dt.date) -> list[dict[str, Any]]:
    """خروجُ اليوم المفتوحُ إلى العيادة، الأقدمُ أوّلاً — ومعه لحظتا الوصول والمغادرة إن سُجّلتا."""
    qs = (
        ClassExit.objects.filter(
            school=school, session__date=day, destination="clinic", returned_at__isnull=True
        )
        .select_related("student", "session__class_group")
        .order_by("left_at")
    )
    return [
        {
            "pk": e.pk,
            "student": e.student,
            "class_text": class_label(e.session.class_group.grade, e.session.class_group.section),
            "left_at": e.left_at,
            "arrived": e.clinic_arrived_at,
            "departed": e.clinic_left_at,
        }
        for e in qs
    ]


def incoming_to_clinic(school: Any, day: dt.date, now: dt.datetime) -> list[dict[str, Any]]:
    """«قادمون إليك»: خروجُ اليوم المفتوحُ إلى العيادة الذي لم يُسجَّل وصولُه، مع دقائق الانتظار منذ الخروج."""
    rows = []
    for row in clinic_exits(school, day):
        if row["arrived"] is None:
            wait = max(0, int((now - row["left_at"]).total_seconds() // 60))
            rows.append({**row, "wait_minutes": wait})
    return rows


@dataclass(frozen=True)
class ClinicReturn:
    """حالُ خروج العيادة المفتوح لغير الممرّض: حركةٌ فقط، بلا سببٍ ولا تشخيص."""

    no_return: bool
    #: دقائقُ ما بعد المغادرة، أو `None` لمن لن يعود.
    minutes: int | None = None

    @property
    def text(self) -> str:
        if self.no_return:
            return "لن يعود إلى الفصل"
        return f"في الطريق من العيادة · منذ {self.minutes} د"


def clinic_trips(school: Any, student_ids: Iterable[Any], day: dt.date) -> dict[Any, Any]:
    """سطورُ خروج هؤلاء الطلبة في `day` بمفتاح السطر — استعلامٌ واحدٌ تُتبَع منه سلسلةُ الامتدادات (`trip_links`)."""
    rows = ClassExit.objects.filter(
        school=school, student_id__in=list(student_ids), session__date=day
    ).values("pk", "continued_from_id", "left_at", "clinic_arrived_at", "clinic_left_at")
    return {row["pk"]: row for row in rows}


def trip_links(rows: dict[Any, Any], pk: Any) -> list[dict[str, Any]]:
    """الرحلةُ الواحدة من سطرها الجاري إلى أصلها: الجرسُ يقطعها سطوراً ولحظتا العيادة على أحدها."""
    links = []
    while pk in rows:
        links.append(rows[pk])
        pk = rows[pk]["continued_from_id"]
    return links


def return_states(
    school: Any, exits: Iterable[ClassExit], now: dt.datetime
) -> dict[Any, ClinicReturn]:
    """«في الطريق من العيادة» أو «لن يعود إلى الفصل» بمفتاح الخروج — لخروج اليوم المفتوح إلى العيادة وحدَه.

    من الزيارة تُقرأ نتيجتُها ووقتُ إغلاقها وحدَهما: لا يُحمَّل سببٌ ولا أعراضٌ ولا إجراء.
    """
    opened = [e for e in exits if e.destination == "clinic" and e.returned_at is None]
    if not opened:
        return {}
    rows = clinic_trips(school, {e.student_id for e in opened}, timezone.localdate(now))
    trips = {e.pk: (e.student_id, trip_links(rows, e.pk)) for e in opened if e.pk in rows}
    if not trips:
        return {}
    # الأحدثُ إغلاقاً يغلب لكلّ طالب.
    closed = {
        student_id: (closed_at, outcome)
        for student_id, closed_at, outcome in ClinicVisit.objects.filter(
            school=school,
            student_id__in={student_id for student_id, _ in trips.values()},
            closed_at__gte=min(links[-1]["left_at"] for _, links in trips.values()),
        )
        .order_by("closed_at")
        .values_list("student_id", "closed_at", "outcome")
    }
    states: dict[Any, ClinicReturn] = {}
    for pk, (student_id, links) in trips.items():
        visit = closed.get(student_id)
        # زيارةٌ أُغلقت قبل بدء هذه الرحلة لا تخصّها.
        left_at = links[-1]["left_at"]
        if visit and visit[1] == OUTCOME_LEAVE and visit[0] and visit[0] >= left_at:
            states[pk] = ClinicReturn(no_return=True)
            continue
        departed = next((r["clinic_left_at"] for r in links if r["clinic_left_at"]), None)
        if departed is not None:
            minutes = max(0, int((now - departed).total_seconds() // 60))
            states[pk] = ClinicReturn(no_return=False, minutes=minutes)
    return states


def marks_set_by(school: Any, user: Any, day: dt.date) -> list[dict[str, Any]]:
    """الوسومُ السارية التي وضعها هذا المستخدمُ نفسُه — لا وسمَ غيره ولا سببَه."""
    qs = (
        ExcusedExit.objects.filter(school=school, set_by=user, ends_on__gte=day)
        .select_related("student")
        .order_by("ends_on")
    )
    return [{"student": m.student, "starts_on": m.starts_on, "ends_on": m.ends_on} for m in qs]


def student_in_school(school: Any, student_id: Any) -> CustomUser | None:
    """الطالبُ بمعرّفه إن كان مقيَّداً نشطاً في المدرسة، وإلا `None` (معرّفٌ فاسدٌ أو من مدرسةٍ أخرى)."""
    try:
        return (
            CustomUser.objects.filter(
                enrollments__is_active=True, enrollments__class_group__school=school
            )
            .distinct()
            .filter(pk=student_id)
            .first()
        )
    except (ValueError, TypeError, ValidationError):
        return None

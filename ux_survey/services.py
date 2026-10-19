"""خدمةُ الاستبانة: الأهليّة والحفظ والتأجيل والتجميع بحجب المجموعات الصغيرة والمراجعة والمحو الدوريّ.

كلُّ ما يربط المستخدمَ بالاستبانة هنا يمرّ على `SurveyParticipation` وحدَه، والإجابةُ تُكتب بلا أيّ معرّفٍ منه.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from typing import Any

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from core.models import AuditLog
from ux_survey.groups import GROUPS, group_of
from ux_survey.models import SurveyParticipation, SurveyResponse, SurveyWave

RESPOND = "ux_survey.respond"
DASHBOARD = "ux_survey.dashboard"
#: أقلُّ عددِ ردودٍ يُعرض لمجموعةٍ — دونه تُحجب (قرارُ المالك، المواصفة W-20261015-001).
MIN_GROUP = 5
RETENTION_DAYS = 365
SUS_FIELDS = ("sus_easy", "sus_slow", "sus_confident", "sus_remember")
CHOICE_FIELDS = ("usage_frequency", "usage_place", "find_fast")
REVIEW_NEW, REVIEW_OK, REVIEW_NO = 0, 1, 2


class SurveyError(Exception):
    pass


def active_wave() -> SurveyWave | None:
    return SurveyWave.objects.filter(is_active=True).order_by("-pk").first()


def _week_of(day: dt.date) -> dt.date:
    return day - dt.timedelta(days=day.weekday())


def _participation(user, wave: SurveyWave) -> SurveyParticipation:
    return SurveyParticipation.objects.get_or_create(user=user, wave=wave)[0]


def is_eligible(user) -> bool:
    """موظفٌ له مجموعة، وموجةٌ مفتوحة، ولم يُجب ولم يُغلق، وليس في فترة التأجيل."""
    if group_of(user.get_role()) is None:
        return False
    wave = active_wave()
    if wave is None:
        return False
    part = SurveyParticipation.objects.filter(user=user, wave=wave).first()
    if part is None:
        return True
    if part.status in (SurveyParticipation.ANSWERED, SurveyParticipation.CLOSED):
        return False
    return not (part.snooze_until and part.snooze_until > timezone.localdate())


def submit(user, cleaned: dict[str, Any]) -> None:
    """يحفظ الإجابةَ بلا معرّفٍ للمجيب ويسجّل مشاركته في الجدول الآخر، في معاملةٍ واحدة."""
    group = group_of(user.get_role())
    wave = active_wave()
    if group is None or wave is None:
        raise PermissionDenied("لا استبانةَ لهذا الحساب.")
    with transaction.atomic():
        part = _participation(user, wave)
        if part.status == SurveyParticipation.ANSWERED:
            raise SurveyError("سبقت إجابتُك على هذه الموجة.")
        SurveyResponse.objects.create(
            wave=wave,
            role_group=group,
            week=_week_of(timezone.localdate()),
            usage_frequency=cleaned["usage_frequency"],
            usage_place=cleaned["usage_place"],
            find_fast=cleaned["find_fast"],
            hardest_task=cleaned["hardest_task"],
            wish=cleaned.get("wish", ""),
            **{f: int(cleaned[f]) for f in SUS_FIELDS},
        )
        part.status = SurveyParticipation.ANSWERED
        part.snooze_until = None
        part.save(update_fields=["status", "snooze_until"])


def snooze(user) -> None:
    wave = active_wave()
    if wave is None or group_of(user.get_role()) is None:
        return
    part = _participation(user, wave)
    if part.status in (SurveyParticipation.ANSWERED, SurveyParticipation.CLOSED):
        return
    part.status = SurveyParticipation.SNOOZED
    part.snooze_until = timezone.localdate() + dt.timedelta(days=wave.snooze_days)
    part.save(update_fields=["status", "snooze_until"])


def close(user) -> None:
    wave = active_wave()
    if wave is None or group_of(user.get_role()) is None:
        return
    part = _participation(user, wave)
    if part.status == SurveyParticipation.ANSWERED:
        return
    part.status = SurveyParticipation.CLOSED
    part.snooze_until = None
    part.save(update_fields=["status", "snooze_until"])


def _group_stats(rows: list[SurveyResponse]) -> dict[str, Any]:
    n = len(rows)
    return {
        "n": n,
        "sus": {f: round(sum(getattr(r, f) for r in rows) / n, 2) for f in SUS_FIELDS},
        "dist": {f: dict(Counter(getattr(r, f) for r in rows)) for f in CHOICE_FIELDS},
    }


def aggregate(wave: SurveyWave | None) -> dict[str, Any]:
    """متوسطاتٌ وتوزيعاتٌ بالمجموعة مع حجب ما دون الحدّ ومنع الاستنتاج بالطرح.

    - مجموعةٌ دون الحدّ تُحجب كاملةً.
    - إن حُجبت مجموعةٌ واحدةٌ فقط حُجبت معها أصغرُ المجموعات الظاهرة (حجبٌ تكميليّ)، فلا يُستخرج
      المحجوب بطرح الظاهر من الإجمالي.
    - الإجماليُّ لا يُعرض إلّا إن لم يُحجب شيء.
    """
    empty: dict[str, Any] = {"groups": [], "hidden": 0, "total": None, "overall": None}
    if wave is None:
        return empty
    by_group: dict[str, list[SurveyResponse]] = {}
    for row in SurveyResponse.objects.filter(wave=wave):
        by_group.setdefault(row.role_group, []).append(row)
    total = sum(len(v) for v in by_group.values())
    if total < MIN_GROUP:
        return {**empty, "hidden": len(by_group)}
    shown = {g: rows for g, rows in by_group.items() if len(rows) >= MIN_GROUP}
    hidden = len(by_group) - len(shown)
    if hidden == 1 and shown:
        del shown[min(shown, key=lambda g: (len(shown[g]), g))]
        hidden += 1
    groups = [
        {"key": g, "label": GROUPS.get(g, g), **_group_stats(shown[g])}
        for g in GROUPS
        if g in shown
    ]
    everyone = [r for rows in by_group.values() for r in rows]
    return {
        "groups": groups,
        "hidden": hidden,
        "total": None if hidden else total,
        "overall": None if hidden else _group_stats(everyone),
    }


def texts_for_dashboard(wave: SurveyWave | None) -> dict[str, list[dict[str, str]]]:
    """النصوصُ المقبولة بعد المراجعة، لمجموعةٍ ظاهرةٍ فقط، بلا أيّ معرّف."""
    if wave is None:
        return {}
    visible = {g["key"] for g in aggregate(wave)["groups"]}
    out: dict[str, list[dict[str, str]]] = {}
    for row in SurveyResponse.objects.filter(wave=wave, review=REVIEW_OK, role_group__in=visible):
        out.setdefault(GROUPS[row.role_group], []).append(
            {"hardest": row.hardest_task, "wish": row.wish}
        )
    return out


def pending_review(wave: SurveyWave | None) -> list[SurveyResponse]:
    if wave is None:
        return []
    return list(SurveyResponse.objects.filter(wave=wave, review=REVIEW_NEW).order_by("week", "pk"))


def review(reviewer, decisions: dict[str, int]) -> int:
    """يسجّل قرارَ المراجعة البشريّة (مقبولٌ/مرفوض). سطرُ التدقيق بالعدد لا بالنصّ ولا بالمعرّف."""
    if reviewer.get_role() != "platform_developer":
        raise PermissionDenied("المراجعةُ للمطوّر المالك وحدَه.")
    done = 0
    with transaction.atomic():
        for pk, decision in decisions.items():
            if decision not in (REVIEW_OK, REVIEW_NO):
                continue
            done += SurveyResponse.objects.filter(pk=pk, review=REVIEW_NEW).update(review=decision)
        if done:
            AuditLog.objects.create(
                user=reviewer,
                action="update",
                model_name="other",
                object_repr="مراجعة نصوص استبانة تجربة المستخدم",
                changes={"count": done},
            )
    return done


def purge_old(today: dt.date | None = None) -> int:
    """يحذف الإجاباتِ الفرديّة الأقدمَ من 12 شهراً (احتفاظٌ يقرّره المالك). آمنٌ للتكرار."""
    today = today or timezone.localdate()
    cutoff = today - dt.timedelta(days=RETENTION_DAYS)
    deleted, _ = SurveyResponse.objects.filter(week__lt=cutoff).delete()
    return deleted

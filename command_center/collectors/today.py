"""لوحةُ «ما نُشر اليوم» — عددُ الطلبات المدموجة اليوم (بتوقيت الدوحة) وحالةُ نشرها (GitHub العامّ، أرقامٌ فقط).

لا عنوانَ طلبٍ ولا رقمَه هنا (`command_center/contract.py`: لا نصَّ من طرفٍ ثالثٍ، والمستودعُ عامّ) — العددُ وحدَه.
«منشورةٌ» = دمجُها قبل آخر نشرٍ مسجَّلٍ في `deployments`؛ والباقي بانتظار دفعة اليوم (طبيعيٌّ حسب `schoolos-flow`:
نافذةُ نشرٍ واحدةٌ بعد الدوام، لا نشرةَ لكلّ طلب) فلا «أحمر» هنا، بل «انتبه» حين تتراكم بلا نشرٍ فوق يومٍ كامل.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any

from command_center import contract
from command_center.collectors import github
from command_center.collectors.publish import failed, publish

PANEL = "today"
MERGED_PATH = "pulls?state=closed&sort=updated&direction=desc&per_page=50"
DEPLOY_PATH = "deployments?per_page=1"
DOHA_OFFSET = timedelta(hours=3)
STALE_BACKLOG = 5


def _doha_midnight_epoch(moment: float) -> float:
    """بدايةُ اليوم الحاليّ بتوقيت الدوحة (UTC+3)، كطابعٍ زمنيٍّ UTC."""
    doha_now = datetime.fromtimestamp(moment, tz=UTC) + DOHA_OFFSET
    doha_midnight = doha_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return (doha_midnight - DOHA_OFFSET).timestamp()


def reduce_merged(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, list):
        return None
    stamps = [
        t
        for t in (
            github.epoch(p.get("merged_at"))
            for p in payload
            if isinstance(p, dict) and p.get("merged_at")
        )
        if t is not None
    ]
    return {"stamps": stamps}


def reduce_deploy(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, list):
        return None
    stamp = (
        github.epoch(payload[0].get("created_at"))
        if payload and isinstance(payload[0], dict)
        else None
    )
    return {"stamp": stamp}


def collect(now: float | None = None) -> None:
    moment = time.time() if now is None else now
    merged = github.fetch(MERGED_PATH, reduce_merged)
    if merged is None:
        failed(PANEL, "github")
        return
    boundary = _doha_midnight_epoch(moment)
    today_stamps = sorted(t for t in merged["stamps"] if t >= boundary)
    merged_today = len(today_stamps)

    deploy = github.fetch(DEPLOY_PATH, reduce_deploy)
    deploy_stamp = deploy.get("stamp") if deploy else None

    if deploy_stamp is not None:
        published = sum(1 for t in today_stamps if t <= deploy_stamp)
    else:
        published = 0
    pending = merged_today - published

    if merged_today == 0:
        headline = "لا شيءَ دُمج اليوم"
        gauge = None
    else:
        headline = f"{merged_today} طلباً دُمج اليوم"
        gauge = 100 * published / merged_today

    oldest_pending_hours = None
    if pending and today_stamps:
        unpublished = [t for t in today_stamps if deploy_stamp is None or t > deploy_stamp]
        if unpublished:
            oldest_pending_hours = (moment - min(unpublished)) / 3600

    status = contract.OK
    if oldest_pending_hours is not None and oldest_pending_hours > 24:
        status = contract.WARN
    if pending > STALE_BACKLOG:
        status = contract.WARN

    publish(
        PANEL,
        status=status,
        headline=headline,
        gauge=gauge,
        metrics=(
            ("مدموجةٌ اليوم", merged_today),
            ("نُشرت منها", published),
            ("بانتظار الدفعة", pending),
            (
                "آخر دمجٍ",
                "—" if not today_stamps else f"منذ {int((moment - max(today_stamps)) / 60)} د",
            ),
        ),
    )

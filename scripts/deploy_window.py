"""نافذةُ النشر: لا دمجَ إلى main وقتَ الدوام إلّا الإصلاحَ العاجل.

كلُّ دمجٍ إلى main نشرٌ فوريٌّ على Railway. وحادثة 2026-09-17 نُشرت 09:15 صباح
يومِ دوام فسقط الموقعُ على المدرسة كلِّها ثلاثَ ساعاتٍ ونصفاً. قرارُ المالك:
لا نشرَ من الأحد إلى الخميس بين 07:00 و14:00 بتوقيت قطر.

يُفرض في طابور الدمج (`merge_group`) وحدَه — هناك يقع النشرُ فعلاً. والإصلاحُ
العاجل يمرّ بوسم الطلب بـ`LABEL`؛ وإلّا خرج الطلبُ من الطابور ويُعاد بعد 14:00.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone

# قطر بلا توقيتٍ صيفيّ، فالإزاحةُ الثابتة تغني عن قاعدة المناطق الزمنيّة.
QATAR = timezone(timedelta(hours=3))
SCHOOL_DAYS = {6, 0, 1, 2, 3}  # الأحد..الخميس في `weekday()`
WINDOW_START_HOUR = 7
WINDOW_END_HOUR = 14
LABEL = "نشر-عاجل"

_QUEUE_PR_RE = re.compile(r"/pr-(\d+)-")


def in_school_hours(now: datetime) -> bool:
    local = now.astimezone(QATAR)
    return local.weekday() in SCHOOL_DAYS and WINDOW_START_HOUR <= local.hour < WINDOW_END_HOUR


def queued_pr_number(head_ref: str) -> int | None:
    match = _QUEUE_PR_RE.search(head_ref)
    return int(match.group(1)) if match else None


def pr_labels(repo: str, number: int) -> list[str]:
    # وسائطُ ثابتةٌ بلا shell، وgh على PATH في مشغّلات GitHub.
    argv = ["gh", "api", f"repos/{repo}/pulls/{number}", "--jq", "[.labels[].name]"]
    result = subprocess.run(argv, check=True, capture_output=True, text=True)  # noqa: S603
    return json.loads(result.stdout)


def decide(event: str, now: datetime, labels: list[str] | None) -> tuple[bool, str]:
    """(مسموح؟، الرسالة)."""
    local = now.astimezone(QATAR).strftime("%A %H:%M")
    if not in_school_hours(now):
        return True, f"خارج الدوام ({local} بتوقيت قطر) — النشر مسموح."
    if event != "merge_group":
        return True, (
            f"وقت الدوام ({local}) — الفحص لا يمنع هنا؛ طابور الدمج سيرفض الطلب "
            f"حتى 14:00 ما لم يُوسم بـ«{LABEL}»."
        )
    if labels and LABEL in labels:
        return True, f"وقت الدوام ({local}) لكنّ الطلب موسومٌ «{LABEL}» — يمرّ إصلاحاً عاجلاً."
    return False, (
        f"وقت الدوام ({local} بتوقيت قطر): الدمج إلى main نشرٌ فوريّ، والنشر ممنوعٌ "
        f"الأحد–الخميس 07:00–14:00. أعد الأمر بعد 14:00، أو وسم الطلب بـ«{LABEL}» "
        f"إن كان إصلاحاً عاجلاً."
    )


def main() -> int:
    event = os.environ.get("EVENT", "")
    now = datetime.now(UTC)
    labels = None
    if event == "merge_group" and in_school_hours(now):
        number = queued_pr_number(os.environ.get("HEAD_REF", ""))
        if number is not None:
            labels = pr_labels(os.environ["REPO"], number)
    allowed, message = decide(event, now, labels)
    print(message if allowed else f"::error::{message}")
    return 0 if allowed else 1


if __name__ == "__main__":
    sys.exit(main())

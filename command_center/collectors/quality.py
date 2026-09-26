"""لوحةُ «جودة الاختبارات» — من تشغيلات `quality-gate` (GitHub العامّ): نسبةُ إعادة التشغيل (مؤشّرُ التذبذب) وفشلُ الطلبات ومدّةُ البوّابة.

**لا تغطيةَ ولا عددَ اختباراتٍ هنا** (تحتاج نشرَ artifact من CI بصلاحيّة كتابة — قرارٌ لاحق `PR-D`)؛ فتُعرض أرقامٌ متاحةٌ علناً بصدق.
- **نسبةُ إعادة التشغيل** = تشغيلاتٌ `run_attempt > 1` من آخر 30: من يعيد التشغيلَ يقول إنّ الفشلَ لم يكن حقيقيّاً (تذبذب). «انتبه» من 20% وأحمرُ من 40%.
- **فشلُ طلباتِ الدمج** = نسبةُ التشغيلات الفاشلة في `pull_request`: «انتبه» من 40%.
- **مدّةُ البوّابة** (وسيطُ الناجحة): «انتبه» فوق 30 دقيقة (بوّابةٌ بطيئةٌ تُبطئ الجميع).
"""

from __future__ import annotations

from typing import Any

from command_center import contract
from command_center.collectors import github
from command_center.collectors.publish import failed, publish, score, worst

PANEL = "quality"
PATH = "actions/workflows/quality-gate.yml/runs?status=completed&per_page=30"
RERUN_WARN, RERUN_BAD = 0.20, 0.40
PR_FAIL_WARN = 0.40
DURATION_WARN_SECONDS = 30 * 60
MIN_RUNS = 10
COUNTED = ("success", "failure", "timed_out")


def reduce(payload: Any) -> dict[str, Any] | None:
    runs = payload.get("workflow_runs") if isinstance(payload, dict) else None
    if not isinstance(runs, list):
        return None
    counted = [r for r in runs if isinstance(r, dict) and r.get("conclusion") in COUNTED]
    durations = []
    for run in counted:
        if run.get("conclusion") != "success":
            continue
        start, end = github.epoch(run.get("run_started_at")), github.epoch(run.get("updated_at"))
        if start and end and end >= start:
            durations.append(end - start)
    durations.sort()
    prs = [r for r in counted if r.get("event") == "pull_request"]
    return {
        "total": len(counted),
        "reruns": sum(1 for r in counted if int(r.get("run_attempt") or 1) > 1),
        "pr_total": len(prs),
        "pr_failed": sum(1 for r in prs if r.get("conclusion") != "success"),
        "median_seconds": durations[len(durations) // 2] if durations else None,
    }


def levels(summary: dict[str, Any]) -> list[str]:
    total, prs = summary["total"], summary["pr_total"]
    rerun = summary["reruns"] / total if total else 0
    pr_fail = summary["pr_failed"] / prs if prs else 0
    median = summary["median_seconds"] or 0
    if rerun >= RERUN_BAD:
        rerun_level = contract.BAD
    else:
        rerun_level = contract.WARN if rerun >= RERUN_WARN else contract.OK
    return [
        rerun_level,
        contract.WARN if pr_fail >= PR_FAIL_WARN else contract.OK,
        contract.WARN if median > DURATION_WARN_SECONDS else contract.OK,
    ]


def collect() -> None:
    summary = github.fetch(PATH, reduce)
    if summary is None:
        failed(PANEL, "github")
        return
    if summary["total"] < MIN_RUNS:
        publish(
            PANEL,
            status=contract.WARN,
            headline=f"عيّنةٌ قليلةٌ ({summary['total']} من {MIN_RUNS} تشغيلات)",
            gauge=None,
        )
        return
    found = levels(summary)
    overall = worst(found)
    rerun_pct = round(100 * summary["reruns"] / summary["total"])
    headline = "البوّابةُ مستقرّة" if overall == contract.OK else "استقرارُ البوّابة بحاجةٍ إلى نظر"
    median = summary["median_seconds"]
    pr_text = f"{summary['pr_failed']} من {summary['pr_total']}" if summary["pr_total"] else "—"
    publish(
        PANEL,
        status=overall,
        headline=headline,
        gauge=score(found),
        metrics=(
            ("إعادةُ التشغيل (تذبذب)", f"{rerun_pct}%"),
            ("فشلُ طلبات الدمج", pr_text),
            ("مدّةُ البوّابة (وسيط)", "—" if median is None else f"{int(median // 60)} د"),
        ),
    )

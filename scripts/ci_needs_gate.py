#!/usr/bin/env python3
"""حَكَمُ «ملخّص بوابة الجودة» و«Security Summary» — نتيجةُ كلِّ مهمّةٍ في needs يجب أن تكون success.

كانت كلُّ بوّابةٍ تسرد أسماءَ مهامّها في موضعَين (جدولُ الملخّص وشرطُ الفشل)، فنسيانُ أحدهما
يُمرّر مهمّةً خارجَ الحكم بصمت. فالسكربتُ يقرأ `toJSON(needs)` كلَّه فتُحكم أيُّ مهمّةٍ تُضاف
بلا تعديل شرط.

القواعد (مراجعةُ 0105، W-20261002-031):
  - `success` وحدَه نجاح. `failure` و`cancelled` و`skipped` وأيُّ نصٍّ غيرِ معروفٍ فشل.
  - الإعفاءُ الوحيد: جدولُ EXEMPT — (الحدث، المهمّة) ونتيجتُها `skipped` حصراً، بسببٍ معلَّل.
    وcancelled/failure لا يُعفيان أبداً.
  - الفشلُ مغلق: JSON فاسدٌ أو فارغ، needs فارغة، متغيّرٌ مفقود، حدثٌ غيرُ معروف ⇒ خروجٌ بـ1.
"""

from __future__ import annotations

import json
import os
import sys

KNOWN_EVENTS = {"push", "pull_request", "merge_group", "workflow_dispatch", "schedule"}
KNOWN_RESULTS = {"success", "failure", "cancelled", "skipped"}

# (الحدث، المهمّة) ← السبب. تُعفى `skipped` وحدَها، والمهمّةُ المعفاةُ لا تعتمد إلا على مهامَّ غيرِ معفاة
# (يفرضه tests/test_ci_gate_needs.py) فلا يُخفي إعفاؤها فشلَ مهمّةٍ سابقة.
EXEMPT: dict[tuple[str, str], str] = {
    ("push", "mypy"): "يُفحص على الطلب وطابور الدمج («main + الطلب») قبل الدمج",
    ("push", "axe-a11y"): "يُفحص على الطلب وطابور الدمج قبل الدمج",
    ("push", "e2e"): "يُفحص على الطلب وطابور الدمج قبل الدمج",
}


def judge(
    needs: dict[str, dict], event: str, exempt: dict[tuple[str, str], str] | None = None
) -> tuple[list[tuple[str, str, str]], list[str]]:
    """يُعيد (صفوفَ الجدول [المهمّة، النتيجة، الحكم]، قائمةَ أسباب الفشل)."""
    exempt = EXEMPT if exempt is None else exempt
    rows: list[tuple[str, str, str]] = []
    failures: list[str] = []
    for job, info in sorted(needs.items()):
        result = info.get("result") if isinstance(info, dict) else None
        if result not in KNOWN_RESULTS:
            rows.append((job, str(result), "FAIL"))
            failures.append(f"{job}: نتيجةٌ غيرُ معروفة ({result!r})")
        elif result == "success":
            rows.append((job, result, "PASS"))
        elif result == "skipped" and (event, job) in exempt:
            rows.append((job, result, "EXEMPT"))
        else:
            rows.append((job, result, "FAIL"))
            failures.append(f"{job}: {result}")
    return rows, failures


def run(
    needs_json: str | None,
    event: str | None,
    title: str,
    summary_path: str | None,
    exempt: dict[tuple[str, str], str] | None = None,
) -> int:
    exempt = EXEMPT if exempt is None else exempt
    if not needs_json or not needs_json.strip():
        print("::error::NEEDS_JSON مفقودٌ أو فارغ — لا حكمَ بلا بيانات")
        return 1
    if event not in KNOWN_EVENTS:
        print(f"::error::حدثٌ غيرُ معروف: {event!r}")
        return 1
    try:
        needs = json.loads(needs_json)
    except ValueError:
        print("::error::NEEDS_JSON ليس JSON صالحاً")
        return 1
    if not isinstance(needs, dict) or not needs:
        print("::error::needs فارغةٌ أو بلا بنية — لا حكمَ بلا مهامّ")
        return 1

    rows, failures = judge(needs, event, exempt)
    lines = [f"## {title}", "| المهمّة | النتيجة | الحكم |", "|---|---|---|"]
    lines += [f"| {job} | {result} | {verdict} |" for job, result, verdict in rows]
    lines += [
        f"| (إعفاء {job}) | skipped | {reason} |"
        for (ev, job), reason in sorted(exempt.items())
        if ev == event and any(r[0] == job and r[2] == "EXEMPT" for r in rows)
    ]
    text = "\n".join(lines)
    print(text)
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    if failures:
        print("::error::" + title + " — لم تنجح كلُّ المهامّ المطلوبة:")
        for reason in failures:
            print(f"  {reason}")
        return 1
    return 0


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--no-exempt"]
    title = args[0] if args else "بوّابة"
    # `--no-exempt`: بوّابةٌ لا تعفي مهمّةً على أيّ حدث (Security Summary) — لا يسري عليها جدولُ EXEMPT.
    exempt = {} if "--no-exempt" in sys.argv[1:] else None
    return run(
        os.environ.get("NEEDS_JSON"),
        os.environ.get("GITHUB_EVENT_NAME"),
        title,
        os.environ.get("GITHUB_STEP_SUMMARY"),
        exempt,
    )


if __name__ == "__main__":
    sys.exit(main())

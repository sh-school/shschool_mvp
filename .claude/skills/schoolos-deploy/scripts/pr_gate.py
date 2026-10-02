"""بوّابةُ ما قبل الإدخال: يقرأ طلبَ دمجٍ (أو عدّة طلبات) ويعدّد ما يمنع إدخالَه طابورَ الدمج وما يحتاج عيناً.

قراءةٌ فقط: `gh pr view` و`gh pr diff` — لا يدمج ولا يُدخل طابوراً ولا يلمس الإنتاج.
وهو **لا يغني عن قراءة الفرق الفعليّ** (`git diff origin/main...<رأس الطلب>`): حادثةُ #715 كان
وصفُها «لا أثرَ بصريّ» وفرقُها يحذف إصلاحاً منشوراً مع اختباره. هذا السكربتُ يلفت العينَ إلى
مواضع الخطر فقط؛ الحكمُ بعد القراءة.

الاستعمال:
    python pr_gate.py <رقم> [<رقم> ...]            # حيّاً من GitHub (داخل نسخةٍ من المستودع)
    python pr_gate.py <رقم> --no-diff               # بلا جلب الفرق (أسرع، وبلا فحص الهجرات والحذف)
    python pr_gate.py <رقم> --fixture <مجلّد>       # من ملفّين محفوظين <رقم>.json و<رقم>.diff (للاختبار)
    python pr_gate.py <رقم> --now 2026-09-28T10:00:00+03:00   # وقتٌ بديلٌ لفحص نافذة الدوام

الخروج: 0 = لا مانعَ آليّاً؛ 1 = مانعٌ في طلبٍ واحدٍ على الأقلّ؛ 2 = استعمالٌ خاطئ أو فشلُ القراءة.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ثوابتُ النافذة منقولةٌ من scripts/deploy_window.py في المستودع — إن تغيّرت هناك فهنا.
QATAR = timezone(timedelta(hours=3))
SCHOOL_DAYS = {6, 0, 1, 2, 3}  # الأحد..الخميس في weekday()
WINDOW_START_HOUR, WINDOW_END_HOUR = 7, 14
URGENT_LABEL = "نشر-عاجل"

# سطرُ الاعتماد كما في CLAUDE.md («الفلو»، البند 6) — يُطابَق بعد نزع التشكيل.
APPROVAL_RE = re.compile(r"اعتمد من المالك على 8500")
DIACRITICS_RE = re.compile(r"[ـً-ْ]")

PR_FIELDS = (
    "number,title,body,state,isDraft,baseRefName,headRefName,headRefOid,"
    "mergeStateStatus,labels,statusCheckRollup,files,autoMergeRequest"
)

MIGRATION_RE = re.compile(r"(^|/)migrations/\d{4}_[^/]+\.py$")
# ملفّاتٌ تغيّر البناءَ أو الإقلاعَ أو البيئة: تُقرأ سطراً سطراً قبل الإدخال.
INFRA_RE = re.compile(
    r"^(requirements[^/]*\.txt|Dockerfile|Procfile|\.railway/|scripts/railway-|"
    r"shschool/settings/|shschool/celery\.py|\.github/workflows/)"
)
TASKS_RE = re.compile(r"(^|/)tasks(/|\.py$)")
SW_RE = re.compile(r"(^|/)(sw|sw_global)\.js$")
DESTRUCTIVE_OPS = ("RemoveField", "DeleteModel", "RenameField", "RenameModel", "RenameIndex")
REVIEW_OPS = ("AlterField", "RunPython", "RunSQL", "AlterUniqueTogether", "AddConstraint")
ENV_HINT_RE = re.compile(r"ImproperlyConfigured|os\.environ\[|env\(\s*[\"'][A-Z_]+[\"']\s*\)")

FAILED = {"FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE", "ERROR"}


def gh(*args: str) -> str:
    # وسائطُ ثابتةٌ بلا shell؛ gh يقرأ المستودعَ من مجلّد العمل فلا يُكتب اسمُه هنا.
    result = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")  # noqa: S603, S607
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"gh {' '.join(args)} failed")
    return result.stdout


def load(number: int, fixture: Path | None, want_diff: bool) -> tuple[dict, str | None]:
    if fixture is not None:
        data = json.loads((fixture / f"{number}.json").read_text(encoding="utf-8"))
        diff_file = fixture / f"{number}.diff"
        diff = diff_file.read_text(encoding="utf-8") if (want_diff and diff_file.exists()) else None
        return data, diff
    data = json.loads(gh("pr", "view", str(number), "--json", PR_FIELDS))
    diff = gh("pr", "diff", str(number)) if want_diff else None
    return data, diff


def in_school_hours(now: datetime) -> bool:
    local = now.astimezone(QATAR)
    return local.weekday() in SCHOOL_DAYS and WINDOW_START_HOUR <= local.hour < WINDOW_END_HOUR


def check_states(rollup: list[dict]) -> tuple[list[str], list[str]]:
    """(الفاشلة، الجارية) من statusCheckRollup — CheckRun وStatusContext معاً."""
    failed, pending = [], []
    for item in rollup or []:
        name = item.get("name") or item.get("context") or "?"
        conclusion = (item.get("conclusion") or "").upper()
        state = (item.get("state") or "").upper()
        status = (item.get("status") or "").upper()
        if conclusion in FAILED or state in FAILED:
            failed.append(name)
        elif (status and status != "COMPLETED") or state in {"PENDING", "EXPECTED"}:
            pending.append(name)
    return failed, pending


def diff_sections(diff: str) -> dict[str, list[str]]:
    """{المسار: الأسطرُ المضافة}، ومفتاحٌ خاصّ `__deleted__` للملفّات المحذوفة كلّيّاً."""
    sections: dict[str, list[str]] = {"__deleted__": []}
    current = None
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            current = line.split(" b/", 1)[-1]
            sections.setdefault(current, [])
        elif line.startswith("deleted file mode") and current:
            sections["__deleted__"].append(current)
        elif current and line.startswith("+") and not line.startswith("+++"):
            sections[current].append(line[1:])
    return sections


def evaluate(data: dict, diff: str | None, now: datetime) -> tuple[list[str], list[str], list[str]]:
    """(موانع، تنبيهاتٌ تحتاج عيناً، معلومات)."""
    block, warn, info = [], [], []

    if data.get("state", "OPEN") != "OPEN":
        block.append(f"حالتُه {data.get('state')} لا OPEN")
    if data.get("isDraft"):
        block.append("مسوّدة — لا تُدخل الطابور")

    body = DIACRITICS_RE.sub("", data.get("body") or "")
    if not APPROVAL_RE.search(body):
        block.append(
            "لا سطرَ «اعتُمد من المالك على 8500» في الوصف — لا دمجَ إلا باعتمادٍ مباشرٍ من المالك "
            "في محادثتك بعد معاينته (والفحصُ الفنّيّ لازمٌ غيرُ كافٍ)"
        )

    base = data.get("baseRefName")
    if base and base != "main":
        block.append(f"متراكبٌ على «{base}» لا main — يُدمج أساسُه أوّلاً ثمّ يُعاد أساسُ هذا على main")

    merge_state = (data.get("mergeStateStatus") or "UNKNOWN").upper()
    if merge_state == "DIRTY":
        block.append("DIRTY: يتعارض مع main — يعود لصاحبه يدمج origin/main ويحسم (بلا force)")
    elif merge_state in {"UNKNOWN", "BLOCKED", "UNSTABLE"}:
        warn.append(f"mergeStateStatus={merge_state} — أعِد القراءةَ بعد دقيقة وانظر الفحوص")
    else:
        info.append(f"mergeStateStatus={merge_state}")

    rollup = data.get("statusCheckRollup") or []
    failed, pending = check_states(rollup)
    if not rollup:
        warn.append("لا فحوصَ مسجّلةً على الرأس بعد — لا يُحكم بالخضرة قبل ظهورها")
    if failed:
        block.append("فحوصٌ فاشلة: " + "، ".join(sorted(set(failed))))
    if pending:
        warn.append("فحوصٌ جارية: " + "، ".join(sorted(set(pending))))

    labels = [lb.get("name") for lb in data.get("labels") or []]
    if in_school_hours(now):
        if URGENT_LABEL in labels:
            warn.append(f"وقتُ دوام والطلبُ موسومٌ «{URGENT_LABEL}» — يلزم إذنُ المالك الصريح لهذا النشر العاجل")
        else:
            block.append(
                f"وقتُ دوام (الأحد–الخميس 07:00–14:00 الدوحة): الطابورُ يُسقطه — انتظر 14:00، "
                f"أو «{URGENT_LABEL}» بإذن المالك الصريح"
            )
    if data.get("autoMergeRequest"):
        info.append("الدمجُ التلقائيّ مفعَّلٌ عليه (قد يكون في الطابور) — لا دفعَ إلى فرعه (GH006)")

    paths = [f.get("path", "") for f in data.get("files") or []]
    migrations = [p for p in paths if MIGRATION_RE.search(p)]
    infra = [p for p in paths if INFRA_RE.search(p)]
    if migrations:
        warn.append("هجرات: " + "، ".join(migrations) + " — توسيعٌ ثمّ تقليص؟ متوافقةٌ مع الشيفرة القديمة؟")
        if any(p.startswith("roadmap/migrations/") for p in migrations):
            warn.append("هجرةُ خارطة: لا يكتبها إلا «0701 · تحديث الخارطة» — تحقّق من صاحب الطلب")
    if infra:
        warn.append("ملفّاتُ بناءٍ/إقلاعٍ/بيئة: " + "، ".join(infra) + " — اقرأها سطراً سطراً")
    if any(TASKS_RE.search(p) for p in paths):
        warn.append("مهامُّ Celery: هل تُوجَّه إلى طابورٍ يستهلكه العامل؟ وتحقّق بعد النشر بـ--expect-task إن لزم")
    if any(SW_RE.search(p) for p in paths):
        warn.append("عاملُ الخدمة تغيّر: هل رُفع رقمُ CACHE_NAME إن تغيّر منطقُه؟")

    if diff is None:
        info.append("لم يُجلب الفرق — فحصُ عمليّات الهجرة والحذف لم يُجرَ")
        return block, warn, info

    sections = diff_sections(diff)
    deleted = sections.pop("__deleted__")
    if deleted:
        warn.append("ملفّاتٌ محذوفةٌ كلّيّاً: " + "، ".join(deleted) + " — أهي من موضوع الطلب؟")
    for path, added in sections.items():
        text = "\n".join(added)
        if MIGRATION_RE.search(path):
            hits = [op for op in DESTRUCTIVE_OPS if op in text]
            if hits:
                block.append(f"{path}: {'، '.join(hits)} — هدّامٌ في خطوةٍ واحدة (P4-1) إلا بقرارٍ صريحٍ في المراجعة")
            review = [op for op in REVIEW_OPS if op in text]
            if review:
                warn.append(f"{path}: {'، '.join(review)} — راجع القفلَ والرجوعَ (schoolos-migration-guard)")
        if path.startswith("shschool/settings/") and ENV_HINT_RE.search(text):
            warn.append(
                f"{path}: متغيّرٌ قد يصير إلزاميّاً — اسأل المالكَ هل ضُبط على الخدمات الثلاث (الويب والعامل وbeat)"
            )
    return block, warn, info


def main() -> int:
    parser = argparse.ArgumentParser(description="بوّابةُ ما قبل إدخال طلب الدمج (قراءةٌ فقط)")
    parser.add_argument("numbers", nargs="+", type=int)
    parser.add_argument("--no-diff", action="store_true")
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--now", help="وقتٌ ISO بإزاحته، للاختبار")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    now = datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc)
    local = now.astimezone(QATAR)
    window = "دوامٌ (الدمجُ ممنوعٌ إلا نشر-عاجل)" if in_school_hours(now) else "خارج الدوام"
    print(f"الوقت: {local:%A %Y-%m-%d %H:%M} الدوحة — {window}")

    any_block = False
    for number in args.numbers:
        try:
            data, diff = load(number, args.fixture, not args.no_diff)
        except (RuntimeError, OSError, json.JSONDecodeError) as exc:
            print(f"\n#{number}: تعذّرت القراءة — {exc}")
            return 2
        block, warn, info = evaluate(data, diff, now)
        head = (data.get("headRefOid") or "")[:8]
        print(f"\n#{number} {head} — {data.get('title', '')}")
        for line in block:
            print(f"  [مانع]   {line}")
        for line in warn:
            print(f"  [عين]    {line}")
        for line in info:
            print(f"  [معلومة] {line}")
        verdict = "ممنوعُ الإدخال" if block else "لا مانعَ آليّاً — اقرأ git diff الفعليّ ثمّ قرّر"
        print(f"  الحكم: {verdict}")
        any_block = any_block or bool(block)
    return 1 if any_block else 0


if __name__ == "__main__":
    sys.exit(main())

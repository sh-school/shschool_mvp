#!/usr/bin/env python3
"""فحصٌ محلّيٌّ موحَّدٌ قبل «جاهزٌ للمعاينة» (W-20261016-020، المكوّن A من خطّة الفلو بلا تدخّل).

الدافع: فشلُ #1098 (حارسان في test_preview_setup يرفضان `rm -rf` و`--force-recreate`) لم يُكشف إلا في CI بعد الدفع
فأبطل الاعتمادَ وأعاد الدورة (إعادةُ الاعتماد 33%). ولا فحصَ محلّيّاً إلزاميّاً يجمع ما يسقط في CI.

الاستعمال:
    python scripts/premerge.py [--base origin/main] [--enforce] [--dry-run] [--skip prepush,affected,references,merge,prs]

يجمع خمسةَ فحوص ويطبع جدولاً عربيّاً وزمنَ كلٍّ منها وبصمةً في سطرٍ واحدٍ:
  1. prepush     — `scripts/prepush_check.py` (ruff، البيانات الشخصيّة، الأسرار، التعقيد، الهويّة، mypy).
  2. affected    — `scripts/affected_tests.py` (الحرّاسُ المتأثّرة بالبصمة).
  3. references  — اختباراتٌ **تذكر** مسارَ ملفٍّ معدَّلٍ في نصّها؛ يغطّي ما لا تغطّيه قواعدُ affected (سكربتات `.sh`
                   ووثائقُ وإعدادات): فتعديلُ `scripts/preview.sh` لا تطابقه قاعدةٌ في affected، وهو بالضبط ما أسقط #1098.
  4. merge       — محاكاةُ دمج origin/main في الرأس بـ`git merge-tree --write-tree` (لا تمسّ شجرةً ولا فهرساً ولا فرعاً).
  5. prs         — تداخلُ ملفّاتك مع ملفّاتِ الطلباتِ المفتوحة (`gh pr list` قراءةً فقط): **تحذيرٌ** لا فشل.

ما لا يستطيع فحصٌ تشغيلَه يطبع «غير مقيس» ولا يُعدّ سليماً. رمزُ الخروج: 0 كلُّ شيءٍ مقيسٍ نجح، 1 فحصٌ فشل، 3 غيرُ مقيس.

**وضعُ الظلّ (الافتراضيّ أسبوعاً قبل أيّ إلزام):** يُشغَّل ويطبع ويسجّل نتيجته في `.git/premerge_shadow.jsonl` ولا يحجب
(رمزُ الخروج 0 دائماً)، ثمّ تُقارَن سجلّاتُه بفشل CI الفعليّ. و`--enforce` (أو PREMERGE_ENFORCE=1) يفعّل رمزَ الخروج الحقيقيّ.

حدٌّ صريح: مساعدٌ للمطوِّر لا حاجزٌ ولا مرجعٌ للاعتماد؛ الاعتمادُ للمالك على 8500. لا يدفع ولا يكتب في الدفتر ولا يعدّل شيئاً.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from shutil import which

ROOT = Path(__file__).resolve().parent.parent

OK, FAIL, MISSING, WARN = "ok", "fail", "missing", "warn"
LABELS = {OK: ("✔", "نجح"), FAIL: ("✘", "فشل"), MISSING: ("؟", "غير مقيس"), WARN: ("!", "تحذير")}
CHECKS = ("prepush", "affected", "references", "merge", "prs")
TITLES = {
    "prepush": "الفحوصُ السريعة (prepush)",
    "affected": "الحرّاسُ المتأثّرة (affected)",
    "references": "اختباراتٌ تذكر الملفَّ المعدَّل",
    "merge": "محاكاةُ دمج origin/main",
    "prs": "تداخلٌ مع الطلبات المفتوحة",
}
#: سقفُ ما يشغّله فحصُ المراجع دفعةً واحدة؛ ما زاد يُعلَن ولا يُسقَط بصمت.
MAX_REFERENCE_TESTS = 40


def _load_affected():
    """تحميلُ affected_tests كما يفعل اختبارُه (لقراءة CI_ENV وrun_pytest دون تعديل الأداة)."""
    spec = importlib.util.spec_from_file_location(
        "affected_tests", ROOT / "scripts" / "affected_tests.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 — أوامرُ ثابتةٌ بلا مدخلٍ خارجيّ
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd or ROOT,
        check=False,
    )


def _git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return _run(["git", *args], cwd=cwd)


def _tail(proc: subprocess.CompletedProcess, lines: int = 12) -> str:
    return "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-lines:])


# ── الفحوص: كلٌّ منها يعيد (الحالة، التفاصيل) ──────────────────────────────


def _tool_status(proc: subprocess.CompletedProcess) -> tuple[str, str]:
    """رمزُ خروج أداةِ المستودع: 0 نجح، 3 غيرُ مقيس، غيرُ ذلك فشل."""
    if proc.returncode == 0:
        return OK, ""
    if proc.returncode == 3:
        return MISSING, _tail(proc, 6)
    return FAIL, _tail(proc)


def check_prepush(cwd: Path | None = None) -> tuple[str, str]:
    return _tool_status(_run([sys.executable, "scripts/prepush_check.py"], cwd=cwd))


def check_affected(cwd: Path | None = None) -> tuple[str, str]:
    return _tool_status(_run([sys.executable, "scripts/affected_tests.py"], cwd=cwd))


def changed_files(base: str, cwd: Path | None = None) -> list[str] | None:
    """الملفّاتُ التي يغيّرها الرأسُ عن الأساس المشترك مع `base`؛ None إن تعذّر الأساس."""
    merge_base = _git("merge-base", base, "HEAD", cwd=cwd)
    if merge_base.returncode != 0:
        return None
    span = f"{merge_base.stdout.strip()}...HEAD"
    out = _git("diff", "-z", "--name-only", "--diff-filter=ACMRD", span, cwd=cwd).stdout
    return sorted(name for name in out.split("\0") if name)


def tests_mentioning(changed: list[str], root: Path = ROOT) -> list[str]:
    """اختباراتُ tests/ التي يرد في نصّها مسارُ ملفٍّ معدَّلٍ (غيرِ اختبار) كاملاً. حتميّ: أبجديّ."""
    targets = [p for p in changed if not p.startswith("tests/")]
    tests_dir = root / "tests"
    if not targets or not tests_dir.is_dir():
        return []
    found = []
    for path in sorted(tests_dir.glob("test_*.py")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(t in text for t in targets):
            found.append(path.relative_to(root).as_posix())
    return found


def check_references(base: str, cwd: Path | None = None) -> tuple[str, str]:
    changed = changed_files(base, cwd)
    if changed is None:
        return MISSING, f"لا أساسَ للمقارنة ({base}): git fetch origin main أوّلاً"
    tests = tests_mentioning(changed, cwd or ROOT)
    if not tests:
        return OK, "لا اختبارَ يذكر ملفّاً معدَّلاً"
    note = ""
    if len(tests) > MAX_REFERENCE_TESTS:
        note = f"\nتنبيه: {len(tests)} اختباراً يذكر الملفّاتِ المعدَّلة؛ شُغّل أوّلُ {MAX_REFERENCE_TESTS} فقط."
        tests = tests[:MAX_REFERENCE_TESTS]
    status, detail = _load_affected().run_pytest(tests)
    shown = "، ".join(tests[:6]) + (" …" if len(tests) > 6 else "")
    return status, f"{len(tests)} اختباراً: {shown}" + note + (f"\n{detail}" if detail else "")


def check_merge(base: str, cwd: Path | None = None) -> tuple[str, str]:
    """محاكاةُ دمج `base` في الرأس: `git merge-tree` يكتب كائناتٍ وسيطةً فقط، لا شجرةَ ولا فهرسَ ولا فرع."""
    stale = ""
    if base == "origin/main" and _git("fetch", "-q", "origin", "main", cwd=cwd).returncode != 0:
        stale = " (تعذّر تحديثُ origin/main — قد تكون المحاكاةُ على نسخةٍ قديمة)"
    proc = _git("merge-tree", "--write-tree", "--name-only", base, "HEAD", cwd=cwd)
    if proc.returncode == 0:
        return OK, "الدمجُ نظيفٌ" + stale
    if proc.returncode == 1:
        names = proc.stdout.split("\n\n", 1)[0].splitlines()[
            1:
        ]  # السطرُ الأوّل شجرةٌ ناتجة، ثمّ الملفّاتُ المتعارضة
        return FAIL, "تعارضٌ عند الدمج في: " + (
            "، ".join(sorted(set(names))[:10]) or proc.stdout.strip()[:200]
        ) + stale
    return MISSING, "تعذّرت المحاكاة (git 2.38+ مطلوب لـmerge-tree --write-tree): " + _tail(proc, 3)


def check_prs(base: str, cwd: Path | None = None) -> tuple[str, str]:
    """ملفّاتُ الطلبات المفتوحة التي تشاركك تعديلها: تحذيرٌ لا فشل."""
    changed = changed_files(base, cwd)
    if changed is None:
        return MISSING, f"لا أساسَ للمقارنة ({base})"
    if not which("gh"):
        return MISSING, "gh غير مثبَّت"
    head = _git("rev-parse", "HEAD", cwd=cwd).stdout.strip()
    proc = _run(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "open",
            "--limit",
            "100",
            "--json",
            "number,headRefOid,files",
        ],
        cwd=cwd,
    )
    if proc.returncode != 0:
        return MISSING, "تعذّرت قراءةُ الطلبات المفتوحة (gh): " + _tail(proc, 3)
    try:
        prs = json.loads(proc.stdout)
    except ValueError:
        return MISSING, "مخرجُ gh غيرُ مقروء"
    return overlap_status(changed, prs, head)


def overlap_status(changed: list[str], prs: list[dict], head: str) -> tuple[str, str]:
    mine = set(changed)
    lines = []
    for pr in prs:
        if pr.get("headRefOid") == head:
            continue  # طلبُ هذا الرأس نفسِه
        shared = sorted(mine & {f.get("path", "") for f in pr.get("files", [])})
        if shared:
            lines.append(
                f"#{pr['number']}: {'، '.join(shared[:5])}{' …' if len(shared) > 5 else ''}"
            )
    if not lines:
        return OK, "لا تداخلَ مع طلبٍ مفتوح"
    return WARN, "تداخلٌ في الملفّات (قد يسبّب تعارضاً لمن يُدمج ثانياً):\n" + "\n".join(lines[:12])


RUNNERS = {
    "prepush": lambda base, cwd: check_prepush(cwd),
    "affected": lambda base, cwd: check_affected(cwd),
    "references": check_references,
    "merge": check_merge,
    "prs": check_prs,
}


# ── الحكمُ والبصمةُ والتسجيل ──────────────────────────────────────


def verdict(results: dict[str, dict], enforce: bool) -> int:
    """رمزُ الخروج: في الظلّ 0 دائماً؛ وعند الإلزام 1 لأيّ فشل، ثمّ 3 لأيّ غيرِ مقيس، وإلا 0. التحذيرُ لا يؤثّر."""
    if not enforce:
        return 0
    statuses = {r["status"] for r in results.values()}
    if FAIL in statuses:
        return 1
    if MISSING in statuses:
        return 3
    return 0


def fingerprint(head: str, results: dict[str, dict]) -> str:
    body = {"head": head, "results": {k: v["status"] for k, v in sorted(results.items())}}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def run_all(
    base: str, skip: set[str], runners: dict | None = None, cwd: Path | None = None
) -> dict[str, dict]:
    runners = runners or RUNNERS
    results: dict[str, dict] = {}
    for name in CHECKS:
        if name in skip:
            continue
        print(f"… {TITLES[name]}", flush=True)
        started = time.monotonic()
        status, detail = runners[name](base, cwd)
        results[name] = {
            "status": status,
            "detail": detail,
            "seconds": round(time.monotonic() - started, 1),
        }
    return results


def _log_shadow(
    head: str, enforce: bool, total: float, digest: str, results: dict[str, dict]
) -> None:
    git_path = _git("rev-parse", "--git-path", "premerge_shadow.jsonl").stdout.strip()
    if not git_path:
        return
    record = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "head": head,
        "mode": "enforce" if enforce else "shadow",
        "seconds": total,
        "digest": digest,
        "results": {
            k: {"status": v["status"], "seconds": v["seconds"]} for k, v in results.items()
        },
    }
    try:
        with open(git_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass  # السجلُّ مساعدٌ للمقارنة؛ تعذّرُه لا يُسقط الفحص


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="فحصٌ محلّيٌّ موحَّدٌ قبل «جاهزٌ للمعاينة»")
    parser.add_argument("--base", default="origin/main")
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="يفعّل رمزَ الخروج الحقيقيّ (الافتراضيُّ وضعُ الظلّ: لا يحجب)",
    )
    parser.add_argument("--dry-run", action="store_true", help="يعرض الفحوصَ ولا يشغّلها")
    parser.add_argument("--skip", default="", help="فحوصٌ تُترك، مفصولةٌ بفاصلة: " + ",".join(CHECKS))
    args = parser.parse_args(argv)
    enforce = args.enforce or os.environ.get("PREMERGE_ENFORCE") == "1"
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    unknown = skip - set(CHECKS)
    if unknown:
        print(f"✘ فحصٌ غيرُ معروف: {', '.join(sorted(unknown))}")
        return 2

    head = _git("rev-parse", "HEAD").stdout.strip()
    print(
        f"الرأس {head[:8]} · الأساس {args.base} · {'إلزام' if enforce else 'وضعُ الظلّ: يطبع ولا يحجب'}"
    )
    if args.dry_run:
        for name in CHECKS:
            print(f"  · {TITLES[name]}{'  (يُترك)' if name in skip else ''}")
        return 0

    started = time.monotonic()
    results = run_all(args.base, skip)
    total = round(time.monotonic() - started, 1)

    print("\n=== النتيجة ===")
    for name, res in results.items():
        mark, label = LABELS[res["status"]]
        print(f"{mark} {TITLES[name]}: {label}  ({res['seconds']} ث)")
        if res["detail"] and res["status"] != OK:
            print("    " + res["detail"].replace("\n", "\n    "))
    print(f"\nالزمنُ الكلّيّ: {total} ث")
    digest = fingerprint(head, results)
    print(f"بصمة premerge: head={head[:8]} sha256={digest[:16]}")
    _log_shadow(head, enforce, total, digest, results)

    statuses = {r["status"] for r in results.values()}
    if FAIL in statuses:
        print(
            "لا تُعلن «جاهزٌ»: فحصٌ فشل"
            + ("." if enforce else " (وضعُ الظلّ لم يحجب؛ هذا ما كان سيحجب).")
        )
    elif MISSING in statuses:
        print("غيرُ مقيس: ما قيس لا يكفي حكماً — شغّله ببيئةٍ فيها المتطلّبات.")
    else:
        print("كلُّ ما قيس نجح. مساعدٌ للمطوِّر لا حاجزٌ ولا مرجعٌ للاعتماد.")
    return verdict(results, enforce)


if __name__ == "__main__":
    sys.exit(main())

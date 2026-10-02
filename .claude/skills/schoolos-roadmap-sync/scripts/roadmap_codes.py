#!/usr/bin/env python3
"""فهرسُ رموز خارطة التجويد كما تراها الهجراتُ المدموجة — قراءةٌ فقط، بلا قاعدةٍ ولا Django.

يجيب عن ثلاثة أسئلةٍ تتكرّر قبل كلّ هجرة مزامنة:
  1. ما رقمُ الهجرة التالية، وهل في السلسلة رقمٌ مكرّرٌ أو ورقتان (تصادمُ ترقيم)؟
  2. ما آخرُ رقمٍ مستعملٍ في كلّ عائلة (N-، SCH-، REP-، V-K…) فلا يُعاد رمزٌ قائم؟
  3. أين لُمس رمزٌ ما، وما آخرُ (حالة، تقدّم) كتبته له هجرة — لبناء الصفّ «المتوقَّع» في UPDATES
     أو لمقارنة قاعدةٍ محلّيّةٍ منحرفة بالمدموج.
  4. (check) هل «المتوقَّعُ» في صفوف UPDATES لهجرتك يطابق ما كتبته الهجراتُ قبلها؟ الاختلافُ
     لا يعني خطأً حتماً (قد يكون المطوّرُ حرّك البندَ من الصفحة) لكنّه يستحقّ نظرةً قبل الدفع:
     توقُّعٌ لا يطابق الإنتاجَ يجعل الصفَّ يُتخطّى صامتاً فلا يتحدّث البند.

حدودُه (لا يدّعي أكثر منها):
  - لا يرى ما أنشأه المطوّرُ أو عدّله من صفحة /roadmap/ في الإنتاج (رموزُ N-… تُولَّد هناك أيضاً)؛
    فالرقمُ «التالي» أدنى حدٍّ لا ضمان — قارنه بالصفحة قبل الاعتماد.
  - يقرأ ثوابتَ الهجرات بتحليل AST فقط؛ لا يُنفّذ شيفرةَ أيّ هجرة.

الاستعمال:
  python roadmap_codes.py summary                  # من origin/main في المستودع الحاليّ
  python roadmap_codes.py summary --family SCH-    # عائلةٌ واحدة
  python roadmap_codes.py code U-33                # أين لُمس الرمز وآخرُ انتقالٍ له
  python roadmap_codes.py summary --tree .         # من شجرة العمل (هجرتُك غيرُ المدموجة معها)
  python roadmap_codes.py check --tree .           # توقّعاتُ آخر هجرةٍ في الشجرة مقابل ما قبلها
  python roadmap_codes.py check 0043 --repo D:/shschool_mvp
  python roadmap_codes.py summary --repo D:/shschool_mvp --ref origin/main --json
رمزُ الخروج: 0 سليم، 1 هجرةٌ أو مصدرٌ غيرُ موجود، 2 خطأُ استعمال (argparse)،
3 توقّعٌ يخالف آخرَ حالةٍ مكتوبة، 4 تصادمُ ترقيمٍ في السلسلة.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

MIGRATIONS_DIR = "roadmap/migrations"
# رمزُ بندٍ أو مؤشّرٍ أو قرار: N-050، SCH-19، QCC-01b، V-K01، MK17، VD1، D-12.
# بلا شرطة يلزم حرفان فأكثر (فلا يُعدّ «A3» حجمُ ورقٍ رمزاً).
CODE_RE = re.compile(r"^(?:[A-Z]{1,4}-[A-Z]{0,2}\d{1,3}|[A-Z]{2,4}\d{1,3})[a-z]?$")
SPLIT_RE = re.compile(r"^(.*?)(\d+)([a-z]?)$")
MIGRATION_RE = re.compile(r"^(\d{4})_\w+\.py$")


def load_sources(repo: str, ref: str | None, tree: str | None) -> dict[str, str]:
    """يُرجع {اسمُ الملفّ: نصُّه} لهجرات roadmap من شجرةٍ على القرص أو من مرجعٍ في غيت."""
    if tree:
        folder = Path(tree) / MIGRATIONS_DIR
        if not folder.is_dir():
            sys.exit(f"لا مجلّدَ {folder}")
        return {p.name: p.read_text(encoding="utf-8") for p in folder.glob("*.py")}
    listing = subprocess.run(
        ["git", "-C", repo, "ls-tree", "--name-only", f"{ref}:{MIGRATIONS_DIR}"],
        capture_output=True, text=True, encoding="utf-8",
    )
    if listing.returncode != 0:
        sys.exit(f"تعذّرت قراءةُ {ref}:{MIGRATIONS_DIR} — {listing.stderr.strip()}")
    sources = {}
    for name in listing.stdout.split():
        if name.endswith(".py"):
            shown = subprocess.run(
                ["git", "-C", repo, "show", f"{ref}:{MIGRATIONS_DIR}/{name}"],
                capture_output=True, text=True, encoding="utf-8",
            )
            sources[name] = shown.stdout
    return sources


def _const(node: ast.AST) -> object:
    return node.value if isinstance(node, ast.Constant) else None


def _transition(elts: list[ast.expr]) -> tuple | None:
    """صفُّ UPDATES: (رمز، (حالة، تقدّم) متوقَّعان، حالةٌ جديدة، تقدّمٌ جديد، …) — وإلّا None."""
    if len(elts) < 4 or not isinstance(elts[1], ast.Tuple) or len(elts[1].elts) != 2:
        return None
    old_status, old_progress = (_const(e) for e in elts[1].elts)
    new_status, new_progress = _const(elts[2]), _const(elts[3])
    if isinstance(old_status, str) and isinstance(new_status, str) and all(
        isinstance(v, int) for v in (old_progress, new_progress)
    ):
        return (old_status, old_progress, new_status, new_progress)
    return None


STATUSES = {"todo", "doing", "done", "blocked", "deferred"}  # roadmap.models.ItemStatus


def _created_state(elts: list[ast.expr]) -> tuple | None:
    """صفُّ إنشاءٍ (NEW_ITEMS وأخواتُها): أوّلُ حالةٍ معروفةٍ يليها عددٌ صحيح = (الحالة، التقدّم)."""
    values = [_const(e) for e in elts]
    for i in range(1, len(values) - 1):
        if values[i] in STATUSES and isinstance(values[i + 1], int) and 0 <= values[i + 1] <= 100:
            return (values[i], values[i + 1])
    return None


def scan_module(source: str) -> tuple[list[dict], list[str]]:
    """يُرجع (لمساتِ الرموز، اعتماديّاتِ roadmap) من الثوابت العليا للهجرة وحدَها."""
    tree = ast.parse(source)
    touches: list[dict] = []
    deps: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):  # class Migration: dependencies = [("roadmap", "00NN_…")]
            for stmt in node.body:
                if isinstance(stmt, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "dependencies" for t in stmt.targets
                ):
                    for dep in getattr(stmt.value, "elts", []):
                        pair = [_const(e) for e in getattr(dep, "elts", [])]
                        if len(pair) == 2 and pair[0] == "roadmap":
                            deps.append(str(pair[1]))
            continue
        if not isinstance(node, ast.Assign) or not isinstance(node.targets[0], ast.Name):
            continue
        group = node.targets[0].id
        seen_first: set[int] = set()
        for sub in ast.walk(node.value):
            if isinstance(sub, (ast.Tuple, ast.List)) and sub.elts:
                head = _const(sub.elts[0])
                if isinstance(head, str) and CODE_RE.match(head):
                    seen_first.add(id(sub.elts[0]))
                    move = _transition(sub.elts)
                    touches.append({
                        "code": head, "group": group, "role": "row", "transition": move,
                        "created": None if move else _created_state(sub.elts),
                    })
            elif isinstance(sub, ast.Dict):
                for key, value in zip(sub.keys, sub.values):
                    if _const(key) in ("code", "id") and isinstance(_const(value), str) and CODE_RE.match(_const(value)):
                        seen_first.add(id(value))
                        touches.append(
                            {"code": _const(value), "group": group, "role": "row", "transition": None, "created": None}
                        )
        for sub in ast.walk(node.value):  # ذكرٌ عابرٌ (اعتماديّة، مفتاحُ قاموس) لا صفٌّ باسمه
            value = _const(sub)
            if isinstance(value, str) and CODE_RE.match(value) and id(sub) not in seen_first:
                touches.append(
                    {"code": value, "group": group, "role": "mention", "transition": None, "created": None}
                )
    return touches, deps


def build_index(sources: dict[str, str]) -> dict:
    migrations = sorted(n for n in sources if MIGRATION_RE.match(n))
    by_number: dict[str, list[str]] = defaultdict(list)
    depended: set[str] = set()
    codes: dict[str, list[dict]] = defaultdict(list)
    for name in migrations:
        by_number[name[:4]].append(name)
        touches, deps = scan_module(sources[name])
        depended.update(deps)
        for touch in touches:
            codes[touch["code"]].append({"migration": name[:-3], **touch})
    stems = [n[:-3] for n in migrations]
    leaves = [s for s in stems if s not in depended]
    duplicates = {k: v for k, v in by_number.items() if len(v) > 1}
    last = max(by_number) if by_number else "0000"
    families: dict[str, dict] = {}
    for code in codes:
        match = SPLIT_RE.match(code)
        if not match:
            continue
        prefix, digits = match.group(1), match.group(2)
        fam = families.setdefault(prefix, {"max": 0, "width": len(digits), "count": 0})
        fam["count"] += 1
        if int(digits) >= fam["max"]:
            fam["max"], fam["width"] = int(digits), max(fam["width"], len(digits))
    for prefix, fam in families.items():
        fam["next"] = f"{prefix}{fam['max'] + 1:0{fam['width']}d}"
    return {
        "migrations": stems,
        "last": stems[-1] if stems else None,
        "next_number": f"{int(last) + 1:04d}",
        "leaves": leaves,
        "duplicates": duplicates,
        "families": dict(sorted(families.items())),
        "codes": codes,
    }


def last_state(entries: list[dict]) -> tuple | None:
    """آخرُ (حالة، تقدّم) كتبته هجرةٌ للرمز (انتقالُ UPDATES أو حالةُ الإنشاء) — لا يرى تعديلاتِ الصفحة."""
    for entry in reversed(entries):
        if entry["transition"]:
            return entry["transition"][2:]
        if entry["created"]:
            return entry["created"]
    return None


def run_check(index: dict, number: str, as_json: bool) -> int:
    """يقارن «المتوقَّع» في صفوف UPDATES للهجرة `number` بآخر حالةٍ كتبتها الهجراتُ قبلها."""
    target = next((m for m in index["migrations"] if m.startswith(number)), None)
    if target is None:
        print(f"لا هجرةَ برقم {number}")
        return 1
    rows = []
    for code, entries in index["codes"].items():
        for position, entry in enumerate(entries):
            if entry["migration"] == target and entry["transition"]:
                before = last_state([e for e in entries[:position] if e["migration"] < target])
                expected = tuple(entry["transition"][:2])
                verdict = "unknown" if before is None else ("ok" if tuple(before) == expected else "mismatch")
                rows.append({"code": code, "expected": expected, "previous": before, "verdict": verdict})
    if as_json:
        print(json.dumps({"migration": target, "rows": rows}, ensure_ascii=False, indent=1))
    else:
        print(f"الهجرة: {target}")
        labels = {"ok": "مطابق", "mismatch": "يخالف", "unknown": "لا سابقَ في الهجرات"}
        for row in rows:
            prev = f"{row['previous'][0]} {row['previous'][1]}" if row["previous"] else "—"
            exp = f"{row['expected'][0]} {row['expected'][1]}"
            print(f"{row['code']:<10} المتوقَّع {exp:<12} آخرُ مكتوب {prev:<12} {labels[row['verdict']]}")
        if not rows:
            print("لا صفوفَ UPDATES بانتقال حالةٍ في هذه الهجرة")
    return 3 if any(r["verdict"] == "mismatch" for r in rows) else 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # طرفيّةُ ويندوز cp1256 تشوّه العربيّة
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="فهرسُ رموز خارطة التجويد من الهجرات (قراءةٌ فقط)")
    parser.add_argument("command", choices=["summary", "code", "check"])
    parser.add_argument("value", nargs="?", help="الرمزُ مع code، ورقمُ الهجرة مع check (افتراضاً آخرُها)")
    parser.add_argument("--repo", default=".", help="مستودعُ غيت (افتراضاً المجلّدُ الحاليّ)")
    parser.add_argument("--ref", default="origin/main", help="المرجعُ المقروء (افتراضاً origin/main)")
    parser.add_argument("--tree", help="اقرأ من شجرة عملٍ على القرص بدل غيت")
    parser.add_argument("--family", help="اعرض عائلةً واحدة، مثل SCH- أو N-")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "code" and not args.value:
        parser.error("code يحتاج رمزاً، مثل: code U-33")

    index = build_index(load_sources(args.repo, None if args.tree else args.ref, args.tree))
    source = args.tree or f"{args.repo}@{args.ref}"
    collision = bool(index["duplicates"]) or len(index["leaves"]) > 1

    if args.command == "check":
        return run_check(index, args.value or (index["last"] or "")[:4], args.json)

    if args.command == "code":
        entries = index["codes"].get(args.value, [])
        result = {"code": args.value, "source": source, "touches": entries, "last_state": last_state(entries)}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=1))
            return 0
        if not entries:
            print(f"{args.value}: لم تلمسه أيُّ هجرةٍ في {source} (قد يكون من الاستيراد الأوّل أو من الصفحة)")
            return 0
        for e in entries:
            move, born = e["transition"], e["created"]
            detail = ""
            if move:
                detail = f"  من {move[0]} {move[1]} إلى {move[2]} {move[3]}"
            elif born:
                detail = f"  أُنشئ {born[0]} {born[1]}"
            print(f"{e['migration']}  {e['group']}  {e['role']}{detail}")
        state = result["last_state"]
        print(
            f"آخرُ حالةٍ كتبتها هجرة: {state[0]} {state[1]} (صفحةُ الإنتاج قد تخالفها — الحارسُ يتخطّى حينها)"
            if state else "لا حالةَ مكتوبةً في الهجرات (من الاستيراد الأوّل أو ملاحظاتٌ فقط)"
        )
        return 0

    families = index["families"]
    if args.family:
        families = {k: v for k, v in families.items() if k == args.family}
    summary = {k: index[k] for k in ("last", "next_number", "leaves", "duplicates")}
    summary.update(source=source, families=families, collision=collision)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=1))
    else:
        print(f"المصدر: {source}")
        print(f"آخرُ هجرة: {index['last']} — التالية: {index['next_number']}_…")
        if collision:
            print(f"تصادمُ ترقيم! أوراقُ السلسلة: {index['leaves']} مكرّرات: {index['duplicates']}")
        for prefix, fam in families.items():
            print(f"{prefix:<8} أعلى {fam['max']:>3}  التالي {fam['next']:<10} ({fam['count']} رمزاً)")
        print("تنبيه: رموزُ N-… تُولَّد من الصفحة أيضاً — قارن «التالي» بأعلى N- في /roadmap/ قبل الاعتماد.")
    return 4 if collision else 0


if __name__ == "__main__":
    sys.exit(main())

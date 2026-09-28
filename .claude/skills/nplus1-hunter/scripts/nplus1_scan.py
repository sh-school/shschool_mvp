#!/usr/bin/env python3
"""
nplus1_scan.py — صيّاد N+1 الاستدلاليّ لمنصّة SchoolOS (Python AST + قوالب Django).

يرصد مرشّحاتٍ لا أحكاماً: حلقةٌ تعبر علاقةً (obj.rel.attr أو obj.rel.all()/count())
ومصدرُها لا يظهر فيه select_related/prefetch_related/annotate/values.

الاستخدام (من جذر الشجرة، على المضيف أو في الحاوية — لا يحتاج Django ولا قاعدة):
    python .claude/skills/nplus1-hunter/scripts/nplus1_scan.py
    python .claude/skills/nplus1-hunter/scripts/nplus1_scan.py --app operations
    python .claude/skills/nplus1-hunter/scripts/nplus1_scan.py --path api/views.py
    python .claude/skills/nplus1-hunter/scripts/nplus1_scan.py --templates-only --max 50

لا يخرج برمز خطأ على المرشّحات (أداةُ إرشاد)؛ يخرج بـ2 إن لم يوجد المسارُ المطلوب.
كلُّ مرشّحٍ يُؤكَّد بعدّ الاستعلامات (references/02-measure-and-test.md) قبل أيّ إصلاح.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

# جذرُ الشجرة: scripts ← nplus1-hunter ← skills ← .claude ← الجذر
ROOT = Path(__file__).resolve().parents[4]

# مجلّداتٌ لا تُفحص — تُقارن بالأجزاء «نسبةً إلى الجذر» لا بالمسار المطلق،
# وإلّا سقط كلُّ ملفٍّ حين تكون الشجرةُ نفسُها تحت .claude/worktrees/ (فلا مرشّحات بصمت).
SKIP = {".venv", "venv", "node_modules", "__pycache__", ".git", "migrations",
        "staticfiles", "_archive", "tests", "AAdocs", "docs", "staging", "loadtest"}

REL_METHODS = {"all", "filter", "exclude", "count", "exists", "first", "last",
               "aggregate", "values", "values_list", "order_by", "get"}
SAFE_ATTRS = {"pk", "id", "name", "value", "label"}
HANDLED_MARKERS = ("select_related", "prefetch_related", "values(", "values_list(",
                   "annotate(", "Prefetch(")


def _skipped(path: Path) -> bool:
    rel = path.relative_to(ROOT).parts
    return any(part in SKIP or part.startswith(".") for part in rel[:-1])


def _iter(pattern: str, sub: str | None):
    base = (ROOT / sub) if sub else ROOT
    if base.is_file():
        if base.match(pattern):
            yield base
        return
    for p in base.rglob(pattern):
        if not _skipped(p):
            yield p


def _loop_var_and_iter(node: ast.For):
    """يعيد (اسمَ متغيّر الحلقة، عقدةَ المصدر) — ويفكّ `for i, obj in enumerate(x)`."""
    target, it = node.target, node.iter
    if (isinstance(target, ast.Tuple) and len(target.elts) == 2
            and isinstance(target.elts[1], ast.Name)
            and isinstance(it, ast.Call) and isinstance(it.func, ast.Name)
            and it.func.id == "enumerate" and it.args):
        return target.elts[1].id, it.args[0]
    if isinstance(target, ast.Name):
        return target.id, it
    return None, it


class ForVisitor(ast.NodeVisitor):
    def __init__(self, src: str):
        self.src = src
        self.hits: list[tuple[int, str]] = []
        # مصادرُ الإسناد في الدالّة الجارية: qs = X.objects.select_related(...)
        self._assigned: list[dict[str, str]] = [{}]

    def _enter_scope(self, node):
        scope: dict[str, str] = {}
        for sub in ast.walk(node):
            if isinstance(sub, ast.Assign):
                seg = ast.get_source_segment(self.src, sub.value) or ""
                for t in sub.targets:
                    if isinstance(t, ast.Name):
                        scope[t.id] = scope.get(t.id, "") + " " + seg
        self._assigned.append(scope)
        self.generic_visit(node)
        self._assigned.pop()

    visit_FunctionDef = _enter_scope
    visit_AsyncFunctionDef = _enter_scope

    def _handled(self, iter_node) -> bool:
        seg = ast.get_source_segment(self.src, iter_node) or ""
        # المصدرُ متغيّرٌ أُسند إليه استعلامٌ مُحسَّنٌ في الدالّة نفسها
        for n in ast.walk(iter_node):
            if isinstance(n, ast.Name):
                seg += " " + self._assigned[-1].get(n.id, "")
        return any(m in seg for m in HANDLED_MARKERS)

    def visit_For(self, node):
        var, it = _loop_var_and_iter(node)
        if var and not self._handled(it):
            for stmt in node.body:
                for sub in ast.walk(stmt):
                    self._check(sub, var)
        self.generic_visit(node)

    def _check(self, sub, var):
        if (isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Attribute)
                and isinstance(sub.value.value, ast.Name) and sub.value.value.id == var):
            mid = sub.value.attr
            # obj.rel.count يُلتقط استدعاءً في الفرع الثاني — لا يُعدّ مرّتين
            if (mid not in SAFE_ATTRS and not mid.startswith(("get_", "_"))
                    and sub.attr not in REL_METHODS):
                self.hits.append((sub.lineno, f"{var}.{mid}.{sub.attr}"))
        if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                and sub.func.attr in REL_METHODS
                and isinstance(sub.func.value, ast.Attribute)
                and isinstance(sub.func.value.value, ast.Name)
                and sub.func.value.value.id == var):
            self.hits.append((sub.lineno, f"{var}.{sub.func.value.attr}.{sub.func.attr}()"))


def scan_python(sub):
    out = []
    for p in _iter("*.py", sub):
        try:
            src = p.read_text(encoding="utf-8", errors="ignore")
            v = ForVisitor(src)
            v.visit(ast.parse(src))
        except SyntaxError:
            continue
        for line, expr in sorted(set(v.hits)):
            out.append((p.relative_to(ROOT).as_posix(), line, expr))
    return out


FOR_RE = re.compile(r"{%-?\s*for\s+(?:\w+\s*,\s*)?(\w+)\s+in\s+")
ENDFOR_RE = re.compile(r"{%-?\s*endfor\s*-?%}")


def scan_templates(sub):
    out = []
    for p in _iter("*.html", sub):
        lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        stack: list[str] = []
        for i, line in enumerate(lines, 1):
            for m in FOR_RE.finditer(line):
                stack.append(m.group(1))
            for var in set(stack):
                if var == "forloop":
                    continue
                pattern = r"\b" + re.escape(var) + r"\.(\w+)\.(\w+)"
                for mm in re.finditer(pattern, line):
                    a, b = mm.group(1), mm.group(2)
                    if a in SAFE_ATTRS or a.startswith("get_"):
                        continue
                    out.append((p.relative_to(ROOT).as_posix(), i, f"{var}.{a}.{b}"))
            for _ in ENDFOR_RE.findall(line):
                if stack:
                    stack.pop()
    return out


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):  # طرفيّةُ ويندوز: العربيّةُ تفسد بترميز cp1252
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="صيّاد N+1 لـ SchoolOS")
    ap.add_argument("--app", help="مجلّدُ تطبيقٍ نسبةً إلى الجذر (operations، api، …)")
    ap.add_argument("--path", help="ملفٌّ أو مجلّدٌ بعينه نسبةً إلى الجذر")
    ap.add_argument("--templates-only", action="store_true")
    ap.add_argument("--python-only", action="store_true")
    ap.add_argument("--max", type=int, default=400, help="أقصى ما يُطبع من كلّ قسم")
    args = ap.parse_args()

    sub = args.path or args.app
    if sub and not (ROOT / sub).exists():
        print(f"المسار غير موجود نسبةً إلى الجذر {ROOT}: {sub}")
        return 2

    bar = "=" * 72
    print(bar)
    print(f"  صيّاد N+1 — SchoolOS  [مرشّحات لمراجعة بشريّة]  الجذر: {ROOT}")
    print(bar)

    if not args.templates_only:
        py = scan_python(sub)
        print(f"\n### Python — حلقاتٌ تعبر علاقةً بلا select/prefetch [{len(py)}] ###")
        for path, line, expr in py[: args.max]:
            print(f"  [PY] {path}:{line}   ->  {expr}")
        if not py:
            print("  لا مرشّحات.")

    if not args.python_only:
        tp = scan_templates(sub)
        print(f"\n### قوالب — عبورُ علاقةٍ داخل حلقة for [{len(tp)}] ###")
        for path, line, expr in tp[: args.max]:
            print(f"  [TPL] {path}:{line}   ->  {{{{ {expr} }}}}")
        if not tp:
            print("  لا مرشّحات.")

    print("\n" + bar)
    print("  التالي: أكّد كلَّ مرشّحٍ بعدّ الاستعلامات (صفٌّ واحد مقابل ثلاثة)، ثمّ أصلِح في مصدر الاستعلام.")
    print(bar)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

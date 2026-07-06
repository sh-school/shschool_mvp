#!/usr/bin/env python3
"""
nplus1_scan.py — صيّاد N+1 الاستدلالي لـ SchoolOS (Python AST + قوالب Django).
يرصد المرشّحات: حلقات تعبر علاقة داخل التكرار دون select_related/prefetch_related.

الاستخدام:
    python nplus1_scan.py                 # الكل
    python nplus1_scan.py --app operations
    python nplus1_scan.py --templates-only
    python nplus1_scan.py --python-only

النتائج مرشّحات — أكّدها بعدّ الاستعلامات قبل الإصلاح. لا يخرج برمز خطأ (أداة إرشاد).
"""
from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SKIP = {".venv", "venv", "node_modules", "__pycache__", ".git", "worktrees",
        "migrations", "staticfiles", "_archive", ".claude", "tests"}

REL_METHODS = {"all", "filter", "exclude", "count", "exists", "first", "last",
               "aggregate", "values", "values_list"}
SAFE_ATTRS = {"pk", "id", "name", "value", "label"}


def _iter(pattern, sub):
    base = (ROOT / sub) if sub else ROOT
    if not base.exists():
        return
    for p in base.rglob(pattern):
        if any(part in SKIP or part.startswith(".") for part in p.parts):
            continue
        yield p


class ForVisitor(ast.NodeVisitor):
    def __init__(self, src):
        self.src = src
        self.hits = []

    def visit_For(self, node):
        if isinstance(node.target, ast.Name):
            var = node.target.id
            itersrc = ast.get_source_segment(self.src, node.iter) or ""
            handled = ("select_related" in itersrc or "prefetch_related" in itersrc
                       or "values(" in itersrc or "annotate(" in itersrc)
            if not handled:
                for sub in ast.walk(node):
                    self._check(sub, var)
        self.generic_visit(node)

    def _check(self, sub, var):
        if (isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Attribute)
                and isinstance(sub.value.value, ast.Name) and sub.value.value.id == var):
            mid = sub.value.attr
            if mid not in SAFE_ATTRS and not mid.startswith("get_"):
                self.hits.append((sub.lineno, var + "." + mid + "." + sub.attr))
        if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                and sub.func.attr in REL_METHODS
                and isinstance(sub.func.value, ast.Attribute)
                and isinstance(sub.func.value.value, ast.Name)
                and sub.func.value.value.id == var):
            rel = sub.func.value.attr
            self.hits.append((sub.lineno, var + "." + rel + "." + sub.func.attr + "()"))


def scan_python(sub):
    out = []
    for p in _iter("*.py", sub):
        try:
            src = p.read_text(encoding="utf-8", errors="ignore")
            v = ForVisitor(src)
            v.visit(ast.parse(src))
        except SyntaxError:
            continue
        seen = set()
        for line, expr in v.hits:
            key = (line, expr)
            if key in seen:
                continue
            seen.add(key)
            out.append((str(p.relative_to(ROOT)), line, expr))
    return out


FOR_RE = re.compile(r"{%\s*for\s+(\w+)\s+in\s+([\w.]+)")
ENDFOR_RE = re.compile(r"{%\s*endfor\s*%}")


def scan_templates(sub):
    out = []
    for p in _iter("*.html", sub):
        lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        stack = []
        for i, line in enumerate(lines, 1):
            for m in FOR_RE.finditer(line):
                stack.append(m.group(1))
            for var in list(stack):
                if var == "forloop":
                    continue
                pattern = r"\b" + re.escape(var) + r"\.(\w+)\.(\w+)"
                for mm in re.finditer(pattern, line):
                    a, b = mm.group(1), mm.group(2)
                    if a in SAFE_ATTRS or a.startswith("get_"):
                        continue
                    out.append((str(p.relative_to(ROOT)), i, var + "." + a + "." + b))
            if ENDFOR_RE.search(line) and stack:
                stack.pop()
    return out


def main():
    ap = argparse.ArgumentParser(description="صيّاد N+1 لـ SchoolOS")
    ap.add_argument("--app")
    ap.add_argument("--templates-only", action="store_true")
    ap.add_argument("--python-only", action="store_true")
    args = ap.parse_args()

    bar = "=" * 72
    print(bar)
    print("  صيّاد N+1 — SchoolOS  [مرشّحات لمراجعة بشرية]")
    print(bar)

    if not args.templates_only:
        py = scan_python(args.app)
        print("\n### Python — حلقات تعبر علاقة بلا select/prefetch [" + str(len(py)) + "] ###")
        for path, line, expr in py[:400]:
            print("  [PY] " + path + ":" + str(line) + "   ->  " + expr)
        if not py:
            print("  OK لا مرشّحات.")

    if not args.python_only:
        tp = scan_templates(args.app)
        print("\n### قوالب — عبور علاقة داخل حلقة for [" + str(len(tp)) + "] ###")
        for path, line, expr in tp[:400]:
            print("  [TPL] " + path + ":" + str(line) + "   ->  {{ " + expr + " }}")
        if not tp:
            print("  OK لا مرشّحات.")

    print("\n" + bar)
    print("  التالي: أكّد كل مرشّح بـ django_assert_num_queries، ثم أصلِح في مصدر الـ queryset.")
    print(bar)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

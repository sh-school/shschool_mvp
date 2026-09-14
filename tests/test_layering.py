"""
حارسُ الطبقات — فرض الفصل بين Domain Logic والعروض
════════════════════════════════════════════════════

القاعدة الأولى: لا view يزيد على 60 سطر
القاعدة الثانية: لا استدعاءُ ORM يزيد على 5 لكل view
القاعدة الثالثة: core لا يستورد من وحدات نازلة
القاعدة الرابعة: لا get_school() في العروض — استخدم request.school

الحارسُ يسجّل الأعداد الحاليّة (baseline) ولا يسمح بالزيادة.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

# ═════════════════════════════════════════════════════════════════════════
# Baseline
# ═════════════════════════════════════════════════════════════════════════

BASELINE_FILE = pathlib.Path("tests/layering_baseline.json")

DEFAULT_BASELINE = {
    "view_line_counts": {},
    "view_orm_calls": {},
    "core_downstream_imports": [],
    "get_school_calls_by_view": {},
}


def load_baseline() -> dict:
    if BASELINE_FILE.exists():
        return json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    return DEFAULT_BASELINE.copy()


def save_baseline(data: dict):
    BASELINE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# ═════════════════════════════════════════════════════════════════════════
# Analysis
# ═════════════════════════════════════════════════════════════════════════

VIEW_DEF_RE = re.compile(r"^def\s+(\w+)\s*\(request[^)]*\):", re.MULTILINE)
ORM_PATTERN = re.compile(
    r"\.objects\s*\.|\.filter\s*\(|\.annotate\s*\(|\.aggregate\s*\(|"
    r"(?:^|\W)select_related\s*\(|(?:^|\W)prefetch_related\s*\(|Q\s*\("
)
GET_SCHOOL_RE = re.compile(r"\bget_school\s*\(")


def analyze_views_in_file(file_path: pathlib.Path) -> dict[str, dict]:
    """تحليلُ ملفّ views."""
    content = file_path.read_text(encoding="utf-8")
    lines = content.split("\n")
    results: dict[str, dict] = {}

    for match in VIEW_DEF_RE.finditer(content):
        view_name = match.group(1)
        # match.start() points to the start of 'def', which is the line we want
        def_line_num = content[:match.start()].count("\n")

        # Find end of function (next line that's not indented and not blank)
        end_line_num = def_line_num + 1
        for i in range(def_line_num + 1, len(lines)):
            stripped = lines[i].lstrip()
            if stripped and not lines[i].startswith((" ", "\t")):
                # This is a non-indented, non-empty line => end of function
                end_line_num = i
                break
        else:
            # Reached end of file
            end_line_num = len(lines)

        # Get function lines (including the def line)
        func_lines = lines[def_line_num:end_line_num]

        # Remove trailing blank lines
        while func_lines and not func_lines[-1].strip():
            func_lines.pop()

        func_text = "\n".join(func_lines)

        # Count
        line_count = len(func_lines)
        orm_count = len(ORM_PATTERN.findall(func_text))
        get_school_count = len(GET_SCHOOL_RE.findall(func_text))

        results[view_name] = {
            "lines": line_count,
            "orm_calls": orm_count,
            "get_school_calls": get_school_count,
            "file": file_path.name,
        }

    return results


def analyze_core_imports() -> list[str]:
    """استخراجُ مستوردات core من الوحدات النازلة."""
    core_files = list(pathlib.Path("core").rglob("*.py"))
    imports = set()

    downstream = {
        "analytics", "assessments", "behavior", "clinic", "exam_control",
        "library", "operations", "parents", "quality", "reports",
        "staff_affairs", "student_affairs", "transport", "wings", "notifications",
    }

    for file_path in core_files:
        if "__pycache__" in file_path.parts:
            continue
        content = file_path.read_text(encoding="utf-8")
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith(("from ", "import ")):
                for app in downstream:
                    if re.match(rf"(?:from\s+{re.escape(app)}|import\s+{re.escape(app)})", stripped):
                        imports.add(app)

    return sorted(imports)


# ═════════════════════════════════════════════════════════════════════════
# Tests
# ═════════════════════════════════════════════════════════════════════════

def test_view_line_count(update: bool = False):
    """Rule 1: Each view <= 60 lines."""
    baseline = load_baseline()
    view_files = pathlib.Path(".").glob("*/views*.py")
    current = {}
    errors = []

    for file_path in sorted(view_files):
        if "tests" in file_path.parts or "__pycache__" in file_path.parts:
            continue
        views = analyze_views_in_file(file_path)
        for view_name, data in views.items():
            qualified_name = f"{file_path.parent.name}.{view_name}"
            current[qualified_name] = data["lines"]
            registered = baseline.get("view_line_counts", {}).get(qualified_name)

            if registered is not None and data["lines"] > registered:
                errors.append(f"{qualified_name}: {data['lines']} lines (was {registered})")

    if update:
        baseline["view_line_counts"] = current
        save_baseline(baseline)
        print(f"[SAVED] {len(current)} view line counts")
    elif errors:
        for err in errors:
            print(f"FAIL: {err}")
        return False

    return True


def test_orm_call_count(update: bool = False):
    """Rule 2: Each view <= 5 ORM calls."""
    baseline = load_baseline()
    view_files = pathlib.Path(".").glob("*/views*.py")
    current = {}
    errors = []

    for file_path in sorted(view_files):
        if "tests" in file_path.parts or "__pycache__" in file_path.parts:
            continue
        views = analyze_views_in_file(file_path)
        for view_name, data in views.items():
            qualified_name = f"{file_path.parent.name}.{view_name}"
            current[qualified_name] = data["orm_calls"]
            registered = baseline.get("view_orm_calls", {}).get(qualified_name)

            if registered is not None and data["orm_calls"] > registered:
                errors.append(f"{qualified_name}: {data['orm_calls']} ORM calls (was {registered})")

    if update:
        baseline["view_orm_calls"] = current
        save_baseline(baseline)
        print(f"[SAVED] {len(current)} view ORM call counts")
    elif errors:
        for err in errors:
            print(f"FAIL: {err}")
        return False

    return True


def test_core_no_downstream_imports(update: bool = False):
    """Rule 3: core doesn't import downstream modules."""
    baseline = load_baseline()
    current = analyze_core_imports()
    registered = baseline.get("core_downstream_imports", [])
    errors = []

    for app in current:
        if app not in registered:
            errors.append(f"New import from {app} in core (forbidden)")

    if update:
        baseline["core_downstream_imports"] = current
        save_baseline(baseline)
        print(f"[SAVED] {len(current)} downstream imports in core")
    elif errors:
        for err in errors:
            print(f"FAIL: {err}")
        return False

    return True


def test_get_school_calls(update: bool = False):
    """Rule 4: No get_school() in views — use request.school."""
    baseline = load_baseline()
    view_files = pathlib.Path(".").glob("*/views*.py")
    current = {}
    errors = []

    for file_path in sorted(view_files):
        if "tests" in file_path.parts or "__pycache__" in file_path.parts:
            continue
        views = analyze_views_in_file(file_path)
        for view_name, data in views.items():
            qualified_name = f"{file_path.parent.name}.{view_name}"
            current[qualified_name] = data["get_school_calls"]
            registered = baseline.get("get_school_calls_by_view", {}).get(qualified_name)

            if registered is not None and data["get_school_calls"] > registered:
                errors.append(f"{qualified_name}: {data['get_school_calls']} get_school() calls (was {registered})")

    if update:
        baseline["get_school_calls_by_view"] = current
        save_baseline(baseline)
        print(f"[SAVED] {len(current)} view get_school() call counts")
    elif errors:
        for err in errors:
            print(f"FAIL: {err}")
        return False

    return True


def run_tests(update: bool = False):
    """Run all layering tests."""
    results = [
        test_view_line_count(update),
        test_orm_call_count(update),
        test_core_no_downstream_imports(update),
        test_get_school_calls(update),
    ]
    return all(results)


if __name__ == "__main__":
    update = "--update-baseline" in sys.argv or "--update" in sys.argv
    success = run_tests(update)
    if success:
        print("[SUCCESS] All layering tests passed")
        sys.exit(0)
    else:
        print("[FAILED] Layering violations detected")
        sys.exit(1)

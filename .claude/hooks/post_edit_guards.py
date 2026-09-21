#!/usr/bin/env python3
"""PostToolUse(Edit|Write|MultiEdit): تغذيةٌ راجعةٌ فوريّةٌ بدل انتظار CI.

- تعديلُ `static/css/custom/*` ← حرّاسُ التقسيم والرموز (ثانيةٌ واحدة).
- تعديلُ هجرة ← تنبيهٌ بقاعدة «توسيعٌ ثمّ تقليص» إن ظهر فيها حذفٌ/إعادةُ تسمية.
الفشلُ يخرج برمز 2 فيراه Claude فيُصلح؛ والتنبيهُ بلا فشلٍ يُمرَّر سياقاً.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

DESTRUCTIVE = re.compile(r"\b(RemoveField|DeleteModel|RenameField|RenameModel|RunSQL)\b|DROP\s+(COLUMN|TABLE)", re.I)
CSS_GUARDS = ["tests/test_css_split.py", "tests/test_px_tokens.py"]


sys.stdout.reconfigure(encoding='utf-8'); sys.stderr.reconfigure(encoding='utf-8')


def project_python(root: Path) -> str:
    for candidate in (root / ".venv/Scripts/python.exe", root / ".venv/bin/python"):
        if candidate.exists():
            return str(candidate)
    main_venv = Path("D:/shschool_mvp/.venv/Scripts/python.exe")
    return str(main_venv) if main_venv.exists() else sys.executable


def relpath(file_path: str, root: Path) -> str:
    try:
        return Path(file_path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return ""


def main() -> int:
    payload = json.load(sys.stdin)
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or ".")
    rel = relpath(payload.get("tool_input", {}).get("file_path", ""), root)
    if not rel:
        return 0

    if rel.startswith("static/css/custom/") and rel.endswith(".css"):
        run = subprocess.run(
            [project_python(root), "-m", "pytest", *CSS_GUARDS, "-q", "-x", "-p", "no:cacheprovider"],
            cwd=root, capture_output=True, text=True, timeout=120,
        )
        if run.returncode != 0:
            print("حرّاسُ الأنماط سقطت بعد تعديلك:\n" + run.stdout[-2500:], file=sys.stderr)
            return 2
        return 0

    if re.fullmatch(r".+/migrations/\d{4}_.+\.py", rel):
        text = (root / rel).read_text(encoding="utf-8", errors="ignore")
        hit = DESTRUCTIVE.search(text)
        if hit:
            note = (
                f"تنبيه: الهجرةُ {rel} فيها `{hit.group(0)}`. قاعدةُ المشروع «توسيعٌ ثمّ تقليص» "
                "(حذفُ عمودٍ/جدولٍ أو إعادةُ تسميةٍ على إصدارين)؛ وبوّابةُ migration-linter ستُسقطها في CI."
            )
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": note}}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

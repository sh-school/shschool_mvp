#!/usr/bin/env python3
"""Stop: عند ختم الدور، نبّه إن بقي في الشجرة ما لم يُودَع (لا يُعيد Claude للعمل)."""
import json
import subprocess
import sys


sys.stdout.reconfigure(encoding='utf-8'); sys.stderr.reconfigure(encoding='utf-8')


def main() -> int:
    json.load(sys.stdin)
    out = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
    if out:
        lines = out.splitlines()
        shown = "\n".join(lines[:8]) + (f"\n… و{len(lines) - 8} أخرى" if len(lines) > 8 else "")
        print(json.dumps({"systemMessage": f"في الشجرة تعديلاتٌ لم تُودَع ({len(lines)}):\n{shown}"}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

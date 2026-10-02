"""اختباراتُ مدقّق الأتمتة — تُشغَّل بلا Django ولا شبكة:

    python -m unittest scripts/test_audit_automation.py -v

لكلّ نوعٍ حالةٌ سليمةٌ لا FAIL فيها وحالةٌ معطوبةٌ يلتقطها الرمزُ المتوقَّع.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_automation as aa  # noqa: E402

GOOD_WORKFLOW = """name: قياسٌ أسبوعيّ
on:
  schedule:
    - cron: "0 3 * * 0"  # الأحد 03:00 UTC = 06:00 الدوحة
  workflow_dispatch:
concurrency:
  group: weekly-measure
  cancel-in-progress: true
permissions:
  contents: read
  issues: write
jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - run: |
          set -euo pipefail
          python x.py | tee out.json
      - if: failure()
        run: echo open-issue
"""

BAD_WORKFLOW = """name: مراقبٌ كلَّ 10 دقائق
on:
  schedule:
    - cron: "*/10 * * * *"
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - run: curl -fsS "${URL:-https://demo-app.up.railway.app}/health/" | tee h.txt
"""

GOOD_TASK = '''from celery import shared_task

@shared_task(name="reports.weekly_digest", soft_time_limit=120, time_limit=150,
             autoretry_for=(ConnectionError,), retry_backoff=True)
def weekly_digest():
    return {"pending": 0}
'''

BAD_TASK = '''from celery import shared_task

@shared_task(autoretry_for=(Exception,))
def weekly_digest():
    try:
        work()
    except Exception:
        pass
    print("done")
'''

GOOD_PS1 = """$ErrorActionPreference = 'Stop'
# ملاحظة: كان SilentlyContinue سببَ الحادثة
$mutex = New-Object System.Threading.Mutex($false, "Global\\\\DemoMutex")
try { git status; if ($LASTEXITCODE -ne 0) { throw "git" } ; Set-Content LAST_STATUS.json '{}' }
catch { Set-Content DEMO_FAILED.txt 'x'; exit 1 }
"""

BAD_PS1 = """$ErrorActionPreference = 'SilentlyContinue'
git add -A
Write-Host done
"""

GOOD_SCRIPT = '''import os, sys
from datetime import datetime
def main():
    fd = os.open("x.lock", os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    stamp = datetime.now().astimezone().isoformat()
    open("LAST_STATUS.json", "w").write(stamp)
    return 0
if __name__ == "__main__":
    sys.exit(main())
'''

BAD_SCRIPT = '''from datetime import datetime
def main():
    try:
        print(datetime.now())
    except Exception:
        pass
main()
'''


def codes(text: str, name: str, kind: str | None = None) -> set[str]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return {f["code"] for f in aa.audit(path, kind)["findings"]}


def levels(text: str, name: str) -> set[str]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return {f["level"] for f in aa.audit(path)["findings"]}


class WorkflowTests(unittest.TestCase):
    def test_good_scheduled_workflow_has_no_findings(self):
        self.assertEqual(codes(GOOD_WORKFLOW, "w.yml"), set())

    def test_bad_workflow_is_caught(self):
        found = codes(BAD_WORKFLOW, "w.yml")
        for code in ("W-FAILNOTIFY", "W-CONCURRENCY", "W-PERMS", "W-TIMEOUT", "W-PIPEFAIL", "W-SUBHOUR", "W-CLAIM", "G-HOST"):
            self.assertIn(code, found)

    def test_event_workflow_does_not_need_failure_step(self):
        text = GOOD_WORKFLOW.replace('  schedule:\n    - cron: "0 3 * * 0"  # الأحد 03:00 UTC = 06:00 الدوحة\n', "  pull_request:\n")
        text = text.replace("      - if: failure()\n        run: echo open-issue\n", "")
        self.assertNotIn("W-FAILNOTIFY", codes(text, "w.yml"))

    def test_timezone_comment_on_previous_line_counts(self):
        text = GOOD_WORKFLOW.replace('"0 3 * * 0"  # الأحد 03:00 UTC = 06:00 الدوحة', '"0 3 * * 0"')
        self.assertIn("W-CRON-TZ", codes(text, "w.yml"))
        text = text.replace('    - cron: "0 3 * * 0"', '    # 03:00 UTC = 06:00 الدوحة\n    - cron: "0 3 * * 0"')
        self.assertNotIn("W-CRON-TZ", codes(text, "w.yml"))


class CeleryTests(unittest.TestCase):
    def test_good_task(self):
        self.assertEqual(codes(GOOD_TASK, "tasks.py"), set())

    def test_bad_task(self):
        found = codes(BAD_TASK, "tasks.py")
        self.assertTrue({"C-NAME", "C-TIMELIMIT", "C-RETRY-ALL", "C-SWALLOW", "C-PRINT"} <= found)
        self.assertIn("FAIL", levels(BAD_TASK, "tasks.py"))

    def test_mentioning_decorator_in_a_string_is_not_a_task(self):
        text = 'PATTERN = "@shared_task"\nprint("beat_schedule")\n'
        self.assertEqual(aa.detect_kind(Path("x.py"), text), "pyscript")


class CommandTests(unittest.TestCase):
    def test_writing_command_without_apply(self):
        text = "class Command:\n    def handle(self):\n        Item.objects.filter().delete()\n        print('ok')\n"
        found = codes(text, "app/management/commands/purge.py")
        self.assertTrue({"M-APPLY", "M-PRINT"} <= found)

    def test_writing_command_with_apply(self):
        text = "class Command:\n    def add_arguments(self, p):\n        p.add_argument('--apply')\n    def handle(self):\n        Item.objects.filter().delete()\n"
        self.assertEqual(codes(text, "app/management/commands/purge.py"), set())


class PowerShellTests(unittest.TestCase):
    def test_good_ps1(self):
        self.assertEqual(codes(GOOD_PS1, "job.ps1"), set())

    def test_bad_ps1(self):
        found = codes(BAD_PS1, "job.ps1")
        self.assertTrue({"P-EAP", "P-EXIT", "P-LOCK", "P-STATUS", "P-LASTEXIT"} <= found)


class ScriptTests(unittest.TestCase):
    def test_good_script(self):
        self.assertEqual(codes(GOOD_SCRIPT, "job.py"), set())

    def test_bad_script(self):
        found = codes(BAD_SCRIPT, "job.py")
        self.assertTrue({"S-EXIT", "S-SWALLOW", "S-NAIVE-TIME", "S-LOCK", "S-STATUS"} <= found)


class GenericTests(unittest.TestCase):
    def test_secret_and_personal_number(self):
        token = "gh" + "p_" + "A" * 30
        text = f'TOKEN = "{token}"\nSTAFF = "{"2" + "9" * 10}"\n'
        found = codes(text, "job.py")
        self.assertTrue({"G-SECRET", "G-QID"} <= found)

    def test_personal_number_in_tests_is_allowed(self):
        text = f'SAMPLE = "{"3" + "1" * 10}"\nimport sys\nsys.exit(0)\n'
        self.assertNotIn("G-QID", codes(text, "tests/sample.py"))

    def test_noreply_email_is_fine(self):
        self.assertNotIn("G-EMAIL", codes("A = 'bot@users.noreply.github.com'\n", "job.py"))


class CliTests(unittest.TestCase):
    def test_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            good, bad = Path(tmp) / "g.py", Path(tmp) / "b.py"
            good.write_text(GOOD_SCRIPT, encoding="utf-8")
            bad.write_text(BAD_SCRIPT, encoding="utf-8")
            self.assertEqual(aa.main([str(good), "--json"]), 0)
            self.assertEqual(aa.main([str(bad)]), 1)
            self.assertEqual(aa.main([str(Path(tmp) / "missing.py")]), 2)


if __name__ == "__main__":
    unittest.main()

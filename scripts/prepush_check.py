#!/usr/bin/env python3
"""الفحوصُ السريعةُ نفسُها التي يشغّلها CI، محلّيّاً قبل الدفع (W-20261002-030، merge-speedup-8 بند 3).

الغرضُ: أن لا يُكتشف خطأ ruff أو سرٌّ جديد أو تعقيدٌ حرجٌ بعد دفعٍ وانتظارِ دورة CI كاملة؛ فيُكتشف
هنا في ثوانٍ. الأوامرُ مطابقةٌ لوظائف `quality-gate.yml` (ruff, secrets-scan, complexity, mypy)،
ويحرس `tests/test_prepush_check.py` من انجرافها عن الأصل.

الاستعمال:   python scripts/prepush_check.py [--types] [--all-files] [--allow-missing]
             make prepush

  · `--all-files`: مسحُ الأسرار على كلّ المتتبَّع كما في CI (≈170 ثانية)؛ الافتراضيُّ ما تغيّر عن origin/main.
  · `--types`: يضيف سقّاطةَ mypy (تحتاج بيئةَ المشروع: Django ومكتباتِه، فتُشغَّل داخل الحاوية).
  · أداةٌ غائبة ← «غير مقيس» ورمزُ خروج 3 (لا نجاحٌ صامت)، إلّا بـ`--allow-missing`.
  · خروج 0 = كلُّ ما قيس نجح، 1 = فحصٌ فشل، 3 = أداةٌ غائبة بلا `--allow-missing`.

ملاحظة: ruff-format عبر pre-commit (الإصدار المثبَّت 0.4.4 نفسُه كما في CI) **يُعيد كتابةَ** الملفّ
المخالف ويُخفق؛ بعد ذلك أعد `git add` للمسارات التي عدّلها.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

#: يطابق خطوةَ «فحص التعقيد الحلقي» في quality-gate.yml حرفيّاً (يحرسه test_prepush_check).
RADON_EXCLUDE = (
    "*/migrations/*,*/.venv/*,manage.py,scripts/*,*/scripts/*,tests/*,*/tests/*,*/management/commands/*"
)
# قيمٌ عامّةٌ للاختبار فقط، منسوخةٌ حرفيّاً من quality-gate.yml (لا أسرارَ حقيقيّة).
MYPY_ENV = {
    "DJANGO_SETTINGS_MODULE": "shschool.settings.testing",
    "SECRET_KEY": "ci-testing-only-not-for-production-use-a1b2c3d4e5f6",  # pragma: allowlist secret
    "FERNET_KEY": "dGVzdC1mZXJuZXQta2V5LTMyLWJ5dGVzLWZvcmNpLS0=",  # pragma: allowlist secret
    "EXCEL_PROTECTION_PASSWORD": "ci-testing-only",
}

OK, FAIL, MISSING = "ok", "fail", "missing"
BATCH = 200


def _run(cmd: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, **(env or {})},
    )


def _tail(proc: subprocess.CompletedProcess, lines: int = 12) -> str:
    text = (proc.stdout + proc.stderr).strip().splitlines()
    return "\n".join(text[-lines:])


def check_pre_commit_hook(hook_id: str):
    def run():
        if not shutil.which("pre-commit"):
            return MISSING, "pre-commit غير مثبَّت"
        proc = _run(["pre-commit", "run", hook_id, "--all-files"])
        return (OK, "") if proc.returncode == 0 else (FAIL, _tail(proc))

    return run


def check_personal_data():
    proc = _run([sys.executable, "scripts/check_personal_data.py"])
    return (OK, "") if proc.returncode == 0 else (FAIL, _tail(proc))


def _files_to_scan(all_files: bool) -> tuple[list[str], str]:
    """الملفّات التي يُمسح فيها السرّ. السرُّ الجديد لا يأتي إلّا من ملفٍّ تغيّر، فالافتراضيُّ ما تغيّر عن
    origin/main (مُودَعاً أو لا) مع غير المتتبَّع؛ ومسحُ كلّ المتتبَّع (CI) أخذ 169 ثانية محلّياً.
    """
    tracked = _run(["git", "ls-files"]).stdout.splitlines()
    if all_files:
        return tracked, "كلّ المتتبَّع"
    diff = _run(["git", "diff", "--name-only", "--diff-filter=ACMR", "origin/main"])
    if diff.returncode != 0:
        return tracked, "كلّ المتتبَّع (origin/main غير متاح للمقارنة)"
    untracked = _run(["git", "ls-files", "--others", "--exclude-standard"]).stdout.splitlines()
    return sorted(set(diff.stdout.splitlines()) | set(untracked)), "ما تغيّر عن origin/main"


def check_secrets(all_files: bool = False):
    hook = shutil.which("detect-secrets-hook")
    if not hook:
        return MISSING, "detect-secrets غير مثبَّت"
    files, scope = _files_to_scan(all_files)
    if not files:
        return OK, f"لا ملفّات للمسح ({scope})"
    # دفعاتٌ لا استدعاءٌ واحد: سطرُ أوامر ويندوز له حدٌّ (~32KB) تتجاوزه آلافُ الملفّات المتتبَّعة.
    # ورمزُ الخروج يُجمَّع بالأسوأ: أيُّ دفعةٍ بـ1 أو غيرِ (0، 3) فالنتيجةُ فشل؛ و3 تحذيرٌ لا يُسقط.
    # والخطّاف يُعيد كتابةَ السجلّ حين يتقادم ويشتكي بعدها أنّه «غيرُ مُجدوَل»: فنسخةٌ مؤقّتةٌ خارج
    # المستودع لكلّ دفعة، فلا يُترك في الشجرة أثرٌ جانبيٌّ ولا تتعطّل الدفعةُ التالية.
    worst, detail = 0, ""
    with tempfile.TemporaryDirectory() as tmp:
        for start in range(0, len(files), BATCH):
            baseline = Path(tmp) / "secrets.baseline"
            shutil.copyfile(".secrets.baseline", baseline)
            proc = _run([hook, "--baseline", str(baseline), *files[start : start + BATCH]])
            if proc.returncode not in (0, 3):
                return FAIL, _tail(proc)
            if proc.returncode == 3:
                worst = 3
    if worst == 3:
        detail = "تحذير: سجلُّ الأسرار تقادم (لا سرَّ جديداً) — أعد توليده"
    return OK, f"{detail} [{scope}: {len(files)} ملفّاً]".strip()


def check_complexity():
    proc = _run(
        [
            sys.executable,
            "-m",
            "radon",
            "cc",
            ".",
            "--exclude",
            RADON_EXCLUDE,
            "--min",
            "E",
            "--show-complexity",
        ]
    )
    if proc.returncode != 0 and "No module named radon" in proc.stderr:
        return MISSING, "radon غير مثبَّت"
    out = proc.stdout.strip()
    return (FAIL, out) if out else (OK, "")


def check_types():
    proc = _run([sys.executable, "-m", "tests.mypy_ratchet"], env=MYPY_ENV)
    if proc.returncode != 0 and "ModuleNotFoundError" in proc.stderr:
        return MISSING, "بيئة المشروع غير مثبَّتة هنا — شغّله داخل الحاوية"
    return (OK, "") if proc.returncode == 0 else (FAIL, _tail(proc))


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="الفحوصُ السريعة لـCI قبل الدفع")
    parser.add_argument("--types", action="store_true", help="يضيف سقّاطةَ mypy")
    parser.add_argument("--all-files", action="store_true", help="مسحُ الأسرار على كلّ المتتبَّع كـCI (بطيء)")
    parser.add_argument("--allow-missing", action="store_true", help="أداةٌ غائبة لا تُخرج بـ3")
    args = parser.parse_args(argv)

    checks = [
        ("ruff check", check_pre_commit_hook("ruff")),
        ("ruff format --check", check_pre_commit_hook("ruff-format")),
        ("حارس البيانات الشخصيّة", check_personal_data),
        ("detect-secrets", lambda: check_secrets(args.all_files)),
        ("التعقيد الحلقي (CC ≥ 31)", check_complexity),
    ]
    if args.types:
        checks.append(("mypy ratchet", check_types))

    results = []
    for name, fn in checks:
        print(f"… {name}", flush=True)
        results.append((name, *fn()))

    print("\n=== النتيجة ===")
    failed = missing = 0
    for name, status, detail in results:
        mark = {OK: "✔", FAIL: "✘", MISSING: "؟"}[status]
        label = {OK: "نجح", FAIL: "فشل", MISSING: "غير مقيس"}[status]
        print(f"{mark} {name}: {label}")
        if detail:
            print("    " + detail.replace("\n", "\n    "))
        failed += status == FAIL
        missing += status == MISSING

    if failed:
        print("\nلا تدفع: فحصٌ سريعٌ فشل (سيسقط في CI نفسه).")
        return 1
    if missing and not args.allow_missing:
        print("\nأدواتٌ غائبة فما قيس لا يكفي حكماً — ثبّتها أو استعمل --allow-missing عن وعي.")
        return 3
    print("\nالفحوصُ السريعةُ ناجحة — الدفعُ مسموح (الاختبارات الكاملة تبقى في CI).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

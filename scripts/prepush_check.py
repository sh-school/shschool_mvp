#!/usr/bin/env python3
"""الفحوصُ السريعةُ نفسُها التي يشغّلها CI، محلّيّاً قبل الدفع (W-20261002-030، merge-speedup-8 بند 3).

الغرضُ: أن لا يُكتشف خطأ ruff أو سرٌّ جديد أو تعقيدٌ حرجٌ بعد دفعٍ وانتظارِ دورة CI كاملة؛ فيُكتشف
هنا في ثوانٍ. الأوامرُ مطابقةٌ لوظائف `quality-gate.yml` (ruff, secrets-scan, complexity, mypy)،
ويحرس `tests/test_prepush_check.py` من انجرافها عن الأصل.

الاستعمال:   python scripts/prepush_check.py [--types] [--all-files] [--allow-missing]
             make prepush

  · `--all-files`: مسحُ الأسرار على كلّ المتتبَّع كما في CI (≈170 ثانية)؛ الافتراضيُّ ما تغيّر عن origin/main.
  · سقّاطةُ mypy تعمل افتراضيّاً بإصدار CI (requirements-mypy.txt): يفشل إن اختلف الإصدارُ المحلّيّ أو غاب الفاحص؛ ثبّت `pip install -r requirements-mypy.txt` (وبيئةُ المشروع: Django ومكتباتُه، فتُشغَّل داخل الحاوية).
  · `--no-types`: يتخطّى mypy (غير مقيس ← خروج 3).
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
RADON_EXCLUDE = "*/migrations/*,*/.venv/*,manage.py,scripts/*,*/scripts/*,tests/*,*/tests/*,*/management/commands/*"
# قيمٌ عامّةٌ للاختبار فقط، منسوخةٌ حرفيّاً من quality-gate.yml (لا أسرارَ حقيقيّة).
MYPY_ENV = {
    "DJANGO_SETTINGS_MODULE": "shschool.settings.testing",
    "SECRET_KEY": "ci-testing-only-not-for-production-use-a1b2c3d4e5f6",  # pragma: allowlist secret
    "FERNET_KEY": "dGVzdC1mZXJuZXQta2V5LTMyLWJ5dGVzLWZvcmNpLS0=",  # pragma: allowlist secret
    "EXCEL_PROTECTION_PASSWORD": "ci-testing-only",
}

OK, FAIL, MISSING = "ok", "fail", "missing"
BATCH = 200


def _run(
    cmd: list[str], env: dict[str, str] | None = None, timeout: float | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, **(env or {})},
        timeout=timeout,
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


#: حرّاسُ الهويّة النصّيّة: تقرأ الأنماطَ والقوالبَ نصّاً بلا قاعدةٍ ولا خادم (لا django_db) — فتعمل محلّياً في ثوانٍ.
#: الثلاثةُ الأخيرة أضافها W-20261011-002 (D-376م): سقطت في CI (#972 #977 #978) ولم يلتقطها prepush.
IDENTITY_GUARDS = (
    "tests/test_css_colours_are_tokens.py",
    "tests/test_px_tokens.py",
    "tests/test_design_tokens_resolve.py",
    "tests/test_css_layers.py",
    "tests/test_css_split.py",
    "tests/test_identity_reference_fresh.py",
    "tests/test_dead_classes.py",
    "tests/test_design_ratchet.py",
    "tests/test_tailwind_freeze.py",
)
IDENTITY_PATHS = (
    "static/",
    "templates/",
    "core/icons.py",
    "core/templatetags/ui.py",
    "docs/design/page_layouts.md",
)
#: مهلةُ خطوة الهويّة وحدَها (D-376م: يُجاز رفعُ زمن prepush لهذا الغرض فقط). قيس تشغيلُ الحرّاس الثلاثة
#: المضافة وحدَها ≈20 ثانية على المضيف؛ والمجموعةُ كلّها أبطأ على ويندوز فالمهلةُ سخيّة لا ضيّقة.
IDENTITY_TIMEOUT_SECONDS = 300

#: نتيجةُ خطوة الهويّة في هذا التشغيل لتطبع main إيصالَها آخرَ سطر؛ None = لم تُشغَّل (واجهةٌ لم تتغيّر).
_identity_result: str | None = None


def head8() -> str:
    return _run(["git", "rev-parse", "--short=8", "HEAD"]).stdout.strip() or "unknown"


def changed_paths_vs_merge_base() -> list[str] | None:
    """ما تغيّر عن merge-base مع origin/main (مُودَعاً أو لا) مع غير المتتبَّع؛ None إن تعذّر الحساب."""
    base = _run(["git", "merge-base", "HEAD", "origin/main"])
    if base.returncode != 0 or not base.stdout.strip():
        return None
    diff = _run(["git", "diff", "--name-only", "--diff-filter=ACMR", base.stdout.strip()])
    if diff.returncode != 0:
        return None
    untracked = _run(["git", "ls-files", "--others", "--exclude-standard"]).stdout.splitlines()
    return sorted(set(diff.stdout.splitlines()) | set(untracked))


def touches_interface(paths: list[str]) -> bool:
    return any(p.startswith(IDENTITY_PATHS) for p in paths)


def interface_touched() -> bool:
    paths = changed_paths_vs_merge_base()
    # تعذّر الفرق (لا merge-base): الأحوطُ تشغيلُ الحرّاس لا تخطّيها.
    return True if paths is None else touches_interface(paths)


def _run_identity_guards():
    # --noconftest و-p no:django: الحرّاسُ نصّيّةٌ ولا تحتاج بيئةَ Django (conftest يستورد مكتبات المشروع).
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        *IDENTITY_GUARDS,
        "-q",
        "-p",
        "no:cacheprovider",
        "-p",
        "no:django",
        "--noconftest",
        "--no-header",
    ]
    try:
        proc = _run(cmd, timeout=IDENTITY_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return FAIL, f"حرّاسُ الهويّة تجاوزت المهلة ({IDENTITY_TIMEOUT_SECONDS} ثانية)"
    if proc.returncode != 0 and "No module named pytest" in proc.stderr:
        return MISSING, "pytest غير مثبَّت"
    return (OK, "") if proc.returncode == 0 else (FAIL, _tail(proc, 25))


def check_identity():
    """W-20261011-001/-002: حرّاسُ الهويّة كانت تسقط في CI وحدَه. مانعةٌ إن لمس العملُ الواجهةَ (مقابل merge-base)."""
    global _identity_result
    _identity_result = None
    if not interface_touched():
        return OK, "لا واجهة تغيّرت — تخطّي"
    status, detail = _run_identity_guards()
    if status in (OK, FAIL):
        _identity_result = "نجح" if status == OK else "سقط"
    return status, detail


def _print_identity_receipt() -> None:
    """آخرُ سطرٍ في المخرَج: إيصالُ الحرّاس على رأس الإيداع (يقرؤه الاعتماد لاحقاً — D-376م)."""
    if _identity_result:
        print(f"identity_ack: {head8()} {_identity_result}")


def mypy_version_skew() -> list[str] | None:
    """أسطرُ ما يخالف الإصداراتِ الثابتة في requirements-mypy.txt؛ None إن تعذّر القراءة (W-20261014-002)."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from tests.mypy_ratchet import version_skew

        return version_skew()
    except Exception:  # noqa: BLE001
        return None


def check_types():
    """سقّاطةُ mypy بإصدار CI نفسِه: يفشل إن اختلف الإصدارُ المحلّيّ أو غاب الفاحص (لا «نجح عندي» من إصدارٍ آخر)."""
    skew = mypy_version_skew()
    if skew is None:
        return FAIL, "تعذّرت قراءة إصدارات الفاحص (tests/mypy_ratchet.py أو requirements-mypy.txt)"
    if skew:
        return FAIL, "إصداراتُ الفاحص عندك غيرُ ما تحكم به البوّابة:\n" + "\n".join(skew) + "\nثبّتها: pip install -r requirements-mypy.txt"
    proc = _run([sys.executable, "-m", "tests.mypy_ratchet"], env=MYPY_ENV)
    if proc.returncode != 0 and "ModuleNotFoundError" in proc.stderr:
        return MISSING, "بيئة المشروع غير مثبَّتة هنا — شغّله داخل الحاوية"
    return (OK, "") if proc.returncode == 0 else (FAIL, _tail(proc))


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="الفحوصُ السريعة لـCI قبل الدفع")
    parser.add_argument("--types", action="store_true", help="(افتراضيّ الآن) سقّاطةُ mypy بإصدار CI")
    parser.add_argument("--no-types", action="store_true", help="يتخطّى سقّاطةَ mypy (يُسجَّل غيرَ مقيس فيخرج 3)")
    parser.add_argument(
        "--all-files", action="store_true", help="مسحُ الأسرار على كلّ المتتبَّع كـCI (بطيء)"
    )
    parser.add_argument("--allow-missing", action="store_true", help="أداةٌ غائبة لا تُخرج بـ3")
    args = parser.parse_args(argv)

    checks = [
        ("ruff check", check_pre_commit_hook("ruff")),
        ("ruff format --check", check_pre_commit_hook("ruff-format")),
        ("حارس البيانات الشخصيّة", check_personal_data),
        ("detect-secrets", lambda: check_secrets(args.all_files)),
        ("التعقيد الحلقي (CC ≥ 31)", check_complexity),
    ]
    checks.append(("حرّاس الهويّة النصّيّة", check_identity))
    if args.no_types:
        checks.append(("mypy ratchet", lambda: (MISSING, "تُخطّيت بـ--no-types — سيحكم بها CI")))
    else:
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
        _print_identity_receipt()
        return 1
    if missing and not args.allow_missing:
        print("\nأدواتٌ غائبة فما قيس لا يكفي حكماً — ثبّتها أو استعمل --allow-missing عن وعي.")
        _print_identity_receipt()
        return 3
    print("\nالفحوصُ السريعةُ ناجحة — الدفعُ مسموح (الاختبارات الكاملة تبقى في CI).")
    _print_identity_receipt()
    return 0


if __name__ == "__main__":
    sys.exit(main())

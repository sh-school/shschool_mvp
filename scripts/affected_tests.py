#!/usr/bin/env python3
"""يختار الحرّاسَ والاختبارات المتأثّرةَ بالملفّات المعدَّلة، ويشغّلها، ويكتب بصمةً تُلحق بالبطاقة (W-20261003-004).

الغرضُ: أن لا يُكتشف سقوطُ حارسٍ (حجمُ الملفّات، الطبقات، سقّاطةُ mypy، CSS، سير العمل…) بعد دفعٍ وانتظارِ دورة CI،
ولا أن يُدفع رأسٌ فشل إيداعُه بصمتٍ بسبب خطّاف التنسيق. امتدادٌ لـ`scripts/prepush_check.py` (الفحوصُ الثابتة)؛ وهذه
الأداةُ تختار بحسب ما تغيّر فعلاً.

الاستعمال:
    python scripts/affected_tests.py [--base origin/main] [--out ملفّ] [--dry-run] [--allow-dirty]
    python scripts/affected_tests.py --verify ملفّ-البصمة

  · الاختيارُ جدولٌ في `RULES` أدناه (مسارٌ معدَّل ← حرّاسُه)، ويحرسه `tests/test_affected_tests.py` من الانجراف عن
    خطوة «الحرّاسُ النصّيّة» في quality-gate.yml. حارسٌ مسمّى في جدولٍ وغيرُ موجود **يُسجَّل «غير موجود»** ولا يُسقَط.
  · أداةٌ أو بيئةٌ غائبة ← «غير مقيس» ورمزُ خروج 3 (لا نجاحٌ صامت).
  · شجرةٌ فيها تعديلٌ متتبَّعٌ غيرُ مودَع (إيداعٌ أخفقه خطّافُ التنسيق وترك الملفّاتِ مُجهَّزةً أو معدَّلة) ← فشلٌ برمز 1،
    فالبصمةُ تُوقَّع على رأسٍ لا على شجرةٍ مخالفةٍ له.
  · البصمةُ JSON قانونيٌّ (الرأس، الأساس، الملفّاتُ المتغيّرة، المطلوبُ، النتائج، بصمةُ الأداة) وملخّصُها sha256 في
    سطرٍ واحدٍ يُلصق في البطاقة. و`--verify` يعيد حسابَه ويتحقّق أنّ الرأسَ هو الرأسُ الحاليّ وأنّ الأداةَ التي كتبته
    هي نسخةُ main نفسُها (شرطُ 0105: تُقرأ من main ولا تُعدَّل بصمتُها).
  · رمزُ الخروج: 0 كلُّ ما طُلب نجح، 1 فحصٌ فشل أو شجرةٌ غيرُ نظيفة، 3 غيرُ مقيس.

**حدٌّ صريح (حكم 0105): هذه الأداةُ مساعدٌ للمطوِّر، ليست حاجزاً ولا مرجعاً للاعتماد.** البصمةُ تعاونٌ لا شهادة:
`--verify` يعمل بشيفرة الفرع نفسِه، فمن عدّل الأداةَ أنجحه. وقيمتُه الوحيدة أن يُشغَّل من نسخة main لا من الفرع:

    git show origin/main:scripts/affected_tests.py > "$TMPDIR/affected_tests_main.py"
    python "$TMPDIR/affected_tests_main.py" --verify <ملفّ-البصمة>

والاعتمادُ يبقى للمالك على 8500 ولحكم 0105 في المسارات الحسّاسة؛ و«كلُّ المطلوب نجح» لا يعني السلامة: جدولُ `RULES`
لا يغطّي المساراتِ الحسّاسة بعد (بطاقةٌ لاحقة تقابل security/sensitive_paths.json)، فكلُّ ملفٍّ معدَّلٍ لا تطابقه قاعدةٌ
يُطبع «لا حارسَ مطابق — لا يعني السلامة».
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from shutil import which

#: قيمٌ عامّةٌ للاختبار فقط، منسوخةٌ حرفيّاً من quality-gate.yml (لا أسرارَ حقيقيّة).
CI_ENV = {
    "DJANGO_SETTINGS_MODULE": "shschool.settings.testing",
    "SECRET_KEY": "ci-testing-only-not-for-production-use-a1b2c3d4e5f6",  # pragma: allowlist secret
    "FERNET_KEY": "dGVzdC1mZXJuZXQta2V5LTMyLWJ5dGVzLWZvcmNpLS0=",  # pragma: allowlist secret
    "EXCEL_PROTECTION_PASSWORD": "ci-testing-only",
}

TOOL_PATH = "scripts/affected_tests.py"
FINGERPRINT_VERSION = 1
MYPY_ROOTS = ("core/", "shschool/", "governance/")

CSS_GUARDS = (
    "tests/test_css_budget.py",
    "tests/test_css_split.py",
    "tests/test_css_layers.py",
    "tests/test_css_selectors.py",
    "tests/test_css_colours_are_tokens.py",
    "tests/test_css_dead_overrides.py",
    "tests/test_css_comment_decoration.py",
    "tests/test_px_tokens.py",
    "tests/test_design_ratchet.py",
)
CI_GUARDS = (
    "tests/test_ci_gate_needs.py",
    "tests/test_ci_docs_only.py",
    "tests/test_ci_gates_are_honest.py",
    "tests/test_ci_suite_parity.py",
    "tests/test_ci_sharding.py",
)


def _is_code(path: str) -> bool:
    return path.endswith(".py") and not path.startswith("tests/")


def _is_routing(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return path.endswith(".py") and (name == "urls.py" or name.startswith("views"))


def _is_model_layer(path: str) -> bool:
    return path.endswith(".py") and (
        path.endswith("/models.py") or "/models/" in path or "/migrations/" in path
    )


#: (اسمُ القاعدة، شرطُ المسار المعدَّل، اختباراتُها). الأداتان الثابتتان (mypy وactionlint) في `tools_for`.
RULES: tuple[tuple[str, object, tuple[str, ...]], ...] = (
    ("حجمُ الملفّات والطبقات", _is_code, ("tests/test_file_size.py", "tests/test_layering.py")),
    ("حراسةُ المسارات", _is_routing, ("tests/test_every_route_is_guarded.py",)),
    ("CSS", lambda p: p.startswith("static/css/") or p == "core/css_files.py", CSS_GUARDS),
    (
        "القوالب والهويّة",
        lambda p: p.startswith("templates/"),
        ("tests/test_design_ratchet.py", "tests/test_page_layouts.py"),
    ),
    ("سير العمل", lambda p: p.startswith(".github/workflows/"), CI_GUARDS),
    ("سكربتاتُ CI", lambda p: p.startswith("scripts/ci_") and p.endswith(".py"), CI_GUARDS),
    (
        "خريطةُ الحرّاس",
        lambda p: p == "docs/governance/regression_guards.md"
        or (p.startswith("tests/") and "ratchet" in p),
        ("tests/test_regression_guards_doc.py",),
    ),
    (
        "النماذجُ والهجرات",
        _is_model_layer,
        (
            "tests/test_model_naming.py",
            "tests/test_model_field_labels_arabic.py",
            # حارسُ تصنيف الجداول (بطاقة 0101): لم يُدمَج بعدُ على main فيُسجَّل «غير موجود» حتى يصل لا أن يُتجاهَل.
            "tests/test_table_classification.py",
        ),
    ),
)


def parse_z(output: str) -> list[str]:
    """مخرجُ `git ... -z`: أسماءٌ مفصولةٌ بـ\0 فلا تنكسر بمسافةٍ ولا تُقتبس بغير ASCII."""
    return sorted(name for name in output.split("\0") if name)


def rule_matches(path: str) -> bool:
    return (
        any(matches(path) for _name, matches, _guards in RULES)  # type: ignore[operator]
        or (path.startswith("tests/test_") and path.endswith(".py"))
        or bool(tools_for([path]))
    )


def tools_for(changed: list[str]) -> list[str]:
    tools = []
    if any(p.startswith(MYPY_ROOTS) and p.endswith(".py") for p in changed):
        tools.append("mypy_ratchet")
    if any(p.startswith(".github/workflows/") for p in changed):
        tools.append("actionlint")
    return tools


def select(changed: list[str], exists=lambda p: Path(p).is_file()) -> dict:
    """يختار المطلوبَ من الملفّات المعدَّلة. حتميّ: الترتيبُ أبجديّ، ولا شيءَ يُسقَط بصمت."""
    required: set[str] = set()
    reasons: dict[str, list[str]] = {}
    for name, matches, guards in RULES:
        if any(matches(p) for p in changed):  # type: ignore[operator]
            for guard in guards:
                required.add(guard)
                reasons.setdefault(guard, []).append(name)
    # اختبارٌ معدَّلٌ يُشغَّل بنفسه.
    for path in changed:
        if path.startswith("tests/test_") and path.endswith(".py"):
            required.add(path)
            reasons.setdefault(path, []).append("اختبارٌ معدَّل")
    present = sorted(p for p in required if exists(p))
    absent = sorted(required - set(present))
    return {
        "tests": present,
        "absent": absent,
        "tools": tools_for(changed),
        "unmatched": sorted(p for p in changed if not rule_matches(p)),
        "reasons": {k: sorted(set(v)) for k, v in sorted(reasons.items())},
    }


def dirty_entries(porcelain: str) -> list[str]:
    """تعديلاتٌ متتبَّعةٌ غيرُ مودَعة (مُجهَّزةٌ أو لا). غيرُ المتتبَّع `??` لا يعني إيداعاً أخفق."""
    return [line for line in porcelain.splitlines() if line and not line.startswith("??")]


def digest_of(body: dict) -> str:
    core = {k: v for k, v in body.items() if k not in ("digest", "created")}
    canonical = json.dumps(core, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )


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
    return "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-lines:])


OK, FAIL, MISSING = "ok", "fail", "missing"


def run_pytest(tests: list[str]) -> tuple[str, str]:
    proc = _run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", *tests], CI_ENV)
    text = proc.stdout + proc.stderr
    if proc.returncode != 0 and ("ModuleNotFoundError" in text or "No module named" in text):
        return MISSING, "بيئة المشروع غير مثبَّتة هنا — شغّله داخل الحاوية أو بيئةٍ فيها المتطلّبات"
    return (OK, "") if proc.returncode == 0 else (FAIL, _tail(proc))


def run_mypy() -> tuple[str, str]:
    proc = _run([sys.executable, "-m", "tests.mypy_ratchet"], CI_ENV)
    if proc.returncode != 0 and "ModuleNotFoundError" in proc.stderr:
        return MISSING, "بيئة المشروع غير مثبَّتة هنا — شغّله داخل الحاوية"
    # السقّاطةُ مسجَّلةٌ بإصدارٍ مثبَّت (requirements-mypy.txt): إصدارٌ آخر يعطي أعداداً غيرَ قابلةٍ للمقارنة.
    return (OK, "") if proc.returncode == 0 else (FAIL, _tail(proc))


def run_actionlint() -> tuple[str, str]:
    if not which("actionlint"):
        return MISSING, "actionlint غير مثبَّت"
    proc = _run(["actionlint"])
    return (OK, "") if proc.returncode == 0 else (FAIL, _tail(proc))


TOOL_RUNNERS = {"mypy_ratchet": run_mypy, "actionlint": run_actionlint}


def build_fingerprint(
    head: str, base: str, changed: list[str], plan: dict, results: dict, dirty: list[str]
) -> dict:
    body = {
        "version": FINGERPRINT_VERSION,
        "head": head,
        "base": base,
        "changed": changed,
        "required_tests": plan["tests"],
        "absent_guards": plan["absent"],
        "required_tools": plan["tools"],
        "unmatched": plan["unmatched"],
        "results": results,
        "dirty": dirty,
        "tool_blob": _git("hash-object", TOOL_PATH).stdout.strip(),
    }
    body["digest"] = digest_of(body)
    body["created"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return body


def verify(path: Path) -> int:
    body = json.loads(path.read_text(encoding="utf-8"))
    problems = []
    if body.get("digest") != digest_of(body):
        problems.append("البصمةُ عُدِّلت: الملخّصُ لا يطابق المحتوى")
    head = _git("rev-parse", "HEAD").stdout.strip()
    if body.get("head") != head:
        problems.append(f"البصمةُ لرأس {str(body.get('head'))[:8]} والرأسُ الحاليّ {head[:8]}")
    main_blob = _git("rev-parse", f"origin/main:{TOOL_PATH}")
    if main_blob.returncode != 0:
        problems.append("الأداةُ غيرُ موجودةٍ في origin/main — لا مرجعَ لنسخةٍ معتمَدة")
    elif body.get("tool_blob") != main_blob.stdout.strip():
        problems.append("الأداةُ التي كتبت البصمةَ ليست نسخةَ main")
    if body.get("dirty"):
        problems.append("كُتبت البصمةُ على شجرةٍ غيرِ نظيفة")
    bad = [k for k, v in body.get("results", {}).items() if v["status"] != OK]
    if bad:
        problems.append(f"فحوصٌ لم تنجح: {', '.join(bad)}")
    for line in problems:
        print(f"✘ {line}")
    if not problems:
        print("(تعاونٌ لا شهادة: شغّله من نسخة main لا من الفرع — راجع وصفَ الأداة)")
        print(f"✔ البصمةُ سليمةٌ للرأس {body['head'][:8]} (sha256={body['digest'][:16]})")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="الحرّاسُ المتأثّرةُ بالتعديل + بصمةٌ للبطاقة")
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--out", help="مسارُ ملفّ البصمة (الافتراضيُّ داخل .git فلا يلوّث الشجرة)")
    parser.add_argument("--dry-run", action="store_true", help="يعرض المطلوبَ ولا يشغّل")
    parser.add_argument("--allow-dirty", action="store_true", help="لا يفشل على شجرةٍ غيرِ نظيفة")
    parser.add_argument("--verify", metavar="FILE", help="يتحقّق من بصمةٍ سبق كتابتُها")
    args = parser.parse_args(argv)

    if args.verify:
        return verify(Path(args.verify))

    head = _git("rev-parse", "HEAD").stdout.strip()
    merge_base = _git("merge-base", args.base, "HEAD")
    if merge_base.returncode != 0:
        print(f"✘ لا أساسَ للمقارنة ({args.base}): git fetch origin main أوّلاً")
        return 3
    base = merge_base.stdout.strip()
    changed = parse_z(_git("diff", "-z", "--name-only", "--diff-filter=ACMRD", f"{base}...HEAD").stdout)
    plan = select(changed)
    dirty = dirty_entries(_git("status", "--porcelain").stdout)

    print(f"الرأس {head[:8]} · الأساس {base[:8]} · {len(changed)} ملفّاً معدَّلاً")
    extra = f" + {', '.join(plan['tools'])}" if plan["tools"] else ""
    print(f"المطلوب: {len(plan['tests'])} ملفَّ اختبار{extra}")
    for guard in plan["tests"]:
        print(f"  · {guard}  ← {'، '.join(plan['reasons'].get(guard, []))}")
    for guard in plan["absent"]:
        print(f"  ؟ {guard}  ← غيرُ موجودٍ في هذه الشجرة (يُسجَّل في البصمة)")
    if plan["unmatched"] or not plan["tests"]:
        shown = "، ".join(plan["unmatched"][:8]) + (" …" if len(plan["unmatched"]) > 8 else "")
        print(f"؟ لا حارسَ مطابق لـ{len(plan['unmatched'])} ملفّاً — لا يعني السلامة: {shown}")
    if dirty:
        print("✘ تعديلاتٌ متتبَّعةٌ غيرُ مودَعة (هل أخفق إيداعٌ بسبب خطّاف التنسيق؟):")
        for line in dirty[:12]:
            print(f"    {line}")
    if args.dry_run:
        return 1 if dirty and not args.allow_dirty else 0

    results: dict[str, dict] = {}
    if plan["tests"]:
        print("… pytest", flush=True)
        status, detail = run_pytest(plan["tests"])
        results["pytest"] = {"status": status, "detail": detail}
    for tool in plan["tools"]:
        print(f"… {tool}", flush=True)
        status, detail = TOOL_RUNNERS[tool]()
        results[tool] = {"status": status, "detail": detail}

    fp = build_fingerprint(head, base, changed, plan, results, dirty)
    default_out = _git("rev-parse", "--git-path", "affected_tests_fp.json").stdout.strip()
    out = Path(args.out or default_out)
    out.write_text(json.dumps(fp, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n=== النتيجة ===")
    failed = [k for k, v in results.items() if v["status"] == FAIL]
    missing = [k for k, v in results.items() if v["status"] == MISSING]
    for name, res in results.items():
        mark = {OK: "✔", FAIL: "✘", MISSING: "؟"}[res["status"]]
        label = {OK: "نجح", FAIL: "فشل", MISSING: "غير مقيس"}[res["status"]]
        print(f"{mark} {name}: {label}")
        if res["detail"]:
            print("    " + res["detail"].replace("\n", "\n    "))
    print(f"\nبصمة affected_tests: head={head[:8]} sha256={fp['digest'][:16]}  ({out})")

    if failed:
        print("لا تدفع: فحصٌ فشل (سيسقط في CI نفسه).")
        return 1
    if dirty and not args.allow_dirty:
        print("لا تدفع: الشجرةُ فيها تعديلٌ غيرُ مودَع — البصمةُ لا تغطّي الرأس وحده.")
        return 1
    if missing:
        print("غيرُ مقيس: ما قيس لا يكفي حكماً — شغّله ببيئةٍ فيها المتطلّبات.")
        return 3
    note = " (لا يعني السلامة: لا حارسَ مطابقاً لبعض الملفّات)" if plan["unmatched"] or not plan["tests"] else ""
    print(f"كلُّ المطلوب نجح{note}. مساعدٌ للمطوِّر لا حاجزٌ ولا مرجعٌ للاعتماد.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

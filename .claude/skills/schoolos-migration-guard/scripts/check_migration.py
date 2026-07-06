#!/usr/bin/env python3
"""
check_migration.py — حارس ترحيلات SchoolOS
تحليل ثابت (AST) + فحوصات Django لأمان الـ migrations قبل النشر على الإنتاج.

الاستخدام:
    python check_migration.py --app operations
    python check_migration.py --file operations/migrations/0017_x.py
    python check_migration.py --pending
    python check_migration.py --app assessments --sql   # يستدعي sqlmigrate لكشف الأقفال

يخرج برمز 1 عند وجود بند 🔴 حرج (مناسب لبوابة CI).
"""
from __future__ import annotations

import argparse
import ast
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # جذر المشروع D:\shschool_mvp

CRITICAL, WARNING, OK = "CRITICAL", "WARNING", "OK"
ICON = {CRITICAL: "🔴", WARNING: "🟠", OK: "🟢"}

# جداول كبيرة/حسّاسة يُمنع قفلها الحاجز
HOT_TABLES = {"attendance", "grade", "session", "audit", "enrollment", "notification"}
# جداول تحمل حقولاً مشفّرة (PDPPL) — أي backfill يجب أن يمرّ عبر ORM
ENCRYPTED_MODELS = {"healthrecord", "customuser"}

SCHEMA_OPS = {
    "AddField", "RemoveField", "AlterField", "RenameField", "AddIndex",
    "RemoveIndex", "AddConstraint", "RemoveConstraint", "CreateModel",
    "DeleteModel", "RenameModel", "AlterUniqueTogether", "AlterModelTable",
}
DATA_OPS = {"RunPython", "RunSQL"}


def _kw(call: ast.Call, name: str):
    for k in call.keywords:
        if k.arg == name:
            return k.value
    return None


def _is_true(node) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _field_call(addfield: ast.Call):
    """يعيد Call الخاص بوسيطة field= داخل AddField/AlterField."""
    fv = _kw(addfield, "field")
    return fv if isinstance(fv, ast.Call) else None


def _model_of(call: ast.Call) -> str:
    mv = _kw(call, "model_name") or _kw(call, "name")
    if isinstance(mv, ast.Constant) and isinstance(mv.value, str):
        return mv.value.lower()
    return ""


def _op_name(call: ast.Call) -> str:
    f = call.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return ""


def analyze_file(path: Path) -> list[tuple[str, str]]:
    """يعيد قائمة (severity, message)."""
    findings: list[tuple[str, str]] = []
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))

    ops_calls: list[ast.Call] = []
    atomic_false = "atomic = False" in src or "atomic=False" in src

    # اجمع كل استدعاءات العمليات داخل operations = [...]
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "operations":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        ops_calls += [e for e in node.value.elts if isinstance(e, ast.Call)]

    op_names = [_op_name(c) for c in ops_calls]
    has_schema = any(n in SCHEMA_OPS for n in op_names)
    has_data = any(n in DATA_OPS for n in op_names)

    if has_schema and has_data:
        findings.append((CRITICAL,
            "خلط تعديل schema مع تعبئة بيانات (RunPython/RunSQL) في ملف واحد → "
            "افصلهما إلى ملفين لتجنّب تعارض الأقفال."))

    for c in ops_calls:
        name = _op_name(c)
        model = _model_of(c)
        hot = any(h in model for h in HOT_TABLES)
        enc = any(e in model for e in ENCRYPTED_MODELS)

        if name == "AddField":
            fc = _field_call(c)
            null_true = _is_true(_kw(fc, "null")) if fc else False
            has_default = (_kw(fc, "default") is not None) if fc else False
            if not null_true and not has_default:
                findings.append((CRITICAL,
                    f"AddField على «{model}» بعمود NOT NULL بلا default → "
                    "إعادة كتابة الجدول + قفل. أضِفه null=True أولاً ثم backfill ثم NOT NULL."))
            elif not null_true and has_default:
                findings.append((WARNING,
                    f"AddField على «{model}» بـ default على جدول قد يكون كبيراً — "
                    "آمن على PostgreSQL 16 فقط إذا كان default ثابتاً غير متقلّب."))
            if fc and (_is_true(_kw(fc, "unique")) or _is_true(_kw(fc, "db_index"))):
                findings.append((WARNING,
                    f"AddField على «{model}» يبني فهرساً (unique/db_index) بقفل — "
                    "استخدم AddIndexConcurrently + atomic=False."))

        elif name in {"RemoveField", "DeleteModel"}:
            findings.append((CRITICAL,
                f"{name} على «{model}» → فقد بيانات ويكسر الكود القديم أثناء النشر المتدحرج. "
                "أوقف الاستخدام وانشر أولاً، ثم احذف في إصدار لاحق."))

        elif name in {"RenameField", "RenameModel"}:
            findings.append((CRITICAL,
                f"{name} على «{model}» → الكود المنشور يقرأ الاسم القديم فيفشل. "
                "استخدم نمط أضِف-جديد/انسخ/أوقف-قديم بدل إعادة التسمية المباشرة."))

        elif name == "AlterField":
            sev = CRITICAL if hot else WARNING
            findings.append((sev,
                f"AlterField على «{model}» — إن كان يغيّر النوع/الطول/NULL فقد يعيد كتابة "
                "الجدول ويقفله. افحص sqlmigrate وتأكد من التوافق الرجعي."))

        elif name in {"AddIndex", "AddConstraint", "AlterUniqueTogether"}:
            if not atomic_false:
                findings.append((WARNING,
                    f"{name} على «{model}» يقفل الجدول. على PostgreSQL 16 استخدم "
                    "AddIndexConcurrently (مع atomic=False) أو أنشئ القيد NOT VALID ثم VALIDATE."))

        elif name == "RunPython":
            if _kw(c, "reverse_code") is None:
                findings.append((CRITICAL,
                    "RunPython بلا reverse_code → لا يمكن التراجع عند فشل النشر. "
                    "مرّر reverse_code أو migrations.RunPython.noop صراحةً."))
            if enc:
                findings.append((WARNING,
                    f"RunPython يمسّ model مشفّراً «{model}» — استخدم ORM (لا raw SQL) "
                    "ليمرّ عبر التشفير/HMAC وإلا تُخزَّن بيانات صريحة (خرق PDPPL)."))

        elif name == "RunSQL":
            findings.append((WARNING,
                "RunSQL يدوي — تأكد من reverse_sql، ومن أنه لا يلمس حقولاً مشفّرة، "
                "ومن عدم إحداث قفل حاجز على جدول كبير."))

    # عمليات متزامنة تتطلب atomic=False
    if any(n in {"AddIndexConcurrently", "RemoveIndexConcurrently"} for n in op_names) and not atomic_false:
        findings.append((CRITICAL,
            "AddIndexConcurrently يتطلب atomic = False في صنف Migration وإلا يفشل."))

    if not findings:
        findings.append((OK, "لا مخاطر ثابتة مكتشفة — راجع الحجم الفعلي للجدول يدوياً."))
    return findings


def run_django(cmd: list[str]) -> tuple[int, str]:
    env = dict(os.environ)
    env.setdefault("DJANGO_SETTINGS_MODULE", "shschool.settings.development")
    try:
        p = subprocess.run([sys.executable, "manage.py", *cmd], cwd=ROOT,
                           capture_output=True, text=True, env=env, timeout=120)
        return p.returncode, (p.stdout + p.stderr)
    except Exception as e:  # noqa: BLE001
        return -1, f"تعذّر تشغيل manage.py {' '.join(cmd)}: {e}"


def collect_files(args) -> list[Path]:
    if args.file:
        return [ROOT / args.file if not Path(args.file).is_absolute() else Path(args.file)]
    if args.app:
        return sorted((ROOT / args.app / "migrations").glob("[0-9]*.py"))
    if args.pending:
        code, out = run_django(["showmigrations", "--plan"])
        files: list[Path] = []
        for line in out.splitlines():
            if "[ ]" in line:  # غير مطبّق
                parts = line.replace("[ ]", "").strip().split(".")
                if len(parts) >= 2:
                    app, mig = parts[0], parts[1]
                    f = ROOT / app / "migrations" / f"{mig}.py"
                    if f.exists():
                        files.append(f)
        return files
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description="حارس ترحيلات SchoolOS")
    ap.add_argument("--app", help="اسم التطبيق (يفحص كل migrations فيه)")
    ap.add_argument("--file", help="ملف migration محدد")
    ap.add_argument("--pending", action="store_true", help="كل الترحيلات غير المطبّقة")
    ap.add_argument("--sql", action="store_true", help="استدعِ sqlmigrate لكشف الأقفال")
    args = ap.parse_args()

    print("═" * 70)
    print("  حارس ترحيلات SchoolOS")
    print("═" * 70)

    # 1) فحص فروق models بلا migration
    code, out = run_django(["makemigrations", "--check", "--dry-run"])
    if code == 0:
        print("🟢 makemigrations --check: لا توجد models معدّلة بلا migration.")
    elif code > 0:
        print("🟠 makemigrations --check: توجد تغييرات models بلا migration:")
        print("   " + out.strip().replace("\n", "\n   "))
    else:
        print(f"ℹ️  {out.strip()}")

    files = collect_files(args)
    if not files:
        print("\nلم تُحدَّد ملفات. استخدم --app أو --file أو --pending.")
        return 0

    worst = OK
    for f in files:
        if f.name == "__init__.py" or not f.exists():
            continue
        print(f"\n── {f.relative_to(ROOT)} " + "─" * max(0, 50 - len(f.name)))
        for sev, msg in analyze_file(f):
            print(f"  {ICON[sev]} {msg}")
            if sev == CRITICAL:
                worst = CRITICAL
            elif sev == WARNING and worst != CRITICAL:
                worst = WARNING

        if args.sql and args.app:
            num = f.name.split("_")[0]
            c2, sql = run_django(["sqlmigrate", args.app, num])
            if c2 == 0:
                risky = [ln for ln in sql.splitlines()
                         if "ACCESS EXCLUSIVE" in ln.upper() or "REWRITE" in ln.upper()]
                if risky:
                    print("  🔴 SQL يحتوي أقفالاً حاجزة:")
                    for ln in risky:
                        print("     " + ln.strip())
                else:
                    print("  🟢 SQL بلا أقفال حاجزة ظاهرة.")

    print("\n" + "═" * 70)
    print(f"  الحصيلة: {ICON[worst]} {worst}")
    print("═" * 70)
    return 1 if worst == CRITICAL else 0


if __name__ == "__main__":
    raise SystemExit(main())

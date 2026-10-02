#!/usr/bin/env python3
"""
check_migration.py — حارسُ هجرات SchoolOS قبل الدفع.

طبقتان:
  1) تحليلٌ ثابت (AST) لملفّ الهجرة: ماذا تفعل كلُّ عمليّة، ولماذا تخطر، وما البديلُ المعتمد في المشروع.
  2) مع --sql: يولّد SQL الفعليّ بـ`sqlmigrate` ويصنّف جملَه، ثمّ — إن كانت حزمةُ
     django-migration-linter مثبّتةً (وهي في صورة الحاوية) — يمرّرها على محلّلها نفسِه
     الذي تستدعيه بوّابةُ `migration-linter` في CI، فترى حكمَ البوّابة قبل الدفع.

لا يحلّ محلّ البوّابة؛ يسبقها ويشرح.

الاستخدام (داخل حاوية جلستك — --sql و--pending يحتاجان Django والقاعدة):
    python .claude/skills/schoolos-migration-guard/scripts/check_migration.py --file operations/migrations/0056_x.py
    python .claude/skills/schoolos-migration-guard/scripts/check_migration.py --file <مسار> --sql
    python .claude/skills/schoolos-migration-guard/scripts/check_migration.py --app operations --since 0050
    python .claude/skills/schoolos-migration-guard/scripts/check_migration.py --pending --sql
    python manage.py sqlmigrate operations 0056 | python <هذا السكربت> --sql-stdin

رمزُ الخروج: 1 إن وُجد بندٌ حرج (🔴)، و2 لخطأ استعمال، وإلّا 0.
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
from pathlib import Path

# جذرُ الشجرة: scripts ← schoolos-migration-guard ← skills ← .claude ← الجذر
ROOT = Path(__file__).resolve().parents[4]

CRITICAL, WARNING, OK = "CRITICAL", "WARNING", "OK"
ICON = {CRITICAL: "🔴", WARNING: "🟠", OK: "🟢"}
RANK = {OK: 0, WARNING: 1, CRITICAL: 2}

DESTRUCTIVE = {"RemoveField", "DeleteModel", "RenameField", "RenameModel", "AlterModelTable"}
SCHEMA_OPS = {
    "AddField", "RemoveField", "AlterField", "RenameField", "AddIndex", "RemoveIndex",
    "AddConstraint", "RemoveConstraint", "CreateModel", "DeleteModel", "RenameModel",
    "AlterUniqueTogether", "AlterIndexTogether", "AlterModelTable",
    "AddIndexConcurrently", "RemoveIndexConcurrently",
}
DATA_OPS = {"RunPython", "RunSQL"}
CONCURRENT_OPS = {"AddIndexConcurrently", "RemoveIndexConcurrently"}


# ─────────────────────────── أدوات AST ───────────────────────────

def _kw(call: ast.Call | None, name: str):
    if call is None:
        return None
    for k in call.keywords:
        if k.arg == name:
            return k.value
    return None


def _arg(call: ast.Call, pos: int, name: str):
    """قيمةُ وسيطٍ بالاسم أو بالموضع — RunPython(forward, backward) شائعٌ في المشروع."""
    v = _kw(call, name)
    if v is None and len(call.args) > pos:
        v = call.args[pos]
    return v


def _is_const(node, value) -> bool:
    return isinstance(node, ast.Constant) and node.value is value


def _name(call: ast.Call) -> str:
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")


def _str(node) -> str:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else ""


def _model_of(call: ast.Call) -> str:
    for key in ("model_name", "name", "old_name"):
        s = _str(_kw(call, key))
        if s:
            return s.lower()
    return _str(call.args[0]).lower() if call.args else ""


def _field_call(call: ast.Call) -> ast.Call | None:
    fv = _arg(call, 2, "field")
    return fv if isinstance(fv, ast.Call) else None


def _atomic_false(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for stmt in node.body:
                if (isinstance(stmt, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == "atomic" for t in stmt.targets)
                        and _is_const(stmt.value, False)):
                    return True
    return False


def _collect_ops(tree: ast.Module) -> list[ast.Call]:
    """عمليّاتُ `operations = [...]`، مع فكّ database_operations في SeparateDatabaseAndState
    (state_operations لا تلمس القاعدة فلا تُفحص)."""
    top: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "operations" for t in node.targets):
            if isinstance(node.value, (ast.List, ast.Tuple)):
                top += [e for e in node.value.elts if isinstance(e, ast.Call)]
    out: list[ast.Call] = []
    for c in top:
        if _name(c) == "SeparateDatabaseAndState":
            db_ops = _kw(c, "database_operations")
            if isinstance(db_ops, (ast.List, ast.Tuple)):
                out += [e for e in db_ops.elts if isinstance(e, ast.Call)]
        else:
            out.append(c)
    return out


# ───────────────────── نماذجُ المشروع الحسّاسة ─────────────────────

def encrypted_models(root: Path = ROOT) -> set[str]:
    """نماذجُ فيها حقلٌ مشفّر (EncryptedTextField) أو عمودٌ `*_encrypted` يملؤه save().
    تُستخرج من الشيفرة الحيّة لا من قائمةٍ ثابتةٍ تتقادم."""
    found: set[str] = set()
    files = list(root.glob("*/models.py")) + list(root.glob("*/models/*.py"))
    for f in files:
        try:
            src = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for block in re.split(r"(?m)^(?=class \w+\()", src):
            m = re.match(r"class (\w+)\(", block)
            if m and ("EncryptedTextField(" in block or re.search(r"_encrypted\s*=\s*models\.", block)):
                found.add(m.group(1).lower())
    return found


# ─────────────────────────── تحليلُ الملفّ ───────────────────────────

def analyze_file(path: Path, enc_models: set[str] | None = None) -> list[tuple[str, str]]:
    """يعيد قائمة (الخطورة، الرسالة) لملفّ هجرةٍ واحد."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))
    ops = _collect_ops(tree)
    atomic_false = _atomic_false(tree)
    names = [_name(c) for c in ops]
    created = {(_str(_kw(c, "name")) or _str(c.args[0] if c.args else None)).lower()
               for c in ops if _name(c) == "CreateModel"}
    enc_models = encrypted_models() if enc_models is None else enc_models
    f: list[tuple[str, str]] = []

    if any(n in SCHEMA_OPS for n in names) and any(n in DATA_OPS for n in names):
        f.append((WARNING, "تعديلُ مخطّطٍ وRunPython/RunSQL في ملفٍّ واحد — على PostgreSQL تجري الهجرةُ "
                           "في معاملةٍ واحدة فتطول الأقفال، وقد تسقط بـ«pending trigger events». "
                           "الأسلمُ ملفّان (وثائق Django: RunPython)."))

    for c in ops:
        op, model = _name(c), _model_of(c)
        fresh = model in created  # جدولٌ يُنشأ في الملفّ نفسِه — فارغٌ فلا قفلَ يُخشى

        if op == "AddField":
            fc = _field_call(c)
            if fc is None:
                f.append((WARNING, f"AddField «{model}»: تعذّرت قراءةُ الحقل ثابتاً — شغّل --sql."))
                continue
            ftype = _name(fc)
            if ftype == "ManyToManyField" or fresh:
                continue  # جدولٌ وسيطٌ جديد، لا عمودَ على جدولٍ قائم
            null = _is_const(_kw(fc, "null"), True)
            unique = _is_const(_kw(fc, "unique"), True)
            default, db_default = _kw(fc, "default"), _kw(fc, "db_default")
            if not null and db_default is None:
                if default is None:
                    f.append((CRITICAL, f"AddField «{model}»: عمودٌ NOT NULL بلا افتراض — يُسقط الإضافةَ على جدولٍ فيه "
                                        "صفوف، وتُسقطه بوّابةُ CI (NOT NULL). البديل: null=True، أو db_default=."))
                else:
                    f.append((CRITICAL, f"AddField «{model}»: default= بلا db_default= — Django يضيف العمودَ بافتراضٍ ثمّ "
                                        "يُسقطه من القاعدة (DROP DEFAULT)، فالنسخةُ القديمة أثناء النشر تكتب صفّاً بلا "
                                        "العمود فيسقط، وبوّابةُ CI تُسقطه (NOT NULL). أضِف db_default= بالقيمة نفسِها "
                                        "(سابقة: operations/migrations/0053_excuse_review.py)."))
            if unique and default is not None and not isinstance(default, ast.Constant):
                f.append((CRITICAL, f"AddField «{model}»: default قابلٌ للاستدعاء مع unique=True — يُحسب مرّةً واحدة "
                                    "لكلّ الصفوف القائمة فيتكرّر ويسقط القيد. أضِفه null=True ثمّ املأه ثمّ قيّده "
                                    "(وثائق Django: Migrations that add unique fields)."))
            elif unique:
                f.append((CRITICAL, f"AddField «{model}» unique=True على جدولٍ قائم — يبني قيداً فريداً بقفل، "
                                    "وبوّابةُ CI تُسقطه (ADDING unique constraint)."))
            elif _is_const(_kw(fc, "db_index"), True) or ftype in {"ForeignKey", "OneToOneField"}:
                f.append((WARNING, f"AddField «{model}» ({ftype or 'حقل'}) يبني فهرساً/قيداً على جدولٍ قائم بقفل "
                                   "الكتابة — على جدولٍ كبير: db_index=False ثمّ AddIndexConcurrently."))

        elif op in DESTRUCTIVE:
            f.append((CRITICAL, f"{op} «{model}» — هدّامٌ أو يكسر الشيفرةَ المنشورة (القديمةُ تقرأ الاسمَ/العمود القديم). "
                                "«توسيعٌ ثمّ تقليص»: الحذفُ/إعادةُ التسمية خطوةٌ ثانية في إصدارٍ لاحق بعد "
                                "أن يتوقّف كلُّ قارئٍ وكاتب. وبوّابةُ CI تُسقطه (CLAUDE.md، قسم الهجرات)."))

        elif op == "AlterField":
            f.append((WARNING, f"AlterField «{model}» — قد يكون بلا SQL (verbose_name/help_text/choices) وقد "
                               "يغيّر النوعَ أو NULL فيعيد كتابة الجدول. شغّل --sql: «(no-op)» آمن، و"
                               "ALTER COLUMN TYPE أو SET NOT NULL تُسقطهما بوّابةُ CI."))

        elif op in {"AddIndex", "AlterIndexTogether"} and not fresh:
            f.append((WARNING, f"{op} «{model}» يبني فهرساً بقفل الكتابة — على جدولٍ كبير AddIndexConcurrently "
                               "مع atomic = False (سابقة: operations/migrations/0055_attendance_exit_partial_index.py)."))

        elif op in {"AddConstraint", "AlterUniqueTogether"} and not fresh:
            cons = _arg(c, 1, "constraint")
            kind = _name(cons) if isinstance(cons, ast.Call) else ""
            if op == "AlterUniqueTogether" or kind == "UniqueConstraint":
                f.append((CRITICAL, f"{op} «{model}»: قيدٌ فريدٌ على جدولٍ قائم — يفحص الجدولَ كلَّه بقفل، وبوّابةُ CI "
                                    "تُسقطه (ADDING unique constraint). القرارُ في مراجعة الطلب."))
            else:
                f.append((WARNING, f"{op} «{model}» ({kind or 'قيد'}) يفحص الجدولَ كلَّه بقفل — على جدولٍ كبير "
                                   "أنشئه NOT VALID ثمّ VALIDATE في هجرةٍ لاحقة (RunSQL + SeparateDatabaseAndState)."))

        elif op == "RunPython":
            if _arg(c, 1, "reverse_code") is None:
                f.append((CRITICAL, "RunPython بلا reverse_code — لا تراجعَ عند فشل النشر. مرّر دالّةً عكسيّة، أو "
                                    "migrations.RunPython.noop صراحةً مع سببٍ في التعليق (CI يحذّر فقط؛ المهارةُ أشدّ)."))

        elif op == "RunSQL":
            if _arg(c, 1, "reverse_sql") is None:
                f.append((CRITICAL, "RunSQL بلا reverse_sql — لا تراجعَ عند فشل النشر (أو migrations.RunSQL.noop صراحةً)."))
            f.append((WARNING, "RunSQL يدويّ — تحقّق ألّا يكتب حقلاً مشفّراً نصّاً صريحاً ولا يقفل جدولاً كبيراً."))

    if any(n in CONCURRENT_OPS for n in names) and not atomic_false:
        f.append((CRITICAL, "AddIndexConcurrently/RemoveIndexConcurrently يلزمهما `atomic = False` في صنف Migration، "
                            "وإلّا فشلت الهجرة (CONCURRENTLY لا يجري داخل معاملة)."))

    if "RunPython" in names:
        touched = {m.lower() for m in re.findall(r"get_model\(\s*[\"']\w+[\"']\s*,\s*[\"'](\w+)[\"']", src)}
        hit = touched & enc_models
        if hit and not re.search(r"\b(encrypt_field|hmac_field)\b", src):
            f.append((WARNING, f"RunPython يمسّ نموذجاً بحقولٍ مشفّرة ({', '.join(sorted(hit))}) ولا يستدعي "
                               "encrypt_field/hmac_field — النموذجُ التاريخيّ لا يشغّل save() فلا تُحسب أعمدةُ "
                               "*_encrypted و*_hmac تلقائيّاً (سابقة صحيحة: core/migrations/0020_populate_national_id_hmac_encrypted.py)."))
        if touched:
            f.append((OK, "تذكير: النموذجُ التاريخيّ في RunPython بلا دوالّ النموذج (save/خصائص) وبلا مديراتٍ "
                          "مخصّصة (.live() وأمثالُها) — اكتب الاستعلامَ صريحاً."))

    if not any(sev != OK for sev, _ in f):
        f.append((OK, "لا مخاطرَ ثابتةً مكتشفة — راجع حجمَ الجدول وشغّل --sql للتأكّد."))
    return f


# ─────────────────────────── تصنيفُ SQL ───────────────────────────

_TABLE = r'"?(\w+)"?'


def sql_statements(sql: str) -> list[str]:
    out = []
    for line in sql.splitlines():
        s = line.strip()
        if not s or s.startswith("--") or s.upper() in {"BEGIN;", "COMMIT;"}:
            continue
        out.append(s)
    return out


def analyze_sql(sql: str) -> list[tuple[str, str]]:
    """يصنّف جملَ sqlmigrate. الجداولُ المنشأةُ في SQL نفسِه تُستثنى من تحذيرات الأقفال."""
    stmts = sql_statements(sql)
    created = {m.group(1) for s in stmts for m in [re.match(r"CREATE TABLE " + _TABLE, s, re.I)] if m}
    added_not_null = set()
    f: list[tuple[str, str]] = []
    for s in stmts:
        up = s.upper()
        t = re.match(r"(?:ALTER TABLE|CREATE (?:UNIQUE )?INDEX(?: CONCURRENTLY)?(?: IF NOT EXISTS)? \S+ ON) " + _TABLE, s, re.I)
        table = t.group(1) if t else ""
        fresh = table in created
        col = re.search(r'ADD COLUMN "?(\w+)"?', s, re.I)
        if col and "NOT NULL" in up:
            added_not_null.add((table, col.group(1)))
            if " DEFAULT " not in up:
                f.append((CRITICAL, f"{table}: ADD COLUMN NOT NULL بلا DEFAULT — {s}"))
        if "DROP DEFAULT" in up:
            dc = re.search(r'ALTER COLUMN "?(\w+)"? DROP DEFAULT', s, re.I)
            if dc and (table, dc.group(1)) in added_not_null:
                f.append((CRITICAL, f"{table}.{dc.group(1)}: الافتراضُ يُسقط بعد الإضافة → كتابةُ النسخة القديمة "
                                    f"تسقط على NOT NULL؛ استعمل db_default= — {s}"))
        if "SET NOT NULL" in up:
            f.append((CRITICAL, f"{table}: SET NOT NULL — يفحص الجدولَ كلَّه بقفلٍ ويكسر كتابةَ القديم — {s}"))
        if re.search(r"ALTER COLUMN \S+ TYPE", s, re.I):
            f.append((CRITICAL, f"{table}: تغييرُ نوع عمود — قد يعيد كتابةَ الجدول بقفلٍ حاجز، وCI يُسقطه — {s}"))
        if re.search(r"\bDROP (COLUMN|TABLE)\b", up) or re.search(r"\bRENAME\b", up):
            f.append((CRITICAL, f"{table}: حذفٌ أو إعادةُ تسمية — خطوةُ «تقليص» في إصدارٍ لاحق — {s}"))
        if not fresh and "ADD CONSTRAINT" in up and " UNIQUE" in up:
            f.append((CRITICAL, f"{table}: قيدٌ فريدٌ على جدولٍ قائم — CI يُسقطه — {s}"))
        elif not fresh and "ADD CONSTRAINT" in up and ("FOREIGN KEY" in up or " CHECK " in up) and "NOT VALID" not in up:
            f.append((WARNING, f"{table}: قيدٌ يُتحقَّق منه على الجدول كلِّه بقفل (بلا NOT VALID) — {s}"))
        if up.startswith("CREATE") and " INDEX " in f" {up} " and "CONCURRENTLY" not in up and not fresh:
            f.append((WARNING, f"{table}: CREATE INDEX بلا CONCURRENTLY يقفل الكتابة — {s}"))
    if not stmts:
        f.append((OK, "لا جملَ SQL (no-op) — عمليّةُ حالةٍ فقط."))
    elif not f:
        f.append((OK, "جملُ SQL بلا نمطٍ خطِرٍ معروف."))
    return f


def ci_linter_verdict(sql: str) -> list[tuple[str, str]]:
    """حكمُ محلّل django-migration-linter (ما تستدعيه بوّابةُ CI) إن كانت الحزمةُ مثبّتة."""
    try:
        from django_migration_linter.sql_analyser.analyser import analyse_sql_statements
        from django_migration_linter.sql_analyser.postgresql import PostgresqlAnalyser
    except Exception:  # noqa: BLE001 — الحزمةُ اختياريّة خارج الحاوية
        return [(OK, "django-migration-linter غير مثبّت هنا — حكمُ البوّابة يُرى في CI أو داخل الحاوية.")]
    errors, _ignored, warnings = analyse_sql_statements(PostgresqlAnalyser, sql_statements(sql))
    out = [(CRITICAL, f"[مدقّق CI] خطأ: {e.code} — {e.message}") for e in errors]
    out += [(WARNING, f"[مدقّق CI] تحذير: {w.code} — {w.message}") for w in warnings]
    return out or [(OK, "[مدقّق CI] لا أخطاءَ ولا تحذيرات على هذا الـSQL.")]


# ─────────────────────────── Django ───────────────────────────

def run_django(cmd: list[str]) -> tuple[int, str]:
    if not (ROOT / "manage.py").exists():
        return -1, f"لا manage.py في {ROOT}"
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    try:
        p = subprocess.run([sys.executable, "manage.py", *cmd], cwd=ROOT, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", env=env, timeout=180)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:  # noqa: BLE001
        return -1, f"تعذّر تشغيل manage.py {' '.join(cmd)}: {e}"


def app_and_name(path: Path) -> tuple[str, str]:
    return path.parent.parent.name, path.stem


def collect_files(args) -> list[Path]:
    if args.file:
        p = Path(args.file)
        return [p if p.is_absolute() else ROOT / p]
    if args.app:
        files = sorted((ROOT / args.app / "migrations").glob("[0-9]*.py"))
        return [p for p in files if not args.since or p.name[:4] >= args.since]
    if args.pending:
        code, out = run_django(["showmigrations", "--plan"])
        if code != 0:
            print(f"تعذّر showmigrations: {out.strip()[-400:]}")
            return []
        files = []
        for line in out.splitlines():
            m = re.match(r"\s*\[ \]\s+(\w+)\.(\w+)", line)
            if m and (ROOT / m.group(1) / "migrations" / f"{m.group(2)}.py").exists():
                files.append(ROOT / m.group(1) / "migrations" / f"{m.group(2)}.py")
        return files
    return []


def _show(findings, worst: str) -> str:
    for sev, msg in findings:
        print(f"  {ICON[sev]} {msg}")
        if RANK[sev] > RANK[worst]:
            worst = sev
    return worst


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):  # طرفيّةُ ويندوز: العربيّةُ والرموزُ تسقط بترميز cp1252
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="حارس هجرات SchoolOS")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--file", help="ملفُّ هجرةٍ (نسبةً إلى جذر الشجرة أو مطلق)")
    g.add_argument("--app", help="كلُّ هجرات تطبيق (مع --since لتضييقها)")
    g.add_argument("--pending", action="store_true", help="الهجراتُ غيرُ المطبّقة على قاعدة جلستك")
    g.add_argument("--sql-stdin", action="store_true", help="صنِّف SQL يُمرَّر على الدخل القياسيّ")
    ap.add_argument("--since", help="مع --app: أوّلُ رقمٍ يُفحص (مثل 0050)")
    ap.add_argument("--sql", action="store_true", help="ولِّد SQL بـsqlmigrate وصنِّفه ومرِّره على مدقّق CI")
    ap.add_argument("--no-makemigrations", action="store_true", help="لا تشغّل makemigrations --check")
    args = ap.parse_args()

    worst = OK
    if args.sql_stdin:
        sql = sys.stdin.read()
        worst = _show(analyze_sql(sql) + ci_linter_verdict(sql), worst)
        print(f"\nالحصيلة: {ICON[worst]} {worst}")
        return 1 if worst == CRITICAL else 0

    files = collect_files(args)
    if not files:
        print("لا ملفّات. استعمل --file أو --app أو --pending أو --sql-stdin (انظر --help).")
        return 2

    print("═" * 70 + "\n  حارس هجرات SchoolOS\n" + "═" * 70)
    if not args.no_makemigrations:
        code, out = run_django(["makemigrations", "--check", "--dry-run"])
        if code == 0:
            print("🟢 makemigrations --check: لا نماذجَ معدّلةً بلا هجرة.")
        elif "Migrations for" in out:
            print("🟠 makemigrations --check: تغييراتُ نماذج بلا هجرة:\n   " + out.strip().replace("\n", "\n   "))
        else:  # خطأ تشغيل لا «تغييرات» — لا يُخلط بينهما
            print(f"ℹ️  تعذّر makemigrations --check (شغّل داخل حاوية الجلسة): {out.strip()[-300:]}")

    enc = encrypted_models()
    missing = False
    for f in files:
        if not f.exists():
            print(f"\n── غير موجود: {f}")
            missing = True
            continue
        try:
            shown = f.relative_to(ROOT).as_posix()
        except ValueError:
            shown = str(f)
        print(f"\n── {shown}")
        worst = _show(analyze_file(f, enc), worst)
        if args.sql:
            app, name = app_and_name(f)
            code, sql = run_django(["sqlmigrate", app, name])
            if code != 0:
                print(f"  ℹ️  تعذّر sqlmigrate {app} {name}: {sql.strip()[-300:]}")
                continue
            print("  ── SQL:")
            worst = _show(analyze_sql(sql) + ci_linter_verdict(sql), worst)

    print("\n" + "═" * 70 + f"\n  الحصيلة: {ICON[worst]} {worst}\n" + "═" * 70)
    if worst == CRITICAL:
        return 1
    return 2 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())

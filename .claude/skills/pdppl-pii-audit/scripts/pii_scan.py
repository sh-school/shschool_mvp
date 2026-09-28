#!/usr/bin/env python3
"""
pii_scan.py — مدقّق PDPPL الاستدلاليّ لـ SchoolOS.

يفحص ثلاثة أشياء في شيفرة بايثون:
  (1) حقولَ نماذجَ نصّيّةً أسماؤها تدلّ على بيانٍ شخصيّ ولا مرافقَ مشفَّرٌ لها،
  (2) مُسلسِلاتٍ (serializers) تعرض حقلاً شخصيّاً أو كلَّ الحقول (`__all__`)،
  (3) نداءاتِ تسجيلٍ أو طباعةٍ تُدرج قيمةً شخصيّة.

الاستعمال (من جذر المستودع أو من شجرة العمل):
    python .claude/skills/pdppl-pii-audit/scripts/pii_scan.py
    python .claude/skills/pdppl-pii-audit/scripts/pii_scan.py --app clinic
    python .claude/skills/pdppl-pii-audit/scripts/pii_scan.py --serializers-only
    python .claude/skills/pdppl-pii-audit/scripts/pii_scan.py --logs-only --include-tests
    python .claude/skills/pdppl-pii-audit/scripts/pii_scan.py --root D:/path/to/checkout

النتائجُ مرشَّحاتٌ لمراجعةٍ بشريّة لا أحكام. رمزُ الخروج: 0 سليم، 1 عند بندٍ «حرج»،
2 إن لم يُفحص أيُّ ملفّ (جذرٌ خاطئ — لا يُعلَن «سليم» على ما لم يُقرأ).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# مجلّداتٌ لا تُفحص: تُقارَن بأجزاء المسار **نسبةً إلى الجذر** لا بالمسار المطلق —
# شجرةُ العمل تقع تحت `.claude/worktrees/…` فلو قورن المطلقُ لتُخطّي كلُّ ملفٍّ فيها.
SKIP_DIRS = {
    ".venv", "venv", "node_modules", "__pycache__", ".git", "migrations",
    "staticfiles", "_archive", ".claude", "worktrees",
}

# فئاتُ الأسماء (مقاطعُ جزئيّة، بأحرفٍ صغيرة) — الخطورةُ عند التخزين الصريح.
SPECIAL = ["allerg", "chronic", "medication", "diagnos", "blood_type", "disease",
           "psycholog", "mental_", "disabilit", "religion", "ethnic", "medical"]
PII = ["national_id", "iqama", "qid", "passport", "phone", "mobile", "address",
       "birth", "_dob", "dob_", "iban", "bank_", "salary"]
LOW = ["email", "photo", "avatar", "postal"]

# أسماءٌ تحمل مقطعاً شخصيّاً لكنّها ليست بياناً شخصيّاً: عنوانُ رسالةٍ أو قالبُها أو تسميتُها.
NON_PII_SUFFIXES = ("_subject", "_template", "_label", "_help_text", "_format", "_count")

PLAINTEXT_FIELDS = ("CharField", "TextField", "EmailField", "GenericIPAddressField")
FIELD_RE = re.compile(r"^\s*([a-zA-Z_]\w*)\s*=\s*(?:models\.)?(\w+)\s*\(")
SERIALIZER_FIELDS_RE = re.compile(
    r"fields\s*=\s*(\[[^\]]*\]|\([^)]*\)|[\"']__all__[\"'])", re.S
)
# مسجِّلٌ (`logger`، `log`، `audit_log`…) بمستوى، أو `print` كلمةً كاملة (لا `blueprint(`).
LOG_RE = re.compile(
    r"\b\w*log\w*\.(?:debug|info|warning|error|exception|critical)\s*\(|\bprint\s*\("
)

LEVEL_TAG = {"CRITICAL": "[حرج]", "HIGH": "[عالٍ]", "INFO": "[معلومة]"}


def find_root(explicit: str | None) -> Path:
    """الجذر: المعطى صراحةً، وإلّا أقربُ سلفٍ لمجلّد التشغيل فيه `manage.py`، وإلّا موضعُ المهارة."""
    if explicit:
        return Path(explicit).resolve()
    here = Path.cwd().resolve()
    for candidate in (here, *here.parents):
        if (candidate / "manage.py").is_file():
            return candidate
    return Path(__file__).resolve().parents[4]


def iter_py(root: Path, sub: str | None, include_tests: bool):
    base = (root / sub) if sub else root
    if not base.exists():
        return
    for path in base.rglob("*.py"):
        rel_parts = path.relative_to(root).parts
        if any(part in SKIP_DIRS for part in rel_parts[:-1]):
            continue
        if not include_tests and (rel_parts[0] == "tests" or path.name.startswith("test_")):
            continue
        yield path


def categorize(name: str) -> tuple[str | None, str | None]:
    low = name.lower()
    if low.endswith(NON_PII_SUFFIXES):
        return None, None
    if "ip_address" in low:
        return "INFO", "عنوانُ IP بيانٌ شخصيّ — يحكمه الاحتفاظُ (docs/privacy/data_retention.md) لا التشفير"
    if any(k in low for k in SPECIAL):
        return "CRITICAL", "بيانٌ ذو طبيعةٍ خاصّة (PDPPL م.16)"
    if any(k in low for k in PII):
        return "HIGH", "بيانُ تعريفٍ شخصيّ"
    if any(k in low for k in LOW):
        return "INFO", "بيانٌ قد يكون شخصيّاً"
    return None, None


def scan_models(root: Path, files: list[Path]) -> list[tuple]:
    findings = []
    for path in files:
        if not (path.name == "models.py" or path.parent.name == "models"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        declared = set(re.findall(r"^\s*([a-zA-Z_]\w*)\s*=\s*(?:models\.|Encrypted)", text, re.M))
        for line_no, line in enumerate(text.splitlines(), 1):
            match = FIELD_RE.match(line)
            if not match:
                continue
            fname, ftype = match.group(1), match.group(2)
            if "Encrypted" in ftype or ftype not in PLAINTEXT_FIELDS:
                continue
            severity, label = categorize(fname)
            if not severity:
                continue
            # ثلاثيّةُ HMAC: خامٌ مقيَّد + `<name>_encrypted` + `<name>_hmac` (نمطُ core/models/user.py).
            if f"{fname}_encrypted" in declared or fname.endswith(("_hmac", "_encrypted")):
                continue
            rel = path.relative_to(root)
            if f"def set_{fname}" in text or f"def get_{fname}" in text:
                findings.append(("INFO", rel, line_no,
                                 f"{fname} = {ftype}(...) ← {label}: تشفيرٌ يدويٌّ عبر get/set — "
                                 f"الإسنادُ المباشر يتجاوزه؛ الأصلحُ EncryptedTextField الشفّاف."))
                continue
            advice = ("" if severity == "INFO" and "IP" in label
                      else " — EncryptedTextField أو ثلاثيّةُ HMAC، أو برّر أنّه ليس بياناً شخصيّاً.")
            findings.append((severity, rel, line_no, f"{fname} = {ftype}(...) ← {label}{advice}"))
    return findings


def scan_serializers(root: Path, files: list[Path]) -> list[tuple]:
    findings = []
    tokens = SPECIAL + PII
    for path in files:
        if "serializ" not in path.name:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for block in SERIALIZER_FIELDS_RE.finditer(text):
            body = block.group(1)
            line_no = text[: block.start()].count("\n") + 1
            rel = path.relative_to(root)
            if "__all__" in body:
                findings.append(("HIGH", rel, line_no,
                                 "fields = '__all__' يعرض كلَّ حقلٍ حاضراً ومستقبلاً — عدِّد الحقولَ صراحةً."))
                continue
            hits = sorted({t for t in tokens if t in body})
            if hits:
                findings.append(("HIGH", rel, line_no,
                                 f"مُسلسِلٌ يعرض: {', '.join(hits)} — تحقّق من الإذن والستر "
                                 f"(mask_national_id) ووفّر نسخةً بالاسم وحده."))
    return findings


def _call_text(lines: list[str], start: int, limit: int = 6) -> str:
    """نصُّ النداء من سطره حتى يتوازن القوسُ (أو `limit` أسطر) — فالقيمةُ في السطر التالي تُلتقط."""
    chunk, depth = [], 0
    for line in lines[start: start + limit]:
        chunk.append(line)
        depth += line.count("(") - line.count(")")
        if depth <= 0:
            break
    return "\n".join(chunk)


def scan_logs(root: Path, files: list[Path]) -> list[tuple]:
    findings = []
    tokens = SPECIAL + PII
    for path in files:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for idx, line in enumerate(lines):
            if not LOG_RE.search(line) or line.lstrip().startswith("#"):
                continue
            call = _call_text(lines, idx)
            hits = sorted({t for t in tokens
                           if f".{t}" in call or f"{t}=" in call or f"['{t}']" in call or f'["{t}"]' in call})
            if hits:
                findings.append(("CRITICAL", path.relative_to(root), idx + 1,
                                 f"تسجيلٌ أو طباعةٌ لقيمةٍ شخصيّة محتملة ({', '.join(hits)}) — سجّل المعرّفَ (UUID) لا القيمة."))
    return findings


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # طرفيّةُ ويندوز cp1252 تسقط على العربيّة
    parser = argparse.ArgumentParser(description="مدقّق PDPPL الاستدلاليّ لـ SchoolOS")
    parser.add_argument("--app", help="حصرُ الفحص بتطبيقٍ واحد (مجلّد)")
    parser.add_argument("--root", help="جذرُ المستودع (افتراضاً: أقربُ سلفٍ فيه manage.py)")
    parser.add_argument("--include-tests", action="store_true", help="افحص tests/ وملفّاتِ test_* أيضاً")
    only = parser.add_mutually_exclusive_group()
    only.add_argument("--models-only", action="store_true")
    only.add_argument("--serializers-only", action="store_true")
    only.add_argument("--logs-only", action="store_true")
    args = parser.parse_args()

    root = find_root(args.root)
    files = list(iter_py(root, args.app, args.include_tests))
    if not files:
        print(f"لم يُفحص أيُّ ملفٍّ تحت {root} — جذرٌ أو تطبيقٌ خاطئ؛ لا حكمَ بالسلامة.")
        return 2

    groups = []
    if not (args.serializers_only or args.logs_only):
        groups.append(("حقولُ نماذجَ غيرُ مشفّرة", scan_models(root, files)))
    if not (args.models_only or args.logs_only):
        groups.append(("عرضُ بياناتٍ شخصيّة في المُسلسِلات", scan_serializers(root, files)))
    if not (args.models_only or args.serializers_only):
        groups.append(("قيمٌ شخصيّةٌ في السجلّات والطباعة", scan_logs(root, files)))

    order = {"CRITICAL": 0, "HIGH": 1, "INFO": 2}
    total = {"CRITICAL": 0, "HIGH": 0, "INFO": 0}
    print("=" * 72)
    print(f"  مدقّق PDPPL — SchoolOS   الجذر: {root}   ملفّاتٌ مفحوصة: {len(files)}")
    print("=" * 72)
    for title, findings in groups:
        print(f"\n## {title} ({len(findings)})")
        if not findings:
            print("  لا شيء.")
            continue
        for severity, rel, line_no, msg in sorted(findings, key=lambda f: (order[f[0]], str(f[1]), f[2])):
            total[severity] += 1
            print(f"  {LEVEL_TAG[severity]} {rel.as_posix()}:{line_no}\n      {msg}")
    print("\n" + "=" * 72)
    print(f"  الحصيلة: حرج {total['CRITICAL']} · عالٍ {total['HIGH']} · معلومة {total['INFO']}")
    print("  راجع كلَّ بندٍ بسياقه قبل الحكم (references/30-scanner.md: الإيجابيّاتُ الكاذبة المعروفة).")
    print("=" * 72)
    return 1 if total["CRITICAL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

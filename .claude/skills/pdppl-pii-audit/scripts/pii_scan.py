#!/usr/bin/env python3
"""
pii_scan.py — مدقّق PDPPL الاستدلالي لـ SchoolOS
يفحص: (1) حقول models تحمل PII وليست مشفّرة، (2) serializers تعرض PII،
(3) سطور logging/print تسرّب PII.

الاستخدام:
    python pii_scan.py                 # المشروع كامل
    python pii_scan.py --app clinic
    python pii_scan.py --serializers-only
    python pii_scan.py --logs-only

النتائج مرشّحات لمراجعة بشرية، لا أحكام قاطعة. يخرج برمز 1 عند وجود بند CRITICAL.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]

SKIP = {".venv", "venv", "node_modules", "__pycache__", ".git", "worktrees",
        "migrations", "staticfiles", "_archive", ".claude"}

# فئات PII → الخطورة عند التخزين الصريح
SPECIAL = ["allerg", "chronic", "medication", "diagnos", "blood_type", "disease",
           "psycholog", "mental_", "disabilit", "religion", "ethnic", "medical"]
PII = ["national_id", "iqama", "qid", "passport", "phone", "mobile", "address",
       "birth", "_dob", "dob_", "iban", "bank_", "salary"]
LOW = ["email", "photo", "avatar", "postal"]

PLAINTEXT_FIELDS = ("CharField", "TextField", "EmailField", "GenericIPAddressField")
FIELD_RE = re.compile(r"^\s*([a-zA-Z_]\w*)\s*=\s*(?:models\.)?(\w+)\s*\(")
LOG_RE = re.compile(r"(logger\.\w+|print|\.warning|\.error|\.info|\.debug)\s*\(")


def _iter_py(sub: str | None):
    base = (ROOT / sub) if sub else ROOT
    if not base.exists():
        return
    for p in base.rglob("*.py"):
        if any(part in SKIP or part.startswith(".") for part in p.parts):
            continue
        yield p


def _cat(name: str):
    low = name.lower()
    if any(k in low for k in SPECIAL):
        return "CRITICAL", "بيانات ذات طبيعة خاصة (PDPPL م.16)"
    if any(k in low for k in PII):
        return "HIGH", "بيان تعريف شخصي (PII)"
    if any(k in low for k in LOW):
        return "INFO", "بيان قد يكون شخصياً"
    return None, None


def scan_models(sub):
    findings = []
    for p in _iter_py(sub):
        if not (p.name == "models.py" or p.parent.name == "models"):
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        field_names = set(re.findall(r"^\s*([a-zA-Z_]\w*)\s*=\s*(?:models\.|Encrypted)", text, re.M))
        for i, line in enumerate(lines, 1):
            m = FIELD_RE.match(line)
            if not m:
                continue
            fname, ftype = m.group(1), m.group(2)
            if "Encrypted" in ftype or ftype not in PLAINTEXT_FIELDS:
                continue
            sev, label = _cat(fname)
            if not sev:
                continue
            # مُدار عبر ثلاثية HMAC؟ (يوجد <name>_encrypted مرافق)
            if f"{fname}_encrypted" in field_names or fname.endswith(("_hmac", "_encrypted")):
                continue
            # تشفير يدوي عبر get_/set_ (نمط clinic.HealthRecord) — تحذير لا خطأ قاطع
            if f"def set_{fname}" in text or f"def get_{fname}" in text:
                findings.append(("INFO", str(p.relative_to(ROOT)), i,
                                 f"{fname} = {ftype}(...)  ← {label}: تشفير يدوي عبر get/set مكتشف — "
                                 f"تحقّق أن لا إسناد مباشر (obj.{fname}=…) يتجاوزه؛ يُفضّل EncryptedTextField الشفّاف."))
                continue
            findings.append((sev, str(p.relative_to(ROOT)), i,
                             f"{fname} = {ftype}(...)  ← {label} مخزّن صريحاً؛ "
                             f"استخدم EncryptedTextField أو ثلاثية HMAC."))
    return findings


def scan_serializers(sub):
    findings = []
    tokens = SPECIAL + PII
    for p in _iter_py(sub):
        if "serializ" not in p.name:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for block in re.finditer(r"fields\s*=\s*\[([^\]]*)\]", text, re.S):
            body = block.group(1)
            line_no = text[:block.start()].count("\n") + 1
            hits = sorted({t for t in tokens if t in body})
            if hits:
                findings.append(("HIGH", str(p.relative_to(ROOT)), line_no,
                                 f"serializer يعرض PII: {', '.join(hits)} — "
                                 f"تأكّد من permission، ووفّر نسخة «آمنة» بالاسم فقط."))
    return findings


def scan_logs(sub):
    findings = []
    tokens = SPECIAL + PII
    for p in _iter_py(sub):
        text = p.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), 1):
            if not LOG_RE.search(line):
                continue
            hits = sorted({t for t in tokens if f".{t}" in line or f"{t}=" in line
                           or f"['{t}']" in line or f'["{t}"]' in line})
            if hits:
                findings.append(("CRITICAL", str(p.relative_to(ROOT)), i,
                                 f"تسجيل/طباعة PII محتمل ({', '.join(hits)}) — "
                                 f"سجّل UUID فقط لا القيمة."))
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description="مدقّق PDPPL لـ SchoolOS")
    ap.add_argument("--app", help="حصر الفحص بتطبيق واحد")
    ap.add_argument("--serializers-only", action="store_true")
    ap.add_argument("--logs-only", action="store_true")
    args = ap.parse_args()
    sub = args.app

    groups = []
    if args.serializers_only:
        groups = [("عرض PII في Serializers", scan_serializers(sub))]
    elif args.logs_only:
        groups = [("تسريب PII في السجلّات", scan_logs(sub))]
    else:
        groups = [
            ("حقول models غير مشفّرة", scan_models(sub)),
            ("عرض PII في Serializers", scan_serializers(sub)),
            ("تسريب PII في السجلّات", scan_logs(sub)),
        ]

    icon = {"CRITICAL": "🔴", "HIGH": "🟠", "INFO": "🟢"}
    total = {"CRITICAL": 0, "HIGH": 0, "INFO": 0}
    print("═" * 74)
    print("  مدقّق PDPPL — SchoolOS")
    print("═" * 74)

    for title, findings in groups:
        print(f"\n### {title} ({len(findings)}) ###")
        if not findings:
            print("  🟢 لا شيء.")
            continue
        for sev, path, line, msg in sorted(findings, key=lambda x: x[0]):
            total[sev] = total.get(sev, 0) + 1
            print(f"  {icon.get(sev,'•')} {path}:{line}\n      {msg}")

    print("\n" + "═" * 74)
    print(f"  الحصيلة: 🔴 {total['CRITICAL']}   🟠 {total['HIGH']}   🟢 {total['INFO']}")
    print("  تذكير: راجع كل بند بوعي السياق قبل الحكم.")
    print("═" * 74)
    return 1 if total["CRITICAL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

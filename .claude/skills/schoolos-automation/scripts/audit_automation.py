#!/usr/bin/env python3
"""مدقّقُ قائمة فحص الأتمتة — فحصٌ نصّيٌّ ثابتٌ لملفّات الأتمتة في SchoolOS قبل «جاهزٌ للمعاينة».

يلتقط ما يُرى في النصّ من بنود `references/02-automation-checklist.md`: فشلٌ صامت، ومهلةٌ غائبة، واسمُ مهمّةٍ ضمنيّ،
وسرٌّ أو عنوانُ إنتاجٍ حرفيّ، ورقمٌ شخصيّ. لا يشغّل شيئاً ولا يلمس شبكة؛ وما لا يُرى نصّاً (عدمُ التكرار الفعليّ،
صحّةُ الإنذار) يبقى لحكم المراجع.

    python audit_automation.py <ملف> [<ملف> ...] [--kind workflow|celery|command|ps1|pyscript] [--json]

رمزُ الخروج: 0 لا FAIL، و1 وُجد FAIL، و2 خطأُ استعمالٍ أو ملفٌّ لا يُقرأ.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

try:  # PyYAML اختياريّ: بدونه تُفحص مسارات العمل نصّيّاً فقط
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

FAIL, WARN, INFO = "FAIL", "WARN", "INFO"
KINDS = ("workflow", "celery", "command", "ps1", "pyscript")

# أنماطُ الأسرار تُبنى من أجزاء فلا يطابق هذا الملفُّ نفسَه (نمطُ auto_backup.ps1)
SECRET_RE = re.compile(
    "("
    + "|".join(
        (
            "gh" + "p_[A-Za-z0-9]{20,}",
            "github" + "_pat_[A-Za-z0-9_]{20,}",
            "sk" + "-ant-[A-Za-z0-9_-]{10,}",
            "AK" + "IA[0-9A-Z]{16}",
            "xo" + "x[bp]-[A-Za-z0-9-]{10,}",
            "-----BEGIN [A-Z ]*PRIV" + "ATE KEY",
        )
    )
    + ")"
)
# عنوانُ خدمةٍ منشورةٍ حرفيّاً — المستودعُ عامّ فالعنوانُ متغيّرٌ لا نصّ
HOST_RE = re.compile(r"https?://[A-Za-z0-9.-]+\.up\.railway\.app")
# رقمٌ شخصيٌّ قطريّ محتمل (11 خانة تبدأ بـ2 أو 3) — feedback_no_real_ids_in_code
QID_RE = re.compile(r"(?<![\d+])\b[23]\d{10}\b")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
EMAIL_OK = ("noreply", "no-reply", "example.", ".local", "users.noreply.github.com")
SWALLOW_RE = re.compile(r"except(\s+[\w.(), ]+)?\s*:\s*(#[^\n]*)?\n\s*pass\b")


@dataclass
class Finding:
    level: str
    code: str
    message: str
    fix: str = ""


def detect_kind(path: Path, text: str) -> str:
    """نوعُ الملفّ من امتداده ومحتواه — يُتجاوز بـ--kind."""
    suffix = path.suffix.lower()
    posix = path.as_posix()
    if suffix in (".yml", ".yaml"):
        return "workflow"
    if suffix == ".ps1":
        return "ps1"
    if "management/commands/" in posix:
        return "command"
    # مزخرفٌ في أوّل السطر أو تعريفُ الجدول — لا ذكرُهما في نصٍّ أو تعبيرٍ نمطيّ
    if re.search(r"^\s*@(shared_task|app\.task)\b|^\s*app\.conf\.beat_schedule\s*=", text, re.M):
        return "celery"
    return "pyscript"


def generic_checks(path: Path, text: str) -> list[Finding]:
    out: list[Finding] = []
    if SECRET_RE.search(text):
        out.append(Finding(FAIL, "G-SECRET", "نمطُ سرٍّ حرفيٌّ في الملفّ", "انقله إلى متغيّر بيئةٍ أو secrets.* وأبطِل السرَّ المكشوف"))
    if HOST_RE.search(text):
        out.append(Finding(FAIL, "G-HOST", "عنوانُ خدمةٍ منشورةٍ مكتوبٌ حرفيّاً", "vars.PRODUCTION_URL أو إعدادٌ من البيئة بلا قيمةٍ احتياطيّةٍ حرفيّة"))
    if "tests/" not in path.as_posix() and QID_RE.search(text):
        out.append(Finding(FAIL, "G-QID", "رقمٌ من 11 خانةً يشبه رقماً شخصيّاً", "لا أرقامَ شخصيّةً في شيفرةٍ متتبَّعة؛ اقرأها من ملفٍّ متجاهَلٍ أو وسيط"))
    emails = [m for m in EMAIL_RE.findall(text) if not any(ok in m.lower() for ok in EMAIL_OK)]
    if emails:
        out.append(Finding(WARN, "G-EMAIL", f"{len(emails)} عنوانُ بريدٍ حرفيّ", "لا بياناتٍ شخصيّة في الشيفرة أو السجلّ"))
    return out


def _triggers(doc: dict) -> dict:
    """PyYAML يقرأ المفتاحَ on قيمةً منطقيّة True."""
    trig = doc.get("on", doc.get(True, {}))
    if isinstance(trig, str):
        return {trig: None}
    if isinstance(trig, list):
        return {t: None for t in trig}
    return trig or {}


def workflow_checks(text: str) -> list[Finding]:
    out: list[Finding] = []
    doc = None
    if yaml is not None:
        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError:
            return [Finding(FAIL, "W-YAML", "YAML غيرُ صالح")]
    trig = _triggers(doc) if isinstance(doc, dict) else {}
    scheduled = "schedule" in trig if trig else bool(re.search(r"^\s*schedule:", text, re.M))
    if not re.search(r"^concurrency:", text, re.M):
        out.append(Finding(WARN, "W-CONCURRENCY", "لا concurrency: تشغيلان قد يتداخلان", "group ثابت، وcancel-in-progress: false لما لا يُقطع"))
    if not re.search(r"^permissions:", text, re.M):
        out.append(Finding(WARN, "W-PERMS", "لا permissions صريحة", "أدنى حدّ: contents: read (+ issues: write لإبلاغ الفشل)"))
    if isinstance(doc, dict):
        for name, job in (doc.get("jobs") or {}).items():
            if isinstance(job, dict) and "uses" not in job and "timeout-minutes" not in job:
                out.append(Finding(WARN, "W-TIMEOUT", f"الوظيفة {name} بلا timeout-minutes", "سقفٌ صريحٌ أقصرُ من الدورة"))
    if "| tee" in text and "pipefail" not in text:
        out.append(Finding(WARN, "W-PIPEFAIL", "`| tee` بلا pipefail يُخفي فشلَ السكربت", "set -euo pipefail في أوّل run"))
    if not scheduled:
        return out
    if "failure()" not in text:
        out.append(Finding(FAIL, "W-FAILNOTIFY", "مسارٌ مجدولٌ بلا خطوة if: failure() — فشلُه صامت",
                           "قضيّةٌ موسومةٌ تُفتح أو يُعلَّق عليها وتُغلق بالنجاح (nightly.yml)، أو جسرٌ موثَّقٌ إلى المنصّة"))
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.search(r"cron:\s*[\"']([^\"']+)[\"']", line)
        if not match:
            continue
        minute, hour = (match.group(1).split() + ["*", "*"])[:2]
        sub_hour = minute.startswith("*") or hour.startswith("*") or "/" in hour
        # التعليقُ بالتوقيتين على سطر cron أو السطر الذي قبله؛ ولا معنى له لوتيرةٍ دون الساعة
        near = line + (lines[index - 1] if index else "")
        if not sub_hour and not re.search(r"UTC|الدوحة|قطر|Qatar", near):
            out.append(Finding(WARN, "W-CRON-TZ", f"cron «{match.group(1)}» بلا تعليقٍ بالتوقيتين", "# HH:MM UTC = HH:MM الدوحة (UTC+3)"))
        if sub_hour:
            out.append(Finding(WARN, "W-SUBHOUR", f"cron «{match.group(1)}» دون الساعة — جدولةُ GitHub بأفضل جهد",
                               "لا تبنِ عليه إنذارَ غياب؛ نبضةٌ في المنصّة أو مشغّلٌ بحدث"))
    title = doc.get("name", "") if isinstance(doc, dict) else ""
    if re.search(r"كلَّ \d+ (?:دقيقة|دقائق)", str(title)):
        out.append(Finding(WARN, "W-CLAIM", "العنوانُ يَعِد بوتيرةٍ لا تضمنها جدولةُ GitHub", "«بأفضل جهد» و«ثانويّ» (test_monitoring_claims_are_honest)"))
    return out


def celery_checks(text: str) -> list[Finding]:
    out: list[Finding] = []
    # نصُّ المزخرف كلُّه حتى `def` — الوسائطُ قد تحمل أقواساً (autoretry_for=(…,)) وقد تمتدّ أسطراً
    for match in re.finditer(r"^\s*@(shared_task|app\.task)(?P<args>.*?)^\s*(?:async\s+)?def\s", text, re.M | re.S):
        args = match.group("args") or ""
        line = text.count("\n", 0, match.start()) + 1
        if "name=" not in args:
            out.append(Finding(FAIL, "C-NAME", f"سطر {line}: مهمّةٌ بلا name= صريح",
                               "اسمٌ ثابت app.verb_noun — نقلُ الملفّ يغيّر الاسمَ الافتراضيّ فيُرسل beat اسماً بلا عامل"))
        if "time_limit" not in args:
            out.append(Finding(WARN, "C-TIMELIMIT", f"سطر {line}: بلا soft_time_limit/time_limit (يقع على 300/600 العامّين)", "مهلةٌ أقصرُ من دورة الجدول"))
        if re.search(r"autoretry_for\s*=\s*\(\s*Exception\b", args):
            out.append(Finding(WARN, "C-RETRY-ALL", f"سطر {line}: إعادةُ محاولةٍ على كلّ استثناء", "العابرُ وحده (شبكة، مهلة)"))
    out.extend(_python_common(text, prefix="C"))
    return out


def command_checks(text: str) -> list[Finding]:
    out: list[Finding] = []
    writes = re.search(r"\.(save|delete|update|bulk_create|bulk_update|create)\(", text)
    if writes and "--apply" not in text and "--dry-run" not in text:
        out.append(Finding(WARN, "M-APPLY", "أمرٌ يكتب بلا --apply/--dry-run", "عرضٌ افتراضاً وكتابةٌ بـ--apply (نمط enforce_retention)"))
    if re.search(r"^\s*print\(", text, re.M):
        out.append(Finding(WARN, "M-PRINT", "print في أمر إدارة", "self.stdout.write"))
    out.extend(_python_common(text, prefix="M", allow_print=True))
    return out


def _python_common(text: str, prefix: str, allow_print: bool = False) -> list[Finding]:
    out: list[Finding] = []
    if SWALLOW_RE.search(text):
        out.append(Finding(WARN, f"{prefix}-SWALLOW", "except … pass يكتم الفشل", "سجّل واكتب حالةً أو أعِد الرفع"))
    if not allow_print and prefix == "C" and re.search(r"^\s*print\(", text, re.M):
        out.append(Finding(WARN, "C-PRINT", "print في مهمّة", "logger — يمرّ بفلتر pii_masking"))
    return out


def ps1_checks(text: str) -> list[Finding]:
    out: list[Finding] = []
    eap = re.search(r"\$ErrorActionPreference\s*=\s*['\"]?(\w+)", text, re.I)
    if not eap or eap.group(1).lower() != "stop":
        out.append(Finding(FAIL, "P-EAP", "$ErrorActionPreference ليس Stop — الأخطاءُ تُكتم",
                           "$ErrorActionPreference = 'Stop' (حادثة نسخ الذاكرة 05-13←09-28)"))
    # الأسطرُ التعليقيّةُ مستثناة، وكذا ما كتمانُه مقصودٌ ولا يغيّر النتيجة (حذفٌ اختياريّ، بحثٌ نصّيّ، قراءة)
    silent = [i + 1 for i, line in enumerate(text.splitlines())
              if re.search(r"SilentlyContinue", line, re.I) and not line.lstrip().startswith("#")
              and not re.search(r"Remove-Item|Unregister|Select-String|Get-", line, re.I)]
    if silent:
        out.append(Finding(WARN, "P-SILENT", f"SilentlyContinue في الأسطر {silent[:5]}", "لا تكتم خطوةً جوهريّة"))
    if not re.search(r"\bexit\s+(1|\$\w+)", text, re.I):
        out.append(Finding(FAIL, "P-EXIT", "لا رمزَ خروجٍ غيرُ صفريٍّ عند الفشل", "exit 1 في فرع الفشل فتراه جدولةُ ويندوز"))
    if not re.search(r"Mutex|\.lock\b|LockFile", text, re.I):
        out.append(Finding(WARN, "P-LOCK", "لا قفلَ ضدّ التداخل", "Mutex باسمٍ ثابت وتخطٍّ هادئ"))
    if not re.search(r"FAILED|LAST_STATUS", text):
        out.append(Finding(WARN, "P-STATUS", "لا ملفَّ حالةٍ ولا علامةَ فشل", "LAST_STATUS.json و<NAME>_FAILED.txt (03-output-contract.md)"))
    if re.search(r"^\s*&?\s*git\s", text, re.M | re.I) and "$LASTEXITCODE" not in text:
        out.append(Finding(WARN, "P-LASTEXIT", "أوامرُ خارجيّةٌ بلا فحص $LASTEXITCODE", "دالّةٌ تفحص الرمزَ وترمي (Git-Run في auto_backup.ps1)"))
    return out


def pyscript_checks(text: str) -> list[Finding]:
    out: list[Finding] = []
    if not re.search(r"sys\.exit\(|raise SystemExit", text):
        out.append(Finding(FAIL, "S-EXIT", "لا sys.exit برمزٍ عند الفشل", "sys.exit(main()) ورمزٌ غيرُ صفريٍّ لكلّ فرع فشل"))
    if SWALLOW_RE.search(text):
        out.append(Finding(WARN, "S-SWALLOW", "except … pass يكتم الفشل", "سجّل واكتب حالةً أو أعِد الرفع"))
    naive = [m.start() for m in re.finditer(r"datetime\.now\(\s*\)", text)
             if not text[m.end():m.end() + 14].startswith(".astimezone(")]
    if naive:
        out.append(Finding(WARN, "S-NAIVE-TIME", f"{len(naive)} استدعاءٌ لـdatetime.now بلا منطقة", "أضِف .astimezone() فيُكتب الطابعُ بإزاحته"))
    if not re.search(r"O_EXCL|msvcrt|Mutex|\.lock\b|filelock", text):
        out.append(Finding(WARN, "S-LOCK", "لا قفلَ ضدّ التداخل", "ملفُّ قفلٍ بإنشاءٍ حصريّ (os.O_EXCL) بمهلةٍ للعالق"))
    if not re.search(r"FAILED|LAST_STATUS|status", text):
        out.append(Finding(WARN, "S-STATUS", "لا ملفَّ حالةٍ ولا علامةَ فشل", "LAST_STATUS.json و<NAME>_FAILED.txt"))
    return out


CHECKS = {"workflow": workflow_checks, "celery": celery_checks, "command": command_checks,
          "ps1": ps1_checks, "pyscript": pyscript_checks}


def audit(path: Path, kind: str | None = None) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    kind = kind or detect_kind(path, text)
    findings = generic_checks(path, text) + CHECKS[kind](text)
    return {"path": str(path), "kind": kind, "findings": [asdict(f) for f in findings]}


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap =argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--kind", choices=KINDS)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    reports = []
    for path in args.paths:
        if not path.is_file():
            print(f"لا يُقرأ: {path}", file=sys.stderr)
            return 2
        reports.append(audit(path, args.kind))
    if args.json:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
    else:
        for rep in reports:
            print(f"== {rep['path']} ({rep['kind']})")
            for f in rep["findings"] or [asdict(Finding(INFO, "OK", "لا ملاحظاتٍ نصّيّة — الحكمُ على البنود غير النصّيّة باقٍ"))]:
                print(f"[{f['level']}] {f['code']}: {f['message']}" + (f" ← {f['fix']}" if f["fix"] else ""))
    failed = any(f["level"] == FAIL for rep in reports for f in rep["findings"])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""بوّابةُ شروط الدمج الآليّ (W-20260929-016).

**أداةُ «0601 · النشر على الإنتاج والدمج» وحدَها** — الدمجُ والنشرُ من اختصاصها
حصراً (أمرُ المالك، نصُّ الفلو). لا تُشغَّل من جلسةٍ منفِّذة (04) ولا من 0501؛
هي من تستلم رقمَ الطلب في عقد التسليم ثمّ تشغّل هذه الأداةَ بنفسها وتقرّر.

لا تدمج شيئاً بنفسها — تُقرّر فقط: أيُفعَّل `gh pr merge --auto` على طلبٍ معيّن أم يبقى يدويّاً.

الشروطُ الأربعة (كلُّها لازمة):
  1. سطرُ اعتماد المالك موجودٌ حرفيّاً في وصف الطلب (نفسُ تعبير evidence_pack.py:
     يقبل صيغتَي «على 8500» و«مباشرةً بلا معاينة 8500» D-58م معاً).
  2. نطاقُ الملفّات المتغيّرة كلُّه خارج القائمة المحظورة (أمنٌ، صلاحيّات، هجرات).
  3. كلُّ فحوص CI المطلوبة خضراء (لا PENDING ولا FAILURE).
  4. فحصُ «مدقّق الهجرات — Expand/Contract» ضمن الفحوص الخضراء إن وُجد أصلاً في الطلب.

أيُّ طلبٍ يلمس مساراً محظوراً يبقى يدويّاً مهما اكتملت الشروطُ الأخرى — هذا مقصود
(W-016): الدمجُ الآليّ يُسقط فحصَ git diff البشريّ الذي يحمي هذه المناطق تحديداً.

الاستعمال:
    python scripts/auto_merge_gate.py <رقم الطلب> [--repo owner/name] [--enable]

بلا --enable: يطبع الحكمَ فقط (وضعُ الفحص الجاف). بـ--enable: يستدعي
`gh pr merge --auto` إن اجتمعت الشروط (لا --squash: طابورُ الدمج في هذا المستودع يفرض استراتيجيّتَه هو).
رمزُ الخروج: 0 = مسموحٌ بالدمج الآليّ (أو فُعِّل)، 1 = ممنوعٌ ويبقى يدويّاً، 2 = خطأ استعمال/شبكة.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

APPROVAL = re.compile(r"اعتُمد من المالك (?:على 8500|مباشرةً بلا معاينة 8500) — \d{4}-\d{2}-\d{2}")

# مساراتٌ محظورةٌ على الدمج الآليّ مهما اكتملت الشروطُ الأخرى (W-016).
# أنماطُ fnmatch/غلوب بسيطة تُطابَق مقابل كلّ مسارٍ متغيّر.
FORBIDDEN_GLOBS = (
    "*/security/*",
    "security/*",
    "*permissions*",
    "*/migrations/*",
    "*rbac*",
    "*roles*",
    "*Role*",
)

# (D-521م) «يمسّ:» سطرٌ في وصف الطلب يكتبه المشغّل من نصّ المهمّة نفسِه (لا النموذج): فئةٌ مذكورةٌ تُفتح مساراتُها لهذا الطلب وحده،
# بشرط فحصٍ إضافيّ أخضر؛ وفئةٌ غيرُ مذكورةٍ تبقى محظورةً كما كانت.
TOUCH_CATEGORIES = {
    "الأمن": ("*/security/*", "security/*"),
    "الصلاحيات": ("*permissions*",),
    "الأدوار": ("*rbac*", "*roles*", "*Role*"),
    "الهجرات": ("*/migrations/*",),
}
TOUCH_LINE = re.compile(r"^يمسّ:\s*(.+)$", re.MULTILINE)
TOUCH_REQUIRED_CHECK = {
    "الهجرات": "مدقّق الهجرات",
    "الأمن": "المسارات الحسّاسة",
    "الصلاحيات": "المسارات الحسّاسة",
    "الأدوار": "المسارات الحسّاسة",
}

REQUIRED_FAILING_STATES = {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED"}
PENDING_STATES = {"PENDING", "IN_PROGRESS", "QUEUED", "EXPECTED", "REQUESTED", "WAITING"}


def sh_json(args: list[str]) -> object:
    out = subprocess.run(args, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def declared_touches(body: str) -> set[str]:
    """الفئاتُ المذكورةُ في سطر «يمسّ:» (ما عُرف منها فقط)."""
    m = TOUCH_LINE.search(body or "")
    if not m:
        return set()
    return {t.strip() for t in re.split(r"[،,]", m.group(1)) if t.strip() in TOUCH_CATEGORIES}


def path_forbidden(path: str, allowed: set[str] | frozenset[str] = frozenset()) -> str | None:
    import fnmatch

    allowed_globs = {g for cat in allowed for g in TOUCH_CATEGORIES.get(cat, ())}
    for pattern in FORBIDDEN_GLOBS:
        if pattern in allowed_globs:
            continue
        if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path.lower(), pattern.lower()):
            return pattern
    return None


def evaluate(pr_number: str, repo: str | None) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    base = ["gh", "pr", "view", pr_number, "--json", "body,files,statusCheckRollup"]
    if repo:
        base += ["--repo", repo]
    data = sh_json(base)

    body = data.get("body") or ""
    if not APPROVAL.search(body):
        reasons.append(
            "سطرُ اعتماد المالك («اعتُمد من المالك على 8500 — YYYY-MM-DD» أو صيغة D-58م "
            "«اعتُمد من المالك مباشرةً بلا معاينة 8500 — YYYY-MM-DD») غيرُ موجودٍ حرفيّاً في وصف الطلب"
        )

    files = [f.get("path", "") for f in data.get("files") or []]
    blocked = []
    touches = declared_touches(body)
    for path in files:
        pattern = path_forbidden(path, touches)
        if pattern:
            blocked.append(f"{path} (يطابق {pattern})")
    if blocked:
        reasons.append("مساراتٌ محظورةٌ على الدمج الآليّ: " + "، ".join(blocked))

    checks = data.get("statusCheckRollup") or []
    for cat in sorted(touches):  # فئةٌ مذكورة ← فحصُها الإضافيّ لازمٌ وأخضر
        need = TOUCH_REQUIRED_CHECK[cat]
        hits = [c for c in checks if need in (c.get("name") or c.get("context") or "")]
        if not hits or any(
            (c.get("conclusion") or c.get("state") or "").upper() != "SUCCESS" for c in hits
        ):
            reasons.append(f"«يمسّ: {cat}» يلزمه فحصٌ أخضر «{need}»")
    if not checks:
        reasons.append("لا فحوصَ CI مسجَّلةٌ بعدُ على الطلب")
    else:
        for check in checks:
            state = (check.get("state") or check.get("conclusion") or "").upper()
            name = check.get("name") or check.get("context") or "؟"
            if state in REQUIRED_FAILING_STATES:
                reasons.append(f"فحصٌ فاشل: {name} ({state})")
            elif state in PENDING_STATES or not state:
                reasons.append(f"فحصٌ لم يكتمل بعدُ: {name} ({state or 'بلا حالة'})")

    return (not reasons), reasons


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pr_number")
    parser.add_argument("--repo")
    parser.add_argument("--enable", action="store_true", help="فعِّل auto-merge فعليّاً إن اجتمعت الشروط")
    args = parser.parse_args()

    try:
        ok, reasons = evaluate(args.pr_number, args.repo)
    except subprocess.CalledProcessError as exc:
        print(f"[خطأ] تعذّر قراءة الطلب: {exc.stderr.strip() if exc.stderr else exc}", file=sys.stderr)
        return 2
    except (json.JSONDecodeError, KeyError) as exc:
        print(f"[خطأ] استجابةٌ غيرُ متوقَّعة من gh: {exc}", file=sys.stderr)
        return 2

    if ok:
        print(f"[مسموح] الطلبُ #{args.pr_number} يستوفي شروطَ الدمج الآليّ")
        if args.enable:
            cmd = ["gh", "pr", "merge", args.pr_number, "--auto"]
            if args.repo:
                cmd += ["--repo", args.repo]
            subprocess.run(cmd, check=True)
            print("[تفعيل] auto-merge مفعَّلٌ على الطلب")
        return 0

    print(f"[ممنوع] الطلبُ #{args.pr_number} يبقى دمجاً يدويّاً:")
    for reason in reasons:
        print(f"  - {reason}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

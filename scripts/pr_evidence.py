#!/usr/bin/env python3
"""حزمةُ الأدلّة على كلّ طلب دمج — المرحلة 1 الحتميّة (MAE-09، W-20260928-016؛ D-50م: لا أتمتةَ خارج كود المنصّة).

كانت الحزمةُ تُجمع يدويّاً بأداةٍ خارج المستودع. هذه الأداةُ تنشر **تعليقاً واحداً** على الطلب (يُحدَّث في مكانه لا يتكرّر)
بما يُحسب حتميّاً من الطلب نفسِه، بلا شبكةٍ غيرِ GitHub ولا نموذج:
  - الخطورةُ من المسارات المتغيّرة (هجرةٌ وأمنٌ ← عالية، واجهةٌ وكودٌ ← متوسّطة، بنيةٌ ← منخفضة، وثائقُ واختباراتٌ ← خفيفة)؛
  - سطرُ اعتماد المالك في وصف الطلب (بالتعبير نفسِه الذي تعتمده بوّابةُ الدمج الآليّ `auto_merge_gate.py`)؛
  - المساراتُ المحظورةُ على الدمج الآليّ (هجراتٌ وأمنٌ وصلاحيّات) — من القائمة نفسِها فلا تتكرّر ولا تتباعد؛
  - الهجراتُ وما حُذف من ملفّات.

**معلوماتيّةٌ لا بوّابة**: لا تُفشل شيئاً ولا تمنع دمجاً. الفشلُ عند تجاوز ميزانيّةٍ مقيسةٍ هو المرحلة 2 وتلزمها قياساتُ MAE-08 على 8500.
وتصنيفُها مبسَّطٌ يوافق `risk_tier.py` في مستودع المايسترو للحالات الرئيسيّة؛ والمرجعُ لنافذة المراجعة أداةُ المايسترو.

لا نصَّ من وصف الطلب يدخل التعليق (بياناتٌ من طرفٍ آخر، وقد تحوي ما لا يُنشر): أعدادٌ وأسماءُ مساراتٍ وحالاتٌ فقط.

    python scripts/pr_evidence.py <رقم الطلب> [--repo owner/name] [--post]

بلا --post يطبع التعليقَ فقط. ومع --post يُنشئه أو يحدّثه؛ وإن لم يكن للرمز صلاحيّةُ كتابةٍ (طلبٌ من نسخةٍ شقيقة fork)
يطبع إشعاراً ويخرج بـ0 — فلا يسقط الطلبُ بسبب ما ليس خطأَه. رمزُ الخروج: 0 نجاح، 2 خطأُ قراءةٍ من GitHub.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import auto_merge_gate as gate  # noqa: E402  — القائمةُ المحظورةُ وتعبيرُ الاعتماد من مصدرٍ واحد

MARKER = "<!-- pr-evidence -->"

#: ترتيبُ الخطورة من الأعلى؛ والمجهولُ يُرفع إلى «عالية» (يفشل مغلقاً).
TIERS = ("عالية", "متوسّطة", "منخفضة", "خفيفة")
SENSITIVE_EXT = (
    ".csv",
    ".xlsx",
    ".xls",
    ".zip",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".dump",
    ".bak",
    ".sql",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
)
INFRA_PREFIX = (
    ".github/",
    "scripts/",
    ".claude/",
    "docker",
    "requirements",
    "Makefile",
    "pyproject",
    "railway",
)
UI_PREFIX = ("templates/", "static/")


def classify(path: str) -> str:
    """فئةُ الملفّ الواحد: «عالية» أو «متوسّطة» أو «منخفضة» أو «خفيفة»."""
    p = path.replace("\\", "/")
    base = p.rsplit("/", 1)[-1]
    if base.startswith(".env") or base.lower().endswith(SENSITIVE_EXT):
        return "عالية"
    if p.startswith("roadmap/migrations/"):
        return "خفيفة"  # هجراتُ الخارطة بياناتٌ تملكها جلسةُ الخارطة وتمرّ بحارسها
    if gate.path_forbidden(p) or "/settings/" in p:
        return "عالية"
    if p.startswith("tests/") or p.startswith("docs/") or p.endswith(".md"):
        return "خفيفة"
    if p.startswith(INFRA_PREFIX) or "docker-compose" in p:
        return "منخفضة"
    if p.startswith(UI_PREFIX) or p.endswith(".py"):
        return "متوسّطة"
    return "عالية"  # مجهول


def overall(files: list[str]) -> str:
    found = {classify(f) for f in files}
    return next((t for t in TIERS if t in found), "خفيفة")


def render(data: dict) -> str:
    """نصُّ التعليق من بياناتِ الطلب — أرقامٌ وأسماءُ مساراتٍ وحالاتٌ، لا نصَّ من الوصف."""
    files = [f.get("path", "") for f in data.get("files") or []]
    deleted = sum(
        1 for f in data.get("files") or [] if f.get("deletions", 0) and not f.get("additions", 0)
    )
    tier = overall(files)
    migrations = [f for f in files if "/migrations/" in f and not f.startswith("roadmap/")]
    blocked = [f for f in files if gate.path_forbidden(f)]
    approved = bool(gate.APPROVAL.search(data.get("body") or ""))
    lines = [
        MARKER,
        "### حزمةُ الأدلّة (آليّة، معلوماتيّة)",
        "",
        f"- **الخطورةُ من المسارات:** {tier} — عددُ الملفّات {len(files)}"
        + (f"، منها {deleted} حُذف كلُّه" if deleted else ""),
        f"- **سطرُ اعتماد المالك في الوصف:** {'موجود ✔' if approved else 'غيرُ موجود — لا يُدمج الطلبُ بدونه'}",
        f"- **هجراتٌ:** {', '.join(f'`{m}`' for m in migrations) if migrations else 'لا'}",
        "- **مساراتٌ محظورةٌ على الدمج الآليّ:** "
        + (f"{len(blocked)} — يبقى الدمجُ يدويّاً" if blocked else "لا"),
        "",
        "_المرحلةُ 1: تُحسب من المسارات والوصف وحدَها، ولا تمنع دمجاً. القياساتُ (حجم CSS، Web Vitals، الاستعلامات) تأتي في المرحلة 2._",
    ]
    return "\n".join(lines) + "\n"


def sh(args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, input=stdin, capture_output=True, text=True, encoding="utf-8")  # noqa: S603


def read_pr(number: str, repo: str | None) -> dict:
    cmd = ["gh", "pr", "view", number, "--json", "body,files"] + (["--repo", repo] if repo else [])
    out = sh(cmd)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or "تعذّرت قراءةُ الطلب")
    data: dict = json.loads(out.stdout)
    return data


def find_comment(number: str, repo: str) -> str | None:
    """معرّفُ تعليقنا السابق (بعلامته) إن وُجد — فيُحدَّث في مكانه."""
    out = sh(
        [
            "gh",
            "api",
            f"repos/{repo}/issues/{number}/comments",
            "--paginate",
            "-q",
            ".[]|[.id,.body]|@json",
        ]
    )
    if out.returncode != 0:
        return None
    for line in out.stdout.splitlines():
        comment_id, body = json.loads(line)
        if MARKER in (body or ""):
            return str(comment_id)
    return None


def post(number: str, repo: str, body: str) -> bool:
    """يُنشئ التعليقَ أو يحدّثه. يُرجع False إن رُفضت الكتابةُ (نسخةٌ شقيقة بلا صلاحيّة)."""
    existing = find_comment(number, repo)
    if existing:
        cmd = [
            "gh",
            "api",
            "-X",
            "PATCH",
            f"repos/{repo}/issues/comments/{existing}",
            "-F",
            "body=@-",
        ]
    else:
        cmd = ["gh", "api", "-X", "POST", f"repos/{repo}/issues/{number}/comments", "-F", "body=@-"]
    return sh(cmd, stdin=body).returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("pr_number")
    parser.add_argument("--repo")
    parser.add_argument("--post", action="store_true")
    args = parser.parse_args()
    try:
        text = render(read_pr(args.pr_number, args.repo))
    except (RuntimeError, json.JSONDecodeError) as exc:
        print(f"[خطأ] {exc}", file=sys.stderr)
        return 2
    print(text)
    if args.post:
        if not args.repo:
            print("[خطأ] --post يحتاج --repo", file=sys.stderr)
            return 2
        if not post(args.pr_number, args.repo, text):
            print("[تنبيه] لم يُنشر التعليق (لا صلاحيّةَ كتابةٍ على هذا الطلب) — لا يُسقط ذلك الفحص")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

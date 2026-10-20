#!/usr/bin/env python3
"""قائمةُ الخارطة المعلَّقة بعد كلّ نشرٍ ناجح — W-20261010-021 (قاعدة المالك D-50م: الأتمتة داخل كود المنصّة).

يعمل من `.github/workflows/roadmap-queue.yml` عند نجاح نشر production: يجد الطلباتِ المدموجةَ بين آخر نشرٍ ناجحٍ سابقٍ
والنشرِ الحاليّ، فيضع على كلٍّ منها الوسمَ `roadmap-pending` (إلّا ما يحمل `roadmap-synced`)، ويلحق **تعليقاً واحداً مجمَّعاً**
على issue ثابتِ العنوان يسرد الطلباتِ ورموزَ بطاقاتها لتحدّث جلسةُ الخارطة بنودَها. متساوي الأثر: التعليقُ يحمل علامةً
`roadmap-queue:<sha>` فلا يتكرّر لنشرٍ أُعيد تشغيلُه، والوسمُ لا يُعاد وضعُه. طلبٌ بلا رمز بطاقةٍ يُدرَج بتنبيه «بلا بند».
لا أسرارَ إلّا GITHUB_TOKEN؛ وأيُّ عطلٍ في GitHub API يُطبع تحذيراً ويخرج 0 (قائمةٌ إرشاديّةٌ لا تُسقط خطَّ النشر).

    python scripts/ci_roadmap_queue.py --repo OWNER/NAME --sha <commit المنشور> [--env "shschool_mvp / production"]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

PENDING = "roadmap-pending"
SYNCED = "roadmap-synced"
ISSUE_TITLE = "قائمة الخارطة المعلَّقة (roadmap-pending)"
CARD_RE = re.compile(r"\b(?:W|N)-\d{8}-\d{3}\b")
ENV_DEFAULT = "shschool_mvp / production"


def extract_cards(text: str | None) -> list[str]:
    """رموزُ البطاقات (W-… أو N-…) بترتيب ظهورها بلا تكرار."""
    return list(dict.fromkeys(CARD_RE.findall(text or "")))


def marker(sha: str) -> str:
    return f"<!-- roadmap-queue:{sha} -->"


def build_comment(sha: str, prs: list[dict]) -> str:
    """نصُّ التعليق المجمَّع؛ كلُّ طلبٍ سطرٌ برمز بطاقته أو «بلا بند»."""
    lines = [marker(sha), f"### نُشر `{sha[:7]}` — طلباتٌ تنتظر تحديثَ الخارطة ({len(prs)})", ""]
    for p in prs:
        cards = extract_cards(f"{p.get('title', '')}\n{p.get('body') or ''}")
        tag = "، ".join(cards) if cards else "⚠ بلا بند (لا رمزَ بطاقةٍ في العنوان ولا الوصف)"
        lines.append(f"- #{p['number']} — {p.get('title', '')[:90]} — {tag}")
    return "\n".join(lines)


def pending_prs(prs: list[dict]) -> list[dict]:
    """المدموجةُ التي لا تحمل `roadmap-synced`، بترتيب الرقم."""
    keep = [p for p in prs if SYNCED not in {lb["name"] for lb in p.get("labels", [])}]
    return sorted(keep, key=lambda p: p["number"])


def previous_success(api, repo: str, sha: str, env: str) -> str | None:
    """أحدثُ نشرٍ ناجحٍ سابقٍ للحاليّ بـcommit مختلف؛ None إن لم يوجد."""
    for d in (
        api("GET", f"repos/{repo}/deployments?environment={env.replace(' ', '%20')}&per_page=100")
        or []
    ):
        if d["sha"] == sha:
            continue
        sts = api("GET", f"repos/{repo}/deployments/{d['id']}/statuses?per_page=1") or []
        if sts and sts[0]["state"] == "success":
            return d["sha"]
    return None


def merged_between(api, repo: str, prev: str, sha: str) -> list[dict]:
    seen: dict[int, dict] = {}
    for c in (api("GET", f"repos/{repo}/compare/{prev}...{sha}") or {}).get("commits", []):
        for p in api("GET", f"repos/{repo}/commits/{c['sha']}/pulls") or []:
            if p.get("merged_at"):
                seen.setdefault(p["number"], p)
    return list(seen.values())


def queue_issue(api, repo: str) -> int:
    issues = api("GET", f"repos/{repo}/issues?state=open&labels={PENDING}&per_page=100") or []
    mine = [i for i in issues if not i.get("pull_request") and i.get("title") == ISSUE_TITLE]
    if mine:
        return mine[0]["number"]
    body = "قائمةٌ تُلحَق بها تعليقاتٌ آليّةٌ بعد كلّ نشر production (scripts/ci_roadmap_queue.py). تُغلقها جلسةُ الخارطة بعد المزامنة."
    return api(
        "POST", f"repos/{repo}/issues", {"title": ISSUE_TITLE, "labels": [PENDING], "body": body}
    )["number"]


def run(api, repo: str, sha: str, env: str = ENV_DEFAULT) -> str:
    """`api(method, path, payload=None)` ← JSON؛ تُحقَن في الاختبار. تعيد سطراً يصف ما جرى."""
    prev = previous_success(api, repo, sha, env)
    if not prev:
        return "لا نشرَ ناجحاً سابقاً: لا مدى للمقارنة"
    prs = pending_prs(merged_between(api, repo, prev, sha))
    if not prs:
        return "لا طلباتٍ جديدة منذ النشر السابق: لا شيء"
    for p in prs:
        if PENDING not in {lb["name"] for lb in p.get("labels", [])}:
            api("POST", f"repos/{repo}/issues/{p['number']}/labels", {"labels": [PENDING]})
    number = queue_issue(api, repo)
    comments = api("GET", f"repos/{repo}/issues/{number}/comments?per_page=100") or []
    if any(marker(sha) in (c.get("body") or "") for c in comments):
        return f"سبق التعليقُ لـ{sha[:7]} على #{number}: لا تكرار"
    api("POST", f"repos/{repo}/issues/{number}/comments", {"body": build_comment(sha, prs)})
    return f"وُسم {len(prs)} طلباً وعُلِّق على #{number}"


def gh_api(method: str, path: str, payload: dict | None = None):
    cmd = ["gh", "api", "-X", method, path]
    if payload is not None:
        cmd += ["--input", "-"]
    r = subprocess.run(  # noqa: S603
        cmd,
        input=json.dumps(payload) if payload is not None else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return json.loads(r.stdout) if r.stdout.strip() else None


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--sha", required=True)
    ap.add_argument("--env", default=ENV_DEFAULT)
    a = ap.parse_args(argv)
    try:
        print(run(gh_api, a.repo, a.sha, a.env))
    except (subprocess.CalledProcessError, KeyError, ValueError) as exc:
        print(f"::warning::تعذّر بناءُ قائمة الخارطة: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

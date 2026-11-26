#!/usr/bin/env python3
"""قائمةُ الخارطة المعلَّقة بعد كلّ نشرٍ ناجح — W-20261010-021 (قاعدة المالك D-50م: الأتمتة داخل كود المنصّة).

يعمل من `.github/workflows/roadmap-queue.yml` عند نجاح نشر production: يجد الطلباتِ المدموجةَ بين الأساس والنشرِ الحاليّ
(الأساسُ: sha آخر علامةٍ في تعليقات issue القائمة، وإلّا آخرُ نشرٍ ناجحٍ سابق)، فيضع على كلٍّ منها الوسمَ `roadmap-pending` (إلّا ما يحمل `roadmap-synced`)، ويلحق **تعليقاً واحداً مجمَّعاً**
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
from collections.abc import Callable
from typing import Any

PENDING = "roadmap-pending"
SYNCED = "roadmap-synced"
ISSUE_TITLE = "قائمة الخارطة المعلَّقة (roadmap-pending)"
CARD_RE = re.compile(r"\b(?:W|N)-\d{8}-\d{3}\b")
ENV_DEFAULT = "shschool_mvp / production"
MARKER_RE = re.compile(r"<!-- roadmap-queue:([0-9a-f]{7,40}) -->")
PAGE = 100
Api = Callable[..., Any]


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


def previous_success(api: Api, repo: str, sha: str, env: str) -> tuple[str | None, bool]:
    """(أحدثُ نشرٍ ناجحٍ سابقٍ بـcommit مختلف أو None، وهل وُجدت عملياتُ نشرٍ سابقةٌ أصلاً).

    GitHub يحوّل النشرَ الأقدمَ إلى inactive عند نجاح الأحدث، فيُفحص تاريخُ الحالات كلُّه لا آخرُها.
    """
    earlier = False
    for d in (
        api("GET", f"repos/{repo}/deployments?environment={env.replace(' ', '%20')}&per_page=100")
        or []
    ):
        if d["sha"] == sha:
            continue
        earlier = True
        sts = api("GET", f"repos/{repo}/deployments/{d['id']}/statuses?per_page={PAGE}") or []
        if any(st["state"] == "success" for st in sts):
            return d["sha"], True
    return None, earlier


def merged_between(api: Api, repo: str, prev: str, sha: str) -> list[dict]:
    seen: dict[int, dict] = {}
    page = 1
    while True:
        # بلا ترقيمٍ تقف المقارنةُ عند 250 إيداعاً
        path = f"repos/{repo}/compare/{prev}...{sha}?per_page={PAGE}&page={page}"
        commits = (api("GET", path) or {}).get("commits", [])
        for c in commits:
            for p in api("GET", f"repos/{repo}/commits/{c['sha']}/pulls") or []:
                if p.get("merged_at"):
                    seen.setdefault(p["number"], p)
        if len(commits) < PAGE:
            return list(seen.values())
        page += 1


def find_issue(api: Api, repo: str) -> int | None:
    issues = api("GET", f"repos/{repo}/issues?state=open&labels={PENDING}&per_page=100") or []
    mine = [i for i in issues if not i.get("pull_request") and i.get("title") == ISSUE_TITLE]
    return mine[0]["number"] if mine else None


def issue_comments(api: Api, repo: str, number: int) -> list[dict]:
    """كلُّ تعليقات issue بكلّ صفحاتها، من الأقدم إلى الأحدث."""
    out: list[dict] = []
    page = 1
    while True:
        path = f"repos/{repo}/issues/{number}/comments?per_page={PAGE}&page={page}"
        batch = api("GET", path) or []
        out.extend(batch)
        if len(batch) < PAGE:
            return out
        page += 1


def last_marker_sha(comments: list[dict]) -> str | None:
    """sha آخر علامة `roadmap-queue` في التعليقات؛ None إن لم توجد."""
    found = [sha for c in comments for sha in MARKER_RE.findall(c.get("body") or "")]
    return found[-1] if found else None


def create_issue(api: Api, repo: str) -> int:
    body = "قائمةٌ تُلحَق بها تعليقاتٌ آليّةٌ بعد كلّ نشر production (scripts/ci_roadmap_queue.py). تُغلقها جلسةُ الخارطة بعد المزامنة."
    return api(
        "POST", f"repos/{repo}/issues", {"title": ISSUE_TITLE, "labels": [PENDING], "body": body}
    )["number"]


def run(api: Api, repo: str, sha: str, env: str = ENV_DEFAULT) -> str:
    """`api(method, path, payload=None)` ← JSON؛ تُحقَن في الاختبار. تعيد سطراً يصف ما جرى."""
    number = find_issue(api, repo)
    comments = issue_comments(api, repo, number) if number else []
    if any(marker(sha) in (c.get("body") or "") for c in comments):
        return f"سبق التعليقُ لـ{sha[:7]} على #{number}: لا تكرار"
    # العلامةُ أوّلاً: ما فات من نشرٍ لم يُعلَّق عليه يبقى داخل المدى
    base = last_marker_sha(comments)
    if not base:
        base, earlier = previous_success(api, repo, sha, env)
        if not base and earlier:
            return "::warning::وُجدت عملياتُ نشرٍ سابقةٌ ولم يُحدَّد أساسٌ للمقارنة: لم تُبنَ القائمة"
    if not base:
        return "لا نشرَ ناجحاً سابقاً: لا مدى للمقارنة"
    prs = pending_prs(merged_between(api, repo, base, sha))
    if not prs:
        return "لا طلباتٍ جديدة منذ النشر السابق: لا شيء"
    for p in prs:
        if PENDING not in {lb["name"] for lb in p.get("labels", [])}:
            api("POST", f"repos/{repo}/issues/{p['number']}/labels", {"labels": [PENDING]})
    number = number or create_issue(api, repo)
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

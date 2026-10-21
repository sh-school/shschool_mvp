#!/usr/bin/env python3
"""تعليقٌ واحدٌ محدَّثٌ على كلّ طلبٍ أحمرَ حقيقيّ — W-20261003-009 (قاعدة المالك D-50م: الأتمتة داخل كود المنصّة).

يعمل من `.github/workflows/pr-red-comment.yml` بعد اكتمال بوّابة الجودة: يقرأ فحوصَ رأس الطلب، ويصنّفها بمنطق `pr_red.classify`
في مستودع المايسترو: **الأحمرُ الحقيقيّ** فشلٌ فعليّ (failure أو timed_out أو startup_failure أو action_required) في آخر تشغيلٍ لاسم الفحص؛
و**الملغى ليس أحمر** فلا يُعلَّق عليه، وفحصٌ ألغاه تشغيلٌ أحدثُ لنفس الاسم يُهمَل. فإن وُجد أحمرُ نُشر/حُدِّث تعليقٌ **واحدٌ** بعلامةٍ ثابتة
فيه: اسمُ الفحص وأوّلُ سطرِ خطأٍ من سجلّه وبطاقةُ الطلب؛ وإن عاد أخضرَ حُدِّث التعليقُ القائمُ إلى «تعافى» (لا تعليقٌ جديد، ولا حذف).

أمان: يعمل بـ`workflow_run` من فرع الأساس (لا يُنفَّذ شيءٌ من رأس الطلب)؛ ونصُّ سجلّ الفحص بياناتٌ من طرفٍ آخر فيُنقّى (طولٌ وحروفُ تحكّم
وإشاراتٌ `@` وأسوارُ الشيفرة) قبل أن يدخل التعليق. لا يدمج ولا يعتمد ولا يفشل خطَّ الدمج: أيُّ عطلٍ في GitHub يُطبع تحذيراً ويخرج 0.

    python scripts/ci_pr_red_comment.py --repo OWNER/NAME --pr N --sha <رأس الطلب>
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

MARKER = "<!-- pr-red -->"
REAL_FAIL = {"failure", "timed_out", "startup_failure", "action_required"}
CARD_RE = re.compile(r"W-\d{8}-\d{3}")
ERR_LINE = re.compile(r"(error|failed|assert|traceback|exception|✘|خطأ)", re.I)
BOT_LOGIN = "github-actions[bot]"
BOT_APP = "github-actions"
SECRETS = (
    re.compile(r"://[^/\s:@]+:[^/\s@]+@"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"eyJ[\w-]+\.[\w-]+\.[\w-]+"),
    re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key)\s*[=:]\s*\S+"),
)
MAX_ERR = 160


def _when(c: dict) -> str:
    return c.get("completed_at") or c.get("started_at") or ""


def classify(check_runs: list[dict]) -> dict:
    """آخرُ تشغيلٍ لكلّ اسمٍ: failed (حقيقيّ)، cancelled (بلا بديلٍ أحدث)، pending. مطابقٌ لـ`pr_red.classify`."""
    latest: dict[str, dict] = {}
    for i, c in enumerate(check_runs or []):
        name = c.get("name") or f"#{i}"
        if name not in latest or _when(c) >= _when(latest[name]):
            latest[name] = c
    out: dict[str, list[dict]] = {"failed": [], "cancelled": [], "pending": []}
    for c in latest.values():
        if c.get("status") != "completed":
            out["pending"].append(c)
        elif (c.get("conclusion") or "") in REAL_FAIL:
            out["failed"].append(c)
        elif c.get("conclusion") == "cancelled":
            out["cancelled"].append(c)
    return out


def card_of(pr: dict) -> str | None:
    m = CARD_RE.search(
        f"{pr.get('title', '')}\n{pr.get('body') or ''}\n{(pr.get('head') or {}).get('ref', '')}"
    )
    return m.group(0) if m else None


def job_id_of(check: dict, repo: str) -> str | None:
    """رقمُ الوظيفة من `details_url` بتطابقٍ تامٍّ مع مستودعنا، ومن تطبيق github-actions وحدَه؛ وإلا None (لا قراءةَ سجلٍّ غريب)."""
    if (check.get("app") or {}).get("slug") != BOT_APP:
        return None
    m = re.fullmatch(
        rf"https://github\.com/{re.escape(repo)}/actions/runs/\d+/job/(\d+)",
        check.get("details_url") or "",
    )
    return m.group(1) if m else None


def sanitize(text: str) -> str:
    """سطرُ الخطأ بيانات: بلا حروفِ تحكّمٍ ولا أسوارِ شيفرة ولا إشاراتٍ تُنبّه أحداً ولا وسومَ HTML ولا أسرارٍ ظاهرة."""
    s = "".join(ch for ch in text if ch.isprintable())
    for pat in SECRETS:
        s = pat.sub("***", s)
    s = s.replace("`", "'").replace("<", "‹").replace(">", "›").replace("@", "@​").replace("|", "¦")
    return s.strip()[:MAX_ERR]


def first_error(log_text: str) -> str:
    for ln in (log_text or "").splitlines():
        s = ln.split("\t")[-1].strip()
        s = re.sub(r"^\d{4}-\d{2}-\d{2}T\S+\s*", "", s)
        if ERR_LINE.search(s) and len(s) > 8:
            return sanitize(s)
    return ""


def build_comment(sha: str, failed: list[dict], card: str | None, errors: dict[str, str]) -> str:
    lines = [MARKER, f"### ⛔ فحصٌ أحمرُ حقيقيّ على الرأس `{sha[:8]}`", ""]
    lines.append(f"البطاقة: {card or 'لا رمزَ بطاقةٍ في العنوان ولا الوصف ولا اسم الفرع'}")
    lines.append("")
    for c in sorted(failed, key=lambda x: x.get("name", "")):
        name = sanitize(c.get("name", "؟"))
        err = errors.get(c.get("name", ""), "")
        lines.append(f"- `{name}`" + (f" — `{err}`" if err else " — (تعذّرت قراءةُ سطر الخطأ)"))
    lines += ["", "الملغى ليس أحمر. يُحدَّث هذا التعليقُ في مكانه عند كلّ تشغيلٍ جديد."]
    return "\n".join(lines)


def build_recovered(sha: str) -> str:
    return f"{MARKER}\n### ✔ تعافى الطلب — لا فحصَ أحمرَ حقيقيّاً على الرأس `{sha[:8]}`"


def run(api, log_reader, repo: str, pr_number: int, sha: str) -> str:
    """`api(method, path, payload=None)` ← JSON؛ و`log_reader(job_id)` ← نصّ سجلّ الوظيفة. تُحقنان في الاختبار."""
    pr = api("GET", f"repos/{repo}/pulls/{pr_number}") or {}
    if pr.get("state") != "open":
        return "الطلبُ غيرُ مفتوح: لا شيء"
    if (pr.get("head") or {}).get("sha") != sha:
        return "الرأسُ تقدّم عن المفحوص: يتولّاه التشغيلُ التالي"
    runs = (api("GET", f"repos/{repo}/commits/{sha}/check-runs?per_page=100") or {}).get(
        "check_runs", []
    )
    cls = classify(runs)
    comments = api("GET", f"repos/{repo}/issues/{pr_number}/comments?per_page=100") or []
    mine = next(
        (
            c
            for c in comments
            if (c.get("user") or {}).get("login") == BOT_LOGIN and MARKER in (c.get("body") or "")
        ),
        None,
    )
    if cls["failed"]:
        errors = {}
        for c in cls["failed"]:
            job = job_id_of(c, repo)
            errors[c.get("name", "")] = first_error(log_reader(job)) if job else ""
        body = build_comment(sha, cls["failed"], card_of(pr), errors)
    elif mine:
        if cls["pending"]:
            return "فحوصٌ قيدَ التشغيل: أنتظر نتيجتَها قبل إعلان التعافي"
        body = build_recovered(sha)
    else:
        return "لا أحمرَ حقيقيّاً ولا تعليقَ قائماً: لا شيء"
    if mine and (mine.get("body") or "").strip() == body.strip():
        return "التعليقُ محدَّثٌ مسبقاً: لا تكرار"
    if mine:
        api("PATCH", f"repos/{repo}/issues/comments/{mine['id']}", {"body": body})
        return f"حُدِّث التعليقُ على #{pr_number}"
    api("POST", f"repos/{repo}/issues/{pr_number}/comments", {"body": body})
    return f"نُشر تعليقٌ على #{pr_number}"


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


def gh_log(job_id: str, repo: str = "") -> str:
    p = subprocess.run(  # noqa: S603
        ["gh", "run", "view", "--job", job_id, "--log-failed", "-R", repo],  # noqa: S607
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    return p.stdout if p.returncode == 0 else ""


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--pr", type=int, required=True)
    ap.add_argument("--sha", required=True)
    a = ap.parse_args(argv)
    try:
        print(run(gh_api, lambda j: gh_log(j, a.repo), a.repo, a.pr, a.sha))
    except (subprocess.CalledProcessError, KeyError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"::warning::تعذّر تعليقُ الأحمر: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

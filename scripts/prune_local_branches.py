#!/usr/bin/env python3
"""فروعٌ محلّيّةٌ محتواها في main فعلاً — بالمحتوى لا بالسلفيّة (REP-10، RD5). يُستدعى عبر `scripts/prune_local_branches.sh`.

`delete_branch_on_merge` مفعَّلةٌ على المستودع، فيحذف GitHub فرعَ الطلب المدموج نفسَه. لكنّ الفرعَ المحلّيَّ لا يعرف عنه GitHub شيئاً،
والطابورُ يدمج بالسحق (squash) فلا يصير الفرعُ سلفاً لـmain مهما نجح: تتكاثر الفروعُ المحلّيّة يوماً بعد يومٍ ولا يُحذف منها شيء.

الحكمُ هنا **على المحتوى**. الفرعُ آمنٌ للحذف إن لم يُفقَد بحذفه شيءٌ لا يُسترجع من main، بأحد أدلّةٍ مرتَّبةٍ من الأقوى:

  SAFE_ANCESTOR         طرفُه سلفٌ لـmain (دمجٌ عاديّ)
  SAFE_TAGGED           يحويه وسمٌ (أرشيفٌ سابق — الاسترجاعُ `git branch <الاسم> <الوسم>`)
  SAFE_PR_MERGED        طرفُه هو رأسُ طلبٍ مدموجٍ أو سلفٌ له. **لا يكفي اسمُ الفرع**: فرعٌ أُعيد استعمالُ اسمه بعد الدمج وعليه إيداعاتٌ جديدة
                        ليس مدموجاً (كان الفحصُ القديم يثق باسم الرأس وحدَه فيحذف تلك الإيداعات)
  SAFE_CONTENT_IN_MAIN  كلُّ ملفٍّ غيّره الفرعُ منذ تفرّعه موجودٌ بنسخته الأخيرة (blob) في تاريخ main، وكلُّ حذفٍ فعله قد وقع في main —
                        أي دمجٌ مسحوقٌ أو ملتقَط (cherry-pick) أو مُعاد الكتابة

وما ليس عليه دليلٌ فهو REVIEW: محتوًى لا يوجد في main ولا في وسم — **لا يُحذف آليّاً أبداً**. يُحفَظ بـ`--archive` (وسمٌ موصوفٌ محلّيّ
غيرُ هدّام) فيصير SAFE_TAGGED في التشغيل التالي فيُحذف بلا فقدان (RD5: الوسمُ يسبق حذفَ ما لم يُدمج).

وقبل الحكم يُصنَّف كلُّ فرعٍ لا يُمسّ: KEEP_LIVE (مفتوحٌ في شجرة عمل) وKEEP_OPEN_PR (له طلبٌ مفتوح). وما كان آمناً لكنّ طرفَه أحدثُ من 48 ساعة
فهو GRACE — يُحذف بعدها (RD5: حذفٌ عند الدمج أو خلال 48 ساعةً حدّاً أقصى).

الاستخدام:
    scripts/prune_local_branches.sh                # عرضٌ فقط، لا حذف ولا وسم
    scripts/prune_local_branches.sh --archive      # يَسِم فروعَ REVIEW بوسمٍ محلّيّ (لا يحذف)
    scripts/prune_local_branches.sh --apply        # يحذف ما صُنِّف آمناً وحدَه (حتّى --max فرعاً في المرّة)
    scripts/prune_local_branches.sh --json         # مخرَجٌ آليّ فيه RK1 ومرشّحاتُ RK2/RK3 وسقفُ RD5

خيارات: --no-fetch (لا جلبَ من origin)، --no-gh (لا طلباتٍ من GitHub)، --prs-json <ملف> (قائمةُ طلباتٍ جاهزة بدل gh)،
--main <مرجع>، --grace-hours <ساعات>، --max <عدد>، --skip-archive <regex>.

الحكمُ يخصّ الفروعَ المحلّيّةَ وحدَها؛ ولا يدفع الوسومَ ولا يمسّ أيَّ فرعٍ بعيد (المستودعُ عامّ: دفعُ وسمٍ قرارٌ منفصل).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field

GRACE_HOURS = 48  # RD5: حذفٌ عند الدمج أو خلال 48 ساعةً حدّاً أقصى
REVIEW_CEILING = 40  # RD5: سقفُ الفروع الفريدة وغير المدموجة وحدَها
MAX_DELETIONS = 50  # دفعةٌ واحدةٌ كدفعات REP-08؛ ما فوقها يُعاد تشغيلُه
#: فروعٌ لا تُوسَم آليّاً: لقطاتُ نسخٍ احتياطيٍّ (backup-*) وما قبل إصلاحٍ (before-…-fix) قد تحمل ما لا يُنشر، والوسمُ المدفوعُ يُنشره في مستودعٍ عامّ.
ARCHIVE_SKIP = r"(^|/)backup-|before-.*fix"

KEEP_LIVE = "KEEP_LIVE"
KEEP_OPEN_PR = "KEEP_OPEN_PR"
GRACE = "GRACE"
SAFE_ANCESTOR = "SAFE_ANCESTOR"
SAFE_TAGGED = "SAFE_TAGGED"
SAFE_PR_MERGED = "SAFE_PR_MERGED"
SAFE_CONTENT = "SAFE_CONTENT_IN_MAIN"
REVIEW = "REVIEW"
SAFE_VERDICTS = frozenset({SAFE_ANCESTOR, SAFE_TAGGED, SAFE_PR_MERGED, SAFE_CONTENT})
PROTECTED_NAMES = frozenset({"main", "master"})
SUBMODULE_MODE = "160000"


class GitError(RuntimeError):
    pass


def _git_raw(*args: str, timeout: int = 300) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "--no-optional-locks", "-c", "core.quotepath=false", *args],
        capture_output=True,
        timeout=timeout,
    )


def git(*args: str, timeout: int = 300) -> str:
    proc = _git_raw(*args, timeout=timeout)
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise GitError(f"git {' '.join(args)} → {proc.returncode}: {detail}")
    return proc.stdout.decode("utf-8", "replace")


def git_ok(*args: str) -> bool:
    return _git_raw(*args).returncode == 0


@dataclass
class Branch:
    name: str
    tip: str
    committed: int
    verdict: str = ""
    evidence: str = ""  # الحكمُ قبل المهلة (يبقى SAFE_* حين يصير الحكمُ GRACE)
    reason: str = ""
    ahead: int = 0
    unique: list[str] = field(default_factory=list)
    remote_copy: bool = False

    def age_hours(self, now: float) -> float:
        return (now - self.committed) / 3600


@dataclass
class Worktree:
    path: str
    branch: str = ""
    primary: bool = False
    prunable: bool = False


def list_branches() -> list[Branch]:
    fmt = "%(refname)%09%(objectname)%09%(committerdate:unix)"
    branches = []
    for line in git("for-each-ref", f"--format={fmt}", "refs/heads").splitlines():
        ref, tip, stamp = line.split("\t")
        branches.append(Branch(ref.removeprefix("refs/heads/"), tip, int(stamp or 0)))
    return branches


def list_worktrees() -> list[Worktree]:
    trees = []
    for block in git("worktree", "list", "--porcelain").replace("\r", "").split("\n\n"):
        current = None
        for line in block.splitlines():
            key, _, value = line.partition(" ")
            if key == "worktree":
                current = Worktree(value, primary=not trees)
            elif current is not None and key == "branch":
                current.branch = value.removeprefix("refs/heads/")
            elif current is not None and key == "prunable":
                current.prunable = True
        if current is not None:
            trees.append(current)
    return trees


def resolve_main(explicit: str | None) -> str:
    for ref in [explicit] if explicit else ["origin/main", "main"]:
        if ref and git_ok("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"):
            return ref
    raise SystemExit("لا مرجعَ main يُحكَم عليه (جرّب --main <مرجع>)")


def fetch_origin() -> str:
    """جلبٌ يحدّث origin/main وينظّف مراجعَ الفروع المحذوفة بعيداً — فحكمُنا على main الحاليّ لا القديم."""
    if "origin" not in git("remote").split():
        return ""
    try:
        git("fetch", "--prune", "--quiet", "origin", timeout=180)
    except (GitError, subprocess.TimeoutExpired, OSError) as exc:
        return f"تعذّر الجلبُ من origin — الحكمُ على آخر ما في المرجع محلّيّاً (قد يكون قديماً): {exc}"
    return ""


def load_prs(prs_json: str | None, no_gh: bool) -> tuple[list[dict] | None, str]:
    """طلباتُ GitHub: من ملفٍّ جاهز أو من `gh`؛ وNone إن لم تتوفّر (فلا يُعرف أيُّ فرعٍ له طلبٌ مفتوح)."""
    if prs_json:
        return json.loads(pathlib.Path(prs_json).read_text(encoding="utf-8")), ""
    if no_gh or not shutil.which("gh"):
        return (
            None,
            "بلا gh: لا يُعرف أيُّ فرعٍ له طلبٌ مفتوح ولا دليلَ «طلبٍ مدموج» — الحكمُ بالمحتوى وحدَه",
        )
    fields = "number,state,headRefName,headRefOid,mergedAt"
    try:
        proc = subprocess.run(
            ["gh", "pr", "list", "--state", "all", "--limit", "3000", "--json", fields],
            capture_output=True,
            timeout=180,
        )
        if proc.returncode == 0:
            return json.loads(proc.stdout.decode("utf-8")), ""
        return None, "تعذّر جلبُ الطلبات من gh — الحكمُ بالمحتوى وحدَه"
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None, "تعذّر جلبُ الطلبات من gh — الحكمُ بالمحتوى وحدَه"


class MainContent:
    """ما في تاريخ main: كلُّ كائنٍ مرّ فيه (للمحتوى)، وملفّاتُ رأسه (لما حُذف). يُحسب عند أوّل حاجةٍ فقط — هو الأثقل."""

    def __init__(self, main: str) -> None:
        self.main = main
        self._objects: set[str] | None = None
        self._paths: set[str] | None = None

    @property
    def objects(self) -> set[str]:
        if self._objects is None:
            listing = git("rev-list", "--objects", self.main, timeout=900)
            self._objects = {line.split(" ", 1)[0] for line in listing.splitlines() if line}
        return self._objects

    @property
    def paths(self) -> set[str]:
        if self._paths is None:
            listing = git("ls-tree", "-r", "--name-only", "-z", self.main)
            self._paths = {p for p in listing.split("\0") if p}
        return self._paths

    def unique_changes(self, tip: str) -> list[str]:
        """ما غيّره الفرعُ منذ تفرّعه ولا أثرَ له في main: ملفٌّ بنسخةٍ لا توجد في تاريخه، أو حذفٌ لم يقع فيه. فارغةٌ = لا يُفقَد شيء."""
        proc = _git_raw("merge-base", self.main, tip)
        base = proc.stdout.decode("utf-8", "replace").strip() if proc.returncode == 0 else ""
        if not base:
            return ["<تاريخٌ لا يلتقي بـmain>"]
        raw = git("diff", "--raw", "--no-abbrev", "--no-renames", "-z", base, tip, "--")
        tokens = raw.split("\0")
        unique = []
        i = 0
        while i < len(tokens):
            meta = tokens[i]
            if not meta.startswith(":"):
                i += 1
                continue
            path = tokens[i + 1] if i + 1 < len(tokens) else ""
            i += 2
            _old_mode, new_mode, _old_blob, new_blob, status = meta[1:].split(" ")[:5]
            if status.startswith("D"):
                if path in self.paths:
                    unique.append(f"{path} (حذفٌ لم يبلغ main)")
            elif new_mode == SUBMODULE_MODE or new_blob not in self.objects:
                unique.append(path)
        return unique


@dataclass
class Context:
    main: str
    now: float
    grace_hours: float
    live: set[str]
    open_heads: set[str]
    merged_heads: dict[str, list[str]]
    main_commits: set[str]
    tag_commits: set[str]
    content: MainContent


def pr_merged_reason(branch: Branch, ctx: Context) -> str:
    for head in ctx.merged_heads.get(branch.name, []):
        if head == branch.tip:
            return "طرفُه هو رأسُ طلبٍ مدموج"
        if git_ok("cat-file", "-e", f"{head}^{{commit}}") and git_ok(
            "merge-base", "--is-ancestor", branch.tip, head
        ):
            return "طرفُه سلفٌ لرأس طلبٍ مدموج"
    return ""


def has_remote_copy(branch: Branch) -> bool:
    remote = f"refs/remotes/origin/{branch.name}"
    return git_ok("rev-parse", "--verify", "--quiet", remote) and git_ok(
        "merge-base", "--is-ancestor", branch.tip, remote
    )


def find_evidence(branch: Branch, ctx: Context) -> str:
    """الدليلُ الأقوى على أنّ محتوى الفرع في main (SAFE_*)، أو "" إن لم يوجد — فهو عملٌ فريدٌ يُملأ في `branch.unique`."""
    if branch.tip in ctx.main_commits:
        branch.reason = f"سلفٌ لـ{ctx.main} (مدموجٌ فعلاً)"
        return SAFE_ANCESTOR
    if branch.tip in ctx.tag_commits:
        branch.reason = "يحويه وسمٌ (أرشيفٌ يُسترجع منه)"
        return SAFE_TAGGED
    if reason := pr_merged_reason(branch, ctx):
        branch.reason = reason
        return SAFE_PR_MERGED
    branch.ahead = int(git("rev-list", "--count", f"{ctx.main}..{branch.tip}").strip() or 0)
    branch.unique = ctx.content.unique_changes(branch.tip)
    if not branch.unique:
        branch.reason = "كلُّ ما غيّره موجودٌ بنسخته في تاريخ main (دمجٌ مسحوق أو ملتقَط)"
        return SAFE_CONTENT
    sample = "، ".join(branch.unique[:3])
    branch.reason = (
        f"متقدّمٌ {branch.ahead} وفيه {len(branch.unique)} تغييراً غيرَ موجودٍ في main: {sample}"
    )
    return ""


def judge(branch: Branch, ctx: Context) -> None:
    """الحكمُ: ما لا يُمسّ أوّلاً، ثمّ الدليلُ الأقوى؛ وما لا دليلَ عليه REVIEW. وللحيّ دليلُه أيضاً (لـRK3: أشجارٌ فرعُها مدموج)."""
    if branch.name in ctx.open_heads and branch.name not in ctx.live:
        branch.verdict, branch.reason = KEEP_OPEN_PR, "له طلبُ دمجٍ مفتوح"
        return
    branch.evidence = find_evidence(branch, ctx)
    if branch.name in ctx.live:
        merged = " — ومحتواه في main" if branch.evidence else ""
        branch.verdict, branch.reason = KEEP_LIVE, f"مفتوحٌ في شجرة عمل{merged}"
    elif not branch.evidence:
        branch.verdict = REVIEW
        branch.remote_copy = has_remote_copy(branch)
    elif branch.age_hours(ctx.now) < ctx.grace_hours:
        branch.verdict = GRACE
        branch.reason += (
            f" — لكنّ طرفَه قبل {branch.age_hours(ctx.now):.0f} ساعة (مهلةُ {ctx.grace_hours:g})"
        )
    else:
        branch.verdict = branch.evidence


def build_context(
    args: argparse.Namespace, warnings: list[str]
) -> tuple[Context, list[Worktree], bool]:
    main = resolve_main(args.main or os.environ.get("MAIN_BRANCH"))
    prs, note = load_prs(args.prs_json, args.no_gh)
    if note:
        warnings.append(note)
    trees = list_worktrees()
    open_heads = {p["headRefName"] for p in prs or [] if p.get("state") == "OPEN"}
    merged: dict[str, list[str]] = defaultdict(list)
    for pr in prs or []:
        if pr.get("state") == "MERGED" and pr.get("headRefOid"):
            merged[pr["headRefName"]].append(pr["headRefOid"])
    tag_out = _git_raw("rev-list", "--tags").stdout.decode("utf-8", "replace")
    ctx = Context(
        main=main,
        now=time.time(),
        grace_hours=args.grace_hours,
        live={t.branch for t in trees if t.branch},
        open_heads=open_heads,
        merged_heads=merged,
        main_commits=set(git("rev-list", main).split()),
        tag_commits=set(tag_out.split()),
        content=MainContent(main),
    )
    return ctx, trees, prs is not None


def metrics(
    records: list[Branch],
    trees: list[Worktree],
    prs_known: bool,
    now: float = 0.0,
    grace_hours: float = GRACE_HOURS,
) -> dict:
    """مقاييسُ الخارطة (RK1..RK3) وسقفُ RD5. RK1 عدٌّ دقيق (RD5: لا يُعدّ الفرعُ الحيُّ ولا المفتوحُ بطلب).

    أمّا RK2 وRK3 فهنا **مرشّحاتٌ** لا قراءةٌ رسميّة: REVIEW يعني «لم يُثبَت الدمج» لا «عملٌ فريد» — ملفٌّ ساخنٌ دُمج بالسحق مع صفوف غيره لا يطابق
    أيَّ نسخةٍ في main فيُعدّ REVIEW ولو دُمج فعلاً — فمرشّحاتُ RK2 حدٌّ أعلى؛ وأشجارُ RK3 حدٌّ أدنى (لا دليلَ فلا تُعدّ). والقراءةُ الرسميّة
    في الخارطة بعينٍ بشريّةٍ فوق هذه الأرقام.
    """
    by_name = {b.name: b for b in records}
    review = [b for b in records if b.verdict == REVIEW]
    candidates = [
        t
        for t in trees
        if not t.primary
        and (
            t.prunable
            or (
                t.branch in by_name
                and by_name[t.branch].evidence
                and by_name[t.branch].age_hours(now) >= grace_hours
            )
        )
    ]
    return {
        "RK1": sum(1 for b in records if b.verdict not in (KEEP_LIVE, KEEP_OPEN_PR)),
        "RK2_candidates": sum(1 for b in review if not b.remote_copy),
        "RK3_candidates": len(candidates),
        "review_ceiling": {
            "count": len(review),
            "max": REVIEW_CEILING,
            "exceeded": len(review) > REVIEW_CEILING,
        },
        "prs_known": prs_known,
    }


def archive_tag_name(name: str, today: str) -> str:
    base = f"archive/{re.sub(r'^claude/', '', name)}-{today}"
    tag, n = base, 2
    while git_ok("rev-parse", "--verify", "--quiet", f"refs/tags/{tag}"):
        tag, n = f"{base}-{n}", n + 1
    return tag


def archive_review(records: list[Branch], skip: re.Pattern[str]) -> tuple[list[dict], list[str]]:
    """وسمٌ موصوفٌ محلّيٌّ لكلّ فرع REVIEW — لا يحذف ولا يدفع. فيصير SAFE_TAGGED في التشغيل التالي."""
    today = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d")
    made, skipped = [], []
    for branch in sorted(records, key=lambda b: b.committed):
        if branch.verdict != REVIEW:
            continue
        if skip.search(branch.name):
            skipped.append(branch.name)
            continue
        tag = archive_tag_name(branch.name, today)
        git("tag", "-a", tag, branch.tip, "-m", "أرشيفُ فرعٍ فريدٍ قبل حذفه (REP-10، RD5)")
        made.append({"branch": branch.name, "tip": branch.tip, "tag": tag})
    return made, skipped


def delete_branch(name: str, expected_tip: str) -> bool:
    """حذفٌ مشروطٌ بأنّ الطرفَ لم يتحرّك منذ الحكم (compare-and-delete)؛ فلا يُحذف عملٌ أُضيف بين الحكم والحذف."""
    if _git_raw("update-ref", "-d", f"refs/heads/{name}", expected_tip).returncode != 0:
        return False
    _git_raw("config", "--remove-section", f"branch.{name}")  # إعدادُ التتبّع يتيمٌ بعد الحذف
    return True


def apply_deletions(records: list[Branch], limit: int) -> tuple[list[dict], list[dict]]:
    deleted, refused = [], []
    for branch in sorted(records, key=lambda b: b.committed):
        if branch.verdict not in SAFE_VERDICTS:
            continue
        if len(deleted) >= limit:
            refused.append(
                {"branch": branch.name, "why": f"بلغت الدفعةُ سقفَها ({limit}) — أعِد التشغيل"}
            )
            continue
        if delete_branch(branch.name, branch.tip):
            deleted.append({"branch": branch.name, "tip": branch.tip, "verdict": branch.verdict})
        else:
            refused.append({"branch": branch.name, "why": "تحرّك طرفُه أو زال منذ الحكم — لم يُحذف"})
    return deleted, refused


GROUPS = (
    ("safe", "آمنةٌ للحذف", lambda v: v in SAFE_VERDICTS),
    ("grace", f"ضمن مهلة الـ{GRACE_HOURS} ساعة (تُحذف بعدها)", lambda v: v == GRACE),
    ("review", "تحتاج مراجعةً — لا تُحذف آليّاً", lambda v: v == REVIEW),
    ("keep", "محفوظةٌ (حيّةٌ في شجرة عمل أو بطلبٍ مفتوح)", lambda v: v in (KEEP_LIVE, KEEP_OPEN_PR)),
)


def _render_actions(report: dict) -> list[str]:
    lines: list[str] = []
    if report.get("archived"):
        lines += ["", "── وُسمت (محلّيّاً، لم تُدفع؛ يُحذف الفرعُ بـ--apply في التشغيل التالي) ──"]
        lines += [f"  {a['branch']} ← {a['tag']}" for a in report["archived"]]
    if report.get("archive_skipped"):
        lines += [
            "",
            "── لم تُوسَم (لقطةُ نسخٍ أو ما قبل إصلاح — قد تحمل ما لا يُنشر؛ قرارُها للمالك) ──",
        ]
        lines += [f"  {name}" for name in report["archive_skipped"]]
    if report.get("deleted"):
        lines += ["", "── حُذفت ──"]
        lines += [
            f"  {d['branch']} ({d['tip'][:8]}) — استرجاع: git branch {d['branch']} {d['tip']}"
            for d in report["deleted"]
        ]
    if report.get("refused"):
        lines += ["", "── لم تُحذف ──"] + [
            f"  {r['branch']} — {r['why']}" for r in report["refused"]
        ]
    return lines


def render(report: dict, records: list[Branch]) -> str:
    lines = [
        f"المرجع: {report['main_ref']} @ {report['main_sha'][:8]} | فروعٌ محلّيّة: {len(records)}"
    ]
    for key, title, member in GROUPS:
        chosen = sorted((b for b in records if member(b.verdict)), key=lambda b: b.committed)
        lines += ["", f"── {title} ({len(chosen)}) ──"]
        for b in chosen:
            tag = (
                ""
                if key != "review"
                else ("  [له نسخةٌ بعيدة]" if b.remote_copy else "  [نسخةٌ وحيدة]")
            )
            lines.append(f"  {b.name}  — {b.verdict}: {b.reason}{tag}")
    m = report["metrics"]
    ceiling = m["review_ceiling"]
    lines += [
        "",
        f"RK1 (الفروعُ المحلّيّة عدا الحيَّ والمفتوحَ بطلب) = {m['RK1']}",
        f"مرشّحاتُ RK2 (غيرُ مثبَتِ الدمج وبنسخةٍ وحيدة — حدٌّ أعلى يحتاج عيناً بشريّة) = {m['RK2_candidates']}",
        f"مرشّحاتُ RK3 (أشجارٌ فرعُها مدموجٌ منذ ≥ {report['grace_hours']:g} ساعة أو يتيمة — حدٌّ أدنى) = {m['RK3_candidates']}",
        f"سقفُ RD5 على الفريدة وغير المدموجة: {ceiling['count']} من {ceiling['max']}"
        + (" — يتجاوز السقف!" if ceiling["exceeded"] else " — داخل السقف"),
    ]
    lines += _render_actions(report)
    for warning in report["warnings"]:
        lines.append(f"⚠ {warning}")
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="فروعٌ محلّيّةٌ محتواها في main — بالمحتوى لا بالسلفيّة (REP-10)."
    )
    parser.add_argument("--apply", action="store_true", help="احذف ما صُنِّف آمناً وحدَه")
    parser.add_argument("--archive", action="store_true", help="اسِم فروعَ REVIEW بوسمٍ محلّيّ (لا حذف)")
    parser.add_argument("--json", action="store_true", help="مخرَجٌ آليّ")
    parser.add_argument("--no-fetch", action="store_true", help="لا جلبَ من origin")
    parser.add_argument("--no-gh", action="store_true", help="لا طلباتٍ من GitHub")
    parser.add_argument("--prs-json", help="قائمةُ طلباتٍ جاهزةٌ (بصيغة gh pr list --json) بدل gh")
    parser.add_argument("--main", help="مرجعُ main (الافتراضيّ origin/main ثمّ main)")
    parser.add_argument("--grace-hours", type=float, default=GRACE_HOURS)
    parser.add_argument(
        "--max", type=int, default=MAX_DELETIONS, dest="limit", help="أقصى حذفٍ في المرّة"
    )
    parser.add_argument("--skip-archive", default=ARCHIVE_SKIP, help="regex لأسماء فروعٍ لا تُوسَم")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    args = parse_args(sys.argv[1:] if argv is None else argv)
    warnings: list[str] = []
    if not args.no_fetch and (note := fetch_origin()):
        warnings.append(note)
    try:
        ctx, trees, prs_known = build_context(args, warnings)
        protected = PROTECTED_NAMES | {ctx.main.removeprefix("origin/")}
        records = [b for b in list_branches() if b.name not in protected]
        for branch in records:
            judge(branch, ctx)
    except (GitError, subprocess.TimeoutExpired) as exc:
        print(f"تعذّر الحكم: {exc}", file=sys.stderr)
        return 2
    report: dict = {
        "generated": dt.datetime.now(dt.UTC).isoformat(),
        "main_ref": ctx.main,
        "main_sha": git("rev-parse", ctx.main).strip(),
        "grace_hours": ctx.grace_hours,
        "records": [
            {
                "branch": b.name,
                "tip": b.tip,
                "verdict": b.verdict,
                "evidence": b.evidence,
                "reason": b.reason,
                "age_hours": round(b.age_hours(ctx.now), 1),
                "ahead": b.ahead,
                "unique": b.unique,
                "remote_copy": b.remote_copy,
            }
            for b in records
        ],
        "metrics": metrics(records, trees, prs_known, ctx.now, ctx.grace_hours),
        "warnings": warnings,
    }
    exit_code = 0
    if args.archive:
        report["archived"], report["archive_skipped"] = archive_review(
            records, re.compile(args.skip_archive)
        )
    if args.apply:
        report["deleted"], report["refused"] = apply_deletions(records, args.limit)
        exit_code = 1 if any("تحرّك" in r["why"] for r in report["refused"]) else 0
    print(
        json.dumps(report, ensure_ascii=False, indent=1) if args.json else render(report, records)
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""فحصٌ قبل الإيداع والدفع، وحكمٌ على فرعٍ «مدموجٍ؟» — قراءةٌ فقط، لا يغيّر شيئاً في المستودع.

الاستعمال (من داخل شجرة عملك):
    python .claude/skills/schoolos-git-safety/scripts/git_preflight.py            # فحصُ الشجرة والفرع الحاليَّين
    python .../git_preflight.py --fetch --gh                                       # بعد جلب origin، ومع حالة طلبك في GitHub
    python .../git_preflight.py --judge claude/<فرع> [--gh]                         # هل عملُ هذا الفرع في main فعلاً؟

رمزُ الخروج: 0 سليم، 1 تنبيهات تستحقّ النظر، 2 مانعٌ (لا تدفع قبل حلّه).
`--fetch` وحدَه يكتب (مراجعُ origin/* كأيّ `git fetch`)؛ وقراءةُ شجرةٍ أخرى بـ`--no-optional-locks` فلا يُلمس فهرسُها.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

IN_PROGRESS = {
    "rebase-merge": "إعادةُ أساسٍ (rebase) لم تكتمل",
    "rebase-apply": "إعادةُ أساسٍ/am لم تكتمل",
    "MERGE_HEAD": "دمجٌ لم يكتمل",
    "CHERRY_PICK_HEAD": "التقاطٌ (cherry-pick) لم يكتمل",
    "REVERT_HEAD": "عكسٌ (revert) لم يكتمل",
    "BISECT_LOG": "تنصيفٌ (bisect) جارٍ",
}
MAIN_NAMES = {"main", "master"}
SKIP_DIRS = ("/.venv/", "/venv/", "/node_modules/", "/__pycache__/")


class Report:
    """يجمع الأحكامَ بثلاث درجات ويطبعها بالترتيب الذي وقعت به."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.level = 0

    def ok(self, text: str) -> None:
        self.lines.append(f"[سليم]  {text}")

    def warn(self, text: str) -> None:
        self.lines.append(f"[تنبيه] {text}")
        self.level = max(self.level, 1)

    def block(self, text: str) -> None:
        self.lines.append(f"[مانع]  {text}")
        self.level = 2

    def info(self, text: str) -> None:
        self.lines.append(f"        {text}")


def git(*args: str, cwd: str | None = None, raw: bool = False) -> tuple[int, str]:
    """raw=True يُبقي المخرجَ كما هو: أوّلُ رمزٍ في `status --porcelain` قد يكون مسافةً ذاتَ معنى."""
    proc = subprocess.run(
        ["git", "--no-optional-locks", "-c", "core.quotepath=false", *args],
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return proc.returncode, proc.stdout if raw else proc.stdout.strip()


def out(*args: str, cwd: str | None = None) -> str:
    return git(*args, cwd=cwd)[1]


def ref_exists(ref: str) -> bool:
    return git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")[0] == 0


def is_ancestor(a: str, b: str) -> bool:
    return git("merge-base", "--is-ancestor", a, b)[0] == 0


def gh_prs(branch: str) -> list[dict] | None:
    """طلباتُ هذا الفرع بكلّ حالاتها؛ None إن تعذّر gh (فلا حكمَ بحالة الطلب)."""
    if not shutil.which("gh"):
        return None
    proc = subprocess.run(
        ["gh", "pr", "list", "--head", branch, "--state", "all", "--limit", "50",
         "--json", "number,state,headRefOid,mergedAt,isDraft"],
        capture_output=True, encoding="utf-8", errors="replace", check=False,
    )
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return None


def pr_verdict(tip: str, prs: list[dict], rep: Report) -> str:
    """الحكمُ بحالة الطلب لا بعدّ الإيداعات: الدمجُ بالسحق يترك الفرعَ «متقدّماً» على main ولو اندمج كلُّه.
    يُرجع: open | merged | after_merge | closed | reused_name | none."""
    opened = [p for p in prs if p["state"] == "OPEN"]
    if opened:
        rep.ok("طلبٌ مفتوح: " + "، ".join(f"#{p['number']}" + (" (مسوّدة)" if p.get("isDraft") else "") for p in opened))
        return "open"
    merged = [p for p in prs if p["state"] == "MERGED"]
    covering = [p for p in merged if p["headRefOid"] == tip or is_ancestor(tip, p["headRefOid"])]
    if covering:
        rep.ok("طرفُه رأسُ طلبٍ مدموجٍ أو سلفُه: " + "، ".join(f"#{p['number']}" for p in covering))
        return "merged"
    beyond = [p for p in merged if is_ancestor(p["headRefOid"], tip)]
    if beyond:
        rep.warn("إيداعاتٌ بعد دمج " + "، ".join(f"#{p['number']}" for p in beyond)
                 + " — عملٌ جديدٌ غيرُ مدموج يحتاج طلباً جديداً (الاسمُ القديمُ لا يكفي دليلاً)")
        return "after_merge"
    closed = [p for p in prs if p["state"] == "CLOSED"]
    if closed:
        rep.warn("طلبٌ مغلقٌ بلا دمج: " + "، ".join(f"#{p['number']}" for p in closed))
        return "closed"
    if merged:
        rep.warn("طلبٌ مدموجٌ بالاسم نفسِه لكنّ طرفَه لا يلتقي به — اسمٌ أُعيد استعمالُه؛ لا تعدّه مدموجاً")
        return "reused_name"
    rep.info("لا طلبَ لهذا الفرع على GitHub")
    return "none"


def parse_status(root: str) -> list[tuple[str, str]]:
    """(رمزان، مسار) لكلّ مدخلٍ في `git status --porcelain -z`؛ إعادةُ التسمية تُرجع المسارَ الجديد."""
    _, raw = git("status", "--porcelain=v1", "-z", "--untracked-files=all", cwd=root, raw=True)
    tokens = raw.split("\0")
    entries, i = [], 0
    while i < len(tokens):
        tok = tokens[i]
        i += 1
        if len(tok) < 4:
            continue
        code, path = tok[:2], tok[3:]
        if code[0] in "RC":
            i += 1  # المسارُ القديم يلي الجديدَ في صيغة -z
        entries.append((code, path))
    return entries


def check_status(root: str, rep: Report) -> None:
    entries = parse_status(root)
    if not entries:
        rep.ok("الشجرةُ نظيفة (لا تعديلَ ولا ملفَّ غيرَ متتبَّع)")
        return
    conflicted = [p for c, p in entries if "U" in c or c in ("AA", "DD")]
    if conflicted:
        rep.block(f"ملفّاتٌ بتعارضٍ لم يُحلّ ({len(conflicted)}): " + "، ".join(conflicted))
    rep.warn(f"{len(entries)} مدخلاً في git status — اقرأها كلَّها؛ ما لا تعرفه عملُ جلسةٍ أخرى: قِف واسأل")
    for code, path in entries:  # القائمةُ كاملةً بلا قصّ: المسحُ المقطوعُ يبدو كاملاً
        note = ""
        if code[1] == "M" and git("diff", "--ignore-cr-at-eol", "--quiet", "--", path, cwd=root)[0] == 0:
            note = "  ← نهاياتُ أسطرٍ فقط (CRLF)، لا فرقَ في المحتوى"
        rep.info(f"{code} {path}{note}")


def check_ignored_modules(root: str, rep: Report) -> None:
    """وحدةُ بايثون جديدةٌ باسمٍ يبدأ بـ`_` تُسقطها قاعدةُ `.gitignore` بصمت فلا يضمّها `git add`.
    `--directory` يطوي المجلّدَ المتجاهَلَ كلَّه (بيئاتٌ ومسوّداتٌ) فيبقى ما تجاهلته قاعدةُ الاسم وحدَها."""
    _, listing = git("ls-files", "-o", "-i", "--exclude-standard", "--directory", cwd=root)
    hits = []
    for path in listing.splitlines():
        base = path.rsplit("/", 1)[-1]
        if base.endswith(".py") and base.startswith("_") and base != "__init__.py" \
                and not any(d in f"/{path}" for d in SKIP_DIRS):
            hits.append(path)
    if hits:
        rep.warn("ملفّاتُ بايثون جديدةٌ يتجاهلها .gitignore فلن تُودَع (سمِّها بلا `_`): " + "، ".join(hits))


def check_main_relation(branch: str, main: str, rep: Report) -> None:
    ahead = int(out("rev-list", "--count", f"{main}..HEAD") or 0)
    behind = int(out("rev-list", "--count", f"HEAD..{main}") or 0)
    if ahead == 0:
        rep.warn(f"لا إيداعَ لك فوق {main} — دفعُ هذا الرأس يجعل الفرعَ مطابقاً لـmain فيُغلق GitHub طلبَه")
    else:
        rep.ok(f"متقدّمٌ على {main} بـ{ahead} إيداعاً")
    if behind:
        rep.warn(f"متأخّرٌ عن {main} بـ{behind} إيداعاً — ادمج {main} في فرعك قبل الدفع إن تعارض أو طُلب")
    rc, merged = git("merge-tree", "--write-tree", "--name-only", "--no-messages", "HEAD", main)
    if rc == 1:
        files = merged.splitlines()[1:]
        rep.warn(f"الدمجُ مع {main} يتعارض في: " + "، ".join(files)
                 + " — لن يظهر فرعُك على 8500 حتى يُحلّ")
    elif rc == 0:
        rep.ok(f"لا تعارضَ مع {main} (merge-tree)")
    changed = out("diff", "--name-only", f"{main}...HEAD").splitlines()
    if changed:
        rep.info(f"ملفّاتُ فرقك عن {main} ({len(changed)}) — تأكّد أنّها كلَّها من عملك:")
        for path in changed:
            rep.info(f"  {path}")


def check_remote(branch: str, rep: Report) -> None:
    remote = f"origin/{branch}"
    if not ref_exists(remote):
        rep.info(f"لا نسخةَ على GitHub لـ{branch} بعد (فرعٌ لم يُدفع قطّ لا يعرف عنه GitHub شيئاً)")
        return
    unpushed = int(out("rev-list", "--count", f"{remote}..HEAD") or 0)
    missing = int(out("rev-list", "--count", f"HEAD..{remote}") or 0)
    if missing:
        rep.block(f"على {remote} {missing} إيداعاً ليست عندك — الدفعُ سيُرفض ولا force: ادمج {remote} أوّلاً")
    rep.info(f"إيداعاتٌ لم تُدفع إلى {remote}: {unpushed}")


def preflight(args: argparse.Namespace) -> int:
    rep = Report()
    root = out("rev-parse", "--show-toplevel")
    if not root:
        print("لستَ داخل مستودع git", file=sys.stderr)
        return 2
    if args.fetch:
        rc, _ = git("fetch", "--quiet", "origin")
        (rep.ok if rc == 0 else rep.warn)("جُلب origin" if rc == 0 else "تعذّر جلبُ origin — الأحكامُ على آخر ما جُلب")
    git_dir, common = out("rev-parse", "--absolute-git-dir"), out("rev-parse", "--path-format=absolute", "--git-common-dir")
    if os.path.normcase(git_dir) == os.path.normcase(common):
        rep.warn(f"أنت في الجذر المشترك ({root}) لا في شجرة عمل — لا تبدّل فرعَه؛ صدفةُ المالك وحاوياتُ القاعدة تعمل منه")
    else:
        rep.ok(f"شجرةُ عمل: {root}")
    for name, label in IN_PROGRESS.items():
        if os.path.exists(out("rev-parse", "--path-format=absolute", "--git-path", name)):
            rep.block(f"{label} — أكملها أو ألغِها قبل أيّ إيداعٍ أو دفع")
    branch = out("symbolic-ref", "--short", "-q", "HEAD")
    if not branch:
        rep.block("رأسٌ منفصل (detached) — لا فرعَ يُدفع؛ أنشئ فرعاً لعملك أوّلاً")
    elif branch in MAIN_NAMES:
        rep.block("أنت على main — لا إيداعَ ولا دفعَ منه؛ اعمل على فرع claude/<اسم-المهمّة>")
    else:
        rep.ok(f"الفرع: {branch}")
    check_status(root, rep)
    check_ignored_modules(root, rep)
    if ref_exists(args.main):
        check_main_relation(branch, args.main, rep)
    else:
        rep.warn(f"لا مرجعَ {args.main} — شغّل مع --fetch")
    if branch and branch not in MAIN_NAMES:
        check_remote(branch, rep)
        if args.gh:
            prs = gh_prs(branch)
            if prs is None:
                rep.warn("تعذّر gh — لا حكمَ بحالة الطلب")
            else:
                pr_verdict(out("rev-parse", "HEAD"), prs, rep)
        target = branch if branch.startswith("claude/") else "claude/<اسم-المهمّة>"
        rep.info(f"أمرُ الدفع (بعد اعتماد المالك وحدَه): git push origin HEAD:refs/heads/{target}")
    print("\n".join(rep.lines))
    return rep.level


def judge(args: argparse.Namespace) -> int:
    """هل عملُ فرعٍ في main فعلاً؟ الأدلّةُ من الأقوى، ولا حكمَ بالحذف: ذاك للأداة المركزيّة وقرارِ صاحبه."""
    rep = Report()
    name = args.judge.removeprefix("refs/heads/")
    tip = out("rev-parse", "--verify", "--quiet", f"{args.judge}^{{commit}}")
    if not tip:
        print(f"لا مرجعَ باسم {args.judge}", file=sys.stderr)
        return 2
    main = args.main
    rep.info(f"الفرع {name} @ {tip[:10]} — مقابل {main} @ {out('rev-parse', '--short', main)}")
    for block in out("worktree", "list", "--porcelain").replace("\r", "").split("\n\n"):
        fields = dict(line.partition(" ")[::2] for line in block.splitlines())
        if fields.get("branch") == f"refs/heads/{name}":
            dirty = len(out("status", "--porcelain", cwd=fields["worktree"]).splitlines())
            rep.warn(f"مفتوحٌ في شجرة عمل {fields['worktree']} ({dirty} ملفّاً غيرَ مودَع) — حيٌّ حتى يثبت العكس")
    if is_ancestor(tip, main):
        rep.ok(f"سلفٌ لـ{main}: مدموجٌ بالنسب")
        print("\n".join(rep.lines))
        return rep.level
    tags = out("tag", "--contains", tip).split()
    if tags:
        rep.ok("يحويه وسم (يُسترجع منه): " + "، ".join(tags))
    remote_copy = ref_exists(f"origin/{name}") and is_ancestor(tip, f"origin/{name}")
    if remote_copy:
        rep.ok(f"له نسخةٌ على GitHub تحويه (origin/{name})")
    pr_state = "unknown"
    if args.gh:
        prs = gh_prs(name)
        if prs is None:
            rep.warn("تعذّر gh — الحكمُ بالمحتوى وحدَه")
        else:
            pr_state = pr_verdict(tip, prs, rep)
    cherry = out("cherry", main, tip).splitlines()
    plus = sum(1 for line in cherry if line.startswith("+"))
    rep.info(f"git cherry: {len(cherry) - plus} رقعةً في main و{plus} «+» — و«+» ليس دليلَ عدم دمج (السحقُ يغيّر البصمة)")
    base = out("merge-base", main, tip)
    unique: list[str] = []
    for line in out("diff", "--raw", "--no-abbrev", "--no-renames", base, tip).splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if len(parts) < 5:
            continue
        blob, status = parts[3], parts[4]
        if status.startswith("D"):
            if git("cat-file", "-e", f"{main}:{path}")[0] == 0:
                unique.append(f"{path} (حذفٌ لم يبلغ main)")
        elif out("rev-parse", "--verify", "--quiet", f"{main}:{path}") == blob:
            continue
        elif not out("log", "-1", "--format=%h", f"--find-object={blob}", main):
            unique.append(path)
    if unique and pr_state == "merged":  # الطلبُ المدموجُ دليلٌ أقوى: ملفٌّ ساخنٌ دُمج مع صفوف غيره فتغيّرت نسختُه
        rep.info(f"{len(unique)} ملفّاً بنسخةٍ ليست في تاريخ {main} ({'، '.join(unique)}) — مألوفٌ في ملفٍّ ساخنٍ مع طلبٍ مدموج")
    elif unique:
        rep.warn(f"{len(unique)} تغييراً لا أثرَ لنسخته في تاريخ {main}: " + "، ".join(unique)
                 + " — عملٌ فريدٌ أو ملفٌّ ساخنٌ دُمج مع صفوف غيره؛ لا يُحذف قبل وسمِ أرشيف")
        if not remote_copy and not tags:
            rep.warn("ولا نسخةَ بعيدةَ ولا وسمَ يحويه — نسختُه المحلّيّةُ وحيدة، فحذفُه يُضيّعه")
    else:
        rep.ok(f"كلُّ ما غيّره موجودٌ بنسخته في تاريخ {main} (دمجٌ مسحوقٌ أو ملتقَط)")
    rep.info("الحذفُ والإزالةُ ليسا لهذه الأداة: scripts/prune_local_branches.sh (عرضٌ فقط) ثمّ قرارُ المالك")
    print("\n".join(rep.lines))
    return rep.level


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass  # مجرًى مُعاد توجيهُه بلا reconfigure: يبقى بترميزه
    parser = argparse.ArgumentParser(description="فحصُ ما قبل الإيداع والدفع، وحكمُ «مدموج؟» — قراءةٌ فقط")
    parser.add_argument("--main", default="origin/main", help="مرجعُ main (الافتراضيّ origin/main)")
    parser.add_argument("--fetch", action="store_true", help="اجلب origin أوّلاً")
    parser.add_argument("--gh", action="store_true", help="اسأل GitHub عن طلب الفرع")
    parser.add_argument("--judge", metavar="BRANCH", help="احكم على فرعٍ آخر بدل فحص الشجرة الحاليّة")
    args = parser.parse_args()
    return judge(args) if args.judge else preflight(args)


if __name__ == "__main__":
    sys.exit(main())

# المحظوراتُ وأسبابُها — ما يحجبه الحارسُ فعلاً وما لا يحجبه

متى تقرأ هذا الملف: حين يُحجب أمرٌ برسالة «محجوب بحارس الغيت (REP-19) [<معرّف>]»، أو قبل أمرٍ لستَ متأكّداً أنّه
مسموح، أو حين تظنّ أنّ «الحارس سيمنعني إن أخطأت» — فهو لا يمنع كلَّ شيء.

## لماذا القيود أصلاً

المستودعُ واحد، ورأسُه ومكدّسُ خبيئته ومراجعُه مشتركةٌ بين الجذر `D:\shschool_mvp` وكلّ شجرةٍ تحت
`.claude/worktrees/`، وكلُّ شجرةٍ عليها جلسةٌ تعمل الآن. أمرٌ يمسّ المشترك يُبطل عملَ جلسةٍ أخرى لا تعلم به،
والمستودعُ عامّ فما يُدفع يُنشر. المصدر: CLAUDE.md «غيت في المحادثات المتوازية»، ورأسُ `.claude/hooks/guard_git.py`.

قاعدةُ «لا worktree، عدّل في `D:\shschool_mvp` وحدَه» **أُلغيت 2026-09-08**؛ القاعدةُ الآن: اعمل في شجرتك ولا
تعبر إلى شجرة غيرك. المصدر: CLAUDE.md «القاعدة رقم 1»، وذاكرة feedback_parallel_sessions.

## ما يحجبه الحارس (مقروءٌ من `.claude/hooks/guard_git.py` في main، 2026-09-28)

يعمل `PreToolUse` على أداتَي Bash وPowerShell (`.claude/settings.json`)، ويخرج برمز 2 فيُمنع الأمر.

| المعرّف | ما يُحجب | ما يبقى مسموحاً |
|---|---|---|
| add-all | `add -A`/`--all`/`-u` بلا مسار، و`add .` و`:/` و`*` | `add <مسارات>`، و`add -A <مسارات>`، و`add -n` |
| commit-all | `commit -a`/`--all` (ومنه العنقود `-am`) | `commit` بعد `add` صريح |
| stash | كلُّ `stash` | `stash list` و`stash show` |
| push-main | الدفعُ إلى `main`/`master`/`refs/heads/main`، والدفعُ بلا وجهةٍ أو بـ`HEAD` وأنت على main | الدفعُ إلى `claude/…` |
| push-force | `--force`، `-f`، `--force-with-lease`، `--force-if-includes`، `+refspec` | — |
| push-delete | `--delete`، `-d`، `:ref`، `--prune`، `--mirror` | — |
| push-bulk | `--all`، `--branches`، `--tags`، وأيُّ وجهةٍ تحت `archive/` | دفعُ مرجعٍ واحدٍ صريح |
| no-verify | `--no-verify`، `commit -n`، بادئةُ `SKIP=` مع commit/push/merge/rebase/am/cherry-pick، `-c core.hooksPath`، `git config core.hooksPath <قيمة>` | — |
| reset-hard | `reset --hard` | `reset --soft`، `reset --mixed`، `reset HEAD -- <مسار>` |
| branch-delete | `branch -D`، و`-d` مع `--force`/`-f` | `branch -d` (يرفض غيرَ المدموج بالنسب) |
| tag-delete | `tag -d` | إنشاءُ وسمٍ محلّيّ |
| ref-delete | `update-ref -d` لغير `refs/tmp/` | حذفُ `refs/tmp/…` |
| history-rewrite | `filter-branch`، `filter-repo`، `reflog expire|delete`، `gc --prune=now|all`، `prune` | `gc` العاديّ، `prune -n` |
| clean-force | `clean -f` بلا `-n` | `clean -n` |
| discard-all | `checkout .`/`restore .` (و`:/` و`*`)، و`checkout|switch -f`/`--discard-changes` | `checkout -- <مسارات>`، و`restore --staged .` وحدَه |
| prune-apply | `prune_local_branches(.sh|.py) … --apply` | العرضُ و`--json` و`--archive` |

ويفكّ الحارسُ ما يلتفّ به الأمر: `git -C`/`-c`، المسارَ الكامل و`git.exe`، `env`/`sudo`/`command`/`exec`/`nohup`/
`timeout`/`xargs`/`wsl`، `bash -c` و`sh -c` و`eval` و`pwsh -Command` و`-EncodedCommand` و`cmd /c` و`iex`،
`$(…)` وbackticks، وheredoc التي تغذّي صدفةً، و`& git` في PowerShell، وأسماءَ git المستعارة (بما فيها `!صدفة`).
المصدر: الشيفرة نفسُها (`WRAPPERS`، `_c_strings`، `_resolve_alias`)، وصفُّ REP-19 في `docs/governance/regression_guards.md`.

## حدودُ الحارس — لا تعتمد عليه فيما لا يراه

- **لا يرى داخل سكربتٍ يُشغَّل** (`bash x.sh`، `python -c "subprocess…"`) **ولا متغيّراً غيرَ محلول** (`$CMD`).
- **لا يحلّل النصَّ بين علامات الاقتباس ولا أجسامَ heredoc البيانيّة** — رسالةُ إيداعٍ تذكر `git push --force` تمرّ.
- **القواعدُ المحلّيّة لا تسري خارج المستودع وأشجاره** (مستودعُ الوثائق الخاصّ مثلاً)؛ أمّا push-force وpush-delete
  وpush-bulk فتسري في كلّ مكان. ومجلّدٌ غيرُ معلوم (`cd "$P"`) يُعامَل كأنّه داخله.
- **خللُه لا يمنع**: استثناءٌ داخله يُطبع ويمرّ الأمر؛ وإن لم يجد `guard_git.sh` بايثون 3.9+ يعمل خرج برمز 1
  (خطأٌ ظاهرٌ لا منع) — فالحارسُ «غيرُ فعّالٍ في هذه الجلسة».
- **لا يحرس صدفةَ المالك في طرفيّته**، ولا يحرس شجرةً لم يصلها: الإعدادُ والحارسُ ملفّان متتبَّعان يُقرآن من
  `$CLAUDE_PROJECT_DIR`، فشجرةٌ أساسُها أقدمُ من دمج #649 (2026-09-26) لا حارسَ فيها. تحقّق: `ls .claude/hooks/guard_git.py`.
المصدر: `guard_git.py` (رأسُ الملفّ و`main()`)، `guard_git.sh`، `.claude/settings.json`، وذاكرة project_rep19_git_guard.

## محظورٌ بالبروتوكول ولا يحجبه الحارس

| الفعل | لماذا محظور | المصدر |
|---|---|---|
| `git switch/checkout <فرع>` في شجرةٍ لستَ فيها، أو في الجذر من جلسة شجرة | يسحب الأرضَ من تحت جلستها؛ وفي الجذر صدفةُ المالك وحاوياتُ القاعدة وredis | CLAUDE.md البند 1؛ docs/archive_survey_2026-09-28.md في حزمة المايسترو |
| `git -C <شجرة غيرك> <أيّ أمرٍ يكتب>` | العبورُ نفسُه، ولو بلا `cd` | CLAUDE.md «القاعدة رقم 1» |
| `git pull --rebase` على شجرةٍ متّسخة | يخلط غيرَ المودَع بإعادة الأساس | CLAUDE.md البند 4 |
| `git push` عارياً أو قبل اعتماد المالك | `push.default=current` يدفع فوراً؛ والدفعُ قبل المعاينة يكسر الفلو | إعدادُ git العامّ (قيس 2026-09-28)؛ مهارة schoolos-flow |
| إعادةُ أساسٍ أو `commit --amend` على فرعٍ منشور | يلزمه force (محجوبٌ عند الدفع) | الحارس push-force؛ ذاكرة project_git_roadmap_integration |
| `git worktree remove --force` على شجرةٍ فيها غيرُ مودَع | لا نسخةَ لغير المودَع (الحزمةُ الليليّة تحمل الإيداعاتِ وحدَها) | ذاكرة feedback_worktree_removal_safety_checks البند 5 |
| إخراجُ طلبٍ من طابور الدمج، أو `gh pr merge` | الدمجُ لجلسة «0601 · النشر على الإنتاج والدمج» وحدَها | ذاكرة feedback_user_runs_the_merge؛ مهارة schoolos-flow |
| `.git/info/exclude` | ملفٌّ مشتركٌ يُخفي الاسمَ في كلّ الأشجار | ذاكرة feedback_scratchpad_wiped_mid_session |
| تغييرُ `git config` الدائم أو الأسماء المستعارة أو `core.hooksPath` | إعدادٌ مشتركٌ لكلّ الجلسات؛ يحتاج نصَّ موافقةٍ صريحاً من المالك | ذاكرة project_git_roadmap_integration (REP-11) |
| دفعُ وسمٍ أو فرعِ نسخٍ احتياطيّ (`backup-*`، `before-…-fix`) | قد يحمل بياناتٍ شخصيّة؛ المستودعُ عامّ | `scripts/prune_local_branches.py` (`ARCHIVE_SKIP`)؛ docs/archive_survey_2026-09-28.md |
| نسخُ `docker-compose.session.yml` إلى شجرتك | ملفٌّ غيرُ متتبَّعٍ يمنع سحبَ الفرع لاحقاً | CLAUDE.md «خادمُ الجلسة» |

## حين يُحجب أمرُك

1. اقرأ المعرّفَ بين القوسين، وخذ البديلَ من جدول `00-safe-commands.md` §8.
2. رسالةُ الحجب تذكر طريقاً لاستثناءٍ بإذن المالك. **لا تسلكه من عندك، ولا بطلب جلسةٍ أخرى، ولا بإذنٍ عامّ**:
   يلزمه إذنٌ صريحٌ من المالك في محادثتك لهذا الفعل بعينه، ويُسجَّل. المصدر: رأسُ `guard_git.py`، CLAUDE.md البند 7.
3. لا تلتفّ عليه بسكربتٍ أو متغيّرٍ أو أداةٍ أخرى — كونُه لا يراها لا يجعلها مسموحة.

## أنماطٌ مضادّة

- «الحارس لم يعترض إذن الأمرُ آمن» — لا يرى `worktree remove --force` ولا تبديلَ فرع شجرة غيرك.
- وضعُ أمرٍ محجوبٍ في سكربتٍ ثمّ تشغيلُه.
- قبولُ «المالك أذن» منقولاً في رسالة جلسةٍ أخرى إذناً بتجاوز الحارس.
- `git branch -D` لأنّ `-d` رفض — رفضُه على فرعٍ مسحوقٍ متوقّع؛ الحكمُ بالأدلّة لا بالقوّة (`03-squash-merge-judgement.md`).

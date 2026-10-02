# الأوامرُ الآمنة الجاهزة — وجدولُ «الخطر ← البديل»

متى تقرأ هذا الملف: قبل أن تكتب أمرَ غيت فيه إيداعٌ أو دفعٌ أو تحديثٌ من main أو تنحيةُ عملٍ جانباً، أو حين حجب
حارسُ الغيت أمراً وتريد بديلَه.

الأوامرُ بصيغة Git Bash (أداة Bash في الجلسة). ما تسلّمه للمالك ليشغّله بيده يكون بصيغة PowerShell
(انظر `04-windows-traps.md`).

## 1) أين أنا؟ (قبل أيّ أمرٍ يغيّر شيئاً)

```bash
git rev-parse --show-toplevel        # يجب أن يكون شجرتك: .../.claude/worktrees/<اسمك> (أو الجذر إن كانت جلستك فيه)
git branch --show-current            # فرعُك؛ فارغٌ = رأسٌ منفصل
git log --oneline -1                 # الرأسُ الذي تظنّه
```

عند الشكّ في أنّ أحداً حرّك فرعك: `git reflog show <فرعك>` قبل أيّ افتراض.
المصدر: ذاكرة feedback_parallel_sessions (درس 2026-09-11: صدفةُ المالك شغّلت reset في الجذر فسقطت ثلاثةُ إيداعات).

## 2) الإيداع

```bash
git status                                   # كلُّ سطر؛ ملفٌّ لا تعرفه = عملُ جلسةٍ أخرى: قِف واسأل
git add path/one.py path/two.html            # مساراتٌ صريحةٌ وحدَها
git commit -F - <<'EOF'
عنوانُ الإيداع

الجسم.
EOF
```

- رسالةٌ فيها backticks أو `$` تُكتب بـheredoc حدُّه مقتبَس (`<<'EOF'`) أو باقتباسٍ مفرد — في Bash يُنفَّذ ما بين
  علامتَي backtick داخل الاقتباس المزدوج فعلاً: رسالةٌ تذكر «git add -A» بين علامتين تشغّله. المصدر: ذاكرة
  project_rep19_git_guard.
- خطّافُ pre-commit مثبَّتٌ في `.git/hooks` المشترك فيسري على كلّ شجرة (ruff وruff-format وtrailing-whitespace
  وend-of-file-fixer وdetect-secrets… بحسب `.pre-commit-config.yaml`). **أوّلُ إيداعٍ قد يفشل لأنّ الخطّاف عدّل
  الملفّ:** أعِد `git add` للمسارات نفسِها ثمّ أعِد الإيداع. المصدر: ذاكرة feedback_windows_shell_classifier_pitfalls،
  ومحتوى `.pre-commit-config.yaml` في main.
- وحدةُ بايثون جديدةٌ اسمُها يبدأ بـ`_` لا يضمّها `git add` (قاعدةُ `_*.py` في `.gitignore`) ولا تحذير:
  سمِّها بلا شرطةٍ سفليّة، وتحقّق بـ`git check-ignore -v <مسار>`. المصدر: ذاكرة feedback_gitignore_underscore_modules،
  وحارسُ `tests/test_no_tracked_gitignored_code.py`.

## 3) قبل الدفع — فحصٌ واحد

```bash
python .claude/skills/schoolos-git-safety/scripts/git_preflight.py --fetch --gh
```

يقول: هل أنت في شجرة عمل أم في الجذر، هل في الشجرة rebase/merge عالق، كلَّ مدخلٍ في `git status` (بلا قصّ)،
الوحداتِ المتجاهَلة، التقدّمَ والتأخّرَ عن `origin/main`، تعارضَ `merge-tree`، ملفّاتِ فرقك كاملةً، وهل على
الفرع البعيد ما ليس عندك، وحالةَ طلبك في GitHub. رمزُ الخروج 2 = لا تدفع.
ومعناه اليدويّ إن لم يتوفّر السكربت:

```bash
git fetch origin
git rev-list --left-right --count origin/main...HEAD      # «متأخّر  متقدّم»
git merge-tree --write-tree --name-only HEAD origin/main  # سطرٌ واحد (تجزئة) = نظيف؛ وإلّا ملفّاتُ التعارض
git diff --stat origin/main...HEAD                        # هل كلُّ هذه الملفّات من عملك؟
```

- متقدّمٌ بصفر إيداع = لا تدفع: دفعُ رأسٍ يساوي main يجعل الفرعَ مطابقاً لـmain فيُغلق GitHub الطلبَ تلقائيّاً
  (حادثة #277). المصدر: ذاكرة feedback_check_rebase_before_push.
- لا تحدّث فرعاً نظيفاً غيرَ متعارضٍ بلا داعٍ: كلُّ دفعٍ يعيد كلَّ فحوص CI. المصدر: ذاكرة feedback_merge_queue_branch_lock.

## 4) الدفع (بعد اعتماد المالك وحدَه — تفاصيلُ الاعتماد في مهارة schoolos-flow)

```bash
git push origin HEAD:refs/heads/claude/<اسم-المهمّة>
```

- الوجهةُ صريحةٌ دائماً ولا تُحرّك الرأس ولا تبدّل فرعاً. المصدر: CLAUDE.md «غيت في المحادثات المتوازية» البند 1.
- لا `git push` عارياً: في إعداد git العامّ للمستخدم `push.default=current` (قيس 2026-09-28)، فالعاري يدفع
  فرعَك الحاليّ باسمه فوراً — أي قبل الاعتماد إن سبقتَه. والحارسُ يحجبه وأنت على main فقط.
- فرعٌ دخل طلبُه طابورَ الدمج يرفض الدفعَ بـ`GH006 … merge queue`: لا تُخرجه بنفسك؛ أبلغ جلسةَ «0601 · النشر على
  الإنتاج والدمج». المصدر: ذاكرة feedback_merge_queue_branch_lock وrep10_prune_by_content («ملكُ جلسة النشر»).

## 5) تحديثُ فرعك من main

فرعٌ **منشور** (له نسخةٌ على GitHub): دمجٌ لا إعادةُ أساس، فالدفعُ بعده تقدّمٌ خالصٌ بلا force.

```bash
git fetch origin
git merge origin/main            # حُلّ التعارض، ثمّ git add <المسارات> وgit commit
git diff --stat origin/main...HEAD
```

فرعٌ **لم يُدفع قطّ**: إعادةُ الأساس جائزة، لكن لا تجمعها مع الدفع في أمرٍ واحد، وتحقّق بعدها:
`git status` لا يقول «rebase in progress»، و`git log origin/main..HEAD` غيرُ فارغ.
فرعٌ مكدَّسٌ فوق طلبٍ دُمج بالسحق: `git rebase --onto origin/main <آخرُ إيداعٍ من الطلب المدموج>`.
المصدر: CLAUDE.md البند 4، وذاكرة feedback_check_rebase_before_push وproject_git_roadmap_integration (#604: الدمجُ لا
إعادةُ الأساس للفرع المنشور).

بعد أيّ دمجٍ حُلّ فيه تعارض: افحص `git diff origin/main...HEAD` ملفّاً ملفّاً. حلٌّ اختار نسختك القديمة من ملفٍّ لا
علاقة له بمهمّتك يمحو إصلاحَ غيرك بصمت ولا يُسقطه CI (حادثة #715 مع #709). وفي جدول
`docs/governance/regression_guards.md` تعارضٌ متكرّر: أبقِ صفوفَ الطرفين. المصدر: ذاكرة
feedback_verify_actual_diff_before_enqueue وfeedback_merge_queue_branch_lock.

## 6) تنحيةُ عملٍ جانباً بلا `stash`

الخبيئةُ مشتركةٌ بين كلّ الأشجار (تخبّئ أنت ويستخرج غيرُك)، والحارسُ يحجب كلَّ `stash` عدا `list`/`show`.

- إيداعٌ مؤقّت — **بشرط أن يُقلع**: رأسُ كلّ شجرةِ جلسةٍ يدخل تكاملَ المعاينة على 8500 بعد نحو خمس دقائق، وإقلاعٌ
  يفشل مرّتين متتاليتين يُطفئ التكاملَ للجميع حتى يراجعه المالك. المصدر: `scripts/preview.sh` (`integ_candidates`،
  `apply_main`) وCLAUDE.md «الفلو» البند 3.
  ```bash
  git add <المسارات> && git commit -m "wip: <ما هو>"
  git reset --soft HEAD~1          # لاحقاً، وقبل أيّ دفع: يعيد التعديلات كما كانت (--soft غيرُ محجوب)
  ```
- ما لا يُقلع: رقعةٌ خارج المستودع ثمّ إرجاعُ المسارات بأسمائها.
  ```bash
  git diff -- <المسارات> > C:/Users/<المستخدم>/<اسمك>_work/aside.patch
  git checkout -- <المسارات>       # بأسمائها؛ `checkout .` محجوب
  git apply C:/Users/<المستخدم>/<اسمك>_work/aside.patch   # عند العودة
  ```
  والمجلّدُ خارج المؤقّت (scratchpad يُمسح عند إقلاع جلساتٍ أخرى) وخارج الشجرة (وإلّا ظهر في `git status`).
  المصدر: ذاكرة feedback_scratchpad_wiped_mid_session.

## 7) قراءةُ عمل جلسةٍ أخرى دون لمس شجرتها

الأشجارُ تشترك في مخزن الكائنات: `git show <sha>`، `git log <فرعها>`، `git diff origin/main...<فرعها>` تكفي.
لا `git -C <شجرتها> checkout/switch/reset/commit` أبداً. المصدر: ذاكرة project_git_roadmap_integration (مقارنةُ
REP-18 بين جلستين بـ`git show` من المخزن المشترك).

## 8) جدول: الأمرُ الخطر ← البديلُ الآمن

| الخطر | لماذا | البديل |
|---|---|---|
| `git add -A` / `git add .` | يبتلع ملفّاتِ جلسةٍ أخرى نصفَ مكتوبة | `git add <مسارات>` (و`add -A <مسارات>` مسموح) |
| `git commit -a` | يودِع كلَّ متتبَّعٍ معدَّل | `git add <مسارات>` ثمّ `git commit` |
| `git stash` / `stash pop` | الخبيئةُ مشتركة | إيداعٌ مؤقّت يُقلع، أو رقعةٌ خارج المستودع (§6) |
| `git push` عارياً، أو `git checkout <فرع>` ثمّ push | يدفع/يحرّك ما لا تقصد | `git push origin HEAD:refs/heads/claude/<اسم>` |
| `git push … main` | يتجاوز طلبَ الدمج والبوّابات | فرعُ `claude/…` وطلبُ دمج (schoolos-flow) |
| `push --force` / `--force-with-lease` / `+ref` | يعيد كتابةَ فرعٍ منشور | إيداعٌ إضافيّ أو `git merge origin/main` |
| `git pull --rebase` على شجرةٍ متّسخة | يخلط عملك غيرَ المودَع بإعادة الأساس | `git fetch` ثمّ `git merge origin/main` |
| `git switch/checkout <فرع>` في شجرةٍ ليست لك أو في الجذر | يسحب الأرضَ من تحت جلستها | لا بديل: اقرأ بـ`git show`؛ أو اطلب من صاحبها |
| `git reset --hard` | يمحو غيرَ المودَع | `git reset --soft`/`--mixed`، أو أودِع أوّلاً |
| `git checkout .` / `restore .` / `switch -f` | تجاهلٌ جماعيّ لتعديلات | `git checkout -- <مسارات>`؛ و`restore --staged .` (إلغاءُ التجهيز وحدَه) مسموح |
| `git clean -f` | يمسح غيرَ المتتبَّع بلا رجعة | `git clean -n` (معاينة) ثمّ حذفُ ما هو لك بالاسم |
| `git branch -D` | يُسقط إيداعاتٍ لم تُدمج | `git branch -d` (يرفض غيرَ المدموج)؛ والحكمُ في `03-squash-merge-judgement.md` |
| `commit --no-verify` / `-n` / `SKIP=` | يُسكت فحوصَ الإيداع | أصلِح ما يفشل ثمّ أعِد `git add` والإيداع |
| `prune_local_branches.sh --apply` | حذفٌ جماعيّ للفروع | العرضُ بلا `--apply`؛ الحذفُ بيد المالك |
| `git worktree remove --force` (غيرُ محجوب!) | يمحو غيرَ المودَع بلا نسخة | قائمةُ الفحص في `03-squash-merge-judgement.md` §4، والتنفيذُ لأمين المستودع |
| `.git/info/exclude` لإخفاء ملفّاتك | الملفُّ مشتركٌ فيُعمي `git status` كلَّ الأشجار | انقل الملفّاتِ إلى `C:/Users/<المستخدم>/<اسمك>_work/` |

مصدرُ الجدول: الحارس `.claude/hooks/guard_git.py` (ما هو محجوب فعلاً)، وCLAUDE.md «غيت في المحادثات المتوازية»،
وذاكرة feedback_scratchpad_wiped_mid_session (`info/exclude`).

## أنماطٌ مضادّة

- كتابةُ الأوامر الثلاثة (rebase ثمّ push) في سطرٍ واحدٍ بـ`&&` — دفعُ رأسٍ عالقٍ أغلق طلباً من قبل.
- الوثوقُ بأنّ «الفرع نظيف» لأنّ `git status | head` لم يُظهر شيئاً — اعرض كلَّ السطور.
- `git -C D:/shschool_mvp …` لتعديل شيءٍ «بسيط» في الجذر من جلسة شجرة.
- تحديثُ فرعٍ منشورٍ بـrebase ثمّ محاولةُ دفعه — يلزمه force، وهو محجوبٌ ومحظور.

# فخاخُ ويندوز وMSYS في أوامر غيت

متى تقرأ هذا الملف: حين يعطي أمرُ غيت نتيجةً غريبةً على هذا الجهاز (مسارٌ مشوَّه، ملفٌّ «معدَّل» بلا فرق، سكربتٌ
مكتوبٌ فيه محارفُ تحكّم)، أو قبل أن تسلّم المالكَ أمراً ليشغّله في طرفيّته.

## 1) Git Bash يحوّل مساراتِ الوسائط

`git show origin/main:.github/workflows/x.yml` صار `origin\main;.github\…` لأنّ MSYS ظنّ الوسيطَ مساراً.
ضع `MSYS_NO_PATHCONV=1` قبل الأمر (أو `export` في أوّل السكربت)، وكذلك قبل `docker … -v` و`tasklist /FI`.

```bash
MSYS_NO_PATHCONV=1 git show origin/main:.claude/hooks/guard_git.py
```

المصدر: ذاكرة feedback_windows_shell_classifier_pitfalls، وfeedback_docker_network_pool_exhausted.

## 2) طرفيّةُ المالك PowerShell

ما تكتبه «ليشغّله المالكُ بيده» يُشغَّل في PowerShell كما هو: `rmdir a b` تصير `Remove-Item` بمسارٍ واحد، ومساراتُ
`/d/…` لا تُفهم. اكتب له صيغةَ PowerShell (`Remove-Item -LiteralPath 'D:\…','D:\…'`، بترتيب: المتداخلُ قبل الأصل)،
أو أوامرَ تعمل في الصدفتين (`git …`).
المصدر: ذاكرة feedback_windows_shell_classifier_pitfalls.

رسالةُ إيداعٍ متعدّدةُ الأسطر في PowerShell: here-string مفردُ الاقتباس، وخاتمتُه `'@` في العمود الأوّل على سطرٍ وحدَه.

```powershell
git commit -m @'
عنوانُ الإيداع

الجسم.
'@
```

## 3) heredoc في Bash يطوي الشرطةَ المائلة

نصٌّ فيه `\` يُمرَّر عبر heredoc (ولو بحدٍّ مقتبَس) قد يصل القرصَ بشرطةٍ مطويّةٍ أو محرفِ تحكّم (`\b` صار Backspace
فمرّ اختبارُ حارسٍ بلا أن يفحص شيئاً). كلُّ ملفٍّ فيه شرطةٌ مائلة يُكتب بأداة Write/Edit لا بـheredoc؛ و`SyntaxWarning:
invalid escape sequence` في المخرج = توقّفْ وافحص الملفّ. رسالةُ الإيداع بلا شرطاتٍ مائلة تسلم بـheredoc.
المصدر: ذاكرة feedback_heredoc_backslash (تكرّر ستَّ مرّات).

## 4) نهاياتُ الأسطر

`ruff format` و`Path.write_text` على ويندوز يكتبان CRLF، فيظهر الملفُّ ` M` بلا فرقٍ في المحتوى. `.gitattributes` في main
يفرض `*.py text eol=lf` فيُطبَّع عند الإيداع؛ تحقّق بـ`git ls-files --eol <مسار>`، واكتب بايتاتٍ (`write_bytes`) في
أدواتك. سكربتُ هذه المهارة يعلّم «نهاياتُ أسطرٍ فقط».
المصدر: ذاكرة project_rep10_prune_by_content («ما تعلّمتُه أثناء البناء»)، و`.gitattributes` في main.

## 5) `python3` قد يكون مُشغِّلَ متجرٍ لا يعمل

`command -v python3` ينجح والأمرُ لا يعمل. لذا يجرّب `guard_git.sh` و`prune_local_branches.sh` `python3` ثمّ `python`
ثمّ `py` ويتحقّقان أنّه يعمل؛ واستدعِ أنت سكربتَ المهارة بـ`python`. وإن لم يجد الحارسُ بايثون يعمل طبع «حارسُ الغيت
غيرُ فعّالٍ في هذه الجلسة» — فاعمل كأنّه غائب.
المصدر: `.claude/hooks/guard_git.sh`، `scripts/prune_local_branches.sh`.

## 6) غيت لا يعمل داخل الحاويات

`.git` في شجرة العمل ملفٌّ يشير بمسارٍ مطلقٍ إلى `D:/shschool_mvp/.git/worktrees/<اسم>`، والصورةُ بلا git: شغّل أوامرَ
غيت (وسقّاطاتٍ تحتاجه) على المضيف لا في `docker exec`.
المصدر: ذاكرة project_rep10_prune_by_content («الصورةُ بلا git… وشجرةُ الجلسة تحمل `.git` كملفٍّ بمسارٍ مطلق»)،
وصفُّ «الطبقات» في `docs/governance/regression_guards.md` («على المضيف: `git` ليس في الحاوية»).

## 7) ما يُكتب أين

- **المؤقّت (scratchpad) يُمسح** عند إقلاع جلساتٍ أخرى: ما يلزم أكثرَ من ساعة يُكتب في `C:/Users/<المستخدم>/<اسمك>_work/`.
- **لا داخلَ الشجرة**: يظهر في `git status` ويُربك قاعدةَ «ملفٌّ لا تعرفه = قِف».
- **لا `.git/info/exclude`**: في شجرة العمل هو الملفُّ المشتركُ `D:/shschool_mvp/.git/info/exclude`.
المصدر: ذاكرة feedback_scratchpad_wiped_mid_session.

## 8) الوقت

التواريخُ في سجلّات git بتوقيت UTC غالباً؛ نافذةُ النشر والمواعيدُ بتوقيت الدوحة (UTC+3). المصدر: ذاكرة
feedback_doha_time_on_windows، وCLAUDE.md «نافذةُ النشر».

## أنماطٌ مضادّة

- إعادةُ الأمر نفسِه بعد مسارٍ مشوَّه بدل إضافة `MSYS_NO_PATHCONV=1`.
- إيداعُ ملفٍّ «معدَّل» ليس فيه إلّا CRLF.
- تسليمُ المالك كتلةَ `bash` ليشغّلها في PowerShell.
- ترقيعُ ملفّ بايثون فيه regex عبر `python - <<'PY'`.

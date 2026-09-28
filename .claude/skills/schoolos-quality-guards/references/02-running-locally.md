# إعادةُ إنتاج البوّابة محلّيّاً — بالإصدارات التي تحكم بها

متى تقرأ هذا الملف: تريد أن تعرف هل سيسقط طلبُك قبل الدفع، أو سقط حارسٌ في CI ولا يسقط عندك، أو فشل إصلاحان متتاليان.
خادمُ الجلسة وتشغيلُه وإطفاؤه من مهارة `schoolos-flow`؛ هنا ما يُشغَّل عليه وبأيّ إصدار.

## 1. الإصداراتُ المثبَّتة (من سير العمل لا من requirements-dev)
| الأداة | الإصدارُ الحاكم | مصدرُه | في requirements-dev |
|---|---|---|---|
| Python | 3.12 | `setup-python` في كلّ سير | — |
| ruff | 0.4.4 | `quality-gate.yml`، `.pre-commit-config.yaml` | 0.4.4 |
| mypy / django-stubs / drf-stubs | 1.10.0 / 5.0.2 / 3.15.0 | `requirements-mypy.txt` (مصدرٌ واحد، OWN-30) | يستدعيه بـ`-r` |
| django-migration-linter | 5.2.0 | `quality-gate.yml` | 6.0.0 — انجراف |
| radon | 6.0.1 | `quality-gate.yml`، `quality.yml` | — |
| detect-secrets | 1.5.0 | `quality-gate.yml` | 1.5.0 |
| pip-audit / bandit | 2.7.3 / 1.7.8 | `security-scan.yml` | 2.10.1 / 1.9.4 — انجراف |
| pytest-playwright / axe-playwright-python | 0.9.0 / 0.1.8 | `quality-gate.yml` | مطابق |
| rcssmin (تصغير CSS) | 1.2.2 | `requirements.txt` | — |
لا تحفظ الجدول: `python scripts/guard_margins.py --repo <المستودع>` يطبع `pins.gate` و`pins.drift` من المرجع الحيّ.
حيث تنجرف النسختان، الحاكمُ نسخةُ سير العمل. المصدر: الملفّات المذكورة على main@81bc4937.

## 2. الأوامر (جُرّب كلٌّ منها 2026-09-28 ما لم يُذكر غيرُه)
الحرّاسُ النصّيّة بلا خادمٍ ولا قاعدة (CSS، px، الحجم، الزخرفة، النظائر) — حاويةٌ عابرةٌ بلا شبكة، والشجرةُ للقراءة:
```bash
MSYS_NO_PATHCONV=1 docker run --rm --network none --env-file D:/shschool_mvp/.env \
  -v "<مسار شجرتك>:/app:ro" -w /app -e DJANGO_SETTINGS_MODULE=shschool.settings.testing \
  shschool_mvp-web python -m pytest tests/test_px_tokens.py tests/test_css_budget.py \
  tests/test_css_dead_overrides.py tests/test_css_comment_decoration.py tests/test_file_size.py -q -p no:cacheprovider
```
(31 ناجحاً في 43 ثانية. `-p no:cacheprovider` لازمٌ لأنّ التركيب للقراءة، و`--env-file` لأنّ الإعدادات تطلب SECRET_KEY.)
المصدر: `CLAUDE.md` («ما لا يحتاج قاعدةً يعمل بلا خادم: docker run --rm --network none»).

الاختباراتُ التي تحتاج قاعدة: من خادم جلستك بالأمر الوارد في `CLAUDE.md` (سير العمل، البند 3) بإعدادات `testing`.

ruff — الشجرةُ كلُّها، والبوّابتان معاً:
```bash
~/ruff044_work/bin/ruff.exe check .
~/ruff044_work/bin/ruff.exe format --check .
```
غيرُ موجود؟ `python -m pip install --target ~/<اسم>_work ruff==0.4.4` ثمّ الثنائيّ من `bin/`. تحقّق بـ`--version` أنّه 0.4.4.
لا `python -m ruff` ولا ruff الحاوية (0.15/0.16): تنسيقُهما يخالف 0.4.4 حتى على ملفٍّ جديد (رسالةُ `assert` طويلة).
المصدر: `feedback_ruff_pinned_version`، `feedback_ci_gates_that_bit_2026_09_23`.

mypy — داخل حاوية الجلسة بالإصدارات الثابتة (لم يُجرَّب في هذه الجلسة؛ وصفةُ الذاكرة):
```bash
MSYS_NO_PATHCONV=1 docker compose -p schoolos-$(basename $PWD) --project-directory . \
  -f D:/shschool_mvp/docker-compose.session.yml exec -T web sh -c \
  'pip install -q --target /tmp/mypyci -r requirements-mypy.txt && PYTHONPATH=/tmp/mypyci python -m tests.mypy_ratchet'
```
- علامةُ البيئة الخطأ: أسطرُ «تحذير: … الثابتُ … والمثبَّتُ عندك» أوّلَ المخرَج، أو أعدادٌ تزيد وتنقص معاً. المعتبرُ أسطرُ «زاد».
- بديلٌ على المضيف: `~/crypto_mypy_work/venv` فيه mypy 1.10.0 وdjango-stubs 5.0.2 وdrf-stubs 3.15.0 (تحقّقتُ 2026-09-28)، لكنّ السقّاطةَ تحتاج أيضاً متطلّباتِ المشروع وإعداداتِه — لم تُجرَّب منه.
- ملفٌّ مشتبه: امسح `.mypy_cache` وشغّل mypy عليه وحدَه — التشغيلُ على الأهداف كلِّها قد يُخفي خطأً في ملفٍّ يُفحص عبر استيرادٍ عابر.
- لا `--update` على الأهداف كلِّها: عدِّل سطرَ الملفّ والمجموعَ يدويّاً في `tests/mypy_ratchet_baseline.json` وتحقّق بـ`git diff`.
المصدر: `feedback_mypy_ci_versions`، `feedback_reproduce_ci_before_refix`، `tests/mypy_ratchet.py`.

بقيّةُ البوّابة:
- radon: `radon cc . --exclude "*/migrations/*,*/.venv/*,manage.py,scripts/*,*/scripts/*,tests/*,*/tests/*,*/management/commands/*" --min E --show-complexity` (فارغٌ = يمرّ).
- الأرقامُ الشخصيّة: `python scripts/check_personal_data.py` (المخرجُ مقنَّع).
- الأسرار: `detect-secrets-hook --baseline .secrets.baseline <ملفّات طلبك>` بإصدار 1.5.0 (رمز 0 نظيف). القيمةُ الوهميّة في اختبار: `# pragma: allowlist secret` على سطرها هي، لا على قوس الإغلاق.
- الهجرات: `python manage.py lintmigrations --git-commit-id <أساس الفرع>` بإصدار 5.2.0 — والتفصيلُ في `schoolos-migration-guard`.
المصدر: `quality-gate.yml`، `feedback_ci_gates_that_bit_2026_09_23` (البند 7).

## 3. حرّاسُ المتصفّح (axe، Web Vitals، الجوال، e2e)
- تبدأ بـ`pytest.importorskip("pytest_playwright")` أو `axe_playwright_python`: بلا الحزمة **تتخطّى** ولا تفشل. «مرّ عندي» بلا متصفّح لا يعني شيئاً.
- حاويةُ الجلسة بلا Chromium؛ فلا تُقاس هناك. البديلُ الساكن: `guard_margins.py` لبايتات CSS (الخامّ والمصغَّر)، وهو ما يُسقط `css_kb` في الغالب.
- القياسُ الحيّ المشترك (axe وLighthouse واللقطات) أداةٌ واحدةٌ لكلّ مؤشّر؛ وخادمُ القياس يُقام لقياسٍ محدّدٍ ثمّ يُطفأ (ذاكرةُ الجهاز محدودة، و4 متصفّحاتٍ مع Docker تستنفدها).
المصدر: `tests/test_web_vitals_budget.py`، `tests/test_a11y_axe_ratchet.py`، `project_lane_quality_8204`، `project_container_query_measurement_2026_09_24`.

## 4. إجراءُ «إصلاحان فاشلان»
بعد سقوطَين لبوّابةٍ واحدة بعد إصلاحَين، لا دفعَ ثالثٌ بالتخمين:
1. اقرأ سجلَّ الوظيفة الفاشلة كاملاً (`gh run view <id> --log-failed`) — الأسطرُ التي حكمت لا الملخّص.
2. ابنِ البيئةَ بالإصدارات الحاكمة (§1) خارج المؤقّت (`~/<اسم>_work/`؛ مجلّدُ المؤقّت قد يُمسح أثناء الجلسة).
3. أعِد إنتاج العددَ أو الخطأَ نفسَه الذي رآه CI. إن طابق، فالمحاكاةُ أمينة؛ وإن لم يطابق فالبيئةُ خاطئةٌ لا الشيفرة.
4. أصلِح ما يمسّ الأسطرَ التي حكمت فقط، وقارن `git diff` بالأصل (لا تُضعف منطقاً ولا تحذف تعليلاً لتمرّ).
5. إعادةُ تسمية وحدة: `git grep -n "<الاسم القديم>" origin/main` بكلّ أنواع الملفّات؛ mypy يتغاضى (`ignore_missing_imports = true`).
6. وصفُ الطلب: المقيسُ فقط، وقسمٌ صريحٌ «ما لم يُقَس».
المصدر: `feedback_reproduce_ci_before_refix` (حادثةُ ثلاث محاولاتٍ على #684).

## 5. فخاخُ البيئة
- Git Bash يحوّل `/tmp/x` و`/admin/` إلى مسارات ويندوز: `MSYS_NO_PATHCONV=1` مع docker وgit show. المصدر: `feedback_mypy_ci_versions`.
- قاعدةُ الجلسة المنسوخة قد تتأخّر عشراتِ الهجرات: `migrate` قبل أيّ قياسٍ حيّ. المصدر: `feedback_migrate_after_session_db`.
- حمرةٌ تُخفي حمرة: سيرٌ أحمرُ لسببٍ يحجب ما خلفه؛ بعد الإصلاح الأوّل افحص التشغيلَ التالي فوراً. المصدر: `regression_guards.md` §5.
- `{# … #}` على سطرين يُطبع نصّاً في الصفحة: `tests/test_template_tags_are_single_line.py` قبل الدفع متى لمستَ قالباً.
- مسارٌ بـ`@login_required` وحارسُه داخل العرض يُسمّى في `GUARDED_INSIDE` وإلّا سقط `tests/test_every_route_is_guarded.py`.
المصدر: `feedback_ci_gates_that_bit_2026_09_23`.

## أنماطٌ مضادّة
- خطأ: فحصُ ملفّات طلبك وحدَها بـruff الصواب: الشجرةُ كلُّها: البوّابةُ تفحص `.`.
- خطأ: تثبيتُ `requirements-dev.txt` واعتبارُه بيئةَ البوّابة الصواب: إصداراتُ سير العمل (§1).
- خطأ: دفعٌ ثالثٌ «لنرى» الصواب: إعادةُ إنتاجٍ مطابقةٌ أوّلاً (§4).
- خطأ: تشغيلُ خادمٍ مقيمٍ للقياس الصواب: يُقام ثمّ يُطفأ؛ والقياسُ الساكنُ أوّلاً.

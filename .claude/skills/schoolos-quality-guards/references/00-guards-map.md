# خريطةُ الحرّاس — من يحجب الدمج، وأين يعيش كلُّ حارس

متى تقرأ هذا الملف: فشلت وظيفةٌ في CI أو حارسٌ محلّيّاً وتريد أن تعرف ما يحميه وهل يحجب الدمج وما تفعله؛ أو تضيف حارساً وتسأل أين يوضع.
المرجعُ الكامل (قرابة 90 صفّاً بأسبابها ودروسها): `docs/governance/regression_guards.md`. هنا الخلاصةُ التشغيليّة وما تغيّر بعدها.

## 1. ما يحجب الدمج فعلاً (قيس 2026-09-28)
- حمايةُ `main`: فحصان مطلوبان فقط، `ملخص بوابة الجودة` و`Security Summary`، و`strict: true`.
  المصدر: `gh api "repos/{owner}/{repo}/branches/main/protection/required_status_checks"` (قراءة).
- `ملخص بوابة الجودة` (`gate-summary` في `.github/workflows/quality-gate.yml`) يشترط نجاحَ تسع وظائف:
  `test-coverage` · `ruff` · `mypy` · `migration-linter` · `complexity` · `secrets-scan` · `deploy-window` · `axe-a11y` · `e2e`.
  وظيفةُ `tailwind-build` التي تذكرها الوثيقةُ في §3 لم تعد موجودة (حُذف خطُّ بناء Tailwind في VI-12).
- `Security Summary` (`security-scan.yml`) يشترط `!= success` على أربع: `pip-audit-pypi` · `pip-audit-osv` · `bandit` · `django-check`.
- القاعدةُ الحاكمة: وظيفةٌ ليست في `needs` وشرط الفشل داخل الملخّص لا تحجب شيئاً. فحارسٌ جديدٌ يوضع في وظيفةٍ مدرجة
  (كما وُضعت ميزانيّةُ Web Vitals في `axe-a11y`) أو يُضاف اسمُ وظيفته إلى الملخّص في الطلب نفسِه. المصدر: `regression_guards.md` §3 و§4.6.

## 2. وظائفُ البوّابة: ما فيها وما تفعله حين تسقط
| الوظيفة | ما تشغّله | تحجب؟ | حين تسقط |
|---|---|---|---|
| `test-coverage` (pytest — تغطية) | `makemigrations --check`، `check --fail-level WARNING`، ثمّ `pytest -n auto --cov` والعتبةُ `fail_under` في `pyproject.toml` | نعم | فيها كلُّ الحرّاس النصّيّة (CSS، px، الحجم، الطبقات، الهويّة، الوصوليّة، الوثيقة…): اقرأ اسمَ الاختبار الفاشل ثمّ ملفَّه |
| `ruff` | `ruff check .` و`ruff format --check .` بـ0.4.4 على الشجرة كلِّها | نعم | بوّابتان مستقلّتان؛ أعد التنسيق بالثنائيّ 0.4.4 لا بغيره |
| `mypy` | `python -m tests.mypy_ratchet` بإصدارات `requirements-mypy.txt` | نعم | «زاد» = خطأُ أنواعٍ جديد؛ «نقص ولم يُسجَّل» = سجِّل النقص (01) |
| `migration-linter` | `lintmigrations --git-commit-id <الأساس>` بـdjango-migration-linter 5.2.0 | نعم | توسيعٌ ثمّ تقليص — مهارة `schoolos-migration-guard` |
| `complexity` | `radon cc` بـ6.0.1: CC ≥ 31 فشل، 11–30 تحذير (بلا الاختبارات والهجرات والأوامر والسكربتات) | نعم | قسِّم الدالّة؛ لا استثناءَ في الأمر |
| `secrets-scan` | `scripts/check_personal_data.py` ثمّ `detect-secrets-hook` 1.5.0 مقابل `.secrets.baseline` | نعم | رقمٌ شخصيّ بهيئة الحقيقيّ أو قيمةٌ عاليةُ الإنتروبيا (تجزئةٌ في اختبار) — `pragma: allowlist secret` على سطر القيمة نفسِه |
| `deploy-window` | `scripts/deploy_window.py`: الأحد–الخميس 07:00–14:00 بتوقيت الدوحة ممنوعٌ إلّا بوسم «نشر-عاجل» | نعم | توقيتٌ لا عطل: يُعاد تفعيلُ الدمج بعد 14:00 |
| `axe-a11y` | `test_a11y_axe_ratchet.py`، `test_web_vitals_budget.py` + `test_action_cards_fit_narrow_screens.py`، `test_mobile_audit.py` في Chromium/WebKit | نعم | أكثرُ ما يسقط بـCSS: `css_kb` الخامّ، وعُقد axe، وأهدافُ اللمس |
| `e2e` | `pytest tests/e2e/` بـPlaywright | نعم | فيه حرّاسٌ حيّةٌ للتخطيط (1366×768، الزرّ الرئيسيّ مرئيّ، سجلّ الموظفين) |
| `pr-file-collision` | ملفّاتٌ يعدّلها طلبٌ مفتوحٌ آخر | تحذير | نسِّق مع صاحب الطلب الآخر |
| Security Summary (4) | pip-audit 2.7.3 مرّتين، bandit 1.7.8، `check --deploy --fail-level WARNING` | نعم | ثغرةُ تبعيّةٍ أو تحذيرُ إعدادٍ للإنتاج |

المصدر: `.github/workflows/quality-gate.yml` و`security-scan.yml` على main@81bc4937.

## 3. ما لا يحجب الدمج (تقاريرُ وإنذارات)
| السير | متى | ما فيه | لماذا يهمّ 0702 |
|---|---|---|---|
| `nightly.yml` | يوميّاً 02:00 UTC | المجموعةُ كاملةً متسلسلةً + خطوةُ متصفّحٍ منفصلة + Lighthouse للجوال (الأداءُ لا ينزل أكثرَ من 15 نقطة، والوصوليّةُ لا تنزل) | يكشف الاختبارَ المتقلّب وانحدارَ Lighthouse؛ يفتح قضيّةَ فشلٍ ليليّ |
| `quality.yml` | الأحد 06:00 UTC | pip-audit، radon (تقرير)، vulture ومutmut (`continue-on-error` بمهلة)، تغطيةٌ أسبوعيّة، عقودُ API | اتّجاهُ الدَّين؛ كان أحمرَ أسابيعَ لعدم عزل المتصفّح (REP-18) |
| `identity-kpis.yml` | الأحد 03:00 UTC | `scripts/measure_identity_kpis.py . --json` إلى artifact | قراءةٌ أسبوعيّةٌ جاهزة لمؤشّرات الهويّة (V-K*) |
| `visual-snapshots.yml` | كلُّ طلب | لقطاتُ الهويّة: حتميّة ≤ 0.05%، تغيُّر 0.1% وتسامحٌ 12/255؛ وسمُ «تغيير-بصريّ» يجعل الفرقَ ملخّصاً | استشاريٌّ حتى تُقاس عتباتُه من تشغيلات CI |
| `post-deploy-canary.yml` | عند نجاح نشرٍ في Railway | `scripts/canary-check.sh`: الـcommit المنشور حيٌّ وصفحةُ الدخول تُرسم | أوّلُ دليلٍ أنّ النشر وصل |
| `monitor.yml`، `worker-heartbeat.yml` | مجدولان | «ثانويّ، بأفضل جهد» — الجدولةُ تعمل بنحو 4–7% من المعلَن | لا تبنِ عليهما ضماناً |

المصدر: رؤوس الملفّات في `.github/workflows/`، و`regression_guards.md` (Lighthouse، اللقطات، صدق المراقبة).

## 4. عائلاتُ الحرّاس (خلاصة §2 من الوثيقة)
| العائلة | الحرّاس (أمثلة) | ما تحميه | الوظيفة |
|---|---|---|---|
| سقّاطاتُ عدّ | `design_ratchet`، `a11y_ratchet`، `a11y_axe_ratchet`، `mobile_audit`، `mypy_ratchet`، `layering_ratchet`، `file_size_ratchet`، `page_layout_ratchet`، `print_frame_ratchet` | ديونٌ لا تُصفَّر دفعةً: لا تزيد، والنقصُ يُسجَّل | تغطية، mypy، axe-a11y |
| سقوف | `test_css_budget`، `web_vitals.py:BUDGET`، `test_px_tokens`، `test_css_dead_overrides`، Lighthouse | مقياسٌ ينمو مع الميزات: رقمٌ لا يُتجاوز | تغطية، axe-a11y، ليليّ |
| بنيةُ CSS | `test_css_split`، `test_css_layers`، `test_css_selectors`، `test_css_comment_decoration`، `test_dead_classes` | لا قاعدةَ خارج `@layer`، لا محدِّدَ ناقصٌ يُسقط القاعدة، لا زخرفةَ تنفخ الخامّ | تغطية |
| الألوانُ والهويّة | `test_css_colours_are_tokens`، `test_contrast_ratios`، `test_identity_roles`، `test_tailwind_freeze` | لا لونَ حرفيّاً، تباينٌ، Tailwind لا يعود | تغطية |
| الخصوصيّةُ والمستودعُ العامّ | `test_uploads_are_photo_cleaned`، `check_personal_data.py`، `test_teacher_name_map`، `test_no_tracked_gitignored_code` | PDPPL: صورٌ منظَّفة، لا أرقامَ ولا أسماءَ حقيقيّة، لا ملفَّ شيفرةٍ يُسقطه `.gitignore` | تغطية، secrets-scan |
| صدقُ البوّابات | `test_ci_gates_are_honest`، `test_security_gate`، `test_mypy_pins_are_one_source`، `test_nightly_isolates_browser_tests`، `test_regression_guards_doc` | لا `\|\| true` ولا `\| tee` بلا pipefail، إصدارُ mypy من مصدرٍ واحد، الوثيقةُ لا تذكر اختباراً ميّتاً | تغطية |
| التخطيطُ والجوال | `test_rtl_logical_properties`، `test_reflow`، `test_page_layouts`، `test_wcag22_mobile`، `test_every_route_is_guarded` | RTL منطقيّ، لا عرضَ ثابتاً > 320px، نمطُ تخطيطٍ معلَن، كلُّ مسارٍ محروس | تغطية، e2e |

## 5. حين يسقط حارس: ترتيبُ القرار
1. أهو في وظيفةٍ حاجبة؟ إن لا، فهو تقرير: سجِّله للمتابعة ولا توقف الدمج بسببه.
2. «زاد» أو تجاوزٌ للسقف: شيفرتُك أضافت مخالفة — أصلحها أو عوِّضها في الطلب نفسِه.
3. «نقص ولم يُسجَّل»: أحسنت، سجِّل بأمر `--update` المذكور في رسالة الحارس (أو يدويّاً لـmypy، انظر 02).
4. سقوطٌ لا تفهمه بعد إصلاحٍ واحد: أعِد إنتاجه محلّيّاً بالإصدار المثبَّت (02) قبل الدفع الثاني.
5. الحارسُ مخطئٌ فعلاً؟ عدِّل افتراضَه مع سببٍ في رسالة الإيداع — لا بحذفه ولا بتخفيف شرطه (§4.1 من الوثيقة).

## 6. إضافةُ حارسٍ جديد (خلاصة §6)
قِس أوّلاً ← اختر النوع ← اكتب المحلِّلَ باختباراتٍ لمنطقه ← أثبت أنّه يسقط بلا الإصلاح ← ضعه في وظيفةٍ مدرجةٍ في الملخّص
← أضِفه إلى `regression_guards.md` في الطلب نفسِه (`test_regression_guards_doc` يتحقّق أنّ كلَّ اسمٍ مذكورٍ موجود).

## أنماطٌ مضادّة
- خطأ: الحكمُ على «يحجب/لا يحجب» من اسم الوظيفة أو لونها الصواب: من `needs` في `gate-summary` وحماية الفرع.
- خطأ: نقلُ قائمة الملخّص من الوثيقة (فيها `tailwind-build`) الصواب: من `quality-gate.yml` الحيّ.
- خطأ: اعتبارُ فشل `deploy-window` عطلاً الصواب: هو توقيت؛ الطلبُ يعود بعد 14:00 بتوقيت الدوحة.
- خطأ: تخفيفُ اختبارٍ متصفّحيّ (`.first`) ليخضرّ الصواب: الحمرةُ الكاذبة قد تخفي علّةً حقيقيّة (سابقةُ معرّفٍ مكرَّر كشفه اختبارُ `page_nav`). المصدر: `project_lane_quality_8204`.

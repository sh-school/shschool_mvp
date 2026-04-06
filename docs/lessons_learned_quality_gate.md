# Lessons Learned: Quality Gate CI/CD Pipeline Debugging
# الدروس المستفادة: إصلاح خط أنابيب بوابة الجودة CI/CD

**Project / المشروع:** SchoolOS
**Date / التاريخ:** 2026-04-06
**Severity / الخطورة:** Critical -- Pipeline completely broken
**Resolution / الحل:** 8 commits across one debugging session
**Author / الكاتب:** Elite Archive & Knowledge Management

---

## Table of Contents / فهرس المحتويات

1. [Lesson 1: mypy CLI Flag Error](#lesson-1-mypy-cli-flag-error)
2. [Lesson 2: base.py ImproperlyConfigured in CI](#lesson-2-basepy-improperlyconfigured-in-ci)
3. [Lesson 3: Stray Decorators on Helper Functions](#lesson-3-stray-decorators-on-helper-functions)
4. [Lesson 4: Missing View Imports After Refactor](#lesson-4-missing-view-imports-after-refactor)
5. [Lesson 5: Radon --exclude Syntax](#lesson-5-radon---exclude-syntax)
6. [Lesson 6: pytest Not in requirements.txt](#lesson-6-pytest-not-in-requirementstxt)
7. [Lesson 7: pycairo Build Failure in mypy Job](#lesson-7-pycairo-build-failure-in-mypy-job)
8. [Lesson 8: Validation Order Change During Refactoring](#lesson-8-validation-order-change-during-refactoring)
9. [Lesson 9: mypy 849 Type Errors in Legacy Codebase](#lesson-9-mypy-849-type-errors-in-legacy-codebase)
10. [Golden Rules for CI/CD](#golden-rules-for-cicd)

---

## Lesson 1: mypy CLI Flag Error
## الدرس 1: خطأ في أعلام mypy في سطر الأوامر

### What Happened / ماذا حدث
The CI pipeline passed `--django-settings-module` as a CLI flag to mypy. mypy rejected it because it is not a valid command-line argument.

تم تمرير `--django-settings-module` كعلم في سطر الأوامر لـ mypy. رفضه mypy لأنه ليس وسيطة صالحة.

### Root Cause / السبب الجذري
`--django-settings-module` is a **configuration-only** option that belongs in `pyproject.toml` under `[tool.django-stubs]`. It was mistakenly used as a CLI flag.

`--django-settings-module` هو خيار **إعدادات فقط** يوضع في `pyproject.toml` تحت `[tool.django-stubs]`. استُخدم بالخطأ كعلم في سطر الأوامر.

### Fix Applied / الإصلاح المطبق
Set the `DJANGO_SETTINGS_MODULE` environment variable in the CI workflow instead of using the CLI flag.

تم ضبط متغير البيئة `DJANGO_SETTINGS_MODULE` في سير عمل CI بدلا من استخدام العلم.

### Prevention Rule / قاعدة المنع
> **RULE-01:** Before adding any tool flag to CI, verify it exists in the tool's `--help` output. Configuration-file-only options are NOT CLI flags.

> **قاعدة-01:** قبل إضافة أي علم لأداة في CI، تحقق من وجوده في خرج `--help` للأداة. خيارات ملف الإعدادات ليست أعلام سطر أوامر.

---

## Lesson 2: base.py ImproperlyConfigured in CI
## الدرس 2: خطأ ImproperlyConfigured من base.py في CI

### What Happened / ماذا حدث
When `testing.py` does `from .base import *`, Django executes `base.py` first. In CI there is no `.env` file, so `DEBUG=False` and `SECRET_KEY=""`. The guard at line 181 of base.py raises `ImproperlyConfigured` **before** `testing.py` has a chance to set its own `SECRET_KEY`.

عند تنفيذ `from .base import *` في `testing.py`، ينفذ Django ملف `base.py` أولا. في CI لا يوجد ملف `.env`، فيكون `DEBUG=False` و `SECRET_KEY=""`. يرفع الحارس في السطر 181 خطأ `ImproperlyConfigured` **قبل** أن يتمكن `testing.py` من ضبط قيمته.

### Root Cause / السبب الجذري
Security guard in `base.py` validates secrets at module load time. CI has no `.env` file, so required secrets are empty strings when the guard runs.

حارس الأمان في `base.py` يتحقق من الأسرار وقت تحميل الوحدة. CI ليس لديه ملف `.env`، فتكون الأسرار فارغة عند تشغيل الحارس.

### Fix Applied / الإصلاح المطبق
Set `SECRET_KEY`, `FERNET_KEY`, and `EXCEL_PROTECTION_PASSWORD` as environment variables in the CI workflow YAML.

تم ضبط `SECRET_KEY` و `FERNET_KEY` و `EXCEL_PROTECTION_PASSWORD` كمتغيرات بيئة في ملف YAML لسير عمل CI.

### Prevention Rule / قاعدة المنع
> **RULE-02:** Every secret that `base.py` validates at import time MUST have a corresponding `env:` entry in all CI workflow files. Maintain a checklist: if you add a secret guard in settings, add the CI env var in the same PR.

> **قاعدة-02:** كل سر يتحقق منه `base.py` عند الاستيراد يجب أن يكون له إدخال `env:` مقابل في جميع ملفات سير عمل CI. احتفظ بقائمة مراجعة: إذا أضفت حارس سر في الإعدادات، أضف متغير البيئة في CI في نفس طلب السحب.

---

## Lesson 3: Stray Decorators on Helper Functions
## الدرس 3: مزخرفات شاردة على دوال مساعدة

### What Happened / ماذا حدث
During refactoring of `upload_grade_file` (Cyclomatic Complexity 37 down to 12), the `@login_required` and `@role_required` decorators were accidentally left on the extracted helper function `_find_data_start_row` instead of the actual view function. This would cause runtime `TypeError` because decorators expect a view, not a utility function.

أثناء إعادة هيكلة `upload_grade_file` (تعقيد حلقي من 37 إلى 12)، تُركت المزخرفات `@login_required` و `@role_required` بالخطأ على الدالة المساعدة `_find_data_start_row` بدلا من دالة العرض الفعلية.

### Root Cause / السبب الجذري
Copy-paste during extract-method refactoring. The decorators were copied with the code block but not moved back to the correct function.

نسخ ولصق أثناء إعادة الهيكلة باستخراج الدوال. نُسخت المزخرفات مع كتلة الكود ولم تُنقل للدالة الصحيحة.

### Fix Applied / الإصلاح المطبق
Removed decorators from `_find_data_start_row` and ensured they remain on the `upload_grade_file` view function.

أُزيلت المزخرفات من `_find_data_start_row` وتم التأكد من بقائها على دالة العرض `upload_grade_file`.

### Prevention Rule / قاعدة المنع
> **RULE-03:** After every extract-method refactoring, run a grep for `@login_required` and `@role_required` on private helper functions (functions starting with `_`). Decorators on `_`-prefixed functions are almost always a bug.

> **قاعدة-03:** بعد كل إعادة هيكلة باستخراج دوال، شغّل بحثا عن `@login_required` و `@role_required` على الدوال المساعدة الخاصة (التي تبدأ بـ `_`). المزخرفات على دوال `_` هي خطأ في الغالب.

---

## Lesson 4: Missing View Imports After Refactor
## الدرس 4: استيرادات عرض مفقودة بعد إعادة الهيكلة

### What Happened / ماذا حدث
`operations/views.py` was missing 5 imports: `schedule_settings`, `add_exemption`, `remove_exemption`, `toggle_double_period`, `teacher_preferences`. These functions lived in `views_schedule.py` but were not re-exported through `views.py`, causing `AttributeError` on URL resolution at runtime.

كان ملف `operations/views.py` يفتقد 5 استيرادات. هذه الدوال موجودة في `views_schedule.py` لكنها لم تُعاد تصديرها عبر `views.py`، مما يسبب `AttributeError` عند حل عناوين URL.

### Root Cause / السبب الجذري
When views were split into multiple files (`views.py`, `views_schedule.py`), the `__init__`-style re-export from `views.py` was not updated to include the new functions.

عند تقسيم العروض إلى ملفات متعددة، لم يتم تحديث إعادة التصدير من `views.py` لتشمل الدوال الجديدة.

### Fix Applied / الإصلاح المطبق
Added the missing imports to `operations/views.py`.

أُضيفت الاستيرادات المفقودة إلى `operations/views.py`.

### Prevention Rule / قاعدة المنع
> **RULE-04:** When splitting a module into sub-modules, add a CI step that checks: every function referenced in `urls.py` must be importable from the module path used in `urls.py`. A simple `python -c "from operations.views import X"` smoke test per URL-referenced view catches this instantly.

> **قاعدة-04:** عند تقسيم وحدة إلى وحدات فرعية، أضف خطوة CI تتحقق: كل دالة مشار إليها في `urls.py` يجب أن تكون قابلة للاستيراد من مسار الوحدة المستخدم في `urls.py`.

---

## Lesson 5: Radon --exclude Syntax
## الدرس 5: صيغة --exclude في Radon

### What Happened / ماذا حدث
`radon cc --exclude "migrations,.venv,manage.py,scripts,tests"` did not actually exclude those paths. Radon still scanned everything.

لم يستبعد `radon cc --exclude "migrations,..."` تلك المسارات فعليا. استمر radon في فحص كل شيء.

### Root Cause / السبب الجذري
Radon uses `fnmatch` internally, which requires **glob patterns**, not plain directory names. A bare `migrations` does not match `accounts/migrations/0001_initial.py`.

يستخدم radon مكتبة `fnmatch` داخليا، والتي تتطلب **أنماط glob**، وليس أسماء مجلدات عادية.

### Fix Applied / الإصلاح المطبق
Changed to glob-style patterns:
```
--exclude "*/migrations/*,*/.venv/*,manage.py,scripts/*,*/scripts/*,tests/*,*/tests/*,*/management/commands/*"
```

### Prevention Rule / قاعدة المنع
> **RULE-05:** Always test exclude patterns locally before committing. Run `radon cc --exclude "<pattern>" . -s -n C` and verify excluded files do not appear. Document the correct pattern syntax in a comment in the CI YAML.

> **قاعدة-05:** اختبر أنماط الاستبعاد محليا دائما قبل الالتزام. شغّل الأمر وتحقق من عدم ظهور الملفات المستبعدة. وثّق صيغة النمط الصحيحة في تعليق في ملف CI YAML.

---

## Lesson 6: pytest Not in requirements.txt
## الدرس 6: pytest غير موجود في requirements.txt

### What Happened / ماذا حدث
The CI test job failed immediately because `pytest` was not installed. It is a dev dependency that was never added to `requirements.txt`.

فشلت مهمة اختبار CI فورا لأن `pytest` لم يكن مثبتا. هو اعتماد تطوير لم يُضف أبدا إلى `requirements.txt`.

### Root Cause / السبب الجذري
No `requirements-dev.txt` or `[dev]` extras in the project. Dev dependencies were only installed locally and never tracked.

لا يوجد `requirements-dev.txt` أو إضافات `[dev]` في المشروع. كانت اعتمادات التطوير مثبتة محليا فقط ولم تُتبع.

### Fix Applied / الإصلاح المطبق
Added `pip install pytest pytest-django pytest-cov pytest-asyncio factory-boy` to the CI workflow.

أُضيف تثبيت `pytest pytest-django pytest-cov pytest-asyncio factory-boy` إلى سير عمل CI.

### Prevention Rule / قاعدة المنع
> **RULE-06:** Maintain a `requirements-dev.txt` (or `pyproject.toml [project.optional-dependencies] dev = [...]`). CI must install both production AND dev dependencies. If a tool is invoked in CI, its package must be in a tracked requirements file.

> **قاعدة-06:** احتفظ بملف `requirements-dev.txt`. يجب على CI تثبيت اعتمادات الإنتاج والتطوير معا. إذا استُدعيت أداة في CI، يجب أن تكون حزمتها في ملف اعتمادات مُتتبَّع.

---

## Lesson 7: pycairo Build Failure in mypy Job
## الدرس 7: فشل بناء pycairo في مهمة mypy

### What Happened / ماذا حدث
The mypy job installed `requirements.txt` which includes `pycairo`. The build failed because `pycairo` needs system library `libcairo2-dev` which is not present on the CI runner image.

ثبّتت مهمة mypy ملف `requirements.txt` الذي يتضمن `pycairo`. فشل البناء لأن `pycairo` يحتاج مكتبة النظام `libcairo2-dev` غير الموجودة على صورة CI.

### Root Cause / السبب الجذري
Python packages with C extensions need system-level build dependencies. CI runners (Ubuntu) don't have these pre-installed.

حزم Python ذات امتدادات C تحتاج اعتمادات بناء على مستوى النظام. أجهزة CI (Ubuntu) لا تثبتها مسبقا.

### Fix Applied / الإصلاح المطبق
Added `sudo apt-get install -y libcairo2-dev pkg-config` before `pip install` in the mypy job.

أُضيف `sudo apt-get install -y libcairo2-dev pkg-config` قبل `pip install` في مهمة mypy.

### Prevention Rule / قاعدة المنع
> **RULE-07:** For every Python package that wraps a C library (pycairo, Pillow, psycopg2, lxml, etc.), document its system dependency in a `# System deps: libcairo2-dev` comment in `requirements.txt` AND in the CI workflow. When adding such a package, update CI in the same PR.

> **قاعدة-07:** لكل حزمة Python تغلف مكتبة C (مثل pycairo, Pillow, psycopg2)، وثّق اعتمادها على النظام في تعليق في `requirements.txt` وفي سير عمل CI. عند إضافة حزمة كهذه، حدّث CI في نفس طلب السحب.

---

## Lesson 8: Validation Order Change During Refactoring
## الدرس 8: تغيير ترتيب التحقق أثناء إعادة الهيكلة

### What Happened / ماذا حدث
Extracting `_validate_upload_request` from `upload_grade_file` inadvertently changed the validation order. File validation ran **before** assessment lookup. A request from a wrong school with no file would get a 302 (redirect for missing file) instead of the correct 404 (assessment not found). This is a **security-adjacent** bug: it reveals that the URL endpoint exists.

أدى استخراج `_validate_upload_request` إلى تغيير ترتيب التحقق بدون قصد. تحقق الملف يُشغَّل **قبل** البحث عن التقييم. طلب من مدرسة خاطئة بدون ملف سيحصل على 302 بدلا من 404 الصحيح.

### Root Cause / السبب الجذري
When extracting multiple validations into one function, the developer grouped them by "type" (all request validations together) rather than preserving the original execution order. The original order was deliberate: check authorization/resource-existence first, then check input format.

عند استخراج عدة تحققات في دالة واحدة، جمعها المطور حسب "النوع" بدلا من الحفاظ على الترتيب الأصلي. الترتيب الأصلي كان متعمدا.

### Fix Applied / الإصلاح المطبق
Restored original order: assessment lookup first, then file validation.

أُعيد الترتيب الأصلي: البحث عن التقييم أولا، ثم تحقق الملف.

### Prevention Rule / قاعدة المنع
> **RULE-08:** Refactoring MUST preserve observable behavior, including the **order of HTTP status codes** for different error conditions. Write a test matrix: (wrong school + no file -> 404), (right school + no file -> 302), etc. Run this matrix before AND after refactoring.

> **قاعدة-08:** إعادة الهيكلة يجب أن تحافظ على السلوك الملاحظ، بما في ذلك **ترتيب أكواد حالة HTTP** لحالات الخطأ المختلفة. اكتب مصفوفة اختبار وشغّلها قبل وبعد إعادة الهيكلة.

---

## Lesson 9: mypy 849 Type Errors in Legacy Codebase
## الدرس 9: 849 خطأ أنواع mypy في قاعدة الكود القديمة

### What Happened / ماذا حدث
Enabling mypy with `disallow_untyped_defs = true` on the legacy Django codebase produced 849 `no-untyped-def` errors. The CI pipeline failed and could not be unblocked without addressing them.

تفعيل mypy مع `disallow_untyped_defs = true` على قاعدة الكود القديمة أنتج 849 خطأ. فشل خط أنابيب CI ولم يمكن إلغاء حظره.

### Root Cause / السبب الجذري
Strict type checking was enabled all-at-once on a codebase that was never typed. This is an unrealistic gate for a legacy project.

تم تفعيل فحص الأنواع الصارم دفعة واحدة على قاعدة كود لم تكن مُنمّطة أبدا.

### Fix Applied / الإصلاح المطبق
Phase 1: Warn-only mode (mypy runs but does not block the pipeline). Phase 2: Gradual typing -- add types to new code and critical modules incrementally.

المرحلة 1: وضع التحذير فقط. المرحلة 2: إضافة الأنواع تدريجيا.

### Prevention Rule / قاعدة المنع
> **RULE-09:** When introducing a new linter/checker to a legacy codebase, ALWAYS start in warn-only mode. Transition to blocking mode only when errors are below a manageable threshold (< 50). Never gate a pipeline on a tool that produces hundreds of errors on day one.

> **قاعدة-09:** عند إدخال أداة فحص جديدة لقاعدة كود قديمة، ابدأ دائما بوضع التحذير فقط. انتقل إلى وضع الحظر فقط عندما تكون الأخطاء تحت عتبة قابلة للإدارة (< 50).

---

## Golden Rules for CI/CD
## القواعد الذهبية لـ CI/CD

These rules are distilled from the 9 lessons above. They apply to SchoolOS and any Django project.

هذه القواعد مستخلصة من الدروس التسع أعلاه. تنطبق على SchoolOS وأي مشروع Django.

### 1. Test Locally Before Pushing to CI / اختبر محليا قبل الدفع إلى CI
```
# Run every CI command locally first:
mypy --help | grep "django-settings"   # Does the flag exist?
radon cc --exclude "<pattern>" . -n C   # Does the exclude work?
pytest --co                              # Can pytest collect tests?
```

### 2. CI Must Be Self-Contained / يجب أن يكون CI مكتفيا ذاتيا
- Every secret referenced at import time needs a CI env var
- Every system library needed for pip install needs an `apt-get` step
- Every dev tool invoked in CI needs to be in a tracked requirements file
- **Never assume `.env` exists in CI**

- كل سر مشار إليه وقت الاستيراد يحتاج متغير بيئة CI
- كل مكتبة نظام مطلوبة لـ pip install تحتاج خطوة `apt-get`
- **لا تفترض أبدا وجود `.env` في CI**

### 3. Refactoring Must Preserve Observable Behavior / إعادة الهيكلة يجب أن تحافظ على السلوك الملاحظ
- Validation order matters for security (authorization before input validation)
- HTTP status code sequences are part of the API contract
- Decorators must stay on the correct function
- All public imports must be re-exported from the package interface

- ترتيب التحقق مهم للأمان (التفويض قبل تحقق المدخلات)
- تسلسل أكواد حالة HTTP جزء من عقد الـ API
- يجب أن تبقى المزخرفات على الدالة الصحيحة

### 4. Introduce Strictness Gradually / أدخل الصرامة تدريجيا
- New linters on legacy code: warn-only first
- Set a threshold, track progress, convert to blocking when ready
- Never block a pipeline on day one of a new tool

- أدوات فحص جديدة على كود قديم: تحذير فقط أولا
- حدد عتبة، تتبع التقدم، حوّل إلى حظر عند الجهوزية

### 5. The CI YAML Is Production Code / ملف CI YAML هو كود إنتاجي
- Review it with the same rigor as application code
- Comment non-obvious flags and patterns
- Version-control all CI changes -- no manual pipeline edits
- Every CI change needs a local dry-run

- راجعه بنفس دقة كود التطبيق
- علّق على الأعلام والأنماط غير الواضحة
- تحكم بالإصدار لجميع تغييرات CI -- بدون تعديلات يدوية

### 6. Checklist for Every PR That Touches CI / قائمة مراجعة لكل طلب سحب يمس CI

- [ ] All new env vars added to CI workflow
- [ ] All system deps documented and installed
- [ ] All dev tools in requirements-dev.txt
- [ ] All tool flags verified against `--help`
- [ ] Exclude patterns tested locally with sample output
- [ ] Refactored code tested for status code order preservation
- [ ] No decorators on `_`-prefixed helper functions
- [ ] All split-module imports verified against urls.py

---

## Summary Statistics / إحصائيات ملخصة

| Metric | Value |
|--------|-------|
| Total issues found | 9 |
| Pipeline-blocking issues | 8 |
| Security-adjacent issues | 2 (stray decorators, validation order) |
| Environment/config issues | 4 (mypy flag, base.py secrets, pytest missing, pycairo deps) |
| Refactoring regressions | 3 (decorators, imports, validation order) |
| Tool syntax issues | 2 (mypy flag, radon exclude) |
| Commits to fix | 8 |

---

*This document is maintained by the Elite Archive & Knowledge Management department.*
*Last updated: 2026-04-06*

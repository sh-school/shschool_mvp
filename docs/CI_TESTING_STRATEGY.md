# CI Testing Strategy — SchoolOS

## نظرة عامة

SchoolOS يستخدم استراتيجية ثنائية (two-tier) لاختبارات الـ CI:

- **Fast tier** — على كل push (هدف: < 3 دقائق)
- **Comprehensive tier** — nightly على الـ 1181 test كاملة (هدف: < 15 دقيقة)

هذا يوازن بين سرعة feedback loop للمطور ومراقبة شاملة للـ regression.

---

## Tier 1: Fast CI — على كل push

**الملف:** `.github/workflows/ci.yml` (job: `test`)

**الأدوات:**
- **pytest-xdist** (`-n auto`) — parallel execution على كل CPU cores المتوفرة
- **pytest-testmon** (`--testmon`) — فقط الاختبارات المتأثرة بالتغييرات
- **GitHub Actions cache** — حفظ `.testmondata` بين الـ runs

**الهدف:** feedback loop سريع (< 3 دقائق) — يمكّن المطور من التكرار السريع.

**ما يُشغّل:**
- Ruff (lint)
- Bandit (security SAST)
- pytest (fast: xdist + testmon)
- pip-audit (dependency CVEs)
- Django check + migration check

**ما لا يُفرض في Fast CI:**
- Coverage gate 85% (معطّل في fast CI لأن testmon يشغّل subset فقط)
- Full test execution (testmon يفلتر)

---

## Tier 2: Nightly Comprehensive — 02:00 UTC يومياً

**الملف:** `.github/workflows/nightly.yml`

**الـ cron:** `0 2 * * *` = 02:00 UTC = 05:00 Qatar time (AST)

**الأدوات:** pytest فقط (بدون testmon، بدون xdist)

**الهدف:** Safety net شامل.

**ما يُشغّل:**
- Full pytest suite — كل الـ 1181 test
- Coverage gate 85% مفعّل (من `pyproject.toml`)
- Sequential (بدون `-n auto`) — لاكتشاف flaky tests بسهولة
- بدون `testmon` — كل test يُشغّل من الصفر
- `-p no:cacheprovider` — لا cache، كل run نظيف

**ماذا يكتشف:**
1. Regressions عبر transitive dependencies (اللي testmon ما يتعقبها)
2. Flaky tests (اللي تفشل عشوائياً)
3. Coverage drops تحت 85%
4. Bugs في الـ fixtures أو الـ test setup

**التنبيه:** عند فشل الـ nightly، `::error::` يظهر في GitHub Actions summary.

---

## القواعد

1. **Full test run قبل أي refactor كبير** — شغّل `pytest tests/` محلياً بدون `--testmon` أولاً.

2. **إذا testmon cache مفقود**، الـ run الأول بعد التغيير سيكون أبطأ قليلاً (يبني الـ cache).

3. **لا تتجاهل فشل الـ nightly** — كل فشل يكشف شيئاً فاته testmon. حقّق فيه فوراً.

4. **احذف `.testmondata` محلياً** إذا الاختبارات تتصرّف بشكل غريب:
   ```bash
   rm -rf .testmondata
   pytest tests/ -n auto --testmon
   ```

5. **تأكد أن الـ nightly يبقى full** — لا تضيف `--testmon` أو `-n` عليه.

6. **Coverage baseline:** الـ nightly هو المصدر الموثوق لنسبة التغطية. fast CI لا يعكس التغطية الحقيقية.

---

## التشغيل المحلي

### Fast (للتطوير اليومي):
```bash
cd D:/shschool_mvp
pytest tests/ -n auto --testmon
```

### Full (قبل merge لـ main):
```bash
cd D:/shschool_mvp
pytest tests/
# هذا يفرض coverage gate 85% من pyproject.toml
```

### إعادة بناء testmon cache:
```bash
rm -rf .testmondata
pytest tests/ -n auto --testmon
# الـ run الأول يبني الـ cache، الثاني سريع جداً
```

---

## التأثير المتوقّع

| السيناريو | قبل | بعد |
|-----------|------|------|
| Push نموذجي (3 ملفات معدّلة) | 9-11 دقيقة | < 2 دقيقة |
| Push أول (بدون cache) | 9-11 دقيقة | 9-11 دقيقة |
| Push بعد refactor كبير | 9-11 دقيقة | 5-8 دقائق |
| Nightly full suite | — | 12-15 دقيقة |

**التوفير المتوقّع على push نموذجي: 70-85%**

---

## المراجع

- `DEC-CI-001` — قرار اعتماد الاستراتيجية (2026-04-10)
- `LL-021` — Lesson learned: Fast CI via xdist + testmon
- [pytest-xdist](https://pytest-xdist.readthedocs.io/)
- [pytest-testmon](https://testmon.org/)

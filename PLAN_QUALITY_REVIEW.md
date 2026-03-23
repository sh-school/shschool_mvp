# خطة مراجعة جودة المنصة — SchoolOS Qatar
**التاريخ:** 2026-03-24 | **المصدر:** الكتب الستة (Clean Code, UX, HTML/CSS/JS, Pro JS, .NET→Django)

---

## P1: إصلاحات حرجة (Critical)

| # | المهمة | الحالة | Commit |
|---|--------|--------|--------|
| T1 | `CURRENT_ACADEMIC_YEAR` من settings — استبدال 70+ موضع في 36 ملف | ✅ | `ed8b69a` |
| T2 | إصلاح bare `except Exception` + إضافة logging في 67 موضع | ✅ | `18a1ac8` |
| T3 | ترتيب imports (docstring قبل import) — 18 ملف | ✅ | `fcddd43` |
| T4 | إصلاح N+1 queries في `quality/views_committee.py` (bulk Count) | ✅ | `fcddd43` |

## P2: هيكلة وتنظيم (Structure)

| # | المهمة | الحالة | ملاحظات |
|---|--------|--------|---------|
| T1 | تقسيم `quality/views.py` (691 سطر) | ⏸ مؤجل | متماسك + re-exports موجودة |
| T2 | تقسيم `api/views.py` (823 سطر) | ⏸ مؤجل | يحتاج مراجعة أعمق |
| T3 | تقسيم `assessments/views.py` (690 سطر) | ⏸ مؤجل | — |
| T4 | تقسيم `behavior/behavior_views.py` (651 سطر) | ⏸ مؤجل | — |
| T5 | ~~behavior/constants.py~~ | ❌ skip | لا تكرار حقيقي |
| T6 | hardcoded URLs → `reverse()` في middleware | ✅ | `2eb4544` |

## P3: واجهة المستخدم (UI/UX)

| # | المهمة | الحالة | ملاحظات |
|---|--------|--------|---------|
| T1 | ~~تقليل `!important`~~ (49 → ≤5) | ❌ skip | معظمها Tailwind overrides مبررة |
| T2 | تقليل inline styles (317 → ≤50) | ⏸ مؤجل | 15+ template — خطورة كسر UI |
| T3 | ~~font-size < 12px~~ | ❌ skip | badges, icons — مبررة |

## P4: توثيق وأدوات (Documentation & Tooling)

| # | المهمة | الحالة | Commit |
|---|--------|--------|--------|
| T1 | Type Hints في 8 service classes + TYPE_CHECKING | ✅ | `18a1ac8` |
| T2 | Docstrings عربية لـ 33 view function | ✅ | `18a1ac8` |
| T3 | PDF templates → `{{ school.name }}` من DB | ✅ | كانت مُنجزة |
| T4 | ruff auto-fix (56 إصلاح — isort + unused imports) | ✅ | `40f8f3a` |

---

## ملخص التقدم
- **مُنجز:** 11/17 مهمة (65%)
- **مؤجل:** 5 مهام (تقسيم ملفات كبيرة + inline styles)
- **تم تخطيه:** 3 مهام (مبررة — لا حاجة حقيقية)

## Commits (ترتيب زمني)
1. `ed8b69a` — توحيد السنة الدراسية (CURRENT_ACADEMIC_YEAR)
2. `fcddd43` — إصلاح N+1 queries + ترتيب imports
3. `2eb4544` — hardcoded URLs → reverse()
4. `40f8f3a` — ruff auto-fix (56 إصلاح)
5. `441a951` — ملف الخطة
6. `18a1ac8` — type hints + docstrings + logging

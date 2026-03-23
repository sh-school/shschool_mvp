# خطة مراجعة جودة المنصة — SchoolOS Qatar
**التاريخ:** 2026-03-24 | **المصدر:** الكتب الستة (Clean Code, UX, HTML/CSS/JS, Pro JS, .NET→Django)

---

## P1: إصلاحات حرجة (Critical)

| # | المهمة | الحالة | Commit |
|---|--------|--------|--------|
| T1 | `CURRENT_ACADEMIC_YEAR` من settings — استبدال 70+ موضع في 36 ملف | ✅ | `ed8b69a` |
| T2 | إصلاح bare `except Exception` + إضافة logging في 67 موضع | 🔄 agent | — |
| T3 | ترتيب imports (docstring قبل import) — 18 ملف | ✅ | `fcddd43` |
| T4 | إصلاح N+1 queries في `quality/views_committee.py` (bulk Count) | ✅ | `fcddd43` |

## P2: هيكلة وتنظيم (Structure)

| # | المهمة | الحالة | Commit |
|---|--------|--------|--------|
| T1 | تقسيم `quality/views.py` (689 سطر) | ⏳ | — |
| T2 | تقسيم `api/views.py` (823 سطر) | ⏳ | — |
| T3 | تقسيم `assessments/views.py` (690 سطر) | ⏳ | — |
| T4 | تقسيم `behavior/behavior_views.py` (651 سطر) | ⏳ | — |
| T5 | ~~behavior/constants.py~~ — لا تكرار حقيقي | ❌ skip | — |
| T6 | hardcoded URLs → `reverse()` في middleware | ✅ | `2eb4544` |

## P3: واجهة المستخدم (UI/UX)

| # | المهمة | الحالة | Commit |
|---|--------|--------|--------|
| T1 | ~~تقليل `!important`~~ — معظمها مبررة (Tailwind overrides) | ❌ skip | — |
| T2 | تقليل inline styles (317 → ≤50) | ⏳ | — |
| T3 | ~~font-size < 12px~~ — كلها في أماكن مبررة (badges, icons) | ❌ skip | — |

## P4: توثيق وأدوات (Documentation & Tooling)

| # | المهمة | الحالة | Commit |
|---|--------|--------|--------|
| T1 | Type Hints في 8 service classes | 🔄 agent | — |
| T2 | Docstrings لـ 33 view function | 🔄 agent | — |
| T3 | PDF templates → `{{ school.name }}` من DB | ✅ (كانت مُنجزة) | — |
| T4 | ruff auto-fix (56 إصلاح — isort + unused imports) | ✅ | `40f8f3a` |

---

## ملخص التقدم
- **مُنجز:** 8/17 مهمة (47%)
- **جارٍ:** 3 agents تعمل بالتوازي
- **متبقٍّ:** 3 مهام كبيرة (تقسيم ملفات) + inline styles
- **تم تخطيه:** 3 مهام (مبررة)

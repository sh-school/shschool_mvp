# CHANGES — web-design-mastery

الأصل: `snapshot/.claude/skills/web-design-mastery/` — SKILL 255 سطراً وعشرةُ مراجع (2,278 سطراً، أكبرُها `reports-print.md` 749). التحقّقُ على `origin/main@81bc4937` (2026-09-28) وعلى `CLAUDE.md`.

## سجلُّ الادّعاءات (SKILL.md)
| # | الادّعاء | الحكم | الدليل |
|---|---|---|---|
| 1 | الأنماطُ ثمانيةُ ملفّاتٍ في `static/css/custom/` (ADR-0003) | صحيح | `core/css_files.py` |
| 2 | جملةُ الطبقات `tailwind, reset, base, tokens, layout, components, modules, utilities, themes` | صحيح | `10-foundation.css:27` |
| 3 | الألوانُ القطريّة (`--maroon` #8A1538… `--status-*`، `--text-primary/secondary`) | صحيح | `10-foundation.css:116-191` |
| 4 | `--text-muted: #6b7280` بتباين 4.63 | قديم | `#5f6775` (5.70 على السطح؛ القديم 4.27 على الأرضيّة) |
| 5 | سلّمُ `--text-xs..3xl` | صحيح | `10-foundation.css:274-280` |
| 6 | `--sp-1 → --sp-16` مضاعفاتُ 4 | ناقص | أضيفت النصفيّة `--sp-0-5/1-5/2-5/3-5/4-5`، والسلّم 15 درجة |
| 7 | z: base 1، dropdown 500، navbar 1000، modal 9000، toast 9500 | صحيحٌ ناقص | + raised 100، banner 300، sticky 700، sidebar 1100، nav-menu 1200، critical 9999 |
| 8 | Amiri للجداول (subset ~120KB) | خاطئ للويب | لا Amiri في CSS الويب؛ هو للـPDF (`core/pdf_utils.py`) |
| 9 | سكربتُ الليل يتبع `prefers-color-scheme` | قديم | اختيارٌ صريحٌ فقط: `templates/base/base.html:16`، `base.js` |
| 10 | Nav ليلاً `--maroon-dark`، Cards `#1f2937` | قديم | رموزٌ تنقلب (`--surface` #1e293b ليلاً)؛ القائمةُ رملٌ `--nav-bg` (قرار 2026-09-24) |
| 11 | `.site-nav`، `.nb`، `.nav-bell`، `.nav-user-btn`، `.nav-hamburger`، `.mobile-bottom-nav`، `.msg-bar`، `.sd-menu`، `.progress-qatar` | صحيح | معرَّفةٌ في CSS |
| 12 | `.card-qatar` + `.card-header`؛ `.data-table` «موجود» | خاطئ | `.card-header` و`.data-table` صفرُ تعريف؛ `card-qatar` تعدّه سقّاطةُ الهويّة «بنيةً باليد» |
| 13 | HTMX 1.9.12 محلّيّ، `#htmx-loading-bar`، منطقةُ قارئ الشاشة | صحيح | `static/js/htmx.min.js`، `base.html:68,77,80` |
| 14 | نمطُ `{% if request.htmx %}…{% extends %}{% endif %}` | **خاطئ (لا يعمل)** | `extends` أوّلُ وسمٍ؛ الصحيح `core.htmx_utils.htmx_or_full` |
| 15 | معالجُ `htmx:responseError` و`showToast` من `HX-Trigger` | صحيح | `static/js/app.js:148-170` |
| 16 | `templates/base.html` | قديم | `templates/base/base.html` |
| 17 | لا `?v=N`، `max-age=0` في التطوير | صحيح | `CLAUDE.md`، `development.py:88-90` |
| 18 | Excel من `reports/services.py` (رأسٌ 4 صفوف، badge-72.png) و«django-weasyprint» | قديمٌ/خاطئ | الترويسةُ `add_excel_title_rows` بشعار `logowhite.png`؛ `django-weasyprint` غيرُ مثبَّت (`requirements.txt`) |
| 19 | ميزانيّة «Dashboard < 800KB، جداول < 1.2MB، جوال < 500KB» | غيرُ موثَّق | الحيّ: `tests/web_vitals.py:BUDGET` و`test_css_budget.py` |
| 20 | `--on-fill` لا `#fff` | صحيح | `10-foundation.css:206`، `tests/test_on_fill.py` |
| 21 | «لا `<style>` في القوالب ولا inline» | صحيحٌ مع استثناء | `style=` صفرٌ بالسقّاطة؛ `<style>` مسموحٌ لقوالب PDF وحالاتٍ مسمّاة |

## سجلُّ المراجع العشرة
| المرجعُ القديم | الحالة | أبرزُ ما خالف المنصّة أو CLAUDE.md | صار |
|---|---|---|---|
| `css-architecture.md` (141) | قديمٌ جزئيّاً | لوحةُ `:root` عامّة (`--color-primary: #1a237e`)، `#333`، `prefers-reduced-motion` بـ`!important` | `10-css-architecture.md` + `00-tokens-theming.md`؛ المبادئ في `90` |
| `accessibility.md` (194) | صحيحٌ عامّ | `.skip-link { left: 0; top: -40px }` (فيزيائيّ وpx)؛ غيابُ حرّاس المشروع | `40-accessibility.md` |
| `checklist.md` (145) | **يخالف CLAUDE.md** | «رفعتَ `?v=N` بعد تعديل CSS؟»، «CSS في الملفّ المركزيّ»، «Container queries»، «هوامش 20mm»، INP < 200 | `95-checklist.md` بقيم المنصّة |
| `patterns.md` (233) | عامّ | `.table-responsive`/`.btn--primary` غيرُ معرَّفة، `data-label` بطاقات، `type="module"` | `20`، `30`، `90` |
| `performance.md` (154) | يخالف | ميزانيّاتٌ من كتاب، INP 200، «CSS < 30KB»، خطُّ Cairo، `django-compressor` | `70-performance.md` |
| `reports-print.md` (749) | **يخالف ويكرّر مهارةً أخرى** | لونُ `#1F4E79`، Cairo/Noto Sans، `running()` داخل `@media print`، `django-weasyprint`، `freeze_panes='A2'`، `oddFooter` يمحو الرؤية، اسمُ مدرسةٍ حقيقيّ | `80-print-and-export.md` (26 سطراً) ويحيل إلى `schoolos-report-ar` |
| `responsive.md` (192) | يخالف | mobile-first بـ`min-width` قاعدةً، Container Queries «مفيدةٌ جدّاً»، `max-width: 1140px` | `50-responsive-mobile.md` |
| `svg-icons.md` (179) | يخالف | ورقةٌ مضمَّنة `includes/icon_sprite.html` ووسمُ `svg_tags` خاصّ | `{% icon %}` و`sprite.svg` في `20`؛ المبادئ في `90` |
| `typography.md` (160) | عامّ | خطوطُ Cairo/Noto Kufi، سلّم Perfect Fourth، `[lang=ar] font-size: 1.1em` | `60-typography.md` |
| `visual-design.md` (131) | عامٌّ صحيح | شبكةُ 12 عموداً وBento واتّجاهاتُ 2025 لا تنطبق | مبادئُه في `90-book-principles.md` |

## التغييرات
| البند | القديم | الجديد | السبب | الدليل |
|---|---|---|---|---|
| الوصف | عربيٌّ بلا «ليست لـ» ولا EN | EN ثمّ AR pushy ثمّ «ليست لـ» (report-ar، quality-guards، sma-design، nplus1) | الكرّاسة §2 | BRIEF.md |
| الطول | 255 سطراً | 62 | ≤ 120 | — |
| أنماطُ التخطيط | غائبة | الإجراءُ يبدأ بـ`{% page_layout %}` والأنماطُ السبعة | D-16 وسقّاطة `page_layout_ratchet` | `core/templatetags/ui.py:401`، `docs/design/page_layouts.md` |
| المكوّنات | أصنافٌ بعضُها غيرُ معرَّف | وسومُ `ui.py` بقواعدها التسع، والتنبيهاتُ الخمسة كما في الشيفرة | مصدرٌ واحد | `core/templatetags/ui.py` |
| الرموز | 25 رمزاً بعضُها قديم | أدوارُ الألوان (`-fg`، `--on-fill`، `--gold-mark`، القائمةُ والذيل، الرسوم) والسلالمُ كاملة | الحرّاسُ تعدّ الحرفيّ | `10-foundation.css`، `40-themes.css` |
| الليل | قاعدةُ FOUC بـ`matchMedia` | اختيارٌ صريح، رموزٌ تنقلب، `40-themes` وحدَه، حارسا التكافؤ والتباين | الشيفرة | `base.html:16`، `test_dark_parity` |
| CSP وJS | غائب | `nonce`، الإنتاجُ يفرض (`CSP_ENFORCE`)، مفرداتُ `actions.js`، IIFE | معالجٌ مضمَّنٌ يموت في الإنتاج صامتاً | `production.py:374-387`، `actions.js` |
| الميزانيّات | أرقامُ كتب | 269KB مصغَّر، 470KB خامّ، JS 400، LCP/INP/CLS 2500/300/0.1، ≤ 10 أوراق | من ملفّاتها الحيّة | `tests/web_vitals.py:146-155`، `tests/test_css_budget.py:36` |
| `@container` | موصًى به | مرفوضٌ بقرار | ADR-0005 D3، ADR-0006 | — |
| الجوال | عامّ | أربعةُ أجهزة، نقاطُ القطع القائمة، الحرّاسُ M/Q | أمرُ المالك 2026-09-22 | `feedback_all_devices_responsive.md` |
| الطباعة | 749 سطراً تخالف | 26 سطراً + إحالة | تكرارٌ مع `schoolos-report-ar` وتضارب | الكرّاسة §3 |
| الكتب | موزَّعةٌ على المراجع بأمثلةٍ تخالف | `90-book-principles.md` بعمود «في المنصّة» | لا تُحذف معرفةٌ صحيحة ولا تُنقل مخالفة | — |

## تباينٌ بين `CLAUDE.md` والشيفرة الحاليّة (للمالك)
1. **التنبيهات:** `CLAUDE.md` يقول إنّ `warning` سطرٌ ظاهرٌ دائماً؛ `core/templatetags/ui.py` (`TIP_KINDS`) يجعله أيقونةً تُظهر نصَّها بالمرور «قرارُ المالك 2026-09-20»، والظاهرُ `error` و`success` فقط (أو `show=True`). المهارةُ تتبع الشيفرة وتنبّه.
2. **LAY-03:** `CLAUDE.md` يقول «حتى يُبنى LAY-03 اتّبع النمطَ بالأدوات القائمة»؛ الوسمُ `page_layout` مبنيٌّ ومستعمَلٌ في 24 قالباً ومحروسٌ بسقّاطة.
3. **ميزانيّة CSS الخامّ:** `CLAUDE.md` 460KB؛ `tests/web_vitals.py` 470KB.
4. **`docs/governance/regression_guards.md`:** المصغَّرُ 260KB (الحيّ 269KB)، وpx خارج السلّم ≤ 79 (الحيّ 78).

## يحتاج قرارَ المالك أو تأكيدَه
1. تحديثُ `CLAUDE.md` في البنود الأربعة أعلاه (أو تأكيدُ أنّ الشيفرةَ هي الصحيحة).
2. **`templates/behavior/pdf/base_form.html`** يُطبع بـ«SchoolOS v6» في زاوية التذييل (مفصَّلٌ في CHANGES مهارة `schoolos-report-ar`).
3. هل تبقى `90-book-principles.md` (ملخّصُ الكتب العشرة بعد المواءمة) أم تُحذف لأنّ Claude يعرف الكتب؟ أبقيتُها لأنّ التعليمات تمنع حذف معرفةٍ صحيحة، وجعلتُ كلَّ مبدأٍ مقروناً بحكم المنصّة.
4. مسألةٌ مفتوحةٌ من الذاكرة: هل الرملُ المشتقّ للقائمة يدخل حظرَ «Sand #A29475 محظورٌ على المدارس»؟ (`project_nav_footer_colors_2026_09_24.md`: سُئل المالك ولم يُجب).

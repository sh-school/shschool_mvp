# وصفاتُ قياس المسارات التسعة — مؤشّرٌ ← أداة ← مصدر ← تاريخ

متى تقرأ هذا الملف: بعد كلّ نشرٍ لقياس ما مسّه، وفي القراءة الأسبوعيّة للمسارات التسعة، أو حين يُطلب منك رقمُ مؤشّرٍ (PK/UK/V-K/MK/LK/DK/RK…).
المصدر الأصليّ لكلّ وصفة بطاقةُ مسارها في ذاكرة المشروع (`memory/on_demand/<الملف>`)؛ هنا الوصفةُ مختصرةً ومتحقَّقاً من وجود أداتها يومَ 2026-09-28.
لا قيمَ هنا عمداً: القيمةُ تُقاس اليومَ بأداتها، والقديمةُ في بطاقة المسار بتاريخها. الحالةُ المتقلّبة (مفتوح/منجز/نسبة) من `/roadmap/` لا من الذاكرة.

## 1. قواعدُ القياس (تسري على كلّ الجداول)
- مؤشّرٌ واحدٌ = أداةٌ واحدةٌ = مالكٌ واحد؛ قيمتان لمؤشّرٍ واحدٍ ممنوعتان. أدواتُ axe وLighthouse وRUM ولقطاتِ المقارنة مشتركة
  (كانت لمسار الجودة؛ والقياسُ الدوريّ اليوم لـ0702). المصدر: `project_lane_quality_8204`، ميثاق 0702 في `delivery_manager_work/docs/tab_charters.md`.
- كلُّ قراءة: القيمة + التاريخ بتوقيت الدوحة + الأداة أو الأمر + المرجع (sha أو «الإنتاج»). بلا اشتقاقٍ للنسبة ← «اقتراحُ صاحبه لا قياساً».
- اذكر «محلّيّ لا إنتاج» حين تقيس على قاعدة جلسةٍ ببياناتٍ مزروعة (سطح المكتب، الجوال). المصدر: `project_track_desktop_8207`.
- مؤشّرٌ يغيّره غيرُك أثناء القياس (عددُ الفروع مثلاً) يُقاس مرّتين بفاصلٍ ويُعتمد بعد الاستقرار. المصدر: `project_lane_quality_8204` (RK1).
- ما يحتاج الإنتاج: أمرُ قراءةٍ بأعدادٍ فقط يُجهَّز للمالك ويشغّله هو؛ لا أسماءَ ولا أرقامَ شخصيّةً في أيّ مخرَج. المصدر: `project_lane_sec_state`، `project_ops_track_owner_2026_09_25`.
- القاعدةُ المحلّيّة للخارطة قد تنجرف عن الهجرات المدموجة: قارنها بـ`/roadmap/` وبـ`roadmap/migrations/` على `origin/main`. المصدر: `feedback_local_roadmap_db_drift`.

## 2. أدواتٌ مشتركة (متحقَّقٌ من وجودها)
| الأداة | ماذا تعطي | أين |
|---|---|---|
| `scripts/guard_margins.py` (هذه المهارة) | هوامشُ CSS والحجم، خطوطُ أساس السقّاطات، الإصداراتُ وانجرافُها | `--repo <المستودع> --ref origin/main` |
| `scripts/measure_identity_kpis.py . --json` | مؤشّراتُ الهويّة K02..K20 وما بعدها (V-K*) | المستودع؛ ويشغّله `identity-kpis.yml` أسبوعيّاً إلى artifact |
| `scripts/measure_layout_kpis.py . --json` | LK1..LK5 (أنماطُ التخطيط، تحليلٌ نصّيٌّ للقوالب) | المستودع |
| `scripts/prune_local_branches.py --json --no-fetch` | RK1 (وRK2/RK3 مرشَّحاتٍ لا قراءةً رسميّة) — **بلا `--apply` ولا `--archive` أبداً** | المستودع |
| `~/quality_lane_work/measure_quality_kpis.py <شجرة>` | PK6، UK11، PK7، V-K20، V-K25، تغطيةُ axe — أسطرُ «رمز = قيمة \| مصدر» | خارج المستودع، قراءةٌ فقط |
| مركزُ قيادة الجودة `/command-center/` | لوحاتٌ حيّة من الإنتاج (النشر، الامتثال، الحرّاس والميزانيّات، الأداء…) — «غيرُ معلوم» ليس أخضر | صفحةُ المطوّر في المنصّة؛ `docs/governance/quality_command_center.md` |

## 3. الوصفاتُ حسب المسار
### sec — الأمن والامتثال (`project_lane_sec_state`)
| المؤشّر | الأداة | المصدر |
|---|---|---|
| UK6 حقولُ هويّةٍ صريحة في نموذج المستخدم | بحثٌ نصّيٌّ في `core/models/user.py` (وكيلٌ لا فحصُ مخطّط) | الشيفرة على main |
| UK4 وUK5 وPK3 أعمدةُ PII المعطوبة | `manage.py repair_pii_columns --check` — قراءةٌ بأعدادٍ فقط، على الإنتاج بيد المالك | الإنتاج؛ PK2..PK4 مرآةُ UK2..UK4 لا إعادةُ قياس |
| RK5 أرقامٌ شخصيّةٌ في المستودع | `python scripts/check_personal_data.py` | main (وفي `secrets-scan`) |
| صفرُ حسابٍ على كلمةٍ مؤقّتة (OWN-25) | عدُّ `must_change_password=True` للكادر — أمرُ قراءةٍ بيد المالك | الإنتاج |

### backend — الخلفيّة والبيانات (`project_track_backend_8202`)
| المؤشّر | الأداة | المصدر |
|---|---|---|
| PK5 (= UK9) مدخلاتُ العروض المخالفة | `python -m tests.layering_ratchet` ← `views` | `tests/layering_baseline.json`؛ السلسلةُ التاريخيّة بـ`git show <إيداع>:tests/layering_baseline.json` |
| UK8 استيراداتُ core النازلة | المصدرُ نفسُه ← `core_imports` (تطبيقات) وعددُ الجمل | ADR-0004 |
| UK12 أكبرُ ملفٍّ في `operations/services` | `wc -l` | الشجرة؛ ولا يرى `student_affairs/views.py` — انظر DK1 |
| UK18 استعلاماتُ التقارير | لا اختبارَ عدٍّ لها بعد | غيرُ مقيس |

### ops — التشغيل والموثوقيّة (`project_ops_track_owner_2026_09_25`)
| المؤشّر | الأداة | المصدر |
|---|---|---|
| PK15 زمنُ الطلب حتى الدمج | `gh pr list --state merged --search "merged:>=<قبل 14 يوماً> base:main" --json number,createdAt,mergedAt` ← الوسيط | GitHub |
| PK16 وRK7 النشرُ ونشرُ الدوام | `gh api "repos/{owner}/{repo}/deployments"` وحالةُ كلّ نشر؛ التجميعُ بالـsha (سجلٌّ لكلّ خدمة)، والدوحةُ UTC+3، والعاجلُ بوسم «نشر-عاجل» | GitHub |
| RK8 فجواتُ المراقبة المجدولة | `gh run list --workflow <ملفّ السير> --json createdAt,conclusion` ← أكبرُ فرقٍ بين تشغيلين | GitHub |
| RK1 الفروعُ الراكدة | `prune_local_branches.py --json --no-fetch` ← `metrics.RK1` (يستثني الحيَّ والمفتوحَ بطلب) | المستودع المحلّيّ |
| RK3 أشجارُ العمل | `git worktree list` (العددُ الكلّيّ) | المستودع المحلّيّ |
| UK22 الطلباتُ المفتوحة | `gh pr list --state open` | GitHub |
| أخطاءُ Sentry | عدّاداتٌ فقط بإذن المالك، لا حمولاتُ أحداث | لوحة Sentry — المعرّفاتُ في بطاقة المسار لا تُنسخ |

### quality — الجودة والاختبارات والوثائق (`project_lane_quality_8204`)
| المؤشّر | الأداة | المصدر |
|---|---|---|
| PK6 (= UK10) أخطاءُ mypy | مجموعُ `tests/mypy_ratchet_baseline.json` (قيمةُ البوّابة بـ1.10.0) | main |
| UK11 وحداتٌ تحت mypy | عددُ `TARGETS` في `tests/mypy_ratchet.py` | main |
| PK7 التخطّي | ثابتٌ: `xfail` + `skip` غيرُ مشروط (AST)؛ تشغيليّ: skipped+xfailed من ملخّص pytest في Nightly | `measure_quality_kpis.py`، `gh run view --log` |
| V-K20 أنماطٌ مضمَّنة | `measure_identity_kpis.py` ← `K20_inline_style_attrs_and_blocks` (لا تعريفَ ثانٍ) | main |
| V-K25 صفحاتٌ بلقطاتٍ آليّة | `tests/visual_snapshots.py::matrix()` | main؛ «مقيسٌ بتشغيلٍ ناجح» بعد أوّل تشغيلٍ أخضر لـ`visual-snapshots.yml` |
| تغطيةُ axe | `PAGES` + `EVALUATION_PAGES` في `tests/test_a11y_axe_ratchet.py` من عدد الصفحات | main |
| PK18 وثائقُ حيّة | أربعُ وثائق بتاريخ مراجعةٍ ≤ 90 يوماً | الوثائقُ نفسُها |
| خضرةُ Nightly/الأسبوعيّ | `gh run list --workflow nightly.yml --event schedule --limit 3` (ومثله `quality.yml`) | GitHub |

### frontend — الواجهة والهويّة (`project_track_frontend_8205`)
| المؤشّر | الأداة | المصدر |
|---|---|---|
| V-K01 CSS المصغَّر | `guard_margins.py` ← `css.shipped_bytes` (أو `tests.css_source.shipped_size()`) | main؛ هو نفسُه MK14 — مالكٌ واحد |
| هامشُ الخامّ (DBT-36 سابقاً) | `guard_margins.py` ← `css.raw_margin_bytes` | main |
| V-K02..V-K19 | `measure_identity_kpis.py . --json` | main أو artifact `identity-kpis` |
| LK1..LK5 | `measure_layout_kpis.py . --json` | main |
| أصنافُ Tailwind | `python ~/frontend_track_work/tailwind_classes.py <الجذر> --list` | main؛ والحارسُ `tailwind_freeze_baseline.json` |

### mobile — الجوال وتجربة المستخدم (`project_track_mobile_8206`)
| المؤشّر | الأداة | المصدر |
|---|---|---|
| MK1..MK5 أهدافُ اللمس والنصّ والتجاوز | `python ~/mobile_track_work/mobile_audit_aggregate.py` من جذر الشجرة | `tests/mobile_audit_baseline.json` (السقّاطةُ تجعله يساوي المقيس) |
| MK14 | = V-K01 | لا قياسَ ثانٍ |
| MK17 وMK24 | `tests/font_scale.py` (`small_declarations`) وعدُّ `font-size:<رقم>px` في `read_css()` | main |
| MK9/MK11/MK18/MK19 | بحثٌ نصّيّ: `100vh` بلا `100dvh`، `type="number"` بلا `inputmode`، z-index خامّ، `.btn-sm` | main |
| MK13 وMK25 | `tests/lighthouse_baseline.json` — مختبريٌّ بأصولٍ خامّ لا رقمُ الإنتاج | main |
| MK12، MK22، MK27 | لا أداةَ بعد (MK22/MK27 تنتظر RUM وموافقة المسؤول عن حماية البيانات) | غيرُ مقيس |

### desktop — سطح المكتب واللابتوب (`project_track_desktop_8207`)
| المؤشّر | الأداة | المصدر |
|---|---|---|
| D1 (= PK14) لوحاتٌ بلا تمرير، وD2 فيضٌ أفقيّ | عدّةُ `~/desktop_lane_work/`: `prep.py` (في حاوية الجلسة بـ`manage.py shell`، دخولٌ بـ`force_login` على نسخة قاعدتك وحدَها) ثمّ `measure.py` (Playwright) ثمّ `summarize.py` | «محلّيّ لا إنتاج»؛ 1366×768 و1366×625 و1920×1080 |
| شريطُ أدوات الجدول (LAY-09) | `desktop_lane_work/toolbar.py` | الارتفاعاتُ هي المعتمدة لا عدّادُ الصفوف |
خادمٌ قصيرٌ بإذن المالك ثمّ يُطفأ؛ لا تُدخل كلمةَ مرور؛ ولا تُرسل لقطاتِ حساباتٍ تُظهر أسماء.

### debt — الديون التقنيّة (`project_track_debt_8208`)
| المؤشّر | الأداة | المصدر |
|---|---|---|
| DK1 ملفّاتٌ فوق 1000 سطر، DK2 فائضُها | `python -c "from tests import file_size_ratchet as r; m=r.measure(); o={k:v for k,v in m.items() if v>r.HARD_LIMIT}; print(len(o), sum(v-1000 for v in o.values()))"` | شجرةٌ نظيفةٌ على main |
| DK3 دوالُّ درجة D (CC 21–30) | `radon cc . --min D --max D` باستثناءات البوّابة (الأمرُ مشتقٌّ من التعريف؛ البطاقةُ لا تحفظ أمرَها) | main |
| DK4 قمعُ المدقّقات | عدُّ `noqa` + `type: ignore` في الشيفرة المتتبَّعة (البطاقةُ تفصلهما) | main |
| DK5 قواعدُ ruff المعطَّلة | قائمةُ `ignore` في `[tool.ruff.lint]` بـ`pyproject.toml` (ومنها مؤقّتة) | main |
| التخطّي بسبب | AST على كلّ `.py` المتتبَّعة: `skip`/`xfail` وسببُها؛ `importorskip` بيئيّةٌ لا تُعدّ | main |

### product — وظائفُ المنتج (`project_product_lane_snapshot_2026_09_25`)
| المؤشّر | الأداة | المصدر |
|---|---|---|
| V-K38 صيغةُ اسم المنتج الواحدة | `git grep` على القوالب والسكربتات والمانيفستين **بلا التعليقات** (العدُّ بالتعليقات كان مضخَّماً) | main |
بنودُ المسار أغلبُها بوّابتُها قرارُ المالك؛ لا مؤشّرَ آليّاً آخرَ موثَّقاً في بطاقته.

## 4. بعد كلّ نشر: ماذا تقيس
| ما مسّه النشر | ما تقيسه |
|---|---|
| `static/css/**` | هامشا CSS (`guard_margins.py`)، V-K01/MK14، px، ومؤشّراتُ الهويّة |
| `templates/**` | LK1..LK5، V-K20، وما تمسّه صفحاتُ رحلات الجوال (MK1..5 عند تحديث خطّ الأساس) |
| `*.py` في `core`/`shschool`/`governance` | PK6، والطبقات (PK5/UK8)، وحجمُ الملفّات (DK1/DK2) |
| هجرةٌ أو مهمّةٌ دوريّة | لوحاتُ مركز القيادة المعنيّة (الهجراتُ المعلَّقة، العامل، النسخ) |
| سيرُ عملٍ أو حارس | خريطةُ الحرّاس (`regression_guards.md`) وقائمةُ `gate-summary` |
وكلُّ نشرٍ: كنارُ ما بعد النشر أخضر؟ ثمّ القراءةُ إلى 0701 والانحرافُ إلى 0204 (04).

## أنماطٌ مضادّة
- خطأ: نقلُ قيمةٍ من بطاقة مسارٍ على أنّها قراءةُ اليوم الصواب: أعِد القياسَ بأداتها واذكر تاريخها.
- خطأ: تعريفٌ ثانٍ لمؤشّرٍ قائم (عدٌّ بـgrep بدل الأداة الرسميّة) الصواب: الأداةُ المسجَّلةُ وحدَها، وتغييرُ التعريف يُعلَن في ملاحظة المؤشّر.
- خطأ: `prune_local_branches.py --apply` «للقياس» الصواب: `--json` وحدَه؛ الحذفُ بإذن المالك المستقلّ.
- خطأ: نسخُ معرّفات Sentry أو الخدمات أو أسماءٍ من اللقطات إلى تقرير الصواب: أعدادٌ وتسمياتٌ وتواريخ فقط.

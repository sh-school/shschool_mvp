---
paths:
  - "static/**"
  - "templates/**"
  - "core/templatetags/ui.py"
  - "core/icons.py"
---

# مرجعُ الهويّة المولَّد: الألوان والأيقونات وأنماط الصفحات

> مولَّدٌ آليّاً من `static/css/custom/` و`core/icons.py` و`docs/design/page_layouts.md` — لا يُحرَّر بيدٍ؛ أعِد توليده بـ`python scripts/gen_identity_reference.py`. يقوم مقامَ صفحات `/styleguide/` لمن لا حسابَ مطوّر له.
> القاعدة: لونٌ برمزٍ لا بقيمة، وأيقونةٌ بمعناها `{% icon "المفتاح" %}`، وصفحةٌ بنمطٍ مسمّى `{% page_layout "…" %}`.

## أنماط الصفحات السبعة

- `layout-dashboard` (لوحة): نظرةٌ واحدةٌ على الحال لصاحب دورٍ، تُقرأ بلا تمرير على `expanded`.
- `layout-hub` (مدخلُ وحدة): صفحةُ الدخول إلى وحدةٍ فيها وظائف كثيرة، يختار منها المستخدم.
- `layout-list` (سجلّ): قائمةُ سجلّاتٍ للبحث والتصفية والفتح.
- `layout-detail` (تفصيل): سجلٌّ واحدٌ بكلّ ما يتعلّق به (طالب، موظّف، بلاغ، زيارة).
- `layout-form` (نموذج): إدخالُ سجلٍّ أو تعديلُه.
- `layout-sheet` (ورقةٌ كثيفة): شبكةٌ من صفوفٍ وأعمدةٍ كثيرة تُقرأ وتُحرَّر في مكانها.
- `layout-report` (تقرير): وثيقةٌ تُقرأ ثمّ تُصدَّر أو تُطبع ورقاً (قرارُ المالك: الكشوفُ الورقيّة تبقى قابلةً للطباعة).

## رموز الألوان (`:root` + `html.dark`)

### الهويّة

| الرمز | نهاراً | ليلاً |
|---|---|---|
| `--maroon` | `#8A1538` | — |
| `--maroon-dark` | `#6b0f2a` | — |
| `--maroon-light` | `#b8294e` | — |
| `--maroon-bg` | `#fdf2f5` | `#3b1125` |
| `--maroon-border` | `#e8b4c3` | `#6b2640` |
| `--gold` | `#D4A843` | — |
| `--gold-mark` | `var(--gold)` | — |
| `--skyline` | `#0D4261` | — |
| `--palm` | `#129B82` | — |
| `--sea` | `#4194B3` | — |
| `--maroon-fg` | `#8A1538` | `#f9a8c9` |
| `--skyline-fg` | `#0D4261` | `#93c5fd` |
| `--gold-deep` | `#c9952e` | `#c9952e` |
| `--maroon-link` | `var(--maroon-fg)` | `#f9a8d4` |

### النصّ والأسطح

| الرمز | نهاراً | ليلاً |
|---|---|---|
| `--text-primary` | `#111827` | `#f1f5f9` |
| `--text-secondary` | `#4b5563` | `#cbd5e1` |
| `--text-muted` | `#5f6775` | `#94a3b8` |
| `--border` | `#e5e7eb` | `#334155` |
| `--border-strong` | `#d1d5db` | `#475569` |
| `--surface` | `#ffffff` | `#1e293b` |
| `--surface-alt` | `#e3e8f0` | `#0f172a` |
| `--page-bg` | `#d7dee8` | `#0f172a` |
| `--focus-color` | `var(--maroon-fg)` | — |
| `--on-fill` | `#ffffff` | — |
| `--border-soft` | `#e2e8f0` | `var(--border)` |
| `--surface-sunken` | `var(--surface)` | `var(--surface-alt)` |

### الترويسة والقائمة والذيل

| الرمز | نهاراً | ليلاً |
|---|---|---|
| `--footer-brand-chip-bg` | `#ffffff` | `#ffffff` |
| `--header-bg` | `var(--maroon)` | `#1a0a12` |
| `--nav-bg` | `#f4f0e7` | `#2c2922` |
| `--nav-fg` | `var(--maroon-dark)` | `var(--on-fill)` |
| `--nav-hover` | `color-mix(in srgb, var(--maroon) 12%, transparent)` | `color-mix(in srgb, var(--on-fill) 12%, transparent)` |
| `--nav-mark` | `var(--maroon)` | `var(--gold)` |
| `--footer-bg` | `var(--header-bg)` | — |
| `--footer-fg` | `var(--on-fill)` | — |
| `--footer-fg-soft` | `#e5cbd3` | `#cbd5e1` |
| `--footer-line` | `color-mix(in srgb, var(--on-fill) 35%, transparent)` | — |
| `--menu-ink` | `#1e293b` | `var(--text-primary)` |
| `--menu-ink-strong` | `#0f172a` | `var(--text-primary)` |
| `--menu-label` | `#5a3928` | `var(--text-muted)` |
| `--menu-divider` | `#f1f5f9` | `var(--border)` |
| `--menu-bg` | `var(--nav-bg)` | — |
| `--menu-hover` | `color-mix(in srgb, var(--maroon) 9%, var(--menu-bg))` | `var(--maroon-bg)` |
| `--menu-rule` | `color-mix(in srgb, var(--menu-bg) 85%, var(--menu-ink-strong))` | — |

### الحالات

| الرمز | نهاراً | ليلاً |
|---|---|---|
| `--status-danger` | `#dc2626` | — |
| `--status-danger-dark` | `#991b1b` | — |
| `--status-danger-bg` | `#fef2f2` | `#3b1114` |
| `--status-danger-border` | `#fecaca` | `#7f1d1d` |
| `--status-warning` | `#d97706` | — |
| `--status-warning-dark` | `#92400e` | — |
| `--status-warning-bg` | `#fef3c7` | `#3a2a08` |
| `--status-warning-border` | `#f59e0b` | `#92400e` |
| `--status-success` | `#16a34a` | — |
| `--status-success-dark` | `#166534` | — |
| `--status-success-bg` | `#dcfce7` | `#0d2a1a` |
| `--status-success-border` | `#86efac` | `#166534` |
| `--status-info` | `#2563eb` | — |
| `--status-info-dark` | `#1e40af` | — |
| `--status-info-bg` | `#dbeafe` | `#10233f` |
| `--status-info-border` | `#93c5fd` | `#1e40af` |
| `--neutral-solid` | `#4b5563` | — |
| `--status-danger-fg` | `#c81e1e` | `#fca5a5` |
| `--status-warning-fg` | `#92400e` | `#fbbf24` |
| `--status-success-fg` | `#166534` | `#86efac` |
| `--status-info-fg` | `#1d4ed8` | `#93c5fd` |
| `--status-success-border-soft` | `#bbf7d0` | `var(--status-success-border)` |
| `--status-warning-border-soft` | `#fde68a` | `var(--status-warning-border)` |
| `--status-info-border-soft` | `#bfdbfe` | `var(--status-info-border)` |
| `--status-neutral-bg` | `#f8fafc` | `var(--surface)` |
| `--status-neutral-fg` | `#475569` | `var(--text-muted)` |
| `--status-warning-bright` | `#f59e0b` | `#f59e0b` |
| `--status-warning-deep` | `#b45309` | `#b45309` |
| `--status-info-strong` | `#1d4ed8` | `#1d4ed8` |
| `--status-danger-tint` | `var(--status-danger-bg)` | `#1a0a0a` |
| `--status-warning-tint` | `var(--status-warning-bg)` | `#1c1305` |
| `--status-warning-tint-strong` | `var(--status-warning-bg)` | `#422006` |
| `--status-warning-tint-deep` | `var(--status-warning-bg)` | `#451a03` |
| `--status-warning-badge-bg` | `var(--status-warning-bg)` | `#351c05` |
| `--status-warning-fg-vivid` | `var(--status-warning-fg)` | `var(--status-warning-bright)` |
| `--status-info-fg-vivid` | `var(--status-info-fg)` | `#60a5fa` |

### ألوان التمييز

| الرمز | نهاراً | ليلاً |
|---|---|---|
| `--accent-teal` | `#0d9488` | — |
| `--accent-teal-fg` | `#0f766e` | `#5eead4` |
| `--accent-orange` | `#ea580c` | — |
| `--accent-orange-fg` | `#c2410c` | `#fdba74` |
| `--accent-purple` | `#7c3aed` | — |
| `--accent-purple-fg` | `#7c3aed` | `#c4b5fd` |
| `--accent-sky` | `#0284c7` | — |
| `--accent-sky-fg` | `#0369a1` | `#7dd3fc` |
| `--accent-rose` | `#e11d48` | — |
| `--accent-rose-fg` | `#be123c` | `#fda4af` |
| `--accent-green` | `#059669` | — |
| `--accent-green-fg` | `#047857` | `#6ee7b7` |

### الرسوم البيانيّة

| الرمز | نهاراً | ليلاً |
|---|---|---|
| `--ring-track` | `#e5e7eb` | `#374151` |
| `--chart-1` | `#8A1538` | `#e78fae` |
| `--chart-2` | `#0D7B6A` | `#2dd4bf` |
| `--chart-3` | `#1A3A5C` | `#a5b4fc` |
| `--chart-4` | `#946f0e` | `#D4A843` |
| `--chart-5` | `#2E7D9A` | `#67b8d6` |
| `--chart-6` | `#6B7280` | `#94a3b8` |

### الأدوار والوحدات

| الرمز | نهاراً | ليلاً |
|---|---|---|
| `--role-executor-bg` | `#eff6ff` | — |
| `--q-silver` | `#C0C0C0` | — |
| `--q-silver-light` | `rgba(192,192,192,0.3)` | — |
| `--q-modal-scrim` | `rgba(0,0,0,.6)` | `rgba(0,0,0,.65)` |
| `--q-badge-warning-bg` | `color-mix(in srgb, var(--caution) 15%, transparent)` | `color-mix(in srgb, var(--caution) 20%, transparent)` |
| `--q-badge-warning-fg` | `var(--caution)` | `var(--status-warning-fg)` |
| `--q-badge-neutral-bg` | `rgba(107,114,128,.12)` | `rgba(148,163,184,.15)` |
| `--swap-bg` | `#f3e8ff` | `rgba(126, 34, 206, .18)` |
| `--swap-border` | `#7e22ce` | — |
| `--swap-fg` | `#6b21a8` | `#d8b4fe` |

### أخرى

| الرمز | نهاراً | ليلاً |
|---|---|---|
| `--control-border` | `#6b7280` | `#64748b` |
| `--popover-bg` | `color-mix(in srgb, var(--status-success) 10%, var(--surface))` | — |
| `--popover-border` | `color-mix(in srgb, var(--status-success) 35%, var(--surface))` | — |
| `--form-band` | `#943634` | — |
| `--form-key-bg` | `#DDD9C3` | — |
| `--print-ink` | `#000000` | — |
| `--print-ink-soft` | `#444444` | — |
| `--dept-sharia` | `#d9ead3` | `#366c23` |
| `--dept-arabic` | `#fce5cd` | `#8f4900` |
| `--dept-math` | `#cfe2f3` | `#0f4b80` |
| `--dept-english` | `#ead1dc` | `#6d2243` |
| `--dept-science` | `#d0e8e4` | `#246b5f` |
| `--dept-biology` | `#eef3cf` | `#70800f` |
| `--dept-chemistry` | `#fad4d0` | `#8f0e00` |
| `--dept-physics` | `#dcd8f0` | `#2a1c73` |
| `--dept-social` | `#fdedb3` | `#8f7000` |
| `--dept-tech` | `#d8e2e6` | `#2e5261` |
| `--dept-business` | `#e8e0c8` | `#705c1f` |
| `--dept-pe` | `#cfe8d8` | `#236b3d` |
| `--dept-arts` | `#f4d9e8` | `#7c134d` |
| `--dept-life-skills` | `#e8ded0` | `#6b4d24` |
| `--dept-other` | `#e8e8e8` | `#52525b` |
| `--shadow-ink` | `#000` | `#000` |
| `--shadow-modal-box` | `var(--shadow-md)` | `0 20px 60px rgba(0,0,0,.6)` |
| `--overlay-scrim` | `rgba(0,0,0,.45)` | `rgba(0,0,0,.65)` |
| `--cmd-scrim` | `rgba(0,0,0,.5)` | `rgba(0,0,0,.7)` |
| `--loading-veil` | `rgba(255,255,255,.4)` | `rgba(15,23,42,.4)` |
| `--admin-header-link` | `#ffe0e9` | `#ffe0e9` |
| `--breadcrumb-hover` | `var(--maroon-dark)` | `#fcc4d8` |
| `--scrollbar-track` | `#f1f5f9` | `var(--surface-alt)` |
| `--scrollbar-thumb-hover` | `var(--maroon-light)` | `#64748b` |
| `--placeholder` | `#6b7280` | `var(--text-muted)` |
| `--placeholder-base` | `#9ca3af` | — |
| `--table-stripe` | `#eef1f5` | `#1a1f35` |
| `--field-border` | `#d1d5db` | `#d1d5db` |
| `--ink-empty` | `#d1d5db` | `#d1d5db` |
| `--skeleton-base` | `#f0f0f0` | `var(--surface)` |
| `--skeleton-shine` | `#e0e0e0` | `var(--border)` |
| `--dropzone-preview-bg` | `var(--surface)` | `#1f2937` |
| `--btn-secondary-hover-bg` | `#fce8ee` | `var(--maroon-bg)` |
| `--free-slot-bg` | `#D1FAE5` | `var(--status-success-bg)` |
| `--free-slot-fg` | `#065F46` | `var(--status-success-fg)` |
| `--caution` | `#ca8a04` | `#ca8a04` |
| `--plan-row-pending` | `rgba(251,191,36,.7)` | `rgba(251,191,36,.7)` |
| `--plan-row-completed` | `rgba(34,197,94,.6)` | `rgba(34,197,94,.6)` |
| `--asg-warning-border` | `#fde68a` | `#fde68a` |
| `--asg-success-border` | `#bbf7d0` | `#bbf7d0` |
| `--login-bg-start` | `var(--maroon-bg)` | `var(--surface-alt)` |
| `--login-bg-mid` | `var(--surface-alt)` | `#1a0a12` |
| `--login-bg-end` | `#f0f4ff` | `var(--status-info-bg)` |
| `--login-card-border` | `rgba(255,255,255,.8)` | `var(--border)` |
| `--login-input-border` | `#d1d5db` | `var(--border)` |
| `--login-input-bg` | `#fafafa` | `var(--surface-alt)` |
| `--login-input-focus-halo` | `color-mix(in srgb, var(--maroon) 10%, transparent)` | `rgba(249,168,201,.15)` |
| `--paper` | `#fff` | `#fff` |
| `--paper-ink` | `#000` | `#000` |
| `--paper-rule` | `#ccc` | `#ccc` |
| `--df-ink` | `#333` | `var(--text-primary)` |
| `--df-ink-strong` | `#222` | `var(--text-primary)` |
| `--df-history-ink` | `#666` | `var(--text-secondary)` |
| `--df-muted` | `var(--text-muted)` | `#b8b8b8` |
| `--df-field-bg` | `#fff` | `#1f0c14` |
| `--df-panel-bg` | `#fafafa` | `#1f0c14` |
| `--df-focus-halo` | `color-mix(in srgb, var(--maroon) 15%, transparent)` | `rgba(245,208,220,.15)` |
| `--df-dot-ring` | `#fff` | `var(--maroon-bg)` |
| `--df-chip-bg` | `#f5f5f5` | `var(--maroon-bg)` |
| `--df-chip-fg` | `#424242` | `var(--text-primary)` |
| `--df-chip-border` | `#bdbdbd` | `var(--maroon-border)` |
| `--df-new-bg` | `#e3f2fd` | `#0d2a4a` |
| `--df-new-fg` | `#0d47a1` | `#bbdefb` |
| `--df-new-border` | `#90caf9` | `#1565c0` |
| `--df-seen-bg` | `#f3e5f5` | `#2d1b3d` |
| `--df-seen-fg` | `#4a148c` | `#e1bee7` |
| `--df-seen-border` | `#ce93d8` | `#6a1b9a` |
| `--df-progress-bg` | `#fff3e0` | `#3e2510` |
| `--df-progress-fg` | `#c24400` | `#ffcc80` |
| `--df-progress-border` | `#ffb74d` | `#e65100` |
| `--df-resolved-bg` | `#e8f5e9` | `#0d3b14` |
| `--df-resolved-fg` | `#1b5e20` | `#a5d6a7` |
| `--df-resolved-border` | `#81c784` | `#2e7d32` |
| `--df-closed-bg` | `#eceff1` | `#263238` |
| `--df-closed-fg` | `#37474f` | `#cfd8dc` |
| `--df-closed-border` | `#b0bec5` | `#546e7a` |
| `--df-high-bg` | `#ffebee` | `#3d0f12` |
| `--df-high-fg` | `#b71c1c` | `#ef9a9a` |
| `--df-high-border` | `#ef9a9a` | `#b71c1c` |
| `--df-low-bg` | `#e0f7fa` | `#0d2a2e` |
| `--df-low-fg` | `#006064` | `#80deea` |
| `--df-low-border` | `#80deea` | `#00838f` |
| `--df-edited-bg` | `#fff3cd` | `#4a3a10` |
| `--df-edited-fg` | `#856404` | `#ffe08a` |
| `--df-edited-border` | `#ffeaa7` | `#6b531a` |
| `--df-success-ring` | `#81c784` | `#4caf50` |

## قاموس الأيقونات (بالمعنى لا بالشكل)

**وحدات المنصّة** (42): `quality` الجودة والخطّة التشغيليّة؛ `behavior` السلوك؛ `dashboard` لوحة التحكّم؛ `library` المكتبة؛ `grades` الدرجات وكشوفها؛ `notifications` الإشعارات؛ `transport` النقل المدرسيّ؛ `observation` الزيارات الصفّيّة؛ `assessments` التقييمات والاختبارات؛ `clinic` العيادة المدرسيّة؛ `staff` شؤون الموظفين؛ `student_info` مركز معلومات الطلبة؛ `wings` أجنحة المدرسة؛ `security` الأمان والصلاحيات؛ `workload` الإسناد والأنصبة؛ `activities` الأنشطة؛ `periods_today` حصص اليوم (حيّة)؛ `schedule` الجدول الدراسي؛ `academic` الشؤون الأكاديميّة والموادّ؛ `parents` أولياء الأمور؛ `breach` خرق البيانات (PDPPL)؛ `messages` الرسائل والبريد؛ `counseling` الإرشاد الاجتماعيّ والنفسيّ؛ `developer` المساعد والمطوّر؛ `exam_control` الكنترول؛ `services` الخدمات المدرسيّة؛ `my_actions` إجراءاتي؛ `plan_execution` تنفيذ الخطّة؛ `self_review` المراجعة الذاتيّة؛ `plan_committee` لجنة منفّذي الخطّة؛ `review_committee` لجنة المراجعة الذاتيّة؛ `staff_register` سجلّ الموظفين؛ `departments` الأقسام التعليميّة؛ `exam_analytics` تحليلات الاختبارات؛ `observation_reports` تقارير الأداء الصفّيّ؛ `elearning` التعليم الإلكترونيّ؛ `mail_unread` الرسائل الجديدة؛ `mail_sent` الرسائل المرسلة؛ `password` كلمة المرور؛ `two_factor` المصادقة الثنائيّة؛ `dev_inbox` صندوق رسائل المطوّر؛ `roadmap` خارطة تجويد المنصّة

**الحياة المدرسيّة** (29): `reinforcement` التعزيز الإيجابيّ؛ `psychology` الأخصائي النفسيّ؛ `behavior_team` فريق سلوك الطلبة؛ `wing_coverage` تغطية الأجنحة والإنابة؛ `absence` الغياب؛ `behavior_violation` مخالفة سلوكيّة (بالدرجة)؛ `attendance_register` رصد الحضور؛ `swap_requests` طلبات التبديل والتنقّلات؛ `behavior_committee` لجنة الضبط والقرار؛ `leave` الإجازات؛ `tardiness` التأخّر؛ `attendance_teacher_absence` غياب المعلّمين والبدلاء؛ `compensation` الحصص التعويضيّة؛ `staff_evaluation` تقييم أداء الموظفين؛ `failing_students` الطلاب المتعثّرون والراسبون؛ `licences` الرخص المهنيّة؛ `bells` التوقيت والأجراس؛ `clinic_visit` زيارة الطالب للعيادة؛ `exemptions` تفريغات المعلّمين؛ `sent_home` استئذان وإرسال للمنزل؛ `restroom` دورة المياه؛ `substitution` تعيين بديل؛ `arabic_subject` اللغة العربيّة؛ `certificates` الشهادات؛ `islamic_ed` التربية الإسلاميّة؛ `prayer` الصلاة والمصلّى؛ `qr_door` رمز باب الشعبة؛ `injury` الإصاباتُ والأضرار؛ `grade_sheets` أوراقُ الرصد والتصحيح

**الكيانات** (7): `students` الطلاب والشُّعب؛ `profile` الملفّ الشخصيّ؛ `children` أبنائي (بوّابة الوليّ)؛ `school_building` المدرسة؛ `teacher` المعلّم؛ `student` الطالب؛ `supervisors` مشرفو الكنترول

**البيانات والتقارير** (10): `location` الموقع والخريطة؛ `stats` الإحصائيّات والتوزيعات؛ `checklist` قائمة بنود؛ `document` مستند؛ `reports` التقارير؛ `date` التاريخ والتقويم؛ `kpi` مؤشّرات الأداء؛ `trend` الاتّجاه عبر الزمن؛ `folder` مجلّد؛ `policy` اللوائح والقرارات الرسميّة

**الأفعال** (25): `edit_record` تحرير سجلّ / ملاحظة؛ `print` طباعة؛ `confirm` تأكيد؛ `export_excel` تصدير Excel؛ `export_pdf` تصدير PDF؛ `refresh` تحديث / إعادة؛ `add` إضافة؛ `search` بحث؛ `import` استيراد؛ `call_parent` استدعاء وليّ الأمر؛ `save` حفظ؛ `delete` حذف؛ `generate` توليد تلقائيّ؛ `link` الربط؛ `student_add` إضافة طالب؛ `download` تنزيل؛ `all_present` الكلّ حاضر؛ `filter` تصفية؛ `upload` رفع؛ `edit` تعديل؛ `user_add` إضافة مستخدم؛ `view` عرض؛ `attach` مرفق؛ `calculate` حساب؛ `user_remove` إزالة مستخدم

**الحالات والتنبيهات** (11): `status_warning` تحذير؛ `status_success` نجاح / مكتمل؛ `status_error` خطأ / مرفوض؛ `time` الوقت والمهلة؛ `status_info` معلومة؛ `empty` لا بيانات؛ `loading` جارٍ التحميل؛ `status_critical` حرِج / عاجل؛ `offline` لا اتّصال؛ `status_blocked` محظور / غير متاح؛ `tip` تلميح

**هيكل الواجهة** (12): `settings` الإعدادات؛ `back` رجوع؛ `close` إغلاق؛ `maintenance` صيانة وأدوات؛ `next` التالي؛ `prev` السابق؛ `theme_dark` الوضع الليليّ؛ `install_app` تثبيت التطبيق؛ `logout` تسجيل الخروج؛ `menu` القائمة؛ `role_switch` تبديل الدور؛ `theme_light` الوضع النهاريّ

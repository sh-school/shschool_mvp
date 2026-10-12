---
paths:
  - "static/**"
  - "templates/**"
  - "core/templatetags/ui.py"
  - "core/icons.py"
---

# رموزُ الألوان (2/2): التمييز والرسوم والأدوار وغيرها

> مولَّدٌ آليّاً — لا يُحرَّر بيدٍ؛ أعِد توليده بـ`python scripts/gen_identity_reference.py`.
> نهاراً في `:root` وليلاً في `html.dark`.

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

---
paths:
  - "static/**"
  - "templates/**"
  - "core/templatetags/ui.py"
  - "core/icons.py"
---

# رموزُ الألوان (1/2): الهويّة والنصّ والترويسة والحالات

> مولَّدٌ آليّاً — لا يُحرَّر بيدٍ؛ أعِد توليده بـ`python scripts/gen_identity_reference.py`.
> نهاراً في `:root` وليلاً في `html.dark`.

### الهويّة

| الرمز | نهاراً | ليلاً |
|---|---|---|
| `--maroon` | `#8A1538` | — |
| `--maroon-dark` | `#75002b` | — |
| `--maroon-light` | `#aa3e55` | — |
| `--maroon-bg` | `#f1d9d5` | `#402c31` |
| `--maroon-border` | `#ffc2c9` | `#888086` |
| `--gold` | `#D4A843` | — |
| `--gold-mark` | `var(--gold)` | — |
| `--skyline` | `#0D4261` | — |
| `--palm` | `#129B82` | — |
| `--sea` | `#4194B3` | — |
| `--maroon-fg` | `#8A1538` | `#f49fab` |
| `--skyline-fg` | `#0D4261` | `#93c5fd` |
| `--gold-deep` | `#c9952e` | `#c9952e` |
| `--maroon-link` | `var(--maroon-fg)` | `#f9a8d4` |

### النصّ والأسطح

| الرمز | نهاراً | ليلاً |
|---|---|---|
| `--text-primary` | `#24202a` | `#f9f3f7` |
| `--text-secondary` | `#575055` | `#f9f3f7` |
| `--text-muted` | `#575055` | `#bfb8bd` |
| `--border` | `#d8d2d7` | `#575055` |
| `--border-strong` | `#888086` | `#888086` |
| `--surface` | `#f9f3f7` | `#2c272b` |
| `--surface-alt` | `#ece6ea` | `#413b40` |
| `--page-bg` | `#fff8f1` | `#1b171a` |
| `--focus-color` | `var(--maroon-fg)` | — |
| `--on-fill` | `#ffffff` | — |
| `--border-soft` | `#e2e8f0` | `var(--border)` |
| `--surface-sunken` | `var(--surface)` | `var(--surface-alt)` |

### الترويسة والقائمة والذيل

| الرمز | نهاراً | ليلاً |
|---|---|---|
| `--footer-brand-chip-bg` | `#ffffff` | `#ffffff` |
| `--header-bg` | `var(--maroon)` | `#1a0a12` |
| `--nav-bg` | `#f4f0e7` | `#2c272b` |
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
| `--status-warning` | `#7b3800` | — |
| `--status-warning-dark` | `#92400e` | — |
| `--status-warning-bg` | `#fff2eb` | `#2b0f00` |
| `--status-warning-border` | `#f59e0b` | `#92400e` |
| `--status-success` | `#176239` | — |
| `--status-success-dark` | `#166534` | — |
| `--status-success-bg` | `#deffe7` | `#001f0d` |
| `--status-success-border` | `#86efac` | `#166534` |
| `--status-info` | `#215b75` | — |
| `--status-info-dark` | `#1e40af` | — |
| `--status-info-bg` | `#eaf8ff` | `#001b28` |
| `--status-info-border` | `#93c5fd` | `#1e40af` |
| `--neutral-solid` | `#4b5563` | — |
| `--status-danger-fg` | `#ba1c1c` | `#fca5a5` |
| `--status-warning-fg` | `#7b3800` | `#fbbf24` |
| `--status-success-fg` | `#176239` | `#86efac` |
| `--status-info-fg` | `#215b75` | `#93c5fd` |
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
| `--status-warning-badge-bg` | `var(--status-warning-bg)` | `#351c05` |
| `--status-warning-fg-vivid` | `var(--status-warning-fg)` | `var(--status-warning-bright)` |
| `--status-info-fg-vivid` | `var(--status-info-fg)` | `#60a5fa` |

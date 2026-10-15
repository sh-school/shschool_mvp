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
| `--header-bg` | `#efe6d2` | `#1a0a12` |
| `--header-fg` | `var(--maroon-dark)` | `var(--on-fill)` |
| `--nav-bg` | `#f4f0e7` | `#2c2922` |
| `--nav-fg` | `var(--maroon-dark)` | `var(--on-fill)` |
| `--nav-hover` | `color-mix(in srgb, var(--maroon) 12%, transparent)` | `color-mix(in srgb, var(--on-fill) 12%, transparent)` |
| `--nav-mark` | `var(--maroon)` | `var(--gold)` |
| `--footer-bg` | `var(--header-bg)` | — |
| `--footer-fg` | `var(--maroon-dark)` | `var(--on-fill)` |
| `--footer-fg-soft` | `var(--text-secondary)` | `#cbd5e1` |
| `--footer-line` | `color-mix(in srgb, var(--maroon-dark) 35%, transparent)` | `color-mix(in srgb, var(--on-fill) 35%, transparent)` |
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
| `--status-warning-badge-bg` | `var(--status-warning-bg)` | `#351c05` |
| `--status-warning-fg-vivid` | `var(--status-warning-fg)` | `var(--status-warning-bright)` |
| `--status-info-fg-vivid` | `var(--status-info-fg)` | `#60a5fa` |

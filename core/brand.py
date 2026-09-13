"""ألوانُ الهويّة لِما يُولَّد من بايثون — PDF والرسوم والتصدير.

مصدرُ الحقيقةِ لألوان المنصّة هو `:root` في `static/css/custom.css`، والقوالبُ
تقرأه بـ`var()` و`tailwind.config.js` كذلك. لكنّ ما يُبنى في بايثون — CSS
الـPDF، ولوحاتُ Chart.js، وترويسةُ التصدير — لا يمرّ بمتصفّحٍ يحلّ `var()`،
فيحتاج القيمةَ رقماً.

فهذا الملفُّ مرآةُ تلك الرموز لا مصدرٌ ثانٍ: لكلّ ثابتٍ هنا رمزٌ هناك باسمه،
و`tests/test_design_tokens_resolve.py` يقرأ `:root` ويقارن — فإن تباعدا أخفق
البناء. ولا يُضاف هنا لونٌ لا رمزَ له.
"""

#: `--maroon` — العنّابيّ (Al Adaam)، لونُ العلامة الأوّل.
MAROON = "#8A1538"

#: `--gold`
GOLD = "#D4A843"

#: `--status-danger`
STATUS_DANGER = "#dc2626"

#: `--status-warning`
STATUS_WARNING = "#d97706"

#: `--status-success`
STATUS_SUCCESS = "#16a34a"

#: `--status-info`
STATUS_INFO = "#2563eb"

#: `--accent-orange` — درجةُ خطورةٍ بين المتوسّطة والشديدة
ACCENT_ORANGE = "#ea580c"

#: `--accent-purple`
ACCENT_PURPLE = "#7c3aed"

#: `--text-muted` — قيمتُه النهاريّة. الرماديُّ الفاتحُ تحت نصٍّ أبيضَ نسبتُه 3.40.
TEXT_MUTED = "#5f6775"

#: `--on-fill` — ما يُكتب فوق حشوٍ داكن (ترويسةٌ عنّابيّة).
ON_FILL = "#ffffff"

#: `--maroon-bg` — قيمتُه النهاريّة: الصفُّ المتناوبُ تحت الترويسة العنّابيّة.
MAROON_BG = "#fdf2f5"

#: `--status-warning-bg` — قيمتُه النهاريّة.
STATUS_WARNING_BG = "#fef3c7"

#: `--maroon-light` — الصفُّ الثاني في ترويسة التصدير.
MAROON_LIGHT = "#b8294e"

#: `--border` — قيمتُه النهاريّة: شبكةُ الجداول المصدَّرة.
BORDER = "#e5e7eb"

#: `--text-primary` و`--text-secondary` — قيمتاهما النهاريّتان.
TEXT_PRIMARY = "#111827"
TEXT_SECONDARY = "#4b5563"

#: ألوانُ الحالة للنصّ وأسطحُها — القيمُ النهاريّة المقيسة.
STATUS_DANGER_BG = "#fef2f2"
STATUS_DANGER_FG = "#c81e1e"
STATUS_WARNING_FG = "#92400e"
STATUS_SUCCESS_FG = "#166534"
STATUS_INFO_BG = "#dbeafe"
STATUS_INFO_FG = "#1d4ed8"
ACCENT_ORANGE_FG = "#c2410c"
ACCENT_TEAL_FG = "#0f766e"

#: حدودُ الحالات وحشواتُها الداكنة — للوثائق المطبوعة (PDF والبريد) لا للشاشة.
STATUS_DANGER_BORDER = "#fecaca"
STATUS_DANGER_DARK = "#991b1b"
STATUS_SUCCESS_BG = "#dcfce7"
STATUS_SUCCESS_BORDER = "#86efac"
STATUS_SUCCESS_DARK = "#166534"
STATUS_WARNING_BORDER = "#f59e0b"
STATUS_WARNING_DARK = "#92400e"

#: أسطحُ النهار وحدودُه وأخواتُ العنّابيّ.
SURFACE = "#ffffff"
SURFACE_ALT = "#f9fafb"
PAGE_BG = "#eef1f5"
BORDER_STRONG = "#d1d5db"
MAROON_DARK = "#6b0f2a"
MAROON_BORDER = "#e8b4c3"
SKYLINE = "#0D4261"


#: قيمُ الليل لما يُرسم خارجَ `custom.css` ويتبع الوضع — صفحاتُ الخطأ.
#: الاسمُ اسمُ ثابت النهار، والرمزُ في `TOKEN_OF`؛ ويُقارَن بكتلة `html.dark`.
DARK = {
    "PAGE_BG": "#0f172a",
    "SURFACE": "#1e293b",
    "BORDER": "#334155",
    "TEXT_PRIMARY": "#f1f5f9",
    "TEXT_MUTED": "#94a3b8",
    "MAROON_BG": "#3b1125",
    "MAROON_FG": "#f9a8c9",
    "STATUS_DANGER_FG": "#fca5a5",
    "STATUS_WARNING_FG": "#fbbf24",
}

#: `--maroon-fg` — العنّابيُّ حين يُقرأ نصّاً (ينقلب ليلاً).
MAROON_FG = "#8A1538"


def rgba(colour: str, alpha: float) -> str:
    """`#RRGGBB` مع شفّافيّةٍ — لئلّا تُكتب القناةُ الرقميّةُ نسخةً ثانية."""
    r, g, b = (int(colour.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def excel(colour: str) -> str:
    """openpyxl يأخذ اللونَ ستّةَ أحرفٍ بلا `#` — `excel(MAROON)` ← `"8A1538"`.

    وبلا `#` كان اللونُ يُنسخ في مولّدات Excel فلا يراه حارسُ الألوان.
    """
    return colour.lstrip("#").upper()


#: أسماءُ الرموز المقابلة — يقرؤها الفحصُ ليقارن قيمةً بقيمة.
TOKEN_OF = {
    "MAROON": "maroon",
    "GOLD": "gold",
    "STATUS_DANGER": "status-danger",
    "STATUS_WARNING": "status-warning",
    "STATUS_SUCCESS": "status-success",
    "STATUS_INFO": "status-info",
    "ACCENT_ORANGE": "accent-orange",
    "ACCENT_PURPLE": "accent-purple",
    "TEXT_MUTED": "text-muted",
    "ON_FILL": "on-fill",
    "MAROON_BG": "maroon-bg",
    "STATUS_WARNING_BG": "status-warning-bg",
    "MAROON_LIGHT": "maroon-light",
    "BORDER": "border",
    "TEXT_PRIMARY": "text-primary",
    "TEXT_SECONDARY": "text-secondary",
    "STATUS_DANGER_BG": "status-danger-bg",
    "STATUS_DANGER_FG": "status-danger-fg",
    "STATUS_WARNING_FG": "status-warning-fg",
    "STATUS_SUCCESS_FG": "status-success-fg",
    "STATUS_INFO_BG": "status-info-bg",
    "STATUS_INFO_FG": "status-info-fg",
    "ACCENT_ORANGE_FG": "accent-orange-fg",
    "ACCENT_TEAL_FG": "accent-teal-fg",
    "STATUS_DANGER_BORDER": "status-danger-border",
    "STATUS_DANGER_DARK": "status-danger-dark",
    "STATUS_SUCCESS_BG": "status-success-bg",
    "STATUS_SUCCESS_BORDER": "status-success-border",
    "STATUS_SUCCESS_DARK": "status-success-dark",
    "STATUS_WARNING_BORDER": "status-warning-border",
    "STATUS_WARNING_DARK": "status-warning-dark",
    "SURFACE": "surface",
    "SURFACE_ALT": "surface-alt",
    "PAGE_BG": "page-bg",
    "BORDER_STRONG": "border-strong",
    "MAROON_DARK": "maroon-dark",
    "MAROON_BORDER": "maroon-border",
    "SKYLINE": "skyline",
    "MAROON_FG": "maroon-fg",
}

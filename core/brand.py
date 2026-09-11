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


def rgba(colour: str, alpha: float) -> str:
    """`#RRGGBB` مع شفّافيّةٍ — لئلّا تُكتب القناةُ الرقميّةُ نسخةً ثانية."""
    r, g, b = (int(colour.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


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
}

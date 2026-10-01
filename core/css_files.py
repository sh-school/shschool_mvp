"""ملفّاتُ أنماط المنصّة بترتيب تحميلها — القائمةُ الوحيدة (ADR-0003).

كان `static/css/custom.css` ملفّاً واحداً؛ صار ثمانيةً على حدود الطبقات.
الترتيبُ هنا هو ترتيبُ الوسوم في الصفحة وترتيبُ القراءة في الحرّاس:

- `10-foundation` أوّلاً حتماً: فيه جملةُ ترتيب الطبقات، ولو سبقه ملفٌّ آخر
  لحدّد أوّلُ ظهورٍ للطبقة ترتيبَها.
- `30..34` بتسلسلها: داخل طبقة `modules` يحسم ترتيبُ المصدر عند تساوي النوعيّة.

`34-docs-viewer.css` استثناءٌ: أنماطُ عارض الوثائق (W-20260930-002) لا يراها
إلّا المطوّرون على `/docs/`، فقرارُ المالك D-81م استبعادُها من التحميل العامّ
(`{% custom_css %}` في كلّ صفحة) ومن ميزانيّة `tests/test_css_budget.py` —
قوالبُ العارض وحدَها تحمّلها صراحةً عبر `{% block extra_css %}`. وتبقى في
`CSS_FILES` كاملةً لأنّ الحرّاسَ (ترتيبُ الطبقات، الرموز، التباينُ الليليّ…)
تفحص كلَّ الأنماط بصرف النظر عن كيفيّة تحميلها — `ALWAYS_LOADED_CSS_FILES`
هي ما يحكم التحميلَ الفعليّ والميزانيّةَ وحدَهما.
"""

from django.contrib.staticfiles import finders

CSS_DIR = "css/custom"

CSS_FILES = (
    "10-foundation.css",
    "20-components.css",
    "30-modules-1.css",
    "31-modules-2.css",
    "32-modules-3.css",
    "33-modules-4.css",
    "34-docs-viewer.css",
    "40-themes.css",
    "50-utilities.css",
)

#: ما يُحمَّل على كلّ صفحةٍ عبر `{% custom_css %}` ويدخل في `shipped_size()` —
#: كلُّ شيءٍ عدا `34-docs-viewer.css` (انظر الشرح أعلاه).
ALWAYS_LOADED_CSS_FILES = tuple(name for name in CSS_FILES if name != "34-docs-viewer.css")


def static_names() -> list[str]:
    """أسماءُ كلّ ملفّات الأنماط كما يعرفها `{% static %}` بترتيب التحميل —
    للحرّاس وصفحة دليل الهويّة (`core/styleguide.py`) اللذين يفحصان الأنماطَ
    كلَّها بصرف النظر عن التحميل الفعليّ."""
    return [f"{CSS_DIR}/{name}" for name in CSS_FILES]


def always_loaded_static_names() -> list[str]:
    """أسماءُ الملفّات المحمَّلة فعليّاً في كلّ صفحة — لـ`{% custom_css %}` وحده."""
    return [f"{CSS_DIR}/{name}" for name in ALWAYS_LOADED_CSS_FILES]


def find_paths() -> list[str]:
    """مساراتُها على القرص، فارغةٌ إن غاب أيُّ ملفٍّ (فلا نصفُ نتيجة)."""
    found = [finders.find(name) for name in static_names()]
    paths = [path for path in found if isinstance(path, str)]
    return paths if len(paths) == len(found) else []

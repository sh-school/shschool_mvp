"""ملفّاتُ أنماط المنصّة بترتيب تحميلها — القائمةُ الوحيدة (ADR-0003).

كان `static/css/custom.css` ملفّاً واحداً؛ صار ثمانيةً على حدود الطبقات.
الترتيبُ هنا هو ترتيبُ الوسوم في الصفحة وترتيبُ القراءة في الحرّاس:

- `10-foundation` أوّلاً حتماً: فيه جملةُ ترتيب الطبقات، ولو سبقه ملفٌّ آخر
  لحدّد أوّلُ ظهورٍ للطبقة ترتيبَها.
- `30..33` بتسلسلها: داخل طبقة `modules` يحسم ترتيبُ المصدر عند تساوي النوعيّة.
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
    "40-themes.css",
    "50-utilities.css",
)


def static_names() -> list[str]:
    """أسماءُ الملفّات كما يعرفها `{% static %}` بترتيب التحميل."""
    return [f"{CSS_DIR}/{name}" for name in CSS_FILES]


def find_paths() -> list[str]:
    """مساراتُها على القرص، فارغةٌ إن غاب أيُّ ملفٍّ (فلا نصفُ نتيجة)."""
    found = [finders.find(name) for name in static_names()]
    paths = [path for path in found if isinstance(path, str)]
    return paths if len(paths) == len(found) else []

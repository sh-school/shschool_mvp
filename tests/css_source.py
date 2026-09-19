"""قراءةُ أنماط المنصّة كنصٍّ واحدٍ بترتيب التحميل — للحرّاس (ADR-0003).

كان الحرّاسُ يقرؤون `static/css/custom.css` مساراً واحداً؛ صار الملفُّ ثمانيةً.
`read_css()` تعيد النصَّ متّصلاً بترتيب `core.css_files.CSS_FILES`، وهو
الترتيبُ الذي يراه المتصفّح، فيبقى حكمُ «آخر قاعدةٍ تغلب» على حاله.
"""

import pathlib

from core.css_files import CSS_DIR, CSS_FILES

ROOT = pathlib.Path(__file__).resolve().parent.parent
CSS_ROOT = ROOT / "static" / CSS_DIR


def css_paths() -> list[pathlib.Path]:
    return [CSS_ROOT / name for name in CSS_FILES]


def read_css() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in css_paths())


def css_size() -> int:
    """بايتاتُ المصدر على القرص — بتعليقاته."""
    return sum(path.stat().st_size for path in css_paths())


def shipped_size() -> int:
    """بايتاتُ ما يصل المتصفّحَ: المصدرُ بعد التصغير الذي يجريه `collectstatic` في الإنتاج."""
    from core.static_storage import minify_css

    return sum(len(minify_css(path.read_text(encoding="utf-8")).encode()) for path in css_paths())

"""تخزينُ الملفّات الثابتة في الإنتاج: يُصغِّر أنماطَ المنصّة قبل أن يبصمها (P3-1/P3-2).

`static/css/custom/*.css` مصدرٌ مكتوبٌ للقراءة: ثلثاه تعليقاتٌ عربيّةٌ وفراغات
(≈397KB خاماً، Brotli ≈68.5KB؛ ومصغَّراً ≈31.6KB). والتعليقاتُ تبرير القرارات
فلا تُحذف من المصدر، بل تُحذف من المنتَج وحدَه — وقتَ `collectstatic`.

- التطوير والاختبارات لا تمرّ من هنا: `StaticFilesStorage` يخدم المصدرَ كما هو.
- التصغيرُ قبل البصمة فتُحسب من المنتَج، وتُعاد كتابةُ `url()` (خطوطٌ) على نصّه.
- ملفٌّ خارج `css/custom/` يمرّ كما هو: لا نصغّر ما لم نقِس تكافؤَه.
"""

from collections.abc import Iterator
from typing import Any

import rcssmin
from django.core.files.base import ContentFile
from whitenoise.storage import CompressedManifestStaticFilesStorage

#: ما يُصغَّر — مجلّدُ أنماط المنصّة وحدَه (ADR-0003).
MINIFIED_PREFIX = "css/custom/"


def minify_css(text: str) -> str:
    return str(rcssmin.cssmin(text))


class _MinifiedSource:
    """يُظهر ملفّاً مصدريّاً بنصٍّ مصغَّر لخطوة البصم — لا يمسّ الأصلَ على القرص."""

    def __init__(self, storage: Any) -> None:
        self._storage = storage

    def open(self, name: str) -> ContentFile:
        with self._storage.open(name) as original:
            text = original.read().decode("utf-8")
        return ContentFile(minify_css(text).encode("utf-8"), name=name)


class MinifiedManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    def post_process(
        self, paths: dict[str, tuple[Any, str]], dry_run: bool = False, **options: Any
    ) -> Iterator[tuple[str, str, bool | Exception]]:
        for name, (storage, path) in list(paths.items()):
            if name.startswith(MINIFIED_PREFIX) and name.endswith(".css"):
                paths[name] = (_MinifiedSource(storage), path)
        yield from super().post_process(paths, dry_run, **options)

"""أنماطُ المنصّة تُصغَّر وقتَ `collectstatic` في الإنتاج وحدَه (P3-2).

الثابتُ الذي يُحرَس: المصدرُ يبقى مقروءاً بتعليقاته، والمنتَجُ المبصومُ مصغَّرٌ
لا يفقد قاعدةً ولا مسارَ خطّ. فكلُّ اختبارٍ هنا يجري `post_process` الحقيقيّ
على مجلّدٍ مؤقّت — لا محاكاةً للدالّة.
"""

import importlib.util
import pathlib
import re

import pytest
from django.core.files.storage import FileSystemStorage

from core.static_storage import MINIFIED_PREFIX, MinifiedManifestStaticFilesStorage, minify_css
from tests.css_source import ROOT, css_paths

SOURCE_CSS = """/* تعليقٌ عربيّ يُبرّر القرار — يبقى في المصدر */
@layer base {
  @font-face {
    font-family: 'F';
    src: url('../../fonts/f.woff2') format('woff2');
  }

  :root { --a: 1px; --b: calc(var(--a) + 2px); }

  .x   >   .y { color : red ; margin: 0 auto ; }
}
"""


def _parser():
    spec = importlib.util.spec_from_file_location(
        "split_custom_css", ROOT / "scripts" / "split_custom_css.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def collected(tmp_path, settings):
    """مصدرٌ مؤقّتٌ فيه خطٌّ وأنماطٌ داخل `css/custom/` وأخرى خارجه، بعد `post_process`."""
    settings.STATIC_URL = "/static/"
    src = tmp_path / "src"
    (src / "css" / "custom").mkdir(parents=True)
    (src / "fonts").mkdir()
    (src / "fonts" / "f.woff2").write_bytes(b"wOF2-not-really")
    (src / "css" / "custom" / "10-x.css").write_text(SOURCE_CSS, encoding="utf-8")
    (src / "css" / "other.css").write_text(
        SOURCE_CSS.replace("../../fonts/", "../fonts/"), encoding="utf-8"
    )

    out = tmp_path / "out"
    storage = MinifiedManifestStaticFilesStorage(location=str(out), base_url="/static/")
    source = FileSystemStorage(location=str(src))
    paths = {}
    for name in ("css/custom/10-x.css", "css/other.css", "fonts/f.woff2"):
        with source.open(name) as handle:
            storage.save(name, handle)  # ما يفعله collectstatic قبل post_process
        paths[name] = (source, name)
    results = list(storage.post_process(paths))
    assert not [r for r in results if isinstance(r[2], Exception)], results
    return storage, out, src


def _hashed(out: pathlib.Path, directory: str, stem: str) -> str:
    found = [
        p for p in (out / directory).glob(f"{stem}.*.css") if not p.name.endswith((".gz", ".br"))
    ]
    assert len(found) == 1, found
    return found[0].read_text(encoding="utf-8")


def test_a_platform_sheet_is_served_minified_with_its_font_path_hashed(collected):
    _storage, out, _src = collected
    text = _hashed(out, "css/custom", "10-x")

    assert "\n" not in text.strip()
    assert "تعليقٌ" not in text
    assert re.search(r"url\(.?\.\./\.\./fonts/f\.[0-9a-f]{12}\.woff2", text), text


def test_a_sheet_outside_the_platform_directory_is_left_alone(collected):
    _storage, out, _src = collected
    text = _hashed(out, "css", "other")

    assert "تعليقٌ" in text


def test_the_source_on_disk_keeps_its_comments(collected):
    _storage, _out, src = collected

    assert "تعليقٌ" in (src / "css" / "custom" / "10-x.css").read_text(encoding="utf-8")


def test_only_the_platform_prefix_is_minified():
    assert MINIFIED_PREFIX == "css/custom/"


def test_minifying_keeps_every_rule_of_the_real_sheets():
    """الكتلُ العليا نفسُها بالترتيب، والنصُّ نفسُه إلّا الفراغَ والتعليقاتِ و`;` الأخيرة."""
    parser = _parser()
    comments = re.compile(r"/\*.*?\*/", re.S)

    def squeeze(css: str) -> str:
        return re.sub(r"\s+", "", comments.sub("", css)).replace(";}", "}")

    total_source = total_minified = 0
    for path in css_paths():
        source = path.read_text(encoding="utf-8")
        minified = minify_css(source)
        total_source += len(source.encode())
        total_minified += len(minified.encode())
        assert [h for h, _, _ in parser.top_level_blocks(minified)] == [
            h for h, _, _ in parser.top_level_blocks(source)
        ], path.name
        assert squeeze(minified) == squeeze(source), path.name
    assert total_minified < total_source * 0.65, (total_minified, total_source)

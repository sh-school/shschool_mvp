"""[أداء] البند 7 من خطّة الإصلاح 2026-09-17 — لا أصلٌ ثابتٌ ميّتٌ، ولا Chart.js يحجب الرسم.

كانت `static/brand/pattern.png` و`pattern-tall.png` (896KB) و`pattern.svg`
تُنسخ مع `collectstatic` بلا مرجعٍ واحد يستعملها. وكان `chart.umd.min.js` يُحمَّل
متزامناً في 12 صفحة يليه سكربتٌ يستعمله فوراً — فحُذف الأصلان معاً، وأُجِّل
الاثنان بـ`defer` لا أحدُهما وحده (وإلّا سقط `Chart is not defined`).
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
TEMPLATES = ROOT / "templates"

#: امتدادات الأصول التي نتحقّق من الإحالة إليها — لا الخطوط ولا الأيقونات
#: المولَّدة (لها حرّاسها الخاصّة في test_icon_dictionary.py).
BRAND_ASSET_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg"}
BRAND_EXEMPT = set()  # لا استثناء اليوم — كلّ ملفّ في static/brand يجب أن يُذكر


def _all_source_text() -> str:
    parts = []
    for pattern in ("**/*.html", "**/*.py", "**/*.js", "**/*.css"):
        for path in ROOT.glob(pattern):
            if any(p in path.parts for p in (".git", "node_modules", ".venv", "staticfiles")):
                continue
            try:
                parts.append(path.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
    return "\n".join(parts)


def test_no_dead_files_remain_in_static_brand():
    """كلُّ ملفٍّ في static/brand يجب أن يذكره قالبٌ أو CSS أو Python باسمه."""
    brand_dir = STATIC / "brand"
    files = [
        p.name for p in brand_dir.iterdir() if p.is_file() and p.suffix in BRAND_ASSET_EXTENSIONS
    ]
    assert files, "static/brand فارغٌ أو غير موجود — تحقّق من المسار"

    haystack = _all_source_text()
    dead = [f for f in files if f not in BRAND_EXEMPT and f not in haystack]

    assert not dead, f"ملفّاتٌ في static/brand بلا أيّ مرجع — احذفها أو استعملها: {dead}"


def test_pattern_assets_are_gone():
    """الأصولُ الثلاثة المؤكَّد موتُها (2026-09-17) — لا تعود بغفلة."""
    brand_dir = STATIC / "brand"
    assert not (brand_dir / "pattern.png").exists()
    assert not (brand_dir / "pattern-tall.png").exists()
    assert not (brand_dir / "pattern.svg").exists()


_CHART_SCRIPT = re.compile(
    r"<script src=\"\{% static 'js/vendor/chart\.umd\.min\.js' %\}\"([^>]*)></script>"
    r"\s*<script nonce=\"\{\{ request\.csp_nonce \}\}\"([^>]*)>"
)


def test_every_chart_js_load_and_its_init_script_are_both_deferred():
    """`defer` على السكربت الأوّل بلا الثاني يُسقط `Chart is not defined` فوراً."""
    checked = 0
    for path in TEMPLATES.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        for vendor_attrs, init_attrs in _CHART_SCRIPT.findall(text):
            checked += 1
            assert "defer" in vendor_attrs, f"{path}: سكربت chart.umd.min.js بلا defer"
            assert (
                "defer" in init_attrs
            ), f"{path}: سكربتُ تهيئة الرسم بلا defer — يسبق تحميل المكتبة"

    assert checked == 12, f"كان المتوقَّع 12 صفحةً تحمّل Chart.js، وُجد {checked}"

"""حارسُ غياب شعار الوزارة من القوالب (W-20261011-012، قرار المالك D-386م).

الشعارُ الذي كان في الترويسة وصفحة الدخول وصفحات الخطأ والطباعة وPDF وصفحةِ ما دون اتصال ولوحة الإدارة أُزيل
من الواجهة والقوالب: يبقى اسمُ المدرسة نصّاً. فهذا الحارسُ يقرأ كلَّ القوالب ويفشل عند أيّ مرجعٍ لصورة
الشعار (`brand/emblem*` أو `brand/logoMaroon.png` أو `brand/logowhite.png`) — فلا يعود من مسارٍ جديدٍ ولا من نسخةٍ قديمة.
توقيعُ المطوّر (`azkia-logo.svg` و`sufyan-logo.png` في `components/site_brand.html`) ليس شعارَ الوزارة فيبقى.
"""

import functools
import pathlib
import re

TEMPLATES = pathlib.Path("templates")

#: صورُ شعار الوزارة/المدرسة الرسميّ: ما أُزيل من الواجهة. وملفّاتُها نفسُها حُذفت (يحرسه `test_brand_emblem.py`).
EMBLEM = re.compile(r"brand/(?:emblem(?:-white)?\.svg|logoMaroon\.png|logowhite\.png)")


def _sources():
    return sorted(p for p in TEMPLATES.rglob("*") if p.suffix in {".html", ".js"} and p.is_file())


def test_no_template_references_the_emblem_image():
    offenders = [p.as_posix() for p in _sources() if EMBLEM.search(p.read_text(encoding="utf-8"))]
    assert offenders == [], f"مراجعُ لصورة الشعار في القوالب: {offenders}"


def test_the_shell_shows_the_platform_logo_before_the_school_name_text():
    """W-20261014-009: شعارُ المنصّة (لا الوزارة) في الترويسة، واسمُ المدرسة نصٌّ يجاوره."""
    nav = pathlib.Path("templates/base/base.html").read_text(encoding="utf-8")
    brand = nav.split('class="nb nav-logo"', 1)[1].split("</a>", 1)[0]
    assert '{% school_logo "nav" %}' in brand and "nav-logo-text" in brand
    assert "ministry_logo" not in brand and "ministry-logo" not in brand


def test_the_login_and_error_cards_show_the_platform_logo_and_keep_the_text():
    login = pathlib.Path("templates/auth/login.html").read_text(encoding="utf-8")
    error = pathlib.Path("templates/errors/_error_page.html").read_text(encoding="utf-8")
    assert '{% school_logo "login" %}' in login and "ministry_logo" not in login
    assert "login-school-name" in login and "الرقم الشخصي" in login  # النصُّ كما هو
    assert "eh-school" in error and "ministry_logo" not in error


def test_the_user_menu_hides_the_national_id_line():
    base = pathlib.Path("templates/base/base.html").read_text(encoding="utf-8")
    assert "sd-user-nid" not in base and "mask_id" not in base


def test_the_service_worker_cache_was_bumped_and_no_longer_precaches_the_emblem():
    js = pathlib.Path("templates/pwa/sw_global.js").read_text(encoding="utf-8")
    version = int(re.search(r"schoolos-global-v(\d+)", js).group(1))
    assert version >= 7, "رفعُ الرقم مع تغيّر الأيقونات (v6 → v7، W-20261014-009)"
    assert "emblem" not in js


def test_no_template_prints_the_users_national_id():
    """السطرُ المقنَّع للرقم الشخصيّ حُذف من قائمة المستخدم لكلّ الأدوار (D-387م) — ولا يعود من قالبٍ آخر."""
    offenders = [
        str(path)
        for path in pathlib.Path("templates").rglob("*.html")
        if "request.user.national_id" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], offenders


#: أسماءُ الأصول المحذوفة: ذكرُها في أيّ مصدرٍ يُنتج 500 في الإنتاج (`ManifestStaticFilesStorage` يرمي ValueError لملفٍّ غيرِ موجود)
#: وبيئةُ الاختبار لا تستعمل الـmanifest فلا يكشفه غيرُ هذا الفحص النصّيّ (تنبيه 0101، W-20261011-012).
REMOVED_ASSETS = re.compile(r"logoMaroon|logowhite|emblem(?:-white)?\.svg")
#: ما يُستثنى: الاختباراتُ (تذكرُ الأسماءَ لتحرسها) وهجراتُ الخارطة (نصوصُ ملاحظاتٍ تاريخيّة) والوثائق.
SCAN_SKIP = (
    "tests/",
    "roadmap/migrations/",
    "docs/",
    ".claude/",
    "staticfiles/",
    "node_modules/",
    ".git/",
)


@functools.cache
def _all_sources():
    root = pathlib.Path(".")
    found = []
    for pattern in (
        "templates/**/*",
        "static/**/*.css",
        "static/**/*.js",
        "static/**/*.json",
        "**/*.py",
        "*.json",
    ):
        for path in root.glob(pattern):
            posix = path.as_posix()
            if path.is_file() and not posix.startswith(SCAN_SKIP) and "/migrations/" not in posix:
                found.append(path)
    return tuple(found)


def test_no_source_mentions_a_removed_logo_file():
    offenders = []
    for path in _all_sources():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if REMOVED_ASSETS.search(text):
            offenders.append(path.as_posix())
    assert offenders == [], f"مراجعُ لملفّاتِ شعارٍ محذوفة: {sorted(set(offenders))}"


STATIC_REF = re.compile(
    r"""(?:\{%\s*static\s+['"]|/static/)((?:brand|icons)/[\w./-]+?)(?=['"\s%)?#]|$)"""
)


def test_every_brand_and_icon_reference_points_to_an_existing_file():
    """مرجعٌ إلى `brand/` أو `icons/` لملفٍّ غيرِ موجود = 500 في الإنتاج: يُفحص كلُّ مرجعٍ في القوالب والمانيفست وعمّال الخدمة والأنماط."""
    missing = []
    for path in _all_sources():
        if path.suffix == ".py":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for ref in STATIC_REF.findall(text):
            if not (pathlib.Path("static") / ref).is_file():
                missing.append((path.as_posix(), ref))
    assert missing == [], missing

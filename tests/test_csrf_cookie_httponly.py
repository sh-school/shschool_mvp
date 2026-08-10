"""
tests/test_csrf_cookie_httponly.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[P2-A] عقد CSRF: الرمز من DOM لا من الكوكي.

كان `CSRF_COOKIE_HTTPONLY = False` لأن موضعين في JavaScript يقرآن
`document.cookie`. جرد الشيفرة على commit 54b1d033 أثبت أنهما الوحيدان:
لا قارئ ثالث، ولا مُعدِّل خفيّ عبر XHR/axios، ولا صفحة غير مُعتمَدة ترسل
طلباً مُعدِّلاً يعتمد على رمز من JavaScript.

هذه الاختبارات تحرس العقد بعد إغلاقه — لا تكرّر الجرد بل تمنع ارتداده.
"""

import re
from pathlib import Path

from django.conf import settings

ROOT = Path(__file__).resolve().parents[1]

BASE_JS = ROOT / "static" / "js" / "base.js"
PARENT_DASHBOARD = ROOT / "templates" / "parents" / "dashboard.html"
BASE_TEMPLATE = ROOT / "templates" / "base" / "base.html"

# قراءة كوكي CSRF من JavaScript بأي صيغة: split/match/regex على document.cookie
COOKIE_CSRF_READ = re.compile(r"document\.cookie[^;\n]*csrftoken", re.IGNORECASE)


def _read(path):
    return path.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════
# 1 + 2 — base.js: لا كوكي، ونعم رمز DOM
# ══════════════════════════════════════════════════════════════════


def test_base_js_does_not_read_the_csrf_cookie():
    """[P2-A] الرجوع إلى الكوكي أُزيل — وهو ما كان يمنع HTTPONLY=True."""
    source = _read(BASE_JS)

    assert not COOKIE_CSRF_READ.search(source)
    assert "csrftoken=" not in source


def test_base_js_still_sends_the_csrf_header_from_the_dom():
    """إزالة الكوكي يجب ألّا تُعطّل حماية HTMX."""
    source = _read(BASE_JS)

    assert "htmx:configRequest" in source
    assert "[name=csrfmiddlewaretoken]" in source
    assert "X-CSRFToken" in source


# ══════════════════════════════════════════════════════════════════
# 3 + 4 — لوحة ولي الأمر: اشتراك Push كان المسار الحاجب الوحيد
# ══════════════════════════════════════════════════════════════════


def test_parent_dashboard_reads_the_token_from_the_dom():
    """[P2-A] _getCsrf كانت تقرأ document.cookie — صارت تقرأ الحقل المخفي."""
    source = _read(PARENT_DASHBOARD)

    assert not COOKIE_CSRF_READ.search(source)
    assert "[name=csrfmiddlewaretoken]" in source


def test_parent_push_subscription_still_sends_the_csrf_header():
    """المسار الوظيفي نفسه يبقى محمياً: POST الاشتراك يحمل الترويسة."""
    source = _read(PARENT_DASHBOARD)

    assert "X-CSRFToken" in source
    assert "_getCsrf()" in source


# ══════════════════════════════════════════════════════════════════
# 5 — الإعداد نفسه
# ══════════════════════════════════════════════════════════════════


def test_csrf_cookie_is_not_readable_by_scripts():
    """[P2-A] لا JavaScript يحتاج الكوكي بعد الآن."""
    assert settings.CSRF_COOKIE_HTTPONLY is True


# ══════════════════════════════════════════════════════════════════
# حارس ارتداد عام — يمنع ظهور قارئ ثالث لا عودة القديمَين فقط
# ══════════════════════════════════════════════════════════════════

SCANNED_ROOTS = (ROOT / "static" / "js", ROOT / "templates")
SCANNED_SUFFIXES = {".js", ".html"}

# مكتبات طرف ثالث: لا نملكها ولا يعنينا عقدها الداخلي.
VENDOR_MARKERS = (".min.", "/vendor/", "\\vendor\\")

# استثناءات صريحة عند ظهور إيجابية كاذبة حقيقية — تُضاف بمبرّر مكتوب.
CSRF_COOKIE_ALLOWLIST: set[str] = set()

# اسم الترويسة X-CSRFToken يحوي "csrftoken" عند تصغير الحروف، وهو بالضبط ما
# نريد إبقاءه. نزيله قبل البحث حتى لا يُجرّم الحارس السلوك الصحيح.
CSRF_HEADER_TOKEN = "x-csrftoken"


def _reads_csrf_cookie(source: str) -> bool:
    """
    استدلال واسع عمداً: اجتماع document.cookie مع اسم كوكي CSRF في ملف واحد.

    لا يحاول تحليل الدلالة — `const c = document.cookie; parse(c, 'csrftoken')`
    يفلت من أي regex ضيّق. حارس الارتداد يحتاج اتساعاً لا دقّة نحوية.
    """
    lowered = source.lower().replace(CSRF_HEADER_TOKEN, "")
    return "document.cookie" in lowered and "csrftoken" in lowered


def test_no_production_script_reads_the_csrf_cookie():
    """
    [P2-A] العقد عالمي لأن الإعداد عالمي.

    اختبارا الموضعين أعلاه يمنعان عودة القديمَين. هذا يمنع الثالث: ملف جديد
    يقرأ الكوكي سيمرّ من هناك ويُكسر العقد صامتاً.
    """
    offenders = []

    for root in SCANNED_ROOTS:
        for path in root.rglob("*"):
            if path.suffix not in SCANNED_SUFFIXES:
                continue

            relative = path.relative_to(ROOT).as_posix()

            if any(marker in str(path) for marker in VENDOR_MARKERS):
                continue
            if relative in CSRF_COOKIE_ALLOWLIST:
                continue

            if _reads_csrf_cookie(path.read_text(encoding="utf-8", errors="ignore")):
                offenders.append(relative)

    assert offenders == [], (
        "CSRF_COOKIE_HTTPONLY=True — لا سكربت تطبيقي يقرأ كوكي CSRF. "
        "خُذ الرمز من [name=csrfmiddlewaretoken] في DOM. المخالفون: " + ", ".join(sorted(offenders))
    )


def test_the_regression_guard_actually_catches_an_offender():
    """
    الحارس نفسه يحتاج برهاناً.

    اختبار يمرّ دائماً لا يحرس شيئاً — نُثبت أنه يلتقط النمط الذي وُضع له،
    بما فيه الشكل الذي يفلت من regex ضيّق.
    """
    inline = "var m = document.cookie.match('csrftoken=([^;]*)');"
    indirect = "const c = document.cookie;\nconst t = parse(c, 'csrftoken');"
    legitimate = (
        "headers['X-CSRFToken'] = document.querySelector('[name=csrfmiddlewaretoken]').value;"
    )

    assert _reads_csrf_cookie(inline)
    assert _reads_csrf_cookie(indirect)
    assert not _reads_csrf_cookie(legitimate)


# ══════════════════════════════════════════════════════════════════
# حارس الافتراض الذي يقوم عليه كل ما سبق
# ══════════════════════════════════════════════════════════════════


def test_base_template_exposes_the_token_to_every_authenticated_page():
    """
    القالب الأساس يضع {% csrf_token %} تحت شرط المصادقة وحده.

    لو أُضيف شرط دور حول نموذج الخروج، لاختفى الحقل عن بعض الصفحات وانكسر
    كل مسار CSRF في JavaScript بصمت — لأن الرجوع إلى الكوكي لم يعد موجوداً.
    """
    source = _read(BASE_TEMPLATE)

    assert "{% csrf_token %}" in source

    lines = source.splitlines()
    csrf_line = next(i for i, line in enumerate(lines, 1) if "{% csrf_token %}" in line)

    depth = 0
    enclosing = []
    for line in lines[:csrf_line]:
        for tag in re.findall(r"\{%\s*(if|endif|with|endwith)\b", line):
            if tag in ("if", "with"):
                depth += 1
                enclosing.append(line.strip())
            elif enclosing:
                enclosing.pop()
                depth -= 1

    assert depth == 2, f"expected exactly two enclosing blocks, found {depth}"
    assert any("user.is_authenticated" in block for block in enclosing)
    assert not any("role ==" in block or "is_admin_role" in block for block in enclosing)

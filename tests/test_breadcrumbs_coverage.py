"""[UX] فتات الخبز في كل صفحة — لا صفحةَ بلا مسارٍ للعودة.

الصفحة بلا فتات خبز تترك المستخدم بلا موضعٍ معلوم ولا طريقٍ للأعلى — لا شيء
يتعطّل، فلا يظهر الغياب في اختبارٍ ولا في سجلّ. وقد غابت عن صفحات الزيارات
الصفّية وصندوق رسائل المطوّر ولوحتَي السلوك والنقل حتى لاحظها المستخدم.

والفحص يشمل قوالب التطبيقات (`<app>/templates/`) لا `templates/` وحدها: تلك
صفحاتٌ كاملة أيضاً، وقصرُ الفحص على الجذر أخفى تسعاً منها.
"""

import pathlib
import re

import pytest

_EXTENDS = re.compile(r'{%\s*extends\s+"([^"]+)"')

#: القوالب التي يرث منها كل صفحةٍ ذات واجهة.
_PAGE_BASES = {"base.html", "base/base.html"}


def _page_templates():
    roots = [pathlib.Path("templates")]
    roots += [p for p in pathlib.Path(".").glob("*/templates") if p.is_dir()]

    for root in roots:
        for f in sorted(root.rglob("*.html")):
            text = f.read_text(encoding="utf-8", errors="ignore")
            parent = _EXTENDS.search(text)
            if not parent or parent.group(1) not in _PAGE_BASES:
                continue
            if not text.strip().endswith("%}") or "{% block" in text:
                yield f, text


def test_every_page_declares_breadcrumbs():
    """`templates/base.html` مستثنى: سطرٌ واحد يُعيد التسمية، لا صفحة."""
    missing = [
        f.as_posix()
        for f, text in _page_templates()
        if "{% block breadcrumbs %}" not in text and f.as_posix() != "templates/base.html"
    ]

    assert not missing, f"صفحات بلا فتات خبز: {missing}"


@pytest.mark.django_db
def test_the_breadcrumb_trail_reaches_the_dashboard(client, principal_user):
    """يُقاس على صفحةٍ مُصيَّرة — وجودُ الوسم في القالب لا يعني ظهوره."""
    from django.urls import reverse

    client.force_login(principal_user)

    html = client.get(reverse("observation_list")).content.decode()

    assert 'class="breadcrumbs"' in html
    assert 'href="/dashboard/"' in html

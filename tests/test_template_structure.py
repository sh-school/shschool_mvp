"""[TEMPLATES] بنيةُ القوالب — كتلةٌ متداخلةٌ تُرسَم مرّتين، وقالبٌ يتيمٌ يُحرَّر بلا أثر.

هذان عطبان صامتان: لا استثناءَ ولا سطرَ في السجلّ ولا صفحةَ تُخفق. ولا
يُمسكان إلّا بفحص.
"""

import pathlib
import re

ROOT_TEMPLATE = pathlib.Path("templates/base/base.html")

BLOCK_RE = re.compile(r"\{%\s*(block\s+(\w+)|endblock)\b")
REF_IN_PY = re.compile(r"""["']([\w./-]+\.(?:html|txt))["']""")
REF_IN_TPL = re.compile(r"""\{%\s*(?:extends|include)\s+["']([\w./-]+\.(?:html|txt))["']""")

#: قوالبُ لا يشير إليها كودٌ لأنّ إطارَ العمل يجدها بالاصطلاح، أو لسببٍ مكتوب.
ALLOWED_ORPHANS = {
    # جانغو يجدهما بـhandler404/handler500 لا باسمٍ مكتوب.
    "404.html",
    "500.html",
}


#: مجلّداتٌ لا تُمسح — نواتجُ بناءٍ وحُزَمٌ خارجيّة.
SKIP = {".local", "staticfiles", "node_modules", ".venv", ".git"}


def _roots():
    yield pathlib.Path("templates")
    yield from sorted(pathlib.Path(".").glob("*/templates"))


def _templates():
    out = []
    for root in _roots():
        for suffix in ("*.html", "*.txt"):
            out += [str(p).replace("\\", "/") for p in root.rglob(suffix)]
    return out


def _python_files():
    for path in pathlib.Path(".").rglob("*.py"):
        if SKIP & set(path.parts):
            continue
        yield path


def _template_name(path: str) -> str:
    if path.startswith("templates/"):
        return path[len("templates/") :]
    return path[path.index("/templates/") + len("/templates/") :]


def test_no_block_is_nested_inside_another_the_parent_also_renders():
    """كتلةٌ داخل كتلةٍ باسمٍ يعرّفه القالبُ الأب تُرسَم مرّتين.

    وقع ذلك في `dashboard/main.html`: كانت `{% block extra_js %}` داخل
    `{% block content %}`، فظهر السكربتُ مرّتين في الصفحة الواحدة وأخفق
    الثاني بـ`Identifier 'OPTS' has already been declared` — فلم يُرسَم
    أحدُ الرسمين، بلا أيّ أثرٍ في السجلّ.

    والمتداخلةُ باسمٍ لا يعرّفه الأبُ سليمةٌ: قالبٌ وسيطٌ يفتح خانةً لأبنائه.
    """
    parent_blocks = set(
        re.findall(r"\{%\s*block\s+(\w+)", ROOT_TEMPLATE.read_text(encoding="utf-8"))
    )
    offenders = []
    for path in _templates():
        if not path.endswith(".html"):
            continue
        text = open(path, encoding="utf-8").read()
        if "{% extends" not in text:
            continue
        depth = 0
        for match in BLOCK_RE.finditer(text):
            if match.group(1).startswith("block"):
                if depth > 0 and match.group(2) in parent_blocks:
                    offenders.append(f"{path}: {{% block {match.group(2)} %}} داخل كتلةٍ أخرى")
                depth += 1
            else:
                depth -= 1
    assert not offenders, "كتلةٌ متداخلةٌ تُرسَم مرّتين:\n  " + "\n  ".join(offenders)


def test_no_template_is_orphaned():
    """قالبٌ لا يشير إليه كودٌ ولا قالب — يُحرَّر ويُراجَع ولا يُعرض أبداً.

    كخمسةِ الـdashboard التي حُذفت: حُرِّرت حتّى 2026-08-27 ولم تُعرض قطّ.
    """
    names = {_template_name(p) for p in _templates()}
    referenced = set()
    for path in _python_files():
        try:
            referenced |= set(REF_IN_PY.findall(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):
            continue
    for path in _templates():
        text = open(path, encoding="utf-8").read()
        referenced |= set(REF_IN_TPL.findall(text))
        referenced |= set(REF_IN_PY.findall(text))
    orphans = sorted(names - referenced - ALLOWED_ORPHANS)
    assert not orphans, "قوالبُ لا يشير إليها شيء — تُوصَل أو تُحذف:\n  " + "\n  ".join(orphans)

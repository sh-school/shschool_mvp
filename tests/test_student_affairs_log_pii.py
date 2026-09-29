"""[W-030] لا اسمَ ولا رقمَ هويّةٍ في نداءات التسجيل داخل `student_affairs`.

حارسُ غيابٍ من المصدر بالشجرة النحوية (كما `test_log_data_minimization`):
كانت `create_student` تكتب الاسمَ ورقمَ الهويّة كاملاً في السجلّ، وخمسةُ نداءاتٍ
أخرى تكتب اسمَ الطالب أو المراجِع. المسموح: `user.pk` أو `transfer.pk`.
"""

import ast
import pathlib

import pytest

import student_affairs

PACKAGE = pathlib.Path(student_affairs.__file__).parent

FORBIDDEN_ATTRIBUTES = {"full_name", "national_id", "phone", "email", "parent_name"}
FORBIDDEN_NAMES = {"national_id", "full_name", "student_name", "phone", "email"}


def _log_calls(tree):
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in {"logger", "logging"}
        ):
            yield node


def _leaked(call):
    leaked = set()
    for node in ast.walk(call):
        if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRIBUTES:
            leaked.add(node.attr)
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            leaked.add(node.id)
    return leaked


def _sources():
    return [
        p
        for p in sorted(PACKAGE.rglob("*.py"))
        if "migrations" not in p.parts and p.name != "__init__.py"
    ]


@pytest.mark.parametrize("path", _sources(), ids=lambda p: p.name)
def test_no_name_or_national_id_in_student_affairs_logs(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders = [(c.lineno, sorted(_leaked(c))) for c in _log_calls(tree) if _leaked(c)]
    assert offenders == [], f"{path.name}: نداء تسجيل يحمل اسماً أو هويّةً — استعمل pk: {offenders}"


def test_the_scanner_sees_a_planted_leak():
    planted = ast.parse(
        'logger.info("x %s", user.full_name)\n'
        'logger.info("nid=%s", national_id)\n'
        'logger.info("ok %s", user.pk)\n'
    )
    assert [sorted(_leaked(c)) for c in _log_calls(planted)] == [
        ["full_name"],
        ["national_id"],
        [],
    ]

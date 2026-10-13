"""لا يخرج نصُّ استثناءٍ إلى العميل من واجهات الرصد والمحو (CodeQL py/stack-trace-exposure #121–#126، W-20261003-026).

كانت الواجهاتُ تُعيد `str(exc)` من استثناءاتٍ برسائلَ ثابتةٍ من كودنا؛ فصارت تُعيد رسالةً **من جدولٍ بالرمز** (`exc.code`)، والرمزُ المجهولُ
رسالةٌ عامّةٌ — فلا نصَّ استثناءٍ يصل المتصفّحَ مهما تغيّرت رسائلُ الطبقات تحتها. قرارُ المالك (#772): الإغلاقُ بالكود لا بالاستبعاد.
"""

import ast
from pathlib import Path

import pytest
from rest_framework.test import APIClient

from api.views_erasure import ERASURE_FAILURES
from governance.erasure_service import ErasureFailedError, ErasureStateError
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import _staff

pytestmark = pytest.mark.django_db

CANARY = "CANARY-نصُّ-الاستثناء-الخامّ-لا-يخرج"
ROOT = Path(__file__).resolve().parent.parent
VIEW_FILES = ("api/views_erasure.py",)


def _raise(exc):
    def boom(*args, **kwargs):
        raise exc

    return boom


@pytest.mark.parametrize("known", ["erasure_wrong_tenant", "erasure_incomplete", "erasure_error"])
def test_a_known_erasure_failure_returns_its_table_message_and_code(
    school, kid, monkeypatch, known
):
    from governance.erasure_service import ErasureService

    admin = _staff(school, "principal", "مدير المحو", "29000006101")
    client = APIClient()
    client.force_login(admin)
    request_id = client.post(
        "/api/v1/erasure/request/",
        format="json",
        data={"student_id": str(kid.id), "reason": "طلبُ محوٍ لاختبار التسرّب"},
    ).data["id"]
    monkeypatch.setattr(
        ErasureService,
        "approve_and_execute",
        staticmethod(_raise(ErasureFailedError(CANARY, known))),
    )
    response = client.post(
        f"/api/v1/erasure/requests/{request_id}/approve/", format="json", data={}
    )
    assert response.status_code == 409
    assert CANARY not in str(response.data)
    code, detail = ERASURE_FAILURES[known]
    assert response.data["code"] == code
    assert response.data["detail"].startswith(detail)


def test_an_unmapped_erasure_code_is_the_generic_one_and_never_echoed(school, kid, monkeypatch):
    from governance.erasure_service import ErasureService

    admin = _staff(school, "principal", "مدير المحو", "29000006102")
    client = APIClient()
    client.force_login(admin)
    request_id = client.post(
        "/api/v1/erasure/request/",
        format="json",
        data={"student_id": str(kid.id), "reason": "طلبُ محوٍ لاختبار التسرّب"},
    ).data["id"]
    monkeypatch.setattr(
        ErasureService,
        "approve_and_execute",
        staticmethod(_raise(ErasureFailedError(CANARY, "<script>x</script>"))),
    )
    response = client.post(
        f"/api/v1/erasure/requests/{request_id}/approve/", format="json", data={}
    )
    assert response.status_code == 409
    assert response.data["code"] == "erasure_error"
    assert CANARY not in str(response.data) and "<script>" not in str(response.data)


def test_a_state_error_returns_the_fixed_sentence_not_the_status_text(school, kid, monkeypatch):
    from governance.erasure_service import ErasureService

    admin = _staff(school, "principal", "مدير المحو", "29000006103")
    client = APIClient()
    client.force_login(admin)
    request_id = client.post(
        "/api/v1/erasure/request/",
        format="json",
        data={"student_id": str(kid.id), "reason": "طلبُ محوٍ لاختبار التسرّب"},
    ).data["id"]
    monkeypatch.setattr(
        ErasureService, "approve_and_execute", staticmethod(_raise(ErasureStateError(CANARY)))
    )
    response = client.post(
        f"/api/v1/erasure/requests/{request_id}/approve/", format="json", data={}
    )
    assert response.status_code == 400
    assert CANARY not in str(response.data)


# ── حارسٌ ساكن: لا `str(exc)` في ردٍّ من هذين الملفّين ─────────────────────────────


def _returns_exception_text(source: str) -> list[int]:
    """أسطرُ نداءاتٍ `Response(...)`/`HttpResponse(...)` تحمل `str(<متغيّرُ استثناء>)` أو f-string به."""
    tree = ast.parse(source)
    lines = []
    for handler in (n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)):
        if not handler.name:
            continue
        for call in (n for n in ast.walk(handler) if isinstance(n, ast.Call)):
            func = call.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name not in {"Response", "HttpResponse", "JsonResponse"}:
                continue
            for node in ast.walk(call):
                if isinstance(node, ast.Name) and node.id == handler.name:
                    lines.append(node.lineno)
    return lines


@pytest.mark.parametrize("rel", VIEW_FILES)
def test_no_response_in_an_except_block_carries_the_exception_variable(rel):
    leaks = _returns_exception_text((ROOT / rel).read_text(encoding="utf-8"))
    assert not leaks, f"{rel}: ردٌّ يحمل متغيّرَ استثناءٍ في الأسطر {leaks} — استعمل جدولَ رسائلَ بالرمز"


def test_the_detector_catches_a_leak():
    assert _returns_exception_text(
        "def v():\n    try:\n        pass\n    except Exception as exc:\n        return Response({'detail': str(exc)})\n"
    ) == [5]
    assert not _returns_exception_text(
        "def v():\n    try:\n        pass\n    except Exception as exc:\n        return Response({'detail': TABLE.get(exc.code)})\n".replace(
            "exc.code", "'k'"
        )
    )

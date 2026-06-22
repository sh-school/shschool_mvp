"""tests/test_request_utils.py — get_client_ip: IP الحقيقي خلف وكيل عكسي."""

from core.request_utils import get_client_ip


class _Req:
    def __init__(self, xff=None, remote=None):
        self.META = {}
        if xff is not None:
            self.META["HTTP_X_FORWARDED_FOR"] = xff
        if remote is not None:
            self.META["REMOTE_ADDR"] = remote


def test_xff_takes_rightmost_trusted_entry():
    # عميل يزوّر أول إدخال؛ الوكيل يُلحق الحقيقي آخراً → نأخذ الأخير
    assert get_client_ip(_Req(xff="1.1.1.1, 203.0.113.9")) == "203.0.113.9"


def test_xff_single_entry():
    assert get_client_ip(_Req(xff="203.0.113.9")) == "203.0.113.9"


def test_fallback_to_remote_addr():
    assert get_client_ip(_Req(remote="10.0.0.5")) == "10.0.0.5"


def test_empty_returns_blank():
    assert get_client_ip(_Req()) == ""


def test_xff_with_spaces_and_blanks():
    assert get_client_ip(_Req(xff="  1.1.1.1 ,  203.0.113.9  ,")) == "203.0.113.9"

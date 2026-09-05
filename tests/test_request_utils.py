"""tests/test_request_utils.py — get_client_ip: عنوانُ العميل خلف وكيلٍ عكسيّ.

كان هذا الملفّ يُثبّت الافتراضَ القديم: «الوكيلُ يُلحق العميلَ الحقيقيَّ آخراً».
وأثبت الإنتاجُ في 2026-09-05 عكسَه — Railway يُلحق العميلَ ثمّ قفزةَ حافّته —
فصار العميلُ ما قبل `TRUSTED_PROXY_HOPS` من اليمين، وبلا وكيلٍ موثوق تُهمَل
الترويسةُ كلُّها لأنّها من العميل. (الشكلُ الحقيقيّ في test_client_ip_behind_railway.)
"""

from core.request_utils import get_client_ip


class _Req:
    def __init__(self, xff=None, remote=None):
        self.META = {}
        if xff is not None:
            self.META["HTTP_X_FORWARDED_FOR"] = xff
        if remote is not None:
            self.META["REMOTE_ADDR"] = remote


def test_behind_one_hop_the_client_is_before_the_edge(settings):
    settings.TRUSTED_PROXY_HOPS = 1
    # عميلٌ يزوّر أوّلَ القائمة؛ الحافّةُ تُلحق العميلَ الحقيقيّ ثمّ نفسَها
    assert get_client_ip(_Req(xff="1.1.1.1, 203.0.113.9, 152.233.12.245")) == "203.0.113.9"


def test_behind_one_hop_a_single_entry_is_taken_as_is(settings):
    """ترويسةٌ أقصرُ ممّا تُلحقه الحافّة — يُؤخذ ما هناك لا فراغ."""
    settings.TRUSTED_PROXY_HOPS = 1
    assert get_client_ip(_Req(xff="203.0.113.9", remote="100.64.0.8")) == "203.0.113.9"


def test_without_a_trusted_hop_the_header_is_ignored(settings):
    settings.TRUSTED_PROXY_HOPS = 0
    assert get_client_ip(_Req(xff="1.1.1.1, 203.0.113.9", remote="10.0.0.5")) == "10.0.0.5"


def test_fallback_to_remote_addr(settings):
    settings.TRUSTED_PROXY_HOPS = 1
    assert get_client_ip(_Req(remote="10.0.0.5")) == "10.0.0.5"


def test_empty_returns_blank(settings):
    settings.TRUSTED_PROXY_HOPS = 1
    assert get_client_ip(_Req()) == ""


def test_spaces_and_blank_entries_are_tolerated(settings):
    settings.TRUSTED_PROXY_HOPS = 1
    assert get_client_ip(_Req(xff="  1.1.1.1 ,  203.0.113.9  , 152.233.12.245 ,")) == "203.0.113.9"


def test_none_request_is_blank():
    assert get_client_ip(None) == ""

"""عنوانُ العميل خلف حافّة Railway — العميلُ قبل الأخير، لا الأخير.

سجّل الحارسُ `internal_only` في 2026-09-05 ما رآه فعلاً:
    XFF='176.202.42.52, 152.233.12.245'  REMOTE_ADDR='100.64.0.8'
الأوّلُ عميلٌ حقيقيّ في قطر، والثاني قفزةُ الحافّة، والثالثُ الوكيلُ الداخليّ.
وكان المشتقُّ يأخذ الأخيرَ فيرى الحافّةَ عميلاً: قائمةُ السماح لا تطابق أحداً،
وسجلّاتُ التدقيق تكتب عنواناً واحداً للجميع.
"""

import pytest

from core.request_utils import get_client_ip


def _req(rf, xff=None, remote="100.64.0.8"):
    request = rf.get("/")
    request.META["REMOTE_ADDR"] = remote
    if xff is not None:
        request.META["HTTP_X_FORWARDED_FOR"] = xff
    return request


@pytest.mark.parametrize("hops", [1])
def test_behind_one_trusted_hop_the_client_is_second_to_last(rf, settings, hops):
    settings.TRUSTED_PROXY_HOPS = hops
    request = _req(rf, "176.202.42.52, 152.233.12.245")
    assert get_client_ip(request) == "176.202.42.52"


def test_a_spoofed_prefix_does_not_move_the_client(rf, settings):
    """المهاجم يضع ما يشاء في أوّل القائمة — الحافّةُ تُلحق العميلَ الحقيقيّ بعده."""
    settings.TRUSTED_PROXY_HOPS = 1
    request = _req(rf, "127.0.0.1, 176.202.42.52, 152.233.12.245")
    assert get_client_ip(request) == "176.202.42.52"


def test_without_a_proxy_the_socket_peer_is_the_client(rf, settings):
    settings.TRUSTED_PROXY_HOPS = 0
    assert get_client_ip(_req(rf, None, remote="127.0.0.1")) == "127.0.0.1"


def test_without_a_proxy_xff_is_untrusted_and_ignored(rf, settings):
    """بلا وكيلٍ موثوق، الترويسةُ كلُّها من العميل — لا يُصدَّق منها شيء."""
    settings.TRUSTED_PROXY_HOPS = 0
    assert get_client_ip(_req(rf, "127.0.0.1", remote="203.0.113.9")) == "203.0.113.9"


def test_fewer_entries_than_hops_falls_back_to_the_last_entry(rf, settings):
    """طلبٌ وصل بترويسةٍ أقصرَ مما تُلحقه الحافّة — يُؤخذ ما هناك لا فراغ."""
    settings.TRUSTED_PROXY_HOPS = 2
    assert get_client_ip(_req(rf, "176.202.42.52")) == "176.202.42.52"

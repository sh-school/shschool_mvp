"""مهلةُ قراءة طبقة القنوات أكبرُ من مهلة القراءة الحاجبة (سقوط WebSocket بـ«Timeout reading from redis»).

redis-py ≥ 8 جعل `socket_timeout` الافتراضيَّ 5s بعد أن كان بلا مهلة، وchannels_redis
ينتظر رسالةً بـ`BZPOPMIN` مدّتُه `brpop_timeout` = 5s على الاتصال نفسه؛ فإن تساوتا
سقط كلُّ مستهلكٍ خامل بـ`TimeoutError` بعد ~5s.
"""

from channels_redis.core import RedisChannelLayer
from channels_redis.utils import create_pool, decode_hosts
from django.conf import settings


def _hosts():
    return decode_hosts(settings.CHANNEL_LAYERS["default"]["CONFIG"]["hosts"])


def test_socket_timeout_exceeds_blocking_pop_timeout():
    for host in _hosts():
        assert host["socket_timeout"] > RedisChannelLayer.brpop_timeout


def test_pool_is_built_with_the_explicit_timeout():
    for host in _hosts():
        kwargs = create_pool(host).connection_kwargs
        assert kwargs["socket_timeout"] == host["socket_timeout"]
        assert kwargs["socket_timeout"] > RedisChannelLayer.brpop_timeout

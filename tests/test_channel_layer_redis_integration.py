"""تكاملٌ حقيقيّ: مستهلكٌ خاملٌ أكثرَ من 5s على redis فعليّ لا يسقط بـ«Timeout reading from redis».

`test_channel_layer_socket_timeout.py` يفحص الإعدادَ نصّاً؛ وهذا يفحص السلوكَ: يبني
`RedisChannelLayer` بإعدادات `settings.CHANNEL_LAYERS` الفعليّة وينتظر `receive()` على
قناةٍ خاملةٍ 7s (فوق `brpop_timeout` = 5s) ثمّ تصلها رسالة. المرجعُ: redis-py 8 جعل
`socket_timeout` الافتراضيَّ 5s فتساوى مع `BZPOPMIN` في channels_redis وسقط كلُّ مستهلكٍ
خامل. الغرضُ أن تُكشف عودتُه عند أيّ ترقيةٍ لـredis-py أو channels-redis أو channels
قبل الإنتاج، لا بعده.

يحتاج redis حقيقيّاً (خدمةُ `redis` في وظائف quality-gate). محلّياً بلا redis يُتخطّى بوضوح؛
وفي CI (`CI=true`) غيابُه **فشلٌ** لا تخطٍّ — كي لا يُعطَّل الحارسُ صامتاً.
"""

import asyncio
import os
import socket
from urllib.parse import urlparse

import pytest
from channels_redis.core import RedisChannelLayer
from channels_redis.utils import decode_hosts
from django.conf import settings

pytestmark = [pytest.mark.integration, pytest.mark.slow]

IDLE_SECONDS = 7  # فوق brpop_timeout (5) وتحت socket_timeout (15)


def _config():
    return settings.CHANNEL_LAYERS["default"]["CONFIG"]


def _redis_reachable() -> bool:
    for host in decode_hosts(_config()["hosts"]):
        url = urlparse(host["address"]) if "address" in host else None
        if url is None:
            return True  # عنوانُ مقبسٍ/sentinel لا نفحصه هنا
        try:
            with socket.create_connection((url.hostname or "localhost", url.port or 6379), timeout=1):
                pass
        except OSError:
            return False
    return True


@pytest.fixture(autouse=True)
def _require_redis():
    if settings.CHANNEL_LAYERS["default"]["BACKEND"] != "channels_redis.core.RedisChannelLayer":
        pytest.skip("طبقةُ القنوات ليست redis في هذه الإعدادات")
    if not _redis_reachable():
        if os.environ.get("CI"):
            pytest.fail("redis غير متاحٍ في CI — خدمةُ redis مطلوبةٌ لهذا الحارس")
        pytest.skip("لا redis محلّيّاً — شغّل redis أو اضبط REDIS_URL لتشغيل هذا الاختبار")


@pytest.mark.asyncio
async def test_idle_receive_survives_longer_than_blocking_pop_timeout():
    layer = RedisChannelLayer(**_config())
    channel = await layer.new_channel()
    message = {"type": "idle.wakeup", "n": 1}

    async def _send_late():
        await asyncio.sleep(IDLE_SECONDS)
        await layer.send(channel, message)

    sender = asyncio.create_task(_send_late())
    try:
        # المهلةُ الخارجيّة تفصل «لم تصل» عن «سقط الاتّصال بـTimeoutError من redis-py»
        received = await asyncio.wait_for(layer.receive(channel), timeout=IDLE_SECONDS + 15)
    finally:
        sender.cancel()
        await layer.flush()
        await layer.close_pools()

    assert received == message

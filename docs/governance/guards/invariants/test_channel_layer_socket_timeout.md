# حارسُ الثوابت: طبقةُ القنوات (redis)

> صفٌّ من جدول «ج. حرّاسُ الثوابت» — مقطعٌ من `docs/governance/regression_guards.md` (الفهرس)؛ النصُّ منقولٌ حرفيّاً (W-20261020-018).

| المجال | الحرّاس | ما يفرضونه |
|---|---|---|
| **طبقةُ القنوات (redis)** | `test_channel_layer_socket_timeout`، `test_channel_layer_redis_integration` | `socket_timeout` أكبرُ من `brpop_timeout` (5s)؛ ومستهلكٌ خاملٌ 7s على redis **حقيقيّ** لا يسقط بـ«Timeout reading from redis». الثاني يعمل في `test-coverage` (خدمةُ `redis` فيها)، ويُتخطّى محلّياً بلا redis ويفشل في CI إن غاب. مرجعُ الفشل: redis-py 8 (`socket_timeout`=5s افتراضاً). تُرقّى `redis` و`channels-redis` و`channels` معاً (مجموعةُ dependabot) |

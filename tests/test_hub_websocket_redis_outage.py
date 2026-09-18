"""دفعُ الإشعار عبر WebSocket لا يُسقط `hub.dispatch()` حين يسقط Redis.

`_push_websocket` fail-safe بالتصميم — توثيقه يقول ذلك صراحةً — لكنّ
`except (ImportError, OSError, RuntimeError, AttributeError)` كان يفلت منه
`redis.exceptions.ConnectionError` الحقيقيّ الذي ترفعه `channels_redis` حين
يسقط خادم Redis أثناء `group_send`، فينهار الإشعار كلّه (لا الجزء اللاسلكيّ
وحده) على قاعدةٍ لا تخصّ WebSocket إطلاقاً.
"""

from unittest.mock import MagicMock, patch

import pytest
import redis

from notifications.hub import _push_websocket
from notifications.models import InAppNotification


@pytest.fixture
def in_app_notif(db, school, teacher_user):
    return InAppNotification.objects.create(
        user=teacher_user,
        school=school,
        title="إشعار تجريبي",
        body="نص الإشعار",
        event_type="general",
        priority="medium",
    )


def test_a_real_redis_connection_error_is_swallowed_not_raised(teacher_user, in_app_notif):
    broken_layer = MagicMock()
    broken_layer.group_send.side_effect = redis.exceptions.ConnectionError("redis down")

    # `_push_websocket` يستورد `get_channel_layer` محلّياً عند النداء، فالتصحيح
    # يستهدف مصدرها لا `notifications.hub` (لا يوجد اسمٌ بهذا المستوى هناك).
    with patch("channels.layers.get_channel_layer", return_value=broken_layer):
        _push_websocket(teacher_user, in_app_notif)  # لا يجوز أن يرفع


def test_a_real_redis_timeout_error_is_swallowed_not_raised(teacher_user, in_app_notif):
    broken_layer = MagicMock()
    broken_layer.group_send.side_effect = redis.exceptions.TimeoutError("redis timeout")

    with patch("channels.layers.get_channel_layer", return_value=broken_layer):
        _push_websocket(teacher_user, in_app_notif)  # لا يجوز أن يرفع

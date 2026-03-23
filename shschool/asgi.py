"""
ASGI config for SchoolOS — v5.1
يدعم HTTP (Django) + WebSocket (Django Channels)
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shschool.settings.production")

# يجب استدعاء get_asgi_application() قبل أي import يعتمد على Django setup
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from notifications.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        # ── HTTP: Django ASGI مُعالِج الطلبات العادية ─────────────────
        "http": django_asgi_app,
        # ── WebSocket: محمي بـ AllowedHosts + Auth ─────────────────────
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(
                URLRouter(websocket_urlpatterns)
            )
        ),
    }
)

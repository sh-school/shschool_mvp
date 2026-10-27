"""W-20261025-022: منافذ docker-compose.yml للتطوير مربوطة بـ127.0.0.1 فلا تُكشف على الشبكة (013 ثم 022)."""

from pathlib import Path

import yaml

COMPOSE = Path(__file__).resolve().parent.parent / "docker-compose.yml"


def test_published_ports_bind_loopback_only():
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    published = [(name, str(p)) for name, svc in services.items() for p in svc.get("ports", [])]
    assert published, "لا منافذ منشورة؟ تغيّر الملف"
    exposed = [(name, p) for name, p in published if not p.startswith("127.0.0.1:")]
    assert not exposed, f"منافذ مكشوفة على كل الواجهات: {exposed}"

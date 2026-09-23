"""فضاءُ الجلسة في redis المشترك — طابورٌ وبادئةُ قنواتٍ باسم قاعدة الشجرة.

كانت مهمّةُ خادم الجلسة تُرسَل إلى الطابور المشترك `celery`، فيلتقطها عاملُ الحزمة
الأصليّة ويبحث عن صفّها في قاعدته هو («صفّ التصدير غير موجود»). يُحرَس هنا أنّ
`SESSION_NAMESPACE` يعزل الطابورَ والقنواتِ، وأنّ فراغَه يُبقي السلوكَ المشترك القديم.
"""

import importlib.util
from pathlib import Path

import pytest

DEV = Path(__file__).resolve().parent.parent / "shschool" / "settings" / "development.py"


def _load(monkeypatch, **env):
    for key in ("SESSION_NAMESPACE", "REDIS_URL"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    spec = importlib.util.spec_from_file_location("shschool.settings._dev_probe", DEV)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_session_gets_its_own_queue_and_channel_prefix(monkeypatch):
    dev = _load(monkeypatch, SESSION_NAMESPACE="ss_tree", REDIS_URL="redis://h:6380/0")

    assert dev.CELERY_TASK_DEFAULT_QUEUE == "ss_tree"
    assert dev.CHANNEL_LAYERS["default"]["CONFIG"]["prefix"] == "asgi:ss_tree"


def test_without_a_namespace_the_shared_queue_is_kept(monkeypatch):
    dev = _load(monkeypatch, REDIS_URL="redis://h:6380/0")

    assert not hasattr(dev, "CELERY_TASK_DEFAULT_QUEUE")
    assert "prefix" not in dev.CHANNEL_LAYERS["default"]["CONFIG"]


def test_the_base_channel_layer_is_not_mutated(monkeypatch):
    from shschool.settings import base

    _load(monkeypatch, SESSION_NAMESPACE="ss_other", REDIS_URL="redis://h:6380/0")

    assert "prefix" not in base.CHANNEL_LAYERS["default"]["CONFIG"]


@pytest.mark.parametrize("service", ["web", "worker"])
def test_the_session_compose_passes_the_namespace_and_starts_the_worker(service):
    import yaml

    compose = yaml.safe_load(
        (Path(__file__).resolve().parent.parent / "docker-compose.session.yml").read_text(
            encoding="utf-8"
        )
    )
    svc = compose["services"][service]
    assert svc["environment"]["SESSION_NAMESPACE"] == "${SESSION_DB:-}"
    assert "profiles" not in svc  # العاملُ يقلع مع الخادم — بلا طابورٍ مشتركٍ يخدمه غيرُه

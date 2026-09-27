"""سجلُّ أنواع التصدير: `kind` ← بنّاءٌ نقيٌّ — تُسجّله التطبيقاتُ من `AppConfig.ready()`.

`build(school, user, params) -> ExportResult` دالّةٌ **بلا `request`**: تعمل في العامل وفي الطلب (النمطُ المتزامن)
بالشكل نفسِه، ومن يحتاج سياقَ الطلب يبنيه من `params` (`QueryDict` بمعاملاتِ الرابط كما وصلت).

الافتراضُ الآمنُ (شرطُ مالك Backend، 2026-09-26): **كلُّ نوعٍ خلفيّ (`job`) ما لم يُثبَت أنّه سريعٌ بقياس**. فالتسجيلُ
`mode="direct"` (متزامنٌ بإشعار الواجهة) يفشل ما لم يُذكَر `p95_ms` مقيساً دافئاً (≥ 20 نداءً على بياناتٍ أقربَ للإنتاج،
`measured_on` بمصدره وتاريخه) وما لم يكن ≤ `DIRECT_P95_CEILING_MS`؛ وتُرقّى الأنواعُ الأبطأ آليّاً إلى `job` بتعديل القياس.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

#: سقفُ حجم الناتج الافتراضيّ (بايت) — عرضُ `bytes(job.content)` يحمّله كلَّه في الذاكرة.
DEFAULT_MAX_BYTES = 25 * 1024 * 1024

#: أبطأُ p95 مقيسٍ يُقبل متزامناً؛ فوقه مهمّةٌ خلفيّةٌ إلزاميّة.
DIRECT_P95_CEILING_MS = 1000

Mode = Literal["job", "direct"]


@dataclass(frozen=True)
class ExportResult:
    content: bytes
    content_type: str
    filename: str
    #: عددُ الأشخاص/السطور في الملفّ ورايةُ «فيه رقمٌ شخصيٌّ كامل» — للأثر في سجلّ التدقيق (`runner.run_job`)؛ `None` = لا صفوف.
    rows: int | None = None
    full_national_id: bool = False
    #: معرّفُ موضوع الملفّ (مفتاحُ الفصل مثلاً) يُكتب في `object_id` بسطر التدقيق — لا اسمَ ولا رقماً شخصيّاً.
    object_id: str = ""


@dataclass(frozen=True)
class ExportKind:
    kind: str
    #: `(school, user, params: QueryDict) -> ExportResult`
    build: Callable[[Any, Any, Any], ExportResult]
    #: مفتاحُ القدرة (`core/capabilities.py`) — يُفحص عند الطلب ومرّةً ثانيةً في العامل.
    capability: str
    max_bytes: int = DEFAULT_MAX_BYTES
    mode: Mode = "job"
    p95_ms: int | None = None
    measured_on: str = ""


_REGISTRY: dict[str, ExportKind] = {}


def register(
    kind: str,
    *,
    build: Callable[[Any, Any, Any], ExportResult],
    capability: str,
    max_bytes: int = DEFAULT_MAX_BYTES,
    mode: Mode = "job",
    p95_ms: int | None = None,
    measured_on: str = "",
) -> ExportKind:
    if not kind:
        raise ValueError("export registry: kind فارغ")
    if kind in _REGISTRY:
        raise ValueError(f"export registry: النوعُ {kind!r} مسجَّلٌ من قبل")
    if mode == "direct":
        if p95_ms is None or not measured_on:
            raise ValueError(
                f"export registry: {kind!r} متزامنٌ بلا قياسِ p95 مثبَّتٍ بمصدره وتاريخه — الافتراضُ الآمن job"
            )
        if p95_ms > DIRECT_P95_CEILING_MS:
            raise ValueError(
                f"export registry: {kind!r} p95={p95_ms}ms فوق {DIRECT_P95_CEILING_MS}ms — يجب أن يكون job"
            )
    spec = ExportKind(kind, build, capability, max_bytes, mode, p95_ms, measured_on)
    _REGISTRY[kind] = spec
    return spec


def get(kind: str) -> ExportKind | None:
    return _REGISTRY.get(kind)


def kinds() -> dict[str, ExportKind]:
    """نسخةٌ من السجلّ (للحرّاس والاختبار)."""
    return dict(_REGISTRY)


def unregister(kind: str) -> None:
    """للاختبار وحدَه: يُزيل نوعاً سجّله اختبارٌ ليخلّف السجلَّ كما وجده."""
    _REGISTRY.pop(kind, None)

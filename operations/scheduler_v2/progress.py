"""progress.py — سجلُّ تقدّم الحلّ وطلبُ الإيقاف المبكر (شريطُ التقدّم، أمرُ المالك).

العقدُ للواجهة (JSON من `snapshot()`؛ كلُّ المعرّفات مختصرةٌ لا أسماء):
    state          running | feasible | optimal | infeasible | timeout | stopped | rejected | failed
    state_label    الوصفُ العربيّ الجاهز للعرض
    done           true حين انتهى الحلُّ نهائيّاً (فتتوقّف الواجهةُ عن الاستعلام)
    elapsed_s      الزمنُ المنقضي بالثواني   ·  max_s السقفُ  ·  remaining_s المتبقّي
    objective      قيمةُ الهدف الحاليّة (null قبل أوّل حلّ)  ·  bound الحدُّ الأدنى المثبَت
    gap_pct        الفجوةُ % = (objective − bound) / max(|objective|, 1) × 100 (null قبل أوّل حلّ)
    solutions      عددُ الحلول التي وجدها
    stop_requested طلبَ المستخدمُ الإيقافَ المبكر
    updated_at     ISO-8601

التخزين في `ScheduleGeneration.metrics["v2_progress"]` بلا هجرة، والقراءةُ والكتابةُ تحت قفل الصفّ فلا يضيع
طلبُ إيقافٍ بين كتابتَين. وهو الطريقُ الوحيد المشترك بين الويب والعامل (المخبأ في التطوير لكلّ عمليّةٍ وحدَها).
"""

from __future__ import annotations

import threading
import time
from typing import Any

from django.db import transaction
from django.utils import timezone

KEY = "v2_progress"
STOP_KEY = "v2_stop_requested"

LABELS = {
    "running": "يعمل — لم يُوجد حلٌّ بعد",
    "feasible": "وُجد حلٌّ ويتحسّن",
    "optimal": "أمثلُ بالبرهان",
    "infeasible": "مستحيلٌ بالبرهان",
    "timeout": "انتهت المهلة",
    "stopped": "أُوقف مبكّراً بأفضل حلّ",
    "rejected": "رفضه المُقيِّم المستقلّ",
    "failed": "فشل",
}
TERMINAL = {"optimal", "infeasible", "timeout", "stopped", "rejected", "failed"}


class ProgressTracker:
    """يجمع حالةَ الحلّ في الذاكرة وينشرها في الصفّ كلَّ ثانية. بلا ortools فيُختبر وحدَه."""

    def __init__(self, generation_id: Any, max_seconds: float) -> None:
        self.generation_id = generation_id
        self.max_seconds = float(max_seconds)
        self.objective: float | None = None
        self.bound: float | None = None
        self.solutions = 0
        self.state = "running"
        self.stop_flag = False
        self._started = time.monotonic()
        self._lock = threading.Lock()

    # ── من الحلّال ──
    def on_solution(self, objective: float, bound: float) -> None:
        with self._lock:
            self.objective, self.bound = objective, bound
            self.solutions += 1
            self.state = "feasible"

    def on_bound(self, bound: float) -> None:
        with self._lock:
            self.bound = bound

    def finish(self, state: str) -> None:
        with self._lock:
            self.state = state
        self.publish()

    # ── العرض ──
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            elapsed = time.monotonic() - self._started
            gap = None
            if self.objective is not None and self.bound is not None:
                gap = round(
                    max(0.0, self.objective - self.bound) / max(abs(self.objective), 1) * 100, 2
                )
            return {
                "state": self.state,
                "state_label": LABELS[self.state],
                "done": self.state in TERMINAL,
                "elapsed_s": round(elapsed, 1),
                "max_s": self.max_seconds,
                "remaining_s": round(max(0.0, self.max_seconds - elapsed), 1),
                "objective": self.objective,
                "bound": self.bound,
                "gap_pct": gap,
                "solutions": self.solutions,
                "stop_requested": self.stop_flag,
                "updated_at": timezone.now().isoformat(),
            }

    def publish(self) -> bool:
        """ينشر اللقطةَ ويُرجع هل طُلب الإيقافُ. قراءةُ العلَم وكتابةُ اللقطة تحت قفلٍ واحد."""
        from operations.models import ScheduleGeneration

        with transaction.atomic():
            row = (
                ScheduleGeneration.objects.select_for_update()
                .filter(pk=self.generation_id)
                .only("metrics")
                .first()
            )
            if row is None:
                return False
            metrics = dict(row.metrics or {})
            self.stop_flag = bool(metrics.get(STOP_KEY))
            metrics[KEY] = self.snapshot()
            ScheduleGeneration.objects.filter(pk=row.pk).update(metrics=metrics)
        return self.stop_flag


def request_stop(generation: Any) -> bool:
    """يطلب إيقافاً مبكّراً يحتفظ بأفضل حلّ. يُرجع False إن لم يكن التوليدُ جارياً."""
    from operations.models import ScheduleGeneration

    with transaction.atomic():
        row = ScheduleGeneration.objects.select_for_update().get(pk=generation.pk)
        if row.status != "running":
            return False
        metrics = dict(row.metrics or {})
        metrics[STOP_KEY] = True
        ScheduleGeneration.objects.filter(pk=row.pk).update(metrics=metrics)
    return True


def read_progress(generation: Any) -> dict[str, Any]:
    """ما تقرؤه نقطةُ الاستعلام: لقطةُ التقدّم وحالةُ الصفّ. خفيفةٌ (حقلٌ واحد)."""
    from operations.models import ScheduleGeneration

    row = ScheduleGeneration.objects.only("status", "metrics", "error_message").get(
        pk=generation.pk
    )
    snap = dict((row.metrics or {}).get(KEY) or {})
    if not snap:
        snap = {"state": "running", "state_label": LABELS["running"], "done": False}
        if row.status in ("queued",):
            snap["state_label"] = "في الانتظار"
    snap["generation_status"] = row.status  # queued | running | draft | failed | approved…
    if row.status == "failed" and not snap.get("done"):
        snap.update(state="failed", state_label=LABELS["failed"], done=True)
    snap["error"] = row.error_message if row.status == "failed" else ""
    snap["stop_requested"] = bool((row.metrics or {}).get(STOP_KEY))
    return snap


class Ticker(threading.Thread):
    """خيطٌ يُحدّث اللقطةَ كلَّ ثانيةٍ ويوقف الحلّالَ عند طلب الإيقاف (`on_stop` تُستدعى مرّةً)."""

    def __init__(self, tracker: ProgressTracker, on_stop: Any, interval: float = 1.0) -> None:
        super().__init__(daemon=True)
        self.tracker, self.on_stop, self.interval = tracker, on_stop, interval
        self._done = threading.Event()

    def run(self) -> None:
        stopped = False
        while not self._done.wait(self.interval):
            try:
                if self.tracker.publish() and not stopped:
                    stopped = True
                    self.on_stop()
            except Exception:  # noqa: BLE001 — تعطّلُ النشر لا يُسقط الحلّ
                pass
        from django.db import connection

        connection.close()  # اتّصالُ هذا الخيط له وحدَه

    def stop(self) -> None:
        self._done.set()
        self.join(timeout=5)

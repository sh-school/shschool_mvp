"""خدماتُ سجلِّ مصدر الحقيقة: التحميلُ والحذفُ الناعم وتغييرُ الحالة، وكلُّها تكتب سطرَ Revision."""

import hashlib
import json
from typing import Any

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from core.capabilities import has_capability
from sot_registry.models import Provision, Revision, Source

_SNAPSHOT_FIELDS = (
    "article",
    "printed_page",
    "file_page",
    "verbatim",
    "explanation",
    "rank",
    "status",
)


class SotError(Exception):
    """خطأٌ في بيانات اللقطة أو في إجراءٍ على حكم."""


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def snapshot_sha256(provisions: list[dict[str, Any]]) -> str:
    """بصمةُ الأحكام بترتيبٍ قانونيّ: تكشف أيَّ تغييرٍ في النصّ أو العدد."""
    canonical = json.dumps(
        sorted(provisions, key=lambda p: p["pid"]), ensure_ascii=False, sort_keys=True
    )
    return text_sha256(canonical)


def actor_label(user: Any) -> str:
    role = user.get_role() if hasattr(user, "get_role") else "system"
    return f"{role}:{getattr(user, 'pk', '')}"[:80]


def _state(p: Provision) -> dict[str, Any]:
    return {f: getattr(p, f) for f in _SNAPSHOT_FIELDS} | {"is_deleted": p.is_deleted}


def _log(p: Provision, action: str, before: dict, after: dict, actor: str) -> None:
    Revision.objects.create(provision=p, action=action, before=before, after=after, actor=actor)


@transaction.atomic
def load_snapshot(data: dict[str, Any], *, actor: str = "sot_load") -> dict[str, int]:
    """يحمّل لقطةً: المصدرُ وأحكامُه «غير مدقَّق».

    idempotent بمفتاح المعرّف: حكمٌ موجودٌ لا يُكرَّر، ولا يُمسّ حكمٌ راجعه بشرٌ أو تغيّرت حالتُه عن «غير مدقَّق».
    يتحقّق من العدد المتوقَّع ومن البصمة قبل أيّ كتابة.
    """
    provisions = data.get("provisions") or []
    expected = int(data.get("expected_count", 0))
    if expected and len(provisions) != expected:
        raise SotError(f"عددُ الأحكام {len(provisions)} لا يطابق المتوقَّع {expected}.")
    declared = data.get("sha256")
    if declared and declared != snapshot_sha256(provisions):
        raise SotError("بصمةُ اللقطة لا تطابق محتواها.")
    for p in provisions:
        for required in ("pid", "article", "printed_page", "verbatim"):
            if p.get(required) in (None, ""):
                raise SotError(f"حكمٌ بلا {required}: {p.get('pid')!r}")

    meta = data["source"]
    source, _ = Source.objects.get_or_create(
        code=meta["code"],
        defaults={
            "kind": meta["kind"],
            "title": meta["title"],
            "issuer": meta.get("issuer", ""),
            "doc_number": meta.get("doc_number", ""),
            "school_year": meta.get("school_year", ""),
            "original_sha256": meta.get("original_sha256", ""),
            "expected_count": expected,
        },
    )
    created = skipped = 0
    for p in provisions:
        if Provision.objects.filter(pid=p["pid"]).exists():
            skipped += 1
            continue
        obj = Provision.objects.create(
            pid=p["pid"],
            source=source,
            article=p["article"],
            printed_page=p["printed_page"],
            file_page=p.get("file_page"),
            verbatim=p["verbatim"],
            explanation=p.get("explanation", ""),
            rank=p.get("rank", 0),
            status=Provision.UNVERIFIED,
            loaded_by=actor,
        )
        _log(obj, Revision.LOAD, {}, _state(obj), actor)
        created += 1
    return {"created": created, "skipped": skipped}


def _require(user: Any, cap: str) -> None:
    if not has_capability(user, cap):
        raise PermissionDenied("لا صلاحيةَ لهذا الإجراء.")


@transaction.atomic
def change_status(user: Any, provision: Provision, status: str) -> Provision:
    """تغييرُ الحالة للمالك وحده؛ و«نافذ» لا يُمنح إلا بعد مراجعةٍ بشريّةٍ غير المحمِّل."""
    _require(user, "sot.approve")
    if status not in dict(Provision.STATUSES):
        raise SotError("حالةٌ غير معروفة.")
    actor = actor_label(user)
    if status == Provision.EFFECTIVE and (
        not provision.reviewed_by or provision.reviewed_by == provision.loaded_by
    ):
        raise SotError("لا يصير الحكمُ نافذًا قبل مراجعةٍ بشريّةٍ من غير المحمِّل.")
    before = _state(provision)
    provision.status = status
    provision.save(update_fields=["status"])
    _log(provision, Revision.STATUS, before, _state(provision), actor)
    return provision


@transaction.atomic
def mark_reviewed(user: Any, provision: Provision) -> Provision:
    _require(user, "sot.approve")
    before = _state(provision)
    provision.reviewed_by = actor_label(user)
    provision.reviewed_at = timezone.now()
    if provision.status == Provision.UNVERIFIED:
        provision.status = Provision.IN_REVIEW
    provision.save(update_fields=["reviewed_by", "reviewed_at", "status"])
    _log(provision, Revision.EDIT, before, _state(provision), provision.reviewed_by)
    return provision


@transaction.atomic
def edit_provision(user: Any, provision: Provision, **changes: Any) -> Provision:
    """تعديلُ حقولٍ مسموحةٍ مع سطر Revision؛ ويعيد الحكمَ «قيد المراجعة» إن كان نافذًا."""
    _require(user, "sot.propose")
    allowed = {"explanation", "verbatim", "article", "printed_page", "file_page", "rank"}
    if set(changes) - allowed:
        raise SotError("حقلٌ غير مسموحٍ تعديلُه.")
    before = _state(provision)
    for key, value in changes.items():
        setattr(provision, key, value)
    fields = list(changes)
    if provision.status == Provision.EFFECTIVE:
        provision.status = Provision.IN_REVIEW
        fields.append("status")
    provision.save(update_fields=fields)
    _log(provision, Revision.EDIT, before, _state(provision), actor_label(user))
    return provision


@transaction.atomic
def soft_delete(user: Any, provision: Provision, reason: str) -> Provision:
    """حذفٌ ناعم للمالك وحده؛ يُرفض لحكمٍ له ربطُ كودٍ أو تعارضٌ مفتوح."""
    _require(user, "sot.approve")
    if not reason.strip():
        raise SotError("سببُ الحذف مطلوب.")
    if provision.is_protected:
        raise SotError("حكمٌ له ربطُ كودٍ أو تعارضٌ مفتوح لا يُحذف.")
    before = _state(provision)
    provision.is_deleted = True
    provision.deleted_at = timezone.now()
    provision.delete_reason = reason[:200]
    provision.save(update_fields=["is_deleted", "deleted_at", "delete_reason"])
    _log(provision, Revision.SOFT_DELETE, before, _state(provision), actor_label(user))
    return provision


@transaction.atomic
def restore(user: Any, provision: Provision) -> Provision:
    _require(user, "sot.approve")
    before = _state(provision)
    provision.is_deleted = False
    provision.deleted_at = None
    provision.delete_reason = ""
    provision.save(update_fields=["is_deleted", "deleted_at", "delete_reason"])
    _log(provision, Revision.RESTORE, before, _state(provision), actor_label(user))
    return provision


def visible_for(user: Any) -> QuerySet[Provision]:
    """الإدارةُ (اعتماد) ترى كلَّ الأحكام الحيّة؛ وغيرُها النافذَ فقط؛ ومن بلا قراءةٍ لا شيء."""
    if not has_capability(user, "sot.read"):
        return Provision.objects.none()
    if has_capability(user, "sot.approve"):
        return Provision.objects.alive()
    return Provision.objects.visible()

"""رفعُ ملفّي aSc من صفحة الجدولة: التحقّقُ، والتخزينُ المؤقّت في الكاش، وجسمُ مهمّة Celery.

الويبُ والعاملُ حاويتان منفصلتان، فلا ملفَّ على القرص ولا صفَّ في قاعدة البيانات: بايتاتُ الملفّات
في الكاش بمفتاحٍ عشوائيٍّ وعمرِ خمسَ عشرةَ دقيقة وتُحذف عند انتهاء المهمّة، والتقريرُ يُحذف
عند أوّل قراءةٍ له بعد الانتهاء. والمنطقُ نفسُه في `asc_import` — لا نسخةَ ثانية.

لا أسماءَ في السجلّات: التقريرُ المعروضُ يحمل بنودَه كما يطبعها الأمر، أمّا `AuditLog` والسجلُّ
التقنيُّ فأعدادٌ وبصماتُ sha256 فقط.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import secrets
from typing import Any

from django.contrib.auth import get_user_model
from django.core.cache import cache

from academic_management import asc_import
from academic_management.management.commands.import_assignments_from_timetable import (
    NameRules,
    load_name_rules,
    rules_from_data,
)
from core.academic_calendar import academic_year_for_school
from core.models import School
from core.models.audit import AuditLog

logger = logging.getLogger(__name__)

MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_RULES_BYTES = 100 * 1024
TTL_SECONDS = 15 * 60
PDF_SIGNATURE = b"%PDF"

#: أقسامُ ملفّ القواعد وشكلُ كلٍّ منها (`TIMETABLE_NAME_RULES_FILE`).
_DICT_SECTIONS = ("teacher_aliases", "sole_holders", "split_subjects")
_LIST_SECTIONS = ("asc_ignore", "asc_title_words")


class UploadError(Exception):
    """ملفٌّ مرفوضٌ برسالةٍ تُعرض للمستخدم — لا تذكر محتواه."""


class StagedFiles:
    """ما حُفظ في الكاش لتشغيلٍ واحد: بايتاتُ ملفّي PDF وملفُّ القواعد الاختياريّ."""

    def __init__(self, teachers: bytes, classes: bytes, rules: bytes | None) -> None:
        self.teachers = teachers
        self.classes = classes
        self.rules = rules


def _key(token: str, part: str) -> str:
    return f"asc_import:{token}:{part}"


def _read_upload(upload: Any, label: str, limit: int) -> bytes:
    if upload is None:
        raise UploadError(f"{label}: لم يُرفع ملفّ.")
    if upload.size > limit:
        mega = limit >= 1024 * 1024
        shown = f"{limit // (1024 * 1024)} ميغابايت" if mega else f"{limit // 1024} كيلوبايت"
        raise UploadError(f"{label}: الملفُّ أكبرُ من الحدّ ({shown}).")
    return bytes(upload.read())


def validate_pdf(upload: Any, label: str) -> bytes:
    """امتدادُ pdf وتوقيعُ `%PDF` وحدُّ الحجم — وإلّا `UploadError`."""
    if upload is not None and not str(upload.name).lower().endswith(".pdf"):
        raise UploadError(f"{label}: الامتدادُ ليس pdf.")
    data = _read_upload(upload, label, MAX_PDF_BYTES)
    if not data.startswith(PDF_SIGNATURE):
        raise UploadError(f"{label}: المحتوى ليس PDF.")
    return data


def validate_rules(upload: Any) -> bytes | None:
    """ملفُّ القواعد اختياريّ؛ إن رُفع فبنيةٌ صحيحةٌ وحدُّه مئةُ كيلوبايت."""
    if upload is None:
        return None
    label = "ملفّ القواعد"
    if not str(upload.name).lower().endswith(".json"):
        raise UploadError(f"{label}: الامتدادُ ليس json.")
    data = _read_upload(upload, label, MAX_RULES_BYTES)
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise UploadError(f"{label}: ليس JSON صحيحاً.") from exc
    if not isinstance(parsed, dict):
        raise UploadError(f"{label}: يجب أن يكون كائناً (قاموساً) في أعلاه.")
    for section in _DICT_SECTIONS:
        if not isinstance(parsed.get(section, {}), dict):
            raise UploadError(f"{label}: القسمُ {section} يجب أن يكون قاموساً.")
    for section in _LIST_SECTIONS:
        if not isinstance(parsed.get(section, []), list):
            raise UploadError(f"{label}: القسمُ {section} يجب أن يكون قائمة.")
    return data


def stage(school_id: Any, files: StagedFiles) -> str:
    """يحفظ البايتاتِ في الكاش بمفتاحٍ عشوائيّ ويضع حالةَ «جارٍ»؛ يُرجع المفتاح."""
    token = secrets.token_urlsafe(24)
    cache.set(_key(token, "teachers"), files.teachers, TTL_SECONDS)
    cache.set(_key(token, "classes"), files.classes, TTL_SECONDS)
    if files.rules is not None:
        cache.set(_key(token, "rules"), files.rules, TTL_SECONDS)
    cache.set(_key(token, "state"), {"state": "running", "school_id": str(school_id)}, TTL_SECONDS)
    return token


def poll(token: str, school_id: Any) -> dict[str, Any] | None:
    """حالةُ التشغيل لمدرسة الطالب. `None` = ليس لمدرستك. والتقريرُ المنتهي يُحذف عند قراءته."""
    state = cache.get(_key(token, "state"))
    if state is None:
        return {"state": "expired"}
    if state.get("school_id") != str(school_id):
        return None
    if state["state"] != "running":
        cache.delete(_key(token, "state"))
    return dict(state)


def _rules_for(raw: bytes | None) -> NameRules:
    """قواعدُ الملفّ المرفوع لهذا التشغيل وحدَه، وإلّا قواعدُ الخادم كما يقرؤها الأمر."""
    return rules_from_data(json.loads(raw.decode("utf-8"))) if raw else load_name_rules()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _report(school: Any, year: str, analysis: asc_import.Analysis) -> dict[str, Any]:
    blocking = set(analysis.blocking)
    return {
        "school_name": school.name,
        "year": year,
        "lessons": analysis.lessons,
        "class_slots": analysis.class_slots,
        "items": [{"text": i.text, "ignored": i not in blocking} for i in analysis.items],
        "blocking": len(analysis.blocking),
    }


def _audit(user: Any, school: Any, create: bool, fields: dict[str, Any]) -> None:
    """أعدادٌ وبصماتٌ فقط — لا أسماءَ ولا نصَّ بند."""
    AuditLog.log(
        user=user,
        action="create" if create else "view",
        model_name="other",
        object_repr="استيرادُ جدول aSc من الصفحة" + (" — إنشاءُ مسودّة" if create else " — تحليل"),
        changes=fields,
        school=school,
    )


def run_job(token: str, school_id: Any, user_id: Any, create: bool, replace: bool) -> None:
    """جسمُ المهمّة: يحلّل، ويكتب المسودّةَ إن طُلب، ويضع النتيجةَ، ويحذف البايتات في كلّ حال."""
    school_key = str(school_id)
    result: dict[str, Any] = {"state": "done", "school_id": school_key, "create": create}
    parts = ("teachers", "classes", "rules")
    try:
        teachers = cache.get(_key(token, "teachers"))
        classes = cache.get(_key(token, "classes"))
        if teachers is None or classes is None:
            result["error"] = "انتهت مهلةُ الملفّات في الذاكرة — ارفعها من جديد."
            return
        school = School.objects.get(pk=school_id)
        year = academic_year_for_school(school)
        raw_rules = cache.get(_key(token, "rules"))
        analysis = asc_import.analyze(
            school, year, io.BytesIO(teachers), io.BytesIO(classes), _rules_for(raw_rules)
        )
        result.update(_report(school, year, analysis))
        audit = {
            "sha256_teachers": _sha(teachers),
            "sha256_classes": _sha(classes),
            "rules_uploaded": raw_rules is not None,
            "lessons": analysis.lessons,
            "class_slots": analysis.class_slots,
            "items": len(analysis.items),
            "blocking": len(analysis.blocking),
        }
        if create:
            try:
                result["written"] = asc_import.write_draft(
                    school,
                    year,
                    analysis,
                    audit["sha256_teachers"],
                    audit["sha256_classes"],
                    replace,
                )
            except asc_import.AscImportRefusedError as refusal:
                result["error"] = f"مرفوض: {refusal.reason}"
            audit.update(written=result.get("written"), replace=replace)
        user = get_user_model().objects.filter(pk=user_id).first()
        _audit(user, school, create and "error" not in result, audit)
    except Exception as exc:
        # نوعُ الخطأ فقط: رسالةُ الاستثناء قد تحمل نصاً من الملفّ.
        logger.error("تعذّر تشغيلُ استيراد aSc من الصفحة: %s", type(exc).__name__)
        result["error"] = "تعذّرت قراءةُ الملفّين — تحقّق أنّهما تصديرُ aSc الصحيح."
    finally:
        cache.delete_many([_key(token, part) for part in parts])
        cache.set(_key(token, "state"), result, TTL_SECONDS)

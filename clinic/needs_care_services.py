"""علامة «يحتاج مراعاةً» — المحدِّد والاستيراد (W-20261010-045، قرارا المالك D-336م وD-337م).

بياناتٌ صحّيّةٌ لقُصّر: أقصى تشديد. العلامةُ محايدةٌ للمعلّم (لا سببَ ولا تشخيص)، يضعها الممرّضُ
صراحةً، وتُستخرج من العيادة **برقم الطالب فقط**:

- `students_needing_care_ids` محدِّدٌ وحيدٌ يعيد معرّفاتِ الطلاب بـ`values_list` دون فكّ أيّ حقلٍ
  مشفَّر (اختبارٌ بـmock يثبّت ذلك)؛ ومنه وحدَه يقرأ جدولُ الرصد لاحقاً.
- `import_needs_care` يطابق ملفاً (رقمٌ وطنيٌّ + صفّ) بالرقم الوطنيّ 11 خانةً بتساوٍ تامّ، والصفُّ
  تحقُّقٌ لا مفتاح. التقريرُ أعدادٌ فقط، والرقمُ الوطنيّ لا يُسجَّل في تدقيقٍ ولا log ولا رسالة خطأ
  ولا اسم ملف، والملفُّ يُقرأ في الذاكرة ولا يُحفظ.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import reduce
from operator import or_
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from clinic.models import HealthRecord
from core.privacy import national_id_search_q

#: الرقمُ الوطنيّ القطريّ 11 خانةً — ما سواه صفٌّ مخالفٌ لا يُخمَّن.
NATIONAL_ID_LENGTH = 11
#: سقفُ حجم الملف: أصغرُ من حدّ Django للذاكرة (2.5 ميغا) فلا يُكتب أبداً في قرصٍ مؤقّت.
MAX_FILE_BYTES = 1_000_000
#: دفعةُ المطابقة: شرطُ OR واحدٌ لكلّ دفعة لا استعلامٌ لكلّ صفّ.
_CHUNK = 200

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
#: فراغاتٌ وعلاماتُ اتجاهٍ خفيّة تأتي من النسخ واللصق.
_INVISIBLE = re.compile(r"[\s‎‏‪-‮⁦-⁩﻿]+")
_GRADE_NUMBER = re.compile(r"(?<!\d)(1[0-2]|0?[7-9])(?!\d)")


class NeedsCareFileError(ValueError):
    """الملفُّ نفسُه غيرُ صالح (نوعٌ أو حجمٌ أو قراءة). رسالتُه عامّةٌ لا تحمل شيئاً من محتواه."""


@dataclass(frozen=True)
class NeedsCareImportReport:
    """أعدادٌ فقط — لا رقمَ ولا اسمَ ولا سطراً. الصفُّ المخالف والبلا مطابقة لا يُضبطان."""

    matched: int = 0  # طُوبق ووُضعت علامتُه
    unmatched: int = 0  # رقمٌ صحيحُ الشكل لا طالبَ به في هذه المدرسة
    violating: int = 0  # رقمٌ ليس 11 خانةً، أو صفٌّ لا يوافق صفَّ الطالب
    already_marked: int = 0  # من المطابَقين، ما كانت علامتُه موضوعةً أصلاً (مشمولٌ في matched)

    @property
    def total(self) -> int:
        return self.matched + self.unmatched + self.violating


# ── المحدِّد ────────────────────────────────────────────────────────────


def students_needing_care_ids(student_ids: Iterable[Any]) -> frozenset:
    """من بين `student_ids`، معرّفاتُ من وُضعت علامتُهم — لا غير.

    `values_list` على عمودين غيرِ مشفّرَين: فلا `from_db_value` يمرّ على حقلٍ طبّيٍّ مشفَّر، ولا
    يخرج من العيادة إلا المعرّف. فلا قائمةَ ولا تصدير: من يستدعيه يعطيه شعبةَ معلّمه ويأخذ منه
    مجموعةً يختبر بها الانتماء.
    """
    ids = list(student_ids)
    if not ids:
        return frozenset()
    return frozenset(
        HealthRecord.objects.filter(student_id__in=ids, needs_care=True).values_list(
            "student_id", flat=True
        )
    )


# ── قراءة الملف (في الذاكرة) ────────────────────────────────────────────


def _clean(cell: Any) -> str:
    """الخليّةُ نصّاً نظيفاً: أرقامٌ غربيّة، بلا فراغٍ ولا علاماتِ اتجاه، وعددٌ صحيحٌ لا «123.0»."""
    if cell is None:
        return ""
    if isinstance(cell, float) and cell.is_integer():
        cell = int(cell)
    return _INVISIBLE.sub("", str(cell)).translate(_ARABIC_DIGITS)


def _read_rows(content: bytes) -> list[tuple[str, str]]:
    """صفوفُ (رقم، صفّ) من xlsx أو csv — كلُّها من `bytes` في الذاكرة."""
    if not content:
        raise NeedsCareFileError("الملفُّ فارغ.")
    if len(content) > MAX_FILE_BYTES:
        raise NeedsCareFileError("الملفُّ أكبرُ من الحدّ المسموح.")
    raw: list[list[Any]] = []
    try:
        if content[:2] == b"PK":  # xlsx = zip
            import openpyxl

            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            raw = [list(r) for r in wb.active.iter_rows(values_only=True)]
        else:
            text = content.decode("utf-8-sig")
            raw = [list(r) for r in csv.reader(io.StringIO(text))]
    except Exception:  # noqa: BLE001 — لا نُسرّب رسالة المكتبة: قد تقتبس خليّةً من الملف
        raise NeedsCareFileError("تعذّرت قراءةُ الملف: ارفع xlsx أو csv سليماً.") from None
    rows: list[tuple[str, str]] = []
    for r in raw:
        cells = [_clean(c) for c in r[:2]]
        nid, grade = (cells + ["", ""])[:2]
        # الأسطرُ الفارغة، والختاميّةُ بحرفٍ واحد (نقطةٌ أو علامةٌ تركها البرنامج)، تُهمَل بلا عدّ.
        if len(nid + grade) <= 1:
            continue
        rows.append((nid, grade))
    # صفُّ الرأس: أوّلُ صفٍّ ليس في خانة الرقم فيه رقمٌ أصلاً.
    if rows and not re.search(r"\d", rows[0][0]):
        rows = rows[1:]
    return rows


def _grade_of(text: str) -> tuple[str, str] | None:
    """(`G10`، شعبة أو "") من خليّة الصف: «10/2» أو «10» أو «G10» أو «الصف العاشر 10». وإلا None."""
    m = _GRADE_NUMBER.search(text)
    if not m:
        return None
    grade = f"G{int(m.group(1))}"
    tail = text[m.end() :].lstrip("/.-")
    section = tail if tail.isdigit() else ""
    return grade, section


def _row_agrees(file_grade: str, class_group: Any) -> bool:
    parsed = _grade_of(file_grade)
    if parsed is None or class_group is None:
        return False
    grade, section = parsed
    if grade != class_group.grade:
        return False
    return not section or section == str(class_group.section).split("/")[-1].strip()


# ── الاستيراد ───────────────────────────────────────────────────────────


def import_needs_care(
    content: bytes, *, school: Any, user: Any, request: Any = None
) -> NeedsCareImportReport:
    """يضع علامةَ المراعاة لمن طُوبق رقمُه وصفُّه، ويُرجع أعداداً فقط.

    - المطابقةُ بتساوٍ تامّ على الرقم الوطنيّ عبر `national_id_search_q`، داخل مدرسة الممرّض.
    - صفٌّ بلا مطابقةٍ أو بصفٍّ مخالفٍ أو برقمٍ مختلّ الشكل **لا يُضبط ولا يُخمَّن**.
    - لا يُزيل علامةً قائمةً: الإزالةُ بيد الممرّض في شاشة السجلّ.
    - تدقيقٌ إجماليٌّ واحدٌ بأعدادٍ فقط، لا رقمَ فيه ولا اسمَ ولا معرّفَ طالب.
    """
    from core.models import AuditLog, CustomUser, StudentEnrollment

    rows = _read_rows(content)

    violating = 0
    candidates: dict[str, str] = {}  # رقم → صفّ الملف (آخرُ تكرارٍ يغلب)
    for nid, grade in rows:
        if not (nid.isdigit() and len(nid) == NATIONAL_ID_LENGTH):
            violating += 1
            continue
        candidates[nid] = grade

    # رقمٌ مكرَّرٌ في الملف يُحسب مرّةً واحدة: العدُّ بالطلاب لا بالأسطر.
    student_for: dict[str, Any] = {}
    numbers = list(candidates)
    for i in range(0, len(numbers), _CHUNK):
        chunk = numbers[i : i + _CHUNK]
        cond: Q = reduce(or_, (national_id_search_q("national_id", n) for n in chunk))
        for pk, nid in CustomUser.objects.filter(cond, memberships__school=school).values_list(
            "id", "national_id"
        ):
            student_for[nid.strip()] = pk

    unmatched = len([n for n in numbers if n not in student_for])

    current: dict[Any, Any] = {}
    for enrol in (
        StudentEnrollment.objects.filter(
            student_id__in=list(student_for.values()),
            is_active=True,
            class_group__school=school,
        )
        .select_related("class_group")
        .newest_first()
    ):
        current.setdefault(enrol.student_id, enrol.class_group)

    to_mark: list[Any] = []
    for nid, pk in student_for.items():
        if nid in candidates and _row_agrees(candidates[nid], current.get(pk)):
            to_mark.append(pk)
        elif nid in candidates:
            violating += 1

    matched, already = _mark(to_mark)

    AuditLog.log(
        user=user,
        action="update",
        model_name="HealthRecord",
        object_repr="استيراد علامة المراعاة (إجمالي)",
        changes={"matched": matched, "unmatched": unmatched, "violating": violating},
        school=school,
        request=request,
    )
    return NeedsCareImportReport(
        matched=matched, unmatched=unmatched, violating=violating, already_marked=already
    )


@transaction.atomic
def _mark(student_ids: list[Any]) -> tuple[int, int]:
    """يضع العلامةَ بلا signal لكلّ سجلّ (التدقيقُ إجماليٌّ واحدٌ يكتبه المستدعي)؛ (طُوبق، كان موضوعاً)."""
    if not student_ids:
        return 0, 0
    existing = dict(
        HealthRecord.objects.filter(student_id__in=student_ids).values_list(
            "student_id", "needs_care"
        )
    )
    already = sum(1 for v in existing.values() if v)
    now = timezone.now()
    HealthRecord.objects.filter(student_id__in=existing).update(needs_care=True, updated_at=now)
    HealthRecord.objects.bulk_create(
        [HealthRecord(student_id=pk, needs_care=True) for pk in student_ids if pk not in existing]
    )
    return len(student_ids), already


def import_from_request(request: Any) -> tuple[NeedsCareImportReport | None, str]:
    """من طلب رفعٍ إلى (تقرير، رسالةُ خطأ عامّة). الملفُّ يُقرأ في الذاكرة ولا يُحفظ."""
    upload = request.FILES.get("needs_care_file")
    if upload is None:
        return None, "اختر ملفاً أولاً."
    if upload.size > MAX_FILE_BYTES:
        return None, "الملفُّ أكبرُ من الحدّ المسموح."
    try:
        report = import_needs_care(
            upload.read(), school=request.school, user=request.user, request=request
        )
    except NeedsCareFileError as exc:
        return None, str(exc)
    return report, ""

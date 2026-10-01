"""خدماتُ النواة — استيرادُ الطلاب وأولياء الأمور من Excel (الكتابةُ خارج العرض).

الكلماتُ الأوّليّةُ الصادرةُ تبقى في قائمةٍ في الذاكرة يعيدها الاستيرادُ لعرضها في
استجابةٍ واحدة؛ لا تُخزَّن ولا تُسجَّل — ويُسجَّل عددُها وحده أثراً.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction

from core.academic_calendar import academic_year_for_school

logger = logging.getLogger(__name__)

# ── ثوابت الاستيراد ──────────────────────────────────────────────────

_IMPORT_RELATION_MAP: dict[str, str] = {
    "father": "father",
    "mother": "mother",
    "guardian": "guardian",
    "other": "other",
    "أب": "father",
    "والد": "father",
    "أم": "mother",
    "ام": "mother",
    "والدة": "mother",
    "وصي": "guardian",
    "وصية": "guardian",
    "شقيق أخ": "other",
    "أخ": "other",
    "جد": "other",
}

#: رؤوسُ الأعمدة الوزاريّة (سجلّ القيد) — القالبُ المعتمَد منذ W-028. القيمةُ
#: `(occurrence, key)`: بعض الرؤوس تتكرّر في الملف (قطاع/جهة العمل مرّتين،
#: والجنسية مرّتين) — الأُولى من «قطاع جهة العمل»/«جهة العمل» فارغةٌ دائماً
#: في الملف الوزاريّ الحقيقيّ (تحقَّق على 735 صفاً)، والثانيةُ بعد بريد وليّ
#: الأمر هي بياناتُه الفعليّة؛ والجنسيّةُ الأولى للطالب والثانية لوليّ الأمر
#: (تحقَّق: تخالف في 39 صفاً حين تكون صلةُ القرابة «أمّ» بجنسيةٍ مختلفة).
_MINISTRY_HEADER_MAP: dict[str, tuple[int, str]] = {
    "الرقم": (0, "student_nid"),
    "الاسم": (0, "full_name"),
    "الجنسية": (0, "nationality"),  # الثانية تُستثنى صراحةً أدناه
    "تاريخ الميلاد": (0, "birth_date_raw"),
    "الشعبة الصفية": (0, "class_combined"),
    "رقم الهاتف": (0, "phone"),
    "البريد الالكتروني": (0, "email"),
    "البلدية": (0, "municipality"),
    "المنطقة": (0, "region"),
    "يستخدم الحافلة": (0, "uses_bus_raw"),
    "اسم المركز الصحي الرئيسي": (0, "health_center_name"),
    "رقم الرعاية الصحية الرئيسي": (0, "health_card_number"),
    "رقم مستشفى حمد": (0, "hamad_hospital_number"),
    "رقم ولي الامر": (0, "parent_nid"),
    "اسم ولي الامر": (0, "parent_name"),
    "صلة القرابة": (0, "relation_raw"),
    "رقم هاتف ولي الامر": (0, "parent_phone"),
    "البريد الالكتروني لولي الامر": (0, "parent_email"),
    "رقم كهرماء": (0, "kahramaa_number"),
}
#: الرأسُ الذي يحدّد بداية جدول البيانات — يُفتَّش عنه في أوّل عشرة صفوف لأنّ
#: الملف الوزاريّ يسبقه سطرُ عنوانٍ وسطرٌ فارغ (رأى ذلك فحصُ الملف الحقيقيّ).
_MINISTRY_HEADER_MARKER = "الرقم"


def _locate_ministry_header(ws: Any) -> tuple[int, dict[str, int]] | None:
    """يبحث عن صفّ الرأس الوزاريّ ويُرجع (رقم الصفّ، فهرس الأعمدة) أو None إن لم يكن ملفّاً وزارياً.

    يميّز العمودين المتكرّرين «قطاع جهة العمل»/«جهة العمل» (الأُولى فارغةٌ
    دائماً فتُهمَل، الثانية لوليّ الأمر) و«الجنسية» (الأولى للطالب والثانية
    لوليّ الأمر) بعدّ التكرار صراحةً — لا بالاعتماد على ترتيب الأعمدة وحده.
    """

    def _norm(v: Any) -> str:
        return str(v).strip().replace("‎", "") if v else ""

    for row_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=10, values_only=True), start=1):
        if row and _norm(row[0]) == _MINISTRY_HEADER_MARKER:
            cols: dict[str, int] = {}
            nat_seen = 0
            sector_seen = 0
            employer_seen = 0
            for idx, cell in enumerate(row):
                name = _norm(cell)
                if not name:
                    continue
                if name == "الجنسية":
                    nat_seen += 1
                    cols["nationality" if nat_seen == 1 else "parent_nationality"] = idx
                    continue
                if name == "قطاع جهة العمل":
                    sector_seen += 1
                    if sector_seen == 2:  # الأُولى فارغةٌ دائماً فتُهمَل
                        cols["parent_employer_sector"] = idx
                    continue
                if name == "جهة العمل":
                    employer_seen += 1
                    if employer_seen == 2:
                        cols["parent_employer_name"] = idx
                    continue
                mapped = _MINISTRY_HEADER_MAP.get(name)
                if mapped:
                    cols[mapped[1]] = idx
            return row_idx, cols
    return None


_IMPORT_GRADE_NORMALIZE = {
    "7": "G7",
    "8": "G8",
    "9": "G9",
    "07": "G7",
    "08": "G8",
    "09": "G9",
    "10": "G10",
    "11": "G11",
    "12": "G12",
    "g7": "G7",
    "g8": "G8",
    "g9": "G9",
    "g10": "G10",
    "g11": "G11",
    "g12": "G12",
    "G7": "G7",
    "G8": "G8",
    "G9": "G9",
    "G10": "G10",
    "G11": "G11",
    "G12": "G12",
}


# ── مساعدات الاستيراد ─────────────────────────────────────────────────


def _split_class_notation(grade_cell: str, section_cell: str) -> tuple[str, str]:
    """يقبل «7/1» في خانة الصف كما يقبل عمودين منفصلين.

    الشُّعب في المدرسة تُسمّى «7/1» و«11/2» — اسمٌ واحد لا حقلان. وكان
    الاستيراد يتوقّع عمودين، فخانةٌ مكتوبٌ فيها «7/1» لا تُطابق مفتاحاً في
    `_IMPORT_GRADE_NORMALIZE`، فيُتخطّى الطالب بلا تسجيل.

    ولا يُخفق الاستيراد: يُنشئ الطالب ويُدرج سطراً في الأخطاء، فيسهل أن يمرّ
    مئةُ طالبٍ بلا شعبة دون أن ينتبه أحد.

    فإن حوت خانة الصف فاصلاً (‏/ أو . أو -) قُسّمت، وإلّا بقي العمودان كما هما.
    """
    if section_cell:
        return grade_cell, section_cell
    for sep in ("/", ".", "-"):
        if sep in grade_cell:
            head, _, tail = grade_cell.partition(sep)
            return head.strip(), tail.strip()
    return grade_cell, section_cell


def _parse_import_row(row: Any) -> dict[str, str]:
    """يحوّل tuple الصف الخام إلى قاموس بأسماء واضحة."""

    def _cell(pos: int, default: str = "") -> str:
        return str(row[pos]).strip() if len(row) > pos and row[pos] else default

    grade_raw, section = _split_class_notation(_cell(2), _cell(3))

    return {
        "student_nid": _cell(0),
        "full_name": _cell(1),
        "grade_raw": grade_raw,
        "section": section,
        "phone": _cell(4),
        "email": _cell(5),
        "parent_nid": _cell(6),
        "parent_name": _cell(7),
        "parent_phone": _cell(8),
        "parent_email": _cell(9),
        "relation_raw": _cell(10, "father"),
    }


def _upsert_user(
    nid: str,
    full_name: str,
    phone: str = "",
    email: str = "",
    *,
    role_label: str = "",
    issued: list[dict] | None = None,
) -> tuple[Any, bool]:
    """
    get_or_create مستخدم بالرقم الشخصي.
    إذا أُنشئ: كلمةُ مرورٍ عشوائيّةٌ (قرارُ المالك: لا تساوي الرقمَ الشخصيّ) مع
    `must_change_password`، ويملأ phone/email.
    إذا كان موجوداً: يُكمل الحقول الفارغة فقط ولا يمسّ كلمتَه.
    يُعيد (user, created).

    `issued`: قائمةُ المستدعي — يُضاف إليها صفُّ ورقةِ الاعتماد للحساب الجديد
    (الرقمُ مستورٌ: كشفٌ جماعيّ). الكلمةُ لا تُحفظ في غير هذه القائمة في الذاكرة.
    """
    from core.initial_passwords import assign_initial_password
    from core.models import CustomUser

    user: Any
    user, created = CustomUser.objects.get_or_create(
        national_id=nid,
        defaults={"full_name": full_name or nid, "is_active": True},
    )
    if created:
        assign_initial_password(user, issued if issued is not None else [], role_label)
        if phone:
            user.phone = phone
        if email:
            user.email = email
        user.save()
    else:
        changed = False
        if not user.full_name and full_name:
            user.full_name = full_name
            changed = True
        if not user.phone and phone:
            user.phone = phone
            changed = True
        if not user.email and email:
            user.email = email
            changed = True
        if changed:
            user.save()
    return user, created


def _enroll_student_in_class(
    student: Any,
    school: Any,
    grade_raw: str,
    section: str,
    stats: dict[str, Any],
    row_num: int,
) -> bool:
    """
    يبحث عن الفصل ويسجّل الطالب فيه.
    يُضيف خطأ إلى stats إذا لم يُعثر على الفصل.
    يُعيد True إذا أُنشئ تسجيل جديد.
    """
    from core.models import ClassGroup, StudentEnrollment

    grade = _IMPORT_GRADE_NORMALIZE.get(grade_raw, "")
    if not (grade and section):
        return False

    # الشُّعب مرتبطةٌ بعامها، فمع وجود عامين تُعيد `first()` واحدةً عشوائية —
    # ويُسجَّل الطالب في شعبة العام الماضي. والتقييد بالعام يمنع ذلك.
    year = academic_year_for_school(school)
    class_group = ClassGroup.objects.filter(
        school=school, grade=grade, section=section, academic_year=year, is_active=True
    ).first()

    if not class_group:
        stats["errors"].append(
            f"سطر {row_num}: الفصل {grade}/{section} غير موجود في {year} "
            f"— تم إنشاء الطالب بدون تسجيل"
        )
        return False

    _, created = StudentEnrollment.objects.get_or_create(
        student=student, class_group=class_group, defaults={"is_active": True}
    )
    return bool(created)


def _link_parent_to_student(
    parent: Any, student: Any, school: Any, relation_raw: str, stats: dict[str, Any]
) -> bool:
    """
    يُنشئ ParentStudentLink إذا لم يكن موجوداً.
    يُعيد True إذا أُنشئ رابط جديد.
    """
    from core.models import ParentStudentLink

    relation = _IMPORT_RELATION_MAP.get(relation_raw, "father")
    _, created = ParentStudentLink.objects.get_or_create(
        parent=parent,
        student=student,
        school=school,
        defaults={
            "relationship": relation,
            "is_primary": True,
            "can_view_grades": True,
            "can_view_attendance": True,
        },
    )
    return created


def _split_ministry_class(combined: str) -> tuple[str, str]:
    """يفكّك «الشعبة الصفية» الوزاريّة («10/2»، «08/ESE») إلى (صفّ، شعبة).

    شُعبُ التربية الخاصّة تحمل الصفَّ داخل اسم الشعبة نفسِه في القاعدة
    («07/ESE» لا «ESE» وحدها — راجع `ClassGroup.section`)، فخانةٌ كـ«08/ESE»
    تبقى شعبتُها «08/ESE» كاملة، بخلاف «10/2» العاديّة التي تُفكَّك فعلاً.
    """
    if "/" not in combined:
        return "", combined
    head, _, tail = combined.partition("/")
    if tail.isdigit():
        return head, tail
    return head, combined


def _first_phone(raw: str) -> str:
    """يأخذ أوّل رقمٍ عند تعدّد أرقام الهاتف في خليّةٍ واحدة («رقم1، رقم2»)
    — النموذجُ حقلٌ واحدٌ (`max_length=20`)، والملفُّ الوزاريّ يضع أحياناً
    أكثر من رقمٍ مفصولةً بفواصل."""
    if not raw:
        return ""
    first = raw.split(",")[0].strip()
    return first[:20]


def _parse_ministry_date(raw: str) -> Any:
    """يحوّل «02/01/2012 12:00:00 ص» إلى `date` — أو None إن تعذّر."""
    import datetime

    if not raw:
        return None
    day_part = raw.strip().split(" ")[0]
    try:
        return datetime.datetime.strptime(day_part, "%d/%m/%Y").date()
    except ValueError:
        return None


def _upsert_user_from_registry(
    nid: str,
    *,
    users_cache: dict[str, Any],
    full_name: str,
    phone: str,
    email: str,
    nationality: str,
    municipality: str,
    region: str,
    employer_sector: str,
    employer_name: str,
    kahramaa_number: str,
    uses_bus: bool | None = None,
    role_label: str,
    issued: list[dict],
) -> tuple[Any, bool]:
    """upsert بالرقم الشخصيّ من ذاكرةٍ مُحمَّلةٌ مسبقاً (`users_cache`) لا استعلامٍ
    لكلّ سطر — المدرسةُ فيها مئاتُ الطلّاب، وقراءةَ كلٍّ منهم على حِدة أبطأت
    استيرادَ 734 صفاً إلى دقيقتين (شكوى المالك 2026-10-01). ومصدرُ مركز
    البيانات الوطنيّ يغلب دائماً على القيم الموجودة، فتُكتب هذه الحقول فوق
    الموجود لا شرط الفراغ، خلافاً لـ`_upsert_user` القديمة.

    `users_cache` يُحدَّث داخل الدالّة عند إنشاء مستخدمٍ جديد — ليراه الاستدعاءُ
    التالي لنفس الرقم الشخصيّ (أخٌ لطالبٍ سابق، أو وليّ أمرٍ تكرّر) بلا استعلامٍ ثانٍ.
    """
    from core.initial_passwords import assign_initial_password
    from core.models import CustomUser

    user = users_cache.get(nid)
    created = False
    if user is None:
        user = CustomUser(national_id=nid, full_name=full_name or nid, is_active=True)
        created = True

    # [أداء] كلّ `save()` يُطلق `core.signals.audit_user_change` فيكتب سطراً
    # في AuditLog — وغالبيّةُ صفوف الاستيراد المتكرّر بلا تغييرٍ فعليّ (الملفُّ
    # نفسُه أعيد رفعُه). فنقيس قبل الكتابة: لا نكتب شيئاً إن لم يتغيّر شيء،
    # بدل upsert أعمى يكلّف صفّاً في سجلّ التدقيق لكلّ طالبٍ في كلّ مرّة.
    before = (
        user.full_name,
        user.phone,
        user.email,
        user.nationality,
        user.municipality,
        user.region,
        user.employer_sector,
        user.employer_name,
        user.kahramaa_number,
        user.uses_bus,
    )

    if full_name:
        user.full_name = full_name
    if phone:
        user.phone = phone
    if email:
        user.email = email
    if nationality:
        user.nationality = nationality
    # البلديّة/المنطقة/الحافلة/قطاع العمل/كهرماء — تُكتب حتى لو فارغة، فهذه
    # حقولٌ مصدرُها الوحيد الملفُّ الوزاريّ، وفراغها في الملف يعني أنها
    # فُرِّغت فعلاً (لا نُبقي قيمةً قديمة يتيمة).
    user.municipality = municipality
    user.region = region
    user.employer_sector = employer_sector
    user.employer_name = employer_name
    user.kahramaa_number = kahramaa_number
    if uses_bus is not None:
        user.uses_bus = uses_bus

    if created:
        assign_initial_password(user, issued, role_label)  # يضبط كلمةَ المرور قبل أوّل save()
        user.save()
    else:
        after = (
            user.full_name,
            user.phone,
            user.email,
            user.nationality,
            user.municipality,
            user.region,
            user.employer_sector,
            user.employer_name,
            user.kahramaa_number,
            user.uses_bus,
        )
        if after != before:
            user.save()

    users_cache[nid] = user
    return user, created


def _sync_student_class_group(
    student: Any,
    school: Any,
    year: str,
    grade_raw: str,
    section: str,
    *,
    class_groups: dict[tuple[str, str], Any],
    enrollments_cache: dict[Any, Any],
    stats: dict[str, Any],
    row_num: int,
) -> None:
    """يزامن شعبة الطالب من فهارس مُحمَّلةٍ مسبقاً — ترفيعٌ أو نقلٌ داخل العام
    نفسِه يُطفئ القيدَ القديم (is_active=False) وينشئ قيداً جديداً، بدل تركِ
    قيدَين نشطَين معاً في العام نفسه (ما لا يمنعه القيدُ الفريد في القاعدة إذ
    هو على زوج (طالب، شعبة) لا (طالب، عام))."""
    from core.models import StudentEnrollment

    grade = _IMPORT_GRADE_NORMALIZE.get(grade_raw, "")
    if not (grade and section):
        stats["errors"].append(f"سطر {row_num}: تعذّر تفسير الصفّ/الشعبة ({grade_raw}/{section})")
        return

    class_group = class_groups.get((grade, section))
    if not class_group and "/" in section:
        # شُعبُ التربية الخاصّة تحمل الصفَّ أحياناً داخل اسمها («08/ESE») وأحياناً
        # لا («ESE» وحدها، كما صار العُرف من 2026-2027) — جُرِّب الاسمَ المجرَّد.
        class_group = class_groups.get((grade, section.rsplit("/", 1)[-1]))
    if not class_group:
        stats["errors"].append(
            f"سطر {row_num}: الشعبة {grade}/{section} غير موجودة في {year} — تجاوز التسجيل"
        )
        return

    current = enrollments_cache.get(student.id)
    if current and current.class_group_id == class_group.id:
        return  # لا تغيير
    if current:
        current.is_active = False
        current.save(update_fields=["is_active"])
        stats["enrollments_transferred"] += 1

    enrollment, created = StudentEnrollment.objects.get_or_create(
        student=student, class_group=class_group, defaults={"is_active": True}
    )
    if not created:
        enrollment.is_active = True
        enrollment.save(update_fields=["is_active"])
    enrollment.class_group = class_group  # للمقارنة التالية إن تكرّر الرقمُ لاحقاً في نفس الملف
    enrollments_cache[student.id] = enrollment
    stats["enrollments_created"] += 1


def _sync_health_record(
    student: Any,
    health_center_name: str,
    health_card_number: str,
    hamad_hospital_number: str,
    *,
    health_cache: dict[Any, Any],
) -> None:
    """upsert لسجلّ العيادة من ذاكرةٍ مُحمَّلةٍ مسبقاً — الحقولُ الثلاثةُ
    الوزاريّةُ وحدها، مشفَّرةٌ at-rest بالحقل الشفّاف (core/fields.py)."""
    from clinic.models import HealthRecord

    record = health_cache.get(student.id)
    is_new = record is None
    if is_new:
        record = HealthRecord(student=student)
    changed = is_new or (
        record.health_center_name,
        record.health_card_number,
        record.hamad_hospital_number,
    ) != (health_center_name, health_card_number, hamad_hospital_number)
    record.health_center_name = health_center_name
    record.health_card_number = health_card_number
    record.hamad_hospital_number = hamad_hospital_number
    if changed:  # [أداء] كلّ save() يكتب سطراً في AuditLog — راجع _upsert_user_from_registry
        record.save()
    health_cache[student.id] = record


def _read_ministry_rows(
    uploaded_file: Any, header_row: int, cols: dict[str, int]
) -> list[dict[str, str]]:
    """يقرأ ملفَّ الإكسل مرّةً واحدةً ويُعيد صفوفاً جاهزةً كقواميسَ نصّيّةٍ
    (مفاتيحُها أسماءُ الحقول في `_MINISTRY_HEADER_MAP`، لا فهارسَ أعمدة) —
    فيُستهلَك مولِّدُ `read_only=True` مرّةً، ويستقلّ باقي الكودِ عن بنية الملف."""
    import openpyxl

    wb = openpyxl.load_workbook(uploaded_file, read_only=True, data_only=True)
    ws = wb.active

    def _cell(row: Any, key: str) -> str:
        idx = cols.get(key)
        if idx is None or idx >= len(row) or row[idx] is None:
            return ""
        v = str(row[idx]).strip()
        return "" if v == "-" else v

    # كلُّ مفاتيح الحقول المعروفة — لا `cols.keys()` وحدها: عمودٌ غائبٌ عن ملفٍّ
    # بعينه (نسخةٌ وزاريّةٌ ناقصةٌ) يجب أن يُقرأ فارغاً ("") لا أن يُسقط المفتاحَ
    # من القاموس فيفجّر `KeyError` لاحقاً في معالجة الصفّ.
    all_keys = {v[1] for v in _MINISTRY_HEADER_MAP.values()} | {
        "parent_nationality",
        "parent_employer_sector",
        "parent_employer_name",
    }
    rows = [
        {k: _cell(r, k) for k in all_keys}
        for r in ws.iter_rows(min_row=header_row + 1, values_only=True)
        if r and _cell(r, "student_nid")
    ]
    wb.close()
    return rows


def _load_ministry_caches(school: Any, year: str, all_nids: set[str]) -> dict[str, Any]:
    """يحمّل كلَّ ما يُحتمل تكرارُه عبر صفوف الاستيراد في فهارس ذاكرةٍ مرّةً
    واحدة — راجع تعليق الأداء في `process_ministry_registry_import`."""
    from clinic.models import HealthRecord
    from core.models import (
        ClassGroup,
        CustomUser,
        Membership,
        ParentStudentLink,
        Profile,
        StudentEnrollment,
    )

    return {
        "users": {u.national_id: u for u in CustomUser.objects.filter(national_id__in=all_nids)},
        "class_groups": {
            (cg.grade, cg.section): cg
            for cg in ClassGroup.objects.filter(school=school, academic_year=year, is_active=True)
        },
        "memberships": (
            set(Membership.objects.filter(school=school).values_list("user_id", "role_id"))
            if school
            else set()
        ),
        "enrollments": (
            {
                e.student_id: e
                for e in StudentEnrollment.objects.filter(
                    class_group__school=school, class_group__academic_year=year, is_active=True
                ).select_related("class_group")
            }
            if school
            else {}
        ),
        "health": {
            h.student_id: h for h in HealthRecord.objects.filter(student__national_id__in=all_nids)
        },
        "profiles": {p.user_id: p for p in Profile.objects.filter(user__national_id__in=all_nids)},
        "links": (
            {
                (link.parent_id, link.student_id): link
                for link in ParentStudentLink.objects.filter(school=school)
            }
            if school
            else {}
        ),
    }


def _sync_student_profile(student: Any, birth_date: Any, profiles_cache: dict[Any, Any]) -> None:
    """upsert لتاريخ ميلاد الطالب من ذاكرةٍ مُحمَّلةٍ مسبقاً — لا كتابة إن لم يتغيّر."""
    from core.models import Profile

    if not birth_date:
        return
    profile = profiles_cache.get(student.id)
    if profile is None:
        profile = Profile(user=student, birth_date=birth_date)
        profile.save()
        profiles_cache[student.id] = profile
    elif profile.birth_date != birth_date:
        profile.birth_date = birth_date
        profile.save(update_fields=["birth_date"])


def _ensure_membership(
    user: Any, school: Any, role: Any, memberships_cache: set[tuple[Any, Any]]
) -> None:
    """ينشئ العضويّة إن لم تكن موجودةً في الفهرس المحمَّل مسبقاً — بلا استعلامٍ لكلّ سطر."""
    from core.models import Membership

    key = (user.id, role.id)
    if key not in memberships_cache:
        Membership.objects.create(user=user, school=school, role=role, is_active=True)
        memberships_cache.add(key)


def _process_ministry_student_row(
    row_num: int,
    cell: dict[str, str],
    *,
    school: Any,
    year: str,
    student_role: Any,
    caches: dict[str, Any],
    issued: list[dict],
    stats: dict[str, Any],
) -> Any | None:
    """يعالج شطرَ الطالب من صفٍّ واحد: upsert + ملفٌّ شخصيّ + عضويّة + شعبة +
    سجلٌّ صحّيّ. يُعيد كائنَ الطالب، أو None إن تُجووز السطرُ (اسمٌ فارغ)."""
    student_nid = cell["student_nid"]
    full_name = cell["full_name"]
    if not full_name:
        stats["errors"].append(f"سطر {row_num}: اسم الطالب {student_nid} فارغ — تجاوز")
        return None

    birth_date = _parse_ministry_date(cell["birth_date_raw"])
    uses_bus_raw = cell["uses_bus_raw"]
    student, s_created = _upsert_user_from_registry(
        student_nid,
        users_cache=caches["users"],
        full_name=full_name,
        phone=_first_phone(cell["phone"]),
        email=cell["email"],
        nationality=cell["nationality"],
        municipality=cell["municipality"],
        region=cell["region"],
        employer_sector="",
        employer_name="",
        kahramaa_number=cell["kahramaa_number"],
        uses_bus=uses_bus_raw in ("نعم", "Yes", "yes", "true", "True"),
        role_label="طالب",
        issued=issued,
    )
    stats["students_created" if s_created else "students_existed"] += 1

    _sync_student_profile(student, birth_date, caches["profiles"])

    if school:
        _ensure_membership(student, school, student_role, caches["memberships"])
        grade_raw, section = _split_ministry_class(cell["class_combined"])
        _sync_student_class_group(
            student,
            school,
            year,
            grade_raw,
            section,
            class_groups=caches["class_groups"],
            enrollments_cache=caches["enrollments"],
            stats=stats,
            row_num=row_num,
        )

    _sync_health_record(
        student,
        cell["health_center_name"],
        cell["health_card_number"],
        cell["hamad_hospital_number"],
        health_cache=caches["health"],
    )
    return student


def _process_ministry_parent_row(
    cell: dict[str, str],
    *,
    student: Any,
    school: Any,
    parent_role: Any,
    caches: dict[str, Any],
    issued: list[dict],
    stats: dict[str, Any],
) -> None:
    """يعالج شطرَ وليّ الأمر من صفٍّ واحد: upsert + عضويّة + رابطُ قرابة.
    لا شيءَ إن كان عمودُ رقم وليّ الأمر فارغاً."""
    from core.models import ParentStudentLink

    parent_nid = cell["parent_nid"]
    if not parent_nid:
        return

    parent, p_created = _upsert_user_from_registry(
        parent_nid,
        users_cache=caches["users"],
        full_name=cell["parent_name"],
        phone=_first_phone(cell["parent_phone"]),
        email=cell["parent_email"],
        nationality=cell["parent_nationality"],
        municipality="",
        region="",
        employer_sector=cell["parent_employer_sector"],
        employer_name=cell["parent_employer_name"],
        kahramaa_number="",
        role_label="ولي أمر",
        issued=issued,
    )
    stats["parents_created" if p_created else "parents_existed"] += 1

    if not school:
        return

    _ensure_membership(parent, school, parent_role, caches["memberships"])

    relation = _IMPORT_RELATION_MAP.get(cell["relation_raw"], "father")
    links_cache = caches["links"]
    link_key = (parent.id, student.id)
    link = links_cache.get(link_key)
    if link is None:
        ParentStudentLink.objects.create(
            parent=parent,
            student=student,
            school=school,
            relationship=relation,
            is_primary=True,
            can_view_grades=True,
            can_view_attendance=True,
        )
        links_cache[link_key] = True
        stats["links_created"] += 1
    elif link is not True and link.relationship != relation:
        link.relationship = relation
        link.save(update_fields=["relationship"])


def process_ministry_registry_import(
    uploaded_file: Any, school: Any, year: str, header_row: int, cols: dict[str, int]
) -> dict[str, Any]:
    """يستورد سجلّ القيد الوزاريّ (26 عموداً، W-028) — upsert مباشر فوق الحقول
    التشغيليّة، ومصدرُ مركز البيانات الوطنيّ يغلب دائماً عند التعارض.

    [أداء] الصفُّ الواحد كان يُجري نحو 15-20 استعلاماً (get_or_create لكلّ
    علاقة) فاستغرق استيرادُ 734 صفاً نحو دقيقتين — شكوى المالك 2026-10-01.
    فصار كلُّ ما يُحتمل تكراره عبر الصفوف (مستخدمون، شُعَب، قيودٌ، سجلّاتٌ
    صحّيّة، روابطُ قرابة، عضويّات) يُحمَّل مرّةً واحدةً قبل الحلقة في فهارس
    ذاكرةٍ (`_load_ministry_caches`)، ومعالجةُ كلّ صفٍّ مقسومةٌ على دالّتَي
    الطالب ووليّ الأمر (`_process_ministry_student_row`/`_parent_row`) — فلا
    يبقى في هذه الدالّة إلّا التنسيق.
    """
    from core.models import Role

    roles = {r.name: r for r in Role.objects.all()}
    student_role = roles.get("student")
    parent_role = roles.get("parent")
    if not student_role or not parent_role:
        return {
            "success": False,
            "errors": ["الأدوار الأساسية (student/parent) غير موجودة — شغّل seed_data أولاً."],
        }

    rows = _read_ministry_rows(uploaded_file, header_row, cols)

    all_nids: set[str] = set()
    for r in rows:
        all_nids.add(r["student_nid"])
        if r["parent_nid"]:
            all_nids.add(r["parent_nid"])

    caches = _load_ministry_caches(school, year, all_nids)

    stats: dict[str, Any] = {
        "students_created": 0,
        "students_existed": 0,
        "parents_created": 0,
        "parents_existed": 0,
        "enrollments_created": 0,
        "enrollments_transferred": 0,
        "links_created": 0,
        "errors": [],
    }
    issued: list[dict] = []

    with transaction.atomic():
        for row_num, cell in enumerate(rows, start=header_row + 1):
            student = _process_ministry_student_row(
                row_num,
                cell,
                school=school,
                year=year,
                student_role=student_role,
                caches=caches,
                issued=issued,
                stats=stats,
            )
            if student is None:
                continue
            _process_ministry_parent_row(
                cell,
                student=student,
                school=school,
                parent_role=parent_role,
                caches=caches,
                issued=issued,
                stats=stats,
            )

    return {
        "success": True,
        "total_rows": stats["students_created"] + stats["students_existed"],
        "students_created": stats["students_created"],
        "students_existed": stats["students_existed"],
        "parents_created": stats["parents_created"],
        "parents_existed": stats["parents_existed"],
        "enrollments_created": stats["enrollments_created"],
        "enrollments_transferred": stats["enrollments_transferred"],
        "links_created": stats["links_created"],
        "error_count": len(stats["errors"]),
        "errors": stats["errors"][:20],
        "credentials": issued,
    }


def process_student_import(uploaded_file: Any, school: Any, year: Any) -> dict[str, Any]:
    """
    يقرأ ملف Excel ويستورد الطلاب + أولياء الأمور.
    يُعيد dict بإحصائيات النتيجة + قائمة الأخطاء.

    يُحاول أوّلاً التعرّفَ على قالب سجلّ القيد الوزاريّ (W-028 — رأسٌ بعموده
    الأوّل «الرقم» خلال أوّل عشرة صفوف) وتفويضَ المعالجة لـ
    `process_ministry_registry_import`، وهو القالبُ المعتمَد منذ 2026-10-01؛
    فإن لم يكن كذلك يرجع إلى القالب المبسَّط القديم (11 عموداً) للتوافق مع
    ملفّاتٍ محليّةٍ قد تبقى مستعملةً.
    """
    import openpyxl

    from core.models import Membership, Role

    detect_wb = openpyxl.load_workbook(uploaded_file, read_only=True, data_only=True)
    located = _locate_ministry_header(detect_wb.active)
    detect_wb.close()
    if located:
        header_row, cols = located
        uploaded_file.seek(0)
        return process_ministry_registry_import(uploaded_file, school, year, header_row, cols)

    roles = {r.name: r for r in Role.objects.all()}
    student_role = roles.get("student")
    parent_role = roles.get("parent")

    if not student_role or not parent_role:
        return {
            "success": False,
            "errors": ["الأدوار الأساسية (student/parent) غير موجودة — شغّل seed_data أولاً."],
        }

    wb = openpyxl.load_workbook(uploaded_file, read_only=True, data_only=True)
    ws = wb.active

    # فلترة صفوف البيانات الصالحة (تجاوز الرأس والتعليقات)
    data_rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        first = str(row[0]).strip()
        if first.startswith("#") or not first[0].isdigit():
            continue
        data_rows.append(row)

    stats: dict[str, Any] = {
        "students_created": 0,
        "students_existed": 0,
        "parents_created": 0,
        "parents_existed": 0,
        "enrollments_created": 0,
        "links_created": 0,
        "errors": [],
    }
    # ورقةُ الاعتماد: في الذاكرة وحدَها، تُعرض في استجابة هذا الطلب ثمّ تزول.
    issued: list[dict] = []

    with transaction.atomic():
        for i, raw_row in enumerate(data_rows, start=2):
            fields = _parse_import_row(raw_row)

            if not fields["student_nid"]:
                stats["errors"].append(f"سطر {i}: الرقم الشخصي فارغ — تجاوز")
                continue
            if not fields["full_name"]:
                stats["errors"].append(f"سطر {i}: اسم الطالب {fields['student_nid']} فارغ — تجاوز")
                continue

            # ── الطالب ──────────────────────────────────────────────
            student, s_created = _upsert_user(
                fields["student_nid"],
                fields["full_name"],
                fields["phone"],
                fields["email"],
                role_label="طالب",
                issued=issued,
            )
            stats["students_created" if s_created else "students_existed"] += 1

            if school:
                Membership.objects.get_or_create(
                    user=student,
                    school=school,
                    role=student_role,
                    defaults={"is_active": True},
                )
                if _enroll_student_in_class(
                    student, school, fields["grade_raw"], fields["section"], stats, i
                ):
                    stats["enrollments_created"] += 1

            # ── ولي الأمر (اختياري) ──────────────────────────────────
            if not fields["parent_nid"]:
                continue

            parent, p_created = _upsert_user(
                fields["parent_nid"],
                fields["parent_name"],
                fields["parent_phone"],
                fields["parent_email"],
                role_label="ولي أمر",
                issued=issued,
            )
            stats["parents_created" if p_created else "parents_existed"] += 1

            if school:
                Membership.objects.get_or_create(
                    user=parent,
                    school=school,
                    role=parent_role,
                    defaults={"is_active": True},
                )
                if _link_parent_to_student(parent, student, school, fields["relation_raw"], stats):
                    stats["links_created"] += 1

    return {
        "success": True,
        "total_rows": len(data_rows),
        "students_created": stats["students_created"],
        "students_existed": stats["students_existed"],
        "parents_created": stats["parents_created"],
        "parents_existed": stats["parents_existed"],
        "enrollments_created": stats["enrollments_created"],
        "links_created": stats["links_created"],
        "error_count": len(stats["errors"]),
        "errors": stats["errors"][:20],
        # كلماتُ مرورٍ نصّيّةٌ — للعرض في استجابةٍ واحدةٍ فقط؛ لا تُخزَّن ولا تُسجَّل.
        "credentials": issued,
    }


def _audit_credentials_issued(user: Any, school: Any, count: int) -> None:
    """يترك أثراً بأنّ كلماتِ مرورٍ صدرت — **العددُ** لا الكلمات ولا أصحابُها."""
    from core.models.audit import AuditLog

    AuditLog.objects.create(
        school=school,
        user=user,
        action="update",
        model_name="other",
        object_id="",
        object_repr=f"استيرادُ الطلاب: صدرت {count} كلمةَ مرورٍ أوّليّة"[:300],
        changes={
            "event": "import_initial_passwords_issued",
            "count": count,
            "must_change_password": True,
        },
    )


def import_result_context(user: Any, school: Any, result: dict[str, Any]) -> dict:
    """ما يُضاف إلى سياق الصفحة من نتيجة الاستيراد: ورقةُ الاعتماد وعدّادُ الأخطاء.

    ورقةُ الاعتماد تُعرض في هذه الاستجابة وحدَها؛ وصفحةٌ للمسجَّل بلا تخزين
    (`PrivateHtmlNoStoreMiddleware`) فلا تبقى في المتصفّح.
    """
    extra: dict = {}
    if result.get("credentials"):
        extra["credentials"] = result["credentials"]
        try:
            _audit_credentials_issued(user, school, len(result["credentials"]))
        except Exception:  # noqa: BLE001 — فشلُ الأثر لا يُضيّع ورقةً لا تُعاد
            logger.exception("تعذّر تسجيل أثر إصدار كلمات المرور")
    # الأخطاءُ تُعرض عشرين، وما بقي يُقال عدداً؛ والكهرمانيُّ حين يوجد خطأ
    # (العتبةُ التي كانت في القالب: أكبرُ من صفر).
    error_count = result.get("error_count", len(result.get("errors", [])))
    extra["errors_more"] = max(0, error_count - len(result.get("errors", [])))
    extra["errors_tone"] = "amber" if error_count > 0 else "green"
    return extra


def count_active_students(school: Any) -> int:
    """عددُ الطلاب الفاعلين في المدرسة (عضويّةٌ بدور student)."""
    from core.models import Membership, Role

    student_role = Role.objects.filter(name="student").first()
    if not (school and student_role):
        return 0
    return Membership.objects.filter(school=school, role=student_role, is_active=True).count()


# ── إعادةُ تعيين كلمات مرور المستخدمين (فنّي تقنية المعلومات) ────────────


def school_users(school: Any, q: str = "") -> Any:
    """مستخدمو مدرسةٍ للبحث والعرض — `search_simple` عند وجود استعلام."""
    from core.models import CustomUser

    people = CustomUser.objects.filter(memberships__school=school).distinct().order_by("full_name")
    if not q:
        return people
    # django-stubs لا يعرف UserQuerySet خلف CustomUserManager — search_simple موجودةٌ فعلاً (core/querysets.py).
    return people.search_simple(q)  # type: ignore[attr-defined]


def reset_user_password(*, school: Any, target_id: Any, actor: Any) -> tuple[Any, str]:
    """يعيد تعيين كلمةَ مرور مستخدمٍ في مدرسة الفاعل — كلمةٌ عشوائيّة (لا حقلَ حرّ)،
    تُلزمه بتغييرها عند الدخول التالي، وتُسجَّل في AuditLog بلا القيمة نفسها.

    يرفع `Http404` إن لم يكن المستخدَمُ عضواً في مدرسة الفاعل — لا تسريبَ بين المدارس.
    """
    from django.shortcuts import get_object_or_404

    from core.initial_passwords import make_initial_password
    from core.models import AuditLog, CustomUser

    target = get_object_or_404(
        CustomUser.objects.filter(memberships__school=school).distinct(), id=target_id
    )
    new_password = make_initial_password()
    with transaction.atomic():
        target.set_password(new_password)
        target.must_change_password = True
        target.save(update_fields=["password", "must_change_password"])
        AuditLog.objects.create(
            school=school,
            user=actor,
            action="update",
            model_name="CustomUser",
            object_id=str(target.id),
            object_repr=f"إعادة تعيين كلمة مرور: {target.full_name}"[:300],
        )
    return target, new_password

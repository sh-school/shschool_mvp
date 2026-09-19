"""
governance/views_media.py
خدمة الملفات المُخزَّنة في قاعدة البيانات (DatabaseStorage) — بتفويض fail-closed.

لكل ملف نُحدِّد السجلّ المالك ومدرسته، ونتحقّق أن المستخدم من نفس المدرسة وله الدور
المناسب (أو أنه مالك السجلّ). يمنع IDOR/BOLA عبر تعداد/تخمين أسماء الملفات.
SVG/HTML لا يُعرَض inline (دفاع XSS مخزّن).

وملفّاتُ الطلبة (عذرُ التأخّر، ومستندُ عذر الغياب، ومرفقُ النشاط) تمرّ بعد الدور على نطاق
الجناح: المقيَّدُ بجناحه لا يفتح ملفَّ طالبٍ من غير جناحه، ولو كان دورُه يفتح النوعَ نفسَه
(قرارُ 2026-09-15: «المشرفُ لجناحه فقط»). والنطاقُ واحدٌ في `wings/scope.py`.
"""

import mimetypes
from urllib.parse import quote

from django.contrib.auth.views import redirect_to_login
from django.http import Http404, HttpResponse

from core.permissions import expand_roles

# أنواع آمنة للعرض داخل المتصفّح؛ ما عداها يُجبَر على التنزيل
_INLINE_SAFE = {"application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp"}
# أنواع تُنفَّذ في المتصفّح — تُحيَّد دائماً
_NEVER_INLINE = {"image/svg+xml", "text/html", "application/xhtml+xml", "text/xml"}


def _resolve_file_access(name):
    """يُعيد (school_id, owner_user_id, allowed_roles, student_owned) للملف، أو None إن لم يُعرَف مالكه.

    `student_owned`: الملفُّ ملفُّ طالبٍ (`owner_user_id` هو الطالب)، فيُسأل عنه نطاقُ الجناح.
    """
    # استيراد كسول لتفادي الدورات
    from core.models import School
    from core.permissions import (
        LIBRARY_FULL,
        LIBRARY_VIEW,
        QUALITY_VIEW,
        STUDENT_AFFAIRS_VIEW,
        STUDENT_FOLLOW_UP,
        WING_DAY_RECORD,
    )
    from library.models import LibraryBook
    from operations.models import AbsenceExcuse, StudentAttendance
    from quality.models import ProcedureEvidence
    from staff_affairs.models import LeaveRequest
    from student_affairs.models import StudentActivity

    # مرفقات الإجازات قد تحوي تقارير طبية حسّاسة → قيادة المدرسة فقط (عدا المالك)
    leave_roles = {"principal", "vice_admin"}

    resolvers = (
        # عذرُ التأخّر الصباحيّ: رصدُه من عمل المشرف (الدليل 2026 م 3.4.2.2) — لجناحه.
        (
            StudentAttendance,
            "excuse_file",
            lambda o: (o.school_id, o.student_id, STUDENT_AFFAIRS_VIEW | STUDENT_FOLLOW_UP, True),
        ),
        # مستندُ عذر الغياب: من يرصد في الأجنحة ومن يرى شؤونَ الطلبة — والطالبُ صاحبُه.
        (
            AbsenceExcuse,
            "document",
            lambda o: (o.school_id, o.student_id, STUDENT_AFFAIRS_VIEW | WING_DAY_RECORD, True),
        ),
        (LeaveRequest, "attachment", lambda o: (o.school_id, o.staff_id, leave_roles, False)),
        (
            ProcedureEvidence,
            "file",
            lambda o: (o.procedure.school_id, o.uploaded_by_id, QUALITY_VIEW, False),
        ),
        (
            StudentActivity,
            "attachment",
            lambda o: (o.school_id, o.student_id, STUDENT_AFFAIRS_VIEW, True),
        ),
        (
            LibraryBook,
            "digital_file",
            lambda o: (o.school_id, None, LIBRARY_VIEW | LIBRARY_FULL, False),
        ),
        # الشعار: أي مستخدم مُصادَق من نفس المدرسة (allowed_roles=None)
        (School, "logo", lambda o: (o.id, None, None, False)),
    )
    for model, field, extract in resolvers:
        obj = model.objects.filter(**{field: name}).first()
        if obj is not None:
            return extract(obj)
    return None


def _authorize(request, access):
    """fail-closed: يرفع Http404 إن لم يُسمَح؛ يُعيد None إن سُمِح؛ أو ردّ تحويل للدخول."""
    school_id, owner_user_id, allowed_roles, student_owned = access

    user = request.user
    if not user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    if user.is_superuser:
        return None

    user_school = user.get_school()
    if user_school is None or user_school.id != school_id:
        raise Http404  # عزل المدرسة
    is_owner = owner_user_id is not None and owner_user_id == user.id
    role_ok = allowed_roles is None or user.get_role() in expand_roles(set(allowed_roles))
    if not (is_owner or role_ok):
        raise Http404  # ليس المالك ولا له الدور المناسب
    if student_owned and not is_owner:
        # ملفُّ طالبٍ خارج الجناح: الدورُ يفتح النوعَ، والنطاقُ يحصره في طلبة جناحه.
        # وغيرُ المقيَّد لا يُنفَّذ له استعلامٌ هنا.
        from wings.scope import student_scope

        student_scope(user, user_school).require_student(owner_user_id)
    return None


def serve_db_file(request, name):
    """يُقدّم ملفاً مُخزَّناً في القاعدة بعد تفويض fail-closed."""
    from core.models import StoredFile

    access = _resolve_file_access(name)
    if access is None:
        raise Http404  # ملف يتيم/غير معروف المالك → لا يُقدَّم

    deny = _authorize(request, access)
    if deny is not None:
        return deny  # تحويل لتسجيل الدخول

    sf = StoredFile.objects.filter(name=name).first()
    if sf is None:
        raise Http404

    content_type = sf.content_type or mimetypes.guess_type(name)[0] or "application/octet-stream"
    disposition = "inline" if content_type in _INLINE_SAFE else "attachment"
    if content_type in _NEVER_INLINE:
        content_type = "application/octet-stream"
        disposition = "attachment"

    response = HttpResponse(bytes(sf.content), content_type=content_type)
    filename = name.rsplit("/", 1)[-1]
    response["Content-Disposition"] = f"{disposition}; filename*=UTF-8''{quote(filename)}"
    response["Content-Length"] = sf.size or len(bytes(sf.content))
    response["X-Content-Type-Options"] = "nosniff"
    return response

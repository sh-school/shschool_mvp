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
from governance.media_selectors import resolve_file_access, stored_file_named

# أنواع آمنة للعرض داخل المتصفّح؛ ما عداها يُجبَر على التنزيل
_INLINE_SAFE = {"application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp"}
# أنواع تُنفَّذ في المتصفّح — تُحيَّد دائماً
_NEVER_INLINE = {"image/svg+xml", "text/html", "application/xhtml+xml", "text/xml"}


def _authorize(request, access):
    """fail-closed: يرفع Http404 إن لم يُسمَح؛ يُعيد None إن سُمِح؛ أو ردّ تحويل للدخول."""
    school_id, owner_user_id, allowed_roles, student_owned = access

    user = request.user
    if not user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    if user.is_superuser:
        return None

    user_school = request.school
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
    access = resolve_file_access(name)
    if access is None:
        raise Http404  # ملف يتيم/غير معروف المالك → لا يُقدَّم

    deny = _authorize(request, access)
    if deny is not None:
        return deny  # تحويل لتسجيل الدخول

    sf = stored_file_named(name)
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

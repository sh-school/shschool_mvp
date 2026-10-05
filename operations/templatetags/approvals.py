"""وسمُ «اعتمادُ الكلّ (N)» — مصدرٌ واحدٌ يُرسَم به الزرُّ في كلّ لوحة غيابٍ للمشرف (شبكةُ الشعبة، تقريرُ غياب اليوم، صفحةُ الاعتماد).

أمرُ المالك 2026-10-04: الزرُّ **في لوحة الغياب نفسِها** لا في صفحةٍ جانبيّة. والعددُ = كلُّ ما في طابور المستخدم (كلُّ الشعب والحصص)؛ ولا يظهر
لمن لا شيءَ ينتظر قرارَه أو لا يملك الاعتمادَ (الطابورُ فارغٌ له).

**لا نموذجَ داخل نموذج** (واقعةُ 2026-10-05): في شبكة الشعبة يقع الزرُّ داخل نموذج التثبيت، والمتصفّحُ يُسقط وسمَ `<form>` الداخليّ فيُشغّل الزرُّ
**التثبيتَ** لا الاعتماد. فهناك يُرسم الزرُّ بـ`detached=True` (`form="approve-all-form"`) والنموذجُ المستقلُّ بعد نهاية نموذج التثبيت (`approve_all_form`).
"""

from django import template

from operations.services.attendance_teacher import TeacherAttendanceService

register = template.Library()


def _count(request) -> int:
    """عددُ ما ينتظر قرارَ المستخدم — يُحسب مرّةً في الطلب (الزرُّ والنموذجُ المستقلُّ يشتركان)."""
    cached = getattr(request, "_approve_all_count", None)
    if cached is not None:
        return int(cached)
    user = getattr(request, "user", None)
    school = getattr(request, "school", None)
    count = 0
    if user is not None and user.is_authenticated and school is not None:
        count = len(TeacherAttendanceService.queue(user, school))
    request._approve_all_count = count
    return count


@register.inclusion_tag("attendance/partials/approve_all.html", takes_context=True)
def approve_all_button(context, detached=False):
    request = context.get("request")
    return {
        "count": _count(request) if request else 0,
        "next": request.get_full_path() if request else "",
        "request": request,
        "detached": detached,
    }


@register.inclusion_tag("attendance/partials/approve_all_form.html", takes_context=True)
def approve_all_form(context):
    request = context.get("request")
    return {
        "count": _count(request) if request else 0,
        "next": request.get_full_path() if request else "",
        "request": request,
    }

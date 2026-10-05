"""وسمُ «اعتمادُ الكلّ (N)» — مصدرٌ واحدٌ يُرسَم به الزرُّ في كلّ لوحة غيابٍ للمشرف (شبكةُ الشعبة، تقريرُ غياب اليوم، صفحةُ الاعتماد).

أمرُ المالك 2026-10-04: الزرُّ **في لوحة الغياب نفسِها** لا في صفحةٍ جانبيّة. والعددُ = كلُّ ما في طابور المستخدم (كلُّ الشعب والحصص)؛ ولا يظهر
لمن لا شيءَ ينتظر قرارَه أو لا يملك الاعتمادَ (الطابورُ فارغٌ له).
"""

from django import template

from operations.services.attendance_teacher import TeacherAttendanceService

register = template.Library()


@register.inclusion_tag("attendance/partials/approve_all.html", takes_context=True)
def approve_all_button(context):
    request = context.get("request")
    user = getattr(request, "user", None)
    school = getattr(request, "school", None)
    count = 0
    if user is not None and user.is_authenticated and school is not None:
        count = len(TeacherAttendanceService.queue(user, school))
    return {"count": count, "next": request.get_full_path() if request else "", "request": request}

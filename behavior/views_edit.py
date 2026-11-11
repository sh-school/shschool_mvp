"""behavior/views_edit.py — تعديلُ مخالفةٍ سلوكيةٍ مسجَّلة من ملفّ الطالب (بلاغ 5D5D، W-20261111-005).

القاعدةُ في `edit_services.can_edit_infraction` (المسجِّلُ، والقائمةُ المغلقة، والمشرفُ لجناحه)
والكتابةُ والتدقيقُ في `edit_services.update_infraction`؛ والعرضُ يربطهما بالنموذج.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from behavior import edit_services
from behavior.forms import InfractionEditForm
from behavior.selectors import editable_categories, school_infraction_or_404
from behavior.services import audit_infraction_read
from core.capabilities import capability_required
from core.permissions import forbidden_page
from wings.scope import student_scope_for


@login_required
@capability_required("behavior.view")
def infraction_edit(request, infraction_id):
    """يعدّل الوصفَ والمخالفةَ والإجراءَ والتاريخ لمخالفةٍ في مدرسة الطلب؛ وغيرُها 404."""
    infraction = school_infraction_or_404(request.school, infraction_id)
    scope = student_scope_for(request)
    if not edit_services.can_edit_infraction(request.user, infraction, scope):
        return forbidden_page(request, "لا يحقّ لك تعديل هذه المخالفة.")

    locked = edit_services.level_locked_by_committee(infraction)
    categories = editable_categories(infraction, locked)
    form = InfractionEditForm(
        request.POST or None, role=request.user.get_role(), infraction=infraction
    )
    if request.method == "POST":
        if not form.is_valid():
            for errs in form.errors.values():
                for err in errs:
                    messages.error(request, err)
        else:
            saved, text = edit_services.save_infraction_edit(
                infraction=infraction,
                editor=request.user,
                scope=scope,
                data=form.cleaned_data,
                categories=categories,
                request=request,
            )
            (messages.success if saved else messages.error)(request, text)
            if saved:
                return redirect("behavior:student_profile", student_id=infraction.student_id)

    audit_infraction_read(request, infraction)
    return render(
        request,
        "behavior/infraction_edit.html",
        {
            "infraction": infraction,
            "categories": categories,
            "action_choices": [c for c in form.fields["disciplinary_action_type"].choices if c[0]],
            "level_locked": locked,
        },
    )

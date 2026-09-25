from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils import timezone

from core.capabilities import capability_required, has_capability
from core.dashboard_presentation import present
from core.dashboard_selectors import (
    ADMIN_OPS_ROLES,
    DIRECTOR_ROLES,
    DIRECTOR_TITLES,
    SERVICE_ROLES,
    SPECIALIST_SOCIAL_ROLES,
    TEACHER_ROLES,
    THERAPIST_ROLES,
    TRANSPORT_ROLES,
    get_activities_ctx,
    get_admin_ops_ctx,
    get_director_ctx,
    get_service_ctx,
    get_specialist_social_ctx,
    get_student_ctx,
    get_teacher_ctx,
    get_therapist_ctx,
    get_transport_ctx,
    supervisor_record_ctx,
)
from core.models.academic import Wing


@login_required
@capability_required("dashboard.open")
def dashboard(request):
    """لوحة التحكم الرئيسية — موزّع يعيد التوجيه أو يبني السياق حسب الدور.

    كلُّ منطق جلب البيانات في `core/dashboard_selectors.py` (طبقةُ قراءة —
    راجعها لسبب الفصل: حارس الطبقات يسقف كلّ دالّةٍ في ملفّ عروضٍ بستّين
    سطراً وخمسة استدعاءات ORM، وكانت هذه الدالّة أثقل عرضٍ في المشروع)."""
    user = request.user
    school = user.get_school()
    role = user.get_role()

    if not school:
        return HttpResponseForbidden("<h2 dir='rtl'>لم يتم تعيينك في أي مدرسة</h2>")

    # ولي الأمر → بوابته المخصصة
    if role == "parent":
        return redirect("parent_dashboard")

    # بتوقيت المدرسة لا UTC: بين 21:00 و00:00 UTC يختلف اليومان، فكان تكليفُ بديلٍ
    # يبدأ «اليوم» (بتوقيت قطر) لا يُرى في اللوحة (سقوطُ البوّابة عند منتصف الليل 2026-09-14).
    today = timezone.localdate()
    ctx = {"today": today, "school": school}

    if role == "student":
        ctx.update(get_student_ctx(user, school, today))
    elif user.is_superuser or role in DIRECTOR_ROLES:
        ctx.update(get_director_ctx(school, today))
        # العنوانُ باسم صاحب اللوحة: النائبُ كان يرى «لوحة تحكم المدير».
        ctx["dashboard_title"] = DIRECTOR_TITLES.get(role, "لوحة تحكم المدير")
        if has_capability(user, "wings.excuse_after_deadline"):
            # أعذارٌ أرسلها المشرفون بعد مهلة العودة — تنتظر النائبَ (قرارُ 2026-09-14).
            from operations.models import AbsenceExcuse

            ctx["pending_excuses"] = AbsenceExcuse.objects.filter(
                school=school, status="pending"
            ).count()
    elif role in TEACHER_ROLES:
        ctx.update(get_teacher_ctx(user, school, today, role))
    elif role in SPECIALIST_SOCIAL_ROLES:
        ctx.update(get_specialist_social_ctx(user, school, today))
    elif role in THERAPIST_ROLES:
        ctx.update(get_therapist_ctx(user, school, today))
    elif role == "activities_coordinator":
        ctx.update(get_activities_ctx(user, school, today))
    elif role in ADMIN_OPS_ROLES:
        ctx.update(get_admin_ops_ctx(user, school, today, role))
    elif role in TRANSPORT_ROLES:
        ctx.update(get_transport_ctx(user, school, today))
    elif role in SERVICE_ROLES:
        ctx.update(get_service_ctx(user, school, today, role))
    elif Wing.is_held_by(user, today):
        # بديلُ الجناح من ملاحظي الطلبة وعمّال الخدمات (قرارُ المدير): لا لوحةَ لدوره،
        # ولوحتُه يومَ تكليفه رصدُ جناحه — لا «لم تُفعَّل صلاحيّاتُك».
        ctx["view_type"] = "wing_holder"
        ctx.update(supervisor_record_ctx(user, school, today))
    else:
        ctx["view_type"] = "other"

    ctx.update(present(ctx))
    return render(request, "dashboard/main.html", ctx)

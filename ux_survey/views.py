"""شاشاتُ الاستبانة: النموذج، التأجيل والإغلاق، لوحةُ التجميع، ومراجعةُ النصوص الحرّة (للمطوّر المالك وحدَه)."""

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core.capabilities import capability_required
from ux_survey import services
from ux_survey.forms import SurveyForm
from ux_survey.groups import GROUPS
from ux_survey.models import SurveyResponse

LABELS = {
    "sus_easy": "أجد أن المنصة سهلة الاستخدام",
    "sus_slow": "أحتاج وقتًا طويلًا حتى أنجز مهمتي المعتادة",
    "sus_confident": "أشعر بالثقة وأنا أستخدمها",
    "sus_remember": "لو لم أستخدمها كثيرًا لوجدتُ صعوبة في تذكر خطواتها",
}


@capability_required(services.RESPOND)
def respond(request):
    if not services.is_eligible(request.user):
        messages.info(request, "لا استبانةَ مفتوحةً لك الآن.")
        return redirect("dashboard")
    form = SurveyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.submit(request.user, form.cleaned_data)
        except services.SurveyError as exc:
            messages.info(request, str(exc))
        else:
            messages.success(request, "شكرًا لك — سُجّلت إجابتُك دون ربطها باسمك.")
        return redirect("dashboard")
    return render(request, "ux_survey/form.html", {"form": form, "sus_labels": LABELS})


@capability_required(services.RESPOND)
@require_POST
def snooze(request):
    services.snooze(request.user)
    return redirect(request.POST.get("next") or "dashboard")


@capability_required(services.RESPOND)
@require_POST
def close(request):
    services.close(request.user)
    return redirect(request.POST.get("next") or "dashboard")


@capability_required(services.DASHBOARD)
def dashboard(request):
    wave = services.active_wave()
    is_owner = request.user.get_role() == "platform_developer"
    result = services.aggregate(wave)
    return render(
        request,
        "ux_survey/dashboard.html",
        {
            "wave": wave,
            "result": result,
            "labels": LABELS,
            "min_group": services.MIN_GROUP,
            "texts": services.texts_for_dashboard(wave) if is_owner else {},
            "is_owner": is_owner,
            "pending": len(services.pending_review(wave)) if is_owner else 0,
        },
    )


@capability_required(services.DASHBOARD)
def review(request):
    if request.user.get_role() != "platform_developer":
        raise PermissionDenied("المراجعةُ للمطوّر المالك وحدَه.")
    wave = services.active_wave()
    if request.method == "POST":
        decisions = {
            key.removeprefix("d_"): int(value)
            for key, value in request.POST.items()
            if key.startswith("d_") and value in ("1", "2")
        }
        done = services.review(request.user, decisions)
        messages.success(request, f"سُجّلت مراجعةُ {done} إجابة.")
        return redirect("ux_survey:review")
    return render(
        request,
        "ux_survey/review.html",
        {"wave": wave, "rows": services.pending_review(wave), "groups": GROUPS},
    )


__all__ = ["respond", "snooze", "close", "dashboard", "review", "SurveyResponse"]

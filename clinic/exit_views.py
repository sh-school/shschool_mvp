"""[CLINIC] W-20261119-003: شاشةُ «بطاقة الخروج» للممرّض والأخصائيّ — وصولُ العيادة ومغادرتُها ووسمُ الخروج المبرَّر.

الكتابةُ في `clinic.exit_services` (فوق `operations.exit_wing`)، والقراءةُ في `clinic.exit_selectors`. لا أسماءَ في السجلّات،
ولا يظهر سببُ الوسم لغير واضعه. الشاشةُ بلا تخزين (`never_cache`): فيها أسماءُ طلبةٍ وحالةٌ صحّيّة.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from clinic.exit_selectors import clinic_exits, marks_set_by
from clinic.exit_services import MOMENTS, excuse_student, press_moment
from clinic.health_access import audit_health_presence
from clinic.selectors import search_students
from core.capabilities import capability_required, has_capability


@login_required
@capability_required("clinic.exit_card")
@never_cache
def exit_card_page(request):
    """الشاشةُ: خارجون إلى العيادة الآن (لمن يملك الكتابةَ الصحّيّة)، وبحثُ طالبٍ لوسمه، ووسومي السارية."""
    school, today = request.school, timezone.localdate()
    term = request.GET.get("q", "")
    moments = has_capability(request.user, "clinic.write")
    exits = clinic_exits(school, today) if moments else []
    audit_health_presence(request, "بطاقة الخروج", [row["student"].pk for row in exits])
    return render(
        request,
        "clinic/exit_card.html",
        {
            "exits": exits,
            "can_clinic_moments": moments,
            "q": term,
            "found": search_students(school, term, user=request.user) if term else [],
            "marks": marks_set_by(school, request.user, today),
            "today": today,
        },
    )


@login_required
@capability_required("clinic.write")
@require_POST
def exit_card_moment(request, pk, step):
    """«وصل العيادة» أو «غادر» بنقرة — الثانيةُ لا تفعل شيئاً. خارجَ مدرسته أو بخطوةٍ مجهولةٍ 404."""
    if step not in MOMENTS:
        raise Http404("خطوةٌ غيرُ معروفة")
    done = press_moment(request.school, pk, step, request.user)
    if done is None:
        raise Http404("بطاقةٌ غيرُ موجودة")
    if not done:
        messages.info(request, "سُجّلت هذه اللحظةُ من قبل أو لا تنطبق على هذه البطاقة.")
    return redirect("clinic:exit_card")


@login_required
@capability_required("clinic.exit_card")
@require_POST
def exit_card_excuse(request):
    """يضع وسمَ «خروجٍ مبرَّرٍ دائم» بمدّة — وطالبٌ خارجَ مدرسته يُرفض بلا كشفِ وجوده."""
    try:
        excuse_student(
            request.school,
            request.user,
            request.POST.get("student", ""),
            request.POST.get("ends_on", ""),
            request.POST.get("reason", ""),
        )
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "وُضع وسمُ الخروج المبرَّر.")
    return redirect("clinic:exit_card")

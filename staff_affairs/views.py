"""
staff_affairs/views.py — شؤون الموظفين
8 views — يتبع أنماط المشروع. الخطوات 3-6 ستملأ تدريجياً.
"""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

from core.permissions import role_required

STAFF_AFFAIRS_MANAGE = {"principal", "vice_admin", "vice_academic", "platform_developer"}


# ═══ الخطوة 3: لوحة التحكم ═══

@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def staff_dashboard(request):
    return HttpResponse("<h1 dir='rtl'>شؤون الموظفين — قيد البناء</h1>")


# ═══ الخطوة 4: سجل الموظفين ═══

@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def staff_list(request):
    return HttpResponse("<h1 dir='rtl'>سجل الموظفين — قيد البناء</h1>")


# ═══ الخطوة 5: ملف الموظف ═══

@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def staff_profile(request, user_id):
    return HttpResponse("<h1 dir='rtl'>ملف الموظف — قيد البناء</h1>")


# ═══ الخطوة 6: الإجازات ═══

@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def leave_list(request):
    return HttpResponse("<h1 dir='rtl'>طلبات الإجازات — قيد البناء</h1>")


@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def leave_request_create(request):
    return HttpResponse("<h1 dir='rtl'>طلب إجازة — قيد البناء</h1>")


@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def leave_detail(request, pk):
    return HttpResponse("<h1 dir='rtl'>تفاصيل الإجازة — قيد البناء</h1>")


@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def leave_review(request, pk):
    return HttpResponse("<h1 dir='rtl'>مراجعة الإجازة — قيد البناء</h1>")


# ═══ الرخص المهنية ═══

@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def licensing_overview(request):
    return HttpResponse("<h1 dir='rtl'>الرخص المهنية — قيد البناء</h1>")

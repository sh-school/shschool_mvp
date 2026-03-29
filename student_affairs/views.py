"""
student_affairs/views.py — شؤون الطلاب
16 view — يتبع أنماط المشروع الموجودة بالضبط.
الخطوات 3-10 ستملأ هذه الـ views تدريجياً.
"""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render

from core.permissions import role_required

# الأدوار المسموح لها بالوصول لشؤون الطلاب
STUDENT_AFFAIRS_MANAGE = {"principal", "vice_admin", "vice_academic", "platform_developer"}
STUDENT_DEACTIVATE = {"principal", "vice_admin", "platform_developer"}


# ═════════════════════════════════════════════════════════════════════
# لوحة شؤون الطلاب — الخطوة 3
# ═════════════════════════════════════════════════════════════════════


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def student_dashboard(request):
    """لوحة شؤون الطلاب — KPIs + روابط سريعة."""
    return HttpResponse("<h1 dir='rtl'>شؤون الطلاب — قيد البناء</h1>", status=200)


# ═════════════════════════════════════════════════════════════════════
# سجل الطلاب — الخطوة 4
# ═════════════════════════════════════════════════════════════════════


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def student_list(request):
    """قائمة الطلاب مع بحث وفلتر."""
    return HttpResponse("<h1 dir='rtl'>سجل الطلاب — قيد البناء</h1>", status=200)


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def student_table_partial(request):
    """HTMX partial — جدول الطلاب للبحث المباشر."""
    return HttpResponse("", status=200)


# ═════════════════════════════════════════════════════════════════════
# إضافة / تعديل / تعطيل — الخطوات 5 + 7
# ═════════════════════════════════════════════════════════════════════


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def student_add(request):
    """إضافة طالب جديد — ينشئ 4 سجلات ذرّياً."""
    return HttpResponse("<h1 dir='rtl'>إضافة طالب — قيد البناء</h1>", status=200)


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def student_edit(request, student_id):
    """تعديل بيانات طالب."""
    return HttpResponse("<h1 dir='rtl'>تعديل طالب — قيد البناء</h1>", status=200)


@login_required
@role_required(STUDENT_DEACTIVATE)
def student_deactivate(request, student_id):
    """تعطيل طالب — is_active=False فقط، لا حذف."""
    return HttpResponse("<h1 dir='rtl'>تعطيل طالب — قيد البناء</h1>", status=200)


# ═════════════════════════════════════════════════════════════════════
# ملف الطالب الشامل — الخطوة 6
# ═════════════════════════════════════════════════════════════════════


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def student_profile(request, student_id):
    """ملف الطالب الشامل — يجمع بيانات من 7 تطبيقات."""
    return HttpResponse("<h1 dir='rtl'>ملف الطالب — قيد البناء</h1>", status=200)


# ═════════════════════════════════════════════════════════════════════
# الانتقالات — الخطوة 8
# ═════════════════════════════════════════════════════════════════════


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def transfer_list(request):
    """قائمة الانتقالات."""
    return HttpResponse("<h1 dir='rtl'>الانتقالات — قيد البناء</h1>", status=200)


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def transfer_create(request):
    """تسجيل طلب انتقال جديد."""
    return HttpResponse("<h1 dir='rtl'>طلب انتقال — قيد البناء</h1>", status=200)


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def transfer_detail(request, pk):
    """تفاصيل طلب انتقال."""
    return HttpResponse("<h1 dir='rtl'>تفاصيل الانتقال — قيد البناء</h1>", status=200)


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def transfer_review(request, pk):
    """مراجعة طلب انتقال — موافقة أو رفض."""
    return HttpResponse("<h1 dir='rtl'>مراجعة الانتقال — قيد البناء</h1>", status=200)


# ═════════════════════════════════════════════════════════════════════
# الحضور والسلوك (ملخصات)
# ═════════════════════════════════════════════════════════════════════


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def attendance_overview(request):
    """ملخص الحضور والغياب — يقرأ من operations."""
    return HttpResponse("<h1 dir='rtl'>ملخص الحضور — قيد البناء</h1>", status=200)


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def behavior_overview(request):
    """ملخص السلوك — يقرأ من behavior."""
    return HttpResponse("<h1 dir='rtl'>ملخص السلوك — قيد البناء</h1>", status=200)


# ═════════════════════════════════════════════════════════════════════
# الأنشطة والإنجازات — الخطوة 9
# ═════════════════════════════════════════════════════════════════════


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def activity_list(request):
    """قائمة الأنشطة والإنجازات."""
    return HttpResponse("<h1 dir='rtl'>الأنشطة — قيد البناء</h1>", status=200)


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def activity_add(request):
    """تسجيل نشاط أو إنجاز جديد."""
    return HttpResponse("<h1 dir='rtl'>إضافة نشاط — قيد البناء</h1>", status=200)


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def activity_edit(request, pk):
    """تعديل نشاط."""
    return HttpResponse("<h1 dir='rtl'>تعديل نشاط — قيد البناء</h1>", status=200)


@login_required
@role_required(STUDENT_AFFAIRS_MANAGE)
def activity_delete(request, pk):
    """حذف نشاط."""
    return HttpResponse("<h1 dir='rtl'>حذف نشاط — قيد البناء</h1>", status=200)

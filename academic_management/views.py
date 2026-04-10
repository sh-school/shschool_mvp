"""
academic_management/views.py — REQ-SH-002
Stub views for the 10 "إدارة الشؤون الأكاديمية" submenu entries.
Each view renders a shared "قيد التطوير" placeholder.
Full features deferred to Phase 2.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

MODULE_NAME = "إدارة الشؤون الأكاديمية"


def _stub_view(request, page_title_ar: str, icon: str = "📚"):
    """Generic stub renderer for academic management pages under construction."""
    return render(
        request,
        "academic_management/stub.html",
        {
            "page_title": page_title_ar,
            "icon": icon,
            "module_name": MODULE_NAME,
        },
    )


@login_required
def evaluations(request):
    return _stub_view(request, "التقييمات والدرجات", "📊")


@login_required
def departments(request):
    return _stub_view(request, "إدارة الأقسام التعليمية", "🏛️")


@login_required
def test_analytics(request):
    return _stub_view(request, "تحليلات الاختبارات", "📈")


@login_required
def workload(request):
    return _stub_view(request, "إسناد الأنصبة", "⚖️")


@login_required
def assignments(request):
    return _stub_view(request, "التكاليف", "📝")


@login_required
def department_reports(request):
    return _stub_view(request, "التقارير الخاصة بالقسم", "📄")


@login_required
def classroom_visits(request):
    return _stub_view(request, "الزيارات الصفية", "👁️")


@login_required
def elearning(request):
    return _stub_view(request, "التعليم الإلكتروني", "💻")


@login_required
def class_performance(request):
    return _stub_view(request, "تقارير الأداء الصفي", "📉")


@login_required
def underperformance(request):
    return _stub_view(request, "إدارة الأداء دون المستوى", "⚠️")

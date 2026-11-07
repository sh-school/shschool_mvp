"""
student_affairs/chronic_views.py — كشفُ اسم الحالة المزمنة من صفحة الطالب (W-20261020-033)
═══════════════════════════════════════════════════════════════════════════════════════
بنقرةٍ مقصودةٍ (POST) تُسجَّل. المنطقُ في `clinic.health_access.reveal_chronic`. والمسارُ هنا لا تحت
`/clinic/` لأنّ بوّابةَ الوسيط تحجب بادئةَ العيادة عن المعلّم.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_POST

from clinic.health_access import reveal_chronic
from core.capabilities import capability_required


@login_required
@capability_required("clinic.chronic_name")
@require_POST
def reveal_chronic_name(request, student_id):
    name = reveal_chronic(request, student_id)
    return render(request, "clinic/partials/_chronic_name.html", {"name": name})

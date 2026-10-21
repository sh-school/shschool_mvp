"""أرشيفُ تقارير الغياب الدوريّة (W-20261020-005 الخطوتان 5 و6).

المستلمون المخوَّلون هم حَمَلةُ `operations.absence_followup_print` (المدير والنائب الإداريّ ومنسّق شؤون الطلبة) كما في
مصفوفة الصلاحيّات — **لا قدرةَ جديدةً ولا تغييرَ صلاحيّة**. والفتحُ والتحديثُ يُدقَّقان بلا أيّ بيانٍ شخصيّ.
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.audit_export import log_export
from core.capabilities import capability_required
from operations.models import AbsenceReportSnapshot

CAPABILITY = "operations.absence_followup_print"
PAGE_SIZE = 60


def _latest_per_report(school: Any, kind: str) -> list[AbsenceReportSnapshot]:
    """أحدثُ نسخةٍ لكلّ (نوع، نطاق، فترة) — الأقدمُ يبقى في الأرشيف ويُرى من صفحة التقرير."""
    seen: set[tuple] = set()
    out: list[AbsenceReportSnapshot] = []
    qs = AbsenceReportSnapshot.objects.filter(school=school)
    if kind:
        qs = qs.filter(kind=kind)
    for snap in qs.order_by("-period_end", "-revision")[: PAGE_SIZE * 4]:
        key = (snap.kind, snap.grade_scope, snap.period_start, snap.period_end)
        if key not in seen:
            seen.add(key)
            out.append(snap)
        if len(out) >= PAGE_SIZE:
            break
    return out


@login_required
@capability_required(CAPABILITY)
def reports_archive(request: HttpRequest) -> HttpResponse:
    kind = request.GET.get("kind", "")
    if kind not in dict(AbsenceReportSnapshot.KINDS):
        kind = ""
    return render(
        request,
        "operations/absence_followup/reports_archive.html",
        {
            "snapshots": _latest_per_report(request.school, kind),
            "kinds": [("", "كلّ الأنواع"), *AbsenceReportSnapshot.KINDS],
            "f_kind": kind,
        },
    )


@login_required
@capability_required(CAPABILITY)
def report_detail(request: HttpRequest, pk: str) -> HttpResponse:
    snap = get_object_or_404(AbsenceReportSnapshot, pk=pk, school=request.school)
    log_export(
        request,
        "operations.absence_report_view",
        object_id=str(snap.pk),
        object_repr=f"{snap.kind}/{snap.grade_scope or 'all'}/{snap.period_start}:{snap.period_end}",
    )
    revisions = AbsenceReportSnapshot.objects.filter(
        school=request.school,
        kind=snap.kind,
        grade_scope=snap.grade_scope,
        period_start=snap.period_start,
        period_end=snap.period_end,
    ).order_by("-revision")
    payload = snap.payload or {}
    lines = [*(payload.get("stages") or []), *(payload.get("wings") or [])]
    if payload.get("outside"):
        lines.append(payload["outside"])
    return render(
        request,
        "operations/absence_followup/report_detail.html",
        {
            "snap": snap,
            "revisions": revisions,
            "lines": lines,
            "school_line": payload.get("school"),
            "is_latest": revisions.first().pk == snap.pk,
        },
    )


@require_POST
@login_required
@capability_required(CAPABILITY)
def report_recompute(request: HttpRequest, pk: str) -> HttpResponse:
    """«أعد الحساب الآن»: عملُ خلفيّةٍ (قد يمتدّ الربعُ سنويّ أشهراً) ينتج نسخةً جديدة ولا يمسّ القديمة."""
    from operations.absence_reports_tasks import recompute_absence_report_task

    snap = get_object_or_404(AbsenceReportSnapshot, pk=pk, school=request.school)
    log_export(
        request,
        "operations.absence_report_recompute",
        object_id=str(snap.pk),
        object_repr=f"{snap.kind}/{snap.grade_scope or 'all'}/{snap.period_start}:{snap.period_end}",
    )
    recompute_absence_report_task.delay(
        str(request.school.pk),
        snap.kind,
        snap.grade_scope,
        snap.period_start.isoformat(),
        snap.period_end.isoformat(),
        str(request.user.pk),
    )
    messages.success(request, "بدأ إعادةُ الحساب في الخلفيّة؛ تظهر النسخةُ الجديدة هنا خلال دقائق.")
    return redirect(reverse("absence_report_detail", args=[snap.pk]))

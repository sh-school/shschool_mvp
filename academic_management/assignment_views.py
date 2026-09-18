"""شاشةُ «الإسناد» الواحدة — بطاقةٌ لكلّ معلّم، والحفظُ في لحظته.

قرارُ الإدارة 2026-09-06: تبسيطٌ إلى أقصاه. كانت صفحتان — «توزيعات المواد على
الشُّعب» تكتب ولا تُري الصورة، و«إسناد الأنصبة» تُري الصورة ولا تكتب — وبينهما
محرّرُ خطّةٍ بسبعة أقسامٍ ومراجعَ ورموزِ سياسات. فصارت بطاقةً واحدةً لكلّ معلّم:

    المعلّم · نصابُه · [المرحلة · الشعبة · المادّة · الحصص · يحضّر ✓] …

لا تخفيضَ ولا مرجعَ ولا رمزَ سياسة. الشعبةُ تُختار فتظهر موادُّ خطّتها
الوزاريّة، والمادّةُ تُختار فتُملأ الحصصُ من الخطّة وتُحفظ من فورها (HTMX)،
وعبءُ التحضير حصّتان لكلّ مقرّر (قرارُ 2026-09-05).

## من يفعل ماذا

المنسّقُ يُدخل لمعلّمي قسمه — من سجلّ العضويّات — ثمّ يرفع. والنائبُ الأكاديميُّ
يراجع، والمديرُ يعتمد؛ ولهما معاً كلُّ الأقسام وكلُّ التعديل. وهذه القدراتُ
تُقرأ من `workload_workflow` لا تُكتب هنا، فتبقى بوّابةُ الاعتماد وختمُه كما هي.

والكتابةُ كلُّها تمرّ بـ`assignment_services` فتُفحص وتُدقَّق كما كانت.
"""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from academic_management import assignment_selectors as selectors
from academic_management import assignment_services as assignment_service
from academic_management import curriculum_services as curriculum_service
from academic_management import workload_workflow as flow
from academic_management.models import FROZEN_STATUSES, CoursePreparation
from core.academic_calendar import academic_year_for
from core.models import ClassGroup, CustomUser, Department, Membership
from core.models.access import DEPARTMENT_ROLES
from operations.models import Subject, SubjectClassAssignment

MODULE_NAME = "إدارة الشؤون الأكاديمية"


# ══════════════════════════════════════════════════════════════════════
#  القدرة والنطاق
# ══════════════════════════════════════════════════════════════════════


def _guard(request, teacher=None):
    """يرفض من لا قدرةَ له، ومن يمدّ يدَه إلى معلّمٍ خارج قسمه.

    تُعيد (المدرسة، القدرات، مفتاحَ نطاق المستخدم، العام). والنطاقُ `None`
    للنائب والمدير: قسمٌ واحدٌ لا يحدّهما.
    """
    school = request.user.get_school()
    caps = selectors.caps(request.user, school)
    if not (caps["edit"] or caps["review"] or caps["approve"]):
        raise PermissionDenied("شاشةُ الإسناد للمنسّق والنائب الأكاديميّ والمدير.")
    year = request.POST.get("year") or request.GET.get("year") or academic_year_for(request)

    unbounded = caps["review"] or caps["approve"] or getattr(request.user, "is_superuser", False)
    scope = None if unbounded else selectors.department_key(request.user, school, year)
    if teacher is not None and scope is not None:
        if selectors.department_key(teacher, school, year) != scope:
            raise PermissionDenied("هذا المعلّمُ خارج قسمك.")
    return school, caps, scope, year


# ══════════════════════════════════════════════════════════════════════
#  بناءُ البطاقة — انتقلت إلى academic_management/assignment_selectors.py
# ══════════════════════════════════════════════════════════════════════


#: قالبُ البطاقة — يُصيَّر مرّتين حين يلزم تحديثُ بطاقتين معاً.
CARD_TEMPLATE = "academic_management/partials/assignment_teacher.html"


def _render_card(request, school, year, teacher, caps, **extra):
    """بطاقةُ معلّمٍ تُعاد — في موضعها هي، ومعها بطاقةُ من طلبها إن اختلفا.

    الصفحةُ تُحدَّث بطاقةً بطاقة، فتبقى بطاقاتُ الزملاء على حالها. فمن ضغط ✕
    أو عدّل حصصاً في بطاقةٍ قديمةٍ بعد أن انتقلت المادّةُ إلى زميل، كان الجوابُ
    **بطاقةَ الزميل تحلّ في موضع البطاقة القديمة**: فيظهر المعلّمُ نفسُه مرّتين
    ويختفي غيرُه — وهو ما رآه المستخدم (2026-09-06).

    فصار الجوابُ يقصد عنصرَه بمعرّفه (`HX-Retarget`)، وتُرسَل معه بطاقةُ العنصر
    الذي طلب (`hx-swap-oob`) محدَّثةً — فتُصحَّح الشاشتان معاً ولا يبقى قديم.
    """
    from django.template.loader import render_to_string

    if "registry" not in extra and caps["review"]:
        extra["registry"] = list(Department.objects.filter(school=school, is_active=True))

    html = render_to_string(
        CARD_TEMPLATE,
        # مفتوحةً: البطاقاتُ مطويّةٌ افتراضاً، ومن حفظ فيها لا تُطوى في وجهه.
        {"card": selectors.card(school, year, teacher, caps, **extra), "open": True},
        request=request,
    )
    html += _stale_card_html(request, school, year, caps, teacher)

    response = HttpResponse(html)
    response["HX-Retarget"] = f"#teacher-{teacher.id}"
    response["HX-Reswap"] = "outerHTML"
    return response


def _stale_card_html(request, school, year, caps, rendered_teacher):
    """بطاقةُ العنصر الذي أرسل الطلبَ حين لا تكون بطاقةَ من رُدّ عليه."""
    from django.template.loader import render_to_string

    target = (request.headers.get("HX-Target") or "").removeprefix("teacher-")
    if not target or target == str(rendered_teacher.id):
        return ""
    other = CustomUser.objects.filter(id=target).first() if _is_uuid(target) else None
    if other is None:
        return ""
    return render_to_string(
        CARD_TEMPLATE,
        {"card": selectors.card(school, year, other, caps), "oob": True},
        request=request,
    )


def _is_uuid(value: str) -> bool:
    from uuid import UUID

    try:
        UUID(value)
    except ValueError:
        return False
    return True


# ══════════════════════════════════════════════════════════════════════
#  الصفحة
# ══════════════════════════════════════════════════════════════════════


@login_required
def assignments(request):
    school, caps, scope, year = _guard(request)
    selected = request.GET.get("dept") or ""
    ctx = selectors.assignments_page_context(school, caps, scope, year, selected)
    return render(
        request,
        "academic_management/assignments.html",
        {
            "page_title": "الإسناد",
            "page_subtitle": selectors.assignments_subtitle(year, ctx["totals"]),
            "module_name": MODULE_NAME,
            "year": year,
            "selected_dept": selected,
            **ctx,
        },
    )


# ══════════════════════════════════════════════════════════════════════
#  الكتابةُ في مكانها
# ══════════════════════════════════════════════════════════════════════


def _locked_card(request, school, year, teacher, caps):
    """بطاقةُ خطأٍ حين تكون مقفلةً — بدل تجاهلٍ صامتٍ للنقرة."""
    plan = selectors.latest_plan(school, teacher, year)
    if selectors.may_write(plan, caps):
        return None
    reason = (
        "هذه الخطّةُ معتمَدةٌ — افتح إصداراً جديداً للتعديل."
        if plan and plan.status in FROZEN_STATUSES
        else "الخطّةُ مرفوعةٌ للمراجعة — لا تُعدَّل حتّى تُردَّ إليك."
    )
    return _render_card(request, school, year, teacher, caps, error=reason)


@login_required
@require_GET
def subject_options(request):
    """موادُّ خطّة الشعبة المختارة — بحصصها ومن يحملها الآن إن كان أحد."""
    school, _caps_, _scope, year = _guard(request)
    class_id = request.GET.get("class_group")
    if not class_id:
        return render(request, "academic_management/partials/assignment_subject_options.html", {})
    group = get_object_or_404(ClassGroup, id=class_id, school=school)
    holders = {
        a.subject_id: a.teacher
        for a in SubjectClassAssignment.objects.live(school, year=year)
        .filter(class_group=group)
        .select_related("teacher")
    }
    options = [
        {"row": row, "holder": holders.get(row.subject_id)}
        for row in curriculum_service.demand_for(group)
    ]
    return render(
        request,
        "academic_management/partials/assignment_subject_options.html",
        {"options": options},
    )


@login_required
@require_POST
def add_row(request, teacher_id):
    """إسنادٌ جديد: الشعبةُ والمادّة — والحصصُ من الخطّة الوزاريّة."""
    teacher = get_object_or_404(CustomUser, id=teacher_id)
    school, caps, _scope, year = _guard(request, teacher)
    locked = _locked_card(request, school, year, teacher, caps)
    if locked is not None:
        return locked

    group = get_object_or_404(ClassGroup, id=request.POST.get("class_group"), school=school)
    subject = get_object_or_404(Subject, id=request.POST.get("subject"), school=school)
    planned = next(
        (r for r in curriculum_service.demand_for(group) if r.subject_id == subject.id), None
    )
    if planned is None:
        return _render_card(
            request,
            school,
            year,
            teacher,
            caps,
            error="لا خطّةَ دراسيّةً لهذه المادّة في هذه الشعبة.",
        )

    try:
        _row, findings = assignment_service.apply_assignment(
            school=school,
            academic_year=year,
            class_group=group,
            subject=subject,
            teacher=teacher,
            weekly_periods=planned.weekly_periods,
            by=request.user,
            confirm_transfer=bool(request.POST.get("confirm_transfer")),
        )
    except assignment_service.AssignmentError as exc:
        codes = {f.code for f in exc.findings if f.blocks}
        if codes == {assignment_service.SUBJECT_HELD_BY_OTHER}:
            # مانعٌ واحدٌ وهو النقل: تُعرض الحقيقةُ ويُطلب التأكيدُ بدل الرفض.
            holder = (
                SubjectClassAssignment.objects.live(school, year=year)
                .filter(class_group=group, subject=subject)
                .select_related("teacher")
                .first()
            )
            return _render_card(
                request,
                school,
                year,
                teacher,
                caps,
                transfer={
                    "class_group": group,
                    "subject": subject,
                    "holder": holder.teacher if holder else None,
                    # خطّةُ صاحب المادّة إن كانت معتمَدةً: النقلُ يُخرجها عمّا
                    # وُقّع عليه، فيُقال ذلك قبل الضغط لا بعده.
                    "holder_approved": bool(
                        holder
                        and (holder_plan := selectors.latest_plan(school, holder.teacher, year))
                        and holder_plan.status in FROZEN_STATUSES
                    ),
                    "prepares": bool(request.POST.get("prepares")),
                    "year": year,
                },
            )
        return _render_card(request, school, year, teacher, caps, error=_message(exc))
    except ValidationError as exc:
        return _render_card(request, school, year, teacher, caps, error=_message(exc))

    if request.POST.get("prepares"):
        try:
            assignment_service.apply_preparation(
                school=school,
                academic_year=year,
                grade=group.grade,
                track=group.track,
                subject=subject,
                teacher=teacher,
                by=request.user,
            )
        except (assignment_service.AssignmentError, ValidationError) as exc:
            return _render_card(
                request, school, year, teacher, caps, error=_message(exc), notes=findings
            )
    return _render_card(request, school, year, teacher, caps, notes=findings)


@login_required
@require_POST
def update_periods(request, assignment_id):
    """تعديلُ الحصص في مكانها — وما خالف الخطّةَ يُكتب سببُه."""
    obj = get_object_or_404(SubjectClassAssignment, id=assignment_id, is_active=True)
    teacher = obj.teacher
    school, caps, _scope, _year = _guard(request, teacher)
    year = obj.academic_year
    locked = _locked_card(request, school, year, teacher, caps)
    if locked is not None:
        return locked

    try:
        periods = int(request.POST.get("weekly_periods") or 0)
    except ValueError:
        return HttpResponseBadRequest("عددُ الحصص رقم")
    try:
        _row, findings = assignment_service.apply_assignment(
            school=school,
            academic_year=year,
            class_group=obj.class_group,
            subject=obj.subject,
            teacher=teacher,
            weekly_periods=periods,
            by=request.user,
            override_reason=(request.POST.get("reason") or "").strip(),
            #: الوسمُ يُحمَل معه لا يُترك لافتراضه.
            #:
            #: `apply_assignment` تكتب `parallel_group = tag` دائماً، وافتراضُها
            #: فراغ. فكلُّ تعديلٍ لعدد الحصص كان **يمحو التوازيَ صامتاً**:
            #: يُعدَّل نصابُ الفنّيّة في 12/1 فتفقد شراكتَها مع التكنولوجيا،
            #: ويصير المولّدُ يطلب لهما خانتين بعد أن كانتا في خانة.
            parallel_group=obj.parallel_group,
            requires_lab=obj.requires_lab,
            expected_updated_at=obj.updated_at,
        )
    except (
        assignment_service.AssignmentError,
        assignment_service.StaleWriteError,
        ValidationError,
    ) as exc:
        return _render_card(request, school, year, teacher, caps, error=_message(exc))
    return _render_card(request, school, year, teacher, caps, notes=findings)


@login_required
@require_POST
def cancel_transfer(request, teacher_id):
    """صرفُ النظر عن نقلٍ لم يُؤكَّد — تُعاد البطاقةُ كما كانت."""
    teacher = get_object_or_404(CustomUser, id=teacher_id)
    school, caps, _scope, year = _guard(request, teacher)
    return _render_card(request, school, year, teacher, caps)


@login_required
@require_POST
def remove_row(request, assignment_id):
    obj = get_object_or_404(SubjectClassAssignment, id=assignment_id, is_active=True)
    teacher = obj.teacher
    school, caps, _scope, _year = _guard(request, teacher)
    year = obj.academic_year
    locked = _locked_card(request, school, year, teacher, caps)
    if locked is not None:
        return locked
    assignment_service.remove_assignment(
        assignment=obj, by=request.user, reason="حُذف من شاشة الإسناد"
    )
    return _render_card(request, school, year, teacher, caps)


@login_required
@require_POST
def set_parallel(request, assignment_id):
    """ربطُ مادّتين في الشعبة توازياً — أو فكُّ الربط.

    التوازي صفةُ **الإسناد** لا الجدول: مادّتان في الشعبة الواحدة تُدرَّسان في
    التوقيت نفسه لقسمَي الطلاب — الفنّيّةُ والتكنولوجيا في 11/1، والفنّيّةُ
    والكيمياء في 11/4. فالمولّدُ يجمعهما في مهمّةٍ واحدةٍ بساكنَين، وبلا الوسم
    يطلب لهما خانتين ويقع في «شعبةٌ بمادّتين».

    ## ولماذا شريكةٌ تُختار لا مربّعٌ يُشعَل

    المربّعُ يوسم مادّةً واحدة، فيُنشئ اليتيمَ بأوّل نقرة: مجموعةٌ بعضوٍ واحدٍ
    ليست توازياً، والمولّدُ لا يخصمها فيظهر «مطلوب 37 والسعة 35» وليس في
    الشعبة فائضٌ أصلاً. فالربطُ هنا ثنائيٌّ في فعلٍ واحد: تُختار الشريكةُ
    فيُوسَم الطرفان معاً، ويُفكّ الوسمُ عنهما معاً — فلا يُولَد يتيمٌ من هذا
    الباب.

    والوسمُ يُشتقّ من الشعبة ولا يُكتب نصّاً، فلا يُطلب من أحدٍ أن يتذكّر
    حروفاً يطابقها.
    """
    obj = get_object_or_404(SubjectClassAssignment, id=assignment_id, is_active=True)
    teacher = obj.teacher
    school, caps, _scope, _year = _guard(request, teacher)
    year = obj.academic_year
    locked = _locked_card(request, school, year, teacher, caps)
    if locked is not None:
        return locked

    raw = (request.POST.get("partner") or "").strip()
    partner = None
    if raw:
        partner = (
            SubjectClassAssignment.objects.live(school, year=year)
            .filter(pk=raw, class_group_id=obj.class_group_id)
            .exclude(pk=obj.pk)
            .first()
        )
        if partner is None:
            return _render_card(
                request, school, year, teacher, caps, error="الشريكةُ ليست من موادّ هذه الشعبة."
            )

    old_tag = (obj.parallel_group or "").strip()
    with transaction.atomic():
        if partner is None:
            #: فكُّ الربط يرفع الوسمَ عن الطرفين — وإلّا بقي الآخرُ يتيماً.
            if old_tag:
                SubjectClassAssignment.objects.filter(
                    class_group_id=obj.class_group_id, parallel_group=old_tag, is_active=True
                ).update(parallel_group="", updated_by=request.user)
            else:
                obj.parallel_group = ""
                obj.updated_by = request.user
                obj.save(update_fields=["parallel_group", "updated_by", "updated_at"])
        else:
            tag = f"par-{obj.class_group.short_code}"[:40]
            for row in (obj, partner):
                row.parallel_group = tag
                row.updated_by = request.user
                row.save(update_fields=["parallel_group", "updated_by", "updated_at"])
    return _render_card(request, school, year, teacher, caps)


@login_required
@require_POST
def toggle_double(request, assignment_id):
    """مربّعُ «مزدوجة» — حصّتان متلاصقتان لهذه المادّة في هذه الشعبة.

    والقرارُ هنا لا في جدول الموادّ: الازدواجُ ليس صفةَ المادّة بإطلاق بل صفةَ
    تدريسها في صفٍّ بعينه — التكنولوجيا متباعدةٌ من السابع إلى العاشر ومزدوجةٌ
    في الحادي عشر/1 حيث هي نصفُ زوجٍ متوازٍ مع الفنّيّة. و`double_period` على
    الإسناد يعلو `Subject.requires_double_period`، فهذا المربّعُ هو الكلمةُ
    الأخيرة.

    ويُكتب صريحاً — `True` أو `False` — لا يُترك `None` («اتبع المادّة»):
    المستخدمُ يرى مربّعاً مشعلاً أو مطفأً، فيجب أن يكون ما يراه هو ما يُقرأ.
    """
    obj = get_object_or_404(SubjectClassAssignment, id=assignment_id, is_active=True)
    teacher = obj.teacher
    school, caps, _scope, _year = _guard(request, teacher)
    year = obj.academic_year
    locked = _locked_card(request, school, year, teacher, caps)
    if locked is not None:
        return locked

    obj.double_period = bool(request.POST.get("double"))
    obj.updated_by = request.user
    obj.save(update_fields=["double_period", "updated_by", "updated_at"])
    return _render_card(request, school, year, teacher, caps)


@login_required
@require_POST
def toggle_preparation(request, teacher_id):
    """مربّعُ «يحضّر» — تعيينُ مسؤوليّة تحضير المقرّر أو إسقاطُها."""
    teacher = get_object_or_404(CustomUser, id=teacher_id)
    school, caps, _scope, year = _guard(request, teacher)
    locked = _locked_card(request, school, year, teacher, caps)
    if locked is not None:
        return locked

    grade = request.POST.get("grade") or ""
    track = request.POST.get("track") or ""
    subject = get_object_or_404(Subject, id=request.POST.get("subject"), school=school)
    try:
        if request.POST.get("prepares"):
            assignment_service.apply_preparation(
                school=school,
                academic_year=year,
                grade=grade,
                track=track,
                subject=subject,
                teacher=teacher,
                by=request.user,
            )
        else:
            current = (
                CoursePreparation.objects.live(school, year=year)
                .filter(grade=grade, track=track, subject=subject, teacher=teacher)
                .first()
            )
            if current:
                assignment_service.remove_preparation(
                    preparation=current, by=request.user, reason="أُسقط من شاشة الإسناد"
                )
    except (assignment_service.AssignmentError, ValidationError) as exc:
        return _render_card(request, school, year, teacher, caps, error=_message(exc))
    return _render_card(request, school, year, teacher, caps)


@login_required
@require_POST
def set_load(request, teacher_id):
    """النصابُ رقمٌ واحد — يُفتح له مسودّةٌ إن لم تكن، ويُحدَّث إن كانت."""
    teacher = get_object_or_404(CustomUser, id=teacher_id)
    school, caps, _scope, year = _guard(request, teacher)
    locked = _locked_card(request, school, year, teacher, caps)
    if locked is not None:
        return locked

    try:
        periods = int(request.POST.get("required_weekly_periods") or 0)
    except ValueError:
        return HttpResponseBadRequest("النصابُ رقم")
    if not 0 <= periods <= 40:
        return _render_card(
            request, school, year, teacher, caps, error="النصابُ بين صفرٍ وأربعين حصّة."
        )

    plan = selectors.latest_plan(school, teacher, year)
    try:
        if plan is None:
            flow.open_draft(
                school,
                teacher,
                year,
                by=request.user,
                required_weekly_periods=periods,
                required_source_kind="manual",
                required_source_reference="شاشة الإسناد",
            )
        else:
            plan.required_weekly_periods = periods
            plan.required_source_kind = "manual"
            plan.required_source_reference = "شاشة الإسناد"
            plan.updated_by = request.user
            plan.full_clean(exclude=["created_by", "updated_by"])
            plan.save()
    except (ValidationError, PermissionDenied) as exc:
        return _render_card(request, school, year, teacher, caps, error=_message(exc))
    return _render_card(request, school, year, teacher, caps)


@login_required
@require_POST
def set_department(request, teacher_id):
    """نقلُ معلّمٍ إلى قسمٍ — للنائب والمدير وحدَهما.

    الانتماءُ يُكتب على عضويّة التدريس لا على المستخدم، ولا يُقبل لدورٍ غير
    تدريسيّ (يحرسه `Membership.clean`). وبهذا يجد المعيَّنُ حديثاً والمنقولُ
    بابَه في المنصّة، بلا لوحةِ إدارة.
    """
    teacher = get_object_or_404(CustomUser, id=teacher_id)
    school, caps, _scope, year = _guard(request, teacher)
    if not (caps["review"] or caps["approve"]):
        raise PermissionDenied("نقلُ المعلّم بين الأقسام للنائب الأكاديميّ والمدير.")

    raw = request.POST.get("department") or ""
    department = (
        get_object_or_404(Department, id=raw, school=school, is_active=True) if raw else None
    )
    memberships = Membership.objects.filter(
        user=teacher, school=school, is_active=True, role__name__in=DEPARTMENT_ROLES
    ).select_related("role")
    if not memberships:
        return _render_card(
            request,
            school,
            year,
            teacher,
            caps,
            error="لا عضويّةَ تدريسٍ لهذا الشخص — والقسمُ الأكاديميُّ لأهل التدريس.",
        )
    try:
        for membership in memberships:
            membership.department_obj = department
            membership.full_clean(exclude=["user", "school", "role"])
            membership.save(update_fields=["department_obj"])
    except ValidationError as exc:
        return _render_card(request, school, year, teacher, caps, error=_message(exc))
    return _render_card(request, school, year, teacher, caps, department=department)


# ══════════════════════════════════════════════════════════════════════
#  الدورة: رفعٌ ← مراجعةٌ ← اعتماد
# ══════════════════════════════════════════════════════════════════════


@login_required
@require_POST
def move(request, teacher_id, action):
    """نقلةٌ واحدةٌ في دورة الخطّة — والبوّابةُ والختمُ في `workload_workflow`."""
    teacher = get_object_or_404(CustomUser, id=teacher_id)
    school, caps, _scope, year = _guard(request, teacher)
    plan = selectors.latest_plan(school, teacher, year)
    if plan is None:
        return _render_card(
            request,
            school,
            year,
            teacher,
            caps,
            error="لا خطّةَ لهذا المعلّم — اكتب نصابَه أوّلاً.",
        )

    comment = (request.POST.get("comment") or "").strip()
    handlers = {
        "submit": lambda: flow.submit_for_review(plan, by=request.user),
        "review": lambda: flow.record_review(plan, by=request.user, comment=comment),
        "return": lambda: flow.return_to_draft(plan, by=request.user, comment=comment),
        "approve": lambda: flow.approve(plan, by=request.user),
        "revise": lambda: flow.new_version_from(plan, by=request.user),
    }
    if action not in handlers:
        return HttpResponseBadRequest("نقلةٌ غيرُ معروفة")
    try:
        handlers[action]()
    except (flow.WorkflowError, ValidationError, PermissionDenied) as exc:
        return _render_card(request, school, year, teacher, caps, error=_message(exc))
    return _render_card(request, school, year, teacher, caps)


def _message(exc) -> str:
    if isinstance(exc, assignment_service.AssignmentError):
        return "؛ ".join(f.message for f in exc.findings if f.blocks) or str(exc)
    if isinstance(exc, assignment_service.StaleWriteError):
        return "عُدّل هذا السطرُ من جهازٍ آخر — أعِد تحميل الصفحة."
    if isinstance(exc, ValidationError):
        return "؛ ".join(
            m for msgs in getattr(exc, "message_dict", {"": exc.messages}).values() for m in msgs
        )
    return str(exc)

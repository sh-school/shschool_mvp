"""
staff_affairs/views.py — شؤون الموظفين
8 views — يتبع أنماط المشروع.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Case, CharField, F, Func, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Coalesce, NullIf
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.academic_calendar import academic_year_for
from core.models.access import DEPARTMENT_ROLES, Membership
from core.models.department import Department
from core.models.user import CustomUser
from core.permissions import STAFF_AFFAIRS_MANAGE, role_required
from core.privacy import mask_national_id
from core.sorting import apply_sort, arabic_key, blank_as_null, normalise_arabic

from . import appointments, profile_service
from .forms import (
    StaffAppointmentForm,
    StaffDepartureForm,
    StaffEmploymentForm,
    StaffPersonForm,
)
from .models import LeaveRequest
from .services import LeaveService, StaffService


def role_label(name: str) -> str:
    """اسمُ الدور بالعربيّة — من قائمة الأدوار الرسميّة لا من قاموسٍ محلّيّ.

    كان هنا قاموسٌ يدويٌّ ينقصه سبعةَ عشرَ دوراً، فكانت الشاشاتُ تكتب
    `student_observer` و`lab_technician` بحروفٍ إنجليزيّةٍ لمن لا يقرؤها.
    والقائمةُ الرسميّةُ في `Role.ROLES` — ومن زاد فيها دوراً ظهر اسمُه هنا
    بلا تعديلِ سطرٍ في هذا الملفّ.
    """
    from core.models.access import Role

    return dict(Role.ROLES).get(name, name)


# ═══════════════════════════════════════════════════════════════════
# الخطوة 3: لوحة شؤون الموظفين
# ═══════════════════════════════════════════════════════════════════


@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def staff_dashboard(request):
    """لوحة شؤون الموظفين — KPIs + روابط سريعة."""
    school = request.user.get_school()
    today = timezone.localdate()
    year = request.GET.get("year") or academic_year_for(request)

    # ✅ v5.4: StaffService.get_dashboard_stats — 7 KPIs في service layer
    stats = StaffService.get_dashboard_stats(school, year, today=today)

    # role_distribution_raw → قائمة مع labels للـ template
    role_distribution = [
        {
            "role_name": r["role__name"],
            "role_display": role_label(r["role__name"]),
            "count": r["count"],
        }
        for r in stats.pop("role_distribution_raw", [])
    ]

    return render(
        request,
        "staff_affairs/dashboard.html",
        {
            "today": today,
            "year": year,
            "role_distribution": role_distribution,
            **stats,
        },
    )


# ═══ الخطوة 4: سجل الموظفين ═══


def _member_or_404(user_id, school, *, active_only=False):
    """منتسبُ هذه المدرسة بهذا المعرّف — بصرف النظر عن عدد عضويّاته.

    الاستعلامُ بالربط `memberships__school=` ضمٌّ لا ترشيح: يُعيد صفّاً لكلّ
    عضويّة، فمن كان موظّفاً ووليَّ أمرٍ يُعيد صفّين ويسقط `get()`. والاستعلامُ
    الداخليُّ في `ever_in_school` يُعيد صفّاً واحداً لكلّ إنسان.

    و«ever» لا «in»: من غادر يبقى ملفُّه مقروءاً — ومن سُجّلت مغادرتُه بالخطأ
    لا يُصحَّح إلّا من صفحته.
    """
    rows = (
        CustomUser.objects.in_school(school)
        if active_only
        else CustomUser.objects.ever_in_school(school)
    )
    return get_object_or_404(rows, id=user_id)


#: الطلابُ وأولياءُ الأمور ليسوا من شؤون الموظفين — بابُهم «شؤون الطلبة»
#: (قرارُ المستخدم 2026-09-06). والسجلُّ هنا لكادر المدرسة بكلّ فئاته:
#: التدريسيّةِ والإداريّةِ والفنّيّةِ والخدماتِ المساندة.
PAGE_SIZE = 50

#: ما يجوز الفرزُ به في سجلّ المنتسبين — مفتاحُ الرابط ← حقولُ الترتيب.
#:
#: `?sort=` نصٌّ يأتي من المستخدم، فلا يبلغ `order_by` إلّا عبر هذه القائمة.
#: والاسمُ فاصلٌ يقطع التساوي في كلّ عمودٍ سواه، وإلّا تراقص ترتيبُ المتساوين
#: بين صفحةٍ وأخرى.
#: مفاتيحُ فرز السجلّ. وكلُّها تنتهي بالاسم فاصلاً يقطع التساوي، وإلّا تبدّل
#: ترتيبُ المتساوين بين نقرةٍ وأخرى فبدا للقارئ أنّ الصفحةَ تتحرّك تحت يده.
#: والمفاتيحُ مُسوّاةٌ عربيّاً ومُفرَّغةٌ من الفراغ في `staff_list` — لا أسماءَ
#: حقولٍ خام: الفرزُ بالحقل الخام يرتّب بالنقطة البرمجيّة لا بالحرف.
STAFF_SORTS = {
    "name": ("name_key",),
    "employee": ("employee_key", "name_key"),
    "national": ("national_key", "name_key"),
    # «المسمّى الوظيفيّ» يُفرَز بما يُعرض في خليّته: المسمّى المسجَّل، ودورُ
    # المنصّة بالعربيّة حين لا مسمّى. وكان يُفرَز بـ`role.name` الإنجليزيّ —
    # ترويسةٌ تَعرض شيئاً وترتّب بغيره.
    "title": ("title_key", "name_key"),
    "department": ("dept_key", "name_key"),
    "phone": ("phone_key", "name_key"),
    "email": ("email_key", "name_key"),
    "residence": ("residence_key", "name_key"),
    "nationality": ("nationality_key", "name_key"),
    "joined": ("gov_joined", "name_key"),
    "license": ("professional_license_expiry", "name_key"),
}


@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def staff_list(request):
    """سجلُّ منتسبي المدرسة — بحثٌ وترشيحٌ بالفئة والدور والقسم.

    كان يستثني الطلابَ وأولياءَ الأمور استثناءً مغلقاً، ويقتطع أوّلَ مئتين
    بلا تصفّح — فمن بحث عن الحادي والمئتين لم يجده ولم يُقل له لماذا. صار
    الاستثناءُ ترشيحاً يُبدَّل، والاقتطاعُ تصفّحاً يُرى.
    """
    school = request.user.get_school()

    q = request.GET.get("q", "").strip()
    role_filter = request.GET.get("role", "")
    dept_filter = request.GET.get("dept", "")

    # المغادرون لا يسقطون من السجلّ — يُرشَّحون. فمن نُقل هذا الصيفَ يبقى ملفُّه
    # مقروءاً، ومن سُجّلت مغادرتُه بالخطأ يُوجَد ليُصحَّح.
    status = request.GET.get("status") or "current"

    # السجلُّ صفٌّ لكلّ إنسانٍ لا لكلّ عضويّة: من كان معلّماً ومنسّقاً له
    # عضويّتان، فكان يُعدّ رجلين ويظهر مرّتين. والتصفّحُ على المستخدمين
    # كي يبقى العددُ في الترويسة هو عددَ من في القائمة.
    memberships = Membership.objects.filter(school=school, is_active=(status != "left")).exclude(
        role__name__in=("student", "parent")
    )
    if role_filter:
        memberships = memberships.filter(role__name=role_filter)
    if dept_filter:
        memberships = memberships.filter(department_obj_id=dept_filter)

    people = CustomUser.objects.filter(id__in=memberships.values("user_id"))

    # الدورُ والقسمُ وتاريخُ الالتحاق صفاتُ عضويّةٍ لا صفاتُ شخص، والتصفّحُ على
    # الأشخاص. فتُجلب صفاتُ **العضويّة الحاكمة** بالاستعلام نفسِه ليصحّ الفرزُ
    # بها على القائمة كلِّها لا على الصفحة الظاهرة.
    from core.models.access import Role
    from core.models.user import role_rank

    governing = memberships.filter(user=OuterRef("pk")).order_by(role_rank(), "joined_at")
    people = people.annotate(
        gov_role=Subquery(governing.values("role__name")[:1]),
        gov_department=Subquery(governing.values("department_obj__name")[:1]),
        gov_joined=Subquery(governing.values("joined_at")[:1]),
        # المسمّى المعروض: المسجَّلُ إن وُجد، وإلّا عنوانُ الدور بالعربيّة.
        # ويُحسَب **داخلَ** الاستعلام المترابط لا خارجَه: بناءُ `Case` على وسمٍ
        # مصدرُه استعلامٌ مترابطٌ يُعيد كتابةَ ذلك الاستعلام في كلّ فرعٍ من
        # فروعه — ثلاثون فرعاً فثلاثون تنفيذاً لكلّ صفّ، وخمسُ ثوانٍ لفرزةٍ
        # أختُها جزءٌ من الثانية. وقائمةُ الأدوار واحدةٌ في `Role.ROLES`.
        gov_title=Subquery(
            governing.annotate(
                shown=Coalesce(
                    NullIf(F("job_title"), Value("")),
                    Case(
                        *[When(role__name=name, then=Value(label)) for name, label in Role.ROLES],
                        default=F("role__name"),
                        output_field=CharField(),
                    ),
                )
            ).values("shown")[:1]
        ),
        # الرقمُ الوظيفيُّ نصٌّ في القاعدة وأطوالُه مختلفة (أربعُ خاناتٍ إلى ستّ)،
        # وفرزُ النصّ يضع «9907» قبل «85308». فيُحشى بأصفارٍ إلى طولٍ واحدٍ
        # فيصير ترتيبُ الحروف هو ترتيبَ الأعداد — بلا تحويلٍ يسقط على قيمةٍ
        # غيرِ رقميّةٍ يوماً. والفارغُ يبقى عَدَماً فلا يتصدّر بأصفارٍ مصنوعة.
        employee_key=Func(
            NullIf(F("employee_number"), Value("")),
            Value(12),
            Value("0"),
            function="LPAD",
            output_field=CharField(),
        ),
        name_key=arabic_key(F("full_name")),
        dept_key=arabic_key(F("gov_department")),
        national_key=blank_as_null("national_id"),
        phone_key=blank_as_null("phone"),
        email_key=blank_as_null("email"),
        residence_key=blank_as_null("residence_area"),
        nationality_key=arabic_key(F("nationality")),
        title_key=arabic_key(F("gov_title")),
    )

    # والبحثُ بعد الوسوم ليبلغ ما تحمله العضويّةُ لا ما يحمله الشخصُ وحدَه.
    # وكلُّ عمودٍ معروضٍ مطلوبٌ به: من يرى «الوكرة» في عمودٍ يتوقّع أن يجدها
    # بكتابتها. والاسمُ والمسمّى يُطابَقان بمفتاحهما المسوّى، فتجد «احمد» من
    # كُتب «أحمد» — وهو أكثرُ ما يُكتب في صندوق بحثٍ عربيّ.
    if q:
        shaped = normalise_arabic(q)
        held_by_membership = memberships.filter(
            Q(job_title__icontains=q) | Q(department_obj__name__icontains=q)
        ).values("user_id")
        people = people.filter(
            Q(name_key__icontains=shaped)
            | Q(title_key__icontains=shaped)
            | Q(national_id__icontains=q)
            | Q(employee_number__icontains=q)
            | Q(phone__icontains=q)
            | Q(email__icontains=q)
            | Q(residence_area__icontains=q)
            | Q(nationality__icontains=q)
            | Q(professional_license_number__icontains=q)
            | Q(id__in=held_by_membership)
        )

    people, sort = apply_sort(
        people,
        request,
        allowed=STAFF_SORTS,
        default="name",
        desc_first=("joined", "license"),
    )

    paginator = Paginator(people, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))

    # عضويّاتُ صفحةٍ واحدةٍ في استعلامٍ واحد، والحاكمةُ منها أوّلاً.
    held = {}
    for m in (
        memberships.filter(user__in=list(page_obj))
        .select_related("role", "department_obj")
        .order_by(role_rank(), "joined_at")
    ):
        held.setdefault(m.user_id, m)

    staff_rows = []
    for user in page_obj:
        m = held.get(user.id)
        staff_rows.append(
            {
                "id": user.id,
                "full_name": user.full_name,
                # آخرُ أربعِ خاناتٍ وما قبلها مستور — والرقمُ كاملاً في
                # وثائق الطباعة وحدَها. والبحثُ يقع على المخزَّن لا المستور.
                "national_id": mask_national_id(user.national_id),
                "employee_number": user.employee_number,
                "role": m.role.name if m and m.role else "—",
                # المسمّى الرسميُّ أوّلاً — والدورُ حين لا مسمّى مسجَّل.
                "role_display": ((m.job_title or role_label(m.role.name)) if m and m.role else "—"),
                # ودورُ المنصّة بجانبه: المسمّى وثيقةٌ إداريّة، والدورُ مفتاحُ
                # الصلاحيّات — و«معلم علوم شرعية» لا يقول أيَّ شاشةٍ تُفتح له.
                "role_label": role_label(m.role.name) if m and m.role else "—",
                "department": (m.department_name if m else "") or "—",
                "phone": user.phone,
                "email": user.email,
                "residence_area": user.residence_area,
                "nationality": user.nationality,
                "joined": m.joined_at if m else None,
                "left": m.left_at if m else None,
                "reference": (m.appointment_reference if m else "") or "",
                "license_number": user.professional_license_number,
                "license_expiry": user.professional_license_expiry,
                "can_sign_in": user.is_active and user.has_usable_password(),
            }
        )

    from core.models.department import Department

    available_roles = (
        Role.objects.filter(school=school)
        .exclude(name__in=("student", "parent"))
        .values_list("name", flat=True)
        .distinct()
        .order_by("name")
    )
    available_depts = Department.objects.filter(school=school, is_active=True).order_by(
        "sort_order"
    )

    ctx = {
        "staff": staff_rows,
        "total": paginator.count,
        "page_obj": page_obj,
        "sort": sort,
        "today": timezone.localdate(),
        "q": q,
        "role_filter": role_filter,
        "dept_filter": dept_filter,
        "status": status,
        "statuses": (("current", "على رأس العمل"), ("left", "المغادرون")),
        "roles": [(r, role_label(r)) for r in available_roles],
        "departments": available_depts,
    }

    if request.headers.get("HX-Request"):
        return render(request, "staff_affairs/_staff_table.html", ctx)

    return render(request, "staff_affairs/staff_list.html", ctx)


# ═══ التعيينُ والمغادرة — قرارٌ يُوثَّق ═══


@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def staff_appoint(request):
    """تعيينُ منتسبٍ جديد — حسابُه وعضويّتُه ومرجعُ قراره في نموذجٍ واحد.

    كان التعيينُ لا يتمّ إلّا من لوحة Django أو من سطر الأوامر، فشؤونُ
    الموظفين تُدير كادراً لا تستطيع أن تضيف إليه أحداً.
    """
    school = request.user.get_school()
    form = StaffAppointmentForm(request.POST or None, school=school)

    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        department = None
        if data["department"]:
            department = get_object_or_404(
                Department, id=data["department"], school=school, is_active=True
            )
        try:
            membership = appointments.appoint(
                school=school,
                national_id=data["national_id"],
                full_name=data["full_name"],
                role_name=data["role_name"],
                department=department,
                email=data["email"],
                phone=data["phone"],
                employee_number=data["employee_number"],
                joined_on=data["joined_on"],
                reference=data["reference"],
                note=data["note"],
                by=request.user,
            )
        except ValidationError as exc:
            for field, errors in _as_errors(exc).items():
                for message in errors:
                    form.add_error(field if field in form.fields else None, message)
        else:
            messages.success(
                request,
                f"عُيّن {membership.user.full_name} — {membership.role.get_name_display()}"
                f" بمرجع «{membership.appointment_reference}». والحسابُ بلا كلمة مرورٍ حتّى تُصدَر له.",
            )
            return redirect("staff_affairs:staff_profile", user_id=membership.user_id)

    return render(
        request,
        "staff_affairs/staff_appoint.html",
        {"form": form, "department_roles": sorted(DEPARTMENT_ROLES)},
    )


@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
@require_POST
def staff_depart(request, user_id):
    """يسجّل مغادرةَ منتسبٍ — تاريخاً وسبباً ومرجعاً، ولا يمحو تاريخَه."""
    school = request.user.get_school()
    user = get_object_or_404(CustomUser, id=user_id)
    # صفةُ وليّ الأمر لا تُمسّ: مغادرةُ الكادر لا تُخرج ابنَه من المدرسة.
    rows = list(
        Membership.objects.filter(user=user, school=school, is_active=True).exclude(
            role__name__in=("student", "parent")
        )
    )
    if not rows:
        messages.error(request, "لا عضويّةَ كادرٍ نشطةً لهذا الشخص في المدرسة.")
        return redirect("staff_affairs:staff_list")

    form = StaffDepartureForm(request.POST)
    if not form.is_valid():
        for errors in form.errors.values():
            for message in errors:
                messages.error(request, message)
        return redirect("staff_affairs:staff_profile", user_id=user_id)

    data = form.cleaned_data
    try:
        for membership in rows:
            appointments.depart(
                membership=membership,
                on=data["on"],
                reason=data["reason"],
                reference=data["reference"],
                note=data["note"],
                by=request.user,
            )
    except ValidationError as exc:
        for errors in _as_errors(exc).values():
            for message in errors:
                messages.error(request, message)
        return redirect("staff_affairs:staff_profile", user_id=user_id)

    messages.success(
        request,
        f"سُجّلت مغادرةُ {user.full_name} في {data['on']} بمرجع «{data['reference']}» —"
        " وسجلُّه محفوظٌ كما هو.",
    )
    return redirect("staff_affairs:staff_list")


@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
@require_POST
def staff_reinstate(request, user_id):
    """يُلغي مغادرةً سُجّلت بالخطأ ويُعيد المنتسبَ إلى الكادر."""
    school = request.user.get_school()
    user = _member_or_404(user_id, school)
    rows = list(
        Membership.objects.filter(user=user, school=school, is_active=False).exclude(
            left_at__isnull=True
        )
    )
    if not rows:
        messages.error(request, "لا مغادرةَ مسجّلةً لهذا المنتسب.")
        return redirect("staff_affairs:staff_profile", user_id=user_id)

    note = (request.POST.get("note") or "").strip()
    try:
        for membership in rows:
            appointments.reinstate(membership=membership, by=request.user, note=note)
    except ValidationError as exc:
        for errors in _as_errors(exc).values():
            for message in errors:
                messages.error(request, message)
        return redirect("staff_affairs:staff_profile", user_id=user_id)

    messages.success(
        request, f"أُلغيت مغادرةُ {user.full_name} — عاد إلى الكادر، والتصحيحُ مسجَّلٌ في ملفّه."
    )
    return redirect("staff_affairs:staff_profile", user_id=user_id)


def _as_errors(exc) -> dict:
    if hasattr(exc, "message_dict"):
        return exc.message_dict
    return {"__all__": exc.messages}


# ═══ الخطوة 5: ملف الموظف ═══


@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def staff_profile(request, user_id):
    """ملف الموظف الشامل — بيانات + غياب + تقييم + إجازات + رخصة."""
    school = request.user.get_school()
    # المغادرُ له ملفٌّ يُفتح: من سُجّلت مغادرتُه بالخطأ لا يُصحَّح إلّا من هنا.
    user = _member_or_404(user_id, school)
    year = request.GET.get("year") or academic_year_for(request)

    # ✅ v5.4: StaffService.get_staff_profile_data — 7 نماذج في طبقة خدمة واحدة
    profile_data = StaffService.get_staff_profile_data(user, school, year)
    membership = profile_data["membership"] or (
        Membership.objects.filter(user=user, school=school)
        .select_related("role", "department_obj")
        .order_by("-joined_at")
        .first()
    )
    profile_data["membership"] = membership
    role_display = "—"
    if membership and membership.role:
        role_display = membership.job_title or membership.role.get_name_display()

    person_form = StaffPersonForm(
        initial={
            field: getattr(user, field, "")
            for field in profile_service.PERSON_FIELDS + profile_service.LICENSE_FIELDS
        }
    )
    employment_form = None
    if membership:
        employment_form = StaffEmploymentForm(
            school=school,
            initial={
                "job_title": membership.job_title,
                "department": str(membership.department_obj_id or ""),
                "joined_at": membership.joined_at,
                "appointment_reference": membership.appointment_reference,
                "appointment_note": membership.appointment_note,
            },
        )

    return render(
        request,
        "staff_affairs/staff_profile.html",
        {
            "staff_user": user,
            "year": year,
            "role_display": role_display,
            "today": timezone.localdate(),
            "departure_form": StaffDepartureForm(initial={"on": timezone.localdate()}),
            "person_form": person_form,
            "employment_form": employment_form,
            # الجدولُ لمن يُدرّس: ملاحظُ الطلبة والمحاسبُ لا حصصَ لهم.
            "teaches": bool(membership and membership.role.name in DEPARTMENT_ROLES),
            "history": profile_service.history(user, membership),
            **profile_data,  # membership, profile, absences, swaps, ...
        },
    )


@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
@require_POST
def staff_profile_save(request, user_id, section):
    """يحفظ قسماً من الملفّ — ويكتب في سجلّ المراجعة من غيّر وماذا ومتى."""
    school = request.user.get_school()
    user = _member_or_404(user_id, school)

    if section == "person":
        form = StaffPersonForm(request.POST)
        if form.is_valid():
            try:
                changed = profile_service.save_person(
                    user=user, data=form.cleaned_data, by=request.user, request=request
                )
            except ValidationError as exc:
                _flash_errors(request, exc)
            else:
                _flash_saved(request, changed)
            return redirect("staff_affairs:staff_profile", user_id=user_id)
    elif section == "employment":
        membership = (
            Membership.objects.filter(user=user, school=school, is_active=True)
            .exclude(role__name__in=("student", "parent"))
            .select_related("role")
            .first()
        )
        if membership is None:
            messages.error(request, "لا عضويّةَ كادرٍ لهذا الشخص.")
            return redirect("staff_affairs:staff_profile", user_id=user_id)
        form = StaffEmploymentForm(request.POST, school=school)
        if form.is_valid():
            data = dict(form.cleaned_data)
            raw = data.pop("department", "")
            data["department"] = (
                get_object_or_404(Department, id=raw, school=school, is_active=True)
                if raw
                else None
            )
            try:
                changed = profile_service.save_employment(
                    membership=membership, data=data, by=request.user, request=request
                )
            except ValidationError as exc:
                _flash_errors(request, exc)
            else:
                _flash_saved(request, changed)
            return redirect("staff_affairs:staff_profile", user_id=user_id)
    else:
        return redirect("staff_affairs:staff_profile", user_id=user_id)

    for errors in form.errors.values():
        for message in errors:
            messages.error(request, message)
    return redirect("staff_affairs:staff_profile", user_id=user_id)


def _flash_saved(request, changed):
    if not changed:
        messages.info(request, "لا تغييرَ — لم يُحفظ شيء.")
        return
    names = "، ".join(profile_service.LABELS.get(f, f) for f in changed)
    messages.success(request, f"حُفظ: {names}. وسُجّل التغييرُ باسمك ووقته.")


def _flash_errors(request, exc):
    for errors in _as_errors(exc).values():
        for message in errors:
            messages.error(request, message)


# ═══ الخطوة 6: الإجازات ═══


@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def leave_list(request):
    """قائمة طلبات الإجازات مع فلتر."""
    school = request.user.get_school()
    leaves = (
        LeaveRequest.objects.filter(school=school).select_related("staff").order_by("-created_at")
    )

    status_filter = request.GET.get("status", "")
    type_filter = request.GET.get("type", "")
    if status_filter:
        leaves = leaves.filter(status=status_filter)
    if type_filter:
        leaves = leaves.filter(leave_type=type_filter)

    from .models import LEAVE_STATUS, LEAVE_TYPES

    return render(
        request,
        "staff_affairs/leave_list.html",
        {
            "leaves": leaves[:100],
            "status_filter": status_filter,
            "type_filter": type_filter,
            "status_choices": LEAVE_STATUS,
            "type_choices": LEAVE_TYPES,
        },
    )


@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def leave_request_create(request):
    """تقديم طلب إجازة جديد."""
    school = request.user.get_school()
    from .forms import LeaveRequestForm

    if request.method == "POST":
        form = LeaveRequestForm(request.POST, request.FILES)
        if form.is_valid():
            cd = form.cleaned_data
            staff = _member_or_404(cd["staff_id"], school, active_only=True)
            # ✅ v5.4: LeaveService.create_leave_request — atomic + audit trail
            LeaveService.create_leave_request(
                school=school,
                staff=staff,
                leave_type=cd["leave_type"],
                start_date=cd["start_date"],
                end_date=cd["end_date"],
                days_count=cd["days_count"],
                reason=cd["reason"],
                attachment=cd.get("attachment"),
                created_by=request.user,
            )
            messages.success(
                request, f"تم تقديم طلب إجازة {staff.full_name} ({cd['days_count']} يوم)."
            )
            return redirect("staff_affairs:leave_list")
    else:
        form = LeaveRequestForm()

    staff_members = (
        Membership.objects.filter(school=school, is_active=True)
        .exclude(role__name__in=("student", "parent"))
        .select_related("user")
        .order_by("user__full_name")
    )
    return render(
        request,
        "staff_affairs/leave_form.html",
        {
            "form": form,
            "staff_members": staff_members,
        },
    )


@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def leave_detail(request, pk):
    """تفاصيل طلب إجازة."""
    school = request.user.get_school()
    leave = get_object_or_404(LeaveRequest, pk=pk, school=school)
    return render(request, "staff_affairs/leave_detail.html", {"leave": leave})


@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
@require_POST
def leave_review(request, pk):
    """مراجعة طلب إجازة — موافقة أو رفض."""
    school = request.user.get_school()
    leave = get_object_or_404(LeaveRequest, pk=pk, school=school)

    from .forms import LeaveReviewForm

    form = LeaveReviewForm(request.POST)
    if form.is_valid():
        action = form.cleaned_data["action"]
        try:
            # ✅ v5.4: LeaveService.review_leave — select_for_update على LeaveBalance
            # يمنع race condition عند موافقة مديرين في نفس الوقت على نفس الطلب
            LeaveService.review_leave(
                leave=leave,
                action=action,
                reviewer=request.user,
                rejection_reason=form.cleaned_data.get("rejection_reason", ""),
            )
            status_label = "موافق عليها" if action == "approved" else "مرفوضة"
            messages.success(request, f"تم تحديث طلب الإجازة إلى: {status_label}")
        except ValueError as e:
            messages.error(request, str(e))

    return redirect("staff_affairs:leave_detail", pk=pk)


# ═══════════════════════════════════════════════════════════════════
# الرخص المهنية
# ═══════════════════════════════════════════════════════════════════


@login_required
@role_required(STAFF_AFFAIRS_MANAGE)
def licensing_overview(request):
    """نظرة شاملة على الرخص المهنية — منتهية / تنتهي قريباً / سارية."""
    school = request.user.get_school()
    today = timezone.localdate()

    # ✅ v5.4: StaffService.get_license_overview — DB filters بدل Python list comprehensions
    # يتجنّب تحميل جميع الموظفين في الذاكرة لتصنيفهم (O(n) memory → O(1))
    license_data = StaffService.get_license_overview(school, today=today)

    return render(
        request,
        "staff_affairs/licensing.html",
        {
            "today": today,
            **license_data,
        },
    )

"""قدراتُ مجال «الحضور والجدول ومتابعة الغياب» — قسمٌ من سجلّ القدرات نُقل حرفاً بلا تغيير قدرةٍ ولا حامل (W-20261019-007)."""

from __future__ import annotations

from core.capabilities.base import Capability, Shared, _cap, _delegated


def attendance_schedule_capabilities(shared: Shared) -> list[Capability]:
    from core import permissions as P  # noqa: N812 — اختصارٌ يُقرأ به السجلُّ كجدول

    followup_writers = shared.followup_writers
    followup_columns = shared.followup_columns
    return [
        # ── الحضور والجدول ──────────────────────────────────────────
        _cap("attendance.mark", "رصدُ حضور الحصّة", P.ATTENDANCE_RECORD),
        _cap("operations.reports", "تقاريرُ الجدول والحضور", P.OPERATIONS_REPORTS),
        _cap(
            "operations.daily_absence",
            "غيابُ اليوم (تقريرُ غياب الطلبة اليوميّ)",
            P.DAILY_STUDENT_ABSENCE_REPORT,
            basis="قرارُ المالك D-273م: إدارةُ شؤون الطلاب كاملةً لمنسّق شؤون الطلبة، دون تقارير المعلّمين",
        ),
        # ── متابعة الغياب (W-20261013-011، بلاغ SOS-20261012-AC00) ───────────
        # الكتابةُ للمدير والنائب الإداريّ ومنسّق شؤون الطلبة على المدرسة، ولمشرف الجناح على جناحه
        # (النطاقُ في العرض بـ`student_scope_for`)؛ والنائبُ الأكاديميّ ومنسّقُ القسم يراقبان بلا تسجيل.
        _cap(
            "operations.absence_followup_view",
            "شاشةُ متابعة الغياب (مراقبة)",
            P.DAILY_STUDENT_ABSENCE_REPORT,
            basis="طلبُ المدير SOS-20261012-AC00؛ والنائبُ الأكاديميّ مراقبٌ فقط",
        ),
        _cap(
            "operations.absence_followup_record",
            "تسجيلُ الاتّصال والإجراء الإداريّ وتصحيحُهما واستلامُ الإجازة المرضيّة في متابعة الغياب",
            followup_writers,
            scope="المدرسة، ولمشرف الجناح جناحُه",
            basis="طلبُ المدير SOS-20261012-AC00؛ وقرارُ المالك D-431م (الرقمُ بلا اسم)",
        ),
        _cap(
            "operations.absence_followup_feedback",
            "قراءةُ التغذية الراجعة من وليّ الأمر (نصٌّ مشفَّر) في متابعة الغياب",
            followup_writers,
            scope="المدرسة، ولمشرف الجناح جناحُه",
            basis="PDPPL — نصٌّ حرٌّ قد يحمل بياناتٍ شخصيّة؛ وفتحُه يُدقَّق بلا نصّه",
        ),
        _cap(
            "operations.absence_followup_print",
            "طباعةُ كشفَي متابعة الغياب (التواصل والإجراءات)",
            followup_columns,
            scope="المدرسة",
            basis="قولُ المالك 2026-10-17 (W-20261017-024): الطباعةُ للمدير والنائب الإداريّ ومنسّق شؤون الطلبة وحدَهم",
        ),
        _cap(
            "operations.absence_followup_followup",
            "عمودا «المتابعة» (حالةُ التواصل وحالةُ الإجراء) في كشف متابعة الغياب",
            followup_columns,
            scope="المدرسة",
            basis="قولُ المالك 2026-10-14 (بلاغا 6E42 وFFED): المدير والنائبُ الإداريّ ومنسّقُ شؤون الطلاب وحدَهم",
        ),
        _cap(
            "operations.substitutes_manage",
            "تسجيلُ غياب معلّمٍ وتعيينُ بديله",
            P.OPERATIONS_SUBSTITUTES_MANAGE,
        ),
        _cap(
            "schedule.day",
            "جدولُ اليوم",
            {
                "principal",
                "vice_academic",
                "vice_admin",
                "coordinator",
                "teacher",
                "ese_teacher",
                "academic_advisor",
                "admin_supervisor",
                "student",
                "parent",
            },
            scope="جدولُ المستخدم نفسِه لغير القيادة",
        ),
        _cap(
            "schedule.weekly",
            "الجدولُ الأسبوعيّ",
            {
                "principal",
                "vice_academic",
                "vice_admin",
                "coordinator",
                "e_projects_coordinator",
                "teacher",
                "ese_teacher",
                "academic_advisor",
                "admin_supervisor",
                "admin",
            },
            scope="جدولُ المستخدم لغير من يتصفّح",
        ),
        _cap("schedule.view", "عرضُ الجدول والتبديلات", P.SCHEDULE_VIEW),
        _cap("schedule.browse", "تصفّحُ جداول الآخرين", P.SCHEDULE_BROWSE),
        _cap(
            "schedule.print",
            "طباعةُ الجدول وتصديرُه",
            P.SCHEDULE_BROWSE | {"teacher", "ese_teacher", "academic_advisor"},
            scope="جدولُ المستخدم لغير من يتصفّح",
        ),
        _cap(
            "schedule.preferences",
            "تفضيلاتُ المعلّم في الجدول",
            {
                "teacher",
                "ese_teacher",
                "coordinator",
                "activities_coordinator",
                "e_projects_coordinator",
            },
            scope="تفضيلاتُه هو",
        ),
        _cap(
            "schedule.preferences_view",
            "اطّلاعٌ على تفضيلات المعلّمين في الجدول",
            {"principal", "vice_academic", "coordinator"},
            scope="المدير والنائب الأكاديميّ: المدرسة؛ منسّق المادّة: قسمُه",
            basis=(
                "قرارُ المالك D-330م (W-20261010-026): قراءةٌ بلا تعديل؛ التعديلُ يبقى لصاحب "
                "التفضيل بـ`schedule.preferences` التي لا تُوسَّع"
            ),
        ),
        _cap("schedule.settings", "إعداداتُ الجدول والتفريغات", P.SCHEDULE_SETTINGS),
        _cap("schedule.admin", "إعدادُ الجدول الإداريّ", P.SCHEDULE_ADMIN),
        _cap("schedule.manage", "توزيعاتُ الموادّ", P.SCHEDULE_MANAGE),
        _cap(
            "schedule.operator",
            "مُشغِّلُ الجدول العامّ — إسنادُ الموادّ وتوليدُ الجدول",
            P.SCHEDULE_ADMIN,
            scope="المدرسة (كلُّ الأقسام)",
            basis=(
                "قرارُ المالك 2026-09-25 (التذكرة SOS-20260924-1CFE): قدرةٌ مفوَّضةٌ باسم المستخدم "
                "يمنحها ويسحبها المديرُ والنائبُ الأكاديميّ ومطوّرُ المنصّة — إدخالُ الإسناد لكلّ الأقسام "
                "بلا وقفِ المنسّقين، وتوليدُ الجدول؛ لا اعتمادَ ولا مراجعةَ ولا إعداداتٍ. الأدوارُ هنا من "
                "يولّد الجدولَ اليوم (`schedule.admin`) فلا يفقد أحدٌ ما يملك"
            ),
            grant=_delegated("schedule.operator"),
        ),
        _cap(
            "schedule.approve",
            "اعتمادُ الجدول",
            P.SCHEDULE_APPROVE,
            basis=(
                "قرارُ المالك 2026-09-25 (جلسةُ الجدول): المديرُ والنائبُ الأكاديميّ، والمطوّرُ استثناءً "
                "في أيّام الدوام بسببٍ إلزاميٍّ وتدقيق — ولا النائبُ الإداريّ. تُعرَّف هنا ويربطها بواجهة "
                "الاعتماد مسارُ الجدول"
            ),
        ),
        _cap(
            "swap.request",
            "طلبُ تبديل حصّة",
            {"teacher", "ese_teacher", "principal", "vice_academic", "vice_admin"},
        ),
        _cap(
            "swap.respond",
            "الردُّ على طلب تبديل",
            {"teacher", "ese_teacher", "coordinator", "principal", "vice_academic", "vice_admin"},
        ),
        _cap(
            "swap.approve",
            "اعتمادُ التبديل",
            {"coordinator", "principal", "vice_academic", "vice_admin", "platform_developer"},
            scope="منسّقا المادّتين",
        ),
        _cap(
            "compensatory.request",
            "طلبُ حصّةٍ تعويضيّة",
            {"teacher", "ese_teacher", "principal", "vice_academic", "vice_admin"},
        ),
        _cap(
            "compensatory.approve",
            "اعتمادُ الحصّة التعويضيّة",
            {"coordinator", "principal", "vice_academic", "vice_admin"},
        ),
    ]

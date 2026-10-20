"""قدراتُ مجال «شؤون الطلبة» — قسمٌ من سجلّ القدرات نُقل حرفاً بلا تغيير قدرةٍ ولا حامل (W-20261019-007)."""

from __future__ import annotations

from core.capabilities.base import Capability, Shared, _cap


def student_affairs_capabilities(shared: Shared) -> list[Capability]:
    from core import permissions as P  # noqa: N812 — اختصارٌ يُقرأ به السجلُّ كجدول
    from student_info.access import MODULE_ROLES as STUDENT_INFO_ROLES

    return [
        # ── شؤون الطلبة ─────────────────────────────────────────────
        _cap("student_affairs.manage", "إدارةُ سجلّات الطلبة", P.STUDENT_AFFAIRS_MANAGE),
        _cap(
            "student_affairs.view",
            "الاطّلاعُ على سجلّات الطلبة",
            P.STUDENT_REGISTER_READ,
            scope="المدرسة؛ المشرفُ الإداريُّ لشُعب جناحه (wings/scope.py)",
            basis=(
                "سجلُّ الطلبة يعرض اسمَ وليّ الأمر وهاتفَه — قاعدةُ الحاجة (PDPPL): منسّقُ الأنشطة يرث المنسّقَ "
                "ولا يتّصل بالأسر، فلا يرث هذه القدرةَ (ويبقى له ما يرثه من غيرها) — بطاقة W-20261010-012، حكم 0104"
            ),
            not_inherited_by={"activities_coordinator"},
        ),
        _cap(
            "student_affairs.follow_up",
            "متابعةُ حضور الطلبة وتأخّرهم وسلوكهم",
            P.STUDENT_FOLLOW_UP,
            scope="المدرسةُ للقيادة؛ المشرفُ الإداريُّ لشُعب جناحه (wings/scope.py)",
            basis="الدليل التنظيميّ 2026: متابعةُ الغياب اليوميّ والتأخّر الصباحيّ؛ وقرارُ المستخدم 2026-09-14: المشرفُ لجناحه فقط",
        ),
        _cap(
            "dashboard.absence_alert_names",
            "أسماءُ تنبيهات الغياب في لوحة الإداريّين",
            P.STUDENT_FOLLOW_UP | {"admin"},
            scope="المدرسةُ للقيادة وadmin؛ المشرفُ الإداريُّ لشُعب جناحه (wings/scope.py)",
            basis=(
                "قرارُ المالك 2026-10-03 (W-20261003-030): يبقى admin يرى أسماءَ قائمة التنبيهات "
                "بقدرةٍ مخصّصةٍ لها وحدَها، لا بمنح student_affairs.follow_up الذي يفتح ملفّاتِ الطلبة "
                "وحركاتِهم وسلوكَهم وتصديرَها والوسائطَ المحمية"
            ),
        ),
        _cap(
            "student_affairs.tardiness",
            "رصدُ التأخّر الصباحيّ وإلغاؤه",
            P.STUDENT_FOLLOW_UP,
            scope="المدرسةُ للقيادة؛ المشرفُ الإداريُّ لشُعب جناحه (wings/scope.py)",
            basis="الدليل التنظيميّ 2026 م 3.4.2.2: التأخّرُ الصباحيُّ على المشرف الإداريّ من أوّل مرّة",
        ),
        _cap("student_affairs.deactivate", "إيقافُ قيد طالب", P.STUDENT_DEACTIVATE),
        _cap(
            "student_affairs.transfers",
            "انتقالاتُ الطلبة (طلبٌ ومراجعةٌ وإتمام)",
            P.STUDENT_AFFAIRS_TRANSFERS,
            basis=(
                "إتمامُ الانتقال الصادر يعطّل عضويّةَ الطالب، فلا يُمنح من يملك إدخالَ البيانات وحدَه "
                "(W-20261001-020)؛ ومنسّقُ شؤون الطلبة منهم بقرار المالك D-265م"
            ),
        ),
        _cap(
            "student_affairs.transfer_approve",
            "اعتمادُ الانتقال الداخلي بين الشعب وإتمامُه ونقلُه المباشر",
            {"principal", "vice_admin"},
            basis=(
                "قرار المالك D-343م (2026-10-10): المنسّقُ يقدّم طلبَ النقل والنائبُ الإداريّ أو المدير يعتمده، "
                "ولهما النقلُ المباشرُ بلا اعتماد أحد؛ والمنسّق لا يدخلها (W-20261001-017)"
            ),
        ),
        _cap(
            "student_affairs.activities",
            "إدارةُ الأنشطة الطلابيّة",
            P.ACTIVITIES_MANAGE,
            basis="ضوابط البرامج والأنشطة ص3: الدخولُ للنائب الأكاديميّ وأخصائيّ الأنشطة",
        ),
        _cap(
            "students.import_export",
            "استيرادُ الطلبة وتصديرُهم",
            {"principal", "vice_admin", "vice_academic", "admin"},
        ),
        _cap(
            "student_info.read",
            "مركزُ معلومات الطالب",
            STUDENT_INFO_ROLES,
            scope="المدرسة للقيادة والجهات؛ المعلّمُ لطلبة شُعبه؛ المشرفُ الإداريُّ لشُعب جناحه",
            basis="قرارُ المستخدم: القراءةُ لكلّ من يُدرّس الطالب",
        ),
        _cap(
            "students.search",
            "البحثُ السريعُ عن الطلبة",
            # سحبٌ صريحٌ من أربعةٍ لا يبحث أحدُهم عن طالبٍ في عمله (قرارُ المالك D-192م، 2026-10-04) — والباقون كما كانوا:
            # لم نحصرها بأصحاب `reports.results` لأنّ مشرفَ الجناح ومن في حكمه يبحثون بها مقيَّدين بجناحهم (قرارُ 2026-09-15).
            P.ALL_STAFF_ROLES
            - {"messenger", "storekeeper", "lab_technician", "canteen_supervisor"},
            scope="عشرُ نتائجَ بحدٍّ أقصى",
            basis="قرارُ المالك D-192م: تُسحب من المندوب وأمين المخزن ومحضّر المختبر ومشرف المقصف",
        ),
    ]

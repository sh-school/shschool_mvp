"""
منطقُ مركز معلومات الطلبة — خارج الشاشات.

وأهمُّ ما فيه شريحةُ التحصيل: عتباتُها ليست جديدةً ولا مُختلَقة، بل هي
العتباتُ نفسها التي تلوّن بها المنصّةُ نتائجَ الطلاب منذ البداية في
`AnnualSubjectResult.grade_color_css` — ٨٠ و٦٥ و٥٠. ولو اخترعنا لها عتباتٍ
أخرى لصار للطالب مستويان مختلفان في شاشتين من المنصّة نفسها.
"""

from collections import OrderedDict, defaultdict

from django.db.models import Avg, Count, Q

from assessments.models import AnnualSubjectResult
from core.models.academic import ClassGroup, StudentEnrollment, grade_number
from student_affairs.models import StudentActivity
from student_info.models import NOTE_CATEGORIES, StudentNote

#: شرائحُ التحصيل من الأعلى إلى الأدنى: (المفتاح، الاسم، الحدّ الأدنى، لون).
#: والترتيبُ مقصود — `band_for` يمرّ عليها بالترتيب فيقف عند أوّل ما ينطبق.
ACHIEVEMENT_BANDS = (
    ("advanced", "متقدّم", 80, "#146356"),
    ("proficient", "متمكّن", 65, "#1D4E89"),
    ("basic", "مقبول", 50, "#8A6512"),
    ("below", "دون مستوى النجاح", 0, "#A8261E"),
)

BAND_LABELS = OrderedDict((key, label) for key, label, _, _ in ACHIEVEMENT_BANDS)
BAND_COLORS = {key: color for key, _, _, color in ACHIEVEMENT_BANDS}


def band_for(total):
    """شريحةُ درجةٍ من مئة — و`None` لمن لا نتيجةَ له بعد."""
    if total is None:
        return None
    value = float(total)
    for key, _label, floor, _color in ACHIEVEMENT_BANDS:
        if value >= floor:
            return key
    return "below"


# ── الشُّعب ومدخلُ المركز ─────────────────────────────────────────────


def sections_with_counts(class_groups):
    """الشُّعبُ ومعها عددُ طلاب كلٍّ منها — استعلامٌ واحدٌ لا استعلامٌ لكلّ شعبة."""
    return class_groups.annotate(
        student_count=Count("enrollments", filter=Q(enrollments__is_active=True), distinct=True)
    ).select_related("supervisor")


def students_of_section(class_group):
    """طلابُ شعبةٍ مرتّبين بالاسم."""
    return (
        StudentEnrollment.objects.filter(class_group=class_group, is_active=True)
        .select_related("student", "student__profile")
        .order_by("student__full_name")
    )


# ── المستويات التعليمية وربطها بالتحصيل ──────────────────────────────


def achievement_overview(school, year, grade="", track=""):
    """توزيعُ الطلاب على شرائح التحصيل، مقطوعاً بالصفّ والمسار.

    يُرجع ثلاثة أشياء: إجماليَّ التوزيع، وتوزيعاً لكلّ صفّ، وتوزيعاً لكلّ
    مادّة — فالسؤالُ «أين نقف؟» لا يُجاب بعددٍ واحد.
    """
    results = (
        AnnualSubjectResult.objects.filter(school=school, academic_year=year)
        .exclude(annual_total__isnull=True)
        .select_related("setup__subject", "setup__class_group")
    )
    if grade:
        results = results.filter(setup__class_group__grade=grade)
    if track:
        results = results.filter(setup__class_group__track=track)

    overall = dict.fromkeys(BAND_LABELS, 0)
    by_grade = defaultdict(lambda: dict.fromkeys(BAND_LABELS, 0))
    by_subject = defaultdict(lambda: dict.fromkeys(BAND_LABELS, 0))

    for r in results.only("annual_total", "setup"):
        band = band_for(r.annual_total)
        if band is None:
            continue
        overall[band] += 1
        by_grade[r.setup.class_group.get_grade_display()][band] += 1
        by_subject[r.setup.subject.name_ar][band] += 1

    return {
        "overall": overall,
        "by_grade": _sorted_rows(by_grade),
        "by_subject": _sorted_rows(by_subject),
        "total": sum(overall.values()),
    }


def _sorted_rows(mapping):
    """صفوفُ جدولٍ مرتّبةً تنازلياً بنسبة «دون مستوى النجاح» — الأحوجُ أوّلاً."""
    rows = []
    for name, counts in mapping.items():
        total = sum(counts.values())
        rows.append(
            {
                "name": name,
                "counts": counts,
                "total": total,
                "below_pct": round(counts["below"] * 100 / total, 1) if total else 0.0,
            }
        )
    return sorted(rows, key=lambda r: (-r["below_pct"], r["name"]))


def grade_and_track_choices(school, year):
    """الصفوفُ والمساراتُ الموجودةُ فعلاً هذا العام — لا القائمةُ النظريّة."""
    groups = ClassGroup.objects.filter(school=school, academic_year=year, is_active=True)
    grades = [
        (g, dict(ClassGroup.GRADES).get(g, g))
        for g in sorted(set(groups.values_list("grade", flat=True)), key=grade_number)
    ]
    tracks = [
        (t, dict(ClassGroup.TRACKS).get(t, t))
        for t in groups.exclude(track="")
        .values_list("track", flat=True)
        .distinct()
        .order_by("track")
    ]
    return grades, tracks


# ── ملفّ الطالب ───────────────────────────────────────────────────────


def student_results(student, year):
    """نتائجُ الطالب في مواده، ومع كلّ نتيجةٍ شريحتُها."""
    rows = []
    for r in (
        AnnualSubjectResult.objects.filter(student=student, academic_year=year)
        .select_related("setup__subject")
        .order_by("setup__subject__name_ar")
    ):
        band = band_for(r.annual_total)
        rows.append(
            {
                "subject": r.setup.subject.name_ar,
                "total": r.annual_total,
                "letter": r.letter_grade,
                "status": r.get_status_display(),
                "band": band,
                "band_label": BAND_LABELS.get(band, "—"),
                "band_color": BAND_COLORS.get(band, "#838C99"),
            }
        )
    return rows


def student_average(student, year):
    """متوسّطُ الطالب السنويّ وشريحتُه — أو `None` إن لم تُرصد نتيجةٌ بعد."""
    avg = (
        AnnualSubjectResult.objects.filter(student=student, academic_year=year)
        .exclude(annual_total__isnull=True)
        .aggregate(v=Avg("annual_total"))["v"]
    )
    if avg is None:
        return None
    band = band_for(avg)
    return {
        "value": round(float(avg), 1),
        "band": band,
        "band_label": BAND_LABELS[band],
        "band_color": BAND_COLORS[band],
    }


def notes_by_category(student, year):
    """ملاحظاتُ الطالب مجموعةً بجهاتها، وكلُّ جهةٍ حاضرةٌ ولو خالية."""
    grouped = OrderedDict((key, []) for key, _ in NOTE_CATEGORIES)
    for note in (
        StudentNote.objects.filter(student=student, academic_year=year)
        .select_related("created_by")
        .order_by("-occurred_on", "-created_at")
    ):
        grouped[note.category].append(note)
    return grouped


def student_activities(student, year):
    return (
        StudentActivity.objects.filter(student=student, academic_year=year)
        .select_related("recorded_by")
        .order_by("-date")
    )


def current_class_group(student, year):
    enrollment = (
        StudentEnrollment.objects.filter(
            student=student, is_active=True, class_group__academic_year=year
        )
        .select_related("class_group")
        .first()
    )
    return enrollment.class_group if enrollment else None

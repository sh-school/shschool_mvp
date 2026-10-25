"""[SECURITY] رؤيةُ جداول الزملاء للمعلّم المقيَّد (W-20261013-022، D-432م).

يرى زملاءَ مادّته ومن يدرّس شُعبَه وشُعبَه؛ وغيرُهم 404 عبر الورقة وPDF وExcel وخيارات التبديل
والحصص الحرّة. والمنسّق يرى الكلّ. ويومُ التفريغ المفضّل لا يظهر في أيٍّ من ذلك (D-341م).
"""

import datetime as dt

import pytest
from django.test import Client
from django.urls import reverse

from core.academic_calendar import academic_year_for_school
from core.models import ClassGroup, CustomUser
from core.models.access import Membership, Role
from operations.models import ScheduleSlot, Subject
from operations.schedule_visibility import visible_class_ids, visible_teacher_ids


@pytest.fixture
def world(db, school):
    YEAR = academic_year_for_school(school)

    def person(name, role="teacher"):
        user = CustomUser.objects.create(
            must_change_password=False,
            national_id=f"287{abs(hash(name)) % 10**8:08d}",
            full_name=name,
        )
        r, _ = Role.objects.get_or_create(school=school, name=role)
        Membership.objects.create(user=user, school=school, role=r)
        return user

    math = Subject.objects.create(school=school, name_ar="الرياضيات")
    art = Subject.objects.create(school=school, name_ar="الفنون")
    sci = Subject.objects.create(school=school, name_ar="العلوم")
    c1 = ClassGroup.objects.create(school=school, grade="G7", section="1", academic_year=YEAR)
    c2 = ClassGroup.objects.create(school=school, grade="G7", section="2", academic_year=YEAR)
    c3 = ClassGroup.objects.create(school=school, grade="G9", section="3", academic_year=YEAR)

    def slot(teacher, cg, subject, period):
        return ScheduleSlot.objects.create(
            school=school,
            teacher=teacher,
            class_group=cg,
            subject=subject,
            day_of_week=0,
            period_number=period,
            start_time=dt.time(7, 10),
            end_time=dt.time(7, 55),
            academic_year=YEAR,
        )

    me = person("أنا")
    same_subject = person("زميل المادة")
    same_class = person("زميل الشعبة")
    stranger = person("غريب")
    coordinator = person("منسّق", "coordinator")
    mine = slot(me, c1, math, 1)
    slot(same_subject, c2, math, 1)
    slot(same_class, c1, art, 2)
    theirs = slot(stranger, c3, sci, 1)
    return dict(  # noqa: C408
        school=school, me=me, same_subject=same_subject, same_class=same_class,
        stranger=stranger, coordinator=coordinator, c1=c1, c2=c2, c3=c3,
        mine=mine, theirs=theirs,
    )  # fmt: skip


def _get(user, url):
    c = Client()
    c.force_login(user)
    return c.get(url, HTTP_HOST="localhost")


def test_visible_sets(world):
    w = world
    assert visible_teacher_ids(w["school"], w["me"]) == {
        w["me"].pk, w["same_subject"].pk, w["same_class"].pk,
    }  # fmt: skip
    assert visible_class_ids(w["school"], w["me"]) == {w["c1"].pk}


@pytest.mark.parametrize("who", ["same_subject", "same_class", "me"])
def test_teacher_reads_allowed_colleagues(world, who):
    url = reverse("weekly_schedule") + f"?view=teacher&teacher={world[who].id}"
    assert _get(world["me"], url).status_code == 200


def test_teacher_cannot_read_a_stranger(world):
    url = reverse("weekly_schedule") + f"?view=teacher&teacher={world['stranger'].id}"
    assert _get(world["me"], url).status_code == 404


def test_teacher_class_scope(world):
    base = reverse("weekly_schedule") + "?view=class&class="
    assert _get(world["me"], base + str(world["c1"].id)).status_code == 200
    assert _get(world["me"], base + str(world["c3"].id)).status_code == 404


def test_print_and_exports_are_guarded(world):
    q = f"?view=teacher&teacher={world['stranger'].id}"
    for name in ("schedule_print", "weekly_schedule"):
        assert _get(world["me"], reverse(name) + q).status_code == 404
        for fmt in ("pdf", "excel"):
            assert _get(world["me"], reverse(name) + f"{q}&export={fmt}").status_code == 404


def test_picker_lists_only_allowed(world):
    body = _get(world["me"], reverse("schedule_print")).content.decode()
    assert f'<option data-view="teacher" data-teacher="{world["same_subject"].id}"' in body
    assert f'<option data-view="teacher" data-teacher="{world["same_class"].id}"' in body
    assert f'<option data-view="teacher" data-teacher="{world["stranger"].id}"' not in body


def test_coordinator_sees_everyone(world):
    url = reverse("weekly_schedule") + f"?view=teacher&teacher={world['stranger'].id}"
    assert _get(world["coordinator"], url).status_code == 200


def test_swap_options_only_for_own_slot(world):
    own = reverse("swap_options", args=[world["mine"].id])
    other = reverse("swap_options", args=[world["theirs"].id])
    assert _get(world["me"], own).status_code == 200
    assert _get(world["me"], other).status_code == 404
    assert _get(world["coordinator"], other).status_code == 200


def test_free_slots_only_for_visible_teacher(world):
    ok = reverse("teacher_free_slots", args=[world["same_class"].id])
    no = reverse("teacher_free_slots", args=[world["stranger"].id])
    assert _get(world["me"], ok).status_code == 200
    assert _get(world["me"], no).status_code == 404
    assert _get(world["coordinator"], no).status_code == 200


def test_swap_cancel_and_compensatory_respond_stay_owner_only():
    """الحارسُ في الخدمة: لا يلغي ولا يردّ إلا الطرفُ المعنيّ (القوانين 12–14)."""
    import inspect

    from operations.services import CompensatoryService, SwapService

    assert "cancelled_by != swap.teacher_a" in inspect.getsource(SwapService.cancel_swap)
    assert "comp.colleague_id != user.pk" in inspect.getsource(CompensatoryService.colleague_decide)
    assert "comp.teacher_id != user.pk" in inspect.getsource(CompensatoryService.withdraw)

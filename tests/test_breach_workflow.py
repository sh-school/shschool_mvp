"""
tests/test_breach_workflow.py
خدمةُ انتقالات الخرق + التدقيق + الصلاحيّةُ بالقدرة + تحقّقُ نموذج التسجيل.

كانت `_admin_only` تحجب من تمنحه القدرةُ `breach.manage` (النائبان و`admin`) بينما
يصلهم تنبيهُ الجرس برابط الصفحة؛ وكان `create` يسقط بـ500 عند حقلٍ غائبٍ أو رقمٍ فاسد.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import AuditLog, BreachReport
from tests.conftest import MembershipFactory, RoleFactory, UserFactory


@pytest.fixture
def breach(db, school, principal_user):
    return BreachReport.objects.create(
        school=school,
        title="تسرب بيانات",
        description="وصف",
        discovered_at=timezone.now(),
        reported_by=principal_user,
    )


def _user_with_role(school, role_name):
    role = RoleFactory(school=school, name=role_name)
    user = UserFactory(full_name=f"مستخدم {role_name}")
    MembershipFactory(user=user, school=school, role=role)
    return user


def _post_status(c, breach, status):
    return c.post(f"/breach/{breach.pk}/status/", {"status": status}, follow=True)


@pytest.mark.django_db
class TestBreachTransitions:
    def test_discovered_cannot_jump_to_resolved(self, client_as, principal_user, breach):
        """الإغلاقُ بلا تقييمٍ ولا إشعارٍ مرفوض، والرسالةُ تظهر للمستخدم."""
        resp = _post_status(client_as(principal_user), breach, "resolved")
        breach.refresh_from_db()
        assert breach.status == "discovered"
        assert breach.resolved_at is None
        assert "لا يمكن الانتقال" in resp.content.decode()

    def test_assessing_can_close_without_notice_and_it_is_audited(
        self, client_as, principal_user, breach
    ):
        c = client_as(principal_user)
        _post_status(c, breach, "assessing")
        _post_status(c, breach, "resolved")
        breach.refresh_from_db()
        assert breach.status == "resolved" and breach.ncsa_notified_at is None
        last = AuditLog.objects.filter(object_id=str(breach.pk), action="update").latest(
            "timestamp"
        )
        assert last.changes["closed_without_ncsa_notice"] is True

    def test_resolved_is_terminal(self, client_as, principal_user, breach):
        c = client_as(principal_user)
        for status in ("notified", "resolved", "discovered"):
            _post_status(c, breach, status)
        breach.refresh_from_db()
        assert breach.status == "resolved"

    def test_every_transition_writes_an_audit_row(self, client_as, principal_user, breach):
        c = client_as(principal_user)
        _post_status(c, breach, "assessing")
        _post_status(c, breach, "notified")
        rows = list(
            AuditLog.objects.filter(object_id=str(breach.pk), action="update").order_by("timestamp")
        )
        assert [(r.changes["from"], r.changes["to"]) for r in rows] == [
            ("discovered", "assessing"),
            ("assessing", "notified"),
        ]
        assert rows[1].user_id == principal_user.pk
        assert "ncsa_notified_at" in rows[1].changes

    def test_same_status_is_a_no_op_without_new_audit_row(self, client_as, principal_user, breach):
        c = client_as(principal_user)
        _post_status(c, breach, "notified")
        before = AuditLog.objects.filter(object_id=str(breach.pk)).count()
        _post_status(c, breach, "notified")
        assert AuditLog.objects.filter(object_id=str(breach.pk)).count() == before


@pytest.mark.django_db
class TestBreachDashboardAndDeadlineDisplay:
    def test_overdue_count_is_computed_in_the_database(
        self, client_as, school, principal_user, breach
    ):
        """فائتةٌ مفتوحة تُعَدّ؛ ومُشعَرةٌ أو مغلقةٌ أو حاضرةٌ لا تُعَدّ."""
        old = timezone.now() - timedelta(hours=80)

        def make(status):
            return BreachReport.objects.create(
                school=school,
                title=status,
                description="d",
                discovered_at=old,
                status=status,
                reported_by=principal_user,
            )

        make("discovered")
        make("assessing")
        make("notified")
        make("resolved")
        stats = client_as(principal_user).get("/breach/").context["stats"]
        assert stats["overdue"] == 2  # الحاضرةُ (breach) لم تفت
        assert stats["active"] == 3  # 2 فائتتان + الحاضرة
        assert stats["notified"] == 1 and stats["resolved"] == 1

    def test_under_an_hour_left_is_said_explicitly(self, client_as, principal_user, breach):
        breach.ncsa_deadline = timezone.now() + timedelta(minutes=20)
        breach.save()
        html = client_as(principal_user).get(f"/breach/{breach.pk}/").content.decode()
        assert "أقلّ من ساعة" in html


@pytest.mark.django_db
class TestNcsaTextIsFilledNotSent:
    """النصُّ يُملأ من بيانات الخرق؛ والإرسالُ قرارُ المسؤول لا المنصّة."""

    def _post(self, client_as, user, **over):
        data = {
            "title": "تسريب ملف الطلاب",
            "description": "وصف",
            "severity": "high",
            "data_type_affected": "academic",
            "affected_count": "120",
            "discovered_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
            "immediate_action": "إغلاق المنفذ",
        }
        data.update(over)
        return client_as(user).post("/breach/create/", data)

    def test_blank_text_is_filled_from_the_breach_fields(self, client_as, principal_user):
        self._post(client_as, principal_user)
        text = BreachReport.objects.get().notification_text
        assert "تسريب ملف الطلاب" in text
        assert "بيانات أكاديمية" in text and "120" in text and "إغلاق المنفذ" in text
        assert "{" not in text  # لا حقلَ متروكاً بلا قيمة
        assert "لم يُسجَّل بعد" in text  # الاحتواءُ لم يُكتب

    def test_a_text_written_by_the_user_is_kept(self, client_as, principal_user):
        self._post(client_as, principal_user, notification_text="نصٌّ كتبه المسؤول")
        assert BreachReport.objects.get().notification_text == "نصٌّ كتبه المسؤول"

    def test_registering_never_marks_ncsa_as_notified(self, client_as, principal_user):
        """التسجيلُ لا يرسل ولا يختم: الختمُ بزرّ «تم إشعار NCSA» وحدَه."""
        self._post(client_as, principal_user)
        breach = BreachReport.objects.get()
        assert breach.status == "discovered" and breach.ncsa_notified_at is None

    def test_detail_says_it_is_not_sent_automatically(self, client_as, principal_user):
        self._post(client_as, principal_user)
        breach = BreachReport.objects.get()
        html = client_as(principal_user).get(f"/breach/{breach.pk}/").content.decode()
        assert "لا تُرسل المنصّةُ هذا النصَّ تلقائيّاً" in html


@pytest.mark.django_db
class TestBreachAccessFollowsCapability:
    @pytest.mark.parametrize(
        "role", ["principal", "vice_admin", "vice_academic", "admin", "platform_developer"]
    )
    def test_capability_roles_open_list_and_detail(self, client_as, school, breach, role):
        c = client_as(_user_with_role(school, role))
        assert c.get("/breach/").status_code == 200
        assert c.get(f"/breach/{breach.pk}/").status_code == 200

    def test_vice_admin_can_record_the_notice(self, client_as, school, breach):
        c = client_as(_user_with_role(school, "vice_admin"))
        c.post(f"/breach/{breach.pk}/status/", {"status": "notified"})
        breach.refresh_from_db()
        assert breach.status == "notified" and breach.ncsa_notified_at is not None

    @pytest.mark.parametrize("role", ["principal", "vice_admin", "admin", "platform_developer"])
    def test_menu_link_shows_for_everyone_who_can_open_the_page(self, client_as, school, role):
        """كان القسمُ مقيَّداً بالقيادة فلا يرى `admin` رابطَ صفحةٍ يفتحها."""
        html = client_as(_user_with_role(school, role)).get("/breach/").content.decode()
        assert "خروقات البيانات" in html

    def test_module_gate_roles_come_from_the_capability(self):
        """مصدرٌ واحد: لا قائمتان تنجرفان."""
        from core.capabilities import capability
        from core.module_registry import get_protected_paths

        assert set(get_protected_paths()["/breach/"]) == set(
            capability("breach.manage").expanded_roles
        )


@pytest.mark.django_db
class TestBreachEdit:
    def _data(self, **over):
        data = {
            "title": "تسرب بيانات",
            "description": "وصفٌ محدَّث",
            "severity": "high",
            "data_type_affected": "personal",
            "affected_count": "7",
            "immediate_action": "",
            "containment_action": "",
            "evidence_notes": "لقطة من سجلّ الوصول",
            "notification_text": "",
        }
        data.update(over)
        return data

    def test_edit_saves_and_audits_the_changed_fields(self, client_as, principal_user, breach):
        resp = client_as(principal_user).post(f"/breach/{breach.pk}/edit/", self._data())
        breach.refresh_from_db()
        assert resp.status_code == 302
        assert breach.description == "وصفٌ محدَّث" and breach.evidence_notes.startswith("لقطة")
        row = AuditLog.objects.filter(object_id=str(breach.pk), action="update").get()
        assert "description" in row.changes["edited_fields"]

    def test_discovery_time_and_deadline_cannot_be_edited(self, client_as, principal_user, breach):
        """عليهما مهلةُ الـ72 ساعة المعتمَدة قانونيّاً."""
        original = (breach.discovered_at, breach.ncsa_deadline)
        client_as(principal_user).post(
            f"/breach/{breach.pk}/edit/",
            self._data(discovered_at="2020-01-01T00:00", ncsa_deadline="2020-01-04T00:00"),
        )
        breach.refresh_from_db()
        assert (breach.discovered_at, breach.ncsa_deadline) == original

    def test_a_resolved_breach_is_a_record_not_editable(self, client_as, principal_user, breach):
        c = client_as(principal_user)
        _post_status(c, breach, "notified")
        _post_status(c, breach, "resolved")
        resp = c.post(f"/breach/{breach.pk}/edit/", self._data(description="تغيير"), follow=True)
        breach.refresh_from_db()
        assert breach.description == "وصف"
        assert "لا يُعدَّل خرقٌ مُغلق" in resp.content.decode()
        html = c.get(f"/breach/{breach.pk}/").content.decode()
        assert f"/breach/{breach.pk}/edit/" not in html

    def test_notice_text_is_locked_once_notified(self, client_as, principal_user, breach):
        """هو سجلُّ ما أُرسل فعلاً إلى الجهة."""
        c = client_as(principal_user)
        BreachReport.objects.filter(pk=breach.pk).update(notification_text="النصُّ المُرسَل")
        _post_status(c, breach, "notified")
        c.post(f"/breach/{breach.pk}/edit/", self._data(notification_text="نصٌّ آخر"))
        breach.refresh_from_db()
        assert breach.notification_text == "النصُّ المُرسَل"

    def test_regenerate_refreshes_the_notice_text_from_the_updated_data(
        self, client_as, principal_user, breach
    ):
        c = client_as(principal_user)
        BreachReport.objects.filter(pk=breach.pk).update(notification_text="نصٌّ قديم")
        c.post(
            f"/breach/{breach.pk}/edit/",
            self._data(title="عنوانٌ جديد", affected_count="55", regenerate_notice="on"),
        )
        text = BreachReport.objects.get(pk=breach.pk).notification_text
        assert "عنوانٌ جديد" in text and "55" in text and "نصٌّ قديم" not in text

    def test_without_the_box_a_hand_written_text_is_kept(self, client_as, principal_user, breach):
        BreachReport.objects.filter(pk=breach.pk).update(notification_text="نصُّ المسؤول")
        client_as(principal_user).post(
            f"/breach/{breach.pk}/edit/",
            self._data(title="عنوانٌ جديد", notification_text="نصُّ المسؤول"),
        )
        assert BreachReport.objects.get(pk=breach.pk).notification_text == "نصُّ المسؤول"

    def test_regenerate_is_ignored_once_notified(self, client_as, principal_user, breach):
        c = client_as(principal_user)
        BreachReport.objects.filter(pk=breach.pk).update(notification_text="النصُّ المُرسَل")
        _post_status(c, breach, "notified")
        c.post(f"/breach/{breach.pk}/edit/", self._data(title="جديد", regenerate_notice="on"))
        assert BreachReport.objects.get(pk=breach.pk).notification_text == "النصُّ المُرسَل"

    def test_edit_of_another_school_breach_is_404(self, client_as, principal_user, breach):
        from tests.conftest import SchoolFactory

        other = SchoolFactory()
        foreign = BreachReport.objects.create(
            school=other, title="x", description="d", discovered_at=timezone.now()
        )
        assert client_as(principal_user).get(f"/breach/{foreign.pk}/edit/").status_code == 404


@pytest.mark.django_db
class TestBreachAssigneeAndHistory:
    def test_assignee_choices_are_only_those_who_can_open_the_page(
        self, client_as, school, principal_user
    ):
        from breach.forms import BreachReportForm
        from tests.conftest import SchoolFactory

        vice = _user_with_role(school, "vice_admin")
        teacher = _user_with_role(school, "teacher")
        outsider = _user_with_role(SchoolFactory(), "principal")
        ids = set(
            BreachReportForm(school=school)
            .fields["assigned_to"]
            .queryset.values_list("pk", flat=True)
        )
        assert vice.pk in ids and principal_user.pk in ids
        assert teacher.pk not in ids and outsider.pk not in ids

    def test_assignee_and_evidence_are_saved_on_create(self, client_as, school, principal_user):
        vice = _user_with_role(school, "vice_admin")
        client_as(principal_user).post(
            "/breach/create/",
            {
                "title": "خرق",
                "description": "وصف",
                "severity": "medium",
                "data_type_affected": "personal",
                "affected_count": "1",
                "discovered_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
                "assigned_to": str(vice.pk),
                "evidence_notes": "دليل",
            },
        )
        breach = BreachReport.objects.get()
        assert breach.assigned_to_id == vice.pk and breach.evidence_notes == "دليل"

    def test_a_non_eligible_assignee_is_rejected(self, client_as, school, principal_user):
        teacher = _user_with_role(school, "teacher")
        resp = client_as(principal_user).post(
            "/breach/create/",
            {
                "title": "خرق",
                "description": "وصف",
                "severity": "medium",
                "data_type_affected": "personal",
                "affected_count": "1",
                "discovered_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
                "assigned_to": str(teacher.pk),
            },
        )
        assert resp.status_code == 200 and not BreachReport.objects.exists()

    def test_history_shows_who_did_what(self, client_as, principal_user, breach):
        c = client_as(principal_user)
        _post_status(c, breach, "assessing")
        html = c.get(f"/breach/{breach.pk}/").content.decode()
        assert "سجلّ التغييرات" in html
        assert "الحالة: مكتشف ← قيد التقييم" in html
        assert principal_user.full_name in html

    def test_it_technician_is_no_longer_admitted(self, client_as, school):
        """أقلُّ صلاحية: القدرةُ هي المرجع، والبوّابةُ لا تسع من لا تسعه."""
        c = client_as(_user_with_role(school, "it_technician"))
        assert c.get("/breach/").status_code == 403


@pytest.mark.django_db
class TestBreachCreateValidation:
    def test_affected_count_has_an_upper_bound(self, client_as, principal_user):
        resp = client_as(principal_user).post(
            "/breach/create/",
            {
                "title": "خرق",
                "description": "وصف",
                "severity": "medium",
                "data_type_affected": "personal",
                "affected_count": "1000001",
                "discovered_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
            },
        )
        assert resp.status_code == 200 and not BreachReport.objects.exists()
        assert "لا يزيد على" in resp.content.decode()

    def _data(self, **over):
        data = {
            "title": "خرق",
            "description": "وصف",
            "severity": "medium",
            "data_type_affected": "personal",
            "affected_count": "3",
            "discovered_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
        }
        data.update(over)
        return data

    def test_missing_title_is_a_form_error_not_a_500(self, client_as, principal_user):
        data = self._data()
        del data["title"]
        resp = client_as(principal_user).post("/breach/create/", data)
        assert resp.status_code == 200
        assert "عنوانُ الخرق مطلوب" in resp.content.decode()
        assert not BreachReport.objects.exists()

    def test_non_numeric_count_is_a_form_error(self, client_as, principal_user):
        resp = client_as(principal_user).post("/breach/create/", self._data(affected_count="abc"))
        assert resp.status_code == 200
        assert "عددُ المتأثرين" in resp.content.decode()
        assert not BreachReport.objects.exists()

    def test_bad_discovery_time_is_rejected_not_replaced_by_now(self, client_as, principal_user):
        """وقتُ الاكتشاف أساسُ مهلة الـ72 ساعة: لا يُستبدل بصمتٍ بـ«الآن»."""
        resp = client_as(principal_user).post("/breach/create/", self._data(discovered_at="أمس"))
        assert resp.status_code == 200
        assert not BreachReport.objects.exists()

    def test_future_discovery_time_is_rejected(self, client_as, principal_user):
        """موعدُ NCSA = الاكتشافُ + 72 ساعة: وقتٌ مستقبليٌّ يمدّد المهلةَ."""
        later = (timezone.localtime() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
        resp = client_as(principal_user).post("/breach/create/", self._data(discovered_at=later))
        assert resp.status_code == 200
        assert "لا يكون في المستقبل" in resp.content.decode()
        assert not BreachReport.objects.exists()

    def test_valid_post_is_audited_and_redirects_to_detail(self, client_as, principal_user):
        resp = client_as(principal_user).post("/breach/create/", self._data())
        breach = BreachReport.objects.get()
        assert resp.status_code == 302 and resp.url == f"/breach/{breach.pk}/"
        assert breach.affected_count == 3 and breach.reported_by_id == principal_user.pk
        assert AuditLog.objects.filter(object_id=str(breach.pk), action="create").exists()

    def test_missing_count_defaults_to_zero(self, client_as, principal_user):
        data = self._data()
        del data["affected_count"]
        client_as(principal_user).post("/breach/create/", data)
        assert BreachReport.objects.get().affected_count == 0

"""تخطيطُ صندوق الإشعارات: مجموعاتٌ بالأيّام، رقاقاتٌ بأعدادها، وتحديدُ الكلّ لا يمحو القائمة."""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from django.urls import reverse
from django.utils import timezone

from notifications.inbox_presentation import (
    INBOX_COLUMNS,
    group_by_day,
    group_by_type,
    inbox_query,
)
from notifications.models import InAppNotification

TODAY = date(2026, 9, 17)


def _at(days_ago: int, hour: int = 10):
    moment = datetime(TODAY.year, TODAY.month, TODAY.day, hour) - timedelta(days=days_ago)
    return SimpleNamespace(created_at=timezone.make_aware(moment))


class TestGroupByDay:
    def test_buckets_are_ordered_and_empty_ones_dropped(self):
        items = [_at(0), _at(0), _at(1), _at(3), _at(30)]
        groups = group_by_day(items, today=TODAY)
        assert [g["key"] for g in groups] == ["today", "yesterday", "week", "older"]
        assert [g["count"] for g in groups] == [2, 1, 1, 1]

        assert [g["key"] for g in group_by_day([_at(9)], today=TODAY)] == ["older"]
        assert group_by_day([], today=TODAY) == []

    def test_columns_are_sequential_so_reading_order_is_time_order(self):
        items = [_at(0, hour=23 - i) for i in range(7)]
        columns = group_by_day(items, today=TODAY)[0]["columns"]
        assert len(columns) == INBOX_COLUMNS
        assert [n for col in columns for n in col] == items

    def test_a_single_item_is_one_column_not_three_empty_ones(self):
        assert len(group_by_day([_at(0)], today=TODAY)[0]["columns"]) == 1


def _typed(event_type: str):
    return SimpleNamespace(event_type=event_type, created_at=None)


class TestGroupByType:
    LABELS = {"behavior": "مخالفة سلوكية", "grade": "درجات جديدة", "general": "إشعار عام"}

    def test_largest_group_first_and_ties_keep_the_label_order(self):
        items = [_typed("general"), _typed("grade"), _typed("general"), _typed("behavior")]
        groups = group_by_type(items, self.LABELS)
        assert [(g["key"], g["label"], g["count"]) for g in groups] == [
            ("general", "إشعار عام", 2),
            ("behavior", "مخالفة سلوكية", 1),
            ("grade", "درجات جديدة", 1),
        ]

    def test_order_inside_a_group_is_kept(self):
        first, second = _typed("grade"), _typed("grade")
        columns = group_by_type([first, second], self.LABELS)[0]["columns"]
        assert [n for col in columns for n in col] == [first, second]


class TestInboxQuery:
    def test_defaults_leave_no_query_string(self):
        assert inbox_query() == ""
        assert inbox_query(group="day") == ""

    def test_every_state_is_carried(self):
        assert inbox_query(type="grade", unread=True, group="type") == (
            "?type=grade&unread=1&group=type"
        )


@pytest.mark.django_db
class TestInboxView:
    def _make(self, user, school, **kw):
        return InAppNotification.objects.create(
            user=user, school=school, title=kw.pop("title", "إشعار"), **kw
        )

    def test_only_types_present_in_the_inbox_get_a_chip(self, client_as, school, teacher_user):
        self._make(teacher_user, school, event_type="grade")
        self._make(teacher_user, school, event_type="grade")
        self._make(teacher_user, school, event_type="general")

        resp = client_as(teacher_user).get(reverse("notification_inbox"))

        assert [t[:3] for t in resp.context["event_types"]] == [
            ("grade", "درجات جديدة", 2),
            ("general", "إشعار عام", 1),
        ]
        assert resp.context["total_count"] == 3

    def test_the_chosen_type_keeps_its_chip_even_when_empty(self, client_as, school, teacher_user):
        self._make(teacher_user, school, event_type="grade")
        resp = client_as(teacher_user).get(reverse("notification_inbox") + "?type=clinic")
        assert ("clinic", "زيارة عيادة", 0) in [t[:3] for t in resp.context["event_types"]]

    def test_unread_only_filters_the_list(self, client_as, school, teacher_user):
        unread = self._make(teacher_user, school, title="جديد")
        self._make(teacher_user, school, title="قديم", is_read=True)

        resp = client_as(teacher_user).get(reverse("notification_inbox") + "?unread=1")

        assert resp.context["notifications"] == [unread]
        assert resp.context["unread_only"] is True

    def test_group_by_type_groups_the_whole_inbox_by_type(self, client_as, school, teacher_user):
        self._make(teacher_user, school, event_type="grade")
        self._make(teacher_user, school, event_type="grade")
        self._make(teacher_user, school, event_type="clinic")

        resp = client_as(teacher_user).get(reverse("notification_inbox") + "?group=type")

        assert resp.context["group_mode"] == "type"
        assert [(g["key"], g["count"]) for g in resp.context["groups"]] == [
            ("grade", 2),
            ("clinic", 1),
        ]
        # الرقاقاتُ تحمل التجميعَ معها، فالترشيحُ لا يُرجع الصفحةَ إلى الأيّام.
        assert all("group=type" in t[3] for t in resp.context["event_types"])

    def test_mark_all_read_is_a_plain_form_that_returns_to_the_inbox(
        self, client_as, school, teacher_user
    ):
        """كان زرَّ HTMX يضع ردَّ الخادم «0» مكانَ القائمة كلّها."""
        self._make(teacher_user, school)
        c = client_as(teacher_user)
        body = c.get(reverse("notification_inbox")).content.decode()
        assert 'hx-target="#notif-list"' not in body

        resp = c.post(reverse("mark_all_read"), HTTP_HX_REQUEST="true")

        assert resp.status_code == 302
        assert not InAppNotification.objects.filter(user=teacher_user, is_read=False).exists()

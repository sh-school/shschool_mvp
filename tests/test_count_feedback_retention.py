"""أمرُ عدّ الاحتفاظ لرسائل المطوّر: أرقامٌ صحيحة، قراءةٌ تجميعيّةٌ فقط، لا محتوى ولا تعديل (W-20261001-002)."""

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from developer_feedback.models import DeveloperMessage

pytestmark = pytest.mark.django_db


def _make(n: int, age_days: int) -> None:
    for i in range(n):
        m = DeveloperMessage.objects.create(
            ticket_number=f"T{age_days:04d}{i:04d}",
            user_id_hash="a" * 64,
            subject="موضوعٌ اختباريّ",
            body="نصٌّ اختباريٌّ طويلٌ بما يكفي",
        )
        DeveloperMessage.objects.filter(pk=m.pk).update(
            created_at=timezone.now() - timedelta(days=age_days)
        )


def _run() -> str:
    out = StringIO()
    call_command("count_feedback_retention", stdout=out)
    return out.getvalue()


def test_counts_total_older_than_90_days_and_oldest_date():
    _make(2, 10)
    _make(3, 120)
    oldest = (timezone.localtime(timezone.now() - timedelta(days=120))).strftime("%Y-%m-%d")
    text = _run()
    assert "الإجمالي: 5" in text
    assert "الأقدم من 90 يومًا: 3" in text
    assert f"أقدم تاريخ: {oldest}" in text


def test_empty_table_reports_zero_and_no_date():
    text = _run()
    assert "الإجمالي: 0" in text and "الأقدم من 90 يومًا: 0" in text and "لا رسائل" in text


def test_read_only_single_aggregate_without_content_columns_and_no_mutation():
    _make(2, 120)
    before = list(DeveloperMessage.objects.values_list("pk", "updated_at"))
    with CaptureQueriesContext(connection) as ctx:
        _run()
    sqls = [q["sql"].lower() for q in ctx.captured_queries]
    assert len(sqls) == 1 and sqls[0].startswith("select")
    for forbidden in ("subject", "body", "user_id_hash", "context_json", "ticket_number"):
        assert forbidden not in sqls[0]
    assert not any(s.startswith(("update", "delete", "insert")) for s in sqls)
    assert before == list(DeveloperMessage.objects.values_list("pk", "updated_at"))

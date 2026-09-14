"""مدّةُ الاحتفاظ المعطوبة في البيئة تعطّل الحذفَ — ولا تُسقط المنصّة.

يومَ 2026-09-14 دُمجت سياسةُ الاحتفاظ (#268)، فصار `base.py` يقرأ
`PDPPL_DATA_RETENTION_DAYS` بـ`int()` عند الاستيراد. وكانت القيمةُ على خدمة
الويب في Railway `730)` — خطأٌ مطبعيٌّ قديمٌ لم يظهر لأنّ أحداً لم يقرأها —
فسقطت مرحلةُ الإصدار مرّتين بـ`ValueError` قبل الهجرات، وتوقّف كلُّ نشرٍ على
main. والإعداداتُ تُقرأ عند إقلاع كلّ عمليّة (الويب والعامل وBeat والأوامر)،
فعطبُ إعدادٍ فرعيٍّ فيها عطبٌ للمنصّة كلِّها.

والحكمُ هنا بالقيمة التي أسقطت الإنتاجَ حرفيّاً:
- الإقلاعُ بإعدادات الإنتاج ينجح.
- `retention_days()` يُرجع صفراً (تعطيل) — المدّةُ الخاطئة لا تُخمَّن بافتراض،
  لأنّ الخطأَ في اتّجاه الحذف لا يُسترجع.
- ويُسجَّل خطأٌ يسمّي القيمة، فلا يبقى التعطيلُ صامتاً.
"""

import logging

import pytest

from core.retention import retention_days
from tests.test_production_runtime_settings import _load_production_settings

BROKEN = "730)"  # القيمةُ التي كانت على Railway حرفيّاً


def test_production_settings_import_with_the_broken_value():
    result = _load_production_settings(PDPPL_DATA_RETENTION_DAYS=BROKEN)
    assert result.returncode == 0, (
        "إعداداتُ الإنتاج لا تُستورد بقيمة احتفاظٍ معطوبة — المنصّةُ لن تُقلع:\n" + result.stderr
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("730", 730),
        (" 365 ", 365),
        (730, 730),
        ("0", 0),
        ("", 0),
        ("-5", 0),
    ],
)
def test_valid_values_parse(settings, raw, expected):
    settings.PDPPL_DATA_RETENTION_DAYS = raw
    assert retention_days() == expected


@pytest.mark.parametrize("raw", [BROKEN, "730 days", "730x", "2y"])
def test_unreadable_value_disables_and_logs(settings, caplog, raw):
    settings.PDPPL_DATA_RETENTION_DAYS = raw
    with caplog.at_level(logging.ERROR, logger="core.retention"):
        days = retention_days()
    assert days == 0, "قيمةٌ لا تُفهم يجب أن تعطّل الحذف لا أن تُخمَّن"
    assert any(
        "PDPPL_DATA_RETENTION_DAYS" in r.getMessage() for r in caplog.records
    ), "التعطيلُ بسبب قيمةٍ معطوبة صامت — يجب أن يُسجَّل خطأً"
